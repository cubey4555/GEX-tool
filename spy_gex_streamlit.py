# -*- coding: utf-8 -*-
# goliath_master_terminal.py

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go
import streamlit as st
import datetime
import time

st.set_page_config(page_title="GEX MASTER TERMINAL", layout="wide")
st.title("📊 GEX Dashboard (Interactive)")

# --- 1. Symbol & Strike Settings ---
symbol_choice = st.selectbox("Choose symbol:", ["SPY", "QQQ", "SPX"])
ticker_map = {"SPY": "SPY", "QQQ": "QQQ", "SPX": "^SPX"}
symbol = ticker_map[symbol_choice]

default_range = 15 if symbol_choice in ["SPY", "QQQ"] else 80
range_strikes = st.slider("Strike Window:", 1, 100, default_range)

# --- 2. Data Fetching ---
ticker = yf.Ticker(symbol)
expirations = []
for i in range(3):
    try:
        expirations = ticker.options
        if expirations: break
    except:
        time.sleep(0.5)

if not expirations:
    st.warning("No options data available.")
    st.stop()

expiry_choice = st.selectbox("Choose expiry:", expirations, index=0)

def get_options(symbol, expiry):
    ticker = yf.Ticker(symbol)
    chain = ticker.option_chain(expiry)
    return chain.calls, chain.puts

calls, puts = get_options(symbol, expiry_choice)

# --- 3. Preprocess (Preserving Your Original Logic) ---
def preprocess_options(df_calls, df_puts):
    df_calls.columns = [c.lower().strip() for c in df_calls.columns]
    df_puts.columns = [c.lower().strip() for c in df_puts.columns]
    
    df_calls = df_calls.rename(columns={"openinterest": "oi_call", "volume": "vol_call", "impliedvolatility": "iv_call"})
    df_puts = df_puts.rename(columns={"openinterest": "oi_put", "volume": "vol_put", "impliedvolatility": "iv_put"})
    
    df_calls = df_calls[["strike", "oi_call", "vol_call", "iv_call", "lasttradedate"]]
    df_puts  = df_puts[["strike", "oi_put", "vol_put", "iv_put", "lasttradedate"]]
    
    df = pd.merge(df_calls, df_puts, on="strike", suffixes=("_call", "_put"))
    
    for col in ["strike", "iv_call", "oi_call", "iv_put", "oi_put"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    
    df["iv_call"] = df["iv_call"].apply(lambda x: x/100 if x > 1.5 else x)
    df["iv_put"]  = df["iv_put"].apply(lambda x: x/100 if x > 1.5 else x)
    return df

df = preprocess_options(calls, puts)
spot = ticker.history(period="1d")["Close"].iloc[-1]
df = df[(df["strike"] >= spot - range_strikes) & (df["strike"] <= spot + range_strikes)].copy()

# --- VISUAL TABLE (Original) ---
st.write(f"Spot detected: {spot:.2f}")
st.dataframe(df.head(20))

# --- 4. THE GOLIATH GREEK ENGINE (Index-Safe) ---
r, T = 0.05, 1/252

def calc_alpha_greeks(S, K, T, r, sigma, opt_type='call'):
    # Safety: If IV is 0 or extremely low, Black-Scholes fails. Return 0s.
    if T <= 0 or sigma < 0.0001:
        return [0.0]*7
    
    try:
        d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)
        pdf = norm.pdf(d1)
        
        gamma = pdf / (S * sigma * np.sqrt(T))
        vanna = (pdf * d2) / sigma
        charm = -pdf * (r/(sigma*np.sqrt(T)) - d2/(2*T)) if opt_type=='call' else pdf * (r/(sigma*np.sqrt(T)) - d2/(2*T))
        speed = -(gamma / S) * (d1 / (sigma * np.sqrt(T)) + 1)
        vomma = (pdf * d1 * d2) / sigma
        vera  = S * pdf * np.sqrt(T) * d1
        delta = norm.cdf(d1) if opt_type=='call' else norm.cdf(d1) - 1
        
        return [gamma*100*S**2*0.01, delta*100*S, vanna*100*S, charm*100*S, speed*100*S, vomma*100*S, vera*100*S]
    except:
        return [0.0]*7

# CRITICAL: We calculate results and force them back into the dataframe using the original index
c_results = [calc_alpha_greeks(spot, row.strike, T, r, row.iv_call, 'call') for _, row in df.iterrows()]
p_results = [calc_alpha_greeks(spot, row.strike, T, r, row.iv_put, 'put') for _, row in df.iterrows()]

greek_cols = ['GEX', 'DEX', 'Vanna', 'Charm', 'Speed', 'Vomma', 'Vera']
for i, col in enumerate(greek_cols):
    df[f'Net_{col}'] = [(c[i] * row.oi_call) - (p[i] * row.oi_put) for (c, p), (_, row) in zip(zip(c_results, p_results), df.iterrows())]

