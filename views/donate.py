import streamlit as st
import os
import sys
from utils import render_header

def get_resource_path(relative_path):
    """
    获取资源文件的绝对路径。
    - 打包后 (EXE): 资源在 sys._MEIPASS 下
    - 开发时: 资源在当前工作目录的 mortal_write 下 (取决于 relative_path 的传入方式)
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def render_donate():
    """渲染捐赠支持页面"""
    render_header("🍵", "用爱发电")
    
    st.markdown("""
    <div style='padding:20px;border-radius:10px;text-align:center; margin: 0 auto; max-width: 800px;'>
        <h3>您的小说加速器，需要持续的燃料！⛽️ 如果本项目高效地助您构思、加速了您的码字进程，请考虑捐赠。</h3>
        <p style='color:grey'>每一份支持都意义重大！您的支持是我更新的动力。</p>
        <p>📧 联系方式: 1402654622@qq.com</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
    .qr-column-item { text-align: center; }
    .st-emotion-cache-1v0k5s8 img { margin: 0 auto; display: block; }
    </style>
    """, unsafe_allow_html=True)

    col_left_spacer, col_content, col_right_spacer = st.columns([2, 4, 2])

    with col_content:
        col_ali, col_wx = st.columns([1, 1])

        with col_ali:
            st.markdown('<div class="qr-column-item">', unsafe_allow_html=True)
            st.markdown("#### 支付宝 (Alipay)")
            
            # 使用 pay/ali.png，这对应 spec 文件中映射的 'pay' 文件夹
            p_ali = get_resource_path(os.path.join("pay", "ali.png"))
            
            if os.path.exists(p_ali):
                st.image(p_ali, width=200)
            else:
                st.warning(f"图片未找到: {p_ali}")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_wx:
            st.markdown('<div class="qr-column-item">', unsafe_allow_html=True)
            st.markdown("#### 微信支付 (WeChat)")
            
            p_wx = get_resource_path(os.path.join("pay", "wx.png"))
            
            if os.path.exists(p_wx):
                st.image(p_wx, width=200)
            else:
                st.warning(f"图片未找到: {p_wx}")
            st.markdown('</div>', unsafe_allow_html=True)