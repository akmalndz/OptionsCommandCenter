"""
NVDA Options Command Center v4 — Elite Options / Brando Levels Edition
New in v4:
  - Brando's full S/R map (Monthly + Weekly + Daily from TrendSpider charts)
  - Scenario engine: price position relative to Brando's key levels
  - On-level alert when within $3 of a starred level
  - Build_alignment gates now reference Brando levels ($180.34, $184.58, $191)
  - Full "Brando Level Map" panel in dashboard
  - Two-scenario trade plan (Scenario A / Scenario B) auto-generated
Runs 12x/day via GitHub Actions at key NVDA liquidity windows (Chicago time)
"""

import yfinance as yf
import datetime, pytz, math
import feedparser
import numpy as np
from pathlib import Path

CT = pytz.timezone("America/Chicago")
ET = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────
# BRANDO / ELITE OPTIONS LEVELS
# Source: @EliteOptions2 TrendSpider (Monthly + Weekly + Daily charts)
# ─────────────────────────────────────────────
BRANDO = [
    # (price, tf, short_label, note, is_key)
    # ── MONTHLY ──
    (288.00,"MO","$7T MCAP TARGET",   "Brando's mega bull target — $7 trillion market cap",         True),
    (225.00,"MO","MAJOR RESISTANCE",  "Monthly supply zone",                                         False),
    (200.00,"MO","KEY WALL $200",     "Tested 2x on monthly — major resistance",                     True),
    (191.00,"MO","YELLOW LINE $191",  "Appears on monthly AND weekly — Brando watches this closely", True),
    (168.00,"MO","RESISTANCE",        "Monthly level",                                                False),
    (153.37,"MO","DEMAND ZONE TOP",   "Top of monthly demand zone — institutional buy area",          True),
    (141.20,"MO","DEMAND ZONE BOT",   "Bottom of monthly demand zone",                               True),
    (123.94,"MO","YELLOW LINE $124",  "Monthly yellow support pivot",                                True),
    (98.43, "MO","SUPPORT",           "Monthly level",                                                False),
    (76.46, "MO","DEEP DEMAND",       "Lower monthly demand zone",                                    True),
    (50.95, "MO","DEEP SUPPORT",      "Monthly floor",                                                False),
    # ── WEEKLY ──
    (250.00,"WK","RESISTANCE",        "Weekly purple line",                                           False),
    (225.30,"WK","MAJOR RESISTANCE",  "Weekly supply",                                                False),
    (212.32,"WK","PRIOR ATH ZONE",    "Prior all-time high area",                                     True),
    (200.08,"WK","KEY WALL $200",     "Weekly — matches monthly $200",                               True),
    (175.00,"WK","CRITICAL SUPPORT",  "Weekly purple line — last bull defense below $180",            True),
    (149.84,"WK","SUPPORT",           "Weekly level",                                                 False),
    (141.23,"WK","SUPPORT",           "Weekly level",                                                 False),
    (132.86,"WK","SUPPORT",           "Weekly level",                                                 False),
    (123.12,"WK","SUPPORT",           "Weekly level",                                                 False),
    (115.42,"WK","SUPPORT",           "Weekly level",                                                 False),
    (107.50,"WK","SUPPORT",           "Weekly level",                                                 False),
    (95.27, "WK","SUPPORT",           "Weekly level",                                                 False),
    (88.19, "WK","DOUBLE BOTTOM",     "Double bottom base — entire 2024-25 rally launched here",      True),
    # ── DAILY ──
    (200.60,"DY","RESISTANCE",        "Daily red line",                                               False),
    (196.05,"DY","RESISTANCE",        "Daily red line",                                               False),
    (190.40,"DY","RESISTANCE",        "Daily red line",                                               False),
    (184.58,"DY","KEY RESISTANCE",    "Daily ceiling — 200MA cluster zone — first wall to break",     True),
    (180.34,"DY","CRITICAL PIVOT",    "Most important daily level — floor AND ceiling — decision pt", True),
    (175.20,"DY","SUPPORT",           "Daily support",                                                False),
    (168.69,"DY","SUPPORT",           "Daily support",                                                False),
    (163.67,"DY","SUPPORT",           "Daily support",                                                False),
    (158.26,"DY","SUPPORT",           "Daily support",                                                False),
    (153.28,"DY","SUPPORT",           "Daily — merges with monthly demand zone",                      True),
    (149.11,"DY","SUPPORT",           "Daily support",                                                False),
    (144.22,"DY","SUPPORT",           "Daily support",                                                False),
    (140.77,"DY","SUPPORT",           "Daily support",                                                False),
    (136.59,"DY","SUPPORT",           "Daily support",                                                False),
]

TF_COLOR = {"MO": "#b39ddb", "WK": "#7c4dff", "DY": "#4fc3f7"}
TF_LABEL = {"MO": "MONTHLY", "WK": "WEEKLY",  "DY": "DAILY"}

def get_brando_context(price):
    """Returns scenario, nearest key level, next resistance, next support."""
    res = sorted([(p,tf,l,n,k) for (p,tf,l,n,k) in BRANDO if p > price],  key=lambda x: x[0])
    sup = sorted([(p,tf,l,n,k) for (p,tf,l,n,k) in BRANDO if p <= price], key=lambda x: x[0], reverse=True)

    nearest     = min(BRANDO, key=lambda x: abs(x[0]-price))
    on_level    = abs(nearest[0]-price) <= 3.0 and nearest[4]  # within $3 of a KEY level

    key_res = next((l for l in res if l[4]), res[0]  if res else None)
    key_sup = next((l for l in sup if l[4]), sup[0]  if sup else None)

    # Scenario engine
    if price >= 200.00:
        scen_label = "🚀 ABOVE $200 WALL"
        scen_color = "#00ff9d"
        scen_a = f"Hold calls. Target $212 (ATH zone) then $225. Trail stop to $196."
        scen_b = f"Rejection at $200-$212 → take profit on calls. Watch for reversal."
    elif price >= 191.00:
        scen_label = "🔥 ABOVE YELLOW LINE"
        scen_color = "#00ff9d"
        scen_a = f"Bullish. Next wall: $200.08. Buy pullbacks to $191 on 1H."
        scen_b = f"Loses $191 → drops back to $184.58. Calls become risky."
    elif price >= 184.58:
        scen_label = "📈 BETWEEN $184 AND $191"
        scen_color = "#ffd700"
        scen_a = f"Break + close above $184.58 with vol → call target $191 yellow line."
        scen_b = f"Rejection at $184.58 → pullback to $180.34. Reassess."
    elif price >= 180.34:
        scen_label = "⚠️ ON $180.34 — DECISION"
        scen_color = "#ff8c42"
        scen_a = f"CALL: Holds $180.34, reclaims $184.58 → April $190C or $195C. Target $191."
        scen_b = f"PUT: Breaks $180.34 on volume → April $175P. Target $175 weekly support."
    elif price >= 175.00:
        scen_label = "🔴 BELOW $180 — BEARISH"
        scen_color = "#ff3a5e"
        scen_a = f"PUT active. Target $175 weekly purple line. Stop above $180.34."
        scen_b = f"Bounce to $180.34 and fails (lower high) → add to puts."
    elif price >= 153.37:
        scen_label = "🔴 APPROACHING DEMAND"
        scen_color = "#ff3a5e"
        scen_a = f"Puts still valid targeting $153-$141 monthly demand zone."
        scen_b = f"Watch for volume reversal candle AT $153.37 — potential call entry."
    else:
        scen_label = "🆘 INSIDE MONTHLY DEMAND"
        scen_color = "#ffd700"
        scen_a = f"Monthly demand zone $141-$153 — institutional buyers expected here."
        scen_b = f"Watch for weekly reversal candle before entering calls. High risk zone."

    return {
        "res": res[:8], "sup": sup[:8],
        "key_res": key_res, "key_sup": key_sup,
        "nearest": nearest, "on_level": on_level,
        "scen_label": scen_label, "scen_color": scen_color,
        "scen_a": scen_a, "scen_b": scen_b,
    }


# ─────────────────────────────────────────────
# SESSION PHASES (Chicago time)
# ─────────────────────────────────────────────
SESSIONS = [
    {"name":"PRE-MARKET",       "start":(7,0),  "end":(8,30),  "color":"#5a7a99","emoji":"🌅","trade":False,
     "advice":"Bias check only. Watch futures & pre-market news. No trades."},
    {"name":"OPENING FAKE-OUT", "start":(8,30), "end":(9,15),  "color":"#ff8c42","emoji":"⚠️","trade":False,
     "advice":"FAKE-OUT ZONE. Wait for direction to hold 2+ candles before entering."},
    {"name":"CONTINUATION",     "start":(9,15), "end":(10,30), "color":"#ffd700","emoji":"📈","trade":True,
     "advice":"Trend continuation if real. Look for pullback to 8/21 EMA as entry."},
    {"name":"DEAD ZONE / CHOP", "start":(10,30),"end":(13,0),  "color":"#ff3a5e","emoji":"💤","trade":False,
     "advice":"PREMIUM DECAY. Theta bleeds fast. No new entries. Hold existing if profitable only."},
    {"name":"POWER WINDOW",     "start":(13,0), "end":(14,30), "color":"#00ff9d","emoji":"🏆","trade":True,
     "advice":"BEST WINDOW. Institutional push builds 1-3 day swings here. Highest conviction entries."},
    {"name":"CLOSING PUSH",     "start":(14,30),"end":(15,0),  "color":"#4fc3f7","emoji":"🔔","trade":True,
     "advice":"Final push. Hold if working. Exit before close if down."},
    {"name":"AFTER HOURS",      "start":(15,0), "end":(23,59), "color":"#5a7a99","emoji":"🌙","trade":False,
     "advice":"Market closed. Review trades. Plan tomorrow's setup."},
]

def get_session(ct_now):
    t = ct_now.hour * 60 + ct_now.minute
    for s in SESSIONS:
        if s["start"][0]*60+s["start"][1] <= t < s["end"][0]*60+s["end"][1]:
            return s
    return SESSIONS[-1]

