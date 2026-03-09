"""
NVDA Options Command Center — Data Writer (Naked Options Edition)
Writes data.json only. Naked call/put focused analysis.
"""

import yfinance as yf
import datetime, pytz, math, json
import feedparser
import numpy as np
from pathlib import Path

CT = pytz.timezone("America/Chicago")
ET = pytz.timezone("America/New_York")

BRANDO = [
    (288.00,"MO","$7T MCAP TARGET",   True),
    (225.00,"MO","MAJOR RESISTANCE",  False),
    (200.00,"MO","KEY WALL $200",     True),
    (191.00,"MO","YELLOW LINE $191",  True),
    (168.00,"MO","RESISTANCE",        False),
    (153.37,"MO","DEMAND ZONE TOP",   True),
    (141.20,"MO","DEMAND ZONE BOT",   True),
    (123.94,"MO","YELLOW LINE $124",  True),
    (98.43, "MO","SUPPORT",           False),
    (76.46, "MO","DEEP DEMAND",       True),
    (50.95, "MO","DEEP SUPPORT",      False),
    (250.00,"WK","RESISTANCE",        False),
    (225.30,"WK","MAJOR RESISTANCE",  False),
    (212.32,"WK","PRIOR ATH ZONE",    True),
    (200.08,"WK","KEY WALL $200",     True),
    (175.00,"WK","CRITICAL SUPPORT",  True),
    (149.84,"WK","SUPPORT",           False),
    (141.23,"WK","SUPPORT",           False),
    (132.86,"WK","SUPPORT",           False),
    (123.12,"WK","SUPPORT",           False),
    (115.42,"WK","SUPPORT",           False),
    (107.50,"WK","SUPPORT",           False),
    (95.27, "WK","SUPPORT",           False),
    (88.19, "WK","DOUBLE BOTTOM",     True),
    (200.60,"DY","RESISTANCE",        False),
    (196.05,"DY","RESISTANCE",        False),
    (190.40,"DY","RESISTANCE",        False),
    (184.58,"DY","KEY RESISTANCE",    True),
    (180.34,"DY","CRITICAL PIVOT",    True),
    (175.20,"DY","SUPPORT",           False),
    (168.69,"DY","SUPPORT",           False),
    (163.67,"DY","SUPPORT",           False),
    (158.26,"DY","SUPPORT",           False),
    (153.28,"DY","SUPPORT",           True),
    (149.11,"DY","SUPPORT",           False),
    (144.22,"DY","SUPPORT",           False),
    (140.77,"DY","SUPPORT",           False),
    (136.59,"DY","SUPPORT",           False),
]

SESSIONS = [
    {"name":"PRE-MKT",      "start":(7,0),  "end":(8,30),  "trade":False,"advice":"Bias only. No trades."},
    {"name":"FAKE-OUT",     "start":(8,30), "end":(9,15),  "trade":False,"advice":"Fake-out zone. Wait."},
    {"name":"CONTINUATION", "start":(9,15), "end":(10,30), "trade":True, "advice":"Continuation window. EMA pullback entry."},
    {"name":"DEAD ZONE",    "start":(10,30),"end":(13,0),  "trade":False,"advice":"No new entries. Theta bleeds."},
    {"name":"POWER WINDOW", "start":(13,0), "end":(14,30), "trade":True, "advice":"Best entries. Institutional window."},
    {"name":"CLOSING PUSH", "start":(14,30),"end":(15,0),  "trade":True, "advice":"Final push. Exit if down."},
    {"name":"AFTER HOURS",  "start":(15,0), "end":(23,59), "trade":False,"advice":"Market closed. Plan tomorrow."},
]

def get_session(ct_now):
    t = ct_now.hour * 60 + ct_now.minute
    for s in SESSIONS:
        if s["start"][0]*60+s["start"][1] <= t < s["end"][0]*60+s["end"][1]:
            return s
    return SESSIONS[-1]

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def rsi(series, period=14):
    d = series.diff()
    g = d.clip(lower=0).rolling(period).mean()
    l = (-d.clip(upper=0)).rolling(period).mean()
    return (100-(100/(1+g/l.replace(0,np.nan)))).fillna(50)

def atr(hist, period=14):
    h,l,c = hist["High"],hist["Low"],hist["Close"]
    tr = np.maximum(h-l,np.maximum(abs(h-c.shift(1)),abs(l-c.shift(1))))
    return tr.rolling(period).mean()

def bollinger_width(series, period=20):
    mid = series.rolling(period).mean(); std = series.rolling(period).std()
    return ((mid+2*std)-(mid-2*std))/mid*100

def macd_histogram(series, fast=12, slow=26, signal=9):
    m = ema(series,fast)-ema(series,slow); return m-ema(m,signal)

def compression_score(hist):
    an=atr(hist).iloc[-1]; am=atr(hist,50).iloc[-1]
    bn=bollinger_width(hist["Close"]).iloc[-1]; bm=bollinger_width(hist["Close"],50).iloc[-1]
    ar=max(0,min(1,1-(an/am))) if am else 0; br=max(0,min(1,1-(bn/bm))) if bm else 0
    return round((ar*.5+br*.5)*100,1)

