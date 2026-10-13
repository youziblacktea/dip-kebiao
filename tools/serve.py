#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地预览服务器：正确返回 .webmanifest 的 MIME，方便在电脑上先试装 PWA。

用法：python tools/serve.py dist 8000
然后浏览器打开 http://127.0.0.1:8000/
（PWA 安装只在 https 或 localhost 下可用，所以本地预览必须用 localhost/IP 而不是 file://）
"""
import functools
import http.server
import socketserver
import sys
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json",
        ".js": "text/javascript",
        ".json": "application/json",
        ".png": "image/png",
    }

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Service-Worker-Allowed", "/")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def main():
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    if not directory.is_dir():
        raise SystemExit(f"目录不存在：{directory}")
    handler = functools.partial(Handler, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", port), handler) as httpd:
        print(f"预览目录：{directory}")
        print(f"电脑访问：http://127.0.0.1:{port}/")
        print(f"手机访问（同一 WiFi）：http://<本机局域网IP>:{port}/")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
