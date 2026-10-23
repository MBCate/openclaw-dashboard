#!/usr/bin/env python3
"""Fetch A-share noon/close data via AkShare (sina-based sources; eastmoney blocked)."""
import json
import os
import sys
from datetime import datetime, timezone

import akshare as ak
import pandas as pd

OUT = os.path.expanduser("~/projects/openclaw-dashboard/data/a-shares.json")
mode = sys.argv[1] if len(sys.argv) > 1 else "noon"

data = {}
# --- indices (sina) ---
idx = ak.stock_zh_index_spot_sina()
idx["代码"] = idx["代码"].str.strip()
targets = {
    "sh000001": ("上证指数", "000001"),
    "sz399001": ("深证成指", "399001"),
    "sz399006": ("创业板指", "399006"),
    "sh000300": ("沪深300", "000300"),
    "sh000016": ("上证50", "000016"),
    "sh000905": ("中证500", "000905"),
    "sh000688": ("科创50", "000688"),
    "sh000852": ("中证1000", "000852"),
}
indices = {}
for code, (name, short) in targets.items():
    row = idx[idx["代码"] == code]
    if row.empty:
        continue
    r = row.iloc[0]
    indices[name] = {
        "code": short,
        "price": round(float(r["最新价"]), 2),
        "change": round(float(r["涨跌额"]), 2),
        "change_pct": round(float(r["涨跌幅"]), 2),
    }
data["indices"] = indices

# hang seng
try:
    hk = ak.stock_hk_index_spot_sina()
    hs = hk[hk["代码"].str.contains("HSI", na=False)]
    if not hs.empty:
        r = hs.iloc[0]
        data["hang_seng"] = {
            "name": "恒生指数",
            "price": round(float(r["最新价"]), 2),
            "change": round(float(r["涨跌额"]), 2),
            "change_pct": round(float(r["涨跌幅"]), 2),
            "time": str(r.get("时间", "")),
        }
except Exception as e:
    print("hangseng fail", e, file=sys.stderr)

# --- turnover: sum of index amounts (sh + sz) ---
try:
    amt_sh = float(idx[idx["代码"] == "sh000001"].iloc[0]["成交额"])
    amt_sz = float(idx[idx["代码"] == "sz399001"].iloc[0]["成交额"])
    data["total_turnover_yi"] = round((amt_sh + amt_sz) / 1e8, 1)
except Exception as e:
    print("turnover fail", e, file=sys.stderr)
data["total_volume_shares"] = 0.0

# --- sectors: aggregate individual stocks by CSRC industry classification ---
try:
    spot = ak.stock_zh_a_spot()
    spot["涨跌幅"] = pd.to_numeric(spot["涨跌幅"], errors="coerce")
    spot["成交额"] = pd.to_numeric(spot["成交额"], errors="coerce")
    ind = ak.stock_sector_spot(indicator="行业")
    ind["涨跌幅"] = pd.to_numeric(ind["涨跌幅"], errors="coerce")
    ind["总成交额"] = pd.to_numeric(ind["总成交额"], errors="coerce")
    ind = ind.sort_values("涨跌幅", ascending=False)
    top = [
        {"name": r["板块"], "change_pct": round(float(r["涨跌幅"]), 2),
         "turnover": round(float(r["总成交额"]) / 1e8, 2)}
        for _, r in ind.head(5).iterrows()
    ]
    bot = [
        {"name": r["板块"], "change_pct": round(float(r["涨跌幅"]), 2),
         "turnover": round(float(r["总成交额"]) / 1e8, 2)}
        for _, r in ind.tail(5)[::-1].iterrows()
    ]
    data["sectors"] = {"top5": top, "bottom5": bot}
    # market breadth
    data["breadth"] = {
        "up": int((spot["涨跌幅"] > 0).sum()),
        "down": int((spot["涨跌幅"] < 0).sum()),
        "flat": int((spot["涨跌幅"] == 0).sum()),
    }
except Exception as e:
    print("sectors fail", e, file=sys.stderr)

data["north_money"] = None
data["north_money_note"] = "沪深港通北向资金自2024-08起已停止实时披露，接口不可用"
now_cn = datetime.now(timezone.utc)
data["date"] = now_cn.strftime("%Y-%m-%d")
data["time"] = mode
data["fetched_at"] = now_cn.strftime("%Y-%m-%dT%H:%M:%SZ")
data["note"] = "数据源: AkShare(新浪财经指数/恒指 + 证监会行业板块聚合)，东财接口被墙。北向资金已暂停披露。"

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(json.dumps({k: data[k] for k in ("indices", "total_turnover_yi", "sectors", "breadth") if k in data}, ensure_ascii=False, indent=1))