# ─────────────────────────────────────────────
# INDICATOR HELPERS
# ─────────────────────────────────────────────
def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def atr(hist, period=14):
    h, l, c = hist["High"], hist["Low"], hist["Close"]
    tr = np.maximum(h-l, np.maximum(abs(h-c.shift(1)), abs(l-c.shift(1))))
    return tr.rolling(period).mean()

def bollinger_width(series, period=20):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    return ((mid+2*std)-(mid-2*std)) / mid * 100

def macd_histogram(series, fast=12, slow=26, signal=9):
    macd = ema(series,fast) - ema(series,slow)
    return macd - ema(macd, signal)

def detect_rsi_divergence(h, rsi_period=5, lookback=3, max_bars=40):
    """
    eemani123-style RSI divergence detector.
    RSI period 5, pivot lookback 3 bars each side.
    Returns dict with divergence type found on the most recent pivot pair.
    Types: 'regular_bull', 'hidden_bull', 'regular_bear', 'hidden_bear', None
    """
    try:
        c = h["Close"]
        if len(c) < max_bars + rsi_period + lookback * 2 + 5:
            return {"type": None, "label": "—", "color": "#5a7a99", "desc": "Insufficient data"}

        delta = c.diff()
        gain  = delta.clip(lower=0).ewm(com=rsi_period-1, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(com=rsi_period-1, adjust=False).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi_vals = (100 - (100 / (1 + rs))).fillna(50)

        prices = c.values
        rsi_v  = rsi_vals.values
        n      = len(prices)

        def is_pivot_low(arr, i, lb):
            return i >= lb and i < len(arr)-lb and all(arr[i] <= arr[i-j] for j in range(1,lb+1)) and all(arr[i] <= arr[i+j] for j in range(1,lb+1))

        def is_pivot_high(arr, i, lb):
            return i >= lb and i < len(arr)-lb and all(arr[i] >= arr[i-j] for j in range(1,lb+1)) and all(arr[i] >= arr[i+j] for j in range(1,lb+1))

        start = max(lookback, n - max_bars)
        pivot_lows  = [i for i in range(start, n-lookback) if is_pivot_low(prices, i, lookback)]
        pivot_highs = [i for i in range(start, n-lookback) if is_pivot_high(prices, i, lookback)]

        result = {"type": None, "label": "—", "color": "#5a7a99", "desc": "No divergence detected"}

        # ── BULL DIVERGENCES (2 pivot lows) ──
        if len(pivot_lows) >= 2:
            p1, p2 = pivot_lows[-2], pivot_lows[-1]
            price_ll = prices[p2] < prices[p1]
            price_hl = prices[p2] > prices[p1]
            rsi_hl   = rsi_v[p2]  > rsi_v[p1]
            rsi_ll   = rsi_v[p2]  < rsi_v[p1]
            if price_ll and rsi_hl:
                result = {"type":"regular_bull","label":"🟢 REG BULL DIV",
                          "color":"#00ff9d",
                          "desc":f"Price LL (${prices[p1]:.2f}→${prices[p2]:.2f}) / RSI HL ({rsi_v[p1]:.1f}→{rsi_v[p2]:.1f}) — seller exhaustion, reversal UP",
                          "rsi_p1":round(rsi_v[p1],1),"rsi_p2":round(rsi_v[p2],1)}
            elif price_hl and rsi_ll:
                result = {"type":"hidden_bull","label":"🔵 HIDDEN BULL DIV",
                          "color":"#4fc3f7",
                          "desc":f"Price HL (${prices[p1]:.2f}→${prices[p2]:.2f}) / RSI LL ({rsi_v[p1]:.1f}→{rsi_v[p2]:.1f}) — trend continuation UP",
                          "rsi_p1":round(rsi_v[p1],1),"rsi_p2":round(rsi_v[p2],1)}

        # ── BEAR DIVERGENCES (2 pivot highs) — only if no bull found ──
        if result["type"] is None and len(pivot_highs) >= 2:
            p1, p2 = pivot_highs[-2], pivot_highs[-1]
            price_hh = prices[p2] > prices[p1]
            price_lh = prices[p2] < prices[p1]
            rsi_lh   = rsi_v[p2]  < rsi_v[p1]
            rsi_hh   = rsi_v[p2]  > rsi_v[p1]
            if price_hh and rsi_lh:
                result = {"type":"regular_bear","label":"🔴 REG BEAR DIV",
                          "color":"#ff3a5e",
                          "desc":f"Price HH (${prices[p1]:.2f}→${prices[p2]:.2f}) / RSI LH ({rsi_v[p1]:.1f}→{rsi_v[p2]:.1f}) — buyer exhaustion, reversal DOWN",
                          "rsi_p1":round(rsi_v[p1],1),"rsi_p2":round(rsi_v[p2],1)}
            elif price_lh and rsi_hh:
                result = {"type":"hidden_bear","label":"🟠 HIDDEN BEAR DIV",
                          "color":"#ff8c42",
                          "desc":f"Price LH (${prices[p1]:.2f}→${prices[p2]:.2f}) / RSI HH ({rsi_v[p1]:.1f}→{rsi_v[p2]:.1f}) — dead cat bounce, trend DOWN",
                          "rsi_p1":round(rsi_v[p1],1),"rsi_p2":round(rsi_v[p2],1)}

        return result
    except Exception as e:
        return {"type": None, "label": "—", "color": "#5a7a99", "desc": f"Error: {e}"}


def compression_score(hist):
    atr_now  = atr(hist).iloc[-1]
    atr_mean = atr(hist,50).iloc[-1]
    bb_now   = bollinger_width(hist["Close"]).iloc[-1]
    bb_mean  = bollinger_width(hist["Close"],50).iloc[-1]
    ar = max(0,min(1,1-(atr_now/atr_mean))) if atr_mean else 0
    br = max(0,min(1,1-(bb_now/bb_mean)))   if bb_mean  else 0
    return round((ar*0.5+br*0.5)*100, 1)

def higher_highs_lows(hist, lookback=10):
    highs = hist["High"].iloc[-lookback:].values
    lows  = hist["Low"].iloc[-lookback:].values
    hh = all(highs[i]>=highs[i-1] for i in range(1,len(highs)) if i%2==0)
    hl = all(lows[i] >=lows[i-1]  for i in range(1,len(lows))  if i%2==0)
    return hh and hl

# ─────────────────────────────────────────────
# 1. FETCH ALL DATA
# ─────────────────────────────────────────────
def fetch_all():
    nvda = yf.Ticker("NVDA")
    spy  = yf.Ticker("SPY")
    info = nvda.info

    d1   = nvda.history(period="1y",  interval="1d")
    h4   = nvda.history(period="60d", interval="4h")
    h1   = nvda.history(period="30d", interval="1h")
    m5   = nvda.history(period="2d",  interval="5m")
    d1_3m= nvda.history(period="3mo", interval="1d")
    spy_d= spy.history( period="6mo", interval="1d")

    price      = float(info.get("currentPrice") or info.get("regularMarketPrice") or d1["Close"].iloc[-1])
    prev_close = float(info.get("previousClose") or d1["Close"].iloc[-2])
    volume     = int(info.get("regularMarketVolume") or d1["Volume"].iloc[-1])
    avg_vol    = int(info.get("averageVolume")        or d1["Volume"].mean())
    week52h    = float(info.get("fiftyTwoWeekHigh")   or d1["High"].max())
    week52l    = float(info.get("fiftyTwoWeekLow")    or d1["Low"].min())

    def tf_ind(h, label):
        c      = h["Close"]
        e8     = round(float(ema(c,8).iloc[-1]),  2)
        e21    = round(float(ema(c,21).iloc[-1]), 2)
        e50    = round(float(ema(c,50).iloc[-1]), 2)
        rsi_s  = rsi(c)
        r      = round(float(rsi_s.iloc[-1]), 1)
        r_prev = round(float(rsi_s.iloc[-2]), 1)
        mh     = macd_histogram(c)
        mh_n   = round(float(mh.iloc[-1]), 3)
        mh_p   = round(float(mh.iloc[-2]), 3)
        vol_n  = int(h["Volume"].iloc[-1])
        vol_ma = float(h["Volume"].rolling(20).mean().iloc[-1]) or 1
        vr     = round(vol_n/vol_ma, 2)
        hh_hl  = higher_highs_lows(h)
        return {
            "label":label,"e8":e8,"e21":e21,"e50":e50,"rsi":r,"rsi_prev":r_prev,
            "macd_h":mh_n,"macd_h_prev":mh_p,"vol_ratio":vr,"hh_hl":hh_hl,
            "price_vs_e8":  price>e8,
            "price_vs_e21": price>e21,
            "price_vs_e50": price>e50,
            "fast_bull":    e8>e21,
            "above_cloud":  price>max(e21,e50),
            "below_cloud":  price<min(e21,e50),
            "macd_bull":    mh_n>0,
            "macd_turning": mh_n>0 and mh_p<0,
            "macd_turning_bear": mh_n<0 and mh_p>0,
            "rsi_pullback_bull":  45<=r<=55,
            "rsi_expansion_bull": r>60,
            "rsi_pullback_bear":  45<=r<=55,
            "rsi_expansion_bear": r<40,
            "rsi_cross_above_50": r_prev < 50 <= r,
            "rsi_above_50":       r >= 50,
            "rsi_cross_below_50": r_prev > 50 >= r,
            "rsi_below_50":       r < 50,
            "vol_expanded": vr>=1.5,
            "vol_ok":       vr>=1.0,
        }

    daily = tf_ind(d1,  "DAILY")
    h4_tf = tf_ind(h4,  "4-HOUR") if len(h4)>=50 else None
    h1_tf = tf_ind(h1,  "1-HOUR") if len(h1)>=50 else None

    # RSI divergence (eemani123 method: period 5, lookback 3)
    div_4h = detect_rsi_divergence(h4) if len(h4)>=50 else {"type":None,"label":"—","color":"#5a7a99","desc":"No 4H data"}
    div_1h = detect_rsi_divergence(h1) if len(h1)>=50 else {"type":None,"label":"—","color":"#5a7a99","desc":"No 1H data"}

    spy_e50   = float(ema(spy_d["Close"],50).iloc[-1])
    spy_price = float(spy_d["Close"].iloc[-1])
    spy_bull  = spy_price > spy_e50

    comp    = compression_score(d1_3m) if len(d1_3m)>=50 else 0
    atr_val = round(float(atr(d1).iloc[-1]), 2)
    vol20ma = float(d1["Volume"].rolling(20).mean().iloc[-1])

    recent_candles = []
    if len(m5)>=4:
        for idx, row in m5.tail(8).iterrows():
            try:    ts = idx.tz_convert(CT).strftime("%I:%M %p")
            except: ts = str(idx)[-8:-3]
            co, cc = float(row["Open"]), float(row["Close"])
            recent_candles.append({
                "time":ts,"open":round(co,2),"high":round(float(row["High"]),2),
                "low":round(float(row["Low"]),2),"close":round(cc,2),
                "volume":int(row["Volume"]),"bull":cc>=co,
            })

    id_high = round(float(m5["High"].max()),2) if len(m5) else price
    id_low  = round(float(m5["Low"].min()),2)  if len(m5) else price

    return {
        "price":price,"prev_close":round(prev_close,2),
        "change":round(price-prev_close,2),
        "change_pct":round((price-prev_close)/prev_close*100,2),
        "volume":volume,"avg_vol":avg_vol,
        "vol_ratio":round(volume/avg_vol,2) if avg_vol else 1.0,
        "vol_20ma":round(vol20ma/1e6,1),
        "week52h":week52h,"week52l":week52l,
        "atr":atr_val,"compression":comp,
        "daily":daily,"h4":h4_tf,"h1":h1_tf,
        "div_4h":div_4h,"div_1h":div_1h,
        "spy_bull":spy_bull,"spy_price":round(spy_price,2),"spy_e50":round(spy_e50,2),
        "recent_candles":recent_candles,"id_high":id_high,"id_low":id_low,
        "d1":d1,"d1_3m":d1_3m,
    }


def fetch_options(price):
    tk   = yf.Ticker("NVDA")
    exps = tk.options
    today  = datetime.datetime.now(ET).date()
    target = today + datetime.timedelta(days=25)
    chosen = next((e for e in exps if datetime.datetime.strptime(e,"%Y-%m-%d").date()>=target), exps[-1] if exps else None)
    if not chosen:
        return {"expiry":"N/A","calls":[],"puts":[],"iv_30":50,"dte":30,"exp_move":0}

    chain = tk.option_chain(chosen)
    dte   = (datetime.datetime.strptime(chosen,"%Y-%m-%d").date()-today).days
    calls_raw, puts_raw = [], []
    iv_atm = 0.50

    for _, r in chain.calls.iterrows():
        s = float(r["strike"])
        if abs(s-price)<=25:
            calls_raw.append({
                "strike":s,
                "price": round(float(r.get("lastPrice",0) or r.get("ask",0) or 0),2),
                "bid":   round(float(r.get("bid",0) or 0),2),
                "ask":   round(float(r.get("ask",0) or 0),2),
                "delta": round(float(r.get("delta",0) or 0),2),
                "theta": round(float(r.get("theta",0) or 0),3),
                "iv":    round(float(r.get("impliedVolatility",0.5) or 0.5)*100,1),
                "volume":int(r.get("volume",0) or 0),
                "oi":    int(r.get("openInterest",0) or 0),
            })
    for _, r in chain.puts.iterrows():
        s = float(r["strike"])
        if abs(s-price)<=20 and s<=price+5:
            puts_raw.append({
                "strike":s,
                "price": round(float(r.get("lastPrice",0) or r.get("ask",0) or 0),2),
                "bid":   round(float(r.get("bid",0) or 0),2),
                "ask":   round(float(r.get("ask",0) or 0),2),
                "delta": round(float(r.get("delta",0) or 0),2),
                "theta": round(float(r.get("theta",0) or 0),3),
                "iv":    round(float(r.get("impliedVolatility",0.5) or 0.5)*100,1),
                "volume":int(r.get("volume",0) or 0),
                "oi":    int(r.get("openInterest",0) or 0),
            })

    atm_c = [c for c in calls_raw if abs(c["strike"]-price)<5]
    if atm_c: iv_atm = atm_c[0]["iv"]/100

    calls_raw.sort(key=lambda x: x["strike"])
    puts_raw.sort(key=lambda x: x["strike"], reverse=True)
    exp_move = round(price * iv_atm * math.sqrt(dte/365), 2)

    return {"expiry":chosen,"calls":calls_raw[:7],"puts":puts_raw[:4],
            "iv_30":round(iv_atm*100,1),"dte":dte,"exp_move":exp_move}


def fetch_news():
    urls = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US",
        "https://finance.yahoo.com/rss/headline?s=NVDA",
    ]
    bull=["beat","surge","rally","upgrade","buy","growth","record","strong","profit","bullish","target","raise","deal","expand","partnership"]
    bear=["miss","drop","fall","downgrade","sell","cut","loss","bearish","concern","risk","decline","weak","ban","tariff","probe","lawsuit"]
    out=[]
    for url in urls:
        try:
            feed=feedparser.parse(url)
            for e in feed.entries[:8]:
                t=e.get("title",""); txt=(t+" "+e.get("summary","")).lower()
                bs=sum(1 for w in bull if w in txt); bs2=sum(1 for w in bear if w in txt)
                out.append({"title":t[:120],"published":e.get("published","")[:30],
                             "link":e.get("link","#"),
                             "sentiment":"bull" if bs>bs2 else ("bear" if bs2>bs else "neut")})
            if out: break
        except: continue
    return out[:7]


