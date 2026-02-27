import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import time
from sentinel import fetch_market_data, analyze_wyckoff, send_signal_email

# 页面配置
st.set_page_config(page_title="Wyckoff Sentinel", layout="wide")

# 主界面标题
st.title("🛡️ Wyckoff Sentinel: 数据与算法全息看板")
st.markdown("抛弃基于图片的非确定性预测，利用 Python 实施 **纯数据量价解析**。")

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

# Main control area for analysis mode
col1, _, _ = st.columns([2, 2, 1]) # Adjust columns as only analysis_mode remains
with col1:
    analysis_mode = st.selectbox("🧠 分析模式", ['Wyckoff Analysis', 'Volume Profile'])

with st.container():
    c_btn1, c_btn2, _ = st.columns([1, 1, 4])
    with c_btn1:
        if st.button("🚀 开始巡航"):
            st.session_state['is_cruising'] = True
            # 无代理
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
        
    # 位置预留 (原持仓盈亏追踪已移除)
    if df_raw.empty:
        st.error("❌ **连接交易所失败！连续检索不到数据。** \n\n 可能原因：\n1. 网络或地域限制 (部分交易所封锁 US  IP)\n2. 代理设置有误 (请在顶部配置正确的代理地址)\n3. 交易对在当前交易所不存在\n\n*请检查终端 (Terminal) 的具体报错日志。*")
        
        # 冷却 15 秒后重试，避免被无脑 Ban
        time.sleep(15)
        st.rerun()
    else:
        # 进入核心算法层
        phase = "等待扫描..."
        if analysis_mode == 'Wyckoff Analysis':
            df_analyzed, summary = analyze_wyckoff(df_raw, target_symbol)
            
            # 布局: 3:1
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

                # 图表用户持仓线已被移除，只展示系统分析线
                
                # 算法捕捉的高潮锚点 (Spring/SOS/LPS/UT)
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
                    elif 'LPS' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['low'] * 0.995], mode='markers+text',
                                                 marker=dict(symbol="triangle-up", color="#32CD32", size=10),
                                                 text=["LPS"], textposition="bottom center", name="LPS"))
                    elif 'UT' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['high'] * 1.005], mode='markers+text',
                                                 marker=dict(symbol="triangle-down", color="#FF4500", size=12),
                                                 text=["UT"], textposition="top center", name="UT"))
                    elif 'SC' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['low'] * 0.995], mode='markers+text',
                                                 marker=dict(symbol="star", color="#00BFFF", size=14),
                                                 text=["SC"], textposition="bottom center", name="SC"))
                    elif 'BC' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['high'] * 1.005], mode='markers+text',
                                                 marker=dict(symbol="star", color="#FF1493", size=14),
                                                 text=["BC"], textposition="top center", name="BC"))
                    elif 'JAC' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['low'] * 0.995], mode='markers+text',
                                                 marker=dict(symbol="triangle-up", color="#00FA9A", size=14),
                                                 text=["JAC"], textposition="bottom center", name="JAC"))
                    elif 'SOW' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['high'] * 1.005], mode='markers+text',
                                                 marker=dict(symbol="triangle-down", color="#8B0000", size=14),
                                                 text=["SOW"], textposition="top center", name="SOW"))
                    elif 'PSY' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['high'] * 1.005], mode='markers+text',
                                                 marker=dict(symbol="star-triangle-down", color="#FFA500", size=12),
                                                 text=["PSY"], textposition="top center", name="PSY"))
                    elif 'AR' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['high'] * 1.005], mode='markers+text',
                                                 marker=dict(symbol="triangle-up", color="#00FFFF", size=10),
                                                 text=["AR"], textposition="top center", name="AR"))
                    elif 'ST' in sig:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['low'] * 0.995], mode='markers+text',
                                                 marker=dict(symbol="triangle-up", color="#FFD700", size=10),
                                                 text=["ST"], textposition="bottom center", name="ST"))
                    else:
                        fig.add_trace(go.Scatter(x=[idx], y=[row['low'] * 0.98 if 'Demand' in sig else row['high'] * 1.02], 
                                                 mode='markers', marker=dict(size=8, color="#AAAAAA"),
                                                 hoverinfo="text", hovertext=[sig], name="VSA"))

                # --- 动态系统推荐的 TP / SL 投影 (针对还未入场的研判) ---
                if summary.get('Plan'):
                    sys_sl = summary['Plan'].get('Stop Loss', 0)
                    sys_tp_dict = summary['Plan'].get('Take Profit', {})
                    if sys_sl > 0:
                        fig.add_hline(y=sys_sl, line_dash="dash", line_color="red", annotation_text=f"系统推荐防守 SL: {sys_sl:.2f}")
                    
                    if isinstance(sys_tp_dict, dict):
                        if '0.618' in sys_tp_dict:
                            fig.add_hline(y=sys_tp_dict['0.618'], line_dash="dot", line_width=1, line_color="rgba(0, 255, 0, 0.5)", annotation_text="TP1 (0.618)")
                        if '1.0' in sys_tp_dict:
                            fig.add_hline(y=sys_tp_dict['1.0'], line_dash="dot", line_width=1, line_color="rgba(0, 255, 0, 0.5)", annotation_text="TP2 (1.0)")
                        if '1.618' in sys_tp_dict:
                            fig.add_hline(y=sys_tp_dict['1.618'], line_dash="solid", line_width=2, line_color="rgba(0, 255, 0, 0.8)", annotation_text="终极目标 TP3 (1.618)")
                    elif isinstance(sys_tp_dict, (int, float)) and sys_tp_dict > 0:
                        fig.add_hline(y=sys_tp_dict, line_dash="dash", line_color="green", annotation_text=f"系统1.618扩展 TP: {sys_tp_dict:.2f}")

                # 布局美化
                fig.update_layout(
                    template="plotly_dark",
                    height=550, margin=dict(l=0, r=0, t=30, b=0),
                    xaxis_rangeslider_visible=False,
                    xaxis=dict(rangebreaks=[dict(bounds=["sat", "mon"])]), # 可选：跳过周末无交易时段(如果是传统股票)，加密货币可忽略但 yfinance 会自带一些空隙跳过
                    yaxis=dict(title='Price (USDT)', domain=[0.25, 1], side='right'),
                    yaxis2=dict(domain=[0, 0.2], showticklabels=False),
                    showlegend=False
                )
                st.plotly_chart(fig)
                
            with c_data:
                # --- 取值 ---
                long_score = summary.get('Long Confidence', 0)
                short_score = summary.get('Short Confidence', 0)
                conf_score = max(long_score, short_score)
                dominant_direction = summary.get('Plan', {}).get('Direction', 'Long')
                
                phase = summary.get('Current Phase', '分析中')
                core_sig = summary.get('Core Signal', '无信号')
                trend = summary.get('Trend', '未知')
                res = summary.get('Resistance', 0.0)
                supp = summary.get('Support', 0.0)
                high_noise = summary.get('High Noise', False)
                plan = summary.get('Plan', {})
                
                # --- 计算置信分布与交易评分 ---
                conf_score = max(long_score, short_score)
                rr_factor = min(plan.get('RR_Ratio', 0), 3.0) / 3.0 * 100
                decision_score = int(conf_score * 0.7 + rr_factor * 0.3)

                # --- 1. 形态判定 ---
                st.markdown("**1. [形态判定]**")
                # Phase 字符串在 sentinel 中已经根据方向渲染完毕 (如 Phase A: 多头趋势停止)
                st.markdown(f"## **{phase}**")
                
                # --- 2. 判定依据 ---
                sigs = [s.strip() for s in core_sig.split() if s.strip()]
                sig_text = "，".join(sigs) if sigs and core_sig != "No Recent Phase Change" else "无明显核心特征"
                
                # Dynamic Explanatory Text Generator
                explanation = ""
                if 'BC' in core_sig:
                    explanation += f"判定为 BC (抢购高潮)。由于价格触及压力位 `{res:.4f}` 时伴随巨量长上影线，证明散户买盘已被机构供应吞没，上涨动力枯竭。"
                elif 'SC' in core_sig:
                    explanation += f"判定为 SC (卖出高潮)。由于价格触及支撑位 `{supp:.4f}` 时暴出天量且伴随长下影线，代表恐慌盘涌出被机构多头全部承接，空头能量极速耗尽。"
                elif 'AR' in core_sig:
                    explanation += f"判定为 AR (自动反弹/回落)，确立了震荡区间的核心边界 (下轨 `{supp:.4f}` / 上轨 `{res:.4f}`)。"
                elif 'PSY' in core_sig:
                    explanation += "判定为 PSY (初步供应/需求)，处于趋势末端，预示有庞大的相反量能开始暗中介入拦截现有趋势。"
                elif 'Spring' in core_sig:
                    explanation += "判定为 Spring (弹簧假跌破)。价格跌破支撑位后极速缩量并快速收回，洗出最后的不坚定筹码，确认底部有效。"
                elif 'SOS' in core_sig:
                    explanation += "判定为 SOS (强者出现)。结构性放量并产生真正的向上突破，彻底击穿原有压力区。"
                
                st.markdown("**2. [判定依据]**")
                st.markdown(f"- **核心特征**: {sig_text}")
                if explanation:
                    st.markdown(f"  - *{explanation}*")
                st.markdown(f"- **量价配合**: 趋势为 {trend}，压力位 `{res:.4f}`，支撑位 `{supp:.4f}`")
                
                # --- 3. 形态拟合分 (S_Pattern) ---
                st.markdown(f"**3. [形态拟合分]: {conf_score} / 100**")
                st.progress(conf_score / 100.0)
                
                # --- 4. 交易决策及置信评分 (S_Decision) ---
                st.markdown("**4. [交易决策及置信评分]**")
                
                system_says_short = dominant_direction == 'Short'
                system_says_long = dominant_direction == 'Long'

                if high_noise:
                    action_text = "⚪ **不进行操作**"
                    st.markdown(f"{action_text} *(高频噪音冻结)*")
                    st.progress(0.0)
                else:
                    color = "red" if system_says_short else "green"
                    action_dir = "做空 (Short)" if system_says_short else "做多 (Long)"
                    
                    if decision_score >= 80:
                         action_text = f"**强烈建议{action_dir} (High Confidence)**"
                         icon = "🔴" if system_says_short else "🟢"
                         bar_color = "red" if system_says_short else "green"
                    elif decision_score >= 60:
                         action_text = f"**建议{action_dir} (Moderate Confidence)**"
                         icon = "🟡"
                         bar_color = "orange"
                    else:
                         action_text = "**暂无高价值机会 (Low Confidence)**"
                         icon = "⚪"
                         bar_color = "gray"
                         
                    st.markdown(f"{icon} {action_text} | 置信评分: **{decision_score}/100**")
                    # Streamlit progress bar won't take color directly by keyword easily unless using HTML, 
                    # but we can standardise progress value.
                    st.progress(decision_score / 100.0)
                
                # --- 5. 作战计划图示 ---
                st.markdown("**5. [作战计划图示]**")
                entry_p = plan.get('Entry', 0)
                sl_p = plan.get('Stop Loss', supp * 0.99)
                tp_dict = plan.get('Take Profit', {})
                
                if decision_score >= 60:
                    st.markdown(f"- **Entry (进场位)**: `{entry_p:.4f}`")
                    st.markdown(f"- **SL (风险锁定)**: `{sl_p:.4f}`")
                    
                    if isinstance(tp_dict, dict) and '1.618' in tp_dict:
                         try:
                             tp1, tp2, tp3 = tp_dict['0.618'], tp_dict['1.0'], tp_dict['1.618']
                             st.markdown(f"- **TP1 (0.618)**: `{tp1:.4f}`")
                             st.markdown(f"- **TP2 (1.000)**: `{tp2:.4f}`")
                             st.markdown(f"- **TP3 (1.618)**: `{tp3:.4f}`")
                         except Exception as e:
                             st.markdown(f"- **TP**: Error parsing dict {e}")
                    else:
                        st.markdown(f"- **TP (扩展)**: `{tp_dict:.4f}`" if isinstance(tp_dict, (int, float)) else "- **TP**: 未定义")
                else:
                    st.markdown(f"- **Entry / SL / TP**: 分数不足，未下达有效指引")
                
                # --- 智能化自动邮件预警逻辑 (后台静默) ---
                if 'last_analyzed_phase' not in st.session_state:
                    st.session_state['last_analyzed_phase'] = ""
                if 'last_analyzed_score' not in st.session_state:
                    st.session_state['last_analyzed_score'] = 0
                if 'last_email_time' not in st.session_state:
                    st.session_state['last_email_time'] = 0
                
                trigger_b = (phase != st.session_state['last_analyzed_phase'] and decision_score >= 60)
                trigger_c = ('Spring' in core_sig or 'SOS' in core_sig) and (core_sig not in st.session_state.get('last_core_sig', ''))
                
                current_time_sec = time.time()
                email_cooldown_passed = (current_time_sec - st.session_state['last_email_time']) >= 3600
                
                if enable_email and receiver_email:
                    if email_cooldown_passed and (trigger_b or trigger_c):
                        if decision_score >= 80:
                            email_subject = f"🔥 [高置信狙击] 决断得分极高 ({decision_score})，建议执行 ({target_symbol})！"
                        else:
                            email_subject = f"🚨 [Sentinel API] {target_symbol} 侦测到主链级信号! ({core_sig})"
                            
                        email_body = f"""
Wyckoff Sentinel - 最新客观雷达解析结论
======================================
目标标的: {target_symbol} ({target_timeframe})
系统判定胜率: {decision_score} / 100
当前威科夫阶段: {phase}

本次信号源自 {target_timeframe} 级别，侦测主导方向为 {dominant_direction}。
======================================
核心触发特征: {core_sig}
当前盈亏比 (R:R Ratio): {plan.get('RR_Ratio', 0):.2f}

--- 防守风险锁定 ---
防守止损位动态锁定 (Risk Lock SL): {sl_p:.4f}
扩展目标位 (1.618 TP): {tp_p:.4f}

该指令由 Wyckoff Sentinel 动态调仓引擎自动下发。
                        """
                        send_ok = send_signal_email(email_subject, email_body, receiver_email)
                        if send_ok:
                            st.toast("🚨 仓位变动 - 已向下发跨端邮件报警！", icon="📧")
                            st.session_state['last_email_time'] = current_time_sec
                
                st.session_state['last_analyzed_phase'] = phase
                st.session_state['last_analyzed_score'] = conf_score
                st.session_state['last_core_sig'] = core_sig
                
                st.caption(f"上次全息扫描: {time.strftime('%H:%M:%S')}")
                
        else:
            st.info("Volume Profile 模式模块正在建设中... 请切换回 Wyckoff Analysis。")
            
    # 让当前指令流卡住挂机，定时重扫
    time.sleep(60)
    st.rerun()

else:
    st.info("哨兵处于休眠状态... 请在其上方配置您的导弹制导级别并点击[🚀 开始巡航]。")
