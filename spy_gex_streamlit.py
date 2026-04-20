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

def get_vix():
    try:
        vix_ticker = yf.Ticker("^VIX")
        vix_data = vix_ticker.history(period="1d")
        if not vix_data.empty:
            return vix_data['Close'].iloc[-1] / 100
    except:
        pass
    return None

def get_strategic_analysis(master_df, spot_price, current_vix):
    total_gex   = pd.to_numeric(master_df['Net_GEX'].str.replace('M', ''), errors='coerce').sum()
    total_dex   = pd.to_numeric(master_df['Net_DEX'].str.replace('M', ''), errors='coerce').sum()
    total_vanna = pd.to_numeric(master_df['Net_Vanna'].str.replace('M', ''), errors='coerce').sum()
    total_charm = pd.to_numeric(master_df['Net_Charm'].str.replace('M', ''), errors='coerce').sum()

    score = 0
    score += 2 if total_gex   > 0 else -2
    score += 3 if total_dex   > 0 else -3
    score += 1 if total_vanna > 0 else -1
    score += 1 if total_charm > 0 else -1

    if score >= 5:    bias = "🔥 STRONG BULLISH (Full Confluence)"
    elif score > 0:   bias = "📈 MODERATE BULLISH"
    elif score <= -5: bias = "💀 STRONG BEARISH (Crash Gravity)"
    else:             bias = "📉 MODERATE BEARISH"

    vix_pct = (current_vix * 100) if current_vix else 15.0
    if vix_pct > 22:   regime = "HIGH VOL (Gamma Flush Risk)"
    elif vix_pct < 13: regime = "LOW VOL (Melt-Up/Squeeze)"
    else:              regime = "BALANCED (Range Bound)"

    unusual_strikes = []
    for _, row in master_df.iterrows():
        vol = row['Vol_C'] + row['Vol_P']
        oi  = row['OI_C']  + row['OI_P']
        if oi > 500 and vol > (oi * 25):
            side = "CALLS" if row['Vol_C'] > row['Vol_P'] else "PUTS"
            intensity = vol / oi
            unusual_strikes.append(f"STRIKE {row['Strike']}: {side} ({intensity:.1f}x OI)")

    return bias, regime, unusual_strikes, score

# Placeholder rendered immediately after title — filled with TV string once data is ready
tv_string_placeholder = st.empty()

# --- BIAS PANEL PLACEHOLDER (filled after data loads) ---
bias_placeholder = st.empty()

# --- 1. Symbol & Strike Settings ---
symbol_choice = st.selectbox("Choose symbol:", ["SPY", "QQQ", "SPX"])

