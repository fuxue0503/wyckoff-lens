import streamlit as st
import google.generativeai as genai
from PIL import Image

# 1. 配置你的 Gemini API Key
genai.configure(api_key="你的KEY")

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
                你是一位资深威客夫策略专家。请分析这张图片中的价格行为和成交量：
                1. 识别当前处于哪个阶段 (Phase A/B/C/D/E)。
                2. 寻找关键点：SC, AR, ST, Spring, SOS 或 UTAD。
                3. 判断是吸筹 (Accumulation) 还是派发 (Distribution)。
                4. 给出一个 0-100 的信心评分，并提供操作建议。
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
