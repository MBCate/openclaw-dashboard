#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build A-share noon (or close) data when push2 clist/ulist are 502.

2026-11-23: push2 clist (sector/breadth) returned 502 for hours; push2his
(klines) worked. Use push2his daily kline for indices (latest bar = current
session, includes live price during trading), and push2 kamt for southbound.
Sectors / breadth are kept from the previous snapshot with an explicit note.

Usage: python3 scripts/build_noon_fallback.py [noon|close]
"""
import json, os, sys, time
from datetime import datetime, timezone
import requests

BASE = '/home/magicbluecate/projects/openclaw-dashboard/data'
PATH = os.path.join(BASE, 'a-shares.json')
mode = sys.argv[1] if len(sys.argv) > 1 else 'noon'

S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})

SECIDS = [
    ('1.000001', '上证指数', '000001'),
    ('0.399001', '深证成指', '399001'),
    ('0.399006', '创业板指', '399006'),
    ('1.000300', '沪深300', '000300'),
    ('1.000016', '上证50', '000016'),
    ('1.000905', '中证500', '000905'),
    ('1.000688', '科创50', '000688'),
    ('1.000852', '中证1000', '000852'),
]


def r2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return None


def get(url, params, tries=8):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=20)
            if r.status_code == 200 and not r.text.lstrip().startswith('<'):
                return r.json()
        except Exception:
            pass
        time.sleep(2 + i)
    return None


errors = []
indices = {}
today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
bar_date = None
for secid, name, code in SECIDS:
    j = get('https://push2his.eastmoney.com/api/qt/stock/kline/get',
            {'secid': secid, 'fields1': 'f1,f2,f3,f4,f5,f6',
             'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
             'klt': 101, 'fqt': 1, 'end': '20500101', 'lmt': 2})
    if not j or not j.get('data') or not j['data'].get('klines'):
        errors.append(f'{name}: kline fail')
        continue
    k = j['data']['klines'][-1].split(',')
    bar_date = k[0]
    indices[name] = {
        'code': code,
        'price': r2(k[2]),
        'change': r2(k[9]) if len(k) > 9 else None,
        'change_pct': r2(k[8]) if len(k) > 8 else None,
        'open': r2(k[1]),
        'high': r2(k[3]),
        'low': r2(k[4]),
        'volume': int(float(k[5])),
        'turnover_yi': round(float(k[6]) / 1e8, 2) if k[6] else None,
    }

if not indices:
    raise SystemExit('FATAL: no index data')

# Hang Seng
hang_seng = {}
j = get('https://push2his.eastmoney.com/api/qt/stock/kline/get',
        {'secid': '100.HSI', 'fields1': 'f1,f2,f3,f4,f5,f6',
         'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
         'klt': 101, 'fqt': 1, 'end': '20500101', 'lmt': 2})
if j and j.get('data') and j['data'].get('klines'):
    k = j['data']['klines'][-1].split(',')
    hang_seng = {'name': '恒生指数', 'price': r2(k[2]), 'change': r2(k[9]),
                 'change_pct': r2(k[8]), 'time': k[0]}

# Southbound (kamt)
southbound = []
j = get('https://push2.eastmoney.com/api/qt/kamt/get',
        {'fields1': 'f1,f2,f3,f4', 'fields2': 'f51,f52,f53,f54,f55,f56'})
if j and j.get('data'):
    n2s = j['data'].get('n2s') or {}
    net = n2s.get('netBuyAmt') or n2s.get('dayNetAmtIn')
    if net:
        southbound.append({'board': '港股通', 'net': r2(float(net) / 1e4)})
else:
    errors.append('southbound fail')

northbound = {'date': bar_date, 'net': None, 'items': [],
              'note': '北向资金自 2024-08 起停止实时披露净流入, 无可用数据'}

# Keep previous sectors / breadth with explicit stale note
old = {}
try:
    old = json.load(open(PATH, encoding='utf-8'))
except Exception:
    pass

stale = f'sector/涨跌家数接口 (push2 clist) 502 不可用, 板块数据沿用 {old.get("date", "?")} 快照'
sectors = old.get('sectors') or {'top5': [], 'bottom5': []}
breadth = old.get('breadth') or {}
if breadth:
    breadth = dict(breadth)
    breadth['stale_from'] = old.get('date')

amount_total_yi = sum((v.get('turnover_yi') or 0) for v in indices.values())

idx_txt = ', '.join(f'{n} {v["price"]:.2f} ({v["change_pct"]:+.2f}%)'
                    for n, v in indices.items() if v.get('price') is not None)
note = (f'{bar_date} A股{mode}。{idx_txt}。北向资金已停止实时披露。{stale}。'
        f'数据源: 东方财富 push2his 日K (含盘中实时) / push2 kamt。')
if errors:
    note += ' 异常: ' + '; '.join(errors)

out = dict(old) if old else {}
out.update({
    'date': bar_date or today,
    'time': mode,
    'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'indices': indices,
    'indices_list': [{'name': n, **v} for n, v in indices.items()],
    'hang_seng': hang_seng,
    'sectors': sectors,
    'sectors_top5': sectors.get('top5', []),
    'sectors_bottom5': sectors.get('bottom5', []),
    'northbound': northbound,
    'northbound_fallback': True,
    'southbound': southbound,
    'breadth': breadth,
    'amount_total_yi': round(amount_total_yi, 2),
    'note': note,
    'source': '东方财富 (push2his/push2)',
})

with open(PATH, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print('a-shares.json written', out['date'], out['time'])
print(note)