# ─────────────────────────────────────────────
# 2. ALIGNMENT + SIGNAL ENGINE
# ─────────────────────────────────────────────
def build_alignment(d, opts, session, bctx):
    daily = d["daily"]; h4 = d["h4"]; h1 = d["h1"]; price = d["price"]

    def tf_bias(tf):
        if not tf: return "N/A","#5a7a99","—","—","—","—","N/A","#5a7a99",0,False
        if tf["above_cloud"] and tf["hh_hl"]: trend,tc="BULLISH","#00ff9d"
        elif tf["below_cloud"]:               trend,tc="BEARISH","#ff3a5e"
        else:                                  trend,tc="NEUTRAL","#ffd700"
        if tf["rsi_expansion_bull"]:  rsi_l,rc=f"{tf['rsi']} ↑","#00ff9d"
        elif tf["rsi_expansion_bear"]: rsi_l,rc=f"{tf['rsi']} ↓","#ff3a5e"
        else:                           rsi_l,rc=f"{tf['rsi']} ~","#ffd700"
        if tf["macd_turning"]:        macd_l,mc="TURNING ↑","#00ff9d"
        elif tf["macd_bull"]:         macd_l,mc="EXPANDING","#00c87a"
        elif tf["macd_turning_bear"]: macd_l,mc="TURNING ↓","#ff3a5e"
        else:                          macd_l,mc="NEGATIVE","#ff3a5e"
        score=sum([tf["above_cloud"],tf["fast_bull"],tf["macd_bull"],tf["hh_hl"],tf["rsi_expansion_bull"]])
        if score>=4:   bias,bc="LONG","#00ff9d"
        elif score<=1: bias,bc="SHORT","#ff3a5e"
        else:           bias,bc="WATCH","#ffd700"
        return trend,tc,rsi_l,rc,macd_l,mc,bias,bc,tf["vol_ratio"],tf["vol_expanded"]

    rows=[]
    for label,tf in [("DAILY",daily),("4-HOUR",h4),("1-HOUR",h1)]:
        if tf:
            trend,tc,rsi_l,rc,macd_l,mc,bias,bc,vr,ve=tf_bias(tf)
            rows.append({"tf":label,"trend":trend,"tc":tc,"rsi":rsi_l,"rc":rc,
                         "macd":macd_l,"mc":mc,"bias":bias,"bc":bc,"vol_ratio":vr,"vol_expanded":ve})

    bull_count=sum(1 for r in rows if r["bias"]=="LONG")
    bear_count=sum(1 for r in rows if r["bias"]=="SHORT")

    # ── CALL SIGNAL (9 gates: G1-G8 core + G9 divergence bonus) ──
    call_score=0; call_reasons=[]
    # G1: Daily cloud
    if daily["above_cloud"]:
        call_score+=1; call_reasons.append("✅ G1: Daily above 21/50 EMA cloud")
    else:
        call_reasons.append(f"❌ G1: Daily below cloud (${max(daily['e21'],daily['e50']):.2f}) — bias bearish")
    # G2: Daily HH/HL
    if daily["hh_hl"]:
        call_score+=1; call_reasons.append("✅ G2: Daily HH/HL structure intact")
    else:
        call_reasons.append("❌ G2: Daily HH/HL broken — trend not confirmed")
    # G3: SPY macro
    if d["spy_bull"]:
        call_score+=1; call_reasons.append(f"✅ G3: SPY above 50 EMA — macro bull regime")
    else:
        call_reasons.append(f"❌ G3: SPY below 50 EMA (${d['spy_price']} vs ${d['spy_e50']}) — macro headwind")
    # G4: Brando $180.34
    if price >= 180.34:
        call_score+=1; call_reasons.append(f"✅ G4: Above Brando $180.34 — call bias valid")
    else:
        call_reasons.append(f"❌ G4: Below Brando $180.34 — not valid for calls until reclaimed")
    # G5: 4H RSI setup filter (is pullback healthy?)
    if h4 and h4["rsi_pullback_bull"]:
        call_score+=1; call_reasons.append(f"✅ G5: 4H RSI pullback zone ({h4['rsi']}) — setup valid, premium discounted")
    elif h4 and h4["rsi_expansion_bull"]:
        call_reasons.append(f"⚠️ G5: 4H RSI extended ({h4['rsi']}) — chasing, wait for cooling to 45–55")
    elif h4:
        call_reasons.append(f"❌ G5: 4H RSI too weak ({h4['rsi']}) — trend not ready")
    else:
        call_reasons.append("❌ G5: 4H data unavailable")
    # G6: 1H RSI entry trigger (momentum resuming now?)
    if h1 and h1["rsi_cross_above_50"]:
        call_score+=1; call_reasons.append(f"✅ G6: 1H RSI crossed above 50 ({h1['rsi_prev']}→{h1['rsi']}) — ENTRY TRIGGER FIRING")
    elif h1 and h1["rsi_above_50"]:
        call_score+=1; call_reasons.append(f"✅ G6: 1H RSI above 50 ({h1['rsi']}) — momentum confirmed")
    elif h1:
        call_reasons.append(f"❌ G6: 1H RSI below 50 ({h1['rsi']}) — wait for cross above 50")
    else:
        call_reasons.append("❌ G6: 1H data unavailable")
    # G7: 1H MACD
    if h1 and (h1["macd_turning"] or h1["macd_bull"]):
        call_score+=1; call_reasons.append(f"✅ G7: 1H MACD positive ({h1['macd_h']:+.3f}) — momentum up")
    else:
        call_reasons.append(f"❌ G7: 1H MACD not positive ({h1['macd_h'] if h1 else 'N/A'})")
    # G8: Volume
    price_up_today = d["change"] >= 0
    vol_ok = d["vol_ratio"] >= 1.0 or (h1 and h1["vol_expanded"])
    if price_up_today and d["vol_ratio"] >= 1.5:
        call_score+=1; call_reasons.append(f"✅ G8: Volume expanding on UP day ({d['vol_ratio']}x) — institutional accumulation")
    elif price_up_today and vol_ok:
        call_score+=1; call_reasons.append(f"✅ G8: Volume OK on UP day ({d['vol_ratio']}x) — participation confirmed")
    elif not price_up_today and d["vol_ratio"] < 1.0:
        call_score+=1; call_reasons.append(f"✅ G8: Low-volume pullback ({d['vol_ratio']}x) — healthy dip, sellers lack conviction")
    elif not price_up_today and d["vol_ratio"] >= 1.5:
        call_reasons.append(f"❌ G8: HIGH volume selling ({d['vol_ratio']}x) — distribution, avoid calls")
    else:
        call_reasons.append(f"❌ G8: Volume not confirming ({d['vol_ratio']}x)")
    # G9: RSI Divergence bonus (eemani123) — bull divergence = +1, bear = exit warning
    div1h = d.get("div_1h",{}); div4h = d.get("div_4h",{})
    call_div_type = div1h.get("type") or div4h.get("type")
    call_div_src  = "1H" if div1h.get("type") else "4H"
    if call_div_type == "regular_bull":
        call_score+=1; call_reasons.append(f"✅ G9: {call_div_src} Regular Bull Divergence — seller exhaustion, HIGH CONVICTION entry. {div1h.get('desc','') or div4h.get('desc','')}")
    elif call_div_type == "hidden_bull":
        call_score+=1; call_reasons.append(f"✅ G9: {call_div_src} Hidden Bull Divergence — trend continuation, add to calls. {div1h.get('desc','') or div4h.get('desc','')}")
    elif call_div_type == "regular_bear":
        call_reasons.append(f"🚨 G9: {call_div_src} Regular Bear Divergence — buyer exhaustion! EXIT calls if in position. {div1h.get('desc','') or div4h.get('desc','')}")
    elif call_div_type == "hidden_bear":
        call_reasons.append(f"⚠️ G9: {call_div_src} Hidden Bear Divergence — dead cat risk, dead zone. {div1h.get('desc','') or div4h.get('desc','')}")
    else:
        call_reasons.append(f"➖ G9: No divergence signal on 1H/4H — standard gate scoring applies")
    if not session["trade"]:
        call_score=max(0,call_score-1)
        call_reasons.append(f"⚠️ Wrong session ({session['name']}) — wait for Power Window 1PM CT")

    # ── PUT SIGNAL (9 gates: G1-G8 core + G9 divergence bonus) ──
    put_score=0; put_reasons=[]
    # G1: Daily cloud
    if daily["below_cloud"]:
        put_score+=1; put_reasons.append("✅ G1: Daily below 21/50 EMA cloud — bearish structure")
    else:
        put_reasons.append("❌ G1: Daily above cloud — bearish setup weak")
    # G2: Daily HH/HL broken
    if not daily["hh_hl"]:
        put_score+=1; put_reasons.append("✅ G2: Daily HH/HL structure broken — downtrend confirmed")
    else:
        put_reasons.append("❌ G2: Daily HH/HL intact — avoid puts")
    # G3: SPY macro
    if not d["spy_bull"]:
        put_score+=1; put_reasons.append("✅ G3: SPY below 50 EMA — macro bear regime")
    else:
        put_reasons.append("❌ G3: SPY above 50 EMA — macro headwind against puts")
    # G4: Brando $180.34
    if price < 180.34:
        put_score+=1; put_reasons.append(f"✅ G4: Below Brando $180.34 — put bias valid")
    else:
        put_reasons.append(f"❌ G4: Above Brando $180.34 — wait for break + retest as resistance")
    # G5: 4H RSI setup filter
    if h4 and h4["rsi_pullback_bear"]:
        put_score+=1; put_reasons.append(f"✅ G5: 4H RSI bounce zone ({h4['rsi']}) — setup valid, put entry on rejection")
    elif h4 and h4["rsi_expansion_bear"]:
        put_score+=1; put_reasons.append(f"✅ G5: 4H RSI oversold ({h4['rsi']}) — breakdown confirmed, puts valid")
    elif h4:
        put_reasons.append(f"❌ G5: 4H RSI too high ({h4['rsi']}) — bounce risk, wait for fade")
    else:
        put_reasons.append("❌ G5: 4H data unavailable")
    # G6: 1H RSI entry trigger
    if h1 and h1["rsi_cross_below_50"]:
        put_score+=1; put_reasons.append(f"✅ G6: 1H RSI crossed below 50 ({h1['rsi_prev']}→{h1['rsi']}) — ENTRY TRIGGER FIRING")
    elif h1 and h1["rsi_below_50"]:
        put_score+=1; put_reasons.append(f"✅ G6: 1H RSI below 50 ({h1['rsi']}) — bearish momentum confirmed")
    elif h1:
        put_reasons.append(f"❌ G6: 1H RSI above 50 ({h1['rsi']}) — wait for cross below 50")
    else:
        put_reasons.append("❌ G6: 1H data unavailable")
    # G7: 1H MACD
    if h1 and (h1["macd_turning_bear"] or not h1["macd_bull"]):
        put_score+=1; put_reasons.append(f"✅ G7: 1H MACD negative ({h1['macd_h']:+.3f}) — momentum down")
    else:
        put_reasons.append(f"❌ G7: 1H MACD not negative")
    # G8: Volume
    price_down_today = d["change"] < 0
    if price_down_today and d["vol_ratio"] >= 1.5:
        put_score+=1; put_reasons.append(f"✅ G8: HIGH volume selling ({d['vol_ratio']}x) on down day — real distribution, puts valid")
    elif price_down_today and d["vol_ratio"] >= 1.0:
        put_score+=1; put_reasons.append(f"✅ G8: Volume confirming decline ({d['vol_ratio']}x) — sellers in control")
    elif price_down_today and d["vol_ratio"] < 1.0:
        put_reasons.append(f"❌ G8: LOW volume on decline ({d['vol_ratio']}x) — dead cat risk. AVOID puts.")
    elif not price_down_today and d["vol_ratio"] >= 1.5:
        put_reasons.append(f"❌ G8: High volume on UP day ({d['vol_ratio']}x) — buyers stepping in, puts risky")
    else:
        put_reasons.append(f"❌ G8: Volume not confirming bearish move ({d['vol_ratio']}x)")
    # G9: RSI Divergence bonus — bear divergence = +1, bull = exit warning
    put_div_type = div1h.get("type") or div4h.get("type")
    put_div_src  = "1H" if div1h.get("type") else "4H"
    if put_div_type == "regular_bear":
        put_score+=1; put_reasons.append(f"✅ G9: {put_div_src} Regular Bear Divergence — buyer exhaustion, HIGH CONVICTION put entry. {div1h.get('desc','') or div4h.get('desc','')}")
    elif put_div_type == "hidden_bear":
        put_score+=1; put_reasons.append(f"✅ G9: {put_div_src} Hidden Bear Divergence — dead cat bounce failing, add to puts. {div1h.get('desc','') or div4h.get('desc','')}")
    elif put_div_type == "regular_bull":
        put_reasons.append(f"🚨 G9: {put_div_src} Regular Bull Divergence — seller exhaustion! EXIT puts if in position. {div1h.get('desc','') or div4h.get('desc','')}")
    elif put_div_type == "hidden_bull":
        put_reasons.append(f"⚠️ G9: {put_div_src} Hidden Bull Divergence — trend continuation UP risk, tighten stops on puts. {div1h.get('desc','') or div4h.get('desc','')}")
    else:
        put_reasons.append(f"➖ G9: No divergence signal on 1H/4H — standard gate scoring applies")

    call_t = next((c for c in opts["calls"] if 3.50<=c["price"]<=6.50), None)
    put_t  = next((p for p in opts["puts"]  if 3.50<=p["price"]<=6.50), None)

    def rr_calc(opt):
        if not opt: return None
        entry=opt["price"]
        stop   = round(entry * 0.50, 2)   # -50% hard stop
        target = round(entry * 1.80, 2)   # +80% profit target
        risk   = round(entry - stop,   2)
        reward = round(target - entry, 2)
        rr     = round(reward / risk, 1) if risk else 0
        budget = 500                       # $5 target option = ~$500/contract
        contracts = max(1, int(budget / (entry * 100)))
        max_loss  = round(contracts * entry * 100 * 0.50, 0)
        return {"entry":entry,"stop":stop,"target":target,"risk":risk,"reward":reward,
                "rr":rr,"contracts":contracts,"max_risk":int(max_loss),
                "budget":budget}

    return {
        "rows":rows,"bull_count":bull_count,"bear_count":bear_count,
        "call_score":call_score,"call_reasons":call_reasons,
        "put_score":put_score,"put_reasons":put_reasons,
        "call_t":call_t,"put_t":put_t,
        "call_rr":rr_calc(call_t),"put_rr":rr_calc(put_t),
    }