def higher_highs_lows(hist, lookback=10):
    H=hist["High"].iloc[-lookback:].values; L=hist["Low"].iloc[-lookback:].values
    hh=all(H[i]>=H[i-1] for i in range(1,len(H)) if i%2==0)
    hl=all(L[i]>=L[i-1] for i in range(1,len(L)) if i%2==0)
    return hh and hl

def calc_iv_rank(hist_1y, current_iv):
    try:
        closes=hist_1y["Close"]
        log_ret=np.log(closes/closes.shift(1)).dropna()
        hv_series=log_ret.rolling(20).std()*np.sqrt(252)*100
        hv_series=hv_series.dropna()
        if len(hv_series)<20:
            return {"iv_rank":None,"iv_pct":None,"hv_20":None,"iv_vs_hv":None,"iv_quality":"N/A"}
        hv_now=round(float(hv_series.iloc[-1]),1)
        hv_high=float(hv_series.max()); hv_low=float(hv_series.min())
        iv_rank=round((current_iv-hv_low)/(hv_high-hv_low)*100,1) if hv_high!=hv_low else 50.0
        iv_rank=max(0.0,min(100.0,iv_rank))
        iv_pct=round(float((hv_series<current_iv).sum())/len(hv_series)*100,1)
        iv_vs_hv=round(current_iv-hv_now,1)
        if iv_rank<35:   iq="Low IV — good time to buy premium"
        elif iv_rank<60: iq="Moderate IV — acceptable entry"
        else:            iq="High IV — overpaying, consider waiting"
        return {"iv_rank":iv_rank,"iv_pct":iv_pct,"hv_20":hv_now,"iv_vs_hv":iv_vs_hv,"iv_quality":iq}
    except:
        return {"iv_rank":None,"iv_pct":None,"hv_20":None,"iv_vs_hv":None,"iv_quality":"N/A"}

def naked_option_analytics(opt, price, dte, direction):
    if not opt: return None
    prem=opt["price"]; strike=opt["strike"]; iv=opt["iv"]/100
    if direction=="call":
        breakeven=round(strike+prem,2)
        move_to_be=round(breakeven-price,2)
        move_to_be_pct=round(move_to_be/price*100,2)
        moneyness=price/strike
        approx_delta=round(min(0.95,max(0.05,0.5+(moneyness-1)*5)),2)
    else:
        breakeven=round(strike-prem,2)
        move_to_be=round(price-breakeven,2)
        move_to_be_pct=round(move_to_be/price*100,2)
        moneyness=strike/price
        approx_delta=round(min(0.95,max(0.05,0.5+(moneyness-1)*5)),2)
    daily_theta=round(prem*iv*(1/math.sqrt(max(dte,1)))*0.4,3) if dte>0 else 0
    days_to_danger=max(0,dte-21)
    move_for_2x=round(prem/approx_delta,2) if approx_delta>0 else None
    move_for_2x_pct=round(move_for_2x/price*100,2) if move_for_2x else None
    spread=round(opt["ask"]-opt["bid"],2)
    if spread>=0.50:   liq="Wide — avoid"
    elif spread>=0.25: liq="Moderate"
    else:              liq="Tight"
    liq_ok=spread<0.25 and opt["volume"]>300 and opt["oi"]>800
    if not liq_ok and spread<0.25: liq="Low volume"
    return {
        "strike":strike,"premium":prem,"bid":opt["bid"],"ask":opt["ask"],
        "iv":opt["iv"],"volume":opt["volume"],"oi":opt["oi"],
        "breakeven":breakeven,"move_to_be":move_to_be,"move_to_be_pct":move_to_be_pct,
        "approx_delta":approx_delta,"daily_theta":daily_theta,
        "days_to_danger":days_to_danger,"move_for_2x":move_for_2x,
        "move_for_2x_pct":move_for_2x_pct,"max_loss":round(prem*100,2),
        "spread":spread,"liq":liq,"target_prem":round(prem*1.80,2),
        "stop_prem":round(prem*0.50,2),"exit_pct":80,"stop_pct":50,
    }

def calc_ichimoku(hist):
    if len(hist)<60:
        return {"bull":False,"bear":False,"label":"N/A","detail":"No data","tenkan":None,"kijun":None,"cloud_top":None,"cloud_bottom":None}
    c=hist["Close"]; h=hist["High"]; l=hist["Low"]
    tenkan=(h.rolling(9).max()+l.rolling(9).min())/2
    kijun=(h.rolling(26).max()+l.rolling(26).min())/2
    spanA=(tenkan+kijun)/2; spanB=(h.rolling(52).max()+l.rolling(52).min())/2
    tn=float(tenkan.iloc[-1]); kn=float(kijun.iloc[-1])
    an=float(spanA.iloc[-1]); bn=float(spanB.iloc[-1]); pn=float(c.iloc[-1])
    ct=max(an,bn); cb=min(an,bn)
    above=pn>ct; below=pn<cb; tkb=tn>kn; tkbr=tn<kn
    bull=above and tkb; bear=below and tkbr
    if bull:    lbl="BULL";      det=f"Above cloud · T>{kn:.1f}"
    elif bear:  lbl="BEAR";      det=f"Below cloud · T<{kn:.1f}"
    elif above: lbl="WEAK BULL"; det="Above cloud, T≤K"
    elif below: lbl="WEAK BEAR"; det="Below cloud, T≥K"
    else:       lbl="IN CLOUD";  det=f"${cb:.1f}–${ct:.1f}"
    return {"bull":bull,"bear":bear,"label":lbl,"detail":det,"tenkan":round(tn,2),"kijun":round(kn,2),"cloud_top":round(ct,2),"cloud_bottom":round(cb,2)}

