

import streamlit as st
import os
from utils import render_header
from utils import log_operation

def render_donate():
    """渲染捐赠支持页面"""
    render_header("🍵", "用爱发电")
    
    # 顶部文本容器
    st.markdown("""
    <div style='padding:20px;border-radius:10px;text-align:center; margin: 0 auto; max-width: 800px;'>
        <h3>您的小说加速器，需要持续的燃料！⛽️ 如果本项目高效地助您构思、加速了您的码字进程，请考虑捐赠。</h3>
        <p style='color:grey'>每一份支持都意义重大！您的支持是我更新的动力。</p>
        <p>📧 联系方式: 1402654622@qq.com</p>
    </div>
    """, unsafe_allow_html=True)

   

    # 注入 CSS 确保列内部和图片居中
    st.markdown("""
    <style>
    .qr-column-item {
        text-align: center; 
    }
    .st-emotion-cache-1v0k5s8 img {
        margin: 0 auto;
        display: block;
    }
    </style>
    """, unsafe_allow_html=True)


    # 使用 st.columns 创建三列：左侧留白、中间内容、右侧留白
    col_left_spacer, col_content, col_right_spacer = st.columns([2, 4, 2])

    with col_content:
        # 在内容列中创建两列，用于放置支付宝和微信 (确保并排)
        col_ali, col_wx = st.columns([1, 1])

        with col_ali:
            st.markdown('<div class="qr-column-item">', unsafe_allow_html=True)
            st.markdown("#### 支付宝 (Alipay)")
            p_ali = os.path.join("pay", "ali.png")
            if os.path.exists(p_ali):
                st.image(p_ali, width=200)
            else:
                st.info("请将 ali.png 放入 pay 文件夹")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_wx:
            st.markdown('<div class="qr-column-item">', unsafe_allow_html=True)
            st.markdown("#### 微信支付 (WeChat)")
            p_wx = os.path.join("pay", "wx.png")
            if os.path.exists(p_wx):
                st.image(p_wx, width=200)
            else:
                st.info("请将 wx.png 放入 pay 文件夹")
            st.markdown('</div>', unsafe_allow_html=True)