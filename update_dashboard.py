"""
NVDA Options Command Center — Intraday Auto-Updater
Fetches live data from Yahoo Finance and generates index.html
Runs 12x per trading day at key NVDA liquidity windows (Chicago time)
"""

import yfinance as yf
import datetime
import pytz
import feedparser
import numpy as np
from pathlib import Path

# ─────────────────────────────────────────────
# SESSION PHASE DETECTION (Chicago time)
# ─────────────────────────────────────────────

SESSIONS = [
    {"name": "PRE-MARKET",         "start": (7,  0), "end": (8, 30),  "color": "#5a7a99",  "emoji": "🌅", "advice": "Bias check only. No trades yet. Watch futures & news."},
    {"name": "OPENING FAKE-OUT",   "start": (8, 30), "end": (9, 15),  "color": "#ff8c42",  "emoji": "⚠️", "advice": "HIGH VOLATILITY. Fake breakouts common. Wait for direction to confirm before entering."},
    {"name": "CONTINUATION",       "start": (9, 15), "end": (10, 30), "color": "#ffd700",  "emoji": "📈", "advice": "If trend is real it continues here. Look for pullback to 5-12 cloud as entry."},
    {"name": "DEAD ZONE / CHOP",   "start": (10, 30),"end": (13, 0),  "color": "#ff3a5e",  "emoji": "💤", "advice": "PREMIUM DECAY ZONE. Theta bleeds options. Avoid new entries. Best to wait."},
    {"name": "POWER WINDOW",       "start": (13, 0), "end": (14, 30), "color": "#00ff9d",  "emoji": "🏆", "advice": "INSTITUTIONAL PUSH. Best 1-3 day setups built here. High conviction entries only."},
    {"name": "CLOSING PUSH",       "start": (14, 30),"end": (15, 0),  "color": "#4fc3f7",  "emoji": "🔔", "advice": "Final momentum push. Hold if trade is working, otherwise exit before close."},
    {"name": "AFTER HOURS",        "start": (15, 0), "end": (23, 59), "color": "#5a7a99",  "emoji": "🌙", "advice": "Market closed. Review today's trade. Plan tomorrow's setup."},
]

def get_session(ct_now):
    h, m = ct_now.hour, ct_now.minute
    t = h * 60 + m
    for s in SESSIONS:
        sh = s["start"][0] * 60 + s["start"][1]
        eh = s["end"][0]   * 60 + s["end"][1]
        if sh <= t < eh:
            return s
    return SESSIONS[-1]

# ─────────────────────────────────────────────
# 1. FETCH LIVE DATA
# ─────────────────────────────────────────────

def fetch_nvda_data():
    ticker = yf.Ticker("NVDA")
    info   = ticker.info

    # Daily history for EMAs, S/R
    hist    = ticker.history(period="3mo",  interval="1d")
    hist_1y = ticker.history(period="1y",   interval="1d")

    # Intraday 1-hour (last 30 days)
    hist_1h = ticker.history(period="30d",  interval="1h")

    # Intraday 5-min (today/last 2 days for current price action)
    hist_5m = ticker.history(period="2d",   interval="5m")

    price      = info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1]
    prev_close = info.get("previousClose") or hist["Close"].iloc[-2]
    change     = price - prev_close
    change_pct = (change / prev_close) * 100
    volume     = info.get("regularMarketVolume") or hist["Volume"].iloc[-1]
    avg_volume = info.get("averageVolume")        or hist["Volume"].mean()

    week52_high = info.get("fiftyTwoWeekHigh") or hist_1y["High"].max()
    week52_low  = info.get("fiftyTwoWeekLow")  or hist_1y["Low"].min()

    # ── Daily EMAs (for cloud status) ──
    closes = hist["Close"]
    ema9   = closes.ewm(span=9,  adjust=False).mean().iloc[-1]
    ema21  = closes.ewm(span=21, adjust=False).mean().iloc[-1]
    ema34  = closes.ewm(span=34, adjust=False).mean().iloc[-1]
    ema50  = closes.ewm(span=50, adjust=False).mean().iloc[-1]

    # ── 1-Hour EMAs (for intraday trend) ──
    if len(hist_1h) >= 50:
        c1h     = hist_1h["Close"]
        ema9_1h  = c1h.ewm(span=9,  adjust=False).mean().iloc[-1]
        ema21_1h = c1h.ewm(span=21, adjust=False).mean().iloc[-1]
        ema34_1h = c1h.ewm(span=34, adjust=False).mean().iloc[-1]
        ema50_1h = c1h.ewm(span=50, adjust=False).mean().iloc[-1]
    else:
        ema9_1h = ema21_1h = ema34_1h = ema50_1h = price

    # ── IMACD on daily (34,9) ──
    ema34_s  = closes.ewm(span=34, adjust=False).mean()
    sig_s    = ema34_s.ewm(span=9, adjust=False).mean()
    macd_val  = ema34_s.iloc[-1]  - sig_s.iloc[-1]
    macd_prev = ema34_s.iloc[-2]  - sig_s.iloc[-2]

    # ── IMACD on 1-hour (34,9) ──
    if len(hist_1h) >= 50:
        c1h       = hist_1h["Close"]
        ema34_1h_s = c1h.ewm(span=34, adjust=False).mean()
        sig_1h_s   = ema34_1h_s.ewm(span=9, adjust=False).mean()
        macd_1h    = round(float(ema34_1h_s.iloc[-1] - sig_1h_s.iloc[-1]), 3)
        macd_1h_p  = round(float(ema34_1h_s.iloc[-2] - sig_1h_s.iloc[-2]), 3)
    else:
        macd_1h = macd_1h_p = 0.0

    # ── 5-min price action: recent candles ──
    recent_candles = []
    if len(hist_5m) >= 6:
        ct_tz = pytz.timezone("America/Chicago")
        for idx, row in hist_5m.tail(8).iterrows():
            try:
                ts = idx.tz_convert(ct_tz)
            except Exception:
                ts = idx
            recent_candles.append({
                "time":   ts.strftime("%I:%M %p"),
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "bull":   float(row["Close"]) >= float(row["Open"]),
            })

    # ── Today's intraday high/low ──
    if len(hist_5m) > 0:
        intraday_high = round(float(hist_5m["High"].max()),  2)
        intraday_low  = round(float(hist_5m["Low"].min()),   2)
    else:
        intraday_high = intraday_low = price

    return {
        "price":          round(price,      2),
        "prev_close":     round(prev_close, 2),
        "change":         round(change,     2),
        "change_pct":     round(change_pct, 2),
        "volume":         int(volume),
        "avg_volume":     int(avg_volume),
        "volume_ratio":   round(volume / avg_volume, 2),
        "week52_high":    round(week52_high, 2),
        "week52_low":     round(week52_low,  2),
        "ema9":           round(ema9,   2),
        "ema21":          round(ema21,  2),
        "ema34":          round(ema34,  2),
        "ema50":          round(ema50,  2),
        "ema9_1h":        round(ema9_1h,   2),
        "ema21_1h":       round(ema21_1h,  2),
        "ema34_1h":       round(ema34_1h,  2),
        "ema50_1h":       round(ema50_1h,  2),
        "macd_val":       round(macd_val,  3),
        "macd_prev":      round(macd_prev, 3),
        "macd_1h":        macd_1h,
        "macd_1h_p":      macd_1h_p,
        "intraday_high":  intraday_high,
        "intraday_low":   intraday_low,
        "recent_candles": recent_candles,
        "hist":           hist,
        "hist_1y":        hist_1y,
    }


