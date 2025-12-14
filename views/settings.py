# mortal_write/views/settings.py

import streamlit as st
import json
import time
import pandas as pd 
import os
import shutil 
import csv

# 核心修正：从 config 导入配置，避免数据不一致
from config import (
    THEMES, 
    MODEL_GROUPS, 
    DEFAULT_MODEL_MAPPING, 
    FEATURE_MODELS, 
    MODEL_MAPPING, 
    AVAILABLE_MODELS
)

# 尝试导入工具函数
try:
    from utils import log_operation, LOG_FILE, ensure_log_file
except ImportError:
    # 路径兼容性处理，防止报错
    def log_operation(action, details=""): print(f"Logging: {action} - {details}")
    LOG_FILE = "logs/system_log.csv"
    ensure_log_file = lambda: None

# 引入真实的 OpenAI 客户端及异常处理
try:
    from openai import OpenAI, APIConnectionError, AuthenticationError, APITimeoutError
except ImportError:
    st.error("缺失 openai 库，请在终端运行: pip install openai")
    class OpenAI: 
        def __init__(self, **kwargs): pass

# --- 🛠️ 模态弹窗兼容性处理 ---
if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
else:
    dialog_decorator = st.experimental_dialog

# --- 💾 保存配置的模态弹窗逻辑 ---
@dialog_decorator("💾 确认保存配置")
def dialog_save_settings(engine, cfg, assignments):
    st.write("是否确认保存当前所有的厂商设置、Key 以及模型调度分配？")
    st.warning("⚠️ 请确保 API Key 和 Base URL 输入正确。")
    
    col_confirm, col_cancel = st.columns([1, 1])
    
    with col_confirm:
        if st.button("✅ 确认保存", type="primary", use_container_width=True):
            try:
                # 执行保存逻辑
                engine.set_config_db("ai_settings", cfg)
                engine.set_config_db("model_assignments", assignments)
                
                # 触发配置更新回调
                load_and_update_model_config(engine)
                
                st.success("配置已成功保存！")
                log_operation('配置', '已保存全局模型设置及功能分配。') # 🔥 审计日志
                time.sleep(1) # 稍作停留展示成功状态
                st.rerun() # 刷新页面以应用更改
            except Exception as e:
                st.error(f"保存失败: {e}")
                log_operation('配置', f'保存配置失败: {e}') # 🔥 审计日志

    with col_cancel:
        if st.button("❌ 取消", type="secondary", use_container_width=True):
            st.rerun()


# 完全重置的核心逻辑
def _perform_full_reset(db_mgr):
    """清除所有数据和配置，包括 Session State 和文件。"""
    try:
        # 1. 清除数据库
        db_mgr.execute("DELETE FROM configs")
        for table in ["books", "volumes", "chapters", "characters", "plots"]:
            db_mgr.execute(f"DELETE FROM {table}")
        
        # 2. 清除会话状态
        keys_to_reset = list(st.session_state.keys())
        for k in keys_to_reset:
            if k != 'db': del st.session_state[k]
        
        # 3. 清除文件 (包括 logs 文件夹)
        for p in ["logs", "projects/images", "html"]:
            if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p): os.remove(p)

        # 4. 重新初始化日志并记录重置操作
        if 'operation_logs' in st.session_state:
            del st.session_state.operation_logs
        
        ensure_log_file()
        log_operation('系统', '系统数据和配置已彻底清除 (全局重置)。')
        
    except Exception as e:
        st.error(f"⚠️ 系统重置失败: {e}")
        log_operation('系统', f'重置失败：{e}')
    
def load_and_update_model_config(engine_instance):
    # 此函数仅在内存刷新时被调用，具体的保存日志在 dialog_save_settings 中记录
    pass 
    
# 真实的连通性测试逻辑
def test_model_connection(client, model_name):
    try:
        if not model_name:
             return False, "❌ 未提供模型名称 (Model Name)"
        if not client.api_key:
             return False, "❌ API Key 缺失"
             
        start_time = time.time()
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5, 
            timeout=10
        )
        
        elapsed = time.time() - start_time
        
        if response.choices and response.choices[0].message:
            return True, f"✅ 连接成功！(耗时 {elapsed:.2f}s)"
        else:
            return False, "❌ 连接通畅但无内容返回"

    except AuthenticationError:
        return False, "❌ 认证失败：请检查 API Key"
    except APIConnectionError:
        return False, "❌ 连接错误：无法连接到 Base URL"
    except APITimeoutError:
        return False, "❌ 请求超时，网络不稳定"
    except Exception as e:
        return False, f"❌ 错误: {str(e)}"

