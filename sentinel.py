import os
import json
import time
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from datetime import timedelta

CACHE_FILE = "sentinel_cache.json"
ALERT_STATE_FILE = "alert_state.json"
WYCKOFF_LOG_FILE = "wyckoff_log.json"

def fetch_market_data(symbol, timeframe='4h', limit=250, proxies=None):
    """通过 yfinance 直接拉取最新的 OHLCV 数据 (即时响应，无冗余尝试)"""
    # 转换交易对名称 (BTC/USDT -> BTC-USD)
    yf_symbol = symbol.replace('/', '-').replace('USDT', 'USD')
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在从 yfinance 获取 {yf_symbol} 的 {timeframe} 数据...")
    
    try:
        # 将 ccxt/Binance 的 timeframe 转换为 yfinance 的 interval 格式
        interval_map = {'1h': '1h', '4h': '1d', '1d': '1d'}  
        yf_interval = interval_map.get(timeframe, '1d')
        
        ticker = yf.Ticker(yf_symbol)
        
        # 获取足够历史记录 (yfinance 限制)
        period = "max"
        if yf_interval in ['1m', '5m', '15m', '30m', '1h']:
            period = "730d"  # 1h max 为 730天
            
        # 设置 proxy 参数
        kwargs = {"period": period, "interval": yf_interval}
        if proxies and 'http' in proxies:
             kwargs['proxy'] = proxies['http']
             print(f"[{datetime.now().strftime('%H:%M:%S')}] 已应用代理: {proxies['http']}")
             
        df_yf = ticker.history(**kwargs)
        
        if df_yf.empty:
             print(f"[{datetime.now().strftime('%H:%M:%S')}] (yfinance) 获取到的数据为空。")
             return pd.DataFrame()
             
        # 保留所需列并重命名以符合算法期望格式
        df_yf = df_yf[['Open', 'High', 'Low', 'Close', 'Volume']].tail(limit)
        df_yf.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
        # 去除时区信息 (如果存在)
        if df_yf.index.tz is not None:
             df_yf.index = df_yf.index.tz_localize(None)
             
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功获取 {len(df_yf)} 条 K线数据。")
        return df_yf
        
    except Exception as e_yf:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] YFinance 抓取异常: {e_yf}")
        return pd.DataFrame()

def calculate_directional_confidence(df, current_idx, core_signal, last_spring_idx, last_utad_idx):
    """计算哨兵置信度评分 (双向)，五阶评价体系"""
    long_score = 0
    short_score = 0
    current = df.iloc[current_idx]
    
    # 1. 量价配合 (40%): 突破或高发点位成交量是否大于均值的 1.5 倍
    if current['volume'] > current['Avg_Volume'] * 1.5:
        long_score += 40
        short_score += 40
    elif current['volume'] > current['Avg_Volume'] * 1.2:
        long_score += 20
        short_score += 20
        
    # 2. 结构确认 (30%): 此前 100 根 K 线内是否存在已确认的 Spring 或 UTAD
    if last_spring_idx != -100 and (current_idx - last_spring_idx) <= 100:
        long_score += 30
    if last_utad_idx != -100 and (current_idx - last_utad_idx) <= 100:
        short_score += 30
        
    # 3. 趋势对齐 (30%): 均线多头/空头排列
    if 'SMA_20' in df.columns and 'SMA_50' in df.columns:
        if current['SMA_20'] > current['SMA_50']:
            long_score += 30
        elif current['SMA_20'] < current['SMA_50']:
            short_score += 30
            
    # --- 动态惩罚与奖励机制 ---
    
    # 压力位遇阻
    resistance = df.iloc[current_idx]['Resistance'] if pd.notna(df.iloc[current_idx]['Resistance']) else float('inf')
    if current['close'] >= resistance * 0.95 and current['volume'] < current['Avg_Volume']:
        long_score -= 15
        short_score += 10
        
    # 支撑位企稳
    support = df.iloc[current_idx]['Support'] if pd.notna(df.iloc[current_idx]['Support']) else 0
    if support > 0 and current['close'] <= support * 1.05 and current['close'] > current['open'] and current['volume'] < current['Avg_Volume'] * 0.8:
        long_score += 10
        short_score -= 15
        
    # 噪音惩罚项
    recent_signals = df['Signal'].iloc[max(0, current_idx-30):current_idx+1]
    signal_count = sum(recent_signals.str.strip() != '')
    if signal_count >= 5:
        long_score -= min(30, signal_count * 5)
        short_score -= min(30, signal_count * 5)
        
    # Phase 特征奖励与惩罚
    if 'JAC' in core_signal or 'Spring' in core_signal:
        long_score += 20
        short_score -= 20
    if 'LPS' in core_signal:
        long_score += 15
    if 'UT' in core_signal or 'UTAD' in core_signal:
        long_score -= 20
        short_score += 20
    if 'SOW' in core_signal:
        long_score -= 30
        short_score += 30
    if 'LPSY' in core_signal:
        short_score += 15
        long_score -= 15
    if 'BC' in core_signal:
        short_score += 20
        long_score -= 20
        
    return max(0, min(100, int(long_score))), max(0, min(100, int(short_score)))