def calc_kama(hist, length=10, fast_sc=2, slow_sc=30):
    if len(hist)<length+10:
        return {"bull":False,"bear":False,"label":"N/A","detail":"No data","kama_val":None,"er":None}
    hlc3=(hist["High"]+hist["Low"]+hist["Close"])/3
    ch=abs(hlc3-hlc3.shift(length)); vol=abs(hlc3-hlc3.shift(1)).rolling(length).sum()
    er=(ch/vol.replace(0,np.nan)).fillna(0)
    fc=2./(fast_sc+1); sc_=2./(slow_sc+1); sc=(er*(fc-sc_)+sc_)**2
    kv=np.zeros(len(hlc3)); ha=hlc3.values; sa=sc.values; kv[0]=ha[0]
    for i in range(1,len(ha)):
        kv[i]=kv[i-1] if (np.isnan(sa[i]) or np.isnan(ha[i])) else kv[i-1]+sa[i]*(ha[i]-kv[i-1])
    kn=kv[-1]; kp=kv[-2]; hn=float(hlc3.iloc[-1]); en=float(er.iloc[-1])
    kr=kn>kp; kf=kn<kp; bull=hn>kn and kr; bear=hn<kn and kf
    if bull:    lbl="BULL";      det=f"HLC3>{kn:.1f} · KAMA↑ · ER{en:.2f}"
    elif bear:  lbl="BEAR";      det=f"HLC3<{kn:.1f} · KAMA↓ · ER{en:.2f}"
    elif hn>kn: lbl="WEAK BULL"; det="Above KAMA, not rising"
    elif hn<kn: lbl="WEAK BEAR"; det="Below KAMA, not falling"
    else:       lbl="NEUTRAL";   det="On KAMA"
    return {"bull":bull,"bear":bear,"label":lbl,"detail":det,"kama_val":round(kn,2),"er":round(en,3)}

def calc_rsi_signal(hist, period=14, bull_level=45, bear_level=55, oversold=30, overbought=70):
    if len(hist)<period+5:
        return {"bull":False,"bear":False,"label":"N/A","detail":"No data","rsi_val":None,"rsi_prev":None}
    rs=rsi(hist["Close"],period); rn=float(rs.iloc[-1]); rp=float(rs.iloc[-2])
    ca45=rp<bull_level and rn>=bull_level; ob=rn<oversold and rn>rp
    cb55=rp>bear_level and rn<=bear_level; obr=rn>overbought and rn<rp
    bull=ca45 or ob; bear=cb55 or obr
    ct="CROSS↑45" if ca45 else ("OS BOUNCE" if ob else ("CROSS↓55" if cb55 else ("OB REJECT" if obr else None)))
    zone="OB" if rn>overbought else ("OS" if rn<oversold else "MID")
    if bull:   lbl="BULL"; det=f"RSI {rp:.0f}→{rn:.0f} {ct}"
    elif bear: lbl="BEAR"; det=f"RSI {rp:.0f}→{rn:.0f} {ct}"
    else:      lbl=zone;   det=f"RSI {rn:.0f} · wait 45/55"
    return {"bull":bull,"bear":bear,"label":lbl,"detail":det,"rsi_val":round(rn,1),"rsi_prev":round(rp,1)}

def calc_macd_rsi_combo(hist, period=14):
    if len(hist)<30:
        return {"bull":False,"bear":False,"label":"N/A","detail":"No data","macd_h":None,"rsi_val":None}
    c=hist["Close"]; mh=macd_histogram(c); rs=rsi(c,period)
    mn=float(mh.iloc[-1]); mp=float(mh.iloc[-2]); rn=float(rs.iloc[-1])
    mcb=mp<0 and mn>=0; mcbr=mp>0 and mn<=0
    bull=mcb and 40<rn<65; bear=mcbr and 35<rn<60
    if bull:   lbl="BULL"; det=f"MACD↑0 · RSI{rn:.0f}"
    elif bear: lbl="BEAR"; det=f"MACD↓0 · RSI{rn:.0f}"
    else:      lbl="WAIT"; det=f"MACD {mn:+.3f} · RSI{rn:.0f}"
    return {"bull":bull,"bear":bear,"label":lbl,"detail":det,"macd_h":round(mn,3),"rsi_val":round(rn,1)}

