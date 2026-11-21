"""Tests the download of an update against the things that go wrong.

Three cases are checked: a connection that drops halfway, a server
that answers with an error page instead of the file, and a download
that simply works.
"""

from __future__ import annotations

import http.server
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batterytray import update  # noqa: E402

GOOD = b"MZ" + b"\x00" * 4096


class Handler(http.server.BaseHTTPRequestHandler):
    """Serves a file, or breaks the connection on purpose."""

    def log_message(self, *args):
        """Keeps the output quiet."""

    def do_GET(self):
        mode = self.path.strip("/")
        if mode == "drop":
            # Breaks the connection the first time and works after that.
            with self.server.counter_lock:
                self.server.counters[mode] = self.server.counters.get(mode, 0) + 1
                count = self.server.counters[mode]
            if count == 1:
                self.send_response(200)
                self.send_header("Content-Length", str(len(GOOD)))
                self.end_headers()
                self.wfile.write(GOOD[:100])
                self.wfile.flush()
                self.close_connection = True
                try:
                    self.connection.close()
                except OSError:
                    pass
                return
            body = GOOD
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if mode == "errorpage":
            body = b"<html>not a program</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if mode == "flaky":
            # Fails the first two times and works the third time.
            with self.server.counter_lock:
                self.server.counters[mode] = self.server.counters.get(mode, 0) + 1
                count = self.server.counters[mode]
            if count < 3:
                self.send_response(503)
                self.end_headers()
                return
            body = GOOD
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = GOOD
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.counter = 0
    server.counter_lock = threading.Lock()
    # Every case gets its own counter, so that they do not disturb
    # each other.
    server.counters = {}
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    work = Path(tempfile.mkdtemp())
    failures = 0

    # 1. A download that works.
    try:
        target = update.download_file(f"{base}/good", work / "good.exe",
                                      attempts=3)
        ok = target.read_bytes() == GOOD
        print(f"正常下载              -> {'通过' if ok else '失败'}")
        failures += 0 if ok else 1
    except Exception as exc:
        print(f"正常下载              -> 失败 {exc}")
        failures += 1

    # 2. A connection that drops halfway. The retry has to fix it.
    try:
        target = update.download_file(f"{base}/drop", work / "drop.exe",
                                      attempts=3)
        ok = target.read_bytes() == GOOD
        print(f"连接中断后重试        -> {'通过' if ok else '失败'}")
        failures += 0 if ok else 1
    except Exception as exc:
        print(f"连接中断后重试        -> 失败 {exc}")
        failures += 1

    # 3. A server that fails twice and then works.
    try:
        target = update.download_file(f"{base}/flaky", work / "flaky.exe",
                                      attempts=3)
        ok = target.read_bytes() == GOOD
        print(f"服务器报错后重试      -> {'通过' if ok else '失败'}")
        failures += 0 if ok else 1
    except Exception as exc:
        print(f"服务器报错后重试      -> 失败 {exc}")
        failures += 1

    # 4. A file that is not a program has to be refused.
    try:
        update.download_file(f"{base}/errorpage", work / "bad.exe",
                             attempts=2)
        print("拒绝无效文件          -> 失败（没有报错）")
        failures += 1
    except update.UpdateError as exc:
        good = "不是有效的程序文件" in str(exc)
        print(f"拒绝无效文件          -> {'通过' if good else '失败'} ({exc})")
        failures += 0 if good else 1

    # 5. Nothing may be left behind in the folder.
    leftovers = list(work.glob("batterytray-download-*"))
    print(f"没有残留临时文件      -> {'通过' if not leftovers else '失败'}")
    failures += 0 if not leftovers else 1

    server.shutdown()
    print()
    print("全部通过" if failures == 0 else f"{failures} 项失败")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
