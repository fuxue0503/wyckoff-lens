import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import time
from sentinel import fetch_market_data, analyze_wyckoff, generate_llm_report, send_signal_email

# 页面配置
st.set_page_config(page_title="Wyckoff Sentinel", layout="wide")

# 主界面标题
st.title("🛡️ Wyckoff Sentinel: 数据与算法全息看板")
st.markdown("抛弃基于图片的非确定性预测，利用 Pandas 实施 **纯数据量价解析**。")

# --- 核心控制区 (顶部设置) ---
st.subheader("⚙️ 巡航阵列配置")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 哨兵中枢控制台")
    target_symbol = st.selectbox("目标猎物 (Symbol)", ["BTC/USDT", "ETH/USDT"], index=0, help="系统专注且仅支持主流高流动性标的")
    target_timeframe = st.selectbox("雷达频段 (Timeframe)", ["1h", "4h", "1d"], index=1)
    
    st.divider()
    st.subheader("✉️ 跨端狙击报警 (自动邮件)")
    enable_email = st.toggle("启用高分自动化提示", value=False)
    st.caption("注：仅在综合评分 ≥ 70 且检测到关键相位切换时触发狙击警报。")
    receiver_email = st.text_input("接收终端邮箱", "", help="输入你的常用手机邮箱，建议使用 Gmail/Outlook")
    if st.button("🔔 发送测试狙击指令", use_container_width=True):
        if not receiver_email:
            st.error("请输入接收终端邮箱！")
        else:
            success = send_signal_email(
                subject="[Sentinel Test] 哨兵跨端通讯已连接",
                body="测试成功！你的接收终端已成功绑定至 Wyckoff Sentinel。高分报警机制已就绪。",
                receiver_email=receiver_email
            )
            if success:
                st.success("✅ 通讯测试指令已送达，请检查你的邮箱（含垃圾箱）。")
            else:
                st.error("❌ 送达失败，请返回 sentinel.py 检查发件人的应用专用密码 (App Password) 配置！")
    
    st.divider()
    proxy_url = st.text_input("网络桥接 (Proxy, 可选)", "", help="例: http://127.0.0.1:7890\n若直连 yfinance 无压力可留空")

# Main control area for analysis mode
col1, _, _ = st.columns([2, 2, 1]) # Adjust columns as only analysis_mode remains
with col1:
    analysis_mode = st.selectbox("🧠 分析模式", ['Wyckoff Analysis', 'Volume Profile'])

with st.container():
    c_btn1, c_btn2, _ = st.columns([1, 1, 4])
    with c_btn1:
        if st.button("🚀 开始巡航"):
            st.session_state['is_cruising'] = True
            # 将代理保存到 session 以便后续抓取取用
            if proxy_url.strip():
                st.session_state['proxies'] = {'http': proxy_url.strip(), 'https': proxy_url.strip()}
            else:
                st.session_state['proxies'] = None
    with c_btn2:
        if st.button("🛑 停止巡航", key='stop_btn'):
            st.session_state['is_cruising'] = False

st.divider()