def detect_rsi_divergence(hist, rsi_period=5, lookback=3):
    c=hist["Close"]
    if len(c)<rsi_period+lookback+5: return _div_none()
    rs=rsi(c,rsi_period); pv=c.values; rv=rs.values
    cp=pv[-1]; pp=pv[-(lookback+1)]; cr=rv[-1]; pr=rv[-(lookback+1)]
    pu=cp>pp; pd=cp<pp; ru=cr>pr; rd=cr<pr; sp=abs(cr-pr)
    st="strong" if sp>=8 else ("moderate" if sp>=4 else "weak")
    if pd and ru and cr<50: return {"divergence_type":"regular_bull","label":f"Reg Bull ({st})","detail":f"P↓ RSI↑ {pr:.0f}→{cr:.0f}","strength":st,"confirms_bull":True,"confirms_bear":False,"exit_warning_bull":False,"exit_warning_bear":True}
    if pu and rd and cr<55: return {"divergence_type":"hidden_bull","label":f"Hidden Bull ({st})","detail":f"P↑ RSI↓ {pr:.0f}→{cr:.0f}","strength":st,"confirms_bull":True,"confirms_bear":False,"exit_warning_bull":False,"exit_warning_bear":True}
    if pu and rd and cr>50: return {"divergence_type":"regular_bear","label":f"Reg Bear ({st})","detail":f"P↑ RSI↓ {pr:.0f}→{cr:.0f}","strength":st,"confirms_bull":False,"confirms_bear":True,"exit_warning_bull":True,"exit_warning_bear":False}
    if pd and ru and cr>45: return {"divergence_type":"hidden_bear","label":f"Hidden Bear ({st})","detail":f"P↓ RSI↑ {pr:.0f}→{cr:.0f}","strength":st,"confirms_bull":False,"confirms_bear":True,"exit_warning_bull":True,"exit_warning_bear":False}
    return _div_none()

def _div_none():
    return {"divergence_type":None,"label":"None","detail":"","strength":None,"confirms_bull":False,"confirms_bear":False,"exit_warning_bull":False,"exit_warning_bear":False}

def tf_ind(h, label, price):
    c=h["Close"]
    e8=round(float(ema(c,8).iloc[-1]),2); e21=round(float(ema(c,21).iloc[-1]),2); e50=round(float(ema(c,50).iloc[-1]),2)
    r=round(float(rsi(c).iloc[-1]),1); mh=macd_histogram(c)
    mn=round(float(mh.iloc[-1]),3); mp=round(float(mh.iloc[-2]),3)
    vn=int(h["Volume"].iloc[-1]); vm=float(h["Volume"].rolling(20).mean().iloc[-1]) or 1
    vr=round(vn/vm,2); hh=higher_highs_lows(h)
    return {"label":label,"e8":e8,"e21":e21,"e50":e50,"rsi":r,"macd_h":mn,"macd_h_prev":mp,
            "vol_ratio":vr,"hh_hl":hh,"above_cloud":price>max(e21,e50),"below_cloud":price<min(e21,e50),
            "fast_bull":e8>e21,"macd_bull":mn>0,"macd_turning":mn>0 and mp<0,
            "macd_turning_bear":mn<0 and mp>0,"rsi_expansion_bull":r>60,"rsi_expansion_bear":r<40,
            "vol_expanded":vr>=1.5,"rsi_above_50":r>50}

def get_brando_context(price):
    res=sorted([(p,tf,l,k) for (p,tf,l,k) in BRANDO if p>price],key=lambda x:x[0])
    sup=sorted([(p,tf,l,k) for (p,tf,l,k) in BRANDO if p<=price],key=lambda x:x[0],reverse=True)
    nearest=min(BRANDO,key=lambda x:abs(x[0]-price))
    on_level=abs(nearest[0]-price)<=3.0 and nearest[3]
    key_res=next((l for l in res if l[3]),res[0] if res else None)
    key_sup=next((l for l in sup if l[3]),sup[0] if sup else None)
    if   price>=200.00: sl="ABOVE $200 WALL";    sc="bull"; sa="Hold calls. Target $212 then $225. Trail stop $196."; sb="Rejection $200–$212 → take profits."
    elif price>=191.00: sl="ABOVE YELLOW $191";  sc="bull"; sa="Next wall $200. Buy pullbacks to $191 on 1H."; sb="Loses $191 → drops to $184.58."
    elif price>=184.58: sl="$184–$191 ZONE";     sc="neut"; sa="Break above $184.58 with volume → call target $191."; sb="Rejection at $184.58 → pullback to $180.34."
    elif price>=180.34: sl="$180.34 DECISION";   sc="warn"; sa="CALL: Holds $180.34, reclaims $184.58 → $190C target $191."; sb="PUT: Breaks $180.34 with volume → $175P target $175."
    elif price>=175.00: sl="BELOW $180 BEAR";    sc="bear"; sa="PUT active. Target $175 weekly. Stop above $180.34."; sb="Bounce to $180.34 fails → add puts."
    elif price>=153.37: sl="APPROACHING DEMAND"; sc="bear"; sa="Puts targeting $153–$141 monthly demand."; sb="Volume reversal at $153.37 → watch call entry."
    else:               sl="MONTHLY DEMAND";     sc="neut"; sa="Monthly demand $141–$153 — institutional buyers."; sb="Weekly reversal candle before calls."
    def lvl(t): return {"price":t[0],"tf":t[1],"label":t[2],"key":t[3]}
    return {"res":[lvl(x) for x in res[:6]],"sup":[lvl(x) for x in sup[:6]],
            "key_res":lvl(key_res) if key_res else None,"key_sup":lvl(key_sup) if key_sup else None,
            "nearest":lvl(nearest),"on_level":on_level,"scen_label":sl,"scen_color":sc,"scen_a":sa,"scen_b":sb}

