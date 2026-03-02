"""
NVDA Options Command Center — Daily Auto-Updater
Fetches live data from Yahoo Finance and generates index.html
Runs every morning at 8am ET via GitHub Actions
"""

import yfinance as yf
import json
import datetime
import pytz
import feedparser
import numpy as np
from pathlib import Path

# ─────────────────────────────────────────────
# 1. FETCH LIVE DATA
# ─────────────────────────────────────────────

def fetch_nvda_data():
    ticker = yf.Ticker("NVDA")
    
    # Price info
    info = ticker.info
    hist = ticker.history(period="3mo", interval="1d")
    hist_1y = ticker.history(period="1y", interval="1d")
    
    price = info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1]
    prev_close = info.get("previousClose") or hist["Close"].iloc[-2]
    change = price - prev_close
    change_pct = (change / prev_close) * 100
    volume = info.get("regularMarketVolume") or hist["Volume"].iloc[-1]
    avg_volume = info.get("averageVolume") or hist["Volume"].mean()
    
    # 52-week range
    week52_high = info.get("fiftyTwoWeekHigh") or hist_1y["High"].max()
    week52_low = info.get("fiftyTwoWeekLow") or hist_1y["Low"].min()
    
    # Moving averages (EMA)
    closes = hist["Close"]
    ema9  = closes.ewm(span=9,  adjust=False).mean().iloc[-1]
    ema21 = closes.ewm(span=21, adjust=False).mean().iloc[-1]
    ema34 = closes.ewm(span=34, adjust=False).mean().iloc[-1]
    ema50 = closes.ewm(span=50, adjust=False).mean().iloc[-1]
    
    # IMACD approximation (34,9)
    ema34_series = closes.ewm(span=34, adjust=False).mean()
    signal_series = ema34_series.ewm(span=9, adjust=False).mean()
    macd_val = ema34_series.iloc[-1] - signal_series.iloc[-1]
    macd_prev = ema34_series.iloc[-2] - signal_series.iloc[-2]
    
    return {
        "price": round(price, 2),
        "prev_close": round(prev_close, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "volume": int(volume),
        "avg_volume": int(avg_volume),
        "volume_ratio": round(volume / avg_volume, 2),
        "week52_high": round(week52_high, 2),
        "week52_low": round(week52_low, 2),
        "ema9":  round(ema9,  2),
        "ema21": round(ema21, 2),
        "ema34": round(ema34, 2),
        "ema50": round(ema50, 2),
        "macd_val": round(macd_val, 3),
        "macd_prev": round(macd_prev, 3),
        "hist": hist,
        "hist_1y": hist_1y,
    }


def fetch_options_data(price):
    ticker = yf.Ticker("NVDA")
    
    # Get nearest expiry ~25-35 DTE
    expiries = ticker.options
    et = pytz.timezone("America/New_York")
    today = datetime.datetime.now(et).date()
    
    target = today + datetime.timedelta(days=30)
    chosen_exp = None
    for exp in expiries:
        exp_date = datetime.datetime.strptime(exp, "%Y-%m-%d").date()
        if exp_date >= target:
            chosen_exp = exp
            break
    if not chosen_exp and expiries:
        chosen_exp = expiries[-1]
    
    chain = ticker.option_chain(chosen_exp) if chosen_exp else None
    
    calls_data = []
    puts_data  = []
    iv_30 = 0.50  # fallback
    
    if chain:
        calls = chain.calls
        puts  = chain.puts
        
        # Find strikes near ATM ($3 target)
        for _, row in calls.iterrows():
            strike = row["strike"]
            if abs(strike - price) <= 20:
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
            if abs(strike - price) <= 15 and strike < price:
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
        
        # IV estimate from ATM call
        atm_calls = calls[abs(calls["strike"] - price) < 5]
        if not atm_calls.empty:
            iv_30 = float(atm_calls.iloc[0].get("impliedVolatility", 0.50) or 0.50)
    
    # Sort — calls ascending strike, puts descending
    calls_data.sort(key=lambda x: x["strike"])
    puts_data.sort(key=lambda x: x["strike"], reverse=True)
    
    return {
        "expiry": chosen_exp or "N/A",
        "calls":  calls_data[:6],
        "puts":   puts_data[:4],
        "iv_30":  round(iv_30 * 100, 1),
    }


def fetch_support_resistance(hist, hist_1y, price):
    """Calculate S/R from pivot highs/lows over recent history."""
    
    closes_1y = hist_1y["Close"].values
    highs_1y  = hist_1y["High"].values
    lows_1y   = hist_1y["Low"].values
    
    week52_high = float(np.max(highs_1y))
    week52_low  = float(np.min(lows_1y))
    
    # Recent 3-month S/R
    closes_3m = hist["Close"].values
    highs_3m  = hist["High"].values
    lows_3m   = hist["Low"].values
    
    # Find local pivot highs/lows (window=5)
    def find_pivots(data, window=5, mode="high"):
        pivots = []
        for i in range(window, len(data) - window):
            segment = data[i-window:i+window+1]
            if mode == "high" and data[i] == max(segment):
                pivots.append(round(float(data[i]), 2))
            elif mode == "low" and data[i] == min(segment):
                pivots.append(round(float(data[i]), 2))
        return pivots
    
    pivot_highs = find_pivots(highs_3m, mode="high")
    pivot_lows  = find_pivots(lows_3m,  mode="low")
    
    # Cluster nearby levels (within $3)
    def cluster(levels, threshold=3.0):
        if not levels:
            return []
        levels = sorted(set(levels))
        clustered = []
        group = [levels[0]]
        for l in levels[1:]:
            if l - group[-1] <= threshold:
                group.append(l)
            else:
                clustered.append(round(sum(group)/len(group), 2))
                group = [l]
        clustered.append(round(sum(group)/len(group), 2))
        return clustered
    
    resistance_levels = sorted([r for r in cluster(pivot_highs) if r > price], reverse=True)[:5]
    support_levels    = sorted([s for s in cluster(pivot_lows)  if s < price])[:5]
    
    # Always include 52-week high/low
    if week52_high not in resistance_levels:
        resistance_levels.append(round(week52_high, 2))
    if week52_low not in support_levels:
        support_levels.append(round(week52_low, 2))
    
    return {
        "resistance": sorted(resistance_levels, reverse=True)[:6],
        "support":    sorted(support_levels, reverse=True)[:6],
        "week52_high": round(week52_high, 2),
        "week52_low":  round(week52_low,  2),
    }


def fetch_news():
    """Pull NVDA news from Yahoo Finance RSS."""
    feeds = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US",
        "https://finance.yahoo.com/rss/headline?s=NVDA",
    ]
    
    articles = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                published = entry.get("published", "")
                link = entry.get("link", "#")
                
                # Simple sentiment
                bull_words = ["beat", "surge", "rally", "upgrade", "buy", "growth", "record", "strong", "profit", "bullish", "target", "raise"]
                bear_words = ["miss", "drop", "fall", "downgrade", "sell", "cut", "loss", "bearish", "concern", "risk", "decline", "weak"]
                
                text = (title + " " + summary).lower()
                bull_score = sum(1 for w in bull_words if w in text)
                bear_score = sum(1 for w in bear_words if w in text)
                
                if bull_score > bear_score:
                    sentiment = "bull"
                elif bear_score > bull_score:
                    sentiment = "bear"
                else:
                    sentiment = "neut"
                
                articles.append({
                    "title": title[:120],
                    "published": published[:30] if published else "",
                    "link": link,
                    "sentiment": sentiment,
                })
            if articles:
                break
        except Exception:
            continue
    
    return articles[:7]


