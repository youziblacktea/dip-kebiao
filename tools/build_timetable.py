#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 DIPLOMA 的 iCal 导出生成离线课表 App（PWA）。

输入：DIPLOMA 的 Moodle/iCal 导出。
      本地默认读 output/pdf/DIPLOMA-course-calendar.ics；
      自动更新时由 GitHub Actions 传入订阅链接下载下来的文件。
输出：dist/（网站产物）
      dist/index.html            自包含 App（单文件也能直接发到手机用）
      dist/manifest.webmanifest  PWA 清单
      dist/sw.js                 Service Worker（离线缓存 + 错误页防护）
      dist/icons/*.png           应用图标
      dist/data/timetable.json   结构化课表数据
      DIPLOMA-课表-PWA.zip       打包好的上传包
      DIPLOMA-课表.ics           原始日历文件备份

用法：
    python tools/make_icons.py            # 图标只需生成一次（改了设计再跑）
    python tools/build_timetable.py [源 .ics]
"""
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DEFAULT_SRC = Path(r"H:\我的工作区\DIPLOMA相关\output\pdf\DIPLOMA-course-calendar.ics")
TZ = ZoneInfo("Europe/Berlin")
APP_NAME = "DIPLOMA 课表"
APP_SHORT = "课表"


def unescape(s: str) -> str:
    return (s.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\")).strip()


def parse_ics(text: str):
    """展开折行并解析 VEVENT（时间统一转成柏林本地时间）。"""
    text = re.sub(r"\r?\n[ \t]", "", text)
    events = []
    for block in text.split("BEGIN:VEVENT")[1:]:
        props = {}
        for line in block.split("END:VEVENT")[0].splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                props[key.split(";")[0].strip()] = val.strip()
        if "DTSTART" not in props:
            continue

        def to_berlin(value: str) -> datetime:
            if value.endswith("Z"):
                return datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S").replace(
                    tzinfo=timezone.utc).astimezone(TZ)
            return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=TZ)

        detail = unescape(props.get("DESCRIPTION", ""))
        room = re.search(r"Raum:\s*(.*?)\s*(?:Dozent:|$)", detail)
        teacher = re.search(r"Dozent:\s*(.*)$", detail)
        events.append({
            "start": to_berlin(props["DTSTART"]),
            "end": to_berlin(props.get("DTEND", props["DTSTART"])),
            "name": unescape(props.get("SUMMARY", "")),
            "room": room.group(1).strip() if room else "",
            "teacher": teacher.group(1).strip() if teacher else "",
        })
    events.sort(key=lambda e: e["start"])
    return events


def merge(events):
    """把同一门课、同一教室老师、时间连续的分钟块合并成一节课。"""
    merged = []
    for e in events:
        last = merged[-1] if merged else None
        if (last and last["end"] == e["start"] and last["name"] == e["name"]
                and last["room"] == e["room"] and last["teacher"] == e["teacher"]):
            last["end"] = e["end"]
        else:
            merged.append({"start": e["start"], "end": e["end"], "name": e["name"],
                           "room": e["room"], "teacher": e["teacher"]})
    return merged


def data_version(text: str) -> str:
    """课表的“版本日期”＝所有事件里最新的 LAST-MODIFIED。

    这样课表没变时版本号也不变，自动更新不会每天产生无意义的提交；
    DTSTAMP 每次导出都会刷新，只能当兜底。
    """
    for pattern in (r"LAST-MODIFIED:(\d{8})T", r"DTSTAMP:(\d{8})T"):
        stamps = re.findall(pattern, text)
        if stamps:
            newest = max(stamps)
            return f"{newest[:4]}-{newest[4:6]}-{newest[6:]}"
    return datetime.now(TZ).strftime("%Y-%m-%d")


def build_data(events, merged, generated):
    days = defaultdict(list)
    for s in merged:
        days[s["start"].date().isoformat()].append({
            "s": s["start"].strftime("%H:%M"), "e": s["end"].strftime("%H:%M"),
            "t": s["name"], "r": s["room"], "p": s["teacher"],
        })
    for key in days:
        days[key].sort(key=lambda x: x["s"])

    first = events[0]["start"].date()
    last = events[-1]["start"].date()
    first_mon = first - timedelta(days=first.weekday())
    last_mon = last - timedelta(days=last.weekday())

    weeks, mon, n = [], first_mon, 1
    while mon <= last_mon:
        iso = mon.isocalendar()
        weeks.append({"n": n, "kw": iso[1], "year": iso[0], "mon": mon.isoformat()})
        mon += timedelta(days=7)
        n += 1

    subjects = [name for name, _ in Counter(e["name"] for e in events).most_common()]
    meta = {
        "tz": "Europe/Berlin",
        "generated": generated,
        "source": f"DIPLOMA Online Campus iCal 导出（课表最后更新 {generated}）",
        "range": [first.isoformat(), last.isoformat()],
        "subjects": subjects,
        "total": len(merged),
        "periods": len(events),
        "days": len(days),
    }
    return {"meta": meta, "weeks": weeks, "days": dict(sorted(days.items()))}


def manifest_json(data):
    return {
        "name": APP_NAME,
        "short_name": APP_SHORT,
        "description": "DIPLOMA 离线课表：今天上什么课、下一节课还有多久",
        "lang": "zh-CN",
        "start_url": "./index.html",
        "scope": "./",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f4f6f9",
        "theme_color": "#163453",
        "icons": [
            {"src": "./icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "./icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "./icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }


def clean_dist():
    if DIST.exists():
        assert DIST.name == "dist" and DIST.parent == ROOT, f"拒绝删除可疑路径：{DIST}"
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    (DIST / "icons").mkdir()
    (DIST / "data").mkdir()


def clean_old_artifacts():
    """删掉早期放在根目录的旧产物，避免用户拿错文件（已移到 dist/）。

    在 CI（GitHub Actions）里必须跳过：那时仓库根目录本身就是发布出去的网站。
    """
    if os.environ.get("CI"):
        print("CI 环境：跳过根目录清理")
        return
    for p in [ROOT / "index.html", ROOT / "data", ROOT / "DIPLOMA-课表-App.zip"]:
        if p.is_dir():
            shutil.rmtree(p)
            print("清理旧目录", p.name)
        elif p.exists():
            p.unlink()
            print("清理旧文件", p.name)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not src.exists():
        raise SystemExit(f"找不到源文件：{src}")

    text = src.read_text(encoding="utf-8")
    events = parse_ics(text)
    if not events:
        raise SystemExit("解析出的课表是空的，源文件可能有问题")
    merged = merge(events)
    data = build_data(events, merged, data_version(text))
    version = data["meta"]["generated"]

    clean_old_artifacts()
    clean_dist()

    # 1) App 本体（自包含，数据内嵌）
    tpl = (ROOT / "src" / "app.template.html").read_text(encoding="utf-8")
    if "/*__DATA__*/null" not in tpl:
        raise SystemExit("模板缺少 /*__DATA__*/null 占位符")
    (DIST / "index.html").write_text(
        tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"))),
        encoding="utf-8")

    # 2) PWA 清单
    (DIST / "manifest.webmanifest").write_text(
        json.dumps(manifest_json(data), ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) Service Worker
    sw = (ROOT / "src" / "sw.template.js").read_text(encoding="utf-8")
    if "__VERSION__" not in sw:
        raise SystemExit("sw.template.js 缺少 __VERSION__ 占位符")
    (DIST / "sw.js").write_text(sw.replace("__VERSION__", version), encoding="utf-8")

    # 4) 图标
    icon_dir = ROOT / "src" / "icons"
    icons = [p for p in sorted(icon_dir.glob("*.png")) if not p.name.startswith("_")]
    if len(icons) < 4:
        raise SystemExit("图标不足，请先运行 python tools/make_icons.py")
    for p in icons:
        shutil.copyfile(p, DIST / "icons" / p.name)

    # 5) 结构化数据（供查看/二次利用，App 本身不依赖它）
    (DIST / "data" / "timetable.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # 6) 原始日历备份
    shutil.copyfile(src, ROOT / "DIPLOMA-课表.ics")

    # 7) 上传包
    app_zip = ROOT / "DIPLOMA-课表-PWA.zip"
    with zipfile.ZipFile(app_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DIST.rglob("*")):
            if p.is_file():
                z.write(p, str(p.relative_to(DIST)))
        z.write(ROOT / "README.md", "README.md")

    meta = data["meta"]
    print(f"源事件 {meta['periods']} 条 -> 合并后 {meta['total']} 节课 / {meta['days']} 天 / {len(data['weeks'])} 周")
    print(f"课程范围 {meta['range'][0]} ~ {meta['range'][1]}，科目 {len(meta['subjects'])} 门，版本 {version}")
    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"dist/ 共 {len([p for p in DIST.rglob('*') if p.is_file()])} 个文件 {total} bytes；zip {app_zip.stat().st_size} bytes")


if __name__ == "__main__":
    main()
