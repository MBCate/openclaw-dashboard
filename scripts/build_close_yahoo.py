#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build A-share close data (a-shares.json) via Yahoo Finance chart API.

2026-11-23: 东方财富 push2/push2his 与腾讯/新浪行情全部不可达 (网络层阻断),
Yahoo Finance 可用 -> 用 Yahoo 日线作为收盘数据源。板块/涨跌家数/A股个股
明细无法取得, 保留上次快照并加 stale 标注。

Usage: python3 scripts/build_close_yahoo.py [close|noon]
"""
import json, os, sys, time
from datetime import datetime, timezone
import urllib.request
from urllib.error import URLError

BASE = '/home/magicbluecate/projects/openclaw-dashboard/data'
PATH = os.path.join(BASE, 'a-shares.json')
mode = sys.argv[1] if len(sys.argv) > 1 else 'close'

def _http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

SYMS = [
    ('000001.SS', '上证指数', '000001'),
    ('399001.SZ', '深证成指', '399001'),
    ('399006.SZ', '创业板指', '399006'),
    ('000300.SS', '沪深300', '000300'),
    ('000016.SS', '上证50', '000016'),
    ('000905.SS', '中证500', '000905'),
    ('000688.SS', '科创50', '000688'),
    ('000852.SS', '中证1000', '000852'),
]


def r2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return None


def chart(sym, rng='5d'):
    for i in range(5):
        try:
            return _http_json(
                f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}'
                f'?interval=1d&range={rng}')['chart']['result'][0]
        except Exception:
            pass
        time.sleep(1 + i)
    return None


def quote(sym, rng='5d'):
    res = chart(sym, rng)
    if not res:
        return None
    meta = res['meta']
    ts = res['timestamp']
    q = res['indicators']['quote'][0]
    closes = [c for c in q.get('close') or [] if c is not None]
    o = q.get('open') or []
    h = q.get('high') or []
    lo = q.get('low') or []
    v = q.get('volume') or []
    n = len(closes)
    last = closes[-1]
    prev = closes[-2] if n > 1 else meta.get('chartPreviousClose')
    d = datetime.fromtimestamp(ts[-1], timezone.utc)
    return {
        'price': r2(last),
        'prev_close': r2(prev),
        'change': r2(last - prev) if prev else None,
        'change_pct': r2((last - prev) / prev * 100) if prev else None,
        'open': r2(o[-1]), 'high': r2(h[-1]), 'low': r2(lo[-1]),
        'volume': (v[-1] or 0) if n else 0,
        'timestamp': ts[-1],
        'bar_date': d.strftime('%Y-%m-%d'),
    }


indices = {}
errors = []
bar_date = None
for sym, name, code in SYMS:
    q = quote(sym)
    if not q:
        errors.append(f'{name}: yahoo fail')
        continue
    bar_date = q.pop('bar_date')
    q.pop('timestamp', None)
    indices[name] = {'code': code, **q}

if not indices:
    raise SystemExit('FATAL: no index data (yahoo unreachable)')

hang_seng = {}
q = quote('^HSI')
if q:
    q.pop('bar_date')
    q.pop('timestamp', None)
    hang_seng = {'name': '恒生指数', **q}
else:
    errors.append('恒指: yahoo fail')

old = {}
try:
    old = json.load(open(PATH, encoding='utf-8'))
except Exception:
    pass

sectors = old.get('sectors') or {'top5': [], 'bottom5': []}
stale_src = old.get('date', '?')
breadth = dict(old.get('breadth') or {})
if breadth:
    breadth['stale_from'] = stale_src

northbound = {'date': bar_date, 'net': None, 'items': [],
              'note': '北向资金自 2024-08 起停止实时披露净流入, 无可用数据'}

idx_txt = ', '.join(f'{n} {v["price"]:.2f} ({v["change_pct"]:+.2f}%)'
                    for n, v in indices.items() if v.get('price') is not None)
note = (f'{bar_date} A股收盘。{idx_txt}。恒指 {hang_seng.get("price")} '
        f'({hang_seng.get("change_pct"):+.2f}%)。'.replace('None', 'n/a') if hang_seng else
        f'{bar_date} A股收盘。{idx_txt}。')
note += ('板块/涨跌家数/个股榜单接口(东方财富 push2 及腾讯/新浪)全部网络不可达, '
         f'沿用 {stale_src} 快照。北向资金已停止实时披露。数据源: Yahoo Finance chart API。')
if errors:
    note += ' 异常: ' + '; '.join(errors)

amount_total_yi = sum((v.get('turnover_yi') or 0) for v in indices.values())

out = dict(old) if old else {}
out.update({
    'date': bar_date or datetime.now(timezone.utc).strftime('%Y-%m-%d'),
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
    'southbound': old.get('southbound') or [],
    'breadth': breadth,
    'amount_total_yi': amount_total_yi or old.get('amount_total_yi'),
    'note': note,
    'source': 'Yahoo Finance chart API (东财/腾讯/新浪不可达)',
})

with open(PATH, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print('a-shares.json written', out['date'], out['time'])
print(note)