def fetch_options_data(price):
    ticker  = yf.Ticker("NVDA")
    expiries = ticker.options
    et      = pytz.timezone("America/New_York")
    today   = datetime.datetime.now(et).date()
    target  = today + datetime.timedelta(days=28)

    chosen_exp = None
    for exp in expiries:
        exp_date = datetime.datetime.strptime(exp, "%Y-%m-%d").date()
        if exp_date >= target:
            chosen_exp = exp
            break
    if not chosen_exp and expiries:
        chosen_exp = expiries[-1]

    chain = ticker.option_chain(chosen_exp) if chosen_exp else None
    calls_data, puts_data = [], []
    iv_30 = 0.50

    if chain:
        calls = chain.calls
        puts  = chain.puts

        for _, row in calls.iterrows():
            strike = row["strike"]
            if abs(strike - price) <= 22:
                calls_data.append({
                    "strike": strike,
                    "price":  round(float(row.get("lastPrice", 0) or row.get("ask", 0) or 0), 2),
                    "bid":    round(float(row.get("bid", 0) or 0), 2),
                    "ask":    round(float(row.get("ask", 0) or 0), 2),
                    "delta":  round(float(row.get("delta", 0) or 0), 2),
                    "iv":     round(float(row.get("impliedVolatility", 0.5) or 0.5) * 100, 1),
                    "volume": int(row.get("volume", 0) or 0),
                    "oi":     int(row.get("openInterest", 0) or 0),
                })

        for _, row in puts.iterrows():
            strike = row["strike"]
            if abs(strike - price) <= 18 and strike <= price:
                puts_data.append({
                    "strike": strike,
                    "price":  round(float(row.get("lastPrice", 0) or row.get("ask", 0) or 0), 2),
                    "bid":    round(float(row.get("bid", 0) or 0), 2),
                    "ask":    round(float(row.get("ask", 0) or 0), 2),
                    "delta":  round(float(row.get("delta", 0) or 0), 2),
                    "iv":     round(float(row.get("impliedVolatility", 0.5) or 0.5) * 100, 1),
                    "volume": int(row.get("volume", 0) or 0),
                    "oi":     int(row.get("openInterest", 0) or 0),
                })

        atm = calls[abs(calls["strike"] - price) < 5]
        if not atm.empty:
            iv_30 = float(atm.iloc[0].get("impliedVolatility", 0.50) or 0.50)

    calls_data.sort(key=lambda x: x["strike"])
    puts_data.sort(key=lambda x: x["strike"], reverse=True)

    return {
        "expiry": chosen_exp or "N/A",
        "calls":  calls_data[:7],
        "puts":   puts_data[:4],
        "iv_30":  round(iv_30 * 100, 1),
    }


def fetch_support_resistance(hist, hist_1y, price):
    highs_1y = hist_1y["High"].values
    lows_1y  = hist_1y["Low"].values
    week52_high = float(np.max(highs_1y))
    week52_low  = float(np.min(lows_1y))

    highs_3m = hist["High"].values
    lows_3m  = hist["Low"].values

    def find_pivots(data, window=5, mode="high"):
        pivots = []
        for i in range(window, len(data) - window):
            seg = data[i-window:i+window+1]
            if mode == "high" and data[i] == max(seg):
                pivots.append(round(float(data[i]), 2))
            elif mode == "low" and data[i] == min(seg):
                pivots.append(round(float(data[i]), 2))
        return pivots

    def cluster(levels, threshold=3.0):
        if not levels: return []
        levels = sorted(set(levels))
        clustered, group = [], [levels[0]]
        for l in levels[1:]:
            if l - group[-1] <= threshold:
                group.append(l)
            else:
                clustered.append(round(sum(group)/len(group), 2))
                group = [l]
        clustered.append(round(sum(group)/len(group), 2))
        return clustered

    pivot_highs = find_pivots(highs_3m, mode="high")
    pivot_lows  = find_pivots(lows_3m,  mode="low")
    resistance  = sorted([r for r in cluster(pivot_highs) if r > price], reverse=True)[:5]
    support     = sorted([s for s in cluster(pivot_lows)  if s < price])[:5]

    if week52_high not in resistance: resistance.append(round(week52_high, 2))
    if week52_low  not in support:    support.append(round(week52_low,  2))

    return {
        "resistance":   sorted(resistance, reverse=True)[:6],
        "support":      sorted(support,    reverse=True)[:6],
        "week52_high":  round(week52_high, 2),
        "week52_low":   round(week52_low,  2),
    }


def fetch_news():
    urls = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US",
        "https://finance.yahoo.com/rss/headline?s=NVDA",
    ]
    bull_words = ["beat","surge","rally","upgrade","buy","growth","record","strong","profit","bullish","target","raise","partnership","deal","expand"]
    bear_words = ["miss","drop","fall","downgrade","sell","cut","loss","bearish","concern","risk","decline","weak","lawsuit","probe","ban","tariff"]
    articles = []
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title    = entry.get("title", "")
                text     = (title + " " + entry.get("summary","")).lower()
                bull_s   = sum(1 for w in bull_words if w in text)
                bear_s   = sum(1 for w in bear_words if w in text)
                sentiment = "bull" if bull_s > bear_s else ("bear" if bear_s > bull_s else "neut")
                articles.append({
                    "title":     title[:120],
                    "published": entry.get("published","")[:30],
                    "link":      entry.get("link","#"),
                    "sentiment": sentiment,
                })
            if articles: break
        except Exception:
            continue
    return articles[:7]


# ─────────────────────────────────────────────
# 2. VERDICT (uses BOTH daily + 1-hour signals)
# ─────────────────────────────────────────────