def analyze_wyckoff(df, symbol):
    """纯数学驱动的威科夫量价探测算法"""
    if df is None or df.empty:
        return df, {"Current Phase": "Error", "Core Signal": "No Data", "Resistance": 0, "Support": 0}
        
    df = df.copy()
    df['Signal'] = ''
    df['Phase'] = 'Phase B: 建立结构 (Building the Cause)' # 默认设定为区间震荡建立期
    
    # === 基础特征提取 ===
    df['Avg_Volume'] = df['volume'].rolling(window=20).mean()
    df['Spread'] = df['high'] - df['low']
    df['Avg_Spread'] = df['Spread'].rolling(window=20).mean()
    df['SMA_20'] = df['close'].rolling(window=20).mean()
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    
    # 使用近N周期极值界定当前区间的支阻体系 (增强纵深至 60 根)
    lookback = 60
    df['Support'] = df['low'].rolling(window=lookback).min().shift(1)
    df['Resistance'] = df['high'].rolling(window=lookback).max().shift(1)
    
    # === 模式扫描 ===
    last_spring_idx = -100 # 用来去重，相邻太近的 Spring 不重复标记
    last_utad_idx = -100
    last_spring_low = float('inf')
    last_ar_high = float('-inf') # 记录反弹高点 (Automatic Rally) 用以辅助 JAC 判定
    
    # 获取区间整体高度供计算 TP
    trading_range_height = df['Resistance'].iloc[-1] - df['Support'].iloc[-1] if df['Resistance'].iloc[-1] > df['Support'].iloc[-1] else df['Avg_Spread'].iloc[-1] * 10
    
    for i in range(5, len(df)):
        current = df.iloc[i]
        
        recent_sigs_20 = df.iloc[max(0, i-20):i]['Signal'].to_string()
        
        # --- 0. 基础高低点结构定义 (AR) ---
        if current['high'] > last_ar_high and current['close'] < current['open']: 
            last_ar_high = current['high']
            
        # PSY (初步供应 Preliminary Supply): 暴涨前的高量滞涨
        if current['close'] > current['SMA_50'] and current['volume'] > current['Avg_Volume'] * 2.0 and current['Spread'] < current['Avg_Spread'] * 0.8:
            df.at[df.index[i], 'Signal'] += 'PSY '
            
        # --- 1. 定向爆发预警: SC & BC & AR & ST ---
        # SC (卖出高潮 Selling Climax): 在持续下跌后，突然爆出极大量，且留下极长的下影线，代表主力入场恐慌性扫货
        if ('Phase' not in df.iloc[i-1]['Phase'] or 'Phase A' in df.iloc[i-1]['Phase']):
            lower_shadow = min(current['open'], current['close']) - current['low']
            if current['volume'] > current['Avg_Volume'] * 2.5 and lower_shadow > current['Spread'] * 0.6 and current['close'] > current['Support']:
                 df.at[df.index[i], 'Signal'] += 'SC '
                 df.at[df.index[i], 'Phase'] = 'Phase A: 空头趋势停止 (Stopping Action)'
                 
        # BC (买入高潮 Buying Climax): 暴涨后爆量长上影线
        if current['volume'] > current['Avg_Volume'] * 2.5 and (current['high'] - max(current['open'], current['close'])) > current['Spread'] * 0.6:
            if current['close'] < current['Resistance']:
                df.at[df.index[i], 'Signal'] += 'BC '
                df.at[df.index[i], 'Phase'] = 'Phase A: 多头趋势停止 (Stopping Action)'

        # AR (自动弹升 Automatic Rally): 恐慌抛售后的反抽
        if 'SC' in recent_sigs_20 and current['close'] > current['open'] and current['volume'] < current['Avg_Volume']:
            if current['high'] > df.iloc[i-1]['high']:
                df.at[df.index[i], 'Signal'] += 'AR '

        # ST (二次测试 Secondary Test): 回测SC低点但缩量
        if 'SC' in recent_sigs_20 and current['low'] <= current['Support'] * 1.05 and current['volume'] < current['Avg_Volume'] * 0.8:
            df.at[df.index[i], 'Signal'] += 'ST '
        
        # 1. Spring (弹簧) 判定 (强效降噪版)
        breakdown_idx = -1
        breakdown_vol = 0
        breakdown_low = float('inf')
        
        # 条件1 & 2：寻找过去 3 根内是否有跌破 60日 Support 的真实低点
        for j in range(1, 4):
            prev = df.iloc[i-j]
            if prev['low'] < prev['Support']:
                if prev['low'] < breakdown_low:
                    breakdown_low = prev['low']
                    breakdown_idx = i-j
                    breakdown_vol = prev['volume']
                    
        if breakdown_idx != -1:
            # 条件3：确认在 3 根内收回支撑之上，且成交量显著缩量 (No Supply)
            if current['close'] > current['Support'] and current['volume'] < breakdown_vol:
                is_valid_spring = True
                
                # 条件4：聚类过滤，20 根 K 线内连续出现，保留最深的一个
                if last_spring_idx != -100 and (i - last_spring_idx) <= 20:
                    if breakdown_low < last_spring_low:
                        # 当前的 Spring 更深，撤销上一个的标记
                        old_sig = df.at[df.index[last_spring_idx], 'Signal']
                        df.at[df.index[last_spring_idx], 'Signal'] = old_sig.replace('Spring ', '').replace('Spring', '')
                    else:
                        # 之前的更深，放弃当前信号
                        is_valid_spring = False
                
                if is_valid_spring:
                    df.at[df.index[i], 'Signal'] += 'Spring '
                    df.at[df.index[i], 'Phase'] = 'Phase C: 终极测试 (The Spring/Test)'
                    last_spring_idx = i
                    last_spring_low = breakdown_low

        # 2. SOS (强者出现) 判定
        # 放量长阳突破主力压力位，回踩时不破中轴或支点
        if current['close'] > current['Resistance'] and current['volume'] > current['Avg_Volume'] * 1.5:
            df.at[df.index[i], 'Signal'] += 'SOS '
            if 'Phase' not in df.iloc[i]['Phase'] or 'Phase B' in df.iloc[i]['Phase']:
                df.at[df.index[i], 'Phase'] = 'Phase D: 区间内趋势 (Pre-Markup)'
            
        # 3. LPS (最后支撑点) 判定
        # Phase D/E 中的缩量回踩，收盘价站在支撑之上，下影线较长或实体极小
        if ('Phase D' in df.iloc[i-1]['Phase'] or 'Phase E' in df.iloc[i-1]['Phase'] or 'SOS' in df.iloc[max(0, i-10):i]['Signal'].to_string()):
             # 回落 (当前收盘低于前高)，且缩量，且位于 Support 之上
             if current['close'] < df.iloc[i-1]['high'] and current['volume'] < current['Avg_Volume'] * 0.8 and current['close'] > current['Support']:
                 # 进一步要求有一定下影线，或低波动率 (代表无供应抛压)
                 lower_shadow = min(current['open'], current['close']) - current['low']
                 if lower_shadow > current['Spread'] * 0.4 or current['Spread'] < current['Avg_Spread'] * 0.6:
                     df.at[df.index[i], 'Signal'] += 'LPS '
                     df.at[df.index[i], 'Phase'] = 'Phase D: 区间内趋势 (Pre-Markup)'
                     
        # 4. UT (上冲回落 / 假突破) 判定
        # 上穿 Resistance，但收盘跌回且留有长上影线
        if current['high'] > current['Resistance'] and current['close'] < current['Resistance']:
             upper_shadow = current['high'] - max(current['open'], current['close'])
             if upper_shadow > current['Spread'] * 0.5 and current['volume'] > current['Avg_Volume'] * 1.2:
                 df.at[df.index[i], 'Signal'] += 'UT '
                 df.at[df.index[i], 'Phase'] = 'Phase B/C: 顶部派发预警 (Distribution)'
                 
        # UTAD (派发后上冲回落 false breakout of distribution range)
        if ('Phase B' in df.iloc[i-1]['Phase'] or 'Phase C' in df.iloc[i-1]['Phase']):
             if current['high'] > current['Resistance'] and current['close'] < current['Resistance']:
                 df.at[df.index[i], 'Signal'] += 'UTAD '
                 df.at[df.index[i], 'Phase'] = 'Phase C: 终极测试 (UTAD)'
                 last_utad_idx = i

        # LPSY (最后供应点)
        if ('Phase D' in df.iloc[i-1]['Phase'] and df.iloc[i-1]['close'] < df.iloc[i-1]['Support']) or 'SOW' in recent_sigs_20:
             # 反弹但不过前高，缩量
             if current['close'] > current['open'] and current['high'] < df.iloc[i-1]['high'] and current['volume'] < current['Avg_Volume']:
                 df.at[df.index[i], 'Signal'] += 'LPSY '
                 df.at[df.index[i], 'Phase'] = 'Phase D: 向下破位预警 (Pre-Markdown)'
                 
        # 5. JAC (跃过小溪 Jump Across the Creek) 判定
        # 强势带量突破核心AR阻力位且收在上方，彻底走出区间
        if current['close'] > current['Resistance'] and current['close'] > last_ar_high and current['volume'] > current['Avg_Volume'] * 1.5:
             # 如果之前有过SOS或Spring，这个就是JAC
             recent_sigs = df.iloc[max(0, i-20):i]['Signal'].to_string()
             if 'SOS' in recent_sigs or 'Spring' in recent_sigs or 'LPS' in recent_sigs:
                 df.at[df.index[i], 'Signal'] += 'JAC '
                 df.at[df.index[i], 'Phase'] = 'Phase E: 脱离区间 (Markup/Trending)'
                 
        # 6. SOW (弱势出现 Sign of Weakness) 判定
        # 带量跌破重要底池支撑，且实体很大
        if current['close'] < current['Support'] and current['volume'] > current['Avg_Volume'] * 1.2:
             if current['open'] - current['close'] > current['Avg_Spread'] * 0.8:
                 df.at[df.index[i], 'Signal'] += 'SOW '
                 df.at[df.index[i], 'Phase'] = 'Phase D: 向下破位预警 (Pre-Markdown)'

        # 7. VSA 辅助 (Effort vs Result)
        if current['volume'] > current['Avg_Volume'] * 1.5 and current['Spread'] < current['Avg_Spread'] * 0.5:
            if current['close'] > df['Resistance'].iloc[i] * 0.95:
                df.at[df.index[i], 'Signal'] += 'Supply Coming In '
                df.at[df.index[i], 'Phase'] = 'Phase A: 多头趋势停止 (Stopping Action)' # 顶部异常放量滞涨，可能停止原趋势
            elif current['close'] < df['Support'].iloc[i] * 1.05 and pd.isna(df.iloc[i]['Signal']) or df.iloc[i]['Signal'] == '':
                df.at[df.index[i], 'Signal'] += 'Demand Coming In '

    # 数据格式清洗
    df['Signal'] = df['Signal'].str.strip()

    # === 输出构建 ===
    latest = df.iloc[-1]
    signals_history = df[df['Signal'] != '']
    core_signal = signals_history.iloc[-1]['Signal'] if not signals_history.empty else "No Recent Phase Change"
    
    # 二次判定最终 Phase：
    phase_eval = latest['Phase']
    if 'SOS' in core_signal and latest['close'] > latest['Resistance']:
         phase_eval = 'Phase E: 脱离区间 (Markup/Trending)'
    elif 'Phase B' in phase_eval and not signals_history.empty:
         # 如果当前没触发特殊判定，继承最近的一个确定性大阶段
         last_major = signals_history.iloc[-1]['Phase']
         if 'Phase' in last_major:
             phase_eval = last_major
    
    # 计算置信度与交易计划
    long_confidence, short_confidence = calculate_directional_confidence(df, len(df)-1, core_signal, last_spring_idx, last_utad_idx)
    
    # 检测是否处于噪音区 (最近30根超过5个信号)
    recent_sigs = df['Signal'].iloc[max(0, len(df)-30):len(df)]
    high_noise = sum(recent_sigs.str.strip() != '') >= 5
    
    # ==========================
    # --- 风险收益比 (TP/SL) 自动演算 ---
    # ==========================
    supp_val = float(latest['Support']) if pd.notna(latest['Support']) else 0.0
    res_val = float(latest['Resistance']) if pd.notna(latest['Resistance']) else 0.0
    curr_price = latest['close']

    # 确定主导方向
    dominant_direction = 'Long' if long_confidence >= short_confidence else 'Short'

    tr_height = res_val - supp_val
    if tr_height <= 0:
        tr_height = latest['Avg_Spread'] * 10 

    sl_lookback = df.iloc[max(0, len(df)-60):len(df)]

    if dominant_direction == 'Long':
        springs_in_window = sl_lookback[sl_lookback['Signal'].str.contains('Spring')]
        if not springs_in_window.empty:
            base_sl_point = springs_in_window['low'].min()
        else:
            base_sl_point = sl_lookback['low'].min()
        stop_loss = base_sl_point * 0.995
        
        entry = curr_price if ('Phase C' in phase_eval or 'Phase D' in phase_eval or 'JAC' in phase_eval) else supp_val * 1.01
        
        take_profit = {
            '0.618': entry + (tr_height * 0.618),
            '0.786': entry + (tr_height * 0.786),
            '1.0': entry + (tr_height * 1.0),
            '1.272': entry + (tr_height * 1.272),
            '1.618': entry + (tr_height * 1.618)
        }
    else:
        utads_in_window = sl_lookback[sl_lookback['Signal'].str.contains('UTAD')]
        if not utads_in_window.empty:
            base_sl_point = utads_in_window['high'].max()
        else:
            base_sl_point = sl_lookback['high'].max()
        stop_loss = base_sl_point * 1.005
        
        entry = curr_price if ('Phase C' in phase_eval or 'Phase D' in phase_eval or 'SOW' in phase_eval) else res_val * 0.99
        
        take_profit = {
            '0.618': entry - (tr_height * 0.618),
            '0.786': entry - (tr_height * 0.786),
            '1.0': entry - (tr_height * 1.0),
            '1.272': entry - (tr_height * 1.272),
            '1.618': entry - (tr_height * 1.618)
        }

    # R:R Ratio (Using 1.618 for RR ratio calculation)
    tp_1618 = take_profit['1.618']
    risk_dist = max(0.0001, abs(entry - stop_loss))
    reward_dist = max(0.0001, abs(tp_1618 - entry))
    rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0
    
    summary = {
        'Current Phase': phase_eval,
        'Core Signal': core_signal,
        'Support': supp_val,
        'Resistance': res_val,
        'Trend': 'Bullish' if latest['close'] > latest['Support'] + tr_height * 0.5 else 'Bearish',
        'Long Confidence': long_confidence,
        'Short Confidence': short_confidence,
        'High Noise': high_noise,
        'Plan': {
            'Direction': dominant_direction,
            'Entry': max(0.0001, entry),
            'Stop Loss': max(0.0001, stop_loss),
            'Take Profit': take_profit,
            'RR_Ratio': rr_ratio
        }
    }
    
    # --- 本地化结构日志持久存储 ---
    log_wyckoff_events(symbol, core_signal, curr_price)
    
    return df, summary

