# -*- coding: utf-8 -*-
"""把 fetch_feishu.js 抓的 _cache/*.tsv 转成 update_dashboard.py 需要的 cells-get 缓存格式"""
import csv, json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(BASE, '_cache')

JOBS = [
    ('youxuan_sessions.tsv',      'youxuan_daily.json',  60),
    ('guanfang_sessions.tsv',     'guanfang_daily.json', 60),
    ('youxuan_anchors.tsv',       'youxuan_anchor.json', 52),
    ('guanfang_anchors.tsv',      'guanfang_anchor.json', 52),
]

for src, dst, width in JOBS:
    src_p = os.path.join(CACHE, src)
    if not os.path.exists(src_p):
        print(f'[SKIP] {src} 不存在')
        continue
    rows = list(csv.reader(open(src_p, encoding='utf-8-sig'), delimiter='\t'))
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    cells = []
    for r in rows:
        r = list(r) + [''] * (width - len(r))
        cells.append([{'value': c} for c in r[:width]])
    with open(os.path.join(CACHE, dst), 'w', encoding='utf-8') as f:
        json.dump({'ranges': [{'cells': cells}]}, f, ensure_ascii=False)
    print(f'{src} -> {dst}: {len(cells)} rows x {width} cols')
print('CACHES BUILT')