# --- VIX / IV MODE ---
vix_mode = st.selectbox("Volatility Mode:", ["Live IV (from options chain)", "Manual IV / VIX Fallback"])
manual_iv = None
vix_val = get_vix()
if vix_mode == "Manual IV / VIX Fallback":
    if vix_val is not None:
        use_vix = st.selectbox(f"VIX is currently {vix_val*100:.2f}%. Use as fallback IV?", ["Yes — use VIX", "No — enter manually"])
        if use_vix == "Yes — use VIX":
            manual_iv = vix_val
            st.markdown(f"<span style='color:white;font-size:12px;'>Using VIX ({vix_val*100:.2f}%) as IV fallback.</span>", unsafe_allow_html=True)
        else:
            manual_iv = st.number_input("Enter Manual IV (e.g. 0.165 for 16.5%):", min_value=0.01, max_value=2.0, value=0.165, step=0.005)
    else:
        manual_iv = st.number_input("Enter Manual IV (e.g. 0.165 for 16.5%):", min_value=0.01, max_value=2.0, value=0.165, step=0.005)
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
def preprocess_options(df_calls, df_puts, manual_iv=None):
    df_calls.columns = [c.lower().strip() for c in df_calls.columns]
    df_puts.columns = [c.lower().strip() for c in df_puts.columns]
    
    df_calls = df_calls.rename(columns={"openinterest": "oi_call", "volume": "vol_call", "impliedvolatility": "iv_call"})
    df_puts = df_puts.rename(columns={"openinterest": "oi_put", "volume": "vol_put", "impliedvolatility": "iv_put"})
    
    df_calls = df_calls[["strike", "oi_call", "vol_call", "iv_call", "lasttradedate"]]
    df_puts  = df_puts[["strike", "oi_put", "vol_put", "iv_put", "lasttradedate"]]
    
    df = pd.merge(df_calls, df_puts, on="strike", suffixes=("_call", "_put"))
    
    for col in ["strike", "iv_call", "oi_call", "iv_put", "oi_put"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    def fix_iv(iv):
        if manual_iv is not None:
            return manual_iv
        return iv/100 if iv > 1.5 else iv

    df["iv_call"] = df["iv_call"].apply(fix_iv)
    df["iv_put"]  = df["iv_put"].apply(fix_iv)
    return df

df = preprocess_options(calls, puts, manual_iv=manual_iv)
spot = ticker.history(period="1d")["Close"].iloc[-1]
df = df[(df["strike"] >= spot - range_strikes) & (df["strike"] <= spot + range_strikes)].copy()

# --- VISUAL TABLE (Original) ---
st.write(f"Spot detected: {spot:.2f}")
st.dataframe(df.head(20))

# --- 4. THE GOLIATH GREEK ENGINE (Index-Safe) ---
r, T = 0.05, 1/252

def calc_alpha_greeks(S, K, T, r, sigma, opt_type='call'):
    if T <= 0 or sigma < 0.0001:
        return [0.0]*9
    
    try:
        d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)
        pdf = norm.pdf(d1)
        cdf = norm.cdf(d1)
        
        gamma = pdf / (S * sigma * np.sqrt(T))
        vanna = (pdf * d2) / sigma
        charm = -pdf * (r/(sigma*np.sqrt(T)) - d2/(2*T)) if opt_type=='call' else pdf * (r/(sigma*np.sqrt(T)) - d2/(2*T))
        speed = -(gamma / S) * (d1 / (sigma * np.sqrt(T)) + 1)
        color = -(pdf / (2 * S * T * sigma * np.sqrt(T))) * (1 + (d1 * (2 * r * T - d2 * sigma * np.sqrt(T))) / (sigma * np.sqrt(T)))
        vomma = (pdf * d1 * d2) / sigma
        vera  = S * pdf * np.sqrt(T) * d1
        delta = cdf if opt_type=='call' else cdf - 1
        
        return [
            gamma*100*S**2*0.01,   # GEX
            delta*100*S,            # DEX
            vanna*100*S,            # Vanna
            charm*100*S,            # Charm
            speed*100*S,            # Speed
            color*100*S,            # Color
            vomma*100*S,            # Vomma
            vera*100*S,             # Vera
        ]
    except:
        return [0.0]*8

c_results = [calc_alpha_greeks(spot, row.strike, T, r, row.iv_call, 'call') for _, row in df.iterrows()]
p_results = [calc_alpha_greeks(spot, row.strike, T, r, row.iv_put, 'put') for _, row in df.iterrows()]

greek_cols = ['GEX', 'DEX', 'Vanna', 'Charm', 'Speed', 'Color', 'Vomma', 'Vera']
for i, col in enumerate(greek_cols):
    df[f'Net_{col}'] = [(c[i] * row.oi_call) - (p[i] * row.oi_put) for (c, p), (_, row) in zip(zip(c_results, p_results), df.iterrows())]

# --- Average IV & Expected Move ---
avg_iv = df[['iv_call', 'iv_put']].mean().mean()

def get_clean_sigma_levels(spot, iv, dte=1/252):
    daily_move = (iv / 15.87) * spot
    return {
        "2.0_Std_Upper": spot + (daily_move * 2.0),
        "1.5_Std_Upper": spot + (daily_move * 1.5),
        "1.0_Std_Upper": spot + (daily_move * 1.0),
        "0.5_Std_Upper": spot + (daily_move * 0.5),
        "0.0_Std_Anchor": spot,
        "0.5_Std_Lower": spot - (daily_move * 0.5),
        "1.0_Std_Lower": spot - (daily_move * 1.0),
        "1.5_Std_Lower": spot - (daily_move * 1.5),
        "2.0_Std_Lower": spot - (daily_move * 2.0),
        "EM_Value": daily_move
    }

