#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build A-share close data (a-shares.json) via Eastmoney push2 direct HTTP.

2026-11-10: sina endpoints broken (SSL / page-count), akshare EM sharded hosts
unreachable via proxy -> use push2.eastmoney.com with no_proxy.
Run with: no_proxy='*' NO_PROXY='*' python3 build_close_em.py
"""
import json, os
from datetime import datetime, timezone

BASE = '/home/magicbluecate/projects/openclaw-dashboard/data'
import requests

H = {'User-Agent': 'Mozilla/5.0'}
S = requests.Session()
S.trust_env = False  # ignore proxy env


def r2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


out = {
    'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'time': 'close',
    'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
}

IDX = {
    '1.000001': '上证指数', '0.399001': '深证成指', '0.399006': '创业板指',
    '1.000300': '沪深300', '1.000016': '上证50', '1.000905': '中证500',
    '1.000688': '科创50', '1.000852': '中证1000',
}
try:
    r = S.get('https://push2.eastmoney.com/api/qt/ulist.np/get',
              params={'fltt': 2, 'secids': ','.join(IDX), 'fields': 'f2,f3,f4,f6,f12,f13,f14'},
              headers=H, timeout=20)
    idx = {}
    for d in r.json()['data']['diff']:
        name = IDX.get(f"{d['f13']}.{d['f12']}")
        if not name:
            continue
        idx[name] = {
            'code': d['f12'],
            'price': r2(d['f2']),
            'change': r2(d['f4']),
            'change_pct': r2(d['f3']),
            'turnover_yi': round(d.get('f6', 0) / 1e8, 1),
        }
    out['indices'] = idx
except Exception as e:
    out['indices'] = {'error': str(e)[:200]}

# breadth from index constituent stats (sh + sz)
try:
    r = S.get('https://push2.eastmoney.com/api/qt/ulist.np/get',
              params={'fltt': 2, 'secids': '1.000001,0.399001', 'fields': 'f12,f104,f105,f106'},
              headers=H, timeout=20)
    up = down = flat = 0
    for d in r.json()['data']['diff']:
        up += d.get('f104') or 0
        down += d.get('f105') or 0
        flat += d.get('f106') or 0
    out['breadth'] = {'up': up, 'down': down, 'flat': flat}
except Exception as e:
    out['breadth'] = {'error': str(e)[:200]}

# hang seng
try:
    r = S.get('https://push2.eastmoney.com/api/qt/ulist.np/get',
              params={'fltt': 2, 'secids': '100.HSI', 'fields': 'f2,f3,f4,f12,f14'},
              headers=H, timeout=20)
    d = r.json()['data']['diff'][0]
    out['hang_seng'] = {'name': '恒生指数', 'price': r2(d['f2']), 'change': r2(d['f4']),
                        'change_pct': r2(d['f3']), 'time': ''}
except Exception as e:
    out['hang_seng'] = {'error': str(e)[:200]}

# sectors
try:
    r = S.get('https://push2.eastmoney.com/api/qt/clist/get',
              params={'pn': 1, 'pz': 200, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
                      'fid': 'f3', 'fs': 'm:90+t:2+f:!50', 'fields': 'f2,f3,f6,f12,f14'},
              headers=H, timeout=20)
    diff = r.json()['data']['diff']
    top = [{'name': x['f14'], 'change_pct': r2(x['f3']), 'turnover': round(x['f6'] / 1e8, 1)} for x in diff[:5]]
    bot = [{'name': x['f14'], 'change_pct': r2(x['f3']), 'turnover': round(x['f6'] / 1e8, 1)} for x in diff[-5:]]
    out['sectors'] = {'top5': top, 'bottom5': bot, 'count': len(diff), 'source': 'eastmoney'}
except Exception as e:
    out['sectors'] = {'error': str(e)[:200]}

# northbound (suspended since 2024-08; try EM hsgt)
nb = {'date': None, 'net': 0.0, 'items': [], 'note': '沪深港通北向资金自2024-08起停止实时披露'}
try:
    r = S.get('https://push2.eastmoney.com/api/qt/kamt/get',
              params={'fields1': 'f1,f2,f3,f4', 'fields2': 'f51,f52,f53,f54,f55,f56'},
              headers=H, timeout=20)
    out['southbound'] = []
    d = r.json().get('data') or {}
    sh = d.get('hk2sh') or {}
    sz = d.get('hk2sz') or {}
    for brd, seg in (('港股通(沪)', sh), ('港股通(深)', sz)):
        net = seg.get('netBuyAmt')
        if net is not None:
            out['southbound'].append({'board': brd, 'net': round(net / 1e4, 2)})
except Exception:
    out['southbound'] = []

out['northbound'] = nb
out['note'] = '数据源: 东方财富 push2 (指数/行业板块/涨跌家数/恒指)。北向资金已停止实时披露。'

path = os.path.join(BASE, 'a-shares.json')
with open(path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2)[:2500])