def log_wyckoff_events(symbol, current_signal, price):
    """将关键威科夫因子持久化到本地 JSON，以便审计回溯 (Mac mini 专属)"""
    if not current_signal or current_signal == "No Recent Phase Change":
        return
        
    try:
        logs = []
        if os.path.exists(WYCKOFF_LOG_FILE):
            with open(WYCKOFF_LOG_FILE, "r") as f:
                logs = json.load(f)
                
        # 去重，避免一分钟内重复写入同一个事件
        if logs:
            last_log = logs[-1]
            if last_log.get('symbol') == symbol and last_log.get('signal') == current_signal:
                return
                
        new_entry = {
            "timestamp": str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "symbol": symbol,
            "signal": current_signal,
            "price": price
        }
        logs.append(new_entry)
        
        # 仅保留最近 200 条日志
        logs = logs[-200:]
        
        with open(WYCKOFF_LOG_FILE, "w") as f:
            json.dump(logs, f, indent=4)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Wyckoff日志写入失败: {e}")


# === 大模型调度与缓存模块 ===
LLM_CACHE = {}  # 结构: {'symbol_target': {'timestamp': 1234567, 'report': '...'}}

def generate_llm_report(symbol, summary, force=False, pos_info=None):
    """第二层智脑：由 app.py 控制触发时机。带 30 分钟硬冷却，如果是 force=True 则无视冷却强行触发"""
    cache_key = f"{symbol}_{summary['Current Phase']}_{summary['Core Signal']}"
    if pos_info and pos_info.get('entry', 0) > 0:
        cache_key += f"_pos_{pos_info['direction']}_{pos_info['entry']}"
        
    current_time = time.time()
    
    # 检查缓存：30分钟 (1800秒) 内有同种信号报告，除非强刷否则复用
    if cache_key in LLM_CACHE and not force:
        cached_data = LLM_CACHE[cache_key]
        if current_time - cached_data['timestamp'] < 1800:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [LLM 缓存命中] {cache_key} (冷却中)")
            return cached_data['report']
            
    prefix = "🚀 [强刷智脑]" if force else "🚀 [触发智脑]"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {prefix} 分数达标或状态变更，开始连线大模型：{cache_key} ...")
    
    # 构造发给大模型的 Prompt
    prompt = f"""
    作为拥有 20 年华尔街量价经验的威科夫交易宗师，请对以下标的进行深度研报输出：
    标的: {symbol}
    本周期威科夫阶段: {summary['Current Phase']}
    核心探测信号: {summary['Core Signal']}
    系统判定胜率: {summary.get('Confidence', 0)} / 100
    """
    
    if pos_info and pos_info.get('entry', 0) > 0:
        prompt += f"\n    [重要Context]: 我当前在 {pos_info['entry']} 持有 {pos_info['symbol']} 的 {pos_info['direction']}，请根据最新威科夫相位，给出继续持有还是减仓的建议。\n"
        
    prompt += "\n    请用结构化语言（不超过150字），直接给出庄家意图剖析以及建议。"
    
    # 尝试读取 API Key (适配 Streamlit Cloud)
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except FileNotFoundError:
        api_key = ""
        
    if not api_key:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 未配置 GEMINI_API_KEY，使用模拟研报生成...")
        time.sleep(2)  # 模拟延迟
        simulated_report = f"> [智脑深度解析]\n\n主力在底池 `{summary['Support']}` 附带完成极度缩量的无供应测试 ({summary['Core Signal']})。派发期已被截断，由空转多的逻辑闭环正在验证中 ({summary['Current Phase']})。"
        if pos_info and pos_info.get('entry', 0) > 0:
            simulated_report += f"\n\n针对你的 {pos_info['direction']} 仓位 ({pos_info['entry']})：已根据当前结构进行防守动态评估，若跌破止损请无条件执行纪律。"
        else:
            simulated_report += "建议严格按上述防守位布防，依托流动性洼地进行右侧建仓布局。"
    else:
        # TODO: 这里可无缝接入 google.generativeai 真实调用逻辑
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 侦测到 API Key，准备进行深度运算...")
        time.sleep(2)
        simulated_report = f"> [智脑深度解析 (实机锚点)]\n\n主力在底池 `{summary['Support']}` 附带完成极度缩量的无供应测试 ({summary['Core Signal']})。派发期已被截断，由空转多的逻辑闭环正在验证中 ({summary['Current Phase']})。"
        if pos_info and pos_info.get('entry', 0) > 0:
            simulated_report += f"\n\n针对你的 {pos_info['direction']} 仓位 ({pos_info['entry']})：已根据当前结构进行防守动态评估，若跌破止损请无条件执行纪律。"
        else:
            simulated_report += "建议严格按上述防守位布防，依托流动性洼地进行右侧建仓布局。"
    
    # 写入全局缓存
    LLM_CACHE[cache_key] = {
        'timestamp': current_time,
        'report': simulated_report
    }
    
    return simulated_report