em_data = get_clean_sigma_levels(spot, avg_iv, T)

# --- 5. Chart & Power Zone ---
df["abs_gex"] = df["Net_GEX"].abs()
df["total_oi"] = df["oi_call"] + df["oi_put"]

# Build df_total for GEX bars
df["call_gex"] = [c[0] * row.oi_call for c, (_, row) in zip(c_results, df.iterrows())]
df["put_gex"]  = [-p[0] * row.oi_put for p, (_, row) in zip(p_results, df.iterrows())]
df_total = df.groupby("strike").agg({
    "call_gex": "sum", "put_gex": "sum", "oi_call": "sum", "oi_put": "sum",
    "vol_call": "sum", "vol_put": "sum",
    "Net_GEX": "sum", "Net_Vanna": "sum", "iv_call": "mean", "iv_put": "mean"
}).reset_index()
df_total["net_gex"] = df_total["call_gex"] + df_total["put_gex"]

# --- Confluence Scores (from Python version) ---
_em_sigma = spot * avg_iv * np.sqrt(T)

_gauss_weight = np.exp(-((spot - df_total['strike']) ** 2) / (2 * _em_sigma ** 2))
_vol_activity = np.clip(
    (df_total['vol_call'] + df_total['vol_put']) / (df_total['oi_call'] + df_total['oi_put'] + 1),
    0, 1
)
_inertia_raw = df_total['Net_GEX'].abs() * _gauss_weight * (0.5 + 0.5 * _vol_activity)
_inertia_max = _inertia_raw.max()
df_total['inertia_score'] = (_inertia_raw / _inertia_max * 100).round(1) if _inertia_max > 0 else 0

_iv_skew = (df_total['iv_call'] - df_total['iv_put']).abs()
_vp_raw = df_total['Net_Vanna'].abs() * _iv_skew * 1000
_vp_max = _vp_raw.max()
df_total['vanna_press_score'] = (_vp_raw / _vp_max * 100).round(1) if _vp_max > 0 else 0

# Scale overlays to GEX axis
_gex_scale = df_total['net_gex'].abs().max()
_inertia_scaled  = (df_total['inertia_score'] / 100 * _gex_scale).values
_vanna_scaled    = (df_total['vanna_press_score'] / 100 * _gex_scale).values
_vol_max = (df_total['vol_call'] + df_total['vol_put']).max() + 1
_vol_scaled      = ((df_total['vol_call'] + df_total['vol_put']) / _vol_max * _gex_scale).values
_vera_abs_max    = df_total['Net_Vanna'].abs().max() + 1  # reuse Vanna proxy for Vera scaling
_vera_scaled     = (df_total['Net_Vanna'].abs() / _vera_abs_max * _gex_scale).values  # placeholder scaled Vera

# Bar colors
bar_colors = ['rgba(30,100,255,0.85)' if v >= 0 else 'rgba(220,50,50,0.75)' for v in df_total['net_gex']]

# Power Zone (kept from original)


fig = go.Figure()

# Layer 1: Net GEX bars
fig.add_trace(go.Bar(
    x=df_total["strike"],
    y=df_total["net_gex"],
    marker_color=bar_colors,
    name="Net GEX"
))

# Layer 2: Inertia (green area, visible by default)
fig.add_trace(go.Scatter(
    x=df_total['strike'], y=_inertia_scaled,
    name='Inertia (Wall Strength)', fill='tozeroy',
    fillcolor='rgba(0,200,80,0.25)', line=dict(color='rgba(0,220,80,0.9)', width=2),
    visible=True
))

# Layer 3: Vanna Pressure (orange, legend-only toggle)
fig.add_trace(go.Scatter(
    x=df_total['strike'], y=_vanna_scaled,
    name='Vanna Pressure (Magnet)',
    line=dict(color='rgba(255,165,0,0.9)', width=2),
    visible='legendonly'
))

