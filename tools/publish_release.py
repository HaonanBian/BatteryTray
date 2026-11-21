"""Publishes the release of the app on GitHub.

The token is read from a file instead of the environment, so that it does
not end up in the shell history. Put the token into ``tools/.gh_token``
(one line, no spaces around it) and run::

    .venv/Scripts/python.exe tools/publish_release.py

The token needs the ``repo`` scope. It can be thrown away after the
release is out.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN_FILE = HERE / ".gh_token"
SCRIPT = HERE / "publish_release_impl.py"


def read_token() -> str:
    """The token, from the file or from the environment."""
    token = (os.environ.get("GH_TOKEN")
             or os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        return token
    if TOKEN_FILE.is_file():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    return ""


def main() -> int:
    token = read_token()
    if not token:
        print("没有找到令牌。")
        print()
        print("两种方式，任选其一：")
        print()
        print("一、放到文件里（推荐，不会留在历史记录里）：")
        print(f"    把令牌写进 {TOKEN_FILE}")
        print()
        print("二、设成环境变量：")
        print("    set GH_TOKEN=ghp_你的令牌")
        print()
        print("令牌需要 repo 权限：")
        print("    https://github.com/settings/tokens/new")
        print("    → Fine-grained tokens → 选中 BatteryTray 仓库")
        print("    → Repository permissions → Contents: Read and write")
        return 1

    # The token is passed on to the other script through the environment,
    # so it is never written into a command line.
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
