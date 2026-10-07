#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build A-share noon data (a-shares.json) for dashboard.

Sources (2026-10-07): eastmoney push2 sharded hosts unreachable via proxy,
so indices use Sina spot (ak.stock_zh_index_spot_sina) and sectors use
Sina industry boards (ak.stock_sector_spot). Northbound via EM summary
(status 3 = suspended) + southbound 港股通 flows.
"""
import json, os
from datetime import datetime, timezone

os.environ.setdefault('HTTP_PROXY', 'http://127.0.0.1:7897')
os.environ.setdefault('HTTPS_PROXY', 'http://127.0.0.1:7897')

BASE = '/home/magicbluecate/projects/openclaw-dashboard/data'
import akshare as ak


def round2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


# ---------- 1. Indices ----------
indices = {}
try:
    df = ak.stock_zh_index_spot_sina()
    targets = {
        'sh000001': '上证指数',
        'sz399001': '深证成指',
        'sz399006': '创业板指',
        'sh000300': '沪深300',
        'sh000016': '上证50',
        'sh000905': '中证500',
        'sh000688': '科创50',
        'sh000852': '中证1000',
    }
    for code, name in targets.items():
        row = df[df['代码'] == code]
        if not row.empty:
            r = row.iloc[0]
            indices[name] = {
                'code': code[2:],
                'price': round2(r['最新价']),
                'change': round2(r['涨跌额']),
                'change_pct': round2(r['涨跌幅']),
            }
except Exception as e:
    print('indices error:', str(e)[:200])

# ---------- 2. Sectors ----------
sectors = {'top5': [], 'bottom5': [], 'count': 0, 'source': 'sina'}
try:
    sec = ak.stock_sector_spot(indicator='新浪行业')
    sec = sec.sort_values('涨跌幅', ascending=False)
    for _, r in sec.head(5).iterrows():
        sectors['top5'].append({
            'name': str(r['板块']),
            'change_pct': round2(r['涨跌幅']),
            'turnover': round2(float(r['总成交额']) / 1e8),
        })
    for _, r in sec.tail(5).iterrows():
        sectors['bottom5'].append({
            'name': str(r['板块']),
            'change_pct': round2(r['涨跌幅']),
            'turnover': round2(float(r['总成交额']) / 1e8),
        })
    sectors['count'] = int(len(sec))
except Exception as e:
    sectors = {'error': str(e)[:200]}

# ---------- 3. Northbound / Southbound ----------
northbound = {'date': None, 'net': 0.0, 'items': []}
southbound = []
try:
    sf = ak.stock_hsgt_fund_flow_summary_em()
    northbound['date'] = str(sf['交易日'].iloc[0])
    for _, r in sf.iterrows():
        board = str(r['板块'])
        if '股通' in board and '北向' in str(r['资金方向']):
            northbound['items'].append({
                'board': board,
                'net': round2(r['成交净买额']),
                'up': int(r['上涨数']),
                'flat': int(r['持平数']),
                'down': int(r['下跌数']),
            })
        elif '港股通' in board:
            southbound.append({'board': board, 'net': round2(r['成交净买额'])})
    northbound['net'] = round2(sum(i['net'] for i in northbound['items']))
except Exception as e:
    northbound = {'error': str(e)[:200]}

# ---------- 4. Market breadth ----------
breadth = {}
try:
    up = sum(i.get('up', 0) for i in northbound.get('items', []))
    down = sum(i.get('down', 0) for i in northbound.get('items', []))
    flat = sum(i.get('flat', 0) for i in northbound.get('items', []))
    breadth = {'up': up, 'down': down, 'flat': flat}
except Exception:
    pass

# ---------- 5. Hang Seng (live, HK trades on Oct 7) ----------
hang_seng = {}
try:
    import requests
    r = requests.get(
        'https://hq.sinajs.cn/list=rt_hkHSI',
        headers={'Referer': 'https://finance.sina.com.cn'},
        timeout=15,
    )
    parts = r.text.split('"')[1].split(',')
    hang_seng = {
        'name': '恒生指数',
        'price': round2(parts[6]),
        'change': round2(parts[7]),
        'change_pct': round2(parts[8]),
        'time': parts[18] if len(parts) > 18 else '',
    }
except Exception as e:
    hang_seng = {'error': str(e)[:200]}

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
    'note': '数据源: 新浪(指数/行业板块) + 东方财富(AkShare 沪深港通资金)。'
            '东财 push2 分片接口经代理不可达(48/17.push2.eastmoney.com)，'
            '指数改用新浪源；A股国庆假期休市，指数为最近交易日(2026-09-30)数据；'
            '北向资金交易状态为暂停(3)。',
}

with open(os.path.join(BASE, 'a-shares.json'), 'w', encoding='utf-8') as f:
    json.dump(ashares, f, ensure_ascii=False, indent=2)

print('a-shares.json written')
print(json.dumps(ashares, ensure_ascii=False, indent=2))
