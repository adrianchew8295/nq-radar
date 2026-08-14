import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import io
from datetime import datetime, timezone, timedelta

# ==============================================================================
# 🎨 页面基础配置
# ==============================================================================
st.set_page_config(
    page_title="NQmain 跨资产时光机与高低切雷达",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 专属标的池 (存储板块规范为 MU + WDC)
BENCHMARKS = ["NQ=F", "QQQ"]
MAG_7 = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA"]
STORAGE = ["MU", "WDC"]
WATCHLIST = BENCHMARKS + MAG_7 + STORAGE

# ==============================================================================
# 🌐 自动抓取 Invesco 官方 QQQ 每日成分股与权重
# ==============================================================================
@st.cache_data(ttl=86400)  # 每天自动刷新一次官方持仓
def fetch_invesco_qqq_holdings():
    url = "https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings-0.csv?audienceType=Investor&action=download&ticker=QQQ"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if 'Holding Ticker' in df.columns:
                tickers = df['Holding Ticker'].dropna().astype(str).str.strip().tolist()
                valid_tickers = [t for t in tickers if t.isalpha() and len(t) <= 5]
                return valid_tickers[:50]
    except Exception:
        pass
    # 备用 Top 权重清单
    return [
        "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
        "NFLX", "AMD", "QCOM", "ADBE", "LIN", "TXN", "PEP", "AMGN", "ISRG", "INTU",
        "CMCSA", "HON", "BKNG", "AMAT", "VRTX", "LRCX", "ADI", "PANW", "MU", "PLTR",
        "KLAC", "SNPS", "CDNS", "MDLZ", "CRWD", "MAR", "ORLY", "CTAS", "NXPI", "FTNT"
    ]

TOP_WEIGHTS = fetch_invesco_qqq_holdings()
ALL_TICKERS = list(set(WATCHLIST + TOP_WEIGHTS))

# ==============================================================================
# 📡 数据拉取与缓存
# ==============================================================================
@st.cache_data(ttl=1800)
def load_market_data():
    data = yf.download(ALL_TICKERS, period="2y", interval="1d", group_by='ticker', progress=False)
    return data

# ==============================================================================
# 🛑 铁律门禁：未收盘强制拦截验证
# ==============================================================================
def check_market_lockout(target_dt):
    now_et = datetime.now(timezone.utc) - timedelta(hours=4)
    today_et = now_et.date()
    if target_dt == today_et:
        if now_et.time() < datetime.strptime("16:15", "%H:%M").time():
            return False, now_et.strftime('%H:%M:%S')
    return True, ""

# ==============================================================================
# 🎛️ 侧边栏控制面板
# ==============================================================================
st.sidebar.header("🕹️ 时光机控制面板")

query_mode = st.sidebar.radio(
    "选择查询维度:",
    ["📅 指定历史日期", "🎯 NQmain 目标点位反查", "🏆 NQmain 历史最高点 (ATH)"]
)

target_price_input = None
target_date_input = None

if query_mode == "📅 指定历史日期":
    # 默认自动定位到今天（最新交易日）
    target_date_input = st.sidebar.date_input("选择查询交易日", datetime.now().date())
elif query_mode == "🎯 NQmain 目标点位反查":
    target_price_input = st.sidebar.number_input("输入 NQmain 点位 (如 30000)", min_value=10000, max_value=50000, value=30000, step=100)

st.sidebar.markdown("---")
st.sidebar.caption("💡 **操盘风控底线**: 坚持只认定格 DAILY CLOSE，严禁盘中虚假数据！")

# ==============================================================================
# 🧠 核心计算引擎
# ==============================================================================
try:
    raw_data = load_market_data()
    nq_df = raw_data['NQ=F'].dropna() if 'NQ=F' in raw_data and len(raw_data['NQ=F'].dropna()) > 0 else raw_data['QQQ'].dropna()

    if query_mode == "🏆 NQmain 历史最高点 (ATH)":
        target_idx = nq_df['High'].idxmax()
    elif query_mode == "🎯 NQmain 目标点位反查":
        matched = nq_df[nq_df['High'] >= target_price_input]
        if len(matched) > 0:
            target_idx = matched.index[-1]
        else:
            diff = (nq_df['Close'] - target_price_input).abs()
            target_idx = diff.idxmin()
    else:
        t_dt = pd.to_datetime(target_date_input)
        valid_dates = nq_df.index[nq_df.index <= t_dt]
        target_idx = valid_dates[-1] if len(valid_dates) > 0 else nq_df.index[-1]

    target_date_str = target_idx.strftime('%Y-%m-%d')
    target_date_obj = target_idx.date()

    is_closed, current_et_time = check_market_lockout(target_date_obj)
    if not is_closed:
        st.error(f"""
        🛑 **门禁拦截报错 (LOCKOUT ERROR): 拒绝处理未定格数据！**
        * **目标日期**: `{target_date_str}`
        * **当前美东时间**: `{current_et_time} ET` (距离收盘定格 16:15 尚在交易中)
        * **核心铁律**: DAILY CLOSE 尚未走完定格，严禁使用盘中未完成数据计算同步率！请于收盘后再试。
        """)
        st.stop()

    nq_close = nq_df['Close'].loc[target_idx]
    loc_pos_nq = nq_df.index.get_loc(target_idx)
    nq_prev_close = nq_df['Close'].iloc[loc_pos_nq - 1] if loc_pos_nq > 0 else nq_close
    nq_chg_pct = ((nq_close - nq_prev_close) / nq_prev_close) * 100
    nq_ath = nq_df['High'].loc[:target_idx].max()
    nq_drawdown = ((nq_close - nq_ath) / nq_ath) * 100

    qqq_df = raw_data['QQQ'].dropna()
    qqq_close = qqq_df['Close'].loc[target_idx] if target_idx in qqq_df.index else 0
    qqq_prev = qqq_df['Close'].shift(1).loc[target_idx] if target_idx in qqq_df.index else qqq_close
    qqq_chg_pct = ((qqq_close - qqq_prev) / qqq_prev) * 100 if qqq_prev > 0 else 0

    st.title("🎯 NQmain 跨资产归因与高低切雷达")
    st.caption(f"📅 锁定定格交易日: **{target_date_str}** | 门禁审计: **DAILY CLOSE 已定格 ✅**")

    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 NQmain 期货主力", f"{nq_close:,.2f}", f"{nq_chg_pct:+.2f}%")
    col2.metric("📈 QQQ 纳指基准", f"${qqq_close:.2f}", f"{qqq_chg_pct:+.2f}%")
    col3.metric("🏛️ 大盘历史位阶", f"距 ATH {nq_drawdown:+.2f}%", "极高位多头" if nq_drawdown > -3 else "正常洗盘")

    st.markdown("---")

    # 维度一：今日谁在拉盘 TOP 5
    st.subheader("🔥 维度一：今日谁在拉盘？(全市场 100 股拉盘归因 TOP 5)")
    contrib_list = []
    for t in TOP_WEIGHTS:
        if t not in raw_data: continue
        df_t = raw_data[t].dropna()
        if target_idx not in df_t.index: continue
        
        pos = df_t.index.get_loc(target_idx)
        if pos == 0: continue
        
        c = df_t['Close'].iloc[pos]
        prev_c = df_t['Close'].iloc[pos - 1]
        vol = df_t['Volume'].iloc[pos]
        dollar_vol = c * vol
        chg_pct = ((c - prev_c) / prev_c) * 100
        contrib_pts = (chg_pct / 100.0) * (dollar_vol / 1e9) * 2.5
        
        contrib_list.append({
            "代码": t,
            "当日收盘价": f"${c:.2f}",
            "当日涨跌%": chg_pct,
            "成交额($B)": dollar_vol / 1e9,
            "贡献点数": contrib_pts
        })

    df_contrib = pd.DataFrame(contrib_list).sort_values(by="贡献点数", ascending=False).head(5)
    df_contrib_show = df_contrib.copy()
    df_contrib_show['当日涨跌%'] = df_contrib_show['当日涨跌%'].apply(lambda x: f"{x:+.2f}%")
    df_contrib_show['成交额($B)'] = df_contrib_show['成交额($B)'].apply(lambda x: f"${x:.2f}B")
    df_contrib_show['贡献点数'] = df_contrib_show['贡献点数'].apply(lambda x: f"{x:+.1f} 点 🚀")
    st.dataframe(df_contrib_show.reset_index(drop=True), use_container_width=True)

    # 维度二：专属关注池 (Mag 7 + 存储双雄 + Toby 理论)
    st.subheader("🎯 维度二：专属高低切与 Toby 仓位风控雷达 (Mag 7 + 存储双雄)")
    watch_rows = []
    copy_lines = []
    
    for ticker in WATCHLIST:
        if ticker not in raw_data: continue
        df_t = raw_data[ticker].dropna()
        if target_idx not in df_t.index: continue
        
        pos = df_t.index.get_loc(target_idx)
        c = df_t['Close'].iloc[pos]
        h = df_t['High'].iloc[pos]
        l = df_t['Low'].iloc[pos]
        prev_c = df_t['Close'].iloc[pos - 1] if pos > 0 else c
        chg_pct = ((c - prev_c) / prev_c) * 100
        
        vol = df_t['Volume'].iloc[pos]
        vol_ma20 = df_t['Volume'].iloc[max(0, pos-20):pos].mean() if pos > 0 else vol
        vol_ratio = vol / vol_ma20 if vol_ma20 > 0 else 1.0
        
        ath_p = df_t['High'].loc[:target_idx].max()
        drawdown = ((c - ath_p) / ath_p) * 100
        
        rng = h - l
        past_ranges = (df_t['High'].iloc[max(0, pos-6):pos+1] - df_t['Low'].iloc[max(0, pos-6):pos+1]).values
        is_nr7 = len(past_ranges) == 7 and rng == np.min(past_ranges)
        is_nr4 = len(past_ranges) >= 4 and rng == np.min(past_ranges[-4:])
        
        prev_h = df_t['High'].iloc[pos - 1] if pos > 0 else h
        prev_l = df_t['Low'].iloc[pos - 1] if pos > 0 else l
        is_inside = (h <= prev_h) and (l >= prev_l)
        
        avg_5_rng = np.mean(past_ranges[-5:]) if len(past_ranges) >= 5 else rng
        is_expansion = rng > (1.3 * avg_5_rng) and (c > prev_h or c < prev_l)
        
        if is_nr7:
            toby_status = "🔴 CONTRACTION (NR7极窄)"
            action_signal = "🛑 7日最窄收缩！【严禁频繁下单，等待变盘】"
        elif is_inside:
            toby_status = "🟡 INSIDE BAR (内包孕线)"
            action_signal = "🛑 孕线无方向，【管住手，不乱追单】"
        elif is_nr4:
            toby_status = "🔴 CONTRACTION (NR4收缩)"
            action_signal = "🛑 4日收缩！【耐心等放量突破】"
        elif is_expansion:
            toby_status = "🟢 EXPANSION (波动扩张)"
            action_signal = "🚀 波动剧烈扩张！【顺势击球/顺势持仓】"
        else:
            toby_status = "⚪ Normal Range (常态)"
            action_signal = "🟢 常规波动，按既定计划操作"
            
        display_ticker = ticker
        cat = "基准" if ticker in BENCHMARKS else ("存储" if ticker in STORAGE else "7巨头")
            
        watch_rows.append({
            "代码": display_ticker,
            "板块": cat,
            "当日收盘": f"${c:.2f}" if ticker != "NQ=F" else f"{c:,.2f}",
            "涨跌%": chg_pct,
            "量比(20MA)": f"{vol_ratio:.2f}x",
            "距自身ATH%": drawdown,
            "TOBY 形态判定": toby_status,
            "操盘风控指令": action_signal
        })
        
        copy_lines.append(f" • {display_ticker:5s}: 收盘 {c:.2f} ({chg_pct:+.2f}%) | 距ATH {drawdown:+.2f}% | {toby_status} -> {action_signal}")

    df_watch = pd.DataFrame(watch_rows)
    bm_part = df_watch[df_watch['板块'] == '基准']
    st_part = df_watch[df_watch['板块'] != '基准'].sort_values(by="距自身ATH%", ascending=False)
    
    st_part['涨跌%'] = st_part['涨跌%'].apply(lambda x: f"{x:+.2f}%")
    st_part['距自身ATH%'] = st_part['距自身ATH%'].apply(lambda x: f"{x:+.2f}%")
    bm_part['涨跌%'] = bm_part['涨跌%'].apply(lambda x: f"{x:+.2f}%")
    bm_part['距自身ATH%'] = bm_part['距自身ATH%'].apply(lambda x: f"{x:+.2f}%")
    
    final_table = pd.concat([bm_part, st_part])
    st.dataframe(final_table.reset_index(drop=True), use_container_width=True)

    # 维度三：一键复制专属文本框
    st.markdown("---")
    st.subheader("📋 一键极速复制 (直接点击右上角复制，粘贴发给 Gemini)")
    
    top1 = df_contrib.iloc[0]['代码'] if len(df_contrib) > 0 else "N/A"
    top1_chg = df_contrib.iloc[0]['当日涨跌%'] if len(df_contrib) > 0 else 0
    top2 = df_contrib.iloc[1]['代码'] if len(df_contrib) > 1 else "N/A"
    top2_chg = df_contrib.iloc[1]['当日涨跌%'] if len(df_contrib) > 1 else 0
    
    copy_text_block = f"""================================================================================
📊 NQMAIN 跨资产归因与高低切复盘报告 (DAILY CLOSE 定格版)
📅 查询基准日: {target_date_str} | 🎯 NQmain: {nq_close:,.2f} ({nq_chg_pct:+.2f}%) | 📈 QQQ: ${qqq_close:.2f} ({qqq_chg_pct:+.2f}%)
--------------------------------------------------------------------------------
【🔥 今日拉盘 TOP 2 功臣】
 • {top1} ({top1_chg:+.2f}%) 🚀 核心拉盘主力
 • {top2} ({top2_chg:+.2f}%) 🚀 协同进攻主力

【🎯 专属关注池与 TOBY 风控状态】
""" + "\n".join(copy_lines) + """
================================================================================
"""
    st.code(copy_text_block, language="text")

except Exception as e:
    st.error(f"⚠️ 运行出现异常: {str(e)}")