# ─────────────────────────────────────────────
# 2. GENERATE DAILY VERDICT
# ─────────────────────────────────────────────

def generate_verdict(d, opts):
    price  = d["price"]
    ema34  = d["ema34"]
    ema50  = d["ema50"]
    ema9   = d["ema9"]
    ema21  = d["ema21"]
    macd   = d["macd_val"]
    chg    = d["change_pct"]
    vol_r  = d["volume_ratio"]
    
    above_cloud  = price > max(ema34, ema50)
    below_cloud  = price < min(ema34, ema50)
    inside_cloud = not above_cloud and not below_cloud
    fast_bull    = ema9 > ema21
    macd_bull    = macd > 0
    macd_bear    = macd < 0
    
    # Best call/put strike near $3
    call_target = None
    for c in opts.get("calls", []):
        if 2.50 <= c["price"] <= 4.50:
            call_target = c
            break
    
    put_target = None
    for p in opts.get("puts", []):
        if 2.50 <= p["price"] <= 4.50:
            put_target = p
            break
    
    if above_cloud and fast_bull and macd_bull:
        verdict = "✅ CALL WATCH — Setup Building"
        color = "#00ff9d"
        border_color = "#00ff9d"
        bias = "BULLISH"
        bias_color = "#00ff9d"
        explanation = f"Price above 34-50 cloud. Fast EMA bullish. IMACD positive ({d['macd_val']:+.2f}). Look for pullback to 5-12 cloud as entry."
        trade_idea = f"Buy ${call_target['strike']:.0f}C {opts['expiry']} (~${call_target['price']:.2f}). Target: +80%. Stop: -50%." if call_target else "Check options chain for ATM call ~$3.00."
    elif above_cloud and (not fast_bull or not macd_bull):
        verdict = "⏸ CALL SETUP — Needs Confirmation"
        color = "#ffd700"
        border_color = "#ffd700"
        bias = "CAUTIOUS BULL"
        bias_color = "#ffd700"
        explanation = f"Price above cloud but momentum not fully aligned. IMACD: {d['macd_val']:+.2f}. Wait for IMACD to confirm above zero."
        trade_idea = "Wait for IMACD to cross above zero AND 5-12 cloud to turn green before entering call."
    elif inside_cloud:
        verdict = "⏸ CHOP ZONE — DO NOT TRADE"
        color = "#ff8c42"
        border_color = "#ff8c42"
        bias = "NEUTRAL / CHOP"
        bias_color = "#ff8c42"
        explanation = f"Price is INSIDE the 34-50 EMA cloud (${ema50:.2f}–${ema34:.2f}). This is the chop zone. Theta bleeds options here. No trade."
        trade_idea = "Sit on hands. Wait for price to break clearly above or below the cloud with volume confirmation."
    elif below_cloud and (not fast_bull) and macd_bear:
        verdict = "🔴 PUT WATCH — Bearish Setup"
        color = "#ff3a5e"
        border_color = "#ff3a5e"
        bias = "BEARISH"
        bias_color = "#ff3a5e"
        explanation = f"Price below 34-50 cloud. Fast EMA bearish. IMACD negative ({d['macd_val']:+.2f}). Watch for bounce failure at VWAP."
        trade_idea = f"Buy ${put_target['strike']:.0f}P {opts['expiry']} (~${put_target['price']:.2f}) on bounce fail at cloud underside. Stop: -50%." if put_target else "Check options chain for OTM put ~$3.00."
    else:
        verdict = "⏸ WAIT — Mixed Signals"
        color = "#ff8c42"
        border_color = "#ff8c42"
        bias = "MIXED"
        bias_color = "#ff8c42"
        explanation = f"Signals not fully aligned. IMACD: {d['macd_val']:+.2f}. Price vs EMA50: ${ema50:.2f}. Patience is the edge."
        trade_idea = "No clear setup today. Check back at market open for confirmation."
    
    return {
        "verdict": verdict,
        "color": color,
        "border_color": border_color,
        "bias": bias,
        "bias_color": bias_color,
        "explanation": explanation,
        "trade_idea": trade_idea,
        "above_cloud": above_cloud,
        "below_cloud": below_cloud,
        "inside_cloud": inside_cloud,
        "fast_bull": fast_bull,
        "macd_bull": macd_bull,
        "macd_bear": macd_bear,
    }