def fetch_all():
    nvda=yf.Ticker("NVDA"); spy=yf.Ticker("SPY"); info=nvda.info
    d1=nvda.history(period="1y",interval="1d"); h4=nvda.history(period="60d",interval="4h")
    h1=nvda.history(period="30d",interval="1h"); m15=nvda.history(period="5d",interval="15m")
    m5=nvda.history(period="2d",interval="5m"); d1_3m=nvda.history(period="3mo",interval="1d")
    spy_d=spy.history(period="6mo",interval="1d")
    price=float(info.get("currentPrice") or info.get("regularMarketPrice") or d1["Close"].iloc[-1])
    prev_close=float(info.get("previousClose") or d1["Close"].iloc[-2])
    volume=int(info.get("regularMarketVolume") or d1["Volume"].iloc[-1])
    avg_vol=int(info.get("averageVolume") or d1["Volume"].mean())
    week52h=float(info.get("fiftyTwoWeekHigh") or d1["High"].max())
    week52l=float(info.get("fiftyTwoWeekLow") or d1["Low"].min())
    spy_e50=float(ema(spy_d["Close"],50).iloc[-1]); spy_price=float(spy_d["Close"].iloc[-1])
    spy_bull=spy_price>spy_e50
    comp=compression_score(d1_3m) if len(d1_3m)>=50 else 0
    atr_val=round(float(atr(d1).iloc[-1]),2); vol20ma=float(d1["Volume"].rolling(20).mean().iloc[-1])
    sig_ichimoku=calc_ichimoku(m15); sig_kama=calc_kama(h4)
    sig_rsi=calc_rsi_signal(h1); sig_macd_combo=calc_macd_rsi_combo(h1)
    h1_div=detect_rsi_divergence(h1,rsi_period=5,lookback=3) if len(h1)>=20 else _div_none()
    daily_tf=tf_ind(d1,"DAILY",price) if len(d1)>=50 else None
    h4_tf=tf_ind(h4,"4H",price) if len(h4)>=50 else None
    h1_tf=tf_ind(h1,"1H",price) if len(h1)>=50 else None
    m15_tf=tf_ind(m15,"15M",price) if len(m15)>=50 else None
    recent_candles=[]
    if len(m5)>=4:
        for idx,row in m5.tail(8).iterrows():
            try: ts=idx.tz_convert(CT).strftime("%I:%M %p")
            except: ts=str(idx)[11:16]
            co,cc2=float(row["Open"]),float(row["Close"])
            recent_candles.append({"time":ts,"open":round(co,2),"high":round(float(row["High"]),2),"low":round(float(row["Low"]),2),"close":round(cc2,2),"volume":int(row["Volume"]),"bull":cc2>=co})
    id_high=round(float(m5["High"].max()),2) if len(m5) else price
    id_low=round(float(m5["Low"].min()),2) if len(m5) else price
    return {"price":round(price,2),"prev_close":round(prev_close,2),"change":round(price-prev_close,2),
            "change_pct":round((price-prev_close)/prev_close*100,2),"volume":volume,"avg_vol":avg_vol,
            "vol_ratio":round(volume/avg_vol,2) if avg_vol else 1.0,"vol_20ma":round(vol20ma/1e6,1),
            "week52h":round(week52h,2),"week52l":round(week52l,2),"atr":atr_val,"compression":comp,
            "spy_bull":spy_bull,"spy_price":round(spy_price,2),"spy_e50":round(spy_e50,2),
            "sig_ichimoku":sig_ichimoku,"sig_kama":sig_kama,"sig_rsi":sig_rsi,"sig_macd_combo":sig_macd_combo,"h1_div":h1_div,
            "daily":daily_tf,"h4":h4_tf,"h1":h1_tf,"m15":m15_tf,
            "recent_candles":recent_candles,"id_high":id_high,"id_low":id_low,"d1":d1}