# Layer 4: Volume Today (cyan markers, legend-only toggle)
fig.add_trace(go.Scatter(
    x=df_total['strike'], y=_vol_scaled,
    name='Volume Today (scaled)',
    mode='markers', marker=dict(color='rgba(0,200,255,0.35)'),
    visible='legendonly'
))

# Layer 5: Vera Stress (magenta dotted, legend-only toggle)
fig.add_trace(go.Scatter(
    x=df_total['strike'], y=_vera_scaled,
    name='Vera (Vol Stress)',
    line=dict(color='magenta', width=2.5, dash='dot'),
    visible='legendonly',
    hovertemplate='Strike: %{x}<br>Vera Stress Peak<extra></extra>'
))

# Spot line & Power Zone band
fig.add_vline(x=spot, line=dict(color="yellow", dash="dash"), annotation_text="Spot")

# Sigma level lines
min_y = df_total['net_gex'].min()
max_y = df_total['net_gex'].max()
for key, value in em_data.items():
    if "Std" in key:
        fig.add_vline(x=value, line_width=1, line_dash="dot", line_color="rgba(255,255,0,0.4)",
                      annotation_text=key.replace("_Std_Upper", "σ↑").replace("_Std_Lower", "σ↓").replace("_", "").replace("0Std", "0σ"))

fig.update_layout(
    template="plotly_dark",
    title=f"<b>PROPRIETARY ALPHA TAPE: {symbol_choice} @ {spot:.2f}</b> | Toggle Overlays in Legend",
    xaxis_title="Strike",
    plot_bgcolor='#0a0a0a', paper_bgcolor='#0a0a0a',
    hovermode='x unified', height=550,
    yaxis=dict(showgrid=False, zeroline=True, zerolinecolor='white', zerolinewidth=1),
    xaxis=dict(showgrid=False),
    legend=dict(bgcolor='rgba(10,10,10,0.8)', bordercolor='rgba(255,255,255,0.2)', x=0.78, y=0.99)
)
st.plotly_chart(fig, use_container_width=True)

# --- 6. MASTER TERMINAL TABLE (with new Greeks) ---
st.divider()
st.subheader("📋 MASTER PRECISION TERMINAL")

# Build master_profile from df grouped by strike
master_profile = df.groupby('strike').agg({
    'vol_call': 'sum', 'vol_put': 'sum', 'oi_call': 'sum', 'oi_put': 'sum',
    'iv_call': 'mean', 'iv_put': 'mean',
    'Net_GEX': 'sum', 'Net_DEX': 'sum', 'Net_Vanna': 'sum', 'Net_Charm': 'sum',
    'Net_Speed': 'sum', 'Net_Color': 'sum', 'Net_Vomma': 'sum', 'Net_Vera': 'sum'
}).reset_index()

# Filter 2% around spot
final_view = master_profile[
    (master_profile['strike'] >= spot * 0.98) &
    (master_profile['strike'] <= spot * 1.02)
].copy().sort_values('strike').reset_index(drop=True)

# Confluence scores for final_view
_em_sigma_fv = spot * avg_iv * np.sqrt(T)
_gauss_fv = np.exp(-((spot - final_view['strike']) ** 2) / (2 * _em_sigma_fv ** 2))
_vol_act_fv = np.clip(
    (final_view['vol_call'] + final_view['vol_put']) / (final_view['oi_call'] + final_view['oi_put'] + 1), 0, 1
)
_inertia_fv_raw = final_view['Net_GEX'].abs() * _gauss_fv * (0.5 + 0.5 * _vol_act_fv)
_inertia_fv_max = _inertia_fv_raw.max()
final_view['Inertia'] = ((_inertia_fv_raw / _inertia_fv_max * 100).round(1) if _inertia_fv_max > 0 else 0)

_iv_skew_fv = (final_view['iv_call'] - final_view['iv_put']).abs()
_vp_fv_raw = final_view['Net_Vanna'].abs() * _iv_skew_fv * 1000
_vp_fv_max = _vp_fv_raw.max()
final_view['VannaPress'] = ((_vp_fv_raw / _vp_fv_max * 100).round(1) if _vp_fv_max > 0 else 0)