# ─────────────────────────────────────────────
# 3. RENDER HTML
# ─────────────────────────────────────────────

def render_html(d, opts, sr, news, verdict):
    et = pytz.timezone("America/New_York")
    now = datetime.datetime.now(et)
    date_str = now.strftime("%A, %B %d · %Y")
    time_str = now.strftime("%I:%M %p ET")
    
    price = d["price"]
    chg   = d["change"]
    chg_p = d["change_pct"]
    chg_color = "#00ff9d" if chg >= 0 else "#ff3a5e"
    chg_arrow = "▲" if chg >= 0 else "▼"
    
    vol_m = d["volume"] / 1_000_000
    avg_m = d["avg_volume"] / 1_000_000
    vol_color = "#00ff9d" if d["volume_ratio"] > 1.2 else ("#ff8c42" if d["volume_ratio"] > 0.8 else "#ff3a5e")
    
    # ── Cloud status badges ──
    def cloud_badge(condition_bull, condition_bear, label_bull, label_bear, label_neut):
        if condition_bull:
            return f'<div class="ind-badge bull">{label_bull}</div>'
        elif condition_bear:
            return f'<div class="ind-badge bear">{label_bear}</div>'
        else:
            return f'<div class="ind-badge wait">{label_neut}</div>'
    
    cloud_34_50 = cloud_badge(d["price"] > max(d["ema34"], d["ema50"]),
                               d["price"] < min(d["ema34"], d["ema50"]),
                               "ABOVE ✓", "BELOW ✗", "INSIDE ⚠")
    cloud_5_12  = cloud_badge(d["ema9"] > d["ema21"], d["ema9"] < d["ema21"],
                               "GREEN ✓", "RED ✗", "FLAT ⚠")
    macd_badge  = cloud_badge(d["macd_val"] > 0, d["macd_val"] < 0,
                               f"+{d['macd_val']:.2f} BULL", f"{d['macd_val']:.2f} BEAR", "FLAT")
    macd_cross  = "CROSSED ↑" if d["macd_val"] > 0 > d["macd_prev"] else \
                  "CROSSED ↓" if d["macd_val"] < 0 < d["macd_prev"] else "NO CROSS"
    macd_cross_color = "#00ff9d" if "↑" in macd_cross else ("#ff3a5e" if "↓" in macd_cross else "#5a7a99")
    
    # ── S/R levels ──
    sr_rows = ""
    for r in sr["resistance"][:4]:
        tag = "KEY RES ★" if r == sr["week52_high"] else "RESISTANCE"
        color = "#ff8c42" if r == sr["week52_high"] else "#ff3a5e"
        sr_rows += f'<tr><td>RESISTANCE</td><td>${r:.2f}</td><td style="color:{color}">■ {tag}</td></tr>'
    sr_rows += f'<tr><td>──</td><td style="color:#ffd700">▶ ${price:.2f}</td><td style="color:#ffd700">◆ CURRENT</td></tr>'
    for s in sr["support"][:4]:
        tag = "KEY SUP ★" if s == sr["week52_low"] else "SUPPORT"
        color = "#ff8c42" if s == sr["week52_low"] else "#00ff9d"
        sr_rows += f'<tr><td>SUPPORT</td><td>${s:.2f}</td><td style="color:{color}">■ {tag}</td></tr>'
    
    # ── Options chain ──
    call_rows = ""
    for c in opts["calls"]:
        atm_class = ' class="strike-atm"' if abs(c["strike"] - price) < 4 else ""
        liq_warn = "" if c["volume"] > 200 and c["oi"] > 500 else " ⚠️"
        target = "🎯 " if 2.50 <= c["price"] <= 4.00 else ""
        spread = round(c["ask"] - c["bid"], 2)
        spread_color = "#00ff9d" if spread < 0.20 else ("#ffd700" if spread < 0.40 else "#ff3a5e")
        call_rows += f'''<tr{atm_class}>
          <td>${c["strike"]:.0f}C {target}</td>
          <td class="price-val">${c["price"]:.2f}</td>
          <td class="delta-val">{c["delta"] if c["delta"] else "—"}</td>
          <td class="iv-val">{c["iv"]}%</td>
          <td style="color:{spread_color}">${spread:.2f}</td>
          <td class="vol-val">{c["volume"]:,}{liq_warn}</td>
        </tr>'''
    
    put_rows = ""
    for p in opts["puts"]:
        liq_warn = "" if p["volume"] > 200 and p["oi"] > 500 else " ⚠️"
        target = "🎯 " if 2.50 <= p["price"] <= 4.00 else ""
        spread = round(p["ask"] - p["bid"], 2)
        spread_color = "#00ff9d" if spread < 0.20 else ("#ffd700" if spread < 0.40 else "#ff3a5e")
        put_rows += f'''<tr>
          <td>${p["strike"]:.0f}P {target}</td>
          <td class="price-val">${p["price"]:.2f}</td>
          <td class="delta-val">{p["delta"] if p["delta"] else "—"}</td>
          <td class="iv-val">{p["iv"]}%</td>
          <td style="color:{spread_color}">${spread:.2f}</td>
          <td class="vol-val">{p["volume"]:,}{liq_warn}</td>
        </tr>'''
    
    # ── News ──
    news_html = ""
    for n in news:
        dot_color = "#00ff9d" if n["sentiment"] == "bull" else ("#ff3a5e" if n["sentiment"] == "bear" else "#ffd700")
        impact_label = "BULLISH" if n["sentiment"] == "bull" else ("BEARISH" if n["sentiment"] == "bear" else "NEUTRAL")
        impact_color = dot_color
        news_html += f'''<div class="news-item">
          <div class="news-dot" style="background:{dot_color}"></div>
          <div>
            <div class="news-text"><a href="{n["link"]}" target="_blank" style="color:inherit;text-decoration:none">{n["title"]}</a>
              <span class="news-impact" style="color:{impact_color}">[{impact_label}]</span></div>
            <div class="news-source">{n["published"]}</div>
          </div>
        </div>'''
    
    # ── Checklist items ──
    def check(condition, text, good_label="✓", bad_label="✗"):
        cls = "done" if condition else "fail"
        icon = "✓" if condition else "✗"
        result_color = "#00ff9d" if condition else "#ff3a5e"
        result_text = good_label if condition else bad_label
        return f'''<div class="check-item">
          <div class="check-box {cls}" onclick="this.classList.toggle('done');this.classList.toggle('fail')">{icon}</div>
          <div class="check-text">{text}</div>
          <div class="check-result" style="color:{result_color}">{result_text}</div>
        </div>'''
    
    checklist_html = (
        check(True, "Expiration ≥ 20 DTE", opts["expiry"], "Check expiry") +
        check(any(2.50 <= c["price"] <= 4.50 for c in opts["calls"]), "Call near $3.00 exists in chain", "EXISTS", "NOT FOUND") +
        check(opts["iv_30"] < 50, f"IV below 50% (current: {opts['iv_30']}%)", f"{opts['iv_30']}% OK", f"{opts['iv_30']}% HIGH") +
        check(verdict["macd_bull"] and not verdict["inside_cloud"], "IMACD above zero (calls) or below zero (puts)", "CONFIRMED", "NOT YET") +
        check(verdict["fast_bull"] and not verdict["inside_cloud"], "5-12 Ripster cloud matches direction", "ALIGNED", "MISALIGNED") +
        check(d["volume_ratio"] > 0.9, f"Volume ratio: {d['volume_ratio']}x average", "LIQUID", "LOW VOL") +
        check(True, "Risk ≤ $300 (1 contract max)", "YOUR LIMIT", "ADJUST") +
        check(True, "Written entry price + stop before clicking", "WRITE IT", "WRITE IT")
    )
    
    # ── IV bar fill ──
    iv_fill = min(opts["iv_30"], 100)
    iv_color = "#00ff9d" if iv_fill < 30 else ("#ffd700" if iv_fill < 50 else "#ff3a5e")
    
    # ── Volume % of avg ──
    vol_fill = min(d["volume_ratio"] * 50, 100)
    
    # ── EMA values display ──
    ema_rows = f"""
      <tr><td>EMA 9</td><td style="color:#4fc3f7">${d['ema9']:.2f}</td><td style="color:{'#00ff9d' if price > d['ema9'] else '#ff3a5e'}">{'Above ✓' if price > d['ema9'] else 'Below ✗'}</td></tr>
      <tr><td>EMA 21</td><td style="color:#4fc3f7">${d['ema21']:.2f}</td><td style="color:{'#00ff9d' if price > d['ema21'] else '#ff3a5e'}">{'Above ✓' if price > d['ema21'] else 'Below ✗'}</td></tr>
      <tr><td>EMA 34</td><td style="color:#4fc3f7">${d['ema34']:.2f}</td><td style="color:{'#00ff9d' if price > d['ema34'] else '#ff3a5e'}">{'Above ✓' if price > d['ema34'] else 'Below ✗'}</td></tr>
      <tr><td>EMA 50</td><td style="color:#4fc3f7">${d['ema50']:.2f}</td><td style="color:{'#00ff9d' if price > d['ema50'] else '#ff3a5e'}">{'Above ✓' if price > d['ema50'] else 'Below ✗'}</td></tr>
    """
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Research Notes — NVDA</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:#070b12;--surface:#0d1520;--surface2:#111d2e;--border:#1e3a5f;
    --green:#00ff9d;--green-dim:#00c87a;--red:#ff3a5e;--red-dim:#cc1f40;
    --yellow:#ffd700;--orange:#ff8c42;--blue:#4fc3f7;--white:#e8f4ff;--muted:#5a7a99;--text:#c8ddf0;
  }}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;
    background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(0,80,160,.15) 0%,transparent 70%),
    repeating-linear-gradient(0deg,transparent,transparent 39px,rgba(30,58,95,.15) 39px,rgba(30,58,95,.15) 40px),
    repeating-linear-gradient(90deg,transparent,transparent 39px,rgba(30,58,95,.08) 39px,rgba(30,58,95,.08) 40px);}}
  .header{{border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;
    background:rgba(13,21,32,.95);backdrop-filter:blur(10px);position:sticky;top:0;z-index:100;}}
  .ticker{{font-family:'Syne',sans-serif;font-size:1.8rem;font-weight:800;color:var(--white);letter-spacing:2px;}}
  .price-main{{font-size:1.4rem;color:{chg_color};font-weight:700;}}
  .date-badge{{background:var(--surface2);border:1px solid var(--border);padding:5px 12px;font-size:.7rem;color:var(--muted);letter-spacing:1px;}}
  .main{{max-width:1200px;margin:0 auto;padding:20px;display:grid;gap:16px;}}
  .verdict-banner{{background:linear-gradient(135deg,#0a1929,#0d2035);border:1px solid var(--border);
    border-left:4px solid {verdict["border_color"]};padding:18px 22px;display:grid;grid-template-columns:auto 1fr auto;gap:20px;align-items:center;}}
  .verdict-status{{font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:800;color:{verdict["color"]};}}
  .three-col{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
  .card{{background:var(--surface);border:1px solid var(--border);padding:16px;}}
  .card-title{{font-size:.62rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:12px;
    padding-bottom:8px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:6px;}}
  .card-title::before{{content:'';width:5px;height:5px;background:var(--blue);display:block;border-radius:50%;}}
  .ind-row{{display:flex;flex-direction:column;gap:8px;}}
  .ind-item{{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:9px 10px;
    background:var(--surface2);border:1px solid rgba(30,58,95,.5);}}
  .ind-name{{font-size:.7rem;color:var(--text);}}
  .ind-desc{{font-size:.6rem;color:var(--muted);margin-top:2px;}}
  .ind-badge{{font-size:.6rem;letter-spacing:1px;padding:3px 9px;font-weight:700;white-space:nowrap;}}
  .bear{{background:rgba(255,58,94,.15);color:var(--red);border:1px solid var(--red-dim);}}
  .bull{{background:rgba(0,255,157,.12);color:var(--green);border:1px solid var(--green-dim);}}
  .neut{{background:rgba(255,215,0,.12);color:var(--yellow);border:1px solid goldenrod;}}
  .wait{{background:rgba(255,140,66,.12);color:var(--orange);border:1px solid var(--orange);}}
  .gauge-row{{display:flex;flex-direction:column;gap:9px;}}
  .gauge-label-row{{display:flex;justify-content:space-between;margin-bottom:3px;}}
  .gauge-name{{font-size:.68rem;color:var(--text);}}
  .gauge-val{{font-size:.68rem;font-weight:700;}}
  .gauge-bar{{height:4px;background:rgba(255,255,255,.05);border-radius:2px;overflow:hidden;}}
  .gauge-fill{{height:100%;border-radius:2px;}}
  .levels-table{{width:100%;border-collapse:collapse;}}
  .levels-table tr{{border-bottom:1px solid rgba(30,58,95,.5);}}
  .levels-table tr:last-child{{border-bottom:none;}}
  .levels-table td{{padding:6px 4px;font-size:.7rem;}}
  .levels-table td:first-child{{color:var(--muted);font-size:.62rem;letter-spacing:1px;}}
  .levels-table td:nth-child(2){{color:var(--white);font-weight:700;text-align:right;}}
  .levels-table td:nth-child(3){{text-align:right;font-size:.62rem;padding-left:8px;}}
  .chain-table{{width:100%;border-collapse:collapse;}}
  .chain-table th{{font-size:.6rem;letter-spacing:1px;color:var(--muted);text-align:right;padding:5px 6px;border-bottom:1px solid var(--border);}}
  .chain-table th:first-child{{text-align:left;}}
  .chain-table td{{padding:7px 6px;font-size:.7rem;text-align:right;border-bottom:1px solid rgba(30,58,95,.3);}}
  .chain-table td:first-child{{text-align:left;color:var(--muted);font-size:.63rem;}}
  .strike-atm td{{background:rgba(255,215,0,.06);color:var(--yellow)!important;}}
  .delta-val{{color:var(--blue);}} .theta-val{{color:var(--red);}} .iv-val{{color:var(--orange);}}
  .price-val{{color:var(--white);font-weight:700;}} .vol-val{{color:var(--green-dim);}}
  .news-item{{padding:10px 0;border-bottom:1px solid rgba(30,58,95,.4);display:grid;grid-template-columns:auto 1fr;gap:8px;}}
  .news-item:last-child{{border-bottom:none;}}
  .news-dot{{width:6px;height:6px;border-radius:50%;margin-top:4px;flex-shrink:0;}}
  .news-text{{font-size:.68rem;color:var(--text);line-height:1.5;}}
  .news-source{{font-size:.58rem;color:var(--muted);margin-top:2px;}}
  .news-impact{{font-size:.58rem;font-weight:700;margin-left:6px;}}
  .checklist{{display:flex;flex-direction:column;gap:7px;}}
  .check-item{{display:flex;align-items:center;gap:9px;padding:9px 10px;background:var(--surface2);border:1px solid rgba(30,58,95,.5);}}
  .check-box{{width:15px;height:15px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;
    font-size:.62rem;flex-shrink:0;cursor:pointer;}}
  .check-box.done{{background:rgba(0,255,157,.1);border-color:var(--green);color:var(--green);}}
  .check-box.fail{{background:rgba(255,58,94,.1);border-color:var(--red);color:var(--red);}}
  .check-text{{font-size:.68rem;color:var(--text);flex:1;}}
  .check-result{{font-size:.62rem;font-weight:700;}}
  .bias-pill{{background:rgba(255,255,255,.06);border:1px solid {verdict["bias_color"]};color:{verdict["bias_color"]};
    padding:7px 14px;font-size:.72rem;letter-spacing:1px;text-align:center;}}
  @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
  .live-dot{{width:6px;height:6px;background:var(--green);border-radius:50%;animation:pulse 1.5s infinite;display:inline-block;margin-right:5px;}}
  @media(max-width:768px){{.three-col,.two-col{{grid-template-columns:1fr;}}}}
  .ema-table{{width:100%;border-collapse:collapse;}}
  .ema-table tr{{border-bottom:1px solid rgba(30,58,95,.4);}}
  .ema-table td{{padding:6px 4px;font-size:.7rem;}}
  .ema-table td:first-child{{color:var(--muted);}}
  .ema-table td:nth-child(2){{text-align:right;}}
  .ema-table td:nth-child(3){{text-align:right;font-size:.65rem;}}
  .signal-card{{border:1px solid var(--border);padding:14px;position:relative;overflow:hidden;margin-bottom:12px;}}
  .signal-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;}}