def fetch_options(price, d1):
    tk=yf.Ticker("NVDA"); exps=tk.options; today=datetime.datetime.now(ET).date()
    target=today+datetime.timedelta(days=25)
    chosen=next((e for e in exps if datetime.datetime.strptime(e,"%Y-%m-%d").date()>=target),exps[-1] if exps else None)
    if not chosen:
        return {"expiry":"N/A","calls":[],"puts":[],"iv_30":50,"dte":30,"exp_move":0,"iv_stats":{},"call_analytics":None,"put_analytics":None}
    chain=tk.option_chain(chosen); dte=(datetime.datetime.strptime(chosen,"%Y-%m-%d").date()-today).days
    calls_raw,puts_raw=[],[]; iv_atm=0.50
    for _,r in chain.calls.iterrows():
        s=float(r["strike"])
        if abs(s-price)<=20:
            calls_raw.append({"strike":s,"price":round(float(r.get("lastPrice",0) or r.get("ask",0) or 0),2),"bid":round(float(r.get("bid",0) or 0),2),"ask":round(float(r.get("ask",0) or 0),2),"iv":round(float(r.get("impliedVolatility",0.5) or 0.5)*100,1),"volume":int(r.get("volume",0) or 0),"oi":int(r.get("openInterest",0) or 0)})
    for _,r in chain.puts.iterrows():
        s=float(r["strike"])
        if abs(s-price)<=20:
            puts_raw.append({"strike":s,"price":round(float(r.get("lastPrice",0) or r.get("ask",0) or 0),2),"bid":round(float(r.get("bid",0) or 0),2),"ask":round(float(r.get("ask",0) or 0),2),"iv":round(float(r.get("impliedVolatility",0.5) or 0.5)*100,1),"volume":int(r.get("volume",0) or 0),"oi":int(r.get("openInterest",0) or 0)})
    atm_c=[c for c in calls_raw if abs(c["strike"]-price)<5]
    if atm_c: iv_atm=atm_c[0]["iv"]/100
    calls_raw.sort(key=lambda x:x["strike"]); puts_raw.sort(key=lambda x:x["strike"],reverse=True)
    iv_stats=calc_iv_rank(d1,iv_atm*100)
    call_t=next((c for c in calls_raw if 3.0<=c["price"]<=8.0 and c["strike"]>=price),None)
    if not call_t: call_t=next((c for c in calls_raw if c["price"]>=2.0),None)
    put_t=next((p for p in puts_raw if 3.0<=p["price"]<=8.0 and p["strike"]<=price),None)
    if not put_t: put_t=next((p for p in puts_raw if p["price"]>=2.0),None)
    return {"expiry":chosen,"dte":dte,"iv_30":round(iv_atm*100,1),
            "exp_move":round(price*iv_atm*math.sqrt(dte/365),2),
            "calls":calls_raw[:8],"puts":puts_raw[:8],"iv_stats":iv_stats,
            "call_analytics":naked_option_analytics(call_t,price,dte,"call"),
            "put_analytics":naked_option_analytics(put_t,price,dte,"put")}

def fetch_news():
    urls=["https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US","https://finance.yahoo.com/rss/headline?s=NVDA"]
    bull=["beat","surge","rally","upgrade","buy","growth","record","strong","profit","bullish","target","raise","deal","expand","partnership"]
    bear=["miss","drop","fall","downgrade","sell","cut","loss","bearish","concern","risk","decline","weak","ban","tariff","probe","lawsuit"]
    out=[]
    for url in urls:
        try:
            feed=feedparser.parse(url)
            for e in feed.entries[:8]:
                t=e.get("title",""); txt=(t+" "+e.get("summary","")).lower()
                bs=sum(1 for w in bull if w in txt); bs2=sum(1 for w in bear if w in txt)
                out.append({"title":t[:100],"published":e.get("published","")[:22],"link":e.get("link","#"),"sentiment":"bull" if bs>bs2 else ("bear" if bs2>bs else "neut")})
            if out: break
        except: continue
    return out[:5]

USE_4TH_SIGNAL=True

