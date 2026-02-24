import streamlit as st
import google.generativeai as genai
from PIL import Image

# 1. 配置你的 Gemini API Key
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("❌ 未找到 API Key，请检查 Streamlit Secrets 设置。")
st.title("🔍 Wyckoff Lens: 机构行为分析站")

# 2. 页面设置 (UI)
st.set_page_config(page_title="Wyckoff Lens AI", layout="wide")
st.title("🔍 Wyckoff Lens: 机构行为分析站")
st.write("上传一张 K 线截图，让 AI 帮你识别威客夫阶段。")

# 3. 侧边栏设置
st.sidebar.header("参数设置")
model_choice = st.sidebar.selectbox("选择模型", ["gemini-2.5-flash", "gemini-2.0-flash"])

# 4. 上传组件
uploaded_file = st.file_uploader("点击或拖拽上传 K 线截图...", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # 显示图片
    image = Image.open(uploaded_file)
    st.image(image, caption='已上传的 K 线图', use_container_width=True)
    
    if st.button("开始威客夫深度分析"):
        with st.spinner('AI 正在扫描机构足迹，请稍候...'):
            try:
                # 5. 调用 AI 模型
                model = genai.GenerativeModel('gemini-2.5-flash')
                
                # 系统提示词：定义 AI 的专家身份
                prompt = """
                你是一位精通威客夫理论 (Wyckoff Theory) 和量价分析 (VSA) 的对冲基金首席策略师。你擅长通过裸 K 线和成交量识别“复合操作者 (Composite Man)”的足迹。

Task: 请深度扫描上传的 K 线截图，并基于以下逻辑进行多维解构：

威客夫三法则是核心：

供需法则： 当前是供过于求（放量下跌）还是供不应求（缩量回调）？

因果法则： 目前的震荡区间（Cause）是否有足够的量能支撑未来的趋势（Effect）？

努力与结果法则： 识别量价背离。例如：价格剧烈波动但量能极小，或天量成交但价格停滞。

结构化输出要求：

【市场阶段】：明确指出处于 Phase A（停止）、B（建仓）、C（测试）、D（趋势起始）还是 E（趋势爆发）。

【关键点位】：精准定位 Spring (弹簧位)、UTAD (上冲回落) 或 SOS (强势信号)。如果是 Spring，请分析它是否成功扫清了止损（Liquidity Sweep）。

【主力意图】：判断这是吸筹 (Accumulation) 还是派发 (Distribution)。请给出你的核心判断逻辑。

【交易建议】：

信心指数 (0-100)。

偏向 (Long / Short / Neutral)。

关键位置：指出理想的二次测试 (LPS/LPSY) 进场区域。

Tone: 请使用冷峻、客观、专业的交易员口吻，避免任何模棱两可的废话。
                请用中文回答，并使用清晰的列表格式。
                """
                
                response = model.generate_content([prompt, image])
                
                # 6. 展示结果
                st.subheader("📊 AI 分析报告")
                st.markdown(response.text)
                
            except Exception as e:
                st.error(f"分析出错啦: {e}")

else:

    st.info("💡 请先上传一张包含成交量的 K 线图。建议使用 TradingView 的截图。")