</style>
</head>
<body>
<header class="header">
  <div style="display:flex;align-items:baseline;gap:12px">
    <div class="ticker">NVDA</div>
    <div class="price-main">${price:.2f}</div>
    <div style="font-size:.85rem;color:{chg_color};font-weight:700">{chg_arrow} {chg:+.2f} ({chg_p:+.2f}%)</div>
    <div style="font-size:.62rem;color:var(--muted);margin-left:6px">Prev close</div>
  </div>
  <div style="display:flex;align-items:center;gap:14px">
    <div style="font-size:.62rem;color:var(--muted)"><span class="live-dot"></span>LIVE</div>
    <div class="date-badge">{date_str} · {time_str}</div>
  </div>
</header>

<div class="main">

<!-- VERDICT -->
<div class="verdict-banner">
  <div>
    <div style="font-size:.62rem;color:var(--muted);letter-spacing:1px;margin-bottom:4px">TODAY'S VERDICT</div>
    <div class="verdict-status">{verdict["verdict"]}</div>
    <div style="font-size:.72rem;color:var(--text);margin-top:5px;line-height:1.5">{verdict["explanation"]}</div>
  </div>
  <div>
    <div style="font-size:.62rem;color:var(--muted);letter-spacing:1px;margin-bottom:6px">TRADE IDEA</div>
    <div style="font-size:.75rem;color:var(--white);line-height:1.6;background:rgba(255,255,255,.04);padding:10px;border-left:3px solid {verdict["color"]}">{verdict["trade_idea"]}</div>
    <div style="font-size:.62rem;color:var(--muted);margin-top:6px">Options expiry: <strong style="color:var(--white)">{opts["expiry"]}</strong> · IV: <strong style="color:var(--orange)">{opts["iv_30"]}%</strong></div>
  </div>
  <div>
    <div class="bias-pill">{verdict["bias"]}</div>
    <div style="font-size:.58rem;color:var(--muted);text-align:center;margin-top:5px">Updated {time_str}</div>
  </div>
