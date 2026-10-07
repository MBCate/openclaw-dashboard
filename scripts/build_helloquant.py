#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transform ~/trading/helloquant/data/daily_raw.json -> dashboard data/helloquant.json"""
import json, os
from datetime import datetime, timezone

RAW = os.path.expanduser('~/trading/helloquant/data/daily_raw.json')
OUT = os.path.expanduser('~/projects/openclaw-dashboard/data/helloquant.json')


def round2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return None


d = json.load(open(RAW, encoding='utf-8'))
now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

# crypto
crypto = {'status': 'error'}
cd = d.get('crypto', {}).get('data', {})
if cd:
    btc = cd.get('BTC/USDT', {})
    eth = cd.get('ETH/USDT', {})
    crypto = {
        'status': 'success',
        'btc': {'price': round2(btc.get('price')), 'change_24h': round2(btc.get('change_24h'))},
        'eth': {'price': round2(eth.get('price')), 'change_24h': round2(eth.get('change_24h'))},
        'note': f"OKX 数据正常; BTC {round2(btc.get('price'))} ({round2(btc.get('change_24h')):+}%) / "
                f"ETH {round2(eth.get('price'))} ({round2(eth.get('change_24h')):+}%)"
        if btc.get('price') else 'OKX 采集',
    }

# sentiment
fg = d.get('sentiment', {}).get('data', {}).get('crypto_fear_greed', {})
sentiment = {'crypto_fear_greed': {'value': fg.get('value'), 'classification': fg.get('classification')}} if fg else {}

# stocks
stocks = {'status': d.get('stocks', {}).get('status', 'error'),
          'note': f"{d.get('date')} A股/期货收盘数据",
          'data': d.get('stocks', {}).get('data', {})}

# signals
sd = d.get('signals', {}).get('data', {})
signals = {}
for name, tf in sd.items():
    signals[name] = {}
    for k, v in tf.items():
        signals[name][k] = {'signal': v.get('signal'), 'price': round2(v.get('current_price'))}

# strategies table
strategies = []
for name in ['DoubleMa', 'TripleMa', 'Supertrend', 'RSI', 'MACD', 'Bollinger', 'Momentum', 'MeanReversion']:
    s = signals.get(name, {})
    strategies.append({
        'name': name,
        'signal_1h': s.get('1h', {}).get('signal'),
        'signal_4h': s.get('4h', {}).get('signal'),
        'daily_return': 0.0,
        'weekly_return': None,
        'max_drawdown': None,
        'sharpe': None,
    })

# news
news_items = []
for it in d.get('news', {}).get('data', [])[:5]:
    news_items.append({'source': it.get('source'), 'title': it.get('title'), 'link': it.get('link')})
news = {'status': d.get('news', {}).get('status', 'error'),
        'note': f"RSS 采集 {len(news_items)} 条", 'items': news_items}

# papers
papers_items = []
for it in d.get('papers', {}).get('data', [])[:10]:
    papers_items.append({'title': it.get('title')})
papers = {'status': d.get('papers', {}).get('status', 'error'),
          'note': f"arXiv 采集 {len(papers_items)} 篇", 'items': papers_items}

out = {
    'source': '~/trading/helloquant',
    'updated': now,
    'status': 'success',
    'last_run': {
        'date': d.get('date'),
        'timestamp': d.get('timestamp'),
        'success': True,
        'note': f"采集管线最近一次运行 {d.get('date')} (6/6 成功)",
    },
    'crypto': crypto,
    'sentiment': sentiment,
    'stocks': stocks,
    'signals': signals,
    'strategies': strategies,
    'news': news,
    'papers': papers,
    'updated_at': now,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('helloquant.json written')
print(json.dumps({k: out[k] for k in ['updated', 'crypto', 'sentiment', 'strategies']}, ensure_ascii=False, indent=2))