def get_verdict(al, d, session, opts, bctx):
    cs=al["call_score"]; ps=al["put_score"]; price=d["price"]
    div1h=d.get("div_1h",{}); div4h=d.get("div_4h",{})
    active_div = div1h.get("type") or div4h.get("type")
    if not session["trade"]:
        return {"verdict":f"💤 {session['name']} — NO NEW TRADES",
                "color":"#ff3a5e","bias":"WAIT","bias_color":"#ff8c42",
                "explanation":session["advice"],
                "trade_idea":"Hold existing if profitable. Next window: Power Window 1:00 PM CT."}
    if cs>=8:
        ct=al["call_t"]; rr=al["call_rr"]
        div_note = " + RSI Divergence confirmed." if active_div in ("regular_bull","hidden_bull") else ""
        return {"verdict":f"✅ CALL — MAX CONFIDENCE (8-9/9){div_note}","color":"#00ff9d","bias":"STRONG BULL","bias_color":"#00ff9d",
                "explanation":f"All gates pass. 4H+1H RSI aligned. Next wall: ${bctx['key_res'][0] if bctx['key_res'] else '—'}.{div_note}",
                "trade_idea":f"Buy ${ct['strike']:.0f}C {opts['expiry']} (~${ct['price']:.2f}) | Stop ${rr['stop']} | Target ${rr['target']} | R:R {rr['rr']}:1" if ct and rr else "Check chain for ATM call."}
    elif cs>=6:
        ct=al["call_t"]; rr=al["call_rr"]
        return {"verdict":f"🟢 CALL SETUP — Strong ({cs}/9)","color":"#00c87a","bias":"BULLISH","bias_color":"#00ff9d",
                "explanation":f"Strong setup. {9-cs} gate(s) pending. Wait for 1H RSI cross above 50 + pullback to EMA8 (${d['h1']['e8'] if d['h1'] else '—'}).",
                "trade_idea":f"Buy ${ct['strike']:.0f}C {opts['expiry']} (~${ct['price']:.2f}) on pullback | Stop ${rr['stop']} | Target ${rr['target']} | R:R {rr['rr']}:1" if ct and rr else "Check chain."}
    elif ps>=8:
        pt=al["put_t"]; rr=al["put_rr"]
        div_note = " + RSI Divergence confirmed." if active_div in ("regular_bear","hidden_bear") else ""
        return {"verdict":f"🔴 PUT — MAX CONFIDENCE (8-9/9){div_note}","color":"#ff3a5e","bias":"STRONG BEAR","bias_color":"#ff3a5e",
                "explanation":f"All bear gates pass. 4H+1H RSI aligned. Next support: ${bctx['key_sup'][0] if bctx['key_sup'] else '—'}.{div_note}",
                "trade_idea":f"Buy ${pt['strike']:.0f}P {opts['expiry']} (~${pt['price']:.2f}) on bounce fail at EMA8 | Stop ${rr['stop']} | Target ${rr['target']} | R:R {rr['rr']}:1" if pt and rr else "Check chain for OTM put."}
    elif ps>=6:
        pt=al["put_t"]; rr=al["put_rr"]
        return {"verdict":f"🟠 PUT SETUP — Building ({ps}/9)","color":"#ff8c42","bias":"BEARISH","bias_color":"#ff3a5e",
                "explanation":f"Bear setup building. Wait for 1H RSI to cross below 50 + bounce to EMA8 (${d['h1']['e8'] if d['h1'] else '—'}) then fail.",
                "trade_idea":f"Buy ${pt['strike']:.0f}P on EMA8 rejection | R:R {rr['rr']}:1" if pt and rr else "Watch for bounce failure."}
    elif cs==ps:
        return {"verdict":"⏸ MIXED — WAIT","color":"#ff8c42","bias":"NEUTRAL","bias_color":"#ffd700",
                "explanation":f"Call {cs}/9 vs Put {ps}/9 — tied. {bctx['scen_label']} — Price needs to pick a direction.",
                "trade_idea":f"Scenario A: {bctx['scen_a']}  |  Scenario B: {bctx['scen_b']}"}
    else:
        leader="CALL" if cs>ps else "PUT"; ls=max(cs,ps)
        return {"verdict":f"⏸ {leader} WATCH — Not Yet ({ls}/9)","color":"#ffd700","bias":"DEVELOPING","bias_color":"#ffd700",
                "explanation":f"Signal {ls}/9 — need 6+ for entry. {bctx['scen_label']}.",
                "trade_idea":f"Scenario A: {bctx['scen_a']}  |  Scenario B: {bctx['scen_b']}"}


