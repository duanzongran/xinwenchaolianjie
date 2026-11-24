#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻超链接（中国之声 21:00-22:00）播客 RSS 生成器
数据源：云听官方接口 https://ytmsout.radio.cn/web/appProgram/listByDate
只存链接，不下载音频。

设计要点：
1. 每天只跑一次（北京 22:30）。episodes.json 按 date 去重，feed.xml 每次全量重建。
2. 每次回扫最近 N 天，当天没抓到的期会在第二天的运行里自动补上。
3. 只有「文件已完整」才入库：读 Content-Range 拿总字节数，< MIN_BYTES 视为上传中，跳过。
4. guid 固定用日期（xwclj-2026-11-23），节目 id 变了也不会丢已听记录。
5. lastBuildDate 取最新一集的 pubDate，没有新集就不会产生空 commit。
"""
import hashlib
import time
import json
import os
import sys
import datetime
import urllib.parse
import urllib.request
from email.utils import format_datetime
from xml.sax.saxutils import escape

KEY = 'f0fc4c668392f9f9a447e48584c214ee'
BASE = 'https://ytmsout.radio.cn'
BROADCAST_ID = '639'          # 中国之声
PROGRAM_NAME = '新闻超链接'
TZ = datetime.timezone(datetime.timedelta(hours=8))

# 该节目完整一期约 80-87 MB；低于此值视为尚未上传完成
MIN_BYTES = 60 * 1024 * 1024

FEED_TITLE = '新闻超链接（中国之声）'
FEED_DESC = '中央广播电视总台中国之声《新闻超链接》，每天 21:00-22:00 播出。音频来自云听，仅存链接不存文件。'
FEED_LINK = 'https://www.radio.cn/pc-portal/erji/radioStation.html?id=24'
AUTHOR = '中国之声'

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, 'episodes.json')
FEED = os.path.join(HERE, 'feed.xml')


def api(path, params):
    tm = str(int(time.time() * 1000))
    s = '&'.join(f'{k}={params[k]}' for k in sorted(params)) + '&timestamp=' + tm + '&key=' + KEY
    sign = hashlib.md5(s.encode()).hexdigest().upper()
    url = BASE + path + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'Content-Type': 'application/json', 'equipmentId': '0000', 'platformCode': 'WEB',
        'timestamp': tm, 'sign': sign, 'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.radio.cn/pc-portal/erji/radioStation.html?id=24'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode('utf-8'))


def get_meta(url):
    """返回 (是否完整可用, 总字节数, Content-Type)

    用 Range: bytes=0-0 只取 1 字节，从 Content-Range 的 "bytes 0-0/87481043"
    拿到文件真实总长度，以此判断音频是否已经上传完成。
    """
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-0'})
        with urllib.request.urlopen(req, timeout=20) as r:
            ct = (r.headers.get('Content-Type') or '').lower()
            cr = r.headers.get('Content-Range') or ''
            if '/' in cr:
                total = int(cr.split('/')[-1])
            else:
                total = int(r.headers.get('Content-Length') or 0)
        audio = ('m4a' in ct or 'mp4' in ct or 'mpeg' in ct or 'aac' in ct)
        return audio and total >= MIN_BYTES, total, ct
    except Exception as e:
        print(f'  [warn] meta fail: {e}')
        return False, 0, ''


def load_store():
    if os.path.exists(STORE):
        with open(STORE, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_store(items):
    with open(STORE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def crawl_days(days):
    """回扫最近 days 天，返回 {日期: 条目}，只收录已完整的音频"""
    got = {}
    today = datetime.datetime.now(TZ).date()
    for i in range(days):
        d = today - datetime.timedelta(days=i)
        ds = d.strftime('%Y-%m-%d')
        try:
            res = api('/web/appProgram/listByDate', {'date': ds, 'broadcastId': BROADCAST_ID})
            lst = res.get('data') or []
        except Exception as e:
            print(f'[{ds}] 接口失败 {e}')
            continue
        hit = None
        for it in lst:
            if PROGRAM_NAME in (it.get('programName') or ''):
                hit = it
                break
        if not hit:
            print(f'[{ds}] 无《{PROGRAM_NAME}》')
            continue
        url = hit.get('playUrlHigh') or hit.get('playUrlLow')
        if not url:
            print(f'[{ds}] 条目已建但还没上音频')
            continue
        ok, size, ct = get_meta(url)
        if not ok:
            print(f'[{ds}] 音频未完整（{size} bytes），留到下次再抓')
            continue
        start = datetime.datetime.fromtimestamp(hit['startTime'] / 1000, TZ)
        got[ds] = {
            'date': ds,
            'id': str(hit['id']),
            'title': f'{ds} 新闻超链接' + ('（重播）' if '(重播)' in hit.get('programName', '') else ''),
            'url': url,
            'type': 'audio/mpeg' if url.lower().endswith('.mp3') else 'audio/mp4',
            'size': size,
            'start': start.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'start_ts': hit['startTime'],
        }
        print(f'[{ds}] OK {hit["id"]} {size / 1048576:.1f}MB')
    return got


def build_feed(items):
    items = sorted(items, key=lambda x: x['start_ts'], reverse=True)
    if items:
        newest = datetime.datetime.fromtimestamp(items[0]['start_ts'] / 1000, TZ)
    else:
        newest = datetime.datetime.now(TZ)
    parts = [f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>{escape(FEED_TITLE)}</title>
<link>{escape(FEED_LINK)}</link>
<description>{escape(FEED_DESC)}</description>
<language>zh-cn</language>
<itunes:author>{escape(AUTHOR)}</itunes:author>
<itunes:image href="https://duanzongran.github.io/xinwenchaolianjie/cover.jpg"/>
<image><url>https://duanzongran.github.io/xinwenchaolianjie/cover.jpg</url><title>{escape(FEED_TITLE)}</title><link>{escape(FEED_LINK)}</link></image>
<lastBuildDate>{format_datetime(newest)}</lastBuildDate>
<atom:link href="https://duanzongran.github.io/xinwenchaolianjie/feed.xml" rel="self" type="application/rss+xml"/>
''']
    for it in items:
        dt = datetime.datetime.fromtimestamp(it['start_ts'] / 1000, TZ)
        parts.append(f'''<item>
<title>{escape(it['title'])}</title>
<description>{escape(it['title'] + "，中国之声《新闻超链接》当期完整录音。")}</description>
<enclosure url="{escape(it['url'])}" type="{it.get('type', 'audio/mp4')}" length="{it.get('size', 0)}"/>
<guid isPermaLink="false">xwclj-{it['date']}</guid>
<pubDate>{format_datetime(dt)}</pubDate>
<itunes:duration>01:00:00</itunes:duration>
</item>
''')
    parts.append('</channel>\n</rss>\n')
    with open(FEED, 'w', encoding='utf-8') as f:
        f.write(''.join(parts))


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(f'回扫最近 {days} 天 ...')
    store = load_store()
    by_date = {x['date']: x for x in store}
    fresh = crawl_days(days)

    added = updated = 0
    for ds, it in fresh.items():
        old = by_date.get(ds)
        if old is None:
            by_date[ds] = it
            added += 1
            print(f'[{ds}] 新增')
            continue
        if old.get('url') != it['url']:
            by_date[ds] = it
            updated += 1
            print(f'[{ds}] 地址更新')
        elif not old.get('size'):
            old['size'] = it['size']
            updated += 1
            print(f'[{ds}] 补齐文件大小')

    # 历史上因旧逻辑入库的条目，补一次 size（失败不影响）
    for k, v in by_date.items():
        if not v.get('size'):
            _, size, _ = get_meta(v['url'])
            if size:
                v['size'] = size
                updated += 1
                print(f'[{k}] 回填 size {size / 1048576:.1f}MB')

    save_store(sorted(by_date.values(), key=lambda x: x['start_ts']))
    build_feed(list(by_date.values()))
    print(f'完成：新增 {added}，更新 {updated}，库内共 {len(by_date)} 条')


if __name__ == '__main__':
    main()