# --- 主体渲染与分析执行区 ---
if st.session_state.get('is_cruising', False):
    
    # 获取实时流数据
    proxies = st.session_state.get('proxies', None)
    with st.spinner('哨兵正在初始化高维度数据流...'):
        df_raw = fetch_market_data(target_symbol, target_timeframe, limit=250, proxies=proxies)
    
    if df_raw.empty:
        st.error("❌ **连接交易所失败！连续检索不到数据。** \n\n 可能原因：\n1. 网络或地域限制 (部分交易所封锁 US  IP)\n2. 代理设置有误 (请在顶部配置正确的代理地址)\n3. 交易对在当前交易所不存在\n\n*请检查终端 (Terminal) 的具体报错日志。*")
        
        # 冷却 15 秒后重试，避免被无脑 Ban
        time.sleep(15)
        st.rerun()
    else:
        # 进入核心算法层
        phase = "等待扫描..."
        if analysis_mode == 'Wyckoff Analysis':
            df_analyzed, summary = analyze_wyckoff(df_raw)
            
            # 布局: 3/4给图表, 1/4给数据
            c_plot, c_data = st.columns([3, 1])
            
            with c_plot:
                # Plotly 画布搭建
                fig = go.Figure()
                
                # Candlesticks
                fig.add_trace(go.Candlestick(
                    x=df_analyzed.index,
                    open=df_analyzed['open'], high=df_analyzed['high'],
                    low=df_analyzed['low'], close=df_analyzed['close'],
                    name='Price'
                ))
                
                # Volume
                vol_colors = ['rgba(239, 83, 80, 0.7)' if row['close'] < row['open'] else 'rgba(38, 166, 154, 0.7)' 
                              for i, row in df_analyzed.iterrows()]
                fig.add_trace(go.Bar(
                    x=df_analyzed.index, y=df_analyzed['volume'],
                    marker_color=vol_colors, name='Volume', yaxis='y2'
                ))
                
                # 绘制支撑阻力线
                supp = summary['Support']
                res = summary['Resistance']
                if supp > 0 and res > 0:
                    fig.add_hline(y=supp, line_dash="solid", line_color="rgba(38, 166, 154, 0.5)", annotation_text=f"支撑位: {supp:.2f}")
                    fig.add_hline(y=res, line_dash="solid", line_color="rgba(239, 83, 80, 0.5)", annotation_text=f"压力位: {res:.2f}")
                
                # 算法捕捉的高潮锚点 (Spring/SOS)
                anomalies = df_analyzed[df_analyzed['Signal'] != '']
                for idx, row in anomalies.iterrows():
                    sig = row['Signal']
                    if 'Spring' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['low'] * 0.99], mode='markers+text',
                                                 marker=dict(symbol="triangle-up", color="#00FF00", size=15),
                                                 text=[sig], textposition="bottom center", name=sig))
                    elif 'SOS' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['high'] * 1.01], mode='markers+text',
                                                 marker=dict(symbol="star", color="#FFD700", size=15),
                                                 text=[sig], textposition="top center", name=sig))
                    else:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['low'] * 0.98 if 'Demand' in sig else row['high'] * 1.02], 
                                                 mode='markers', marker=dict(size=8, color="#AAAAAA"),
                                                 hoverinfo="text", hovertext=[sig], name="VSA"))

                # 布局美化 (紧凑型以适配 250 根横向拉伸)
                fig.update_layout(
                    template="plotly_dark",
                    height=650, margin=dict(l=10, r=40, t=10, b=10), # 留出右侧空间给标签
                    xaxis_rangeslider_visible=False,
                    xaxis=dict(rangebreaks=[dict(bounds=["sat", "mon"])]), # 可选：跳过周末无交易时段(如果是传统股票)，加密货币可忽略但 yfinance 会自带一些空隙跳过
                    yaxis=dict(title='Price (USDT)', domain=[0.25, 1], side='right'),
                    yaxis2=dict(domain=[0, 0.2], showticklabels=False),
                    showlegend=False
                )
                st.plotly_chart(fig)
                
            with c_data:
                st.subheader("📊 算法定性结果")
                
                conf_score = summary.get('Confidence', 0)
                phase = summary.get('Current Phase', '分析中')
                core_sig = summary.get('Core Signal', '无信号')
                trend = summary.get('Trend', '未知')
                res = summary.get('Resistance', 0.0)
                supp = summary.get('Support', 0.0)
                high_noise = summary.get('High Noise', False)
                
                if high_noise:
                    st.error("📉 **检测到高频震荡噪音，结构尚未稳固，禁止入场。**")
                
                # 1. 重构五阶评分模型 (Score Ranking) 视觉层
                if conf_score >= 86:
                    score_color = "🟢"
                    score_desc = "完美契合 (完善结构)"
                    score_status = "高胜率形态，机构行为完全显现。"
                elif conf_score >= 71:
                    score_color = "🟩"
                    score_desc = "确定性入场 (趋势确认)"
                    score_status = "趋势确认，主力开始发力。"
                elif conf_score >= 51:
                    score_color = "🟨"
                    score_desc = "结构成型 (等待验证)"
                    score_status = "已观察到关键信号，但缺乏量能验证。"
                elif conf_score >= 31:
                    score_color = "🟧"
                    score_desc = "震荡洗盘 (方向不明)"
                    score_status = "处于 Phase B 内部震荡，多空博弈激烈。"
                else:
                    score_color = "🟥"
                    score_desc = "极高风险 (噪音主导)"
                    score_status = "结构完全缺失或处于剧烈派发期，机构无介入迹象。"
                
                st.markdown(f"### {score_color} 哨兵置信度: **{conf_score}** / 100")
                st.caption(f"**{score_desc}**: {score_status}")
                
                st.divider()
                st.metric("现处威科夫阶段", phase)
                st.metric("核心判定特征", core_sig)
                st.metric("结构趋势", trend)
                
                st.divider()
                st.write(f"**上方层层抛压点**: `{res:.4f}`")
                st.write(f"**主力流动性底池**: `{supp:.4f}`")
                
                # --- 新增：哨兵研报 & 作战计划 ---
                st.subheader("🛡️ 哨兵研报 & 作战计划")
                plan = summary.get('Plan', {})
                entry_txt = f"`{plan.get('Entry', 0):.4f}`"
                sl_txt = f"`{plan.get('Stop Loss', 0):.4f}`"
                tp_txt = f"`{plan.get('Take Profit', 0):.4f}`"
                
                plan_markdown = f"""
                **执行位 (Entry)**: {entry_txt}  
                **防守位 (Stop Loss)**: {sl_txt}  
                **目标位 (Take Profit)**: {tp_txt} (1:2 盈亏比)
                """
                
                # --- 新增：强制性交易意见 (Actionable Boundaries) ---
                if conf_score < 50:
                    st.error(f"⛔ **严禁操作 (No Trade Zone)**\n\n当前评分仅为 {conf_score} 分，属于无效结构或高噪音区间，禁止执行任何交易指令。\n\n*请耐心等待结构发酵，保护本金。*")
                elif conf_score >= 70:
                    st.success(f"✅ **建议执行 (Actionable Zone)**\n\n当前评分高达 {conf_score} 分，威科夫结构已获得多维度确认，可按计划执行交易意见。\n{plan_markdown}")
                else:
                    st.warning(f"⚠️ **战术观察 (Tactical Zone)**\n\n当前评分为 {conf_score} 分。严禁追涨，仅限依托核心防守位挂单轻仓试探。\n{plan_markdown}")
                 
                st.divider()
                st.subheader("🤖 智脑研报 (LLM)")
                
                # --- 第二层架构：动态触发 LLM 深度解析 (降本稳健版) ---
                
                # 初始化记忆状态
                if 'last_analyzed_phase' not in st.session_state:
                    st.session_state['last_analyzed_phase'] = ""
                if 'last_analyzed_score' not in st.session_state:
                    st.session_state['last_analyzed_score'] = 0
                if 'last_llm_report' not in st.session_state:
                    st.session_state['last_llm_report'] = ""
                
                if 'last_email_time' not in st.session_state:
                    st.session_state['last_email_time'] = 0
                
                # 定义触发条件矩阵
                trigger_a = (st.session_state['last_analyzed_score'] < 70 and conf_score >= 70) # 首次达标
                trigger_b = (phase != st.session_state['last_analyzed_phase'] and conf_score >= 50) # 相位变更且不是极高噪音
                trigger_c = ('Spring' in core_sig or 'SOS' in core_sig) and (core_sig not in st.session_state.get('last_core_sig', '')) # 罕见重大信号首次出现
                
                # --- 智能化自动邮件预警逻辑 (独立于大模型触发，限制更严) ---
                current_time_sec = time.time()
                email_cooldown_passed = (current_time_sec - st.session_state['last_email_time']) >= 3600  # 60 分钟冷却
                
                if enable_email and receiver_email and conf_score >= 70:
                    # 只有在 60 分钟冷却完毕，或者发生了极其重大的结构切换时才发邮件
                    if email_cooldown_passed or trigger_b:
                        email_subject = f"🚨 [Sentinel API] {target_symbol} 侦测到巨鲸意图! ({core_sig})"
                        email_body = f"""
Wyckoff Sentinel - 自动作战指令下达
======================================
目标标的: {target_symbol} ({target_timeframe})
系统判定胜率: {conf_score} / 100
当前威科夫阶段: {phase}
核心触发特征: {core_sig}

--- 作战计划卡 ---
入场挂单位 (Entry): {plan.get('Entry', 0):.4f}
防守止损位 (Stop Loss): {plan.get('Stop Loss', 0):.4f}
目标止盈位 (Take Profit): {plan.get('Take Profit', 0):.4f}

这封邮件由 Wyckoff Sentinel 数学引警自动下发。
                        """
                        # 尝试发信
                        send_ok = send_signal_email(email_subject, email_body, receiver_email)
                        if send_ok:
                            st.toast("🚨 已向终端下发跨端邮件报警！", icon="📧")
                            st.session_state['last_email_time'] = current_time_sec
                
                # 添加手动强制请求按钮
                force_trigger = st.button("🔄 手动强刷智脑解析 (无视冷却)", type="primary")
                
                if trigger_a or trigger_b or trigger_c or force_trigger:
                    trigger_reason = ""
                    if trigger_a: trigger_reason = "首次突破高潜分水岭"
                    elif trigger_b: trigger_reason = f"侦测到相位切换至 {phase.split(' ')[0]}"
                    elif trigger_c: trigger_reason = "捕捉到极罕见洗盘/突破高潮信号"
                    elif force_trigger: trigger_reason = "指挥官最高权限强刷"
                    
                    with st.spinner(f"🧠 {trigger_reason}，正在连线大模型深度解析庄家意图..."):
                        llm_report = generate_llm_report(target_symbol, summary, force=force_trigger)
                        
                        # 更新记忆
                        st.session_state['last_analyzed_phase'] = phase
                        st.session_state['last_analyzed_score'] = conf_score
                        st.session_state['last_core_sig'] = core_sig
                        st.session_state['last_llm_report'] = llm_report
                        
                        st.info(llm_report)
                else:
                    if st.session_state['last_llm_report']:
                        st.info(st.session_state['last_llm_report'])
                        st.caption("📡 **[缓存]** 结构稳定，暂无重大相变，研报30分钟有效期内。")
                    else:
                        st.caption("📡 **[算法监控中]** 结构尚未达到阈值或未发生实质相变，暂不调用智脑生成深度研报 (省流防噪模式)。")
                
                st.divider()
                st.subheader("📝 阶段形态细解")
                
                # --- 新增：名词百科 ---
                st.divider()
                st.subheader("📖 威科夫名词百科")
                with st.expander("👉 查看当前信号/阶段解析", expanded=True):
                    if 'Phase D' in phase:
                        st.write("**Phase D (拉升前夕)**：主力已完成洗盘，价格正在测试区间顶部压力，准备跳跃小溪 (Jump Across the Creek)。")
                    if 'Phase E' in phase:
                        st.write("**Phase E (脱离区间)**：价格已经成功突破了震荡吸筹区域，正在进入毫无阻力的主升浪趋势中。")
                    if 'Phase C' in phase or 'Spring' in core_sig:
                        st.write("**Phase C / Spring (终极测试)**：主力在拉升前故意跌破前期支撑线，制造恐慌诱空，随后缩量快速拉回，确认底部已无抛压。")
                    if 'Phase A' in phase:
                        st.write("**Phase A (停止行为)**：在一段猛烈的趋势后出现异常的巨量，但价格未能继续推升，代表主力开始介入停止此前趋势。")
                    if 'Phase B' in phase:
                        st.write("**Phase B (建立结构)**：主力在特定的价格区间内进行漫长的吸筹或派发周期，为下一轮大级别行情构建供求关系的原因。")
                    if 'SOS' in core_sig:
                        st.write("**SOS (强者出现)**：多头放量突破，阳线实体大且收盘在高位，代表趋势由弱转强或确认主升浪的关键转折。")
                    if 'Supply' in core_sig:
                        st.write("**Supply Coming In (供应涌现)**：在突破重要阻力区时虽然放出巨量，但 K 线实体很小，说明遭遇到了庞大的隐蔽抛压阻击。")
                
                st.caption(f"上次全息扫描: {time.strftime('%H:%M:%S')}")
                
        else:
            st.info("Volume Profile 模式模块正在建设中... 请切换回 Wyckoff Analysis。")
            
    # 让当前指令流卡住挂机，定时重扫
    time.sleep(60)
    st.rerun()

else:
    st.info("哨兵处于休眠状态... 请在其上方配置您的导弹制导级别并点击[🚀 开始巡航]。")