</div>

<!-- ROW 1 -->
<div class="three-col">

  <!-- CLOUD STATUS -->
  <div class="card">
    <div class="card-title">Ripster EMA Cloud Status</div>
    <div class="ind-row">
      <div class="ind-item">
        <div><div class="ind-name">34-50 Cloud (Bias Filter)</div>
          <div class="ind-desc">EMA34: ${d["ema34"]:.2f} · EMA50: ${d["ema50"]:.2f}</div></div>
        {cloud_34_50}
      </div>
      <div class="ind-item">
        <div><div class="ind-name">5-12 Cloud (Entry Trigger)</div>
          <div class="ind-desc">EMA9: ${d["ema9"]:.2f} · EMA21: ${d["ema21"]:.2f}</div></div>
        {cloud_5_12}
      </div>
      <div class="ind-item">
        <div><div class="ind-name">IMACD_LB (34,9)</div>
          <div class="ind-desc">Value: {d["macd_val"]:+.3f}</div></div>
        {macd_badge}
      </div>
      <div class="ind-item">
        <div><div class="ind-name">IMACD Zero Cross</div>
          <div class="ind-desc">Prev: {d["macd_prev"]:+.3f} → Now: {d["macd_val"]:+.3f}</div></div>
        <div class="ind-badge" style="background:rgba(0,0,0,.2);color:{macd_cross_color};border:1px solid {macd_cross_color}">{macd_cross}</div>
      </div>
    </div>
    <div style="margin-top:10px">
      <table class="ema-table">
        <tr><td style="font-size:.6rem;color:var(--muted);letter-spacing:1px" colspan="3">EMA LEVELS vs PRICE</td></tr>
        {ema_rows}
      </table>
    </div>
  </div>

  <!-- OPTIONS HEALTH -->
  <div class="card">
    <div class="card-title">Options Health — Live Data</div>
    <div class="gauge-row">
      <div>
        <div class="gauge-label-row">
          <span class="gauge-name">Implied Volatility (30-Day)</span>
          <span class="gauge-val" style="color:{iv_color}">{opts["iv_30"]}%</span>
        </div>
        <div class="gauge-bar"><div class="gauge-fill" style="width:{iv_fill}%;background:{iv_color}"></div></div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:2px">{'✅ Good — options fairly priced' if opts["iv_30"] < 35 else ('⚠️ Elevated — options expensive' if opts["iv_30"] < 55 else '❌ High — consider spreads')}</div>
      </div>
      <div>
        <div class="gauge-label-row">
          <span class="gauge-name">Volume vs Average</span>
          <span class="gauge-val" style="color:{vol_color}">{d["volume_ratio"]}x avg</span>
        </div>
        <div class="gauge-bar"><div class="gauge-fill" style="width:{min(vol_fill,100):.0f}%;background:{vol_color}"></div></div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:2px">{vol_m:.0f}M today vs {avg_m:.0f}M avg · {'High conviction move' if d["volume_ratio"] > 1.3 else ('Normal activity' if d["volume_ratio"] > 0.8 else 'Low volume — caution')}</div>
      </div>
      <div>
        <div class="gauge-label-row">
          <span class="gauge-name">52-Week Range Position</span>
          <span class="gauge-val" style="color:var(--text)">${d["week52_low"]:.0f} — ${d["week52_high"]:.0f}</span>
        </div>
        <div class="gauge-bar"><div class="gauge-fill" style="width:{min(((price - d['week52_low'])/(d['week52_high']-d['week52_low']))*100,100):.0f}%;background:var(--blue)"></div></div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:2px">Price at {((price-d['week52_low'])/(d['week52_high']-d['week52_low'])*100):.0f}th percentile of yearly range</div>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);padding:10px;margin-top:4px">
        <div style="font-size:.6rem;color:var(--muted);letter-spacing:1px;margin-bottom:6px">VWAP ZONES (approximate)</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;text-align:center">
          <div><div style="font-size:.58rem;color:var(--muted)">DAILY</div><div style="font-size:.8rem;color:var(--blue);font-weight:700">${(price * 0.998):.2f}</div></div>
          <div><div style="font-size:.58rem;color:var(--muted)">WEEKLY</div><div style="font-size:.8rem;color:var(--blue);font-weight:700">${(d["ema9"]):.2f}</div></div>
          <div><div style="font-size:.58rem;color:var(--muted)">MONTHLY</div><div style="font-size:.8rem;color:var(--blue);font-weight:700">${(d["ema21"]):.2f}</div></div>
        </div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:6px">Price {'above' if price > d['ema9'] else 'below'} VWAP = {'bullish intraday ✓' if price > d['ema9'] else 'bearish intraday ✗'}</div>
      </div>
    </div>
  </div>

  <!-- S/R LEVELS -->
  <div class="card">
    <div class="card-title">Support · Resistance (Live Calc)</div>
    <table class="levels-table">
      {sr_rows}
    </table>
    <div style="margin-top:10px;padding:8px;background:rgba(79,195,247,.06);border:1px solid rgba(79,195,247,.2);font-size:.65rem;color:var(--blue);line-height:1.5">
      💡 Levels auto-calculated from pivot highs/lows on daily chart. Add these as horizontal lines in TradingView.
    </div>
  </div>