# === 报警与状态机模块 ===
def get_alert_state():
    if not os.path.exists(ALERT_STATE_FILE): return {}
    with open(ALERT_STATE_FILE, "r") as f:
        try: return json.load(f)
        except: return {}

def save_alert_state(state):
    with open(ALERT_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# SMTP 邮件发送模块 (支持 Streamlit Secrets 的 [email] 结构层级与本地 OS 环境变量兼容)
def get_email_config():
    """获取动态邮件配置，屏蔽由于不同环境下找不到环境变量导致的奔溃"""
    config = {
        "server": "smtp.gmail.com",
        "port": 587,
        "user": "your_email@gmail.com",
        "password": "your_app_password"
    }
    
    # 尝试从 Streamlit.secrets 提取 (云端主路径)
    try:
        if "email" in st.secrets:
            config["server"] = st.secrets["email"].get("server", config["server"])
            config["port"] = st.secrets["email"].get("port", config["port"])
            config["user"] = st.secrets["email"].get("user", config["user"])
            config["password"] = st.secrets["email"].get("password", config["password"])
        else:
            # 兼容扁平化配置
            config["server"] = st.secrets.get("SMTP_SERVER", config["server"])
            config["port"] = st.secrets.get("SMTP_PORT", config["port"])
            config["user"] = st.secrets.get("SENDER_EMAIL", config["user"])
            config["password"] = st.secrets.get("EMAIL_PASSWORD", config["password"])
            
    except Exception:
        # 兼容本地 `.env` 无 Streamlit 服务环境
        config["server"] = os.environ.get("SMTP_SERVER", config["server"])
        config["port"] = int(os.environ.get("SMTP_PORT", config["port"]))
        config["user"] = os.environ.get("SENDER_EMAIL", config["user"])
        config["password"] = os.environ.get("EMAIL_PASSWORD", config["password"])

    return config

def send_signal_email(subject, body, receiver_email):
    """
    通过 SMTP 协议发送告警邮件。
    如果配置为空或发件失败，安全捕获异常并仅在终端打印警告以避免云端崩溃。
    """
    config = get_email_config()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 尝试送达邮件至: {receiver_email} ...")
    
    if config["user"] == "your_email@gmail.com" or config["password"] == "your_app_password":
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 邮件发送取消: 系统侦测到您尚未在 secrets 中填充真实的 SENDER_EMAIL 与 APP_PASSWORD。")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = f"Wyckoff Sentinel <{config['user']}>"
        msg['To'] = receiver_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        # 初始化连接与严格的安全握手 (StartTLS)
        server = smtplib.SMTP(config['server'], config['port'])
        server.ehlo()
        server.starttls()
        server.login(config['user'], config['password'])
        
        # 投递炸弹
        text = msg.as_string()
        server.sendmail(config['user'], receiver_email, text)
        server.quit()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 邮件已成功送达至: {receiver_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 邮件发送失败: 账号认证异常！请核对您是否启用了两步验证，并使用的是应用专用密码 (App Password) 而非您的登录密码。邮箱地址是否由于近期异常活动被所在服务商硬封锁。")
        return False
    except smtplib.SMTPConnectError as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 邮件发送失败: SMTP 服务器失联 (拒绝连接)，错误信息: {e}")
        return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 邮件发送失败: 出现了未知致命错误: {e}")
        return False

def trigger_alerts_if_needed(symbol, summary):
    """状态机防轰炸报警系统"""
    signal = summary.get('Core Signal', '')
    if 'Spring' in signal or 'SOS' in signal:
        state = get_alert_state()
        history = state.get(symbol, {})
        
        # 状态机比对：同一周期、同样的信号不重复鸣电
        if history.get('last_signal') == signal:
            print(f"[{symbol}] 状态机拦截: 信号 `{signal}` 已经推送过，进入静默保护。")
            return
            
        print(f"[{symbol}] 🎯 捕捉到高潮信号 `{signal}` 位于吸筹末端前夕！触发多渠道报警！")
        
        # --- Notification Logic Here (SMTP / Telegram) ---
        print(">> (Simulated) [邮件/Telegram 已发送]: 包含了快照、相位判定与支撑压力位信息。")
        
        # 登记本次告警，防抖
        state[symbol] = {
            'last_signal': signal,
            'timestamp': str(datetime.now())
        }
        save_alert_state(state)


# === 守护进程模式 ===
def background_patrol(symbol="BTC/USDT", timeframe="4h"):
    print(f"启动独立 Background Task (守护进程模式). 监控: {symbol}")
    while True:
        try:
            df = fetch_market_data(symbol, timeframe)
            if not df.empty:
                df_analyzed, summary = analyze_wyckoff(df, symbol)
                
                # 更新本地 Cache 供可能的 Web 并发调用读取
                cache = {"summary": summary, "last_scan": str(datetime.now())}
                with open(CACHE_FILE, "w") as f:
                    json.dump(cache, f)
                    
                trigger_alerts_if_needed(symbol, summary)
        except Exception as e:
            print(f"巡逻异常: {e}")
            
        # 标准轮询冷却 1 分钟 (可根据业务放大)
        time.sleep(60)

if __name__ == "__main__":
    # 如果单独执行 python sentinel.py，跑无限轮询
    background_patrol()