# Display header info
st.write(f"**{symbol_choice}** Spot: `{spot:.2f}` | Expected Move: ±`{em_data['EM_Value']:.2f}` | "
         f"0.5σ: [{em_data['0.5_Std_Lower']:.2f}–{em_data['0.5_Std_Upper']:.2f}] | "
         f"1.0σ: [{em_data['1.0_Std_Lower']:.2f}–{em_data['1.0_Std_Upper']:.2f}] | "
         f"1.5σ: [{em_data['1.5_Std_Lower']:.2f}–{em_data['1.5_Std_Upper']:.2f}] | "
         f"2.0σ: [{em_data['2.0_Std_Lower']:.2f}–{em_data['2.0_Std_Upper']:.2f}]")
st.markdown("<span style='color:white;font-size:12px;'>Inertia = proximity + volume score 0–100 | VannaPress = IV-forced hedge score 0–100</span>", unsafe_allow_html=True)

# Format for display
display_view = final_view.copy()
for col in ['Net_GEX', 'Net_DEX', 'Net_Vanna', 'Net_Charm', 'Net_Speed', 'Net_Color', 'Net_Vomma', 'Net_Vera']:
    display_view[col] = (display_view[col] / 1_000_000).round(2).astype(str) + "M"
display_view['iv_call'] = (display_view['iv_call'] * 100).round(2).astype(str) + '%'
display_view['iv_put']  = (display_view['iv_put']  * 100).round(2).astype(str) + '%'

display_view.columns = [
    'Strike', 'Vol_C', 'Vol_P', 'OI_C', 'OI_P', 'Avg_IV_C', 'Avg_IV_P',
    'Net_GEX', 'Net_DEX', 'Net_Vanna', 'Net_Charm',
    'Net_Speed', 'Net_Color', 'Net_Vomma', 'Net_Vera',
    'Inertia', 'VannaPress'
]
st.dataframe(display_view, use_container_width=True)

# --- RENDER BIAS PANEL (fills placeholder above symbol selector) ---
vix_for_bias = vix_val if vix_val else None
m_bias, m_regime, m_flow, m_score = get_strategic_analysis(display_view, spot, vix_for_bias)
bias_color = "#00ff00" if "BULLISH" in m_bias else "#ff4444" if "BEARISH" in m_bias else "#ffaa00"
with bias_placeholder.container():
    st.markdown(f"""
    <div style="padding:12px 20px; border:2px solid {bias_color}; border-radius:10px; background:#0a0a0a; margin-bottom:8px;">
        <span style="color:{bias_color}; font-size:1.1em; font-weight:bold;">🛡️ ALPHA BIAS: {m_bias}</span>
        &nbsp;&nbsp;|&nbsp;&nbsp;
        <span style="color:#0088ff;">REGIME: {m_regime}</span>
        &nbsp;&nbsp;|&nbsp;&nbsp;
        <span style="color:#aaa;">Score: {m_score} | VIX: {f"{vix_for_bias*100:.2f}%" if vix_for_bias else "N/A"}</span>
    </div>
    """, unsafe_allow_html=True)

# --- 7. TRADINGVIEW DATA STRING ---
master_profile['Wall_Score'] = master_profile['Net_GEX'].abs() * (
    master_profile['strike'].map(final_view.set_index('strike')['Inertia']).fillna(0) / 100
)

top_calls   = master_profile[master_profile['Net_GEX'] > 0].nlargest(3, 'Wall_Score')
top_puts    = master_profile[master_profile['Net_GEX'] < 0].nlargest(3, 'Wall_Score')
top_overall = master_profile.nlargest(3, 'Wall_Score')

em_1_sigma = em_data['EM_Value']
em_2_sigma = em_data['2.0_Std_Upper'] - spot

wall_output = []
ranked_strikes = pd.concat([top_calls, top_puts, top_overall]).drop_duplicates(subset=['strike'])
for idx, row in ranked_strikes.iterrows():
    inertia_val = final_view.loc[final_view['strike'] == row['strike'], 'Inertia'].values
    inertia_val = inertia_val[0] if len(inertia_val) > 0 else 10
    wall_output.append(f"{row['strike']:.2f}:{row['Net_GEX']/1e6:.1f}:{inertia_val:.0f}")

