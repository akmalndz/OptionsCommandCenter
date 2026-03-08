"""
NVDA Options Command Center v6 — PROVEN SYSTEM Edition
Rebuilt signal engine from backtested Pine Script research:
  - Signal 1: Ichimoku Cloud (15min equiv) — Profit Factor 4.18
  - Signal 2: Kaufman Adaptive MA (45min equiv) — Profit Factor 4.34
  - Signal 3: RSI Strategy (1H) — Win Rate 77%, Profit Factor 2.15
  - Signal 4 (optional): MACD + RSI Combo (45min) — Win Rate 68%
  - Brando S/R levels, sessions, scenarios PRESERVED
  - Quality entries: 2/3 = good, 3/3 = max conviction
  - Position scaling: 2/3=$500, 3/3=$750, 4/4=$1000
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
    res = sorted([(p,tf,l,n,k) for (p,tf,l,n,k) in BRANDO if p > price],  key=lambda x: x[0])
    sup = sorted([(p,tf,l,n,k) for (p,tf,l,n,k) in BRANDO if p <= price], key=lambda x: x[0], reverse=True)
    nearest  = min(BRANDO, key=lambda x: abs(x[0]-price))
    on_level = abs(nearest[0]-price) <= 3.0 and nearest[4]
    key_res  = next((l for l in res if l[4]), res[0]  if res else None)
    key_sup  = next((l for l in sup if l[4]), sup[0]  if sup else None)

    if price >= 200.00:
        scen_label = "🚀 ABOVE $200 WALL";    scen_color = "#00ff9d"
        scen_a = "Hold calls. Target $212 (ATH zone) then $225. Trail stop to $196."
        scen_b = "Rejection at $200-$212 → take profit on calls. Watch for reversal."
    elif price >= 191.00:
        scen_label = "🔥 ABOVE YELLOW LINE";  scen_color = "#00ff9d"
        scen_a = "Bullish. Next wall: $200.08. Buy pullbacks to $191 on 1H."
        scen_b = "Loses $191 → drops back to $184.58. Calls become risky."
    elif price >= 184.58:
        scen_label = "📈 BETWEEN $184 AND $191"; scen_color = "#ffd700"
        scen_a = "Break + close above $184.58 with vol → call target $191 yellow line."
        scen_b = "Rejection at $184.58 → pullback to $180.34. Reassess."
    elif price >= 180.34:
        scen_label = "⚠️ ON $180.34 — DECISION"; scen_color = "#ff8c42"
        scen_a = "CALL: Holds $180.34, reclaims $184.58 → April $190C or $195C. Target $191."
        scen_b = "PUT: Breaks $180.34 on volume → April $175P. Target $175 weekly support."
    elif price >= 175.00:
        scen_label = "🔴 BELOW $180 — BEARISH"; scen_color = "#ff3a5e"
        scen_a = "PUT active. Target $175 weekly purple line. Stop above $180.34."
        scen_b = "Bounce to $180.34 and fails (lower high) → add to puts."
    elif price >= 153.37:
        scen_label = "🔴 APPROACHING DEMAND"; scen_color = "#ff3a5e"
        scen_a = "Puts still valid targeting $153-$141 monthly demand zone."
        scen_b = "Watch for volume reversal candle AT $153.37 — potential call entry."
    else:
        scen_label = "🆘 INSIDE MONTHLY DEMAND"; scen_color = "#ffd700"
        scen_a = "Monthly demand zone $141-$153 — institutional buyers expected here."
        scen_b = "Watch for weekly reversal candle before entering calls. High risk zone."

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

def donchian(series, period):
    """Ichimoku-style donchian channel midline"""
    return (series.rolling(period).min() + series.rolling(period).max()) / 2


# ─────────────────────────────────────────────
# SIGNAL 1: ICHIMOKU CLOUD — PF 4.18 (15min equiv)
# Tenkan/Kijun cross + price above/below cloud
# ─────────────────────────────────────────────
def calc_ichimoku(hist):
    """Calculate Ichimoku on given timeframe data. Returns signal dict."""
    if len(hist) < 60:
        return {"bull": False, "bear": False, "label": "N/A", "detail": "Insufficient data",
                "tenkan": None, "kijun": None, "spanA": None, "spanB": None, "cloud_bull": None}

    c = hist["Close"]
    h = hist["High"]
    l = hist["Low"]

    # Tenkan (9), Kijun (26), Senkou B (52)
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun  = (h.rolling(26).max() + l.rolling(26).min()) / 2
    spanA  = (tenkan + kijun) / 2
    spanB  = (h.rolling(52).max() + l.rolling(52).min()) / 2

    tenkan_now = float(tenkan.iloc[-1])
    kijun_now  = float(kijun.iloc[-1])
    spanA_now  = float(spanA.iloc[-1])
    spanB_now  = float(spanB.iloc[-1])
    price_now  = float(c.iloc[-1])

    cloud_top    = max(spanA_now, spanB_now)
    cloud_bottom = min(spanA_now, spanB_now)
    cloud_bull   = spanA_now > spanB_now

    above_cloud = price_now > cloud_top
    below_cloud = price_now < cloud_bottom
    tk_bull     = tenkan_now > kijun_now
    tk_bear     = tenkan_now < kijun_now

    bull = above_cloud and tk_bull
    bear = below_cloud and tk_bear

    if bull:
        label = "✅ BULLISH"
        detail = f"Price ${price_now:.2f} above cloud (${cloud_top:.2f}) · T>K ({tenkan_now:.2f}>{kijun_now:.2f})"
    elif bear:
        label = "✅ BEARISH"
        detail = f"Price ${price_now:.2f} below cloud (${cloud_bottom:.2f}) · T<K ({tenkan_now:.2f}<{kijun_now:.2f})"
    elif above_cloud:
        label = "⚠️ WEAK BULL"
        detail = f"Above cloud but T≤K — momentum slowing"
    elif below_cloud:
        label = "⚠️ WEAK BEAR"
        detail = f"Below cloud but T≥K — bears not full control"
    else:
        label = "⏸ IN CLOUD"
        detail = f"Price inside cloud (${cloud_bottom:.2f}–${cloud_top:.2f}) — no clear signal"

    return {
        "bull": bull, "bear": bear, "label": label, "detail": detail,
        "tenkan": round(tenkan_now, 2), "kijun": round(kijun_now, 2),
        "spanA": round(spanA_now, 2), "spanB": round(spanB_now, 2),
        "cloud_bull": cloud_bull, "cloud_top": round(cloud_top, 2), "cloud_bottom": round(cloud_bottom, 2),
    }


# ─────────────────────────────────────────────
# SIGNAL 2: KAUFMAN ADAPTIVE MA (KAMA) — PF 4.34 (45min equiv)
# Direction of KAMA + price vs KAMA
# ─────────────────────────────────────────────
def calc_kama(hist, length=10, fast_sc=2, slow_sc=30):
    """Calculate Kaufman Adaptive Moving Average on HLC3."""
    if len(hist) < length + 10:
        return {"bull": False, "bear": False, "label": "N/A", "detail": "Insufficient data",
                "kama_val": None, "er": None, "direction": None}

    hlc3 = (hist["High"] + hist["Low"] + hist["Close"]) / 3

    # Efficiency Ratio
    change = abs(hlc3 - hlc3.shift(length))
    volatility = abs(hlc3 - hlc3.shift(1)).rolling(length).sum()
    er = (change / volatility.replace(0, np.nan)).fillna(0)

    # Smoothing constant
    fast_c = 2.0 / (fast_sc + 1)
    slow_c = 2.0 / (slow_sc + 1)
    sc = (er * (fast_c - slow_c) + slow_c) ** 2

    # KAMA calculation (iterative — can't vectorize cleanly)
    kama_vals = np.zeros(len(hlc3))
    hlc3_arr  = hlc3.values
    sc_arr    = sc.values

    kama_vals[0] = hlc3_arr[0]
    for i in range(1, len(hlc3_arr)):
        if np.isnan(sc_arr[i]) or np.isnan(hlc3_arr[i]):
            kama_vals[i] = kama_vals[i-1]
        else:
            kama_vals[i] = kama_vals[i-1] + sc_arr[i] * (hlc3_arr[i] - kama_vals[i-1])

    kama_now  = kama_vals[-1]
    kama_prev = kama_vals[-2]
    price_now = float(hist["Close"].iloc[-1])
    hlc3_now  = float(hlc3.iloc[-1])
    er_now    = float(er.iloc[-1])
    kama_rising  = kama_now > kama_prev
    kama_falling = kama_now < kama_prev

    bull = hlc3_now > kama_now and kama_rising
    bear = hlc3_now < kama_now and kama_falling

    direction = "RISING" if kama_rising else ("FALLING" if kama_falling else "FLAT")
    dir_color = "#00ff9d" if kama_rising else ("#ff3a5e" if kama_falling else "#ffd700")

    if bull:
        label = "✅ BULLISH"
        detail = f"HLC3 ${hlc3_now:.2f} > KAMA ${kama_now:.2f} · KAMA rising · ER {er_now:.2f}"
    elif bear:
        label = "✅ BEARISH"
        detail = f"HLC3 ${hlc3_now:.2f} < KAMA ${kama_now:.2f} · KAMA falling · ER {er_now:.2f}"
    elif hlc3_now > kama_now:
        label = "⚠️ WEAK BULL"
        detail = f"Above KAMA but KAMA not rising — momentum stalling"
    elif hlc3_now < kama_now:
        label = "⚠️ WEAK BEAR"
        detail = f"Below KAMA but KAMA not falling — bears weak"
    else:
        label = "⏸ NEUTRAL"
        detail = f"On KAMA — no clear direction"

    return {
        "bull": bull, "bear": bear, "label": label, "detail": detail,
        "kama_val": round(kama_now, 2), "er": round(er_now, 3),
        "direction": direction, "dir_color": dir_color,
    }


# ─────────────────────────────────────────────
# SIGNAL 3: RSI STRATEGY (1H) — WR 77%, PF 2.15
# Cross above 45 / bounce from oversold = bull
# Cross below 55 / rejection from overbought = bear
# ─────────────────────────────────────────────
def calc_rsi_signal(hist, period=14, bull_level=45, bear_level=55, oversold=30, overbought=70):
    """RSI signal matching Pine Script logic for 77% win rate."""
    if len(hist) < period + 5:
        return {"bull": False, "bear": False, "label": "N/A", "detail": "Insufficient data",
                "rsi_val": None, "rsi_prev": None, "cross_type": None}

    rsi_series = rsi(hist["Close"], period)
    rsi_now  = float(rsi_series.iloc[-1])
    rsi_prev = float(rsi_series.iloc[-2])

    # Bull: cross above 45 OR bounce from oversold
    cross_above_45 = rsi_prev < bull_level and rsi_now >= bull_level
    oversold_bounce = rsi_now < oversold and (rsi_now > rsi_prev)
    bull = cross_above_45 or oversold_bounce

    # Bear: cross below 55 OR rejection from overbought
    cross_below_55 = rsi_prev > bear_level and rsi_now <= bear_level
    overbought_reject = rsi_now > overbought and (rsi_now < rsi_prev)
    bear = cross_below_55 or overbought_reject

    cross_type = None
    if cross_above_45:     cross_type = "CROSS ↑ 45"
    elif oversold_bounce:  cross_type = "OVERSOLD BOUNCE"
    elif cross_below_55:   cross_type = "CROSS ↓ 55"
    elif overbought_reject: cross_type = "OVERBOUGHT REJECT"

    if bull:
        label = "✅ BULLISH"
        detail = f"RSI {rsi_prev:.1f}→{rsi_now:.1f} · {cross_type} — 77% WR entry"
    elif bear:
        label = "✅ BEARISH"
        detail = f"RSI {rsi_prev:.1f}→{rsi_now:.1f} · {cross_type} — 77% WR entry"
    else:
        zone = "OVERBOUGHT" if rsi_now > overbought else ("OVERSOLD" if rsi_now < oversold else "MID-RANGE")
        label = f"⏸ {zone}"
        detail = f"RSI {rsi_now:.1f} — no trigger yet. Wait for cross at 45 (bull) or 55 (bear)"

    return {
        "bull": bull, "bear": bear, "label": label, "detail": detail,
        "rsi_val": round(rsi_now, 1), "rsi_prev": round(rsi_prev, 1),
        "cross_type": cross_type,
    }


# ─────────────────────────────────────────────
# SIGNAL 4 (OPTIONAL): MACD + RSI COMBO — WR 68%
# MACD hist cross 0 + RSI in 40-65 (bull) or 35-60 (bear)
# ─────────────────────────────────────────────
def calc_macd_rsi_combo(hist, period=14):
    """MACD + RSI combo signal from Pine Script."""
    if len(hist) < 30:
        return {"bull": False, "bear": False, "label": "N/A", "detail": "Insufficient data",
                "macd_h": None, "rsi_val": None}

    c = hist["Close"]
    mh = macd_histogram(c)
    rsi_series = rsi(c, period)

    mh_now  = float(mh.iloc[-1])
    mh_prev = float(mh.iloc[-2])
    rsi_now = float(rsi_series.iloc[-1])

    macd_cross_bull = mh_prev < 0 and mh_now >= 0
    macd_cross_bear = mh_prev > 0 and mh_now <= 0

    bull = macd_cross_bull and 40 < rsi_now < 65
    bear = macd_cross_bear and 35 < rsi_now < 60

    if bull:
        label = "✅ BULLISH"
        detail = f"MACD hist crossed ↑ zero ({mh_prev:.3f}→{mh_now:.3f}) · RSI {rsi_now:.1f} in range"
    elif bear:
        label = "✅ BEARISH"
        detail = f"MACD hist crossed ↓ zero ({mh_prev:.3f}→{mh_now:.3f}) · RSI {rsi_now:.1f} in range"
    else:
        label = "⏸ NO SIGNAL"
        detail = f"MACD hist {mh_now:+.3f} · RSI {rsi_now:.1f} — waiting for cross + RSI confirmation"

    return {
        "bull": bull, "bear": bear, "label": label, "detail": detail,
        "macd_h": round(mh_now, 3), "rsi_val": round(rsi_now, 1),
    }


# ─────────────────────────────────────────────
# RSI DIVERGENCE DETECTOR (eemani123 style)
# Kept from v5 as bonus context
# ─────────────────────────────────────────────
def detect_rsi_divergence(hist, rsi_period=5, lookback=3):
    c = hist["Close"]
    if len(c) < rsi_period + lookback + 5:
        return _div_none()

    rsi_series = rsi(c, rsi_period)
    prices     = c.values
    rsi_vals   = rsi_series.values

    n          = len(prices)
    curr_price = prices[-1]
    prev_price = prices[-(lookback+1)]
    curr_rsi   = rsi_vals[-1]
    prev_rsi   = rsi_vals[-(lookback+1)]

    price_up  = curr_price > prev_price
    price_dn  = curr_price < prev_price
    rsi_up    = curr_rsi   > prev_rsi
    rsi_dn    = curr_rsi   < prev_rsi

    rsi_spread = abs(curr_rsi - prev_rsi)
    if rsi_spread >= 8:   strength = "strong"
    elif rsi_spread >= 4: strength = "moderate"
    else:                  strength = "weak"

    if price_dn and rsi_up and curr_rsi < 50:
        return {"divergence_type": "regular_bull",
                "label": f"📈 REGULAR BULL DIV ({strength.upper()})",
                "detail": f"Price ↓ ${prev_price:.2f}→${curr_price:.2f} · RSI ↑ {prev_rsi:.1f}→{curr_rsi:.1f}",
                "strength": strength, "color": "#00ff9d",
                "confirms_bull": True, "confirms_bear": False,
                "exit_warning_bull": False, "exit_warning_bear": True}

    if price_up and rsi_dn and curr_rsi < 55:
        return {"divergence_type": "hidden_bull",
                "label": f"🔷 HIDDEN BULL DIV ({strength.upper()})",
                "detail": f"Price ↑ ${prev_price:.2f}→${curr_price:.2f} · RSI ↓ {prev_rsi:.1f}→{curr_rsi:.1f}",
                "strength": strength, "color": "#4fc3f7",
                "confirms_bull": True, "confirms_bear": False,
                "exit_warning_bull": False, "exit_warning_bear": True}

    if price_up and rsi_dn and curr_rsi > 50:
        return {"divergence_type": "regular_bear",
                "label": f"📉 REGULAR BEAR DIV ({strength.upper()})",
                "detail": f"Price ↑ ${prev_price:.2f}→${curr_price:.2f} · RSI ↓ {prev_rsi:.1f}→{curr_rsi:.1f}",
                "strength": strength, "color": "#ff3a5e",
                "confirms_bull": False, "confirms_bear": True,
                "exit_warning_bull": True, "exit_warning_bear": False}

    if price_dn and rsi_up and curr_rsi > 45:
        return {"divergence_type": "hidden_bear",
                "label": f"🔻 HIDDEN BEAR DIV ({strength.upper()})",
                "detail": f"Price ↓ ${prev_price:.2f}→${curr_price:.2f} · RSI ↑ {prev_rsi:.1f}→{curr_rsi:.1f}",
                "strength": strength, "color": "#ff8c42",
                "confirms_bull": False, "confirms_bear": True,
                "exit_warning_bull": True, "exit_warning_bear": False}

    return _div_none()

def _div_none():
    return {"divergence_type": None, "label": "No divergence detected",
            "detail": "", "strength": None, "color": "#5a7a99",
            "confirms_bull": False, "confirms_bear": False,
            "exit_warning_bull": False, "exit_warning_bear": False}


# ─────────────────────────────────────────────
# LEGACY MTF HELPERS (for bias table display)
# ─────────────────────────────────────────────
def tf_ind(h, label, price):
    """Compute per-timeframe indicators for MTF bias table display."""
    c = h["Close"]
    e8    = round(float(ema(c,8).iloc[-1]),  2)
    e21   = round(float(ema(c,21).iloc[-1]), 2)
    e50   = round(float(ema(c,50).iloc[-1]), 2)
    r     = round(float(rsi(c).iloc[-1]),    1)
    mh    = macd_histogram(c)
    mh_n  = round(float(mh.iloc[-1]), 3)
    mh_p  = round(float(mh.iloc[-2]), 3)
    vol_n  = int(h["Volume"].iloc[-1])
    vol_ma = float(h["Volume"].rolling(20).mean().iloc[-1]) or 1
    vr     = round(vol_n/vol_ma, 2)
    hh_hl  = higher_highs_lows(h)
    return {
        "label": label, "e8": e8, "e21": e21, "e50": e50,
        "rsi": r, "macd_h": mh_n, "macd_h_prev": mh_p,
        "vol_ratio": vr, "hh_hl": hh_hl,
        "above_cloud":   price > max(e21, e50),
        "below_cloud":   price < min(e21, e50),
        "fast_bull":     e8 > e21,
        "macd_bull":     mh_n > 0,
        "macd_turning":      mh_n > 0 and mh_p < 0,
        "macd_turning_bear": mh_n < 0 and mh_p > 0,
        "rsi_expansion_bull": r > 60,
        "rsi_expansion_bear": r < 40,
        "vol_expanded": vr >= 1.5,
    }


# ─────────────────────────────────────────────
# 1. FETCH ALL DATA
# ─────────────────────────────────────────────
def fetch_all():
    nvda = yf.Ticker("NVDA")
    spy  = yf.Ticker("SPY")
    info = nvda.info

    d1    = nvda.history(period="1y",  interval="1d")
    h4    = nvda.history(period="60d", interval="4h")    # for KAMA (45min proxy)
    h1    = nvda.history(period="30d", interval="1h")    # for RSI + MACD+RSI
    m15   = nvda.history(period="5d",  interval="15m")   # for Ichimoku
    m5    = nvda.history(period="2d",  interval="5m")
    d1_3m = nvda.history(period="3mo", interval="1d")
    spy_d = spy.history(  period="6mo", interval="1d")

    price      = float(info.get("currentPrice") or info.get("regularMarketPrice") or d1["Close"].iloc[-1])
    prev_close = float(info.get("previousClose") or d1["Close"].iloc[-2])
    volume     = int(info.get("regularMarketVolume") or d1["Volume"].iloc[-1])
    avg_vol    = int(info.get("averageVolume")        or d1["Volume"].mean())
    week52h    = float(info.get("fiftyTwoWeekHigh")   or d1["High"].max())
    week52l    = float(info.get("fiftyTwoWeekLow")    or d1["Low"].min())

    spy_e50   = float(ema(spy_d["Close"], 50).iloc[-1])
    spy_price = float(spy_d["Close"].iloc[-1])
    spy_bull  = spy_price > spy_e50

    comp    = compression_score(d1_3m) if len(d1_3m) >= 50 else 0
    atr_val = round(float(atr(d1).iloc[-1]), 2)
    vol20ma = float(d1["Volume"].rolling(20).mean().iloc[-1])

    # ── PROVEN SIGNALS ────────────────────────────────────────────────────
    sig_ichimoku   = calc_ichimoku(m15)          # Signal 1: Ichimoku (15min) PF 4.18
    sig_kama       = calc_kama(h4)               # Signal 2: KAMA (4H as 45min proxy) PF 4.34
    sig_rsi        = calc_rsi_signal(h1)         # Signal 3: RSI (1H) 77% WR
    sig_macd_combo = calc_macd_rsi_combo(h1)     # Signal 4: MACD+RSI combo 68% WR
    h1_div         = detect_rsi_divergence(h1, rsi_period=5, lookback=3) if len(h1) >= 20 else _div_none()

    # Legacy MTF display data
    daily_tf = tf_ind(d1, "DAILY", price) if len(d1) >= 50 else None
    h4_tf    = tf_ind(h4, "4-HOUR", price) if len(h4) >= 50 else None
    h1_tf    = tf_ind(h1, "1-HOUR", price) if len(h1) >= 50 else None

    recent_candles = []
    if len(m5) >= 4:
        for idx, row in m5.tail(8).iterrows():
            try:    ts = idx.tz_convert(CT).strftime("%I:%M %p")
            except: ts = str(idx)[-8:-3]
            co, cc = float(row["Open"]), float(row["Close"])
            recent_candles.append({
                "time": ts, "open": round(co,2), "high": round(float(row["High"]),2),
                "low":  round(float(row["Low"]),2), "close": round(cc,2),
                "volume": int(row["Volume"]), "bull": cc >= co,
            })

    id_high = round(float(m5["High"].max()),2) if len(m5) else price
    id_low  = round(float(m5["Low"].min()),2)  if len(m5) else price

    return {
        "price": price, "prev_close": round(prev_close,2),
        "change":     round(price - prev_close, 2),
        "change_pct": round((price - prev_close) / prev_close * 100, 2),
        "volume": volume, "avg_vol": avg_vol,
        "vol_ratio": round(volume / avg_vol, 2) if avg_vol else 1.0,
        "vol_20ma":  round(vol20ma / 1e6, 1),
        "week52h": week52h, "week52l": week52l,
        "atr": atr_val, "compression": comp,
        # Proven signals
        "sig_ichimoku": sig_ichimoku,
        "sig_kama": sig_kama,
        "sig_rsi": sig_rsi,
        "sig_macd_combo": sig_macd_combo,
        "h1_div": h1_div,
        # Legacy MTF display
        "daily": daily_tf, "h4": h4_tf, "h1": h1_tf,
        "spy_bull": spy_bull, "spy_price": round(spy_price,2), "spy_e50": round(spy_e50,2),
        "recent_candles": recent_candles, "id_high": id_high, "id_low": id_low,
        "d1": d1, "d1_3m": d1_3m,
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
        if abs(s-price) <= 25:
            calls_raw.append({
                "strike": s,
                "price":  round(float(r.get("lastPrice",0) or r.get("ask",0) or 0), 2),
                "bid":    round(float(r.get("bid",0) or 0), 2),
                "ask":    round(float(r.get("ask",0) or 0), 2),
                "delta":  round(float(r.get("delta",0) or 0), 2),
                "theta":  round(float(r.get("theta",0) or 0), 3),
                "iv":     round(float(r.get("impliedVolatility",0.5) or 0.5)*100, 1),
                "volume": int(r.get("volume",0) or 0),
                "oi":     int(r.get("openInterest",0) or 0),
            })
    for _, r in chain.puts.iterrows():
        s = float(r["strike"])
        if abs(s-price) <= 20 and s <= price+5:
            puts_raw.append({
                "strike": s,
                "price":  round(float(r.get("lastPrice",0) or r.get("ask",0) or 0), 2),
                "bid":    round(float(r.get("bid",0) or 0), 2),
                "ask":    round(float(r.get("ask",0) or 0), 2),
                "delta":  round(float(r.get("delta",0) or 0), 2),
                "theta":  round(float(r.get("theta",0) or 0), 3),
                "iv":     round(float(r.get("impliedVolatility",0.5) or 0.5)*100, 1),
                "volume": int(r.get("volume",0) or 0),
                "oi":     int(r.get("openInterest",0) or 0),
            })

    atm_c = [c for c in calls_raw if abs(c["strike"]-price) < 5]
    if atm_c: iv_atm = atm_c[0]["iv"] / 100

    calls_raw.sort(key=lambda x: x["strike"])
    puts_raw.sort(key=lambda x: x["strike"], reverse=True)
    exp_move = round(price * iv_atm * math.sqrt(dte/365), 2)

    return {"expiry": chosen, "calls": calls_raw[:7], "puts": puts_raw[:4],
            "iv_30": round(iv_atm*100,1), "dte": dte, "exp_move": exp_move}


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
# 2. PROVEN SIGNAL AGGREGATION
# 3 core signals (need 2+ to enter) + optional 4th
# Brando $180.34 pivot as directional bias filter
# Volume + session as context filters (not gates)
# ─────────────────────────────────────────────
USE_4TH_SIGNAL = True  # MACD+RSI combo

def build_signals(d, opts, session, bctx):
    price = d["price"]
    sig1 = d["sig_ichimoku"]
    sig2 = d["sig_kama"]
    sig3 = d["sig_rsi"]
    sig4 = d["sig_macd_combo"]
    h1_div = d["h1_div"]
    max_signals = 4 if USE_4TH_SIGNAL else 3

    # ── CALL SIGNALS ──────────────────────────────────────────────────────
    call_count = 0; call_reasons = []

    # S1: Ichimoku (PF 4.18)
    if sig1["bull"]:
        call_count += 1
        call_reasons.append(f'✅ S1 ICHIMOKU (PF 4.18): {sig1["detail"]}')
    else:
        call_reasons.append(f'❌ S1 ICHIMOKU: {sig1["detail"]}')

    # S2: Kaufman KAMA (PF 4.34)
    if sig2["bull"]:
        call_count += 1
        call_reasons.append(f'✅ S2 KAUFMAN (PF 4.34): {sig2["detail"]}')
    else:
        call_reasons.append(f'❌ S2 KAUFMAN: {sig2["detail"]}')

    # S3: RSI (77% WR)
    if sig3["bull"]:
        call_count += 1
        call_reasons.append(f'✅ S3 RSI 77%WR: {sig3["detail"]}')
    else:
        call_reasons.append(f'❌ S3 RSI: {sig3["detail"]}')

    # S4: MACD+RSI Combo (68% WR) — optional
    if USE_4TH_SIGNAL:
        if sig4["bull"]:
            call_count += 1
            call_reasons.append(f'✅ S4 MACD+RSI (68%WR): {sig4["detail"]}')
        else:
            call_reasons.append(f'❌ S4 MACD+RSI: {sig4["detail"]}')

    # ── CONTEXT FILTERS (inform, don't block) ──
    call_context = []

    # Brando bias
    if price >= 180.34:
        call_context.append(f"✅ BIAS: Above Brando $180.34 — call bias confirmed")
    else:
        call_context.append(f"⚠️ BIAS: Below Brando $180.34 (${price:.2f}) — calls against Brando bias")

    # SPY macro
    if d["spy_bull"]:
        call_context.append(f"✅ MACRO: SPY above 50 EMA — tailwind")
    else:
        call_context.append(f"⚠️ MACRO: SPY below 50 EMA — headwind for calls")

    # Volume context
    price_up = d["change"] >= 0
    if price_up and d["vol_ratio"] >= 1.5:
        call_context.append(f"✅ VOL: {d['vol_ratio']}x on up day — institutional accumulation")
    elif not price_up and d["vol_ratio"] < 1.0:
        call_context.append(f"✅ VOL: Low-volume pullback ({d['vol_ratio']}x) — healthy dip")
    elif not price_up and d["vol_ratio"] >= 1.5:
        call_context.append(f"❌ VOL: High-volume selling ({d['vol_ratio']}x) — distribution, calls risky")
    else:
        call_context.append(f"⚠️ VOL: {d['vol_ratio']}x — neutral")

    # Session context
    if session["trade"]:
        sess_name = session["name"]
        if "POWER" in sess_name:
            call_context.append(f"✅ SESSION: Power Window — highest conviction")
        else:
            call_context.append(f"✅ SESSION: {sess_name} — tradeable")
    else:
        call_context.append(f"⚠️ SESSION: {session['name']} — wait for tradeable window")

    # Divergence context
    if h1_div["confirms_bull"]:
        call_context.append(f"✅ DIV: {h1_div['label']} — confirms call entry")
    elif h1_div["exit_warning_bull"]:
        call_context.append(f"🚨 DIV: {h1_div['label']} — EXIT WARNING for calls")
    elif h1_div["divergence_type"]:
        call_context.append(f"ℹ️ DIV: {h1_div['label']} — neutral")

    # ── PUT SIGNALS ───────────────────────────────────────────────────────
    put_count = 0; put_reasons = []

    if sig1["bear"]:
        put_count += 1
        put_reasons.append(f'✅ S1 ICHIMOKU (PF 4.18): {sig1["detail"]}')
    else:
        put_reasons.append(f'❌ S1 ICHIMOKU: {sig1["detail"]}')

    if sig2["bear"]:
        put_count += 1
        put_reasons.append(f'✅ S2 KAUFMAN (PF 4.34): {sig2["detail"]}')
    else:
        put_reasons.append(f'❌ S2 KAUFMAN: {sig2["detail"]}')

    if sig3["bear"]:
        put_count += 1
        put_reasons.append(f'✅ S3 RSI 77%WR: {sig3["detail"]}')
    else:
        put_reasons.append(f'❌ S3 RSI: {sig3["detail"]}')

    if USE_4TH_SIGNAL:
        if sig4["bear"]:
            put_count += 1
            put_reasons.append(f'✅ S4 MACD+RSI (68%WR): {sig4["detail"]}')
        else:
            put_reasons.append(f'❌ S4 MACD+RSI: {sig4["detail"]}')

    # Put context filters
    put_context = []

    if price < 180.34:
        put_context.append(f"✅ BIAS: Below Brando $180.34 — put bias confirmed")
    else:
        put_context.append(f"⚠️ BIAS: Above Brando $180.34 — puts against Brando bias")

    if not d["spy_bull"]:
        put_context.append(f"✅ MACRO: SPY below 50 EMA — tailwind for puts")
    else:
        put_context.append(f"⚠️ MACRO: SPY above 50 EMA — headwind for puts")

    price_down = d["change"] < 0
    if price_down and d["vol_ratio"] >= 1.5:
        put_context.append(f"✅ VOL: High-volume selling ({d['vol_ratio']}x) — real distribution")
    elif price_down and d["vol_ratio"] < 1.0:
        put_context.append(f"❌ VOL: Low-volume decline ({d['vol_ratio']}x) — dead cat, AVOID puts")
    elif not price_down and d["vol_ratio"] >= 1.5:
        put_context.append(f"❌ VOL: High volume on up day ({d['vol_ratio']}x) — buyers active")
    else:
        put_context.append(f"⚠️ VOL: {d['vol_ratio']}x — neutral")

    if session["trade"]:
        sess_name = session["name"]
        if "POWER" in sess_name:
            put_context.append(f"✅ SESSION: Power Window — highest conviction")
        else:
            put_context.append(f"✅ SESSION: {sess_name} — tradeable")
    else:
        put_context.append(f"⚠️ SESSION: {session['name']} — wait for tradeable window")

    if h1_div["confirms_bear"]:
        put_context.append(f"✅ DIV: {h1_div['label']} — confirms put entry")
    elif h1_div["exit_warning_bear"]:
        put_context.append(f"🚨 DIV: {h1_div['label']} — EXIT WARNING for puts")
    elif h1_div["divergence_type"]:
        put_context.append(f"ℹ️ DIV: {h1_div['label']} — neutral")

    # ── R:R CALC ──────────────────────────────────────────────────────────
    call_t = next((c for c in opts["calls"] if 3.50<=c["price"]<=6.50), None)
    put_t  = next((p for p in opts["puts"]  if 3.50<=p["price"]<=6.50), None)

    def rr_calc(opt, sig_count):
        if not opt: return None
        entry     = opt["price"]
        # Asymmetric R:R from Pine research: 60% TP, 35% SL
        stop      = round(entry * (1 - 0.35), 2)
        target    = round(entry * (1 + 0.60), 2)
        risk      = round(entry - stop, 2)
        reward    = round(target - entry, 2)
        rr        = round(reward / risk, 1) if risk else 0
        # Position scaling: 2/3=$500, 3/3=$750, 4/4=$1000
        if sig_count >= 4:   budget = 1000
        elif sig_count >= 3: budget = 750
        else:                budget = 500
        contracts = max(1, int(budget / (entry * 100)))
        max_loss  = round(contracts * entry * 100 * 0.35, 0)
        return {"entry":entry,"stop":stop,"target":target,"risk":risk,"reward":reward,
                "rr":rr,"contracts":contracts,"max_risk":int(max_loss),"budget":budget}

    # MTF bias rows for display
    mtf_rows = []
    for label, tfd in [("DAILY", d["daily"]), ("4-HOUR", d["h4"]), ("1-HOUR", d["h1"])]:
        if tfd:
            mtf_rows.append(tfd)

    return {
        "call_count": call_count, "put_count": put_count,
        "max_signals": max_signals,
        "call_reasons": call_reasons, "put_reasons": put_reasons,
        "call_context": call_context, "put_context": put_context,
        "call_t": call_t, "put_t": put_t,
        "call_rr": rr_calc(call_t, call_count),
        "put_rr":  rr_calc(put_t, put_count),
        "mtf_rows": mtf_rows,
        "h1_div": h1_div,
    }


def get_verdict(al, d, session, opts, bctx):
    cs = al["call_count"]; ps = al["put_count"]; price = d["price"]
    max_s = al["max_signals"]
    div = al["h1_div"]

    if not session["trade"]:
        return {"verdict":f"💤 {session['name']} — NO NEW TRADES",
                "color":"#ff3a5e","bias":"WAIT","bias_color":"#ff8c42",
                "explanation":session["advice"],
                "trade_idea":"Hold existing if profitable. Next window: Power Window 1:00 PM CT."}

    # Position sizing label
    def size_label(count):
        if count >= 4: return "$1,000"
        elif count >= 3: return "$750"
        else: return "$500"

    if cs >= 3:
        ct=al["call_t"]; rr=al["call_rr"]
        div_note = f" · {div['label']}" if div["confirms_bull"] else ""
        conviction = "MAX" if cs >= 4 else "HIGH"
        return {"verdict":f"✅ CALL — {conviction} CONFIDENCE ({cs}/{max_s})","color":"#00ff9d",
                "bias":"STRONG BULL","bias_color":"#00ff9d",
                "explanation":f"3+ proven signals aligned. Ichimoku + KAMA + RSI confirming. Size: {size_label(cs)}. Target: ${bctx['key_res'][0] if bctx['key_res'] else '—'}.{div_note}",
                "trade_idea":f"Buy ${ct['strike']:.0f}C {opts['expiry']} (~${ct['price']:.2f}) | Stop ${rr['stop']} (−35%) | Target ${rr['target']} (+60%) | R:R {rr['rr']}:1 | {rr['contracts']} contracts" if ct and rr else "Check chain for $3-6 ATM call."}
    elif cs == 2:
        ct=al["call_t"]; rr=al["call_rr"]
        return {"verdict":f"🟢 CALL — GOOD SETUP ({cs}/{max_s})","color":"#00c87a",
                "bias":"BULLISH","bias_color":"#00ff9d",
                "explanation":f"2/{max_s} proven signals active. Size: $500. Check context filters for confirmation before entry.",
                "trade_idea":f"Buy ${ct['strike']:.0f}C {opts['expiry']} (~${ct['price']:.2f}) | Stop ${rr['stop']} | Target ${rr['target']} | R:R {rr['rr']}:1" if ct and rr else "Check chain."}
    elif ps >= 3:
        pt=al["put_t"]; rr=al["put_rr"]
        div_note = f" · {div['label']}" if div["confirms_bear"] else ""
        conviction = "MAX" if ps >= 4 else "HIGH"
        return {"verdict":f"🔴 PUT — {conviction} CONFIDENCE ({ps}/{max_s})","color":"#ff3a5e",
                "bias":"STRONG BEAR","bias_color":"#ff3a5e",
                "explanation":f"3+ proven signals aligned bearish. Size: {size_label(ps)}. Target: ${bctx['key_sup'][0] if bctx['key_sup'] else '—'}.{div_note}",
                "trade_idea":f"Buy ${pt['strike']:.0f}P {opts['expiry']} (~${pt['price']:.2f}) | Stop ${rr['stop']} (−35%) | Target ${rr['target']} (+60%) | R:R {rr['rr']}:1 | {rr['contracts']} contracts" if pt and rr else "Check chain for $3-6 OTM put."}
    elif ps == 2:
        pt=al["put_t"]; rr=al["put_rr"]
        return {"verdict":f"🟠 PUT — GOOD SETUP ({ps}/{max_s})","color":"#ff8c42",
                "bias":"BEARISH","bias_color":"#ff3a5e",
                "explanation":f"2/{max_s} proven signals active bearish. Check context: volume must confirm (no dead cat).",
                "trade_idea":f"Buy ${pt['strike']:.0f}P {opts['expiry']} (~${pt['price']:.2f}) | Stop ${rr['stop']} | Target ${rr['target']} | R:R {rr['rr']}:1" if pt and rr else "Watch for breakdown."}
    elif cs == 1 and ps == 1:
        return {"verdict":"⏸ MIXED — NO TRADE","color":"#ff8c42","bias":"NEUTRAL","bias_color":"#ffd700",
                "explanation":f"Signals conflicting (1 bull / 1 bear). {bctx['scen_label']} — wait for alignment.",
                "trade_idea":f"Scenario A: {bctx['scen_a']}  |  Scenario B: {bctx['scen_b']}"}
    elif cs == 1:
        return {"verdict":f"⏸ CALL WATCH — Not Yet ({cs}/{max_s})","color":"#ffd700",
                "bias":"DEVELOPING","bias_color":"#ffd700",
                "explanation":f"Only 1 signal active. Need 2+ for entry. Waiting for KAMA direction or RSI cross.",
                "trade_idea":f"Scenario A: {bctx['scen_a']}  |  Scenario B: {bctx['scen_b']}"}
    elif ps == 1:
        return {"verdict":f"⏸ PUT WATCH — Not Yet ({ps}/{max_s})","color":"#ffd700",
                "bias":"DEVELOPING","bias_color":"#ffd700",
                "explanation":f"Only 1 bear signal. Need 2+ for entry. Watch for Ichimoku cloud break or KAMA turning.",
                "trade_idea":f"Scenario A: {bctx['scen_a']}  |  Scenario B: {bctx['scen_b']}"}
    else:
        return {"verdict":"⏸ NO SIGNAL — FLAT","color":"#5a7a99","bias":"FLAT","bias_color":"#5a7a99",
                "explanation":f"0 proven signals active. Market likely ranging. {bctx['scen_label']}.",
                "trade_idea":"Wait. Quality over quantity. The system is working — no signal IS a signal."}


# ─────────────────────────────────────────────
# 3. RENDER HTML
# ─────────────────────────────────────────────
def render(d, opts, news, al, verdict, session, bctx, ct_now):
    price=d["price"]; chg=d["change"]; chg_p=d["change_pct"]
    chg_c="#00ff9d" if chg>=0 else "#ff3a5e"
    arrow="▲" if chg>=0 else "▼"
    vol_m=d["volume"]/1e6; avg_m=d["avg_vol"]/1e6
    vol_c ="#00ff9d" if d["vol_ratio"]>1.2 else ("#ffd700" if d["vol_ratio"]>0.8 else "#ff3a5e")
    iv_c  ="#00ff9d" if opts["iv_30"]<35 else ("#ffd700" if opts["iv_30"]<55 else "#ff3a5e")
    yr    =min(100,(price-d["week52l"])/(d["week52h"]-d["week52l"])*100) if d["week52h"]!=d["week52l"] else 50
    v     =verdict
    spy_c ="#00ff9d" if d["spy_bull"] else "#ff3a5e"
    spy_l ="BULL ✓" if d["spy_bull"] else "BEAR ✗"
    date_str=ct_now.strftime("%a %b %d, %Y")
    time_str=ct_now.strftime("%I:%M %p CT")
    comp=d["compression"]
    comp_c="#00ff9d" if comp>70 else ("#ffd700" if comp>40 else "#5a7a99")
    h1_div=al["h1_div"]
    max_s = al["max_signals"]

    sig1 = d["sig_ichimoku"]
    sig2 = d["sig_kama"]
    sig3 = d["sig_rsi"]
    sig4 = d["sig_macd_combo"]

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
    mtf_html=""
    for tfd in [d["daily"], d["h4"], d["h1"]]:
        if not tfd: continue
        label = tfd["label"]
        if tfd["above_cloud"] and tfd["hh_hl"]: trend,tc="BULLISH","#00ff9d"
        elif tfd["below_cloud"]:                  trend,tc="BEARISH","#ff3a5e"
        else:                                      trend,tc="NEUTRAL","#ffd700"
        if tfd["rsi_expansion_bull"]:   rl,rc=f'{tfd["rsi"]} ↑',"#00ff9d"
        elif tfd["rsi_expansion_bear"]: rl,rc=f'{tfd["rsi"]} ↓',"#ff3a5e"
        else:                            rl,rc=f'{tfd["rsi"]} ~',"#ffd700"
        if tfd["macd_turning"]:         ml,mc="TURNING ↑","#00ff9d"
        elif tfd["macd_bull"]:          ml,mc="EXPANDING","#00c87a"
        elif tfd["macd_turning_bear"]:  ml,mc="TURNING ↓","#ff3a5e"
        else:                            ml,mc="NEGATIVE","#ff3a5e"
        score = sum([tfd["above_cloud"],tfd["fast_bull"],tfd["macd_bull"],tfd["hh_hl"],tfd["rsi_expansion_bull"]])
        if score>=4:   bias,bc="LONG","#00ff9d"
        elif score<=1: bias,bc="SHORT","#ff3a5e"
        else:           bias,bc="WATCH","#ffd700"
        ve=f'<span style="color:#00ff9d;font-size:.6rem">▲{tfd["vol_ratio"]}x</span>' if tfd["vol_expanded"] else f'<span style="color:{"#ffd700" if tfd["vol_ratio"]>=1.0 else "#ff3a5e"};font-size:.6rem">{tfd["vol_ratio"]}x</span>'
        mtf_html+=f'<tr><td style="color:var(--white);font-weight:700">{label}</td><td style="color:{tc};font-weight:700">{trend}</td><td style="color:{rc}">{rl}</td><td style="color:{mc}">{ml}</td><td style="color:{bc};font-weight:700">{bias}</td><td>{ve}</td></tr>'

    # Signal reason + context builder
    def signal_panel(reasons, context, count, max_s, direction):
        html = '<div style="font-size:.55rem;color:var(--muted);letter-spacing:1px;margin-bottom:6px">PROVEN SIGNALS</div>'
        for r in reasons:
            if r.startswith("✅"):    col="#00ff9d"
            elif r.startswith("❌"):  col="#ff3a5e"
            else:                      col="#ffd700"
            html+=f'<div style="font-size:.63rem;color:{col};padding:4px 0;border-bottom:1px solid rgba(30,58,95,.3)">{r}</div>'
        # Score bar
        pct = round(count / max_s * 100)
        bc = "#00ff9d" if direction == "call" else "#ff3a5e"
        html+=f'<div style="margin-top:8px"><div style="font-size:.58rem;color:var(--muted);margin-bottom:3px">SIGNAL STRENGTH: {count}/{max_s} ({pct}%)</div><div style="height:6px;background:rgba(255,255,255,.05);border-radius:3px"><div style="height:100%;width:{pct}%;background:{bc};border-radius:3px"></div></div></div>'
        # Context
        html += '<div style="font-size:.55rem;color:var(--muted);letter-spacing:1px;margin:10px 0 4px">CONTEXT FILTERS</div>'
        for c in context:
            if c.startswith("✅"):    col="#00ff9d"
            elif c.startswith("❌"):  col="#ff3a5e"
            elif c.startswith("🚨"):  col="#ff3a5e"
            elif c.startswith("⚠️"): col="#ffd700"
            elif c.startswith("ℹ️"): col="#4fc3f7"
            else:                      col="#5a7a99"
            html+=f'<div style="font-size:.6rem;color:{col};padding:2px 0">{c}</div>'
        return html

    # R:R box
    def rr_box(rr, direction):
        if not rr: return '<div style="font-size:.65rem;color:var(--muted);padding:10px">No $3-6 option near ATM</div>'
        bc="#00ff9d" if direction=="call" else "#ff3a5e"
        rc="#00ff9d" if rr["rr"]>=2 else ("#ffd700" if rr["rr"]>=1.5 else "#ff3a5e")
        return f'''<div style="background:var(--surface2);border:1px solid {bc};padding:10px">
          <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:6px;text-align:center">
            <div><div style="font-size:.52rem;color:var(--muted)">ENTRY</div><div style="font-size:.85rem;color:var(--white);font-weight:700">${rr["entry"]:.2f}</div></div>
            <div><div style="font-size:.52rem;color:var(--muted)">R:R</div><div style="font-size:.85rem;font-weight:700;color:{rc}">{rr["rr"]}:1</div></div>
            <div><div style="font-size:.52rem;color:var(--muted)">STOP −35%</div><div style="font-size:.85rem;color:var(--red);font-weight:700">${rr["stop"]:.2f}</div></div>
            <div><div style="font-size:.52rem;color:var(--muted)">TARGET +60%</div><div style="font-size:.85rem;color:var(--green);font-weight:700">${rr["target"]:.2f}</div></div>
          </div>
          <div style="margin-top:6px;border-top:1px solid rgba(255,255,255,.06);padding-top:6px;font-size:.58rem">
            <span>Budget: <strong style="color:var(--white)">${rr["budget"]}</strong></span> ·
            <span>Contracts: <strong style="color:var(--white)">{rr["contracts"]}</strong></span> ·
            <span>Max loss: <strong style="color:var(--red)">${rr["max_risk"]}</strong></span>
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

    # Brando level table
    def brando_table():
        res5 = bctx["res"][:5]
        sup5 = bctx["sup"][:5]
        rows=""
        for (p,tf,lbl,note,key) in res5:
            dist=round(p-price,2)
            key_marker="★ " if key else ""
            tf_c=TF_COLOR.get(tf,"#aaa")
            bg='background:rgba(255,215,0,.05);' if key else ""
            rows+=f'<tr style="{bg}"><td style="color:{tf_c};font-size:.58rem">{TF_LABEL[tf]}</td><td style="color:{"#ffd700" if key else "#ff3a5e"};font-weight:700">${p:.2f}</td><td style="color:var(--muted);font-size:.6rem">{key_marker}{lbl}</td><td style="color:var(--muted);font-size:.58rem;text-align:right">+${dist:.2f}</td></tr>'
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
        on_level_banner=f'<div style="background:rgba(255,215,0,.1);border:1px solid #ffd700;padding:9px 14px;font-size:.68rem;color:#ffd700;font-weight:700;text-align:center;margin-bottom:0;word-break:break-word">⚡ ON BRANDO LEVEL: ${nl[0]:.2f} — {nl[2]} ({TF_LABEL[nl[1]]})</div>'

    candle_rows=""
    for c in d["recent_candles"]:
        cc="#00ff9d" if c["bull"] else "#ff3a5e"
        candle_rows+=f'<tr><td style="color:var(--muted);font-size:.6rem">{c["time"]}</td><td style="color:{cc};font-weight:700">${c["close"]:.2f}</td><td style="color:{cc}">{"▲" if c["bull"] else "▼"}</td><td style="color:var(--muted)">${c["high"]:.2f}</td><td style="color:var(--muted)">${c["low"]:.2f}</td><td style="color:var(--green-dim);font-size:.6rem">{c["volume"]//1000}K</td></tr>'

    # Signal indicator cards
    def sig_card(sig_name, sig_data, pf_label, tf_label, icon, color_accent):
        is_bull = sig_data.get("bull", False)
        is_bear = sig_data.get("bear", False)
        status_color = "#00ff9d" if is_bull else ("#ff3a5e" if is_bear else "#5a7a99")
        border = f"1px solid {status_color}40"
        bg = f"rgba({int(status_color[1:3],16)},{int(status_color[3:5],16)},{int(status_color[5:7],16)},.05)"
        # Extra details per signal type
        extra = ""
        if "tenkan" in sig_data and sig_data["tenkan"]:
            cloud_color = "#00ff9d" if sig_data["cloud_bull"] else "#ff3a5e"
            extra = f'''<div style="font-size:.52rem;color:var(--muted);margin-top:5px;padding-top:5px;border-top:1px solid rgba(255,255,255,.06);word-break:break-word">
              T:${sig_data["tenkan"]} K:${sig_data["kijun"]} Cloud:<span style="color:{cloud_color}">${sig_data["cloud_bottom"]}–${sig_data["cloud_top"]}</span>
            </div>'''
        elif "kama_val" in sig_data and sig_data["kama_val"]:
            extra = f'''<div style="font-size:.52rem;color:var(--muted);margin-top:5px;padding-top:5px;border-top:1px solid rgba(255,255,255,.06);word-break:break-word">
              KAMA:${sig_data["kama_val"]} ER:{sig_data["er"]} <span style="color:{sig_data["dir_color"]}">{sig_data["direction"]}</span>
            </div>'''
        elif "rsi_val" in sig_data and sig_data["rsi_val"] and "cross_type" in sig_data:
            extra = f'''<div style="font-size:.52rem;color:var(--muted);margin-top:5px;padding-top:5px;border-top:1px solid rgba(255,255,255,.06)">
              RSI:{sig_data["rsi_val"]} (prev {sig_data["rsi_prev"]}) {sig_data["cross_type"] or "—"}
            </div>'''
        elif "macd_h" in sig_data and sig_data["macd_h"] is not None and "rsi_val" in sig_data:
            extra = f'''<div style="font-size:.52rem;color:var(--muted);margin-top:5px;padding-top:5px;border-top:1px solid rgba(255,255,255,.06)">
              MACD:{sig_data["macd_h"]:+.3f} RSI:{sig_data["rsi_val"]}
            </div>'''

        return f'''<div style="background:{bg};border:{border};padding:9px;min-width:0;overflow:hidden">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;gap:4px">
            <div style="font-size:.53rem;color:var(--muted);letter-spacing:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{icon} {sig_name} · {tf_label}</div>
            <div style="font-size:.5rem;color:{color_accent};font-weight:700;background:rgba(255,255,255,.05);padding:2px 5px;white-space:nowrap;flex-shrink:0">{pf_label}</div>
          </div>
          <div style="font-size:.73rem;font-weight:700;color:{status_color}">{sig_data["label"]}</div>
          <div style="font-size:.57rem;color:var(--text);margin-top:3px;line-height:1.5;word-break:break-word">{sig_data["detail"]}</div>
          {extra}
        </div>'''

    # Divergence card
    div_color = h1_div["color"]
    div_bg = f"rgba({int(div_color[1:3],16)},{int(div_color[3:5],16)},{int(div_color[5:7],16)},.07)" if h1_div["divergence_type"] else "rgba(255,255,255,.02)"
    if h1_div["confirms_bull"] or h1_div["confirms_bear"]:
        div_action = f'<div style="font-size:.6rem;color:#ffd700;font-weight:700;margin-top:4px">⚡ CONFIRMS ENTRY — adds conviction</div>'
    elif h1_div["exit_warning_bull"] or h1_div["exit_warning_bear"]:
        div_action = f'<div style="font-size:.6rem;color:#ff3a5e;font-weight:700;margin-top:4px">🚨 EXIT WARNING — divergence opposes position</div>'
    else:
        div_action = '<div style="font-size:.6rem;color:var(--muted);margin-top:4px">No action required.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>NVDA Options Command Center v6 — PROVEN SYSTEM</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#070b12;--surface:#0d1520;--surface2:#111d2e;--border:#1e3a5f;
  --green:#00ff9d;--green-dim:#00c87a;--red:#ff3a5e;--red-dim:#cc1f40;
  --yellow:#ffd700;--orange:#ff8c42;--blue:#4fc3f7;--white:#e8f4ff;--muted:#5a7a99;--text:#c8ddf0;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
html{{overflow-x:hidden;}}
body{{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;
  overflow-x:hidden;max-width:100vw;
  background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(0,80,160,.12) 0%,transparent 70%),
  repeating-linear-gradient(0deg,transparent,transparent 39px,rgba(30,58,95,.1) 39px,rgba(30,58,95,.1) 40px),
  repeating-linear-gradient(90deg,transparent,transparent 39px,rgba(30,58,95,.06) 39px,rgba(30,58,95,.06) 40px);}}
.hdr{{border-bottom:1px solid var(--border);padding:10px 16px;display:flex;align-items:center;
  justify-content:space-between;background:rgba(13,21,32,.97);backdrop-filter:blur(10px);
  position:sticky;top:0;z-index:100;flex-wrap:wrap;gap:8px;}}
.main{{max-width:100%;width:100%;margin:0 auto;padding:12px 12px;display:grid;gap:10px;}}
.g4{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.g3{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.card{{background:var(--surface);border:1px solid var(--border);padding:11px;overflow:hidden;word-break:break-word;min-width:0;}}
.ct{{font-size:.58rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:9px;
  padding-bottom:7px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:5px;}}
.ct::before{{content:'';width:4px;height:4px;background:var(--blue);display:block;border-radius:50%;flex-shrink:0;}}
.vb{{padding:13px 16px;border:1px solid var(--border);border-left:4px solid {v["color"]};
  background:linear-gradient(135deg,#0a1929,#0d2035);display:grid;grid-template-columns:1fr 170px;gap:14px;align-items:center;}}
table{{width:100%;border-collapse:collapse;table-layout:fixed;}}
th,td{{padding:4px 3px;font-size:.62rem;border-bottom:1px solid rgba(30,58,95,.35);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
th{{color:var(--muted);font-size:.56rem;letter-spacing:1px;text-align:left;}}
tr:last-child td{{border-bottom:none;}}
.sess-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.dot{{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:4px;animation:pulse 1.5s infinite;}}
@media(max-width:1100px){{.g3{{grid-template-columns:1fr 1fr;}}}}
@media(max-width:900px){{.g4,.g3,.g2{{grid-template-columns:1fr;}} .vb{{grid-template-columns:1fr;}} .sess-grid{{grid-template-columns:repeat(3,1fr);}}}}
</style>
</head>
<body>
<header class="hdr">
  <div style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap">
    <span style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;color:var(--white);letter-spacing:2px">NVDA</span>
    <span style="font-size:1.3rem;color:{chg_c};font-weight:700">${price:.2f}</span>
    <span style="font-size:.8rem;color:{chg_c}">{arrow} {chg:+.2f} ({chg_p:+.2f}%)</span>
    <span style="font-size:.58rem;color:var(--muted)">H:{d["id_high"]} · L:{d["id_low"]} · ATR:${d["atr"]}</span>
    <span style="font-size:.54rem;background:rgba(79,195,247,.1);border:1px solid rgba(79,195,247,.3);color:#4fc3f7;padding:2px 8px;font-weight:700">v6 PROVEN SYSTEM</span>
  </div>
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    <span style="font-size:.65rem;color:{bctx['scen_color']};font-weight:700">{bctx['scen_label']}</span>
    <span style="font-size:.6rem;color:{session['color']}"><span class="dot" style="background:{session['color']}"></span>{session['emoji']} {session['name']}</span>
    <span style="color:{spy_c};font-size:.6rem">SPY {spy_l}</span>
    <span style="background:var(--surface2);border:1px solid var(--border);padding:4px 10px;font-size:.62rem;color:var(--muted)">{date_str} · {time_str}</span>
  </div>
</header>

<div class="main">

{on_level_banner}

<!-- SESSION TIMELINE -->
<div class="sess-grid">{tl}</div>

<!-- VERDICT -->
<div class="vb">
  <div>
    <div style="font-size:.56rem;color:var(--muted);letter-spacing:1px;margin-bottom:3px">PROVEN SYSTEM VERDICT · {time_str}</div>
    <div style="font-family:'Syne',sans-serif;font-size:1.25rem;font-weight:800;color:{v['color']}">{v['verdict']}</div>
    <div style="font-size:.67rem;color:var(--text);margin-top:5px;line-height:1.55">{v['explanation']}</div>
    <div style="margin-top:8px;padding:9px;background:rgba(255,255,255,.03);border-left:3px solid {v['color']};font-size:.67rem;color:var(--white);line-height:1.6">{v['trade_idea']}</div>
  </div>
  <div style="min-width:180px;text-align:center;display:flex;flex-direction:column;gap:7px;justify-content:center">
    <div style="border:1px solid {v['bias_color']};color:{v['bias_color']};padding:7px 12px;font-size:.7rem;letter-spacing:1px;font-weight:700">{v['bias']}</div>
    <div>
      <div style="display:flex;justify-content:space-between;font-size:.58rem;margin-bottom:3px">
        <span style="color:var(--muted)">CALL</span>
        <span style="color:#00ff9d;font-weight:700">{al['call_count']}/{max_s}</span>
      </div>
      <div style="height:6px;background:rgba(255,255,255,.05);border-radius:3px">
        <div style="height:100%;width:{round(al['call_count']/max_s*100)}%;background:linear-gradient(90deg,#00c87a,#00ff9d);border-radius:3px"></div>
      </div>
    </div>
    <div>
      <div style="display:flex;justify-content:space-between;font-size:.58rem;margin-bottom:3px">
        <span style="color:var(--muted)">PUT</span>
        <span style="color:#ff3a5e;font-weight:700">{al['put_count']}/{max_s}</span>
      </div>
      <div style="height:6px;background:rgba(255,255,255,.05);border-radius:3px">
        <div style="height:100%;width:{round(al['put_count']/max_s*100)}%;background:linear-gradient(90deg,#cc1f40,#ff3a5e);border-radius:3px"></div>
      </div>
    </div>
    <div style="border-top:1px solid var(--border);padding-top:6px;display:flex;flex-direction:column;gap:3px">
      <div style="font-size:.55rem;color:var(--muted)">IV <strong style="color:var(--orange)">{opts['iv_30']}%</strong> · DTE <strong style="color:var(--white)">{opts['dte']}</strong></div>
      <div style="font-size:.55rem;color:var(--muted)">Exp move <strong style="color:var(--blue)">±${opts['exp_move']}</strong></div>
      <div style="font-size:.52rem;color:var(--muted);margin-top:2px">2/4=$500 · 3/4=$750 · 4/4=$1000</div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════
     PROVEN SIGNAL CARDS (4 columns)
     ═══════════════════════════════════════════════════ -->
<div class="g4">
  {sig_card("S1 · ICHIMOKU", sig1, "PF 4.18", "15MIN", "☁️", "#b39ddb")}
  {sig_card("S2 · KAUFMAN", sig2, "PF 4.34", "4H", "📐", "#7c4dff")}
  {sig_card("S3 · RSI", sig3, "77% WR", "1H", "📊", "#4fc3f7")}
  {sig_card("S4 · MACD+RSI", sig4, "68% WR", "1H", "⚡", "#ff8c42")}
</div>

<!-- DIVERGENCE CONTEXT -->
<div class="card">
  <div class="ct">RSI Divergence Monitor — Bonus Context</div>
  <div style="background:{div_bg};border:1px solid {div_color}40;padding:10px;margin-bottom:8px">
    <div style="font-size:.78rem;font-weight:700;color:{div_color}">{h1_div['label']}</div>
    <div style="font-size:.58rem;color:var(--muted);margin-top:4px">{h1_div['detail'] or "No divergence on current 1H bars"}</div>
    {div_action}
  </div>
  <div style="font-size:.58rem;color:var(--muted);line-height:1.7;padding:4px">
    <span style="color:#00ff9d">Reg Bull:</span> Price LL + RSI HL → reversal &nbsp;·&nbsp;
    <span style="color:#4fc3f7">Hid Bull:</span> Price HL + RSI LL → continuation<br>
    <span style="color:#ff3a5e">Reg Bear:</span> Price HH + RSI LH → reversal &nbsp;·&nbsp;
    <span style="color:#ff8c42">Hid Bear:</span> Price LH + RSI HH → continuation
  </div>
</div>

<!-- BRANDO MAP + SCENARIO -->
<div class="g2">
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
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:5px">BRANDO'S KEY GATES</div>
      <div style="font-size:.65rem;line-height:1.8">
        {"✅" if price>=191 else "❌"} <strong style="color:#ffd700">$191.00</strong> — Yellow line (MO+WK)<br>
        {"✅" if price>=184.58 else "❌"} <strong style="color:#4fc3f7">$184.58</strong> — Daily key resistance<br>
        {"✅" if price>=180.34 else "❌"} <strong style="color:#ff8c42">$180.34</strong> — Critical daily pivot ★<br>
        {"✅" if price>=175.00 else "❌"} <strong style="color:#7c4dff">$175.00</strong> — Weekly purple support<br>
        {"✅" if price>=153.37 else "❌"} <strong style="color:#b39ddb">$153.37</strong> — Monthly demand zone top
      </div>
    </div>
  </div>
</div>

<!-- MTF + REGIME + CANDLES -->
<div class="g3">
  <div class="card">
    <div class="ct">Multi-Timeframe Bias Table</div>
    <table>
      <tr><th>TF</th><th>TREND</th><th>RSI</th><th>MACD HIST</th><th>BIAS</th><th>VOL</th></tr>
      {mtf_html}
    </table>
    <div style="margin-top:7px;font-size:.6rem;color:var(--muted);line-height:1.6;background:rgba(0,0,0,.15);padding:7px;border:1px solid var(--border)">
      <strong style="color:var(--white)">v6 PROVEN SYSTEM:</strong> Signals come from backtested indicators (Ichimoku + KAMA + RSI), not gate counts. MTF table is context only.<br>
      <strong style="color:var(--yellow)">Position sizing:</strong> 2 signals = $500 · 3 signals = $750 · 4 signals = $1000
    </div>
  </div>

  <div class="card">
    <div class="ct">Market Regime · ATR · Compression</div>
    <div style="background:rgba(0,0,0,.2);border:1px solid {spy_c};padding:9px;margin-bottom:9px">
      <div style="font-size:.58rem;color:var(--muted);margin-bottom:3px">SPY MACRO REGIME</div>
      <div style="font-size:.8rem;font-weight:700;color:{spy_c}">SPY {spy_l} · ${d['spy_price']} vs 50 EMA ${d['spy_e50']}</div>
      <div style="font-size:.6rem;color:var(--muted);margin-top:2px">{"✅ Macro tailwind" if d['spy_bull'] else "❌ Macro headwind"}</div>
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
      <div style="font-size:.58rem;color:var(--muted)">Expected move. Exp options move: <strong style="color:var(--blue)">±${opts['exp_move']}</strong></div>
    </div>
    <div>
      <div style="display:flex;justify-content:space-between;margin-bottom:3px">
        <span style="font-size:.62rem">Volume vs 20-bar avg</span>
        <span style="font-size:.62rem;font-weight:700;color:{vol_c}">{d['vol_ratio']}x · {vol_m:.0f}M / {avg_m:.0f}M</span>
      </div>
      <div style="height:5px;background:rgba(255,255,255,.05);border-radius:3px"><div style="height:100%;width:{min(d['vol_ratio']*50,100):.0f}%;background:{vol_c};border-radius:3px"></div></div>
      <div style="font-size:.58rem;color:var(--muted);margin-top:2px">{"✅ 1.5x+ = high conviction" if d['vol_ratio']>=1.5 else ("OK" if d['vol_ratio']>=1.0 else "❌ Low — likely chop")}</div>
    </div>
  </div>

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
        <div>RSI: <strong style="color:var(--blue)">{d['h1']['rsi'] if d['h1'] else '—'}</strong></div>
      </div>
    </div>
  </div>
</div>

<!-- SIGNAL BREAKDOWN + OPTIONS -->
<div class="g3">
  <div class="card">
    <div class="ct">Call Analysis ({al['call_count']}/{max_s})</div>
    {signal_panel(al['call_reasons'], al['call_context'], al['call_count'], max_s, "call")}
    <div style="margin-top:10px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:5px">CALL R:R CALCULATOR</div>
      {rr_box(al['call_rr'],"call")}
    </div>
  </div>
  <div class="card">
    <div class="ct">Put Analysis ({al['put_count']}/{max_s})</div>
    {signal_panel(al['put_reasons'], al['put_context'], al['put_count'], max_s, "put")}
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
    <div class="ct">v6 Proven Entry Model — Backtested System</div>
    <div style="font-size:.66rem;line-height:1.8;color:var(--text)">
      <div style="color:#4fc3f7;font-weight:700;margin-bottom:6px;font-size:.7rem">🔬 BACKTESTED RESEARCH RESULTS</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px">
        <div style="background:rgba(179,157,219,.08);border:1px solid rgba(179,157,219,.3);padding:6px;text-align:center">
          <div style="font-size:.5rem;color:#b39ddb">S1 ICHIMOKU</div>
          <div style="font-size:.75rem;color:#00ff9d;font-weight:700">PF 4.18</div>
          <div style="font-size:.5rem;color:var(--muted)">49% WR</div>
        </div>
        <div style="background:rgba(124,77,255,.08);border:1px solid rgba(124,77,255,.3);padding:6px;text-align:center">
          <div style="font-size:.5rem;color:#7c4dff">S2 KAUFMAN</div>
          <div style="font-size:.75rem;color:#00ff9d;font-weight:700">PF 4.34</div>
          <div style="font-size:.5rem;color:var(--muted)">63% WR</div>
        </div>
        <div style="background:rgba(79,195,247,.08);border:1px solid rgba(79,195,247,.3);padding:6px;text-align:center">
          <div style="font-size:.5rem;color:#4fc3f7">S3 RSI</div>
          <div style="font-size:.75rem;color:#00ff9d;font-weight:700">77% WR</div>
          <div style="font-size:.5rem;color:var(--muted)">PF 2.15</div>
        </div>
      </div>

      <div style="color:var(--green);font-weight:700;margin-bottom:4px">✅ ENTRY RULES:</div>
      1. Need <strong style="color:var(--white)">2+ proven signals</strong> aligned in same direction<br>
      2. Check <strong style="color:var(--yellow)">context filters</strong>: Brando bias ($180.34), SPY macro, volume<br>
      3. <strong style="color:var(--green)">Power Window (1–2:30 PM CT)</strong> = highest conviction entries<br>
      4. Position size scales with signal count: 2=$500, 3=$750, 4=$1000<br>
    </div>
    <div style="margin-top:9px;padding:9px;background:rgba(255,140,66,.07);border:1px solid rgba(255,140,66,.3);font-size:.65rem;color:var(--orange);line-height:1.6">
      🚪 <strong>EXIT RULES (from backtest):</strong><br>
      +60% → SELL ALL · −35% → HARD STOP · Trailing: Lock +30% at +50% · Max hold: ~1 day<br>
      MACD flips → HALF OUT · RSI divergence opposes → EXIT WARNING<br>
      Day 3 → EXIT regardless (theta decay accelerates)
    </div>
  </div>
  <div class="card">
    <div class="ct">NVDA News — Live</div>
    {news_html or '<div style="font-size:.68rem;color:var(--muted);padding:8px">No articles fetched.</div>'}
  </div>
</div>

<div style="text-align:center;padding:10px;font-size:.54rem;color:var(--muted);border-top:1px solid var(--border);line-height:1.9;margin-top:2px;word-break:break-word">
  🔬 v6 PROVEN SYSTEM · Ichimoku (PF 4.18) + Kaufman (PF 4.34) + RSI (77% WR) + MACD combo (68% WR)<br>
  Auto-updated · Chicago time · Data: Yahoo Finance · S/R: @EliteOptions2<br>
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

    print("📡 Fetching NVDA + SPY (daily/4H/1H/15m/5m)...")
    d = fetch_all()
    print(f"   ${d['price']} | {d['change_pct']:+.2f}% | Vol {d['vol_ratio']}x | ATR ${d['atr']} | Compression {d['compression']}/100")
    print(f"   SPY {'BULL' if d['spy_bull'] else 'BEAR'} | Daily RSI {d['daily']['rsi'] if d['daily'] else '—'}")

    # Print proven signals
    print(f"\n🔬 PROVEN SIGNALS:")
    print(f"   S1 Ichimoku (PF 4.18): {d['sig_ichimoku']['label']} — {d['sig_ichimoku']['detail']}")
    print(f"   S2 Kaufman  (PF 4.34): {d['sig_kama']['label']} — {d['sig_kama']['detail']}")
    print(f"   S3 RSI      (77% WR):  {d['sig_rsi']['label']} — {d['sig_rsi']['detail']}")
    print(f"   S4 MACD+RSI (68% WR):  {d['sig_macd_combo']['label']} — {d['sig_macd_combo']['detail']}")
    print(f"   Divergence: {d['h1_div']['label']}")

    print("\n🗺️  Building Brando level context...")
    bctx = get_brando_context(d["price"])
    print(f"   {bctx['scen_label']} | On level: {bctx['on_level']}")

    print("📋 Fetching options chain...")
    opts = fetch_options(d["price"])
    print(f"   {opts['expiry']} | {opts['dte']} DTE | IV {opts['iv_30']}% | Exp move ±${opts['exp_move']}")

    print("📰 Fetching news...")
    news = fetch_news()
    print(f"   {len(news)} articles")

    print("🧠 Building proven signal aggregation...")
    al = build_signals(d, opts, session, bctx)
    print(f"   Call {al['call_count']}/{al['max_signals']} | Put {al['put_count']}/{al['max_signals']}")

    verdict = get_verdict(al, d, session, opts, bctx)
    print(f"   {verdict['verdict']}")

    print("🖥️  Rendering HTML...")
    html = render(d, opts, news, al, verdict, session, bctx, ct_now)
    Path("index.html").write_text(html, encoding="utf-8")
    print(f"✅ Done — {len(html):,} bytes")