# ─────────────────────────────────────────────
# 3. RENDER HTML
# ─────────────────────────────────────────────
def render(d, opts, news, al, verdict, session, bctx, ct_now):
    price=d["price"]; chg=d["change"]; chg_p=d["change_pct"]
    chg_c="#00ff9d" if chg>=0 else "#ff3a5e"
    arrow="▲" if chg>=0 else "▼"
    vol_m=d["volume"]/1e6; avg_m=d["avg_vol"]/1e6
    vol_c="#00ff9d" if d["vol_ratio"]>1.2 else ("#ffd700" if d["vol_ratio"]>0.8 else "#ff3a5e")
    iv_c ="#00ff9d" if opts["iv_30"]<35 else ("#ffd700" if opts["iv_30"]<55 else "#ff3a5e")
    yr   =min(100,(price-d["week52l"])/(d["week52h"]-d["week52l"])*100) if d["week52h"]!=d["week52l"] else 50
    v    =verdict
    spy_c="#00ff9d" if d["spy_bull"] else "#ff3a5e"
    spy_l="BULL ✓" if d["spy_bull"] else "BEAR ✗"
    date_str=ct_now.strftime("%a %b %d, %Y")
    time_str=ct_now.strftime("%I:%M %p CT")
    comp=d["compression"]
    comp_c="#00ff9d" if comp>70 else ("#ffd700" if comp>40 else "#5a7a99")

    # Session timeline
    tl=""
    for s in SESSIONS[:-1]:
        t=ct_now.hour*60+ct_now.minute
        active=s["start"][0]*60+s["start"][1]<=t<s["end"][0]*60+s["end"][1]
        bg=f"background:{s['color']}18;border:1px solid {s['color']};" if active else "background:var(--surface2);border:1px solid var(--border);"
        nc=s["color"] if active else "var(--muted)"
        dot=f'<div style="font-size:.52rem;color:{s["color"]};margin-top:2px">● NOW</div>' if active else ""
        tl+=f'<div style="{bg}padding:7px;text-align:center"><div style="font-size:.52rem;color:var(--muted)">{s["start"][0]:02d}:{s["start"][1]:02d} CT</div><div style="font-size:.6rem;font-weight:700;color:{nc};margin-top:1px">{s["emoji"]} {s["name"]}</div>{dot}</div>'

    # MTF table
    mtf_rows=""
    for r in al["rows"]:
        ve=f'<span style="color:#00ff9d;font-size:.6rem">▲{r["vol_ratio"]}x</span>' if r["vol_expanded"] else f'<span style="color:{"#ffd700" if r["vol_ratio"]>=1.0 else "#ff3a5e"};font-size:.6rem">{r["vol_ratio"]}x</span>'
        mtf_rows+=f'<tr><td style="color:var(--white);font-weight:700">{r["tf"]}</td><td style="color:{r["tc"]};font-weight:700">{r["trend"]}</td><td style="color:{r["rc"]}">{r["rsi"]}</td><td style="color:{r["mc"]}">{r["macd"]}</td><td style="color:{r["bc"]};font-weight:700">{r["bias"]}</td><td>{ve}</td></tr>'

    # Signal reason lists
    def reason_list(reasons, score, max_s):
        html=""
        for r in reasons:
            col="#00ff9d" if r.startswith("✅") else ("#ff3a5e" if r.startswith("❌") else "#ffd700")
            html+=f'<div style="font-size:.63rem;color:{col};padding:3px 0;border-bottom:1px solid rgba(30,58,95,.3)">{r}</div>'
        pct=round(score/max_s*100)
        bc="#00ff9d" if pct>=70 else ("#ffd700" if pct>=50 else "#ff3a5e")
        html+=f'<div style="margin-top:8px"><div style="font-size:.58rem;color:var(--muted);margin-bottom:3px">SIGNAL STRENGTH: {score}/{max_s} ({pct}%)</div><div style="height:5px;background:rgba(255,255,255,.05);border-radius:3px"><div style="height:100%;width:{pct}%;background:{bc};border-radius:3px"></div></div></div>'
        return html

    # R:R box
    def rr_box(rr, direction):
        if not rr: return '<div style="font-size:.65rem;color:var(--muted);padding:10px">No $3 option near ATM</div>'
        bc="#00ff9d" if direction=="call" else "#ff3a5e"
        rc="#00ff9d" if rr["rr"]>=2 else ("#ffd700" if rr["rr"]>=1.5 else "#ff3a5e")
        return f'''<div style="background:var(--surface2);border:1px solid {bc};padding:11px">
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:7px;text-align:center">
            <div><div style="font-size:.54rem;color:var(--muted)">ENTRY</div><div style="font-size:.9rem;color:var(--white);font-weight:700">${rr["entry"]:.2f}</div></div>
            <div><div style="font-size:.54rem;color:var(--muted)">STOP −50%</div><div style="font-size:.9rem;color:var(--red);font-weight:700">${rr["stop"]:.2f}</div></div>
            <div><div style="font-size:.54rem;color:var(--muted)">TARGET +80%</div><div style="font-size:.9rem;color:var(--green);font-weight:700">${rr["target"]:.2f}</div></div>
            <div><div style="font-size:.54rem;color:var(--muted)">R:R</div><div style="font-size:.9rem;font-weight:700;color:{rc}">{rr["rr"]}:1</div></div>
          </div>
          <div style="margin-top:7px;border-top:1px solid rgba(255,255,255,.06);padding-top:7px;display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:.61rem">
            <div>Contracts for $500: <strong style="color:var(--white)">{rr["contracts"]}</strong></div>
            <div>Max loss at stop: <strong style="color:var(--red)">${rr["max_risk"]}</strong></div>
          </div></div>'''

    # Options chain
    def chain_rows(items):
        rows=""
        for c in items:
            atm=' style="background:rgba(255,215,0,.07)"' if abs(c["strike"]-price)<4 else ""
            tgt="🎯" if 3.50<=c["price"]<=6.50 else ""
            sp=round(c["ask"]-c["bid"],2)
            sp_c="#00ff9d" if sp<0.20 else ("#ffd700" if sp<0.40 else "#ff3a5e")
            liq="⚠️" if c["volume"]<200 or c["oi"]<500 else ""
            theta_c="#ff3a5e" if c["theta"]<-0.10 else "#ffd700"
            rows+=f'<tr{atm}><td style="font-size:.61rem;color:var(--muted)">${c["strike"]:.0f} {tgt}</td><td style="color:var(--white);font-weight:700">${c["price"]:.2f}</td><td style="color:var(--blue)">{c["delta"] or "—"}</td><td style="color:{theta_c}">{c["theta"] if c["theta"] else "—"}</td><td style="color:var(--orange)">{c["iv"]}%</td><td style="color:{sp_c}">${sp:.2f}</td><td style="color:var(--green-dim)">{c["volume"]:,}{liq}</td></tr>'
        return rows

    # News
    news_html=""
    for n in news:
        dc="#00ff9d" if n["sentiment"]=="bull" else ("#ff3a5e" if n["sentiment"]=="bear" else "#ffd700")
        lbl="BULLISH" if n["sentiment"]=="bull" else ("BEARISH" if n["sentiment"]=="bear" else "NEUTRAL")
        news_html+=f'<div style="padding:7px 0;border-bottom:1px solid rgba(30,58,95,.4);display:grid;grid-template-columns:7px 1fr;gap:7px"><div style="width:6px;height:6px;border-radius:50%;background:{dc};margin-top:4px"></div><div><div style="font-size:.65rem;line-height:1.4"><a href="{n["link"]}" target="_blank" style="color:inherit;text-decoration:none">{n["title"]}</a><span style="font-size:.57rem;font-weight:700;margin-left:5px;color:{dc}">[{lbl}]</span></div><div style="font-size:.56rem;color:var(--muted);margin-top:1px">{n["published"]}</div></div></div>'

    # ── BRANDO LEVEL MAP ──────────────────────────────────
    # Full level table grouped by timeframe, showing distance from price
    def brando_table():
        # Show 5 resistance above + 5 support below in a combined table
        res5 = bctx["res"][:5]
        sup5 = bctx["sup"][:5]
        rows=""
        for (p,tf,lbl,note,key) in res5:
            dist=round(p-price,2)
            key_marker="★ " if key else ""
            tf_c=TF_COLOR.get(tf,"#aaa")
            bg='background:rgba(255,215,0,.05);' if key else ""
            rows+=f'<tr style="{bg}"><td style="color:{tf_c};font-size:.58rem">{TF_LABEL[tf]}</td><td style="color:{"#ffd700" if key else "#ff3a5e"};font-weight:700">${p:.2f}</td><td style="color:var(--muted);font-size:.6rem">{key_marker}{lbl}</td><td style="color:var(--muted);font-size:.58rem;text-align:right">+${dist:.2f}</td></tr>'
        # Current price row
        on_str=f' ⚡ ON LEVEL: {bctx["nearest"][2]}' if bctx["on_level"] else ""
        rows+=f'<tr style="background:rgba(255,215,0,.08)"><td style="color:#ffd700;font-size:.6rem">NOW</td><td style="color:#ffd700;font-weight:700;font-size:.8rem">▶ ${price:.2f}</td><td style="color:#ffd700;font-size:.6rem" colspan="2">H:{d["id_high"]} L:{d["id_low"]}{on_str}</td></tr>'
        for (p,tf,lbl,note,key) in sup5:
            dist=round(price-p,2)
            key_marker="★ " if key else ""
            tf_c=TF_COLOR.get(tf,"#aaa")
            bg='background:rgba(255,215,0,.05);' if key else ""
            rows+=f'<tr style="{bg}"><td style="color:{tf_c};font-size:.58rem">{TF_LABEL[tf]}</td><td style="color:{"#ffd700" if key else "#00ff9d"};font-weight:700">${p:.2f}</td><td style="color:var(--muted);font-size:.6rem">{key_marker}{lbl}</td><td style="color:var(--muted);font-size:.58rem;text-align:right">−${dist:.2f}</td></tr>'
        return rows

    # On-level alert banner
    on_level_banner=""
    if bctx["on_level"]:
        nl=bctx["nearest"]
        on_level_banner=f'<div style="background:rgba(255,215,0,.1);border:1px solid #ffd700;padding:9px 14px;font-size:.7rem;color:#ffd700;font-weight:700;text-align:center;margin-bottom:0">⚡ PRICE ON BRANDO LEVEL: ${nl[0]:.2f} — {nl[2]} ({TF_LABEL[nl[1]]}) · {nl[3]}</div>'

    candle_rows=""
    for c in d["recent_candles"]:
        cc="#00ff9d" if c["bull"] else "#ff3a5e"
        candle_rows+=f'<tr><td style="color:var(--muted);font-size:.6rem">{c["time"]}</td><td style="color:{cc};font-weight:700">${c["close"]:.2f}</td><td style="color:{cc}">{"▲" if c["bull"] else "▼"}</td><td style="color:var(--muted)">${c["high"]:.2f}</td><td style="color:var(--muted)">${c["low"]:.2f}</td><td style="color:var(--green-dim);font-size:.6rem">{c["volume"]//1000}K</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Research Notes — NVDA</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#070b12;--surface:#0d1520;--surface2:#111d2e;--border:#1e3a5f;
  --green:#00ff9d;--green-dim:#00c87a;--red:#ff3a5e;--red-dim:#cc1f40;
  --yellow:#ffd700;--orange:#ff8c42;--blue:#4fc3f7;--white:#e8f4ff;--muted:#5a7a99;--text:#c8ddf0;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;
  background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(0,80,160,.12) 0%,transparent 70%),
  repeating-linear-gradient(0deg,transparent,transparent 39px,rgba(30,58,95,.1) 39px,rgba(30,58,95,.1) 40px),
  repeating-linear-gradient(90deg,transparent,transparent 39px,rgba(30,58,95,.06) 39px,rgba(30,58,95,.06) 40px);}}
