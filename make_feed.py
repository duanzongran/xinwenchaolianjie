#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻超链接（中国之声 21:00-22:00）播客 RSS 生成器
数据源：云听官方接口 https://ytmsout.radio.cn/web/appProgram/listByDate
只存链接，不下载音频。
"""
import hashlib, time, json, os, sys, datetime, urllib.parse, urllib.request
from email.utils import format_datetime
from xml.sax.saxutils import escape

KEY = 'f0fc4c668392f9f9a447e48584c214ee'
BASE = 'https://ytmsout.radio.cn'
BROADCAST_ID = '639'          # 中国之声
PROGRAM_NAME = '新闻超链接'
TZ = datetime.timezone(datetime.timedelta(hours=8))

FEED_TITLE = '新闻超链接（中国之声）'
FEED_DESC = '中央广播电视总台中国之声《新闻超链接》，每天 21:00-22:00 播出。音频来自云听，仅存链接不存文件。'
FEED_LINK = 'https://www.radio.cn/pc-portal/erji/radioStation.html?id=24'
AUTHOR = '中国之声'

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'episodes.json')
FEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'feed.xml')


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


def verify(url):
    """确认链接可播：能取到字节且是 m4a/mp4 容器"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-255'})
        with urllib.request.urlopen(req, timeout=20) as r:
            head = r.read(64)
        if len(head) < 8:
            return False
        return head[4:8] == b'ftyp' or head[:3] == b'ID3' or head[:2] == b'\xff\xf3' or head[:2] == b'\xff\xfb'
    except Exception as e:
        print(f'  [warn] verify fail: {e}')
        return False


def load_store():
    if os.path.exists(STORE):
        with open(STORE, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_store(items):
    with open(STORE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def crawl_days(days):
    """抓最近 days 天，返回本期新增条目"""
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
            if it.get('programName') == PROGRAM_NAME:
                hit = it
                break
        if not hit:
            print(f'[{ds}] 无《{PROGRAM_NAME}》')
            continue
        url = hit.get('playUrlHigh') or hit.get('playUrlLow')
        if not url:
            print(f'[{ds}] 无播放地址')
            continue
        start = datetime.datetime.fromtimestamp(hit['startTime'] / 1000, TZ)
        got[ds] = {
            'date': ds,
            'id': str(hit['id']),
            'title': f'{ds} 新闻超链接' + ('（重播）' if '(重播)' in hit.get('programName', '') else ''),
            'url': url,
            'type': 'audio/mpeg' if '.mp3' in url.lower() else 'audio/mp4',
            'start': start.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'start_ts': hit['startTime'],
        }
        print(f'[{ds}] OK {hit["id"]}')
    return got


def build_feed(items):
    items = sorted(items, key=lambda x: x['start_ts'], reverse=True)
    now = datetime.datetime.now(TZ)
    parts = [f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>{escape(FEED_TITLE)}</title>
<link>{escape(FEED_LINK)}</link>
<description>{escape(FEED_DESC)}</description>
<language>zh-cn</language>
<itunes:author>{escape(AUTHOR)}</itunes:author>
<lastBuildDate>{format_datetime(now)}</lastBuildDate>
<atom:link href="feed.xml" rel="self" type="application/rss+xml"/>
''']
    for it in items:
        dt = datetime.datetime.fromtimestamp(it['start_ts'] / 1000, TZ)
        parts.append(f'''<item>
<title>{escape(it['title'])}</title>
<description>{escape(it['title'] + "，中国之声《新闻超链接》当期完整录音。")}</description>
<enclosure url="{escape(it['url'])}" type="{it.get('type','audio/mp4')}" length="0"/>
<guid isPermaLink="false">xwclj-{it['id']}</guid>
<pubDate>{format_datetime(dt)}</pubDate>
<itunes:duration>01:00:00</itunes:duration>
</item>
''')
    parts.append('</channel>\n</rss>\n')
    with open(FEED, 'w', encoding='utf-8') as f:
        f.write(''.join(parts))


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(f'抓取最近 {days} 天 ...')
    fresh = crawl_days(days)
    store = load_store()
    by_date = {x['date']: x for x in store}
    added = 0
    for ds, it in fresh.items():
        if ds in by_date:
            old = by_date[ds]
            if old.get('url') != it['url']:
                by_date[ds] = it
                print(f'[{ds}] 地址更新')
            continue
        if not verify(it['url']):
            print(f'[{ds}] 链接不可播，跳过')
            continue
        by_date[ds] = it
        added += 1
        print(f'[{ds}] 新增')
    save_store(sorted(by_date.values(), key=lambda x: x['start_ts']))
    build_feed(list(by_date.values()))
    print(f'完成：新增 {added} 条，库内共 {len(by_date)} 条，已生成 feed.xml')


if __name__ == '__main__':
    main()