def render_header(icon, title):
    st.markdown(f"## {icon} {title}")

# ----------------------------------------------------

def render_settings(engine):
    """渲染系统设置页面"""
    
    # 确保每次调用 render_settings 时，状态变量都存在
    if 'operation_logs' not in st.session_state:
        st.session_state.operation_logs = []

    if 'reset_successful' not in st.session_state:
        st.session_state.reset_successful = False
    
    # =========================================================================
    # 重置成功后的模态视图
    # =========================================================================
    if st.session_state.reset_successful:
        st.success("✅ **系统已完全重置成功！**")
        st.info("所有数据、配置、API Key 和日志均已清除。")
        st.write("")
        
        if st.button("❌ 关闭窗口并返回首页", key="close_reset_modal", type="primary", use_container_width=True):
            st.session_state.reset_successful = False
            st.session_state.current_menu = "dashboard"
            st.rerun()
        return 

    # ----------------------------------------------------

    render_header("⚙️", "系统设置")
    
    ## 界面风格
    st.subheader("🎨 界面风格")
    
    theme_options = list(THEMES.keys())
    current_theme = st.session_state.current_theme
    
    if current_theme not in theme_options:
        current_theme = theme_options[0] if theme_options else "翡翠森林"
        st.session_state.current_theme = current_theme
        
    curr = st.selectbox(
        "选择主题", 
        theme_options, 
        index=theme_options.index(current_theme) if current_theme in theme_options else 0,
        label_visibility="collapsed" 
    )
    
    if curr != st.session_state.current_theme:
        st.session_state.current_theme = curr
        log_operation('界面', f'主题切换为 {curr}') # 🔥 审计日志
        st.rerun()
        
    
    ## 模型配置与调度中心
    st.subheader("🤖 模型配置与调度中心")
    
    cfg = engine.get_config_db("ai_settings", {})
    assignments = engine.get_config_db("model_assignments", {k: v['default'] for k, v in FEATURE_MODELS.items()})
    
    # 重新构建显示名称列表，确保是完整的
    model_display_names_full = [MODEL_MAPPING[k]['name'] for k in AVAILABLE_MODELS]
    
    provider_keys = list(MODEL_GROUPS.keys())
    selected_provider = st.session_state.selected_provider
    
    # 调整列宽
    col1, col2, col3 = st.columns([1.8, 2.5, 2.5]) 

    if 'custom_provider_name' not in st.session_state:
        st.session_state.custom_provider_name = "自定义厂商"

    with col1:
        st.markdown("##### ① 选择厂商")
        
        def set_provider():
            st.session_state.selected_provider = st.session_state.provider_selector
            st.session_state.selected_model = None 
            st.session_state.custom_model_enabled = False
            
        if selected_provider not in provider_keys:
             selected_provider = provider_keys[0] if provider_keys else None
             st.session_state.selected_provider = selected_provider

        if st.session_state.custom_model_enabled:
            st.session_state.custom_provider_name = st.text_input(
                "🏭 厂商名称",
                value=st.session_state.custom_provider_name,
                key="custom_provider_name_input",
                help="输入自定义的厂商名称"
            )
        else:
            st.selectbox(
                "🏭 厂商名称",
                provider_keys,
                key="provider_selector",
                index=provider_keys.index(selected_provider) if selected_provider and selected_provider in provider_keys else 0,
                on_change=set_provider
            )
        
        st.markdown('<div style="height: 29px; margin-bottom: 0px;"></div>', unsafe_allow_html=True)

        if st.button("🛠️ 自定义", key="enable_custom_model", use_container_width=True, disabled=st.session_state.custom_model_enabled, help="启用自定义模型配置"):
            st.session_state.custom_model_enabled = True
            st.session_state.selected_provider = "Custom"
            st.session_state.selected_model = "CUSTOM_MODEL"
            log_operation('配置', '进入自定义模型配置模式。') # 🔥 审计日志
            st.rerun()
            
        if st.session_state.custom_model_enabled and st.button("🔙 默认", key="disable_custom_model", use_container_width=True, help="返回预设厂商列表"):
            st.session_state.custom_model_enabled = False
            st.session_state.selected_provider = provider_keys[0] 
            st.session_state.selected_model = None
            log_operation('配置', '退出自定义模型配置模式。') # 🔥 审计日志
            st.rerun()

        if not selected_provider:
            return 
        
    if st.session_state.custom_model_enabled:
        custom_key = "CUSTOM_MODEL"
        
        with col2:
            st.markdown("##### ② Base URL / Key")
            
            st.session_state.custom_model_base = st.text_input(
                "🌐 Base URL",
                st.session_state.custom_model_base, 
                key="custom_base_url_input_2",
                help="Base URL 必须是 OpenAI 兼容格式 (例如: https://api.openai.com/v1)。"
            )
            
            st.session_state.custom_model_key = st.text_input(
                "🔑 API Key", 
                st.session_state.custom_model_key, 
                type="password", 
                key="custom_api_key_input_2",
                help="Custom 模型的 API 访问密钥。"
            )
            
        with col3:
            st.markdown("##### ③ 模型信息")
            
            st.session_state.custom_model_name = st.text_input(
                "💡 显示名称", 
                st.session_state.custom_model_name, 
                key="custom_display_name_input_3",
                help="用于功能调度列表中的显示名称。"
            )
            
            st.session_state.custom_api_model = st.text_input(
                "📝 API Model ID", 
                st.session_state.custom_api_model, 
                key="custom_api_model_input_3",
                help="发送给 API 的模型名称 (例如: deepseek-chat)。"
            )
            
            st.markdown('<div style="height: 29px; margin-bottom: 0px;"></div>', unsafe_allow_html=True)
            
            if st.button("🧪 测试连接", key="test_custom_connection", type="secondary", use_container_width=True):
                client = OpenAI(
                    api_key=st.session_state.custom_model_key, 
                    base_url=st.session_state.custom_model_base
                )
                with st.spinner("连接中..."):
                    ok, msg = test_model_connection(client, st.session_state.custom_api_model)
                    log_operation('测试', f'自定义厂商测试结果: {msg}') # 🔥 审计日志
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                        
    else:
        provider = selected_provider
        group = MODEL_GROUPS[provider]
        
        current_base = cfg.get(f"base_{provider}", group['models'][group['default_key']]['base'])
        current_key = cfg.get(f"key_{provider}", "")
        current_recharge = cfg.get(f"recharge_{provider}", 0.0)
        
        with col2:
            st.markdown("##### ② Base URL / Key")
            
            base_val = st.text_input(
                "🌐 Base URL", 
                current_base, 
                key=f"provider_base_{provider}_input",
                help="该厂商所有模型的 API 基础地址。"
            )
            
            k_val = st.text_input(
                "🔑 API Key", 
                current_key, 
                type="password", 
                key=f"k_{provider}_input_global",
                help="该厂商的 API 访问密钥。"
            )
            
            recharge_val = st.number_input(
                "💸 余额 (¥)",
                min_value=0.0,
                value=current_recharge,
                step=1.0,
                format="%.2f",
                key=f"recharge_{provider}_input",
                help="为该厂商充值的总金额（¥）。"
            )
            
            cfg[f"base_{provider}"] = base_val
            cfg[f"key_{provider}"] = k_val
            cfg[f"recharge_{provider}"] = recharge_val 


        with col3:
            st.markdown("##### ③ 模型 / 测试")
            
            provider_models = list(group['models'].keys())
            
            if ('selected_model' not in st.session_state or 
                st.session_state.selected_model not in provider_models):
                st.session_state.selected_model = provider_models[0] if provider_models else None

            selected_model = st.session_state.selected_model

            def set_model_config():
                st.session_state.selected_model = st.session_state.model_selector_detail_key
            
            st.selectbox(
                "🏷️ 选择模型",
                provider_models,
                format_func=lambda k: MODEL_MAPPING[k]['name'],
                key="model_selector_detail_key",
                index=provider_models.index(selected_model) if selected_model else 0,
                on_change=set_model_config
            )
            
            if selected_model:
                model_info = MODEL_MAPPING[selected_model]
                
                st.markdown('<div style="height: 29px; margin-bottom: 0px;"></div>', unsafe_allow_html=True)
                
                if st.button(f"🧪 测试连接", key=f"test_connection_{selected_model}", type="secondary", use_container_width=True):
                    current_base_url_for_test = base_val
                    current_key_for_test = k_val
                    
                    client = OpenAI(api_key=current_key_for_test, base_url=current_base_url_for_test) 
                    
                    with st.spinner("连接中..."):
                        ok, msg = test_model_connection(client, model_info['api_model'])
                        log_operation('测试', f'厂商 {provider} 模型 {model_info["name"]} 测试结果: {msg}') # 🔥 审计日志
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)

    
    ## 布局优化：功能调度模块
    st.markdown("##### ④ 功能调度")
    

    feature_keys = list(FEATURE_MODELS.keys())
    for i in range(0, len(feature_keys)):
        
        key = feature_keys[i]
        feature_info = FEATURE_MODELS[key]
        assigned_model_key = assignments.get(key, feature_info['default'])
        
        col_feature_name, col_feature_select = st.columns([2, 3])
        
        with col_feature_name:
             st.markdown(f"**{feature_info['name']}**")
        
        with col_feature_select:
            try:
                # 兼容性处理：如果 assigned_model_key 不在当前可用列表中，回退到第一个
                default_index = AVAILABLE_MODELS.index(assigned_model_key)
            except ValueError:
                default_index = 0
            
            # 兼容性处理：防止越界
            if default_index >= len(model_display_names_full):
                default_index = 0

            selected_name = st.selectbox(
                "模型选择",
                model_display_names_full,
                index=default_index,
                key=f"assign_{key}_select", 
                label_visibility="collapsed",
                help=f"默认模型: {MODEL_MAPPING.get(feature_info['default'], {}).get('name', 'Unknown')}"
            )
            selected_key = next((k for k, v in MODEL_MAPPING.items() if v['name'] == selected_name), feature_info['default'])
            assignments[key] = selected_key

    # --- 保存和重置按钮 ---
    
    col_save, col_reset = st.columns([3, 1])
    
    # 🔥 关键修改：点击按钮触发模态弹窗
    if col_save.button("💾 保存所有配置和分配", type="primary", use_container_width=True):
        dialog_save_settings(engine, cfg, assignments)
        
    with col_reset:
        with st.popover("❌ 重置系统"):
            st.warning("⚠️ 警告：此操作将**永久清除**所有小说数据、API Key、模型分配及**系统日志**。")
            if st.button("确认彻底清除", key="confirm_reset_all_settings", type="primary", use_container_width=True):
                _perform_full_reset(st.session_state.db) 
                st.session_state.reset_successful = True 
                st.session_state.current_menu = "settings" 
                st.rerun() 

    # ==========================================================================
    # 全局系统日志 (日志查看器)
    # ==========================================================================
    st.subheader("📋 全局系统日志")

    # 1. 读取日志文件
    logs_df = pd.DataFrame()
    
    # 确保文件被创建，避免读取时报错
    ensure_log_file() 

    if os.path.exists(LOG_FILE):
        try:
            logs_df = pd.read_csv(LOG_FILE)
            logs_df = logs_df.iloc[::-1] # 倒序
        except Exception as e:
            st.error(f"日志文件读取错误: {e}")
    
    # 2. 界面展示
    if not logs_df.empty:
        st.caption(f"系统共记录 {len(logs_df)} 条操作。下方仅显示最近 100 条。")
        
        df_display = logs_df.head(100).copy()
        if len(df_display.columns) == 3:
            df_display.columns = ['时间', '操作', '详情']
        
        st.dataframe(
            df_display, 
            use_container_width=True, 
            height=300,
            hide_index=True 
        )
        
        # 3. 导出
        with open(LOG_FILE, "r", encoding='utf-8-sig') as f:
            csv_data = f.read()
            
        st.download_button(
            label="📥 导出完整系统日志 (CSV)",
            data=csv_data,
            file_name=f"mortal_write_full_log_{time.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("暂无日志记录。")