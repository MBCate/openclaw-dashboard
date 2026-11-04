#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build A-share noon data (a-shares.json) for dashboard.

Updated 2026-11-04: Sina (hq.sinajs.cn / stock_zh_index_spot_sina) and
qt.gtimg.cn are unreachable from this host; eastmoney push2 returns 302 to
push2delay.eastmoney.com, so we call raw EM JSON endpoints directly with
redirects followed (requests/curl -L). AkShare EM wrappers do not follow the
302, hence the direct HTTP approach.
"""
import json, os, requests
from datetime import datetime, timezone

BASE = '/home/magicbluecate/projects/openclaw-dashboard/data'
S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})

INDEX_SECIDS = [
    ('1.000001', '上证指数', '000001'),
    ('0.399001', '深证成指', '399001'),
    ('0.399006', '创业板指', '399006'),
    ('1.000300', '沪深300', '000300'),
    ('1.000016', '上证50', '000016'),
    ('1.000905', '中证500', '000905'),
    ('1.000688', '科创50', '000688'),
    ('1.000852', '中证1000', '000852'),
]


def round2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def em(url, **kw):
    r = S.get(url, timeout=25, allow_redirects=True, **kw)
    r.raise_for_status()
    return r.json()


errors = []

# ---------- 1. Indices ----------
indices = {}
try:
    secids = ','.join(s for s, _, _ in INDEX_SECIDS)
    j = em(f'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids={secids}'
           '&fields=f2,f3,f4,f12,f14')
    by_code = {d['f12']: d for d in (j.get('data') or {}).get('diff', [])}
    for _, name, code in INDEX_SECIDS:
        d = by_code.get(code)
        if d:
            indices[name] = {
                'code': code,
                'price': round2(d['f2']),
                'change': round2(d['f4']),
                'change_pct': round2(d['f3']),
            }
except Exception as e:
    errors.append('indices: ' + str(e)[:150])

# ---------- 2. Sectors ----------
sectors = {'top5': [], 'bottom5': []}
try:
    j = em('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=200&po=1&np=1'
           '&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f3,f12,f14,f6')
    diff = (j.get('data') or {}).get('diff', [])
    secs = [{'name': d['f14'], 'change_pct': round2(d['f3']),
             'turnover': round2(float(d.get('f6') or 0) / 1e8)} for d in diff]
    sectors['top5'] = secs[:5]
    sectors['bottom5'] = list(reversed(secs[-5:]))
    sectors['count'] = len(secs)
    sectors['source'] = 'eastmoney'
except Exception as e:
    sectors['error'] = str(e)[:150]
    errors.append('sectors: ' + str(e)[:150])

# ---------- 3. Northbound / Southbound ----------
northbound = {'date': None, 'net': 0.0, 'items': [],
              'note': '沪深港通北向资金自2024-08起停止实时披露'}
southbound = []
try:
    j = em('https://push2.eastmoney.com/api/qt/kamt/get?fields1=f1,f2,f3,f4'
           '&fields2=f51,f52,f53,f54,f55,f56')
    d = j.get('data') or {}
    s2n = d.get('s2n') or {}
    if s2n.get('netBuyAmt') is not None:
        northbound['net'] = round2(float(s2n['netBuyAmt']) / 1e4)
        northbound['date'] = s2n.get('date') or s2n.get('date2')
    n2s = d.get('n2s') or {}
    if n2s.get('netBuyAmt') is not None:
        southbound.append({'board': '港股通', 'net': round2(float(n2s['netBuyAmt']) / 1e4)})
except Exception as e:
    southbound = []
    errors.append('hsgt: ' + str(e)[:150])

# ---------- 4. Market breadth ----------
breadth = {}
try:
    j = em('https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=1.000001,0.399001'
           '&fields=f104,f105,f106')
    ups = downs = flats = 0
    for d in (j.get('data') or {}).get('diff', []):
        ups += int(d.get('f104') or 0)
        downs += int(d.get('f105') or 0)
        flats += int(d.get('f106') or 0)
    breadth = {'up': ups, 'down': downs, 'flat': flats}
except Exception as e:
    errors.append('breadth: ' + str(e)[:150])

# ---------- 5. Hang Seng ----------
hang_seng = {}
try:
    j = em('https://push2.eastmoney.com/api/qt/stock/get?secid=100.HSI'
           '&fields=f43,f57,f58,f169,f170,f86')
    d = j.get('data') or {}
    hang_seng = {
        'name': '恒生指数',
        'price': round2(float(d.get('f43') or 0) / 100),
        'change': round2(float(d.get('f169') or 0) / 100),
        'change_pct': round2(float(d.get('f170') or 0) / 100),
        'time': '',
    }
except Exception as e:
    hang_seng = {'error': str(e)[:150]}
    errors.append('hsi: ' + str(e)[:150])

note = '数据源: 东方财富 push2(跟随302到 push2delay) 指数/行业板块/涨跌家数/恒指。'
note += '北向资金已停止实时披露。'
if errors:
    note += ' 部分接口异常: ' + '; '.join(errors)

ashares = {
    'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'time': 'noon',
    'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'indices': indices,
    'hang_seng': hang_seng,
    'sectors': sectors,
    'northbound': northbound,
    'southbound': southbound,
    'breadth': breadth,
    'note': note,
}

if not indices:
    raise SystemExit('FATAL: no index data, aborting write')

with open(os.path.join(BASE, 'a-shares.json'), 'w', encoding='utf-8') as f:
    json.dump(ashares, f, ensure_ascii=False, indent=2)

print('a-shares.json written')
print(json.dumps(ashares, ensure_ascii=False, indent=2))