# --- 5. Chart & Power Zone ---
df["abs_gex"] = df["Net_GEX"].abs()
df["total_oi"] = df["oi_call"] + df["oi_put"]
weights = df["abs_gex"] + 0.25 * df["total_oi"]

if weights.sum() > 0:
    p_center = (df["strike"] * weights).sum() / weights.sum()
    p_std = np.sqrt(((weights * (df["strike"] - p_center) ** 2).sum()) / weights.sum())
    p_low, p_high = p_center - p_std, p_center + p_std
else:
    p_center, p_low, p_high = spot, spot-1, spot+1

fig = go.Figure()
fig.add_trace(go.Bar(
    x=df["strike"], 
    y=df["Net_GEX"], 
    marker_color=["green" if x>=0 else "red" for x in df["Net_GEX"]],
    name="Net GEX"
))
fig.add_vline(x=spot, line=dict(color="yellow", dash="dash"), annotation_text="Spot")
fig.add_vrect(x0=p_low, x1=p_high, fillcolor="purple", opacity=0.15, line_width=0)
fig.update_layout(template="plotly_dark", title=f"{symbol} GEX Roadmap", xaxis_title="Strike")
st.plotly_chart(fig, use_container_width=True)

# --- 6. ALPHA COMMAND CENTER ---
st.divider()
st.subheader("🕹️ ALPHA COMMAND CENTER")

# Format for AI - Final cleanup to ensure no NaNs reach the prompt
ai_df = df[['strike', 'Net_GEX', 'Net_DEX', 'Net_Vanna', 'Net_Charm', 'Net_Speed', 'Net_Vomma', 'Net_Vera']].copy()
for col in [c for c in ai_df.columns if 'Net_' in c]:
    ai_df[col] = ai_df[col].apply(lambda x: f"{(x / 1e6):.2f}M" if not np.isnan(x) else "0.00M")

master_prompt = f"""
[ROLE]: You are the Senior 0DTE Alpha Strategist. I am the execution trader. 
Analyze this raw Greek tape for {symbol_choice} (Spot: {spot:.2f}).

[THE DATA FEED]:
{ai_df.head(15).to_string(index=False)}

[POWER ZONE]: {p_low:.2f} - {p_high:.2f} (Center: {p_center:.2f})

[YOUR STRATEGIC MANDATE]:
1. **DIRECTIONAL POLARITY**: 
   - Compare Spot ({spot:.2f}) to the Power Zone Center ({p_center:.2f}). 
   - Are we in a "Bullish Expansion" (Spot > Center with Positive GEX) or a "Bearish Trap" (Spot < Center with Deepening Negative GEX)? 
   - Give a definitive Lean: BULLISH, BEARISH, or NEUTRAL/CHOP.

2. **THE LINES IN THE SAND**: 
   - **Goliath Floor**: The strike with the largest Negative Net_GEX (The "Wall").
   - **Magnet Pivot**: The high-volume Net_DEX strike that price is gravitating toward.
   - **The Ceiling**: The strike where GEX flips positive or where DEX friction is highest.

3. **MARKET DYNAMICS**: 
   - Analyze the "Accelerated Gravity" vs. "Mean Reversion." 
   - If GEX is deep negative across the board, explain the "Slippage Risk" if the Goliath Floor breaks.

4. **THE ROADMAP (TIMED)**: 
   - **9:30-10:30 (Opening Vol)**: What is the primary risk at the open?
   - **10:30-1:00 (The Grind)**: Where is the Magnet Pivot pulling us?
   - **1:00-4:00 (0DTE Gamma Decay)**: How will the end-of-day delta hedging affect price?

5. **VOLATILITY CHECK**: 
   - Use Net_Speed and Net_Vera. If these are spiking at a specific strike, is a "Gamma Squeeze" or "Liquidity Hole" imminent?

[THINK FREELY]: Use the Greeks to spot the fakeouts. If Spot is bouncing but Vanna is deep negative, tell me it's a "Dead Cat Bounce" and dealers will sell into it.
6. 
    - look at all the greeks and determine the most levels that price will bounce off of and pivot off. make sure you look at put call walls and filter them out using the other greeks to find the best ones that price will pivot from and list them. make sure its in a list format and give the reason behind the level and what price will do at the pivot level. also make sure its put and call walls so gamma walls so make sure it is just a whole number. format should be like this: whole number put wall - reasoning behind it - what price will do. do this for all imporant pivots. and remember make sure the greeks back up the level. only give the valid levels price will bounce from and the accelotrs. fianlly when you are done give it to a data string and give me a data string that i can input into a tradingview indicator make it copiable.  
"""

col1, col2 = st.columns(2)
with col1:
    st.info("Strategy Alpha Prompt")
    st.code(master_prompt, language="text")
with col2:
    st.info("Full Raw Greek Table")
    st.code(ai_df.to_string(index=False), language="text")