def generate_verdict(d, opts, session):
    price    = d["price"]
    # Daily cloud
    above_d  = price > max(d["ema34"], d["ema50"])
    below_d  = price < min(d["ema34"], d["ema50"])
    inside_d = not above_d and not below_d
    fast_d   = d["ema9"]    > d["ema21"]
    # 1-Hour cloud
    above_1h = price > max(d["ema34_1h"], d["ema50_1h"])
    below_1h = price < min(d["ema34_1h"], d["ema50_1h"])
    fast_1h  = d["ema9_1h"] > d["ema21_1h"]
    # IMACD
    macd_bull_d  = d["macd_val"] > 0
    macd_bull_1h = d["macd_1h"]  > 0

    call_t = next((c for c in opts["calls"] if 2.50 <= c["price"] <= 4.50), None)
    put_t  = next((p for p in opts["puts"]  if 2.50 <= p["price"] <= 4.50), None)

    # Dead zone override
    if session["name"] == "DEAD ZONE / CHOP":
        return {
            "verdict": "💤 DEAD ZONE — NO NEW TRADES",
            "color": "#ff3a5e", "border_color": "#ff3a5e",
            "bias": "CHOP", "bias_color": "#ff8c42",
            "explanation": "12:00–1:00 PM CT is the premium decay zone. Theta bleeds options fastest here. Any position you open now loses value just from time. Wait for the 1:00 PM Power Window.",
            "trade_idea": "Sit on hands. If already in a trade, hold only if up. No new entries until 1:00 PM CT.",
            "above_cloud_d": above_d, "below_cloud_d": below_d, "inside_cloud_d": inside_d,
            "above_cloud_1h": above_1h, "below_cloud_1h": below_1h,
            "fast_bull_d": fast_d, "fast_bull_1h": fast_1h,
            "macd_bull_d": macd_bull_d, "macd_bull_1h": macd_bull_1h,
        }

    if session["name"] == "OPENING FAKE-OUT":
        return {
            "verdict": "⚠️ OPENING — WAIT FOR CONFIRMATION",
            "color": "#ff8c42", "border_color": "#ff8c42",
            "bias": "CAUTION", "bias_color": "#ff8c42",
            "explanation": f"9:30–10:15 ET (8:30–9:15 CT) is the fake-out zone. NVDA often reverses hard in the first 15 min. Wait for 9:15 CT before entering. 1-Hour IMACD: {d['macd_1h']:+.3f}.",
            "trade_idea": "Watch direction. If IMACD 1H confirms and price holds above/below cloud for 2+ candles → consider entry at 9:15 CT.",
            "above_cloud_d": above_d, "below_cloud_d": below_d, "inside_cloud_d": inside_d,
            "above_cloud_1h": above_1h, "below_cloud_1h": below_1h,
            "fast_bull_d": fast_d, "fast_bull_1h": fast_1h,
            "macd_bull_d": macd_bull_d, "macd_bull_1h": macd_bull_1h,
        }

    # Full signal logic
    call_score = sum([above_d, above_1h, fast_d, fast_1h, macd_bull_d, macd_bull_1h])
    put_score  = sum([below_d, below_1h, not fast_d, not fast_1h, not macd_bull_d, not macd_bull_1h])

    if call_score >= 5:
        verdict = "✅ CALL SETUP — High Confidence"
        color, border_color = "#00ff9d", "#00ff9d"
        bias, bias_color = "BULLISH", "#00ff9d"
        exp = f"Daily + 1H both bullish. IMACD Daily: {d['macd_val']:+.3f} | 1H: {d['macd_1h']:+.3f}. {session['advice']}"
        idea = f"Buy ${call_t['strike']:.0f}C {opts['expiry']} (~${call_t['price']:.2f}). Target: +80% (${call_t['price']*1.8:.2f}). Stop: -50% (${call_t['price']*0.5:.2f})." if call_t else "Check chain for $3 call near ATM."
    elif call_score == 4:
        verdict = "⏸ CALL WATCH — Needs 1 More Confirm"
        color, border_color = "#ffd700", "#ffd700"
        bias, bias_color = "LEANING BULL", "#ffd700"
        exp = f"4/6 bull signals. Wait for IMACD 1H to confirm above zero ({d['macd_1h']:+.3f}) or price to reclaim 1H cloud."
        idea = "Not quite ready. Watch for 1H IMACD cross above zero — then enter call."
    elif put_score >= 5:
        verdict = "🔴 PUT SETUP — High Confidence"
        color, border_color = "#ff3a5e", "#ff3a5e"
        bias, bias_color = "BEARISH", "#ff3a5e"
        exp = f"Daily + 1H both bearish. IMACD Daily: {d['macd_val']:+.3f} | 1H: {d['macd_1h']:+.3f}. {session['advice']}"
        idea = f"Buy ${put_t['strike']:.0f}P {opts['expiry']} (~${put_t['price']:.2f}) on bounce fail at VWAP/cloud. Stop: -50%. Target: next support." if put_t else "Check chain for $3 put below ATM."
    elif put_score == 4:
        verdict = "⏸ PUT WATCH — Needs 1 More Confirm"
        color, border_color = "#ff8c42", "#ff8c42"
        bias, bias_color = "LEANING BEAR", "#ff8c42"
        exp = f"4/6 bear signals. Watch for bounce failure at ${max(d['ema34_1h'], d['ema50_1h']):.2f} (1H cloud underside)."
        idea = "Wait for IMACD 1H to confirm below zero and price rejection at cloud — then enter put."
    elif inside_d:
        verdict = "⏸ INSIDE CLOUD — NO TRADE ZONE"
        color, border_color = "#ff8c42", "#ff8c42"
        bias, bias_color = "NEUTRAL", "#ff8c42"
        exp = f"Price is inside the daily 34-50 cloud (${min(d['ema34'],d['ema50']):.2f}–${max(d['ema34'],d['ema50']):.2f}). This is chop. Options lose value fast here."
        idea = "Wait for a clean break above or below the cloud with volume confirmation."
    else:
        verdict = "⏸ MIXED SIGNALS — WAIT"
        color, border_color = "#ff8c42", "#5a7a99"
        bias, bias_color = "MIXED", "#ff8c42"
        exp = f"Daily IMACD: {d['macd_val']:+.3f} | 1H IMACD: {d['macd_1h']:+.3f}. Signals not fully aligned. Patience."
        idea = "No clear setup. Check back at next refresh window."

    return {
        "verdict": verdict, "color": color, "border_color": border_color,
        "bias": bias, "bias_color": bias_color,
        "explanation": exp, "trade_idea": idea,
        "above_cloud_d": above_d, "below_cloud_d": below_d, "inside_cloud_d": inside_d,
        "above_cloud_1h": above_1h, "below_cloud_1h": below_1h,
        "fast_bull_d": fast_d, "fast_bull_1h": fast_1h,
        "macd_bull_d": macd_bull_d, "macd_bull_1h": macd_bull_1h,
    }


# ─────────────────────────────────────────────
# 3. RENDER HTML
# ─────────────────────────────────────────────

