#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从浏览器的下载记录/历史里，把学校课表 iCal 的“订阅链接”挖出来。

为什么需要它：下载到本地的 icalexport.ics 是一次性快照，
而带 authtoken 的 export_execute.php 链接每次访问都会返回最新课表——
那个链接才是能做“自动更新”的关键。

用法：python tools/find_ical_link.py
说明：只读，不改动任何浏览器数据；浏览器运行时也能安全读取（immutable 模式）。
"""
import glob
import os
import sqlite3
import sys

# Chrome 系（含 Edge/Brave）的 History、Firefox 的 places.sqlite
CHROMIUM_ROOTS = [
    r"C:\Users\bt\AppData\Local\Google\Chrome\User Data",
    r"C:\Users\bt\AppData\Local\Microsoft\Edge\User Data",
    r"C:\Users\bt\AppData\Local\BraveSoftware\Brave-Browser\User Data",
    r"C:\Users\bt\AppData\Roaming\Mozilla\Firefox\Profiles",
]

KEYWORDS = ("ical", ".ics", "calendar", "export_execute", "export.php", "webcal")


def find_databases():
    files = []
    for root in CHROMIUM_ROOTS:
        if not os.path.isdir(root):
            continue
        if "Firefox" in root:
            files += glob.glob(os.path.join(root, "*", "places.sqlite"))
        else:
            files += glob.glob(os.path.join(root, "*", "History"))
    return files


def open_readonly(path):
    uri = "file:" + path.replace("\\", "/") + "?immutable=1"
    return sqlite3.connect(uri, uri=True)


def human(ts):
    try:
        return str(ts)[:19]
    except Exception:
        return "?"


def scan(path):
    hits = []
    try:
        con = open_readonly(path)
        cur = con.cursor()
        # 1) 下载记录：.ics 文件是从哪个 URL 下载的
        try:
            for row in cur.execute(
                "SELECT current_path, target_path, tab_url, referrer, site_url, "
                "datetime(start_time/1000000-11644473600,'unixepoch','localtime') "
                "FROM downloads ORDER BY start_time DESC LIMIT 2000"
            ):
                blob = " ".join(str(x) for x in row).lower()
                if any(k in blob for k in KEYWORDS):
                    hits.append(("下载记录", human(row[5]), row[2] or row[3] or row[4] or row[1]))
        except sqlite3.Error:
            pass
        # 2) 浏览历史：直接出现过导出链接
        try:
            for row in cur.execute(
                "SELECT url, title, "
                "datetime(last_visit_time/1000000-11644473600,'unixepoch','localtime') "
                "FROM urls WHERE url LIKE '%export%' OR url LIKE '%calendar%' OR url LIKE '%ical%' OR url LIKE '%webcal%' "
                "ORDER BY last_visit_time DESC LIMIT 200"
            ):
                hits.append(("浏览历史", human(row[2]), row[0]))
        except sqlite3.Error:
            pass
        con.close()
    except Exception as e:  # noqa: BLE001
        print(f"  (打不开 {path}: {e})")
    return hits


def main():
    files = find_databases()
    if not files:
        print("没找到任何浏览器数据库")
        return 1
    print(f"找到 {len(files)} 个浏览器数据库\n")
    total = 0
    for path in files:
        hits = scan(path)
        if not hits:
            continue
        browser = "Chrome" if "Chrome" in path else ("Edge" if "Edge" in path else ("Brave" if "Brave" in path else "Firefox"))
        print(f"===== {browser} · {os.path.basename(os.path.dirname(path))} =====")
        seen = set()
        for kind, when, url in hits:
            if url in seen:
                continue
            seen.add(url)
            total += 1
            print(f"  [{kind}] {when}")
            print(f"    {url}")
        print()
    if not total:
        print("没找到课表相关链接 —— 可能不是用浏览器下载的，或换了 profile。")
        return 2
    print("提示：带 authtoken 的链接 = 你的个人凭据，别发到公开场合。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