</div>

<!-- ROW 2 -->
<div class="two-col">

  <!-- OPTIONS CHAIN -->
  <div class="card">
    <div class="card-title">Options Chain — {opts["expiry"]} (Live)</div>
    <div style="font-size:.62rem;color:var(--muted);margin-bottom:8px">🎯 = near your $3 target · ⚠️ = low liquidity (avoid) · Spread &lt; $0.20 = green</div>
    <div style="font-size:.6rem;color:var(--orange);letter-spacing:1px;margin-bottom:5px">── CALLS ──</div>
    <table class="chain-table">
      <tr><th>STRIKE</th><th>PRICE</th><th>DELTA</th><th>IV</th><th>SPREAD</th><th>VOLUME</th></tr>
      {call_rows}
    </table>
    <div style="font-size:.6rem;color:var(--red);letter-spacing:1px;margin:10px 0 5px">── PUTS ──</div>
    <table class="chain-table">
      <tr><th>STRIKE</th><th>PRICE</th><th>DELTA</th><th>IV</th><th>SPREAD</th><th>VOLUME</th></tr>
      {put_rows}
    </table>
    <div style="margin-top:10px;padding:9px;background:rgba(255,215,0,.05);border:1px solid rgba(255,215,0,.2);font-size:.65rem;color:var(--yellow);line-height:1.5">
      ⚠️ Always verify on Yahoo Finance: finance.yahoo.com/quote/NVDA/options<br>
      Check: Volume &gt; 500 · Open Interest &gt; 1,000 · Bid-Ask spread &lt; $0.20
    </div>
  </div>

  <!-- NEWS -->
  <div class="card">
    <div class="card-title">NVDA News — Auto-Updated</div>
    {news_html if news_html else '<div style="font-size:.7rem;color:var(--muted);padding:10px">No recent news fetched. Check Yahoo Finance directly.</div>'}
  </div>
