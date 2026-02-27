import re

path = r"c:\Users\wongs\.gemini\antigravity\scratch\wyckoff-lens\app.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern bounds
start_str = '            with c_data:\n                st.subheader("📊 算法定性结果")'
end_str = '                st.caption(f"上次全息扫描: {time.strftime(\'%H:%M:%S\')}")'

if start_str not in content or end_str not in content:
    print("Error: Could not find bounds.")
    import sys
    sys.exit(1)

start_idx = content.find(start_str)
end_idx = content.find(end_str) + len(end_str)

new_content = """            with c_data:
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
                
                # --- 计算持仓目标 (包括 Timeframe 扣除) ---
                if conf_score >= 90: base_pos = 100
                elif conf_score >= 80: base_pos = 60
                elif conf_score >= 70: base_pos = 30
                else: base_pos = 0
                
                tf_coef = {"1h": 0.5, "4h": 0.8, "1d": 1.0}.get(target_timeframe, 1.0)
                target_pos_pct = int(base_pos * tf_coef)
                
                if high_noise or conf_score < 70:
                    target_pos_pct = 0

                # --- 1. 形态判定 ---
                st.markdown("**1. [形态判定]**")
                st.markdown(f"## **{phase}**")
                
                # --- 2. 判定依据 ---
                sigs = [s.strip() for s in core_sig.split() if s.strip()]
                sig_text = "，".join(sigs) if sigs and core_sig != "No Recent Phase Change" else "无明显核心特征"
                st.markdown("**2. [判定依据]**")
                st.markdown(f"- **核心特征**: {sig_text}\\n- **量价配合**: 趋势为 {trend}，压力位 `{res:.4f}`，支撑位 `{supp:.4f}`")
                
                # --- 3. 拟合评分 ---
                st.markdown(f"**3. [拟合评分]: {conf_score} / 100**")
                st.progress(conf_score / 100.0)
                
                # --- 4. 交易决策 ---
                st.markdown("**4. [交易决策]**")
                if high_noise or conf_score < 70:
                    action_text = "⚪ **不进行操作**"
                    reason = " *(高频噪音冻结)*" if high_noise else " *(评分未达 70 阈值)*"
                    st.markdown(f"{action_text}{reason}")
                else:
                    action_text = "🟢 **做多 (Long)**" if long_score >= short_score else "🔴 **做空 (Short)**"
                    st.markdown(f"{action_text}")
                
                # --- 5. 仓位策略 ---
                st.markdown("**5. [仓位策略]**")
                entry_p = plan.get('Entry', 0)
                sl_p = plan.get('Stop Loss', supp * 0.99)
                tp_p = plan.get('Take Profit', 0)
                
                st.markdown(f"- **目标持仓比例**: **{target_pos_pct}%** *(基准 {base_pos}%, {target_timeframe} 折算 {tf_coef}x)*")
                if target_pos_pct > 0:
                    st.markdown(f"- **Entry**: `{entry_p:.4f}`\\n- **SL (风险锁定)**: `{sl_p:.4f}`\\n- **TP (1.618 扩展)**: `{tp_p:.4f}`")
                else:
                    st.markdown(f"- **Entry / SL / TP**: 暂无")
                
                # --- 智能化自动邮件预警逻辑 (后台静默) ---
                if 'last_analyzed_phase' not in st.session_state:
                    st.session_state['last_analyzed_phase'] = ""
                if 'last_analyzed_score' not in st.session_state:
                    st.session_state['last_analyzed_score'] = 0
                if 'last_email_time' not in st.session_state:
                    st.session_state['last_email_time'] = 0
                if 'last_target_pos_pct' not in st.session_state:
                    st.session_state['last_target_pos_pct'] = target_pos_pct
                
                trigger_pos_change = (target_pos_pct != st.session_state['last_target_pos_pct'])
                if trigger_pos_change:
                    st.session_state['last_target_pos_pct'] = target_pos_pct
                
                trigger_b = (phase != st.session_state['last_analyzed_phase'] and conf_score >= 50)
                trigger_c = ('Spring' in core_sig or 'SOS' in core_sig) and (core_sig not in st.session_state.get('last_core_sig', ''))
                
                current_time_sec = time.time()
                email_cooldown_passed = (current_time_sec - st.session_state['last_email_time']) >= 3600
                
                if enable_email and receiver_email:
                    if email_cooldown_passed and (trigger_b or trigger_c or trigger_pos_change):
                        if target_pos_pct == 100:
                            email_subject = f"🔥 [满仓狙击] 哨兵得分突破 90，建议满仓执行 ({target_symbol})！"
                        elif target_pos_pct > pos_size:
                            email_subject = f"📈 [加仓警报] 哨兵得分攀升至 {conf_score}，目标仓位调至 {target_pos_pct}%！"
                        elif target_pos_pct < pos_size:
                            email_subject = f"📉 [减仓警报] 风控启动！得分已降至 {conf_score}，建议将仓位缩紧至 {target_pos_pct}%！"
                        else:
                            email_subject = f"🚨 [Sentinel API] {target_symbol} 侦测到巨鲸连续异动! ({core_sig})"
                            
                        if plan.get('RR_Ratio', 0) > 2.0 and target_pos_pct >= 30:
                             email_subject = f"⭐ [强烈建议操作] {email_subject} (R:R Ratio = {plan.get('RR_Ratio', 0):.2f})"
                             
                        email_body = f\"\"\"
Wyckoff Sentinel - 最新作战雷达与仓位调度指令
======================================
目标标的: {target_symbol} ({target_timeframe})
系统判定胜率: {conf_score} / 100
当前威科夫阶段: {phase}
目标仓位建议: 调整至 {target_pos_pct}% (当前实仓为 {pos_size}%)

本次信号源自 {target_timeframe} 级别，侦测主导方向为 {dominant_direction}。
======================================
核心触发特征: {core_sig}
当前盈亏比 (R:R Ratio): {plan.get('RR_Ratio', 0):.2f}

--- 防守风险锁定 ---
防守止损位动态锁定 (Risk Lock SL): {sl_p:.4f}
扩展目标位 (1.618 TP): {tp_p:.4f}

该指令由 Wyckoff Sentinel 动态调仓引擎自动下发。
                        \"\"\"
                        send_ok = send_signal_email(email_subject, email_body, receiver_email)
                        if send_ok:
                            st.toast("🚨 仓位变动 - 已向下发跨端邮件报警！", icon="📧")
                            st.session_state['last_email_time'] = current_time_sec
                
                st.session_state['last_analyzed_phase'] = phase
                st.session_state['last_analyzed_score'] = conf_score
                st.session_state['last_core_sig'] = core_sig
                
                st.caption(f"上次全息扫描: {time.strftime('%H:%M:%S')}")"""

content = content[:start_idx] + new_content + content[end_idx:]

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Refactor complete.")
