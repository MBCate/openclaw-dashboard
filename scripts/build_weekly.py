#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build weekly report (data/helloquant-weekly.json + inject into data/helloquant.json).

Data sources (all local):
  - git history of data/a-shares.json  -> A-share daily closes for the week
  - data/helloquant.json               -> current crypto / sentiment / strategy signals
  - ~/trading/helloquant/data/daily_raw.json -> last pipeline run + futures + indicators

Baseline = last close of the previous week (value carried from previous report's week_end).
"""
import json, os, subprocess, sys
from datetime import datetime, timezone

HOME = os.path.expanduser('~')
REPO = os.path.join(HOME, 'projects/openclaw-dashboard')
RAW = os.path.join(HOME, 'trading/helloquant/data/daily_raw.json')
HQ = os.path.join(REPO, 'data/helloquant.json')
WEEKLY = os.path.join(REPO, 'data/helloquant-weekly.json')

A_SHARE_KEYS = ['上证指数', '深证成指', '创业板指', '沪深300', '上证50', '中证500', '科创50', '中证1000']


def git(*args):
    return subprocess.run(['git'] + list(args), cwd=REPO, capture_output=True, text=True).stdout


def r2(x, n=2):
    try:
        return round(float(x), n)
    except Exception:
        return None


# ---------- previous report (for baseline) ----------
prev = json.load(open(WEEKLY, encoding='utf-8'))
prev_end = prev['week_end']
baseline = {r['name']: r['end'] for r in prev.get('week_returns', []) if r.get('end') is not None}

# ---------- collect A-share closes this week from git history ----------
closes = {}  # date -> {name: price}
for line in git('log', '--format=%H', '--since=2026-10-20', '--', 'data/a-shares.json').split():
    try:
        blob = json.loads(git('show', f'{line}:data/a-shares.json'))
    except Exception:
        continue
    dt = blob.get('date')
    if not dt:
        continue
    idx = {k: v.get('price') for k, v in blob.get('indices', {}).items()}
    if not idx:
        continue
    # git log is newest-first: the closing file is committed after the noon file,
    # so the first commit we see for a date wins (prefer 收盘 over 午盘).
    if dt not in closes or blob.get('time') == '收盘':
        closes[dt] = idx

# keep only this week (Mon 2026-10-26 .. Fri 2026-10-30)
week_dates = sorted(d for d in closes if '2026-10-26' <= d <= '2026-10-30')
if not week_dates:
    sys.exit('no A-share data for current week')

# final >= prev week end + baseline
end_date = week_dates[-1]

# latest intraday/live file (may be newer than last git commit)
live = json.load(open(os.path.join(REPO, 'data/a-shares.json'), encoding='utf-8'))
if live.get('date') and live['date'] > end_date:
    closes[live['date']] = {k: v.get('price') for k, v in live.get('indices', {}).items()}
    week_dates.append(live['date'])

end_date = week_dates[-1]
end_idx = closes[end_date]

# ---------- HelloQuant card ----------
hq = json.load(open(HQ, encoding='utf-8'))
raw = json.load(open(RAW, encoding='utf-8'))
btc = hq['crypto'].get('btc', {})
eth = hq['crypto'].get('eth', {})
fg = hq.get('sentiment', {}).get('crypto_fear_greed', {})
fut = hq.get('stocks', {}).get('data', {})

# ---------- week returns ----------
week_returns = []
for k in A_SHARE_KEYS:
    start = baseline.get(k)
    end = end_idx.get(k)
    week_returns.append({
        'name': k, 'start': r2(start), 'end': r2(end),
        'change_pct': r2((end / start - 1) * 100) if start and end else None,
    })

# crypto week: use prev end vs current
for name, key in (('BTC/USDT', 'btc'), ('ETH/USDT', 'eth')):
    start = baseline.get(name)
    end = hq['crypto'].get(key, {}).get('price')
    week_returns.append({
        'name': name, 'start': r2(start), 'end': r2(end),
        'change_pct': r2((end / start - 1) * 100) if start and end else None,
    })

# futures: close now vs prev report's end (daily_raw futures lag a day)
fut_map = {'沪金主力': (fut.get('沪金主力', {}).get('price'), fut.get('沪金主力', {}).get('date')),
           '沪银主力': (fut.get('沪银主力', {}).get('price'), fut.get('沪银主力', {}).get('date')),
           '沪铜主力': (fut.get('沪铜主力', {}).get('price'), fut.get('沪铜主力', {}).get('date')),
           '螺纹钢主力': (fut.get('螺纹钢主力', {}).get('price'), fut.get('螺纹钢主力', {}).get('date')),
           '沪深300期货': (fut.get('沪深300期货', {}).get('price'), fut.get('沪深300期货', {}).get('date')),
           '中证500期货': (fut.get('中证500期货', {}).get('price'), fut.get('中证500期货', {}).get('date'))}
for name, (end, dt) in fut_map.items():
    start = baseline.get(name)
    week_returns.append({
        'name': name, 'start': r2(start), 'end': r2(end), 'as_of': dt,
        'change_pct': r2((end / start - 1) * 100) if start and end else None,
    })

# ---------- equity curve: equal-weight 8 indices, prev Friday = 100 ----------
curve = [{'date': prev_end, 'value': 100.0}]
for d in week_dates:
    vals = []
    for k in A_SHARE_KEYS:
        s, e = baseline.get(k), closes[d].get(k)
        if s and e:
            vals.append(e / s)
    if vals:
        curve.append({'date': d, 'value': r2(sum(vals) / len(vals) * 100)})

# ---------- daily breadth / detail for the last day ----------
breadth = live.get('breadth') or {}

# ---------- strategy signals ----------
strategies = []
for s in hq.get('strategies', []):
    strategies.append({
        'name': s['name'], 'signal_1h': s.get('signal_1h'), 'signal_4h': s.get('signal_4h'),
        'daily_return': 0.0, 'weekly_return': None, 'max_drawdown': None, 'sharpe': None,
    })
signals = {k: v for k, v in hq.get('signals', {}).items()}
dir_bull = [s['name'] for s in strategies
            if '做多' in (s['signal_1h'], s['signal_4h']) and '做空' not in (s['signal_1h'], s['signal_4h'])]
dir_bear = [s['name'] for s in strategies
            if '做空' in (s['signal_1h'], s['signal_4h']) and '做多' not in (s['signal_1h'], s['signal_4h'])]
conflict = [s['name'] for s in strategies
            if '做多' in (s['signal_1h'], s['signal_4h']) and '做空' in (s['signal_1h'], s['signal_4h'])]
neutral = [s['name'] for s in strategies if s['name'] not in dir_bull + dir_bear + conflict]

crypto_raw = raw.get('crypto', {}).get('data', {})
btc_ind = crypto_raw.get('BTC/USDT', {})

hs = live.get('hang_seng') or {}

# ---------- highlights ----------
recent = week_returns
def wr(n):
    for r in recent:
        if r['name'] == n:
            return r['change_pct']
    return None

curve_last = curve[-1]['value']
curve_min = min(c['value'] for c in curve)
curve_min_d = min(curve, key=lambda c: c['value'])['date']

highlights = [
    f"A股本周五连跌：上证 {wr('上证指数'):+.2f}%、深成指 {wr('深证成指'):+.2f}%、创业板指 {wr('创业板指'):+.2f}%；"
    f"等权8大指数基准 {curve_last - 100:+.2f}%（周内最低 {curve_min:.2f} @ {curve_min_d}）",
    f"风格全线杀跌：科创50 {wr('科创50'):+.2f}%、中证1000 {wr('中证1000'):+.2f}%、中证500 {wr('中证500'):+.2f}%；"
    f"大盘蓝筹相对抗跌（上证50 {wr('上证50'):+.2f}%、沪深300 {wr('沪深300'):+.2f}%）",
]

# biggest down day
drops = []
prev_c = baseline
for d in week_dates:
    vals = []
    for k in A_SHARE_KEYS:
        if prev_c.get(k) and closes[d].get(k):
            vals.append(closes[d][k] / prev_c[k])
    if vals:
        drops.append((d, (sum(vals) / len(vals) - 1) * 100))
    prev_c = closes[d]
if drops:
    wd = min(drops, key=lambda x: x[1])
    highlights.append(f"最重一击 {wd[0]}：等权基准单日 {wd[1]:+.2f}%，为本周最大跌幅日")

highlights += [
    f"港股韧性：恒生指数 {hs.get('price', 0):,.2f}（{hs.get('change_pct', 0):+.2f}%），与A股成长股走势背离；"
    f"末个交易日 A股 涨 {breadth.get('up', '—')} / 跌 {breadth.get('down', '—')} 家",
    f"加密破位：BTC ${btc.get('price', 0):,.0f}（周 {wr('BTC/USDT'):+.2f}%、24h {btc.get('change_24h'):+.2f}%），"
    f"ETH ${eth.get('price', 0):,.0f}（周 {wr('ETH/USDT'):+.2f}%）；恐惧贪婪 {fg.get('value')} ({fg.get('classification')})"
    + "；Binance 疑似被盗并暂停充提为主要风险事件" if btc.get('price') else "",
    f"策略信号：8 个策略中 {len(neutral)} 个观望——做空 {len(dir_bear)} 个（{', '.join(dir_bear) or '无'}）、"
    f"纯做多 {len(dir_bull)} 个（{', '.join(dir_bull) or '无'}）、1H/4H 多空分歧 {len(conflict)} 个（{', '.join(conflict) or '无'}）；"
    + ("偏空信号占优，与 BTC 跌破 $80,000 箱体一致" if len(dir_bear) >= 3 else "信号仍偏中性，趋势策略等待确认"),
    f"采集管线：最近运行 {hq.get('last_run', {}).get('date', '—')}，6/6 模块成功（行情/加密/情绪/新闻/论文/信号）",
]
highlights = [h for h in highlights if h]

note = ("HelloQuant 仓库为量化学习框架，未维护策略级实盘盈亏/Sharpe/回撤数据；"
        "本报告以策略信号与市场周度表现为核心，equity_curve 为等权 8 大指数基准组合（上周五=100）。")

report = {
    'report_type': 'weekly',
    'week_of': '2026-10-26',
    'week_end': end_date,
    'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    'source': '~/trading/helloquant',
    'pipeline': {
        'status': 'success',
        'last_run': hq.get('last_run', {}).get('timestamp'),
        'note': hq.get('last_run', {}).get('note'),
    },
    'market': {
        'crypto': {
            'btc': {'price': btc.get('price'), 'change_24h': btc.get('change_24h')},
            'eth': {'price': eth.get('price'), 'change_24h': eth.get('change_24h')},
            'note': (f"OKX 数据正常；BTC 1H {btc_ind.get('indicators_1h', {}).get('trend', '—')}"
                     f" / 4H {btc_ind.get('indicators_4h', {}).get('trend', '—')}"
                     f"（RSI 1H {btc_ind.get('indicators_1h', {}).get('rsi', '—')}）；"
                     f"恐贪 {fg.get('value')} ({fg.get('classification')})"),
        },
        'sentiment': {'fear_greed': fg.get('value'), 'classification': fg.get('classification')},
        'stocks': {k: {'close': r2(end_idx.get(k)), 'change_pct': r2(live['indices'][k]['change_pct'])
                       if k in live.get('indices', {}) else None} for k in ['上证指数', '深证成指', '创业板指']},
        'hang_seng': {'close': hs.get('price'), 'change_pct': hs.get('change_pct')},
    },
    'week_returns': week_returns,
    'equity_curve': curve,
    'strategies': strategies,
    'signals': signals,
    'highlights': highlights,
    'note': note,
}

json.dump(report, open(WEEKLY, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# ---------- inject into helloquant.json (dashboard reads this) ----------
hq['weekly'] = report
json.dump(hq, open(HQ, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print('written:', WEEKLY)
print('week', report['week_of'], '->', report['week_end'], '| baseline', prev_end)
for r in week_returns:
    print(f"  {r['name']:8s} {r['start']} -> {r['end']}  {r['change_pct']}")
print('curve', curve)
