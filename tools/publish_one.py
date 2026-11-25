"""Uploads one file of the release to GitHub.

The token is read from the environment, so it never ends up in a file or
in the shell history.

Usage::

    set GH_TOKEN=ghp_xxx
    .venv/Scripts/python.exe tools/publish_one.py BatteryTray-1.3.1.exe
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT / "release"

OWNER = "HaonanBian"
REPO = "BatteryTray"
TAG = "v1.3.4"

API = f"https://api.github.com/repos/{OWNER}/{REPO}"


def request(method: str, url: str, token: str, data=None):
    """Sends a request to the GitHub API and returns the answer."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "BatteryTray",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"GitHub 拒绝了请求 {exc.code}: {detail[:400]}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"连不上 GitHub：{exc.reason}")


def upload(upload_url: str, path: Path, token: str) -> dict:
    """Uploads one file as an asset of the release.

    The file is sent as it is, without a form around it. The name of
    the file goes into the address, because GitHub reads it from there
    and not from the body.

    An earlier version of this script wrapped the file in a multipart
    form. GitHub accepted those files, but it kept the form around
    them, so the file that came back started with the form's boundary
    instead of the real content. The downloaded file was therefore
    broken and could not be run.
    """
    base = upload_url.split("{")[0]
    url = base + "?name=" + urllib.parse.quote(path.name)

    # The file is streamed to the server, so it does not have to be held
    # in memory a second time.
    size = path.stat().st_size
    with path.open("rb") as handle:
        req = urllib.request.Request(
            url, data=handle, method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "BatteryTray",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(size),
            })
        print(f"上传 {path.name} ({size:,} 字节)…", flush=True)
        try:
            with urllib.request.urlopen(req, timeout=900) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise SystemExit(f"上传失败 {exc.code}: {detail[:400]}")


def main() -> int:
    token = (os.environ.get("GH_TOKEN")
             or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        print("没有找到令牌。")
        return 1

    names = sys.argv[1:]
    if not names:
        print("用法：publish_one.py <文件名> [<文件名> …]")
        return 1

    release = request("GET", f"{API}/releases/tags/{TAG}", token)
    upload_url = release.get("upload_url", "")
    have = {a["name"]: a for a in release.get("assets", [])}

    for name in names:
        path = RELEASE_DIR / name
        if not path.is_file():
            print(f"找不到文件：{path}")
            return 1

        # An asset that is already there would be rejected, so the old
        # one is removed first.
        old = have.get(name)
        if old:
            print(f"  删除旧的 {name}…")
            request("DELETE", f"{API}/releases/assets/{old['id']}", token)

        result = upload(upload_url, path, token)
        print(f"  完成 → {result.get('browser_download_url')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