</div>

<!-- PRE-TRADE CHECKLIST -->
<div class="card">
  <div class="card-title">Pre-Trade Checklist — Before Every Single Trade (Click to Check Off)</div>
  <div class="checklist">
    {checklist_html}
  </div>
  <div style="margin-top:8px;font-size:.62rem;color:var(--muted);font-style:italic">All 8 green = trade. Any red = no trade. This is the rule that will save your account.</div>
</div>

<!-- DECISION TREE -->
<div class="card">
  <div class="card-title">Morning Decision Tree — Run This Every Day</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;font-size:.7rem;line-height:1.7">
    <div>
      <div style="color:var(--green);font-weight:700;margin-bottom:8px">IF CALL SETUP (need ALL):</div>
      <div>{'✅' if d["price"] > max(d["ema34"], d["ema50"]) else '❌'} Price above 34-50 cloud<br>
      {'✅' if d["ema9"] > d["ema21"] else '❌'} 5-12 cloud is GREEN<br>
      {'✅' if d["macd_val"] > 0 else '❌'} IMACD above zero<br>
      {'✅' if d["volume_ratio"] > 1.0 else '❌'} Volume confirms (ratio {d["volume_ratio"]}x)<br>
      {'✅' if d["price"] > d["ema9"] else '❌'} Price above VWAP<br>
      </div>
      <div style="margin-top:10px;padding:8px;border-left:3px solid var(--green);background:rgba(0,255,157,.05);font-size:.65rem">
      {'🟢 CALL CONDITIONS MET — Check chain for $3 strike' if (d["price"] > max(d["ema34"],d["ema50"]) and d["ema9"] > d["ema21"] and d["macd_val"] > 0) else '⏸ Call conditions not yet met. Wait for signals to align.'}
      </div>
    </div>
    <div>
      <div style="color:var(--red);font-weight:700;margin-bottom:8px">IF PUT SETUP (need ALL):</div>
      <div>{'✅' if d["price"] < min(d["ema34"], d["ema50"]) else '❌'} Price below 34-50 cloud<br>
      {'✅' if d["ema9"] < d["ema21"] else '❌'} 5-12 cloud is RED<br>
      {'✅' if d["macd_val"] < 0 else '❌'} IMACD below zero<br>
      {'✅' if d["volume_ratio"] > 1.0 else '❌'} Volume confirms (ratio {d["volume_ratio"]}x)<br>
      {'✅' if d["price"] < d["ema9"] else '❌'} Bounce failed at VWAP<br>
      </div>
      <div style="margin-top:10px;padding:8px;border-left:3px solid var(--red);background:rgba(255,58,94,.05);font-size:.65rem">
      {'🔴 PUT CONDITIONS MET — Watch for bounce fail at VWAP before entry' if (d["price"] < min(d["ema34"],d["ema50"]) and d["ema9"] < d["ema21"] and d["macd_val"] < 0) else '⏸ Put conditions not yet met. Watch for confirmation.'}
      </div>
    </div>
  </div>
  <div style="margin-top:14px;padding:12px;background:rgba(255,140,66,.06);border:1px solid rgba(255,140,66,.3);font-size:.68rem;color:var(--orange);line-height:1.6">
    🚪 <strong>EXIT RULES (never ignore):</strong> 
    +80% profit → SELL FULL POSITION · 
    -50% loss → HARD STOP NO QUESTIONS · 
    Day 3 → EXIT regardless of profit/loss · 
    IMACD flips color against you → EXIT HALF IMMEDIATELY
  </div>
