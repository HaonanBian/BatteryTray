"""Creates the GitHub release for the app and uploads the files.

This script is the one that does the work. It expects the token in the
environment and is called by :mod:`publish_release`, which reads the token
from a file or from the environment.

Usage::

    set GH_TOKEN=ghp_xxx
    .venv/Scripts/python.exe tools/publish_release_impl.py
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
TITLE = "BatteryTray 1.3.4"

API = f"https://api.github.com/repos/{OWNER}/{REPO}"

# The files that make up the release, in the order they are shown to the
# user: the installer first, then the portable archive and the single file
# copy.
ASSETS = [
    "BatteryTray-Setup-1.3.3.exe",
    "BatteryTray-1.3.3-portable.zip",
    "BatteryTray-1.3.3.exe",
]

NOTES = "NOTES-1.3.3.md"


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
        raise SystemExit(f"GitHub 拒绝了请求 {exc.code}: {detail[:500]}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"连不上 GitHub：{exc.reason}")


def upload_asset(upload_url: str, path: Path, token: str) -> None:
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
    # The placeholder in the upload URL has to be replaced by the name of
    # the file.
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
        print(f"    上传 {path.name} ({size:,} 字节)…", end="", flush=True)
        try:
            with urllib.request.urlopen(req, timeout=900) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            print(f" 失败 {exc.code}: {detail[:300]}")
            raise SystemExit(1)
    print(" 完成")


def main() -> int:
    token = (os.environ.get("GH_TOKEN")
             or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        print("没有找到令牌。")
        return 1

    # Check that the token works and who it belongs to.
    user = request("GET", "https://api.github.com/user", token)
    print(f"认证成功：{user.get('login')}")

    # The release may already be there from an earlier attempt.
    try:
        release = request("GET", f"{API}/releases/tags/{TAG}", token)
        print(f"release {TAG} 已经存在，将更新它。")
    except SystemExit:
        print(f"创建 release {TAG}…")
        notes = (RELEASE_DIR / NOTES).read_text(encoding="utf-8")
        release = request("POST", f"{API}/releases", token, data={
            "tag_name": TAG,
            "name": TITLE,
            "body": notes,
            "draft": False,
            "prerelease": False,
            "make_latest": "true",
        })
        print(f"    已创建，id = {release.get('id')}")

    # The assets that are already there would be uploaded a second time,
    # so they are removed first.
    have = {a.get("name") for a in release.get("assets", [])}
    if have:
        print(f"    已有的附件：{sorted(have)}，先删除")
    for asset in release.get("assets", []):
        request("DELETE", f"{API}/releases/assets/{asset['id']}", token)

    upload_url = release.get("upload_url", "")
    if not upload_url:
        raise SystemExit("release 没有 upload_url")

    for name in ASSETS:
        path = RELEASE_DIR / name
        if not path.is_file():
            raise SystemExit(f"找不到文件：{path}")
        upload_asset(upload_url, path, token)

    # Read the release back to make sure everything is in place.
    final = request("GET", f"{API}/releases/tags/{TAG}", token)
    print()
    print("完成：")
    print(f"  tag      : {final.get('tag_name')}")
    print(f"  页面     : {final.get('html_url')}")
    print(f"  draft    : {final.get('draft')}")
    print(f"  附件     : {[a['name'] for a in final.get('assets', [])]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