tv_data_string = f"EM1:{em_1_sigma:.4f}:EM2:{em_2_sigma:.4f}," + ",".join(wall_output)

# Render TV string into the top placeholder (appears right after the title)
with tv_string_placeholder.container():
    st.subheader("📈 TRADINGVIEW DATA STRING")
    st.code(tv_data_string, language="text")
    st.markdown("<span style='color:white;font-size:12px;'>Copy this string into your TradingView indicator input field.</span>", unsafe_allow_html=True)
    st.divider()

# --- 8. ALPHA COMMAND CENTER ---
st.divider()
st.subheader("🕹️ ALPHA COMMAND CENTER")

# Format for AI
ai_df = final_view[['strike', 'Net_GEX', 'Net_DEX', 'Net_Vanna', 'Net_Charm', 'Net_Speed', 'Net_Color', 'Net_Vomma', 'Net_Vera', 'Inertia', 'VannaPress']].copy()
for col in [c for c in ai_df.columns if 'Net_' in c]:
    ai_df[col] = ai_df[col].apply(lambda x: f"{(x / 1e6):.2f}M" if not np.isnan(x) else "0.00M")

master_prompt = f"""
[ROLE]: You are the Senior 0DTE Alpha Strategist. I am the execution trader. 
Analyze this raw Greek tape for {symbol_choice} (Spot: {spot:.2f}).

[THE DATA FEED]:
{ai_df.head(15).to_string(index=False)}

[YOUR STRATEGIC MANDATE]:
1. **DIRECTIONAL POLARITY**: 
   - Is Net_GEX predominantly positive (dealers long gamma = price pinning) or negative (dealers short gamma = trending/volatile)?
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
   - Use Net_Speed, Net_Vomma, Net_Color, and Net_Vera. If these are spiking at a specific strike, is a "Gamma Squeeze" or "Liquidity Hole" imminent?
   - Net_Color = rate of change of gamma over time (theta-gamma bleed). Net_Vomma = vol-of-vol sensitivity. Net_Vera = vol stress (rho-vanna cross). Use these to detect hidden instability.
   - Inertia score = proximity + volume weighted wall strength (0-100). VannaPress = IV-skew forced dealer hedge score (0-100). High Inertia + High VannaPress = fortress level. Low Inertia + High GEX = phantom wall, likely to break.

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

# --- 9. POWER RANKINGS (moved to bottom) ---
st.divider()
st.subheader("🏆 ALPHA TAPE: POWER RANKINGS")

rank_col1, rank_col2, rank_col3 = st.columns(3)

with rank_col1:
    st.markdown("**📞 Top Call Walls**")
    for i, (idx, row) in enumerate(top_calls.iterrows()):
        st.metric(label=f"CALL {i+1} | Strike {row['strike']:.2f}", value=f"Score: {row['Wall_Score']:.0f}")

with rank_col2:
    st.markdown("**🔻 Top Put Walls**")
    for i, (idx, row) in enumerate(top_puts.iterrows()):
        st.metric(label=f"PUT {i+1} | Strike {row['strike']:.2f}", value=f"Score: {row['Wall_Score']:.0f}")

with rank_col3:
    st.markdown("**🔥 Overall Power Ranking**")
    for i, (idx, row) in enumerate(top_overall.iterrows()):
        st.metric(label=f"OVERALL {i+1} | Strike {row['strike']:.2f}", value=f"Score: {row['Wall_Score']:.0f}")

# --- 10. UNUSUAL FLOW RADAR ---
st.divider()
st.subheader("⚠️ UNUSUAL FLOW RADAR")
if m_flow:
    for item in m_flow:
        st.markdown(f"<span style='color:#00ff00; font-family:monospace;'>• {item}</span>", unsafe_allow_html=True)
else:
    st.markdown("<span style='color:white;'>Normal — No Unusual Flow Detected</span>", unsafe_allow_html=True)