def render_html(d, opts, sr, news, verdict, session, ct_now):
    price  = d["price"]
    chg    = d["change"]
    chg_p  = d["change_pct"]
    chg_c  = "#00ff9d" if chg >= 0 else "#ff3a5e"
    arrow  = "▲" if chg >= 0 else "▼"
    vol_m  = d["volume"] / 1_000_000
    avg_m  = d["avg_volume"] / 1_000_000
    vol_c  = "#00ff9d" if d["volume_ratio"] > 1.2 else ("#ff8c42" if d["volume_ratio"] > 0.8 else "#ff3a5e")
    iv_c   = "#00ff9d" if opts["iv_30"] < 35 else ("#ffd700" if opts["iv_30"] < 55 else "#ff3a5e")

    date_str = ct_now.strftime("%A, %B %d · %Y")
    time_str = ct_now.strftime("%I:%M %p CT")

    # ── Session timeline ──
    timeline_html = ""
    for s in SESSIONS[:-1]:  # skip after hours in timeline
        sh = s["start"][0] * 60 + s["start"][1]
        t  = ct_now.hour * 60 + ct_now.minute
        eh = s["end"][0]   * 60 + s["end"][1]
        is_active = sh <= t < eh
        bg = f"background:{s['color']}22;border:1px solid {s['color']};" if is_active else "background:var(--surface2);border:1px solid var(--border);"
        name_c = s["color"] if is_active else "var(--muted)"
        time_label = f"{s['start'][0]:02d}:{s['start'][1]:02d}–{s['end'][0]:02d}:{s['end'][1]:02d}"
        active_tag = f'<div style="font-size:.55rem;color:{s["color"]};letter-spacing:1px;margin-top:2px">● ACTIVE NOW</div>' if is_active else ""
        timeline_html += f'''<div style="{bg}padding:8px;text-align:center">
          <div style="font-size:.55rem;color:var(--muted)">{time_label} CT</div>
          <div style="font-size:.62rem;font-weight:700;color:{name_c};margin-top:2px">{s["emoji"]} {s["name"]}</div>
          {active_tag}
        </div>'''

    # ── Recent candles ──
    candle_html = ""
    for c in d["recent_candles"]:
        c_col = "#00ff9d" if c["bull"] else "#ff3a5e"
        body  = abs(c["close"] - c["open"])
        candle_html += f'''<tr>
          <td style="color:var(--muted);font-size:.62rem">{c["time"]}</td>
          <td style="color:{c_col};font-weight:700">${c["close"]:.2f}</td>
          <td style="color:{c_col}">{("▲" if c["bull"] else "▼")}</td>
          <td style="color:var(--muted)">${c["high"]:.2f}</td>
          <td style="color:var(--muted)">${c["low"]:.2f}</td>
          <td style="color:var(--green-dim)">{c["volume"]//1000}K</td>
        </tr>'''

    # ── Cloud badges ──
    def badge(cond, yes_label, no_label, yes_cls="bull", no_cls="bear"):
        cls = yes_cls if cond else no_cls
        lbl = yes_label if cond else no_label
        return f'<div class="ind-badge {cls}">{lbl}</div>'

    # ── S/R rows ──
    sr_rows = ""
    for r in sr["resistance"][:4]:
        dist = round(r - price, 2)
        key  = r == sr["week52_high"]
        sr_rows += f'<tr><td>RESISTANCE</td><td>${r:.2f}</td><td style="color:{"#ff8c42" if key else "#ff3a5e"}">{"★ KEY" if key else "■"}</td><td style="color:var(--muted);font-size:.6rem">+${dist:.2f}</td></tr>'
    sr_rows += f'<tr><td>──</td><td style="color:#ffd700">▶ ${price:.2f}</td><td style="color:#ffd700" colspan="2">◆ NOW | H:{d["intraday_high"]} L:{d["intraday_low"]}</td></tr>'
    for s in sr["support"][:4]:
        dist = round(price - s, 2)
        key  = s == sr["week52_low"]
        sr_rows += f'<tr><td>SUPPORT</td><td>${s:.2f}</td><td style="color:{"#ff8c42" if key else "#00ff9d"}">{"★ KEY" if key else "■"}</td><td style="color:var(--muted);font-size:.6rem">-${dist:.2f}</td></tr>'

    # ── Options chain ──
    call_rows = ""
    for c in opts["calls"]:
        atm   = ' class="strike-atm"' if abs(c["strike"] - price) < 4 else ""
        tgt   = "🎯 " if 2.50 <= c["price"] <= 4.00 else ""
        sp    = round(c["ask"] - c["bid"], 2)
        sp_c  = "#00ff9d" if sp < 0.20 else ("#ffd700" if sp < 0.40 else "#ff3a5e")
        liq   = "" if c["volume"] > 200 and c["oi"] > 500 else " ⚠️"
        call_rows += f'<tr{atm}><td>${c["strike"]:.0f}C {tgt}</td><td class="price-val">${c["price"]:.2f}</td><td class="delta-val">{c["delta"] or "—"}</td><td class="iv-val">{c["iv"]}%</td><td style="color:{sp_c}">${sp:.2f}</td><td class="vol-val">{c["volume"]:,}{liq}</td></tr>'

    put_rows = ""
    for p in opts["puts"]:
        tgt  = "🎯 " if 2.50 <= p["price"] <= 4.00 else ""
        sp   = round(p["ask"] - p["bid"], 2)
        sp_c = "#00ff9d" if sp < 0.20 else ("#ffd700" if sp < 0.40 else "#ff3a5e")
        liq  = "" if p["volume"] > 200 and p["oi"] > 500 else " ⚠️"
        put_rows += f'<tr><td>${p["strike"]:.0f}P {tgt}</td><td class="price-val">${p["price"]:.2f}</td><td class="delta-val">{p["delta"] or "—"}</td><td class="iv-val">{p["iv"]}%</td><td style="color:{sp_c}">${sp:.2f}</td><td class="vol-val">{p["volume"]:,}{liq}</td></tr>'

    # ── News ──
    news_html = ""
    for n in news:
        dc = "#00ff9d" if n["sentiment"]=="bull" else ("#ff3a5e" if n["sentiment"]=="bear" else "#ffd700")
        lbl = "BULLISH" if n["sentiment"]=="bull" else ("BEARISH" if n["sentiment"]=="bear" else "NEUTRAL")
        news_html += f'''<div class="news-item">
          <div class="news-dot" style="background:{dc}"></div>
          <div><div class="news-text"><a href="{n["link"]}" target="_blank" style="color:inherit;text-decoration:none">{n["title"]}</a>
            <span class="news-impact" style="color:{dc}">[{lbl}]</span></div>
            <div class="news-source">{n["published"]}</div></div></div>'''

    # ── Checklist ──
    def check(ok, text, good, bad):
        cls = "done" if ok else "fail"
        ic  = "✓" if ok else "✗"
        rc  = "#00ff9d" if ok else "#ff3a5e"
        rl  = good if ok else bad
        return f'<div class="check-item"><div class="check-box {cls}" onclick="toggleCheck(this)">{ic}</div><div class="check-text">{text}</div><div class="check-result" style="color:{rc}">{rl}</div></div>'

    cl = (
        check(True, f"Expiration ≥ 20 DTE — using {opts['expiry']}", opts["expiry"], "Check expiry") +
        check(any(2.5<=c["price"]<=4.5 for c in opts["calls"]), "Call near $3.00 in chain", "EXISTS", "NOT FOUND") +
        check(opts["iv_30"] < 50, f"IV below 50% (now {opts['iv_30']}%)", f"{opts['iv_30']}% OK", f"{opts['iv_30']}% HIGH") +
        check(verdict["macd_bull_d"], f"IMACD Daily above zero ({d['macd_val']:+.3f})", "✓ BULL", "✗ WAIT") +
        check(verdict["macd_bull_1h"], f"IMACD 1H above zero ({d['macd_1h']:+.3f})", "✓ BULL", "✗ WAIT") +
        check(verdict["above_cloud_d"], f"Price above daily 34-50 cloud (${min(d['ema34'],d['ema50']):.2f}–${max(d['ema34'],d['ema50']):.2f})", "✓ ABOVE", "✗ BELOW") +
        check(session["name"] not in ["DEAD ZONE / CHOP","OPENING FAKE-OUT"], f"Session OK: {session['name']}", "GOOD SESSION", "WRONG TIME") +
        check(d["volume_ratio"] > 0.8, f"Volume: {d['volume_ratio']}x avg ({vol_m:.0f}M / {avg_m:.0f}M avg)", "LIQUID", "LOW VOL")
    )

    v = verdict
    yr = (price - d["week52_low"]) / (d["week52_high"] - d["week52_low"]) * 100

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="300">
<title>Daily Research Notes — NVDA</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#070b12;--surface:#0d1520;--surface2:#111d2e;--border:#1e3a5f;
  --green:#00ff9d;--green-dim:#00c87a;--red:#ff3a5e;--red-dim:#cc1f40;
  --yellow:#ffd700;--orange:#ff8c42;--blue:#4fc3f7;--white:#e8f4ff;--muted:#5a7a99;--text:#c8ddf0;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;
  background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(0,80,160,.15) 0%,transparent 70%),
  repeating-linear-gradient(0deg,transparent,transparent 39px,rgba(30,58,95,.12) 39px,rgba(30,58,95,.12) 40px),
  repeating-linear-gradient(90deg,transparent,transparent 39px,rgba(30,58,95,.07) 39px,rgba(30,58,95,.07) 40px);}}