def build_signals(d, opts, session, bctx):
    price=d["price"]; s1=d["sig_ichimoku"]; s2=d["sig_kama"]; s3=d["sig_rsi"]; s4=d["sig_macd_combo"]; div=d["h1_div"]
    ms=4 if USE_4TH_SIGNAL else 3
    cc=0; cr=[]
    if s1["bull"]: cc+=1; cr.append({"text":f'S1 ICHI: {s1["detail"]}',"pass":True})
    else:          cr.append({"text":f'S1 ICHI: {s1["detail"]}',"pass":False})
    if s2["bull"]: cc+=1; cr.append({"text":f'S2 KAMA: {s2["detail"]}', "pass":True})
    else:          cr.append({"text":f'S2 KAMA: {s2["detail"]}',"pass":False})
    if s3["bull"]: cc+=1; cr.append({"text":f'S3 RSI: {s3["detail"]}', "pass":True})
    else:          cr.append({"text":f'S3 RSI: {s3["detail"]}',"pass":False})
    if USE_4TH_SIGNAL:
        if s4["bull"]: cc+=1; cr.append({"text":f'S4 MACD: {s4["detail"]}', "pass":True})
        else:          cr.append({"text":f'S4 MACD: {s4["detail"]}',"pass":False})
    cx=[]
    cx.append({"text":f'Brando pivot $180.34 — {"above" if price>=180.34 else "below"}', "pass":price>=180.34})
    cx.append({"text":f'SPY vs 50 EMA — {"tailwind" if d["spy_bull"] else "headwind"}', "pass":d["spy_bull"]})
    pu=d["change"]>=0
    if pu and d["vol_ratio"]>=1.5:      cx.append({"text":f'Vol {d["vol_ratio"]}x — up day','pass':True})
    elif not pu and d["vol_ratio"]<1.0: cx.append({"text":f'Vol {d["vol_ratio"]}x — low-vol pullback','pass':True})
    elif not pu and d["vol_ratio"]>=1.5:cx.append({"text":f'Vol {d["vol_ratio"]}x — selling pressure','pass':False})
    else:                                cx.append({"text":f'Vol {d["vol_ratio"]}x — neutral',"pass":None})
    cx.append({"text":f'Session: {session["name"]}', "pass":session["trade"]})
    if div["confirms_bull"]:       cx.append({"text":f'Divergence: {div["label"]} — confirms','pass':True})
    elif div["exit_warning_bull"]: cx.append({"text":f'Divergence: {div["label"]} — EXIT WARNING','pass':False})

    pc=0; pr=[]
    if s1["bear"]: pc+=1; pr.append({"text":f'S1 ICHI: {s1["detail"]}', "pass":True})
    else:          pr.append({"text":f'S1 ICHI: {s1["detail"]}',"pass":False})
    if s2["bear"]: pc+=1; pr.append({"text":f'S2 KAMA: {s2["detail"]}', "pass":True})
    else:          pr.append({"text":f'S2 KAMA: {s2["detail"]}',"pass":False})
    if s3["bear"]: pc+=1; pr.append({"text":f'S3 RSI: {s3["detail"]}', "pass":True})
    else:          pr.append({"text":f'S3 RSI: {s3["detail"]}',"pass":False})
    if USE_4TH_SIGNAL:
        if s4["bear"]: pc+=1; pr.append({"text":f'S4 MACD: {s4["detail"]}', "pass":True})
        else:          pr.append({"text":f'S4 MACD: {s4["detail"]}',"pass":False})
    px=[]
    px.append({"text":f'Brando pivot $180.34 — {"below" if price<180.34 else "above"}', "pass":price<180.34})
    px.append({"text":f'SPY vs 50 EMA — {"tailwind" if not d["spy_bull"] else "headwind"}', "pass":not d["spy_bull"]})
    pd_=d["change"]<0
    if pd_ and d["vol_ratio"]>=1.5:    px.append({"text":f'Vol {d["vol_ratio"]}x — selling pressure','pass':True})
    elif pd_ and d["vol_ratio"]<1.0:   px.append({"text":f'Vol {d["vol_ratio"]}x — low-vol decline (dead cat)','pass':False})
    elif not pd_ and d["vol_ratio"]>=1.5: px.append({"text":f'Vol {d["vol_ratio"]}x — up day headwind','pass':False})
    else:                               px.append({"text":f'Vol {d["vol_ratio"]}x — neutral',"pass":None})
    px.append({"text":f'Session: {session["name"]}', "pass":session["trade"]})
    if div["confirms_bear"]:       px.append({"text":f'Divergence: {div["label"]} — confirms','pass':True})
    elif div["exit_warning_bear"]: px.append({"text":f'Divergence: {div["label"]} — EXIT WARNING','pass':False})

    return {"call_count":cc,"put_count":pc,"max_signals":ms,
            "call_reasons":cr,"put_reasons":pr,"call_context":cx,"put_context":px,"h1_div":div}