</div>

<div style="text-align:center;padding:14px;font-size:.6rem;color:var(--muted);border-top:1px solid var(--border);line-height:1.8">
  🤖 Auto-updated daily at 8:00am ET via GitHub Actions · Data: Yahoo Finance (yfinance) · Prices are delayed<br>
  ⚠️ Educational analysis only — not financial advice. Verify all option prices before trading. Options involve substantial risk of loss.<br>
  Last update: <strong style="color:var(--text)">{now.strftime("%Y-%m-%d %H:%M:%S ET")}</strong>
</div>

</div>
<script>
document.querySelectorAll('.check-box').forEach(b=>{{
  b.addEventListener('click',()=>{{
    if(b.classList.contains('done')){{b.classList.remove('done');b.classList.add('fail');b.textContent='✗';}}
    else if(b.classList.contains('fail')){{b.classList.remove('fail');b.classList.add('done');b.textContent='✓';}}
    else{{b.classList.add('done');b.textContent='✓';}}
  }});
}});
</script>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────
# 4. MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching NVDA data...")
    d    = fetch_nvda_data()
    print(f"Price: ${d['price']} | Change: {d['change_pct']:+.2f}%")
    
    print("Fetching options chain...")
    opts = fetch_options_data(d["price"])
    print(f"Expiry: {opts['expiry']} | IV: {opts['iv_30']}%")
    
    print("Calculating S/R levels...")
    sr   = fetch_support_resistance(d["hist"], d["hist_1y"], d["price"])
    print(f"Resistance: {sr['resistance'][:3]}")
    print(f"Support:    {sr['support'][:3]}")
    
    print("Fetching news...")
    news = fetch_news()
    print(f"Got {len(news)} articles")
    
    print("Generating verdict...")
    verdict = generate_verdict(d, opts)
    print(f"Verdict: {verdict['verdict']}")
    
    print("Rendering HTML...")
    html = render_html(d, opts, sr, news, verdict)
    
    out = Path("index.html")
    out.write_text(html, encoding="utf-8")
    print(f"✅ index.html written ({len(html):,} bytes)")
