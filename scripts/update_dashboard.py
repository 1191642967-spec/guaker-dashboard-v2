#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桂格直播间运营数据看板 v2 —— 数据更新脚本
从飞书表格 cells 缓存（_cache/*.json）重建 data.json 的 daily_data 与 anchor_data，
保留 accounts / schedule / daily_metrics 不动。

数据源（飞书 cells-get，公式列必须读计算后实际值）：
  优选日数据  token=Qd4LsAIwAhMgBltZNwWcg3pWn9d  sheet=nJjlbb
  官方日数据  wiki=Be7lwLLzJimaA0kYrXhcSsWWnoD  sheet=dtjWao
  优选主播  token=Qd4LsAIwAhMgBltZNwWcg3pWn9d  sheet=e80Dru
  官方主播  wiki=Be7lwLLzJimaA0kYrXhcSsWWnoD  sheet=q1dp44

口径：
  GMV/消耗/乘方推GMV/乘方推消耗 取每天第一场汇总值；其余指标累加所有场次，PCU 取 max。
  源表当天个别列串列时，异常指标置 None（前端显示 '-'），不臆造修正。
"""
import json, re, os
from datetime import datetime
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data.json')
CACHE = os.path.join(BASE, '_cache')

# ---------- 基础工具 ----------
def tn(v):
    if v is None: return None
    s = str(v).strip()
    if s in ('', '-', '#DIV/0!'): return None
    try: return float(s.replace(',', ''))
    except: return None

def pct(v):
    if v is None: return 0
    s = str(v).strip()
    if s in ('', '-', '#DIV/0!'): return 0
    if s.endswith('%'):
        try: return float(s[:-1].replace(',', '')) / 100
        except: return 0
    try: return float(s.replace(',', ''))
    except: return 0

def norm_date(s):
    s = str(s).strip().split(' ')[0]
    for fmt in ('%Y/%m/%d', '%Y-%m-%d'):
        try: return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except: pass
    return None

def load_cells(name):
    with open(os.path.join(CACHE, name), encoding='utf-8') as f:
        data = json.load(f)
    cells = data['ranges'][0]['cells']
    return [[(c.get('value', '') if c else '') for c in row] for row in cells]

# ---------- 日数据列映射（每次更新前以飞书表头为准核对） ----------
# 优选（列0=日期文本，非时间）: 1直播间GMV,2直播间消耗,3开始时间,5时长分钟,6曝光人数,8观看人数,
#       11最高在线PCU,12平均在线ACU,13人均分钟,14评论,15加团,16增粉,20商品曝光人数,21商品点击人数,
#       24订单数,28成交件数,29成交人数
YOUXUAN = dict(
    start=3, dur=5, exp=6, enter=8, pcu=11, acu=12, avg=13, comment=14,
    join=15, fan=16, pexp=20, pclick=21, order=24, pieces=28, buyer=29,
    gmv=1, cost=2, cfgmv=None, cfcost=None,
)
# 官方: 1总GMV,2总消耗,3乘方GMV,4乘方消耗,7开始时间,9时长分钟,10曝光人数,12观看人数,
#       16PCU,17ACU,18人均分钟,19评论,20加团,21增粉,25商品曝光人数,26商品点击人数,
#       29订单数,33成交件数,34成交人数
GUANGFANG = dict(
    start=7, dur=9, exp=10, enter=12, pcu=16, acu=17, avg=18, comment=19,
    join=20, fan=21, pexp=25, pclick=26, order=29, pieces=33, buyer=34,
    gmv=1, cost=2, cfgmv=3, cfcost=4,
)

def parse_daily(cells, cols, account):
    by_day = defaultdict(list)
    for row in cells[1:]:
        if len(row) <= cols['start']: continue
        ds = norm_date(row[cols['start']])
        if ds: by_day[ds].append(row)

    records = []
    for ds in sorted(by_day):
        dr = by_day[ds]
        def col(row, k):
            i = cols[k]
            return tn(row[i]) if i is not None and i < len(row) else None
        # 汇总场：当天总GMV非空的第一场；都为空时回退第一行
        first = next((r for r in dr if col(r, 'gmv') is not None), dr[0])

        gmv = col(first, 'gmv') or 0
        cost = col(first, 'cost') or 0
        cfgmv = col(first, 'cfgmv') or 0 if cols['cfgmv'] is not None else 0
        cfcost = col(first, 'cfcost') or 0 if cols['cfcost'] is not None else 0

        duration = sum((col(r, 'dur') or 0) for r in dr) / 60
        exposure = sum((col(r, 'exp') or 0) for r in dr)
        enter = sum((col(r, 'enter') or 0) for r in dr)
        pexp = sum((col(r, 'pexp') or 0) for r in dr)
        comment_raw = sum((col(r, 'comment') or 0) for r in dr)
        join = sum((col(r, 'join') or 0) for r in dr)
        fan = sum((col(r, 'fan') or 0) for r in dr)

        pcu_raw = max((col(r, 'pcu') or 0) for r in dr)
        acu_raw = sum((col(r, 'acu') or 0) for r in dr)
        avg_min = sum((col(r, 'avg') or 0) for r in dr)
        pclick_raw = sum((col(r, 'pclick') or 0) for r in dr)
        order_raw = sum((col(r, 'order') or 0) for r in dr)
        pieces = sum((col(r, 'pieces') or 0) for r in dr)
        buyer_raw = sum((col(r, 'buyer') or 0) for r in dr)

        # ---- 错乱保护：数值违反漏斗/量级关系时置 None，不写入错误值 ----
        # 商品曝光人数正常约为观看人数 80%~95%；有观看(>5)却极小(<30%)说明该列串列，置空；零场次(enter<=5)保留原值
        pexp_safe = None if (enter > 5 and pexp > 0 and pexp < enter * 0.30) else pexp
        # 商品点击人数：曝光缺失即置空；否则点击人数不应反超商品曝光
        if pexp_safe is None:
            pclick = None
        else:
            pclick = pclick_raw if (pexp_safe <= 0 or pclick_raw <= pexp_safe) else None
        order = order_raw if abs(order_raw - round(order_raw)) < 0.01 else None
        # 订单数物理上不应反超观看人数；超过说明订单列串列，置空
        if order is not None and enter > 0 and order_raw > enter:
            order = None
        buyer = buyer_raw if (pieces <= 0 or buyer_raw >= pieces * 0.3) else None
        # 评论数必须为整数次，小数说明评论列串列，置空
        comment = comment_raw if abs(comment_raw - round(comment_raw)) < 0.01 else None
        # 人均观看历史正常区间约 0.05~5 分钟；超出说明在线/人均列整体错位，PCU/ACU 一并置空
        online_bad = not (0.05 <= avg_min <= 5)
        avg_watch = avg_min * 60 if not online_bad else None
        acu_ok = (not online_bad) and pcu_raw > 0 and 2 <= acu_raw <= pcu_raw
        acu = acu_raw if acu_ok else None
        pcu = pcu_raw if acu is not None else None

        m = {
            '直播时长(h)': duration,
            '进入直播间人数': enter,
            '直播间曝光人数': exposure,
            '观看UV': enter,
            '商品曝光人数': pexp_safe,
            '商品点击人数': pclick,
            'PCU在线峰值': pcu,
            'ACU在线均值': acu,
            '人均观看（秒）': avg_watch,
            '直播期间累计成交金额': gmv,
            '广告消耗': cost,
            '订单数': order,
            '评论数': comment,
            '增粉数': fan,
            '加团人数': join,
            '成交人数': buyer,
            '乘方推商品GMV': cfgmv,
            '乘方推商品消耗': cfcost,
        }
        m['时均GMV'] = gmv / duration if duration > 0 else 0
        m['曝光-进入转化率'] = enter / exposure if exposure > 0 else 0
        m['投产比ROI'] = gmv / cost if cost > 0 else 0
        if cols['cfgmv'] is not None:
            m['乘方推商品ROI'] = cfgmv / cfcost if cfcost > 0 else 0
        records.append({'date': ds, 'account': account, 'metrics': m})
    return records

# ---------- 主播数据列映射（横向分块，每块13列，间隔1空列） ----------
BLOCKS = [0, 13, 26, 39]
ANCHOR_OFF = dict(date=0, dur=1, gmv=2, cost=3, pay=4, roi=8, ctr=9, cvr=10, ctrl=11)

def parse_anchor(cells, account):
    names = [cells[0][b] if len(cells[0]) > b else '' for b in BLOCKS]
    records = []
    for bi, b in enumerate(BLOCKS):
        anchor = str(names[bi]).strip()
        if not anchor: continue
        for row in cells[2:]:
            if len(row) <= b + ANCHOR_OFF['gmv']: continue
            ds = norm_date(row[b + ANCHOR_OFF['date']])
            if not ds: continue
            gmv = tn(row[b + ANCHOR_OFF['gmv']])
            if gmv is None or gmv <= 0: continue  # 未来排班/无成交场次跳过
            records.append({
                'date': ds, 'account': account, 'anchor': anchor,
                'metrics': {
                    '时长': tn(row[b + ANCHOR_OFF['dur']]) or 0,
                    '整体成交金额(元)': gmv,
                    '消耗': tn(row[b + ANCHOR_OFF['cost']]) or 0,
                    '用户实际支付金额(元)': tn(row[b + ANCHOR_OFF['pay']]) or 0,
                    '整体ROI': tn(row[b + ANCHOR_OFF['roi']]) or 0,
                    '曝光点击率': pct(row[b + ANCHOR_OFF['ctr']]),
                    '点击成交率': pct(row[b + ANCHOR_OFF['cvr']]),
                    '场控': str(row[b + ANCHOR_OFF['ctrl']]).strip() if row[b + ANCHOR_OFF['ctrl']] else '',
                }
            })
    return records

# ---------- 主流程 ----------
def main():
    you_daily = parse_daily(load_cells('youxuan_daily.json'), YOUXUAN, '桂格优选')
    gf_daily = parse_daily(load_cells('guanfang_daily.json'), GUANGFANG, '桂格官方')
    you_anchor = parse_anchor(load_cells('youxuan_anchor.json'), '桂格优选')
    gf_anchor = parse_anchor(load_cells('guanfang_anchor.json'), '桂格官方')

    with open(DATA, encoding='utf-8') as f:
        d = json.load(f)

    d['daily_data'] = you_daily + gf_daily
    d['anchor_data'] = you_anchor + gf_anchor
    d['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with open(DATA, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    # 汇总报告
    for account, dl in [('桂格优选', you_daily), ('桂格官方', gf_daily)]:
        octd = [x for x in dl if x['date'].startswith('2026-10')]
        tg = sum(x['metrics']['直播期间累计成交金额'] for x in octd)
        tc = sum(x['metrics']['广告消耗'] for x in octd)
        last = dl[-1]
        m = last['metrics']
        miss = [k for k in ('商品曝光人数', '商品点击人数', '订单数', '成交人数', 'PCU在线峰值', 'ACU在线均值', '人均观看（秒）') if m.get(k) is None]
        flag = f"  ⚠待核对: {','.join(miss)}" if miss else ""
        print(f"{account} 日数据 {len(octd)}天 最新{last['date']} "
              f"GMV=¥{m['直播期间累计成交金额']:,.2f} 消耗=¥{m['广告消耗']:,.2f}{flag}")
        print(f"   本月(10月) GMV=¥{tg:,.0f} 消耗=¥{tc:,.0f} ROI={tg/tc:.2f}")

    for account, al in [('桂格优选', you_anchor), ('桂格官方', gf_anchor)]:
        by = defaultdict(list)
        for x in al: by[x['anchor']].append(x['date'])
        print(f"{account} 主播 {len(al)}条: " + "; ".join(
            f"{a}{len(ds)}条(至{sorted(ds)[-1]})" for a, ds in by.items()))

if __name__ == '__main__':
    main()