def get_verdict(al, d, session, opts, bctx):
    cs=al["call_count"]; ps=al["put_count"]; ms=al["max_signals"]; div=al["h1_div"]
    def sz(c): return "$1,000" if c>=4 else ("$750" if c>=3 else "$500")
    if not session["trade"]:
        return {"verdict":f'{session["name"]} — NO TRADES',"bias":"WAIT","explanation":session["advice"],"trade_idea":"Next: Power Window 1:00 PM CT.","level":"none"}
    ca=opts.get("call_analytics"); pa=opts.get("put_analytics")
    if cs>=3:
        cv="MAX" if cs>=4 else "HIGH"; dn=f' + {div["label"]}' if div["confirms_bull"] else ""
        kr=bctx["key_res"]["price"] if bctx["key_res"] else "—"
        ti=f'${ca["strike"]:.0f}C {opts["expiry"]} @ ${ca["premium"]:.2f} | BE ${ca["breakeven"]:.2f} | need +{ca["move_to_be_pct"]}% | 2x @ +{ca["move_for_2x_pct"]}%' if ca else "Check chain."
        return {"verdict":f"CALL — {cv} ({cs}/{ms})","bias":"BULL","explanation":f"{cs} signals. Size {sz(cs)}. Target ${kr}.{dn}","trade_idea":ti,"level":"strong"}
    elif cs==2:
        ti=f'${ca["strike"]:.0f}C {opts["expiry"]} @ ${ca["premium"]:.2f} | BE ${ca["breakeven"]:.2f} | need +{ca["move_to_be_pct"]}%' if ca else "Check chain."
        return {"verdict":f"CALL — WATCH ({cs}/{ms})","bias":"BULL","explanation":f"2/{ms} signals. $500 size.","trade_idea":ti,"level":"watch"}
    elif ps>=3:
        cv="MAX" if ps>=4 else "HIGH"; dn=f' + {div["label"]}' if div["confirms_bear"] else ""
        ks=bctx["key_sup"]["price"] if bctx["key_sup"] else "—"
        ti=f'${pa["strike"]:.0f}P {opts["expiry"]} @ ${pa["premium"]:.2f} | BE ${pa["breakeven"]:.2f} | need -{pa["move_to_be_pct"]}% | 2x @ -{pa["move_for_2x_pct"]}%' if pa else "Check chain."
        return {"verdict":f"PUT — {cv} ({ps}/{ms})","bias":"BEAR","explanation":f"{ps} signals. Size {sz(ps)}. Target ${ks}.{dn}","trade_idea":ti,"level":"strong"}
    elif ps==2:
        ti=f'${pa["strike"]:.0f}P {opts["expiry"]} @ ${pa["premium"]:.2f} | BE ${pa["breakeven"]:.2f} | need -{pa["move_to_be_pct"]}%' if pa else "Check chain."
        return {"verdict":f"PUT — WATCH ({ps}/{ms})","bias":"BEAR","explanation":f"2/{ms} signals. Confirm volume.","trade_idea":ti,"level":"watch"}
    elif cs==1 and ps==1:
        return {"verdict":"MIXED — NO TRADE","bias":"NEUTRAL","explanation":f"Conflicting. {bctx['scen_label']}.","trade_idea":f"A: {bctx['scen_a']} | B: {bctx['scen_b']}","level":"none"}
    elif cs==1:
        return {"verdict":f"CALL WATCH ({cs}/{ms})","bias":"DEVELOPING","explanation":"1 signal. Need 2+.","trade_idea":bctx['scen_a'],"level":"none"}
    elif ps==1:
        return {"verdict":f"PUT WATCH ({ps}/{ms})","bias":"DEVELOPING","explanation":"1 bear signal. Need 2+.","trade_idea":bctx['scen_b'],"level":"none"}
    else:
        return {"verdict":"FLAT — NO SIGNAL","bias":"FLAT","explanation":f"0 signals. {bctx['scen_label']}.","trade_idea":"No signal IS a signal. Wait.","level":"none"}


if __name__=="__main__":
    ct_now=datetime.datetime.now(CT); session=get_session(ct_now)
    print(f"⏰ {ct_now.strftime('%I:%M %p CT')} — {session['name']}")
    print("📡 Fetching..."); d=fetch_all()
    print(f"   ${d['price']} | {d['change_pct']:+.2f}% | Vol {d['vol_ratio']}x | ATR ${d['atr']}")
    print("📋 Options..."); opts=fetch_options(d["price"],d["d1"])
    print(f"   {opts['expiry']} | {opts['dte']}d | IV{opts['iv_30']}% | IV rank {opts['iv_stats'].get('iv_rank','?')}")
    print("📰 News..."); news=fetch_news(); print(f"   {len(news)} articles")
    bctx=get_brando_context(d["price"]); al=build_signals(d,opts,session,bctx); verdict=get_verdict(al,d,session,opts,bctx)
    print(f"\n🧠 Call {al['call_count']}/{al['max_signals']} | Put {al['put_count']}/{al['max_signals']}")
    print(f"   {verdict['verdict']}")
    d_clean={k:v for k,v in d.items() if k!="d1"}
    payload={"generated_at":ct_now.strftime("%Y-%m-%d %H:%M CT"),"generated_ts":ct_now.isoformat(),
             "session_name":session["name"],"session_trade":session["trade"],"session_advice":session["advice"],
             "market":{"price":d["price"],"prev_close":d["prev_close"],"change":d["change"],"change_pct":d["change_pct"],
                       "volume":d["volume"],"avg_vol":d["avg_vol"],"vol_ratio":d["vol_ratio"],"vol_20ma":d["vol_20ma"],
                       "week52h":d["week52h"],"week52l":d["week52l"],"atr":d["atr"],"compression":d["compression"],
                       "id_high":d["id_high"],"id_low":d["id_low"]},
             "spy":{"price":d["spy_price"],"e50":d["spy_e50"],"bull":d["spy_bull"]},
             "signals":{"ichimoku":d["sig_ichimoku"],"kama":d["sig_kama"],"rsi":d["sig_rsi"],"macd_combo":d["sig_macd_combo"],"divergence":d["h1_div"]},
             "timeframes":{"daily":d["daily"],"h4":d["h4"],"h1":d["h1"],"m15":d["m15"]},
             "brando":bctx,"options":opts,"news":news,"alignment":al,"verdict":verdict,"candles":d["recent_candles"]}
    out=Path("data.json"); out.write_text(json.dumps(payload,indent=2,default=str),encoding="utf-8")
    print(f"\n✅ data.json — {out.stat().st_size:,} bytes")