.hdr{{border-bottom:1px solid var(--border);padding:10px 20px;display:flex;align-items:center;
  justify-content:space-between;background:rgba(13,21,32,.97);backdrop-filter:blur(10px);
  position:sticky;top:0;z-index:100;flex-wrap:wrap;gap:8px;}}
.main{{max-width:1260px;margin:0 auto;padding:14px 16px;display:grid;gap:11px;}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px;}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:11px;}}
.card{{background:var(--surface);border:1px solid var(--border);padding:13px;}}
.ct{{font-size:.58rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:9px;
  padding-bottom:7px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:5px;}}
.ct::before{{content:'';width:4px;height:4px;background:var(--blue);display:block;border-radius:50%;}}
.vb{{padding:14px 18px;border:1px solid var(--border);border-left:4px solid {v["color"]};
  background:linear-gradient(135deg,#0a1929,#0d2035);display:grid;grid-template-columns:1fr auto;gap:16px;}}
table{{width:100%;border-collapse:collapse;}}
th,td{{padding:5px;font-size:.66rem;border-bottom:1px solid rgba(30,58,95,.35);}}
th{{color:var(--muted);font-size:.58rem;letter-spacing:1px;text-align:left;}}
tr:last-child td{{border-bottom:none;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.dot{{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:4px;animation:pulse 1.5s infinite;}}
@media(max-width:900px){{.g3,.g2{{grid-template-columns:1fr;}}}}
</style>
</head>
<body>
<header class="hdr">
  <div style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap">
    <span style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;color:var(--white);letter-spacing:2px">NVDA</span>
    <span style="font-size:1.3rem;color:{chg_c};font-weight:700">${price:.2f}</span>
    <span style="font-size:.8rem;color:{chg_c}">{arrow} {chg:+.2f} ({chg_p:+.2f}%)</span>
    <span style="font-size:.58rem;color:var(--muted)">H:{d["id_high"]} · L:{d["id_low"]} · ATR:${d["atr"]}</span>
  </div>
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    <span style="font-size:.65rem;color:{bctx['scen_color']};font-weight:700">{bctx['scen_label']}</span>
    <span style="font-size:.6rem;color:{session['color']}"><span class="dot" style="background:{session['color']}"></span>{session['emoji']} {session['name']}</span>
    <span style="color:{spy_c};font-size:.6rem">SPY {spy_l}</span>
    <span style="background:var(--surface2);border:1px solid var(--border);padding:4px 10px;font-size:.62rem;color:var(--muted)">{date_str} · {time_str}</span>
  </div>
</header>

<div class="main">

<!-- ON-LEVEL ALERT (shows when price within $3 of a starred Brando level) -->
{on_level_banner}

<!-- SESSION TIMELINE -->
<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:5px">{tl}</div>

<!-- VERDICT -->
<div class="vb">
  <div>
    <div style="font-size:.56rem;color:var(--muted);letter-spacing:1px;margin-bottom:3px">INSTITUTIONAL VERDICT · {time_str}</div>
    <div style="font-family:'Syne',sans-serif;font-size:1.25rem;font-weight:800;color:{v['color']}">{v['verdict']}</div>
    <div style="font-size:.67rem;color:var(--text);margin-top:5px;line-height:1.55">{v['explanation']}</div>
    <div style="margin-top:8px;padding:9px;background:rgba(255,255,255,.03);border-left:3px solid {v['color']};font-size:.67rem;color:var(--white);line-height:1.6">{v['trade_idea']}</div>
  </div>
  <div style="min-width:150px;text-align:center">
    <div style="border:1px solid {v['bias_color']};color:{v['bias_color']};padding:7px 12px;font-size:.7rem;letter-spacing:1px;margin-bottom:8px">{v['bias']}</div>
    <div style="font-size:.58rem;color:var(--muted)">Call {al['call_score']}/7</div>
    <div style="height:5px;background:rgba(255,255,255,.05);border-radius:3px;margin:3px 0 7px">
      <div style="height:100%;width:{round(al['call_score']/7*100)}%;background:#00ff9d;border-radius:3px"></div></div>
    <div style="font-size:.58rem;color:var(--muted)">Put {al['put_score']}/7</div>
    <div style="height:5px;background:rgba(255,255,255,.05);border-radius:3px;margin:3px 0 7px">
      <div style="height:100%;width:{round(al['put_score']/7*100)}%;background:#ff3a5e;border-radius:3px"></div></div>
    <div style="font-size:.55rem;color:var(--muted)">IV <strong style="color:var(--orange)">{opts['iv_30']}%</strong> · DTE <strong style="color:var(--white)">{opts['dte']}</strong></div>
    <div style="font-size:.55rem;color:var(--muted)">Exp move <strong style="color:var(--blue)">±${opts['exp_move']}</strong></div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════
     BRANDO / ELITE OPTIONS LEVEL MAP + SCENARIO ENGINE
     ═══════════════════════════════════════════════════ -->
<div class="g2">

  <!-- BRANDO LEVEL TABLE -->
  <div class="card">
    <div class="ct">Brando · Elite Options S/R Map (Monthly + Weekly + Daily)</div>
    <div style="font-size:.6rem;color:var(--muted);margin-bottom:8px">
      Source: @EliteOptions2 TrendSpider · 
      <span style="color:{TF_COLOR['MO']}">■ Monthly</span> &nbsp;
      <span style="color:{TF_COLOR['WK']}">■ Weekly</span> &nbsp;
      <span style="color:{TF_COLOR['DY']}">■ Daily</span> &nbsp;
      <span style="color:#ffd700">★ = Key starred level</span>
    </div>
    <table>
      <tr><th>TF</th><th>LEVEL</th><th>LABEL</th><th style="text-align:right">DIST</th></tr>
      {brando_table()}
    </table>
  </div>

  <!-- SCENARIO ENGINE -->
  <div class="card">
    <div class="ct">Scenario Engine — Two-Path Trade Plan</div>
    <div style="background:{bctx['scen_color']}15;border:1px solid {bctx['scen_color']};padding:10px;margin-bottom:11px">
      <div style="font-size:.62rem;color:var(--muted);margin-bottom:3px">CURRENT POSITION</div>
      <div style="font-size:.85rem;font-weight:700;color:{bctx['scen_color']}">{bctx['scen_label']}</div>
      <div style="font-size:.6rem;color:var(--muted);margin-top:4px">
        Next KEY resistance: <strong style="color:#ff3a5e">${bctx['key_res'][0]:.2f} {bctx['key_res'][2]}</strong> (+${round(bctx['key_res'][0]-price,2)}) &nbsp;|&nbsp;
        Next KEY support: <strong style="color:#00ff9d">${bctx['key_sup'][0]:.2f} {bctx['key_sup'][2]}</strong> (−${round(price-bctx['key_sup'][0],2)})
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:9px">
      <div style="background:rgba(0,255,157,.06);border:1px solid rgba(0,255,157,.3);padding:10px">
        <div style="font-size:.58rem;color:#00ff9d;letter-spacing:1px;margin-bottom:5px;font-weight:700">SCENARIO A — BULL</div>
        <div style="font-size:.66rem;color:var(--text);line-height:1.6">{bctx['scen_a']}</div>
      </div>
      <div style="background:rgba(255,58,94,.06);border:1px solid rgba(255,58,94,.3);padding:10px">
        <div style="font-size:.58rem;color:#ff3a5e;letter-spacing:1px;margin-bottom:5px;font-weight:700">SCENARIO B — BEAR</div>
        <div style="font-size:.66rem;color:var(--text);line-height:1.6">{bctx['scen_b']}</div>
      </div>
    </div>
    <div style="margin-top:9px;background:var(--surface2);border:1px solid var(--border);padding:9px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:5px">BRANDO'S KEY GATES (must watch)</div>
      <div style="font-size:.65rem;line-height:1.8">
        {"✅" if price>=191 else "❌"} <strong style="color:#ffd700">$191.00</strong> — Yellow line (MO+WK) · Clears = target $200 wall<br>
        {"✅" if price>=184.58 else "❌"} <strong style="color:#4fc3f7">$184.58</strong> — Daily key resistance · 200MA cluster zone<br>
        {"✅" if price>=180.34 else "❌"} <strong style="color:#ff8c42">$180.34</strong> — Critical daily pivot · MOST WATCHED LEVEL<br>
        {"✅" if price>=175.00 else "❌"} <strong style="color:#7c4dff">$175.00</strong> — Weekly purple support · Last bull defense<br>
        {"✅" if price>=153.37 else "❌"} <strong style="color:#b39ddb">$153.37</strong> — Monthly demand zone top · Institutional buy zone
      </div>
    </div>
  </div>
</div>

<!-- ROW: MTF ALIGNMENT + REGIME + COMPRESSION + CANDLES -->
<div class="g3">

  <!-- MTF ALIGNMENT -->
  <div class="card">
    <div class="ct">Multi-Timeframe Alignment</div>
    <table>
      <tr><th>TF</th><th>TREND</th><th>RSI</th><th>MACD HIST</th><th>BIAS</th><th>VOL</th></tr>
      {mtf_rows}
    </table>
    <div style="margin-top:8px;padding:7px;background:rgba(255,255,255,.03);border:1px solid var(--border);font-size:.62rem">
      <span style="color:var(--muted)">TF AGREEMENT: </span>
      <span style="color:{"#00ff9d" if al['bull_count']==3 else ("#ff3a5e" if al['bear_count']==3 else "#ffd700")};font-weight:700">
      {"🟢 ALL BULL — Max conviction" if al['bull_count']==3 else ("🔴 ALL BEAR — Max conviction" if al['bear_count']==3 else f"⚠️ MIXED ({al['bull_count']} bull / {al['bear_count']} bear)")}
      </span>
    </div>
    <div style="margin-top:7px;font-size:.6rem;color:var(--muted);line-height:1.5">
      RSI RULE: 4H in <strong style="color:var(--white)">45–55</strong> = ideal pullback zone → entry.<br>
      NOT 30/70. NVDA trends. Overbought stays overbought.
    </div>
  </div>

  <!-- REGIME + COMPRESSION -->
  <div class="card">
    <div class="ct">Market Regime · ATR · Compression</div>
    <div style="background:rgba(0,0,0,.2);border:1px solid {spy_c};padding:9px;margin-bottom:9px">
      <div style="font-size:.58rem;color:var(--muted);margin-bottom:3px">SPY MACRO REGIME</div>
      <div style="font-size:.8rem;font-weight:700;color:{spy_c}">SPY {spy_l} · ${d['spy_price']} vs 50 EMA ${d['spy_e50']}</div>
      <div style="font-size:.6rem;color:var(--muted);margin-top:2px">{"✅ Macro tailwind — call bias OK" if d['spy_bull'] else "❌ Macro headwind — reduce longs, prefer puts"}</div>
    </div>
    <div style="margin-bottom:9px">
      <div style="display:flex;justify-content:space-between;margin-bottom:3px">
        <span style="font-size:.62rem">ATR Compression Score</span>
        <span style="font-size:.62rem;font-weight:700;color:{comp_c}">{comp}/100</span>
      </div>
      <div style="height:5px;background:rgba(255,255,255,.05);border-radius:3px"><div style="height:100%;width:{comp}%;background:{comp_c};border-radius:3px"></div></div>
      <div style="font-size:.58rem;color:var(--muted);margin-top:2px">{"HIGH — Breakout imminent" if comp>70 else ("BUILDING" if comp>40 else "Normal range")}</div>
    </div>
    <div style="margin-bottom:9px">
      <div style="display:flex;justify-content:space-between;margin-bottom:3px">
        <span style="font-size:.62rem">Daily ATR (14)</span>
        <span style="font-size:.62rem;color:var(--orange);font-weight:700">${d['atr']:.2f}</span>
      </div>
      <div style="font-size:.58rem;color:var(--muted)">Expected 1-day move. Exp options move: <strong style="color:var(--blue)">±${opts['exp_move']}</strong></div>
    </div>
    <div>
      <div style="display:flex;justify-content:space-between;margin-bottom:3px">
        <span style="font-size:.62rem">Volume vs 20-bar avg</span>
        <span style="font-size:.62rem;font-weight:700;color:{vol_c}">{d['vol_ratio']}x · {vol_m:.0f}M / {avg_m:.0f}M</span>
      </div>
      <div style="height:5px;background:rgba(255,255,255,.05);border-radius:3px"><div style="height:100%;width:{min(d['vol_ratio']*50,100):.0f}%;background:{vol_c};border-radius:3px"></div></div>
      <div style="font-size:.58rem;color:var(--muted);margin-top:2px">{"✅ 1.5x+ = high conviction entry" if d['vol_ratio']>=1.5 else ("OK" if d['vol_ratio']>=1.0 else "❌ Low — likely chop")}</div>
    </div>
  </div>

  <!-- 5-MIN CANDLES + RANGE -->
  <div class="card">
    <div class="ct">Recent 5-Min Candles (Chicago time)</div>
    <table>
      <tr><th>TIME</th><th>CLOSE</th><th></th><th>HIGH</th><th>LOW</th><th>VOL</th></tr>
      {candle_rows or "<tr><td colspan='6' style='color:var(--muted);padding:7px'>Market closed / no data</td></tr>"}
    </table>
    <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:9px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:5px">52W RANGE</div>
      <div style="display:flex;justify-content:space-between;font-size:.6rem;color:var(--muted);margin-bottom:3px">
        <span>${d['week52l']:.0f}</span><span style="color:var(--white)">${price:.2f} ({yr:.0f}th pct)</span><span>${d['week52h']:.0f}</span>
      </div>
      <div style="height:6px;background:rgba(255,255,255,.05);border-radius:3px"><div style="height:100%;width:{yr:.0f}%;background:var(--blue);border-radius:3px"></div></div>
    </div>
    <div style="margin-top:10px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:5px">1H EMA LEVELS (Pullback Entry)</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:.63rem">
        <div>EMA8:  <strong style="color:var(--blue)">${d['h1']['e8']  if d['h1'] else '—'}</strong></div>
        <div>EMA21: <strong style="color:var(--blue)">${d['h1']['e21'] if d['h1'] else '—'}</strong></div>
        <div>EMA50: <strong style="color:var(--blue)">${d['h1']['e50'] if d['h1'] else '—'}</strong></div>
        <div>4H RSI: <strong style="color:{"#00ff9d" if d['h4'] and 45<=d['h4']['rsi']<=55 else "#ffd700"}">{d['h4']['rsi'] if d['h4'] else '—'} {"✅ setup" if d['h4'] and 45<=d['h4']['rsi']<=55 else "⏳"}</strong></div>
        <div>1H RSI: <strong style="color:{"#00ff9d" if d['h1'] and d['h1']['rsi_cross_above_50'] else ("#4fc3f7" if d['h1'] and d['h1']['rsi_above_50'] else "#ff3a5e")}">{d['h1']['rsi'] if d['h1'] else '—'} {"🔥 CROSS ↑" if d['h1'] and d['h1']['rsi_cross_above_50'] else ("🔥 CROSS ↓" if d['h1'] and d['h1']['rsi_cross_below_50'] else ("↑" if d['h1'] and d['h1']['rsi_above_50'] else "↓"))}</strong></div>
      </div>
      <div style="margin-top:7px;border-top:1px solid var(--border);padding-top:6px">
        <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:4px">RSI DIVERGENCE (eemani123 · period 5)</div>
        <div style="font-size:.63rem;margin-bottom:3px">
          1H: <strong style="color:{d['div_1h']['color']}">{d['div_1h']['label']}</strong>
        </div>
        <div style="font-size:.6rem;color:var(--muted);line-height:1.4">{d['div_1h']['desc']}</div>
        <div style="font-size:.63rem;margin-top:4px;margin-bottom:3px">
          4H: <strong style="color:{d['div_4h']['color']}">{d['div_4h']['label']}</strong>
        </div>
        <div style="font-size:.6rem;color:var(--muted);line-height:1.4">{d['div_4h']['desc']}</div>
      </div>
    </div>
  </div>
</div>

<!-- SIGNAL BREAKDOWN + OPTIONS -->
<div class="g3">
  <div class="card">
    <div class="ct">Call Signal ({al['call_score']}/9)</div>
    {reason_list(al['call_reasons'], al['call_score'], 9)}
    <div style="margin-top:10px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:5px">CALL R:R CALCULATOR</div>
      {rr_box(al['call_rr'],"call")}
    </div>
  </div>
  <div class="card">
    <div class="ct">Put Signal ({al['put_score']}/9)</div>
    {reason_list(al['put_reasons'], al['put_score'], 9)}
    <div style="margin-top:10px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:5px">PUT R:R CALCULATOR</div>
      {rr_box(al['put_rr'],"put")}
    </div>
  </div>
  <div class="card">
    <div class="ct">Options Chain — {opts['expiry']} ({opts['dte']} DTE)</div>
    <div style="font-size:.58rem;color:var(--muted);margin-bottom:5px">🎯 ~$5 target ($3.50–$6.50) · Δ delta · θ theta · Spread color</div>
    <div style="font-size:.58rem;color:var(--orange);letter-spacing:1px;margin-bottom:3px">── CALLS ──</div>
    <table>
      <tr><th>STRIKE</th><th>PRICE</th><th>Δ</th><th>θ</th><th>IV</th><th>SPRD</th><th>VOL</th></tr>
      {chain_rows(opts['calls']) or "<tr><td colspan='7' style='color:var(--muted)'>Fetching...</td></tr>"}
    </table>
    <div style="font-size:.58rem;color:var(--red);letter-spacing:1px;margin:7px 0 3px">── PUTS ──</div>
    <table>
      <tr><th>STRIKE</th><th>PRICE</th><th>Δ</th><th>θ</th><th>IV</th><th>SPRD</th><th>VOL</th></tr>
      {chain_rows(opts['puts']) or "<tr><td colspan='7' style='color:var(--muted)'>Fetching...</td></tr>"}
    </table>
    <div style="margin-top:7px;padding:7px;background:rgba(255,215,0,.05);border:1px solid rgba(255,215,0,.2);font-size:.6rem;color:var(--yellow);line-height:1.5">
      Verify: finance.yahoo.com/quote/NVDA/options · Vol&gt;500 · OI&gt;1K · Spread&lt;$0.20
    </div>
  </div>
</div>

<!-- ENTRY MODEL + NEWS -->
<div class="g2">
  <div class="card">
    <div class="ct">Entry &amp; Exit Model — Brando + Two-Layer RSI + Divergence</div>
    <div style="font-size:.66rem;line-height:1.8;color:var(--text)">
      <div style="color:var(--green);font-weight:700;margin-bottom:4px">✅ CALL ENTRY CHECKLIST:</div>
      1. Daily + 4H above cloud · HH/HL intact · Above Brando $180.34<br>
      2. 4H RSI cools to <strong style="color:var(--white)">45–55</strong> — setup valid, premium discounted<br>
      3. 1H RSI <strong style="color:var(--white)">crosses above 50</strong> — entry trigger fires<br>
      4. Bonus: <strong style="color:#00ff9d">Regular Bull Div</strong> (seller exhaustion) or <strong style="color:#4fc3f7">Hidden Bull Div</strong> (continuation) on 1H/4H<br>
      5. 1H MACD histogram turns positive · Volume ≥ 1.5x<br>
      6. Enter on break of prior 1H high · Stop under pullback low
    </div>
    <div style="margin-top:8px;font-size:.66rem;line-height:1.8;color:var(--text)">
      <div style="color:var(--red);font-weight:700;margin-bottom:4px">🔴 PUT ENTRY CHECKLIST:</div>
      1. Daily below cloud · HH/HL broken · Below Brando $180.34<br>
      2. 4H RSI bounces to <strong style="color:var(--white)">45–55</strong> on retest OR oversold (&lt;40)<br>
      3. 1H RSI <strong style="color:var(--white)">crosses below 50</strong> — entry trigger fires<br>
      4. Bonus: <strong style="color:#ff3a5e">Regular Bear Div</strong> (buyer exhaustion) or <strong style="color:#ff8c42">Hidden Bear Div</strong> (dead cat) on 1H/4H<br>
      5. 1H MACD negative · High volume on down bars<br>
      6. Enter on break of prior 1H low · Stop above bounce high
    </div>
    <div style="margin-top:8px;padding:8px;background:rgba(0,255,157,.05);border:1px solid rgba(0,255,157,.2);font-size:.63rem;color:var(--green);line-height:1.7">
      🟢 <strong>DIVERGENCE EXIT RULES (eemani123):</strong><br>
      In CALLS → <strong>Regular Bear Div</strong> appears = SELL ALL immediately (buyer exhaustion at top)<br>
      In CALLS → <strong>1H RSI(5) hits 75+</strong> = profit target reached, SELL ALL<br>
      In PUTS → <strong>Regular Bull Div</strong> appears = COVER immediately (seller exhaustion at bottom)<br>
      In PUTS → <strong>Hidden Bull Div</strong> = tighten stop to entry, ready to flip
    </div>
    <div style="margin-top:8px;padding:8px;background:rgba(255,140,66,.07);border:1px solid rgba(255,140,66,.3);font-size:.65rem;color:var(--orange);line-height:1.6">
      🚪 <strong>HARD EXITS:</strong> +80% → SELL ALL · −50% → HARD STOP · Day 3 → EXIT · IMACD flips → HALF OUT
    </div>
  </div>
  <div class="card">
    <div class="ct">NVDA News — Live</div>
    {news_html or '<div style="font-size:.68rem;color:var(--muted);padding:8px">No articles fetched.</div>'}
  </div>
</div>

<div style="text-align:center;padding:10px;font-size:.56rem;color:var(--muted);border-top:1px solid var(--border);line-height:1.9;margin-top:2px">
  🤖 Auto-updated 24× daily · Chicago time · Data: Yahoo Finance · S/R: @EliteOptions2 TrendSpider · RSI Div: eemani123 · Page reloads every 5 min<br>
  ⚠️ Educational only — not financial advice. Verify all prices before trading.<br>
  Last update: <strong style="color:var(--text)">{ct_now.strftime("%Y-%m-%d %H:%M:%S CT")}</strong>
</div>
</div>
</body></html>"""


# ─────────────────────────────────────────────
# 4. MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    ct_now  = datetime.datetime.now(CT)
    session = get_session(ct_now)
    print(f"⏰ {ct_now.strftime('%I:%M %p CT')} — {session['name']}")

    print("📡 Fetching NVDA + SPY (daily/4H/1H/5m)...")
    d = fetch_all()
    print(f"   ${d['price']} | {d['change_pct']:+.2f}% | Vol {d['vol_ratio']}x | ATR ${d['atr']} | Compression {d['compression']}/100")
    print(f"   SPY {'BULL' if d['spy_bull'] else 'BEAR'} | Daily RSI {d['daily']['rsi']} | MACD {d['daily']['macd_h']:+.3f}")
    if d["h4"]: print(f"   4H RSI {d['h4']['rsi']} {'✅ pullback zone' if 40<=d['h4']['rsi']<=60 else ''} | MACD {d['h4']['macd_h']:+.3f}")
    if d["h1"]: print(f"   1H EMA8 ${d['h1']['e8']} | MACD {d['h1']['macd_h']:+.3f}")

    print(f"   1H Div: {d['div_1h']['label']} | 4H Div: {d['div_4h']['label']}")

    print("🗺️  Building Brando level context...")
    bctx = get_brando_context(d["price"])
    print(f"   {bctx['scen_label']} | On level: {bctx['on_level']}")
    print(f"   Next key res: ${bctx['key_res'][0] if bctx['key_res'] else '—'} | Next key sup: ${bctx['key_sup'][0] if bctx['key_sup'] else '—'}")

    print("📋 Fetching options chain...")
    opts = fetch_options(d["price"])
    print(f"   {opts['expiry']} | {opts['dte']} DTE | IV {opts['iv_30']}% | Exp move ±${opts['exp_move']}")

    print("📰 Fetching news...")
    news = fetch_news()
    print(f"   {len(news)} articles")

    print("🧠 Building signals...")
    al = build_alignment(d, opts, session, bctx)
    print(f"   Call {al['call_score']}/9 | Put {al['put_score']}/9 | TF: {al['bull_count']} bull / {al['bear_count']} bear")

    verdict = get_verdict(al, d, session, opts, bctx)
    print(f"   {verdict['verdict']}")

    print("🖥️  Rendering HTML...")
    html = render(d, opts, news, al, verdict, session, bctx, ct_now)
    Path("index.html").write_text(html, encoding="utf-8")
    print(f"✅ Done — {len(html):,} bytes")
