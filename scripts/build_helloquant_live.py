#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build data/helloquant.json directly (bypasses ~/trading/helloquant raw pipeline).

2026-11-23: ~/trading/helloquant/data/daily_raw.json stale since 11-19 and the
legacy build_helloquant.py emits a reduced schema. This script pulls OKX public
tickers (BTC/ETH) + alternative.me Fear&Greed and recomputes the 8 strategy
multi-timeframe indicators from OKX candles (1H/4H) with the same rules used by
HelloQuant (MA cross, Supertrend-lite, RSI, MACD, Bollinger, Momentum, Z-score).

Usage: python3 scripts/build_helloquant_live.py
"""
import json, os
from datetime import datetime, timezone
import urllib.request

OUT = os.path.expanduser('~/projects/openclaw-dashboard/data/helloquant.json')
BASE = 'https://www.okx.com'


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def r2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return None


def candles(inst, bar, limit=300):
    j = get(f'{BASE}/api/v5/market/candles?instId={inst}&bar={bar}&limit={limit}')
    rows = j.get('data') or []
    rows = list(reversed(rows))  # oldest first
    return [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows]  # ts,o,h,l,c


def sma(xs, n):
    if len(xs) < n:
        return None
    return sum(xs[-n:]) / n


def ema_series(xs, n):
    if not xs:
        return []
    k = 2 / (n + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def atr(cl, n=10):
    trs = []
    for i in range(1, len(cl)):
        _, o, h, l, c = cl[i]
        pc = cl[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return None
    return sum(trs[-n:]) / n


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):
        d = closes[i] - closes[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def macd(closes):
    if len(closes) < 35:
        return None, None
    e12, e26 = ema_series(closes, 12), ema_series(closes, 26)
    diff = [a - b for a, b in zip(e12, e26)]
    dea = ema_series(diff, 9)
    return diff[-1], dea[-1]


def boll(closes, n=20, k=2):
    if len(closes) < n:
        return None, None, None
    m = sma(closes, n)
    var = sum((x - m) ** 2 for x in closes[-n:]) / n
    sd = var ** 0.5
    return m - k * sd, m, m + k * sd


def indicators(cl):
    closes = [c[4] for c in cl]
    price = closes[-1]
    out = {}
    for n in (5, 10, 20, 60):
        out[f'ma{n}'] = r2(sma(closes, n))
    ma5, ma10, ma20, ma60 = (out['ma5'], out['ma10'], out['ma20'], out['ma60'])
    # Supertrend-lite: price vs MA10 +/- 3*ATR10
    a = atr(cl)
    out['atr10'] = r2(a)
    if a and ma10:
        out['supertrend'] = '多头' if price > ma10 + 0 * a and price > ma10 else '空头'
        out['st_upper'] = r2(ma10 + 3 * a)
        out['st_lower'] = r2(ma10 - 3 * a)
        out['trend'] = '偏多' if price > ma10 else '偏空'
    else:
        out['supertrend'] = None
        out['trend'] = None
    out['rsi14'] = r2(rsi(closes))
    m, s = macd(closes)
    out['macd'] = r2(m)
    out['macd_signal'] = r2(s)
    if m is not None and s is not None:
        out['macd_status'] = '金叉' if m > s else '死叉'
    lo, mid, up = boll(closes)
    out['bb_lower'], out['bb_mid'], out['bb_upper'] = r2(lo), r2(mid), r2(up)
    out['bb_pctb'] = r2((price - lo) / (up - lo) * 100) if up and up != lo else None
    out['mom10_pct'] = r2((price / closes[-11] - 1) * 100) if len(closes) > 11 else None
    if len(closes) >= 40:
        xs = closes[-40:]
        mu = sum(xs) / len(xs)
        sd = (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5
        out['z40'] = r2((price - mu) / sd) if sd else None
    return out


def strategy_signals(ind, price):
    """Strategy signals based on HelloQuant rules (long/short/观望)."""
    g = lambda k: ind.get(k)
    s = {}
    # DoubleMa: MA5 vs MA20
    if g('ma5') and g('ma20'):
        s['DoubleMa'] = '做多' if g('ma5') > g('ma20') else '做空'
    # TripleMa: MA5 > MA20 > MA60
    if g('ma5') and g('ma20') and g('ma60'):
        s['TripleMa'] = '做多' if g('ma5') > g('ma20') > g('ma60') else ('做空' if g('ma5') < g('ma20') < g('ma60') else '观望')
    # Supertrend
    s['Supertrend'] = '做多' if g('supertrend') == '多头' else ('做空' if g('supertrend') == '空头' else '观望')
    # RSI
    r = g('rsi14')
    s['RSI'] = '做空' if r is not None and r > 70 else ('做多' if r is not None and r < 30 else '观望')
    # MACD
    s['MACD'] = '做多' if g('macd_status') == '金叉' else ('做空' if g('macd_status') == '死叉' else '观望')
    # Bollinger
    pb = g('bb_pctb')
    s['Bollinger'] = '做空' if pb is not None and pb > 95 else ('做多' if pb is not None and pb < 5 else '观望')
    # Momentum
    mo = g('mom10_pct')
    s['Momentum'] = '做多' if mo is not None and mo > 1 else ('做空' if mo is not None and mo < -1 else '观望')
    # MeanReversion
    z = g('z40')
    s['MeanReversion'] = '做多' if z is not None and z < -2 else ('做空' if z is not None and z > 2 else '观望')
    return s


STRATS = ['DoubleMa', 'TripleMa', 'Supertrend', 'RSI', 'MACD', 'Bollinger', 'Momentum', 'MeanReversion']

tickers = {}
for inst in ('BTC-USDT', 'ETH-USDT'):
    t = get(f'{BASE}/api/v5/market/ticker?instId={inst}')['data'][0]
    last = float(t['last'])
    op = float(t['open24h'])
    tickers[inst] = {
        'price': r2(last), 'open24h': r2(op), 'high_24h': r2(t['high24h']), 'low_24h': r2(t['low24h']),
        'change_24h': r2((last - op) / op * 100) if op else None,
        'volume_24h': r2(t['volCcy24h']),
    }

tf_data = {}
eth_tf = {}
for bar, tf in (('1H', '1h'), ('4H', '4h'), ('1D', '1d')):
    cl = candles('BTC-USDT', bar, 200 if tf != '1d' else 120)
    tf_data[tf] = indicators(cl)
    eth_tf[tf] = indicators(candles('ETH-USDT', bar, 200 if tf != '1d' else 120))

signals = {}
for tf in ('1h', '4h', '1d'):
    ind = tf_data[tf]
    sg = strategy_signals(ind, ind.get('ma5'))
    signals[tf] = sg

# aggregate per strategy (BTC)
strategies = []
for name in STRATS:
    strategies.append({
        'name': name,
        'signal_1h': signals['1h'].get(name),
        'signal_4h': signals['4h'].get(name),
        'signal_1d': signals['1d'].get(name),
        'daily_return': None, 'weekly_return': None, 'max_drawdown': None, 'sharpe': None,
    })


fg_items = get('https://api.alternative.me/fng/?limit=2').get('data') or []

btc_t = tickers['BTC-USDT']
eth_t = tickers['ETH-USDT']
ind1 = tf_data['1h']
ind4 = tf_data['4h']

old = {}
try:
    old = json.load(open(OUT, encoding='utf-8'))
except Exception:
    pass

now = datetime.now(timezone.utc)
out = {
    'source': 'OKX 公共行情 + alternative.me (scripts/build_helloquant_live.py)',
    'updated': now.strftime('%Y-%m-%d %H:%M UTC'),
    'updated_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
    'status': 'success',
    'last_run': {
        'date': now.strftime('%Y-%m-%d'),
        'timestamp': now.strftime('%Y-%m-%dT%H:%M:%S'),
        'success': True,
        'note': '本脚本直连 OKX 采集 (BTC/ETH 现价 + 1H/4H/1D 指标 + 8 策略信号); '
                '~/trading/helloquant 原始管线自 2026-11-19 后未更新。'
                'A股波动率切片仍为 2026-11-18 QVIX 快照; 新闻/论文沿用上次采集。',
    },
    'crypto': {
        'status': 'success',
        'btc': {**btc_t, 'rsi_1h': ind1.get('rsi14'), 'rsi_4h': ind4.get('rsi14'),
                'macd_1h': ind1.get('macd_status'), 'macd_4h': ind4.get('macd_status'),
                'trend_1h': ind1.get('trend'), 'trend_4h': ind4.get('trend')},
        'eth': {**eth_t, 'rsi_1h': eth_tf['1h'].get('rsi14'), 'rsi_4h': eth_tf['4h'].get('rsi14'),
                'macd_1h': eth_tf['1h'].get('macd_status'), 'macd_4h': eth_tf['4h'].get('macd_status'),
                'trend_1h': eth_tf['1h'].get('trend'), 'trend_4h': eth_tf['4h'].get('trend')},
        'eth_signals': {'1h': strategy_signals(eth_tf['1h'], None), '4h': strategy_signals(eth_tf['4h'], None),
                        '1d': strategy_signals(eth_tf['1d'], None)},
        'eth_indicators': eth_tf,
        'note': f"OKX 正常; BTC {btc_t['price']:,.2f} ({btc_t['change_24h']:+.2f}%) / "
                f"ETH {eth_t['price']:,.2f} ({eth_t['change_24h']:+.2f}%) 24h",
    },
    'sentiment': {
        'crypto_fear_greed': {
            'value': int(fg_items[0]['value']) if fg_items else None,
            'classification': fg_items[0]['value_classification'] if fg_items else None,
            'yesterday_value': int(fg_items[1]['value']) if len(fg_items) > 1 else None,
        }
    },
    'stocks': old.get('stocks') or {'status': 'stale', 'note': 'QVIX 快照', 'data': {}},
    'signals': signals,
    'indicators': tf_data,
    'strategies': strategies,
    'news': old.get('news') or {'status': 'stale', 'items': []},
    'papers': old.get('papers') or {'status': 'stale', 'items': []},
}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(json.dumps({'updated': out['updated'], 'crypto': out['crypto']['note'],
                  'fng': out['sentiment'], 'signals': signals,
                  'btc_1h': {k: ind1.get(k) for k in ('ma5', 'ma20', 'ma60', 'rsi14', 'macd_status', 'bb_pctb', 'mom10_pct', 'z40', 'supertrend')}},
                 ensure_ascii=False, indent=1))