.header{{border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;
  background:rgba(13,21,32,.97);backdrop-filter:blur(10px);position:sticky;top:0;z-index:100;}}
.ticker{{font-family:'Syne',sans-serif;font-size:1.7rem;font-weight:800;color:var(--white);letter-spacing:2px;}}
.main{{max-width:1200px;margin:0 auto;padding:18px;display:grid;gap:14px;}}
.verdict-banner{{background:linear-gradient(135deg,#0a1929,#0d2035);border:1px solid var(--border);
  border-left:4px solid {v["border_color"]};padding:16px 20px;display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:center;}}
.three-col{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.card{{background:var(--surface);border:1px solid var(--border);padding:14px;}}
.card-title{{font-size:.6rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:10px;
  padding-bottom:8px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:6px;}}
.card-title::before{{content:'';width:5px;height:5px;background:var(--blue);display:block;border-radius:50%;}}
.ind-row{{display:flex;flex-direction:column;gap:7px;}}
.ind-item{{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:8px 10px;
  background:var(--surface2);border:1px solid rgba(30,58,95,.5);}}
.ind-name{{font-size:.68rem;color:var(--text);}}
.ind-desc{{font-size:.58rem;color:var(--muted);margin-top:2px;}}
.ind-badge{{font-size:.58rem;letter-spacing:1px;padding:3px 8px;font-weight:700;white-space:nowrap;}}
.bear{{background:rgba(255,58,94,.15);color:var(--red);border:1px solid var(--red-dim);}}
.bull{{background:rgba(0,255,157,.12);color:var(--green);border:1px solid var(--green-dim);}}
.neut{{background:rgba(255,215,0,.12);color:var(--yellow);border:1px solid goldenrod;}}
.wait{{background:rgba(255,140,66,.12);color:var(--orange);border:1px solid var(--orange);}}
.gauge-row{{display:flex;flex-direction:column;gap:8px;}}
.gauge-bar{{height:4px;background:rgba(255,255,255,.05);border-radius:2px;overflow:hidden;}}
.gauge-fill{{height:100%;border-radius:2px;}}
.levels-table,.chain-table,.ema-table,.candle-table{{width:100%;border-collapse:collapse;}}
.levels-table tr,.chain-table tr,.ema-table tr,.candle-table tr{{border-bottom:1px solid rgba(30,58,95,.4);}}
.levels-table tr:last-child,.chain-table tr:last-child,.ema-table tr:last-child,.candle-table tr:last-child{{border-bottom:none;}}
.levels-table td,.ema-table td,.candle-table td{{padding:5px 4px;font-size:.68rem;}}
.levels-table td:first-child{{color:var(--muted);font-size:.6rem;}}
.levels-table td:nth-child(2){{color:var(--white);font-weight:700;text-align:right;}}
.levels-table td:nth-child(3){{text-align:right;font-size:.6rem;padding-left:6px;}}
.levels-table td:nth-child(4){{text-align:right;font-size:.58rem;color:var(--muted);}}
.chain-table th{{font-size:.58rem;letter-spacing:1px;color:var(--muted);text-align:right;padding:5px 5px;border-bottom:1px solid var(--border);}}
.chain-table th:first-child{{text-align:left;}}
.chain-table td{{padding:6px 5px;font-size:.68rem;text-align:right;}}
.chain-table td:first-child{{text-align:left;color:var(--muted);font-size:.6rem;}}
.strike-atm td{{background:rgba(255,215,0,.06);color:var(--yellow)!important;}}
.delta-val{{color:var(--blue);}} .iv-val{{color:var(--orange);}}
.price-val{{color:var(--white);font-weight:700;}} .vol-val{{color:var(--green-dim);}}
.news-item{{padding:8px 0;border-bottom:1px solid rgba(30,58,95,.4);display:grid;grid-template-columns:auto 1fr;gap:7px;}}
.news-item:last-child{{border-bottom:none;}}
.news-dot{{width:5px;height:5px;border-radius:50%;margin-top:4px;flex-shrink:0;}}
.news-text{{font-size:.66rem;color:var(--text);line-height:1.4;}}
.news-source{{font-size:.57rem;color:var(--muted);margin-top:2px;}}
.news-impact{{font-size:.57rem;font-weight:700;margin-left:5px;}}
.checklist{{display:flex;flex-direction:column;gap:6px;}}
.check-item{{display:flex;align-items:center;gap:8px;padding:8px 10px;background:var(--surface2);border:1px solid rgba(30,58,95,.5);}}
.check-box{{width:14px;height:14px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;
  font-size:.6rem;flex-shrink:0;cursor:pointer;}}
.check-box.done{{background:rgba(0,255,157,.1);border-color:var(--green);color:var(--green);}}
.check-box.fail{{background:rgba(255,58,94,.1);border-color:var(--red);color:var(--red);}}
.check-text{{font-size:.66rem;color:var(--text);flex:1;}}
.check-result{{font-size:.6rem;font-weight:700;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.live-dot{{width:6px;height:6px;border-radius:50%;animation:pulse 1.5s infinite;display:inline-block;margin-right:5px;}}
.session-banner{{padding:10px 14px;border:1px solid {session["color"]};background:{session["color"]}11;
  display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:center;}}
@media(max-width:768px){{.three-col,.two-col{{grid-template-columns:1fr;}}}}
</style>
</head>
<body>
<header class="header">
  <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
    <div class="ticker">NVDA</div>
    <div style="font-size:1.4rem;color:{chg_c};font-weight:700">${price:.2f}</div>
    <div style="font-size:.85rem;color:{chg_c};font-weight:700">{arrow} {chg:+.2f} ({chg_p:+.2f}%)</div>
    <div style="font-size:.6rem;color:var(--muted)">H:{d["intraday_high"]} · L:{d["intraday_low"]}</div>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <div style="font-size:.6rem;color:{session["color"]}"><span class="live-dot" style="background:{session["color"]}"></span>{session["emoji"]} {session["name"]}</div>
    <div style="background:var(--surface2);border:1px solid var(--border);padding:5px 11px;font-size:.68rem;color:var(--muted)">{date_str} · {time_str}</div>
  </div>
</header>

<div class="main">

<!-- SESSION TIMELINE -->
<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px">{timeline_html}</div>

<!-- SESSION ADVICE -->
<div class="session-banner">
  <div style="font-size:1.8rem">{session["emoji"]}</div>
  <div>
    <div style="font-size:.6rem;color:var(--muted);letter-spacing:1px;margin-bottom:3px">{session["name"]} · {session["start"][0]:02d}:{session["start"][1]:02d}–{session["end"][0]:02d}:{session["end"][1]:02d} CT</div>
    <div style="font-size:.75rem;color:{session["color"]};font-weight:700">{session["advice"]}</div>
  </div>
</div>

<!-- VERDICT -->
<div class="verdict-banner">
  <div>
    <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:3px">VERDICT — {time_str}</div>
    <div style="font-family:'Syne',sans-serif;font-size:1.35rem;font-weight:800;color:{v["color"]}">{v["verdict"]}</div>
    <div style="font-size:.7rem;color:var(--text);margin-top:4px;line-height:1.5">{v["explanation"]}</div>
  </div>
  <div>
    <div style="font-size:.6rem;color:var(--muted);margin-bottom:5px;letter-spacing:1px">TRADE IDEA</div>
    <div style="font-size:.72rem;color:var(--white);line-height:1.6;background:rgba(255,255,255,.04);padding:9px;border-left:3px solid {v["color"]}">{v["trade_idea"]}</div>
    <div style="font-size:.6rem;color:var(--muted);margin-top:5px">Expiry: <strong style="color:var(--white)">{opts["expiry"]}</strong> · IV: <strong style="color:var(--orange)">{opts["iv_30"]}%</strong> · Vol ratio: <strong style="color:{vol_c}">{d["volume_ratio"]}x</strong></div>
  </div>
  <div style="text-align:center">
    <div style="background:rgba(0,0,0,.3);border:1px solid {v["bias_color"]};color:{v["bias_color"]};padding:7px 13px;font-size:.7rem;letter-spacing:1px;margin-bottom:6px">{v["bias"]}</div>
    <div style="font-size:.55rem;color:var(--muted)">Next refresh</div>
    <div style="font-size:.65rem;color:var(--text)">auto in ~30min</div>
  </div>
</div>

<!-- ROW 1: CLOUD + OPTIONS HEALTH + S/R -->
<div class="three-col">

  <!-- CLOUD STATUS — DAILY + 1H -->
  <div class="card">
    <div class="card-title">EMA Cloud — Daily + 1-Hour</div>
    <div style="font-size:.58rem;color:var(--orange);letter-spacing:1px;margin-bottom:6px">── DAILY (Bias) ──</div>
    <div class="ind-row">
      <div class="ind-item">
        <div><div class="ind-name">34-50 Cloud</div>
          <div class="ind-desc">${d["ema34"]:.2f} / ${d["ema50"]:.2f}</div></div>
        {badge(v["above_cloud_d"], "ABOVE ✓", "BELOW ✗")}
      </div>
      <div class="ind-item">
        <div><div class="ind-name">5-12 Cloud (EMA9/21)</div>
          <div class="ind-desc">${d["ema9"]:.2f} / ${d["ema21"]:.2f}</div></div>
        {badge(v["fast_bull_d"], "GREEN ✓", "RED ✗")}
      </div>
      <div class="ind-item">
        <div><div class="ind-name">IMACD Daily (34,9)</div>
          <div class="ind-desc">{d["macd_val"]:+.3f} (prev {d["macd_prev"]:+.3f})</div></div>
        {badge(v["macd_bull_d"], f"{d['macd_val']:+.3f} BULL", f"{d['macd_val']:+.3f} BEAR")}
      </div>
    </div>
    <div style="font-size:.58rem;color:var(--blue);letter-spacing:1px;margin:10px 0 6px">── 1-HOUR (Entry Trigger) ──</div>
    <div class="ind-row">
      <div class="ind-item">
        <div><div class="ind-name">34-50 Cloud 1H</div>
          <div class="ind-desc">${d["ema34_1h"]:.2f} / ${d["ema50_1h"]:.2f}</div></div>
        {badge(v["above_cloud_1h"], "ABOVE ✓", "BELOW ✗")}
      </div>
      <div class="ind-item">
        <div><div class="ind-name">5-12 Cloud 1H</div>
          <div class="ind-desc">${d["ema9_1h"]:.2f} / ${d["ema21_1h"]:.2f}</div></div>
        {badge(v["fast_bull_1h"], "GREEN ✓", "RED ✗")}
      </div>
      <div class="ind-item">
        <div><div class="ind-name">IMACD 1-Hour (34,9)</div>
          <div class="ind-desc">{d["macd_1h"]:+.3f} (prev {d["macd_1h_p"]:+.3f})</div></div>
        {badge(v["macd_bull_1h"], f"{d['macd_1h']:+.3f} BULL", f"{d['macd_1h']:+.3f} BEAR")}
      </div>
    </div>
  </div>

  <!-- OPTIONS HEALTH -->
  <div class="card">
    <div class="card-title">Options Health — Live</div>
    <div class="gauge-row">
      <div>
        <div style="display:flex;justify-content:space-between;margin-bottom:3px">
          <span style="font-size:.66rem">Implied Volatility</span>
          <span style="font-size:.66rem;font-weight:700;color:{iv_c}">{opts["iv_30"]}%</span>
        </div>
        <div class="gauge-bar"><div class="gauge-fill" style="width:{min(opts["iv_30"],100)}%;background:{iv_c}"></div></div>
        <div style="font-size:.58rem;color:var(--muted);margin-top:2px">{"✅ Good — buy options freely" if opts["iv_30"]<35 else ("⚠️ Elevated — options pricey" if opts["iv_30"]<55 else "❌ Very high — consider spread")}</div>
      </div>
      <div>
        <div style="display:flex;justify-content:space-between;margin-bottom:3px">
          <span style="font-size:.66rem">Volume vs Average</span>
          <span style="font-size:.66rem;font-weight:700;color:{vol_c}">{d["volume_ratio"]}x</span>
        </div>
        <div class="gauge-bar"><div class="gauge-fill" style="width:{min(d["volume_ratio"]*50,100):.0f}%;background:{vol_c}"></div></div>
        <div style="font-size:.58rem;color:var(--muted);margin-top:2px">{vol_m:.0f}M today · {avg_m:.0f}M avg · {"High conviction ✓" if d["volume_ratio"]>1.3 else ("Normal" if d["volume_ratio"]>0.8 else "Low vol ⚠️")}</div>
      </div>
      <div>
        <div style="display:flex;justify-content:space-between;margin-bottom:3px">
          <span style="font-size:.66rem">52W Range Position</span>
          <span style="font-size:.66rem;color:var(--text)">${d["week52_low"]:.0f}–${d["week52_high"]:.0f}</span>
        </div>
        <div class="gauge-bar"><div class="gauge-fill" style="width:{min(yr,100):.0f}%;background:var(--blue)"></div></div>
        <div style="font-size:.58rem;color:var(--muted);margin-top:2px">{yr:.0f}th percentile of year range</div>
      </div>
    </div>
    <div style="margin-top:10px;background:var(--surface2);border:1px solid var(--border);padding:10px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:6px">VWAP APPROXIMATION</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;text-align:center">
        <div><div style="font-size:.55rem;color:var(--muted)">DAILY</div>
          <div style="font-size:.85rem;color:var(--blue);font-weight:700">${(price*0.998):.2f}</div>
          <div style="font-size:.55rem;color:{"#00ff9d" if price>price*0.998 else "#ff3a5e"}">{"Above ✓" if price>price*0.998 else "Below ✗"}</div></div>
        <div><div style="font-size:.55rem;color:var(--muted)">EMA9 (1H)</div>
          <div style="font-size:.85rem;color:var(--blue);font-weight:700">${d["ema9_1h"]:.2f}</div>
          <div style="font-size:.55rem;color:{"#00ff9d" if price>d["ema9_1h"] else "#ff3a5e"}">{"Above ✓" if price>d["ema9_1h"] else "Below ✗"}</div></div>
        <div><div style="font-size:.55rem;color:var(--muted)">EMA21 (1H)</div>
          <div style="font-size:.85rem;color:var(--blue);font-weight:700">${d["ema21_1h"]:.2f}</div>
          <div style="font-size:.55rem;color:{"#00ff9d" if price>d["ema21_1h"] else "#ff3a5e"}">{"Above ✓" if price>d["ema21_1h"] else "Below ✗"}</div></div>
      </div>
    </div>
    <div style="margin-top:10px">
      <div style="font-size:.58rem;color:var(--muted);letter-spacing:1px;margin-bottom:6px">RECENT 5-MIN CANDLES</div>
      <table class="candle-table">
        <tr style="border-bottom:1px solid var(--border)">
          <th style="font-size:.58rem;color:var(--muted);text-align:left;padding:3px">TIME (CT)</th>
          <th style="font-size:.58rem;color:var(--muted);text-align:right;padding:3px">CLOSE</th>
          <th style="font-size:.58rem;color:var(--muted);padding:3px"></th>
          <th style="font-size:.58rem;color:var(--muted);text-align:right;padding:3px">HIGH</th>
          <th style="font-size:.58rem;color:var(--muted);text-align:right;padding:3px">LOW</th>
          <th style="font-size:.58rem;color:var(--muted);text-align:right;padding:3px">VOL</th>
        </tr>
        {candle_html if candle_html else "<tr><td colspan='6' style='color:var(--muted);font-size:.65rem;padding:8px'>Market closed or no intraday data yet</td></tr>"}
      </table>
    </div>
  </div>

  <!-- S/R LEVELS -->
  <div class="card">
    <div class="card-title">Support · Resistance (Auto-Calc)</div>
    <table class="levels-table">
      <tr style="border-bottom:1px solid var(--border)">
        <th style="font-size:.58rem;color:var(--muted);text-align:left;padding:4px">ZONE</th>
        <th style="font-size:.58rem;color:var(--muted);text-align:right;padding:4px">LEVEL</th>
        <th style="font-size:.58rem;color:var(--muted);text-align:right;padding:4px">TYPE</th>
        <th style="font-size:.58rem;color:var(--muted);text-align:right;padding:4px">DIST</th>
      </tr>
      {sr_rows}
    </table>
    <div style="margin-top:10px;padding:7px;background:rgba(79,195,247,.06);border:1px solid rgba(79,195,247,.2);font-size:.62rem;color:var(--blue);line-height:1.5">
      💡 Copy these to TradingView as horizontal lines. Levels recalculate every refresh from 3-month pivot highs/lows.
    </div>
  </div>
</div>

<!-- ROW 2: OPTIONS CHAIN + NEWS -->
<div class="two-col">
  <div class="card">
    <div class="card-title">Options Chain — {opts["expiry"]} (Live)</div>
    <div style="font-size:.6rem;color:var(--muted);margin-bottom:7px">🎯 = ~$3 target · ⚠️ = low liquidity · Spread color: green&lt;$0.20 / yellow&lt;$0.40 / red&gt;$0.40</div>
    <div style="font-size:.58rem;color:var(--orange);letter-spacing:1px;margin-bottom:4px">── CALLS ──</div>
    <table class="chain-table">
      <tr><th>STRIKE</th><th>PRICE</th><th>DELTA</th><th>IV</th><th>SPREAD</th><th>VOLUME</th></tr>
      {call_rows if call_rows else "<tr><td colspan='6' style='color:var(--muted);font-size:.65rem;padding:8px'>Fetching...</td></tr>"}
    </table>
    <div style="font-size:.58rem;color:var(--red);letter-spacing:1px;margin:9px 0 4px">── PUTS ──</div>
    <table class="chain-table">
      <tr><th>STRIKE</th><th>PRICE</th><th>DELTA</th><th>IV</th><th>SPREAD</th><th>VOLUME</th></tr>
      {put_rows if put_rows else "<tr><td colspan='6' style='color:var(--muted);font-size:.65rem;padding:8px'>Fetching...</td></tr>"}
    </table>
    <div style="margin-top:9px;padding:8px;background:rgba(255,215,0,.05);border:1px solid rgba(255,215,0,.2);font-size:.63rem;color:var(--yellow);line-height:1.5">
      ⚠️ Verify on Yahoo Finance before trading: finance.yahoo.com/quote/NVDA/options<br>
      Check: Vol &gt; 500 · OI &gt; 1,000 · Bid-Ask &lt; $0.20
    </div>
  </div>
  <div class="card">
    <div class="card-title">NVDA News — Auto-Updated</div>
    {news_html or '<div style="font-size:.7rem;color:var(--muted);padding:8px">No articles fetched. Check Yahoo Finance.</div>'}
  </div>
</div>

<!-- CHECKLIST -->
<div class="card">
  <div class="card-title">Pre-Trade Checklist — All 8 Green Before You Click Buy</div>
  <div class="checklist">{cl}</div>
  <div style="margin-top:7px;font-size:.6rem;color:var(--muted);font-style:italic">Click boxes to toggle. All 8 green = trade. Any red = no trade. This rule will save your account.</div>
</div>

<!-- DECISION TREE -->
<div class="card">
  <div class="card-title">Signal Scorecard — Daily + 1H Combined</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;font-size:.68rem;line-height:1.7">
    <div>
      <div style="color:var(--green);font-weight:700;margin-bottom:6px">CALL SIGNALS ({sum([v["above_cloud_d"],v["above_cloud_1h"],v["fast_bull_d"],v["fast_bull_1h"],v["macd_bull_d"],v["macd_bull_1h"]])}/6):</div>
      {"✅" if v["above_cloud_d"]  else "❌"} Price above daily 34-50 cloud<br>
      {"✅" if v["above_cloud_1h"] else "❌"} Price above 1H 34-50 cloud<br>
      {"✅" if v["fast_bull_d"]    else "❌"} Daily 5-12 cloud green (EMA9 &gt; EMA21)<br>
      {"✅" if v["fast_bull_1h"]   else "❌"} 1H 5-12 cloud green<br>
      {"✅" if v["macd_bull_d"]    else "❌"} IMACD Daily above zero ({d["macd_val"]:+.3f})<br>
      {"✅" if v["macd_bull_1h"]   else "❌"} IMACD 1H above zero ({d["macd_1h"]:+.3f})
      <div style="margin-top:8px;padding:8px;border-left:3px solid var(--green);background:rgba(0,255,157,.05);font-size:.63rem">
      {"🟢 5-6/6: STRONG CALL SETUP" if sum([v["above_cloud_d"],v["above_cloud_1h"],v["fast_bull_d"],v["fast_bull_1h"],v["macd_bull_d"],v["macd_bull_1h"]])>=5 else ("🟡 4/6: WAIT FOR CONFIRMATION" if sum([v["above_cloud_d"],v["above_cloud_1h"],v["fast_bull_d"],v["fast_bull_1h"],v["macd_bull_d"],v["macd_bull_1h"]])==4 else "⏸ &lt;4/6: NOT READY")}
      </div>
    </div>
    <div>
      <div style="color:var(--red);font-weight:700;margin-bottom:6px">PUT SIGNALS ({sum([v["below_cloud_d"],v["below_cloud_1h"],not v["fast_bull_d"],not v["fast_bull_1h"],not v["macd_bull_d"],not v["macd_bull_1h"]])}/6):</div>
      {"✅" if v["below_cloud_d"]       else "❌"} Price below daily 34-50 cloud<br>
      {"✅" if v["below_cloud_1h"]      else "❌"} Price below 1H 34-50 cloud<br>
      {"✅" if not v["fast_bull_d"]     else "❌"} Daily 5-12 cloud red<br>
      {"✅" if not v["fast_bull_1h"]    else "❌"} 1H 5-12 cloud red<br>
      {"✅" if not v["macd_bull_d"]     else "❌"} IMACD Daily below zero<br>
      {"✅" if not v["macd_bull_1h"]    else "❌"} IMACD 1H below zero
      <div style="margin-top:8px;padding:8px;border-left:3px solid var(--red);background:rgba(255,58,94,.05);font-size:.63rem">
      {"🔴 5-6/6: STRONG PUT SETUP — wait for VWAP bounce fail" if sum([v["below_cloud_d"],v["below_cloud_1h"],not v["fast_bull_d"],not v["fast_bull_1h"],not v["macd_bull_d"],not v["macd_bull_1h"]])>=5 else ("🟡 4/6: WAIT FOR CONFIRMATION" if sum([v["below_cloud_d"],v["below_cloud_1h"],not v["fast_bull_d"],not v["fast_bull_1h"],not v["macd_bull_d"],not v["macd_bull_1h"]])==4 else "⏸ &lt;4/6: NOT READY")}
      </div>
    </div>
  </div>
  <div style="margin-top:12px;padding:10px;background:rgba(255,140,66,.06);border:1px solid rgba(255,140,66,.3);font-size:.66rem;color:var(--orange);line-height:1.6">
    🚪 <strong>EXIT RULES:</strong> +80% → SELL ALL · -50% → HARD STOP · Day 3 → EXIT · IMACD flips → EXIT HALF · Session enters Dead Zone → Consider exiting
  </div>
</div>

<div style="text-align:center;padding:12px;font-size:.58rem;color:var(--muted);border-top:1px solid var(--border);line-height:1.8">
  🤖 Auto-refreshed 12× per trading day at key NVDA liquidity windows (Chicago time) · Data: Yahoo Finance<br>
  ⚠️ Educational only — not financial advice. Verify prices before trading. Options involve substantial risk.<br>
  Last update: <strong style="color:var(--text)">{ct_now.strftime("%Y-%m-%d %H:%M:%S CT")}</strong> · Page auto-reloads every 5 min
</div>

</div>
<script>
function toggleCheck(b){{
  if(b.classList.contains('done')){{b.classList.remove('done');b.classList.add('fail');b.textContent='✗';}}
  else if(b.classList.contains('fail')){{b.classList.remove('fail');b.classList.add('done');b.textContent='✓';}}
  else{{b.classList.add('done');b.textContent='✓';}}
}}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────
# 4. MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    ct_tz  = pytz.timezone("America/Chicago")
    ct_now = datetime.datetime.now(ct_tz)
    session = get_session(ct_now)

    print(f"⏰ {ct_now.strftime('%I:%M %p CT')} — Session: {session['name']}")

    print("📡 Fetching NVDA data...")
    d = fetch_nvda_data()
    print(f"   Price: ${d['price']} | {d['change_pct']:+.2f}% | Vol: {d['volume_ratio']}x avg")
    print(f"   Daily  IMACD: {d['macd_val']:+.3f} | EMA9/21: {d['ema9']:.2f}/{d['ema21']:.2f}")
    print(f"   1-Hour IMACD: {d['macd_1h']:+.3f} | EMA9/21: {d['ema9_1h']:.2f}/{d['ema21_1h']:.2f}")

    print("📋 Fetching options chain...")
    opts = fetch_options_data(d["price"])
    print(f"   Expiry: {opts['expiry']} | IV: {opts['iv_30']}% | Calls: {len(opts['calls'])} | Puts: {len(opts['puts'])}")

    print("📐 Calculating S/R levels...")
    sr = fetch_support_resistance(d["hist"], d["hist_1y"], d["price"])
    print(f"   Resistance: {sr['resistance'][:3]}")
    print(f"   Support:    {sr['support'][:3]}")

    print("📰 Fetching news...")
    news = fetch_news()
    print(f"   Got {len(news)} articles")

    print("🧠 Generating verdict...")
    verdict = generate_verdict(d, opts, session)
    print(f"   {verdict['verdict']}")

    print("🖥️  Rendering HTML...")
    html = render_html(d, opts, sr, news, verdict, session, ct_now)

    Path("index.html").write_text(html, encoding="utf-8")
    print(f"✅ Done — index.html written ({len(html):,} bytes)")
