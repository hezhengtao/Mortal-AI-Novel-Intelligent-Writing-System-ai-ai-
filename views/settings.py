# mortal_write/views/settings.py

import streamlit as st
import json
import time
import pandas as pd 
import os
import shutil 
import csv
from datetime import datetime

# 核心修正：从 config 导入配置和 DATA_DIR
from config import (
    THEMES, 
    MODEL_GROUPS, 
    FEATURE_MODELS, 
    MODEL_MAPPING, 
    AVAILABLE_MODELS,
    DATA_DIR # 必须导入 DATA_DIR 以确定日志路径
)

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

# ==============================================================================
# 📝 核心修复：独立且健壮的日志系统
# ==============================================================================

# 定义明确的系统日志路径
SYSTEM_LOG_PATH = os.path.join(DATA_DIR, "logs", "system_log.csv")

def write_system_log(action, details):
    """
    🔥 强制写入日志到 CSV 文件，确保看板能显示
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(SYSTEM_LOG_PATH), exist_ok=True)
        
        # 准备数据
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [timestamp, action, details]
        
        # 检查文件是否需要表头
        file_exists = os.path.exists(SYSTEM_LOG_PATH)
        
        with open(SYSTEM_LOG_PATH, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if not file_exists or os.path.getsize(SYSTEM_LOG_PATH) == 0:
                writer.writerow(['timestamp', 'action', 'details']) # 表头
            writer.writerow(row)
            
        print(f"✅ 系统日志已写入: {action} - {details}")
        
    except Exception as e:
        print(f"❌ 日志写入失败: {e}")

# 尝试导入 utils 中的 log_operation 作为备份，但主要依赖上面的 write_system_log
try:
    from utils import log_operation, ensure_log_file, get_log_file_path
except ImportError:
    # 如果导入失败，就把 log_operation 指向我们的本地写入函数
    log_operation = write_system_log
    ensure_log_file = lambda: None
    get_log_file_path = lambda: SYSTEM_LOG_PATH

# ----------------------------------------------------
# 逻辑层辅助
# ----------------------------------------------------
def _refresh_system_config(engine):
    """强制刷新系统配置到内存"""
    try:
        from logic import load_and_update_model_config
        load_and_update_model_config(engine)
    except ImportError:
        pass

def test_model_connection(client, model_name):
    try:
        if not model_name:
             return False, "❌ 未提供模型名称 (Model Name)"
        if not client.api_key:
             return False, "❌ API Key 缺失"
             
        start_time = time.time()
        
        # 简单请求测试
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

def _perform_full_reset(db_mgr):
    """清除所有数据和配置，包括 Session State 和文件。"""
    try:
        # 1. 清除数据库
        db_mgr.execute("DELETE FROM configs")
        for table in ["books", "volumes", "chapters", "characters", "plots", "book_categories", "categories"]:
            try: db_mgr.execute(f"DELETE FROM {table}")
            except: pass
        
        # 2. 清除文件
        if os.path.exists(DATA_DIR):
            for sub in ["logs", "images", "html", "exports", "relations", "ideas"]:
                p = os.path.join(DATA_DIR, sub)
                if os.path.isdir(p): 
                    shutil.rmtree(p, ignore_errors=True)
                    os.makedirs(p, exist_ok=True) 
                elif os.path.isfile(p): os.remove(p)
            
        # 3. 清空 Session
        for k in list(st.session_state.keys()):
            if k not in ['db']: del st.session_state[k]
        
        write_system_log("系统重置", "执行了全量重置 (危险操作)")
        
        return True, "✅ 系统重置成功！所有数据、配置、API Key 和日志均已清除。"
        
    except Exception as e:
        error_msg = f"⚠️ 系统重置失败: {e}"
        write_system_log('系统错误', f'重置失败：{e}')
        return False, error_msg

# --- 🚨 重置系统的模态弹窗逻辑 ---
@dialog_decorator("⚠️ 危险操作：系统重置")
def dialog_reset_confirm():
    """重置确认对话框"""
    st.markdown("### 🚨 警告：此操作不可撤销！")
    st.error("**即将执行以下操作：**")
    
    st.markdown("""
    1. ❌ **所有书籍数据**（章节、卷册）
    2. ❌ **所有角色和剧情设定**
    3. ❌ **所有 AI 配置和 API Key**
    4. ❌ **所有系统日志和导出文件**
    5. ❌ **所有用户设置和自定义内容**
    """)
    
    st.warning("**数据将被永久删除且无法恢复！**")
    
    # 添加二次确认
    confirm_text = st.text_input(
        "请输入 '确认重置' 以继续:",
        placeholder="在此输入确认文字",
        key="reset_confirm_text"
    )
    
    col_confirm, col_cancel = st.columns([1, 1])
    
    with col_confirm:
        confirm_disabled = confirm_text != "确认重置"
        if st.button("🔥 确认重置", 
                    type="primary", 
                    disabled=confirm_disabled,
                    use_container_width=True):
            if confirm_text == "确认重置":
                # 直接执行重置操作
                success, message = _perform_full_reset(st.session_state.db)
                
                if success:
                    # 显示成功信息
                    st.success(message)
                    st.balloons()
                    st.info("系统已重置为初始状态。")
                    
                    # 等待3秒后返回首页
                    time.sleep(3)
                    st.session_state.current_menu = "dashboard"
                    st.rerun()
                else:
                    st.error(message)
    
    with col_cancel:
        if st.button("❌ 取消", type="secondary", use_container_width=True):
            st.rerun()

# --- 💾 保存配置的模态弹窗逻辑 (美化版 - 宽屏 + 滚动优化) ---
@dialog_decorator("💾 确认保存配置", width="large")
def dialog_save_settings(engine, cfg, assignments):
    """保存配置对话框 - 滚动条优化版"""
    
    # 1. 预计算变更数据
    old_cfg = engine.get_config_db("ai_settings", {})
    old_assign = engine.get_config_db("model_assignments", {})
    
    # --- A. 计算厂商配置变更 ---
    config_changes = []
    for k, v in cfg.items():
        old_v = old_cfg.get(k, "")
        if str(v) != str(old_v):
            display_old = "空" if old_v == "" else str(old_v)
            display_new = "空" if v == "" else str(v)
            
            # 脱敏与格式化
            change_type = "⚙️ 通用"
            if "key" in k.lower():
                change_type = "🔑 密钥"
                display_old = "******" if display_old != "空" else "空"
                display_new = "******" if display_new != "空" else "空"
            elif "base" in k.lower():
                change_type = "🌐 地址"
                provider = k.replace("base_", "").upper()
                k = f"{provider} Base URL"
            elif "recharge" in k.lower():
                change_type = "💰 余额"
                provider = k.replace("recharge_", "").upper()
                k = f"{provider} 余额"
                display_old = f"¥ {display_old}"
                display_new = f"¥ {display_new}"
            
            config_changes.append({
                "name": k,
                "type": change_type,
                "old": display_old,
                "new": display_new
            })

    # --- B. 计算模型调度变更 ---
    assign_changes = []
    for feat_key, new_model_key in assignments.items():
        old_model_key = old_assign.get(feat_key, "")
        
        if str(new_model_key) != str(old_model_key):
            def get_display_name(m_key):
                if m_key == "CUSTOM_MODEL": return cfg.get('custom_model_name', '自定义模型')
                if m_key in MODEL_MAPPING: return MODEL_MAPPING[m_key]['name']
                return "未设置" if m_key == "" else m_key

            old_name = get_display_name(old_model_key)
            new_name = get_display_name(new_model_key)
            
            feat_name = FEATURE_MODELS[feat_key]['name']
            if feat_name == "书籍导入 - 简介/分析": feat_name = "书籍管理-导入分析"
            
            assign_changes.append({
                "feature": feat_name,
                "old": old_name,
                "new": new_name
            })

    # ================= UI 渲染部分 =================
    
    # 顶部提示 (固定不滚动)
    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ffbd45;">
        <small>⚠️ 请核对以下变更。保存后立即生效。</small>
    </div>
    """, unsafe_allow_html=True)

    # 概览统计 (固定不滚动)
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("厂商/密钥变更", f"{len(config_changes)} 项", delta="配置修改" if config_changes else None, delta_color="off")
    m_col2.metric("模型调度调整", f"{len(assign_changes)} 项", delta="路由切换" if assign_changes else None, delta_color="off")

    st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)

    # 🔥 核心修改：使用 fixed-height container 包裹内容区域
    # 这样内容过多时只在框内滚动，不会把底部按钮挤下去
    with st.container(height=350, border=True):
        
        # 使用 Tabs 分类显示
        tab_config, tab_assign = st.tabs(["🔧 厂商设置详情", "🔀 模型调度详情"])

        # --- Tab 1: 厂商配置 ---
        with tab_config:
            if not config_changes:
                st.info("✨ 厂商设置无变动")
            else:
                # 表头
                h1, h2, h3 = st.columns([1.5, 2, 2])
                h1.markdown("**配置项**")
                h2.markdown("**原值**")
                h3.markdown("**新值**")
                
                for item in config_changes:
                    with st.container():
                        c1, c2, c3 = st.columns([1.5, 2, 2])
                        with c1:
                            st.caption(item['type'])
                            st.write(item['name'])
                        with c2:
                            st.markdown(f"<span style='color:#999; text-decoration: line-through;'>{item['old']}</span>", unsafe_allow_html=True)
                        with c3:
                            st.markdown(f"**<span style='color:#0f5132;'>{item['new']}</span>**", unsafe_allow_html=True)
                    st.markdown('<div style="height: 5px;"></div>', unsafe_allow_html=True)

        # --- Tab 2: 调度配置 ---
        with tab_assign:
            if not assign_changes:
                st.info("✨ 模型调度无变动")
            else:
                for item in assign_changes:
                    with st.container():
                        ac_main, ac_arrow, ac_target = st.columns([2, 0.5, 2])
                        with ac_main:
                            st.markdown(f"**📌 {item['feature']}**")
                            st.caption("原: " + item['old'])
                        with ac_arrow:
                            st.markdown("<div style='text-align: center; padding-top: 10px;'>➡️</div>", unsafe_allow_html=True)
                        with ac_target:
                            st.markdown(f"**🟢 {item['new']}**")
                            st.caption("新模型")
                    st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)

    # ================= 底部操作区 (始终固定可见) =================
    st.markdown('<div style="height: 15px;"></div>', unsafe_allow_html=True)
    
    col_cancel, col_confirm = st.columns([1, 1])
    
    with col_cancel:
        if st.button("取消", use_container_width=True):
            st.rerun()

    with col_confirm:
        if st.button("✅ 确认并保存", type="primary", use_container_width=True):
            try:
                # 1. 写入新配置
                engine.set_config_db("ai_settings", cfg)
                engine.set_config_db("model_assignments", assignments)
                
                # 2. 强制刷新内存配置
                _refresh_system_config(engine) 
                
                # 3. 🔥 生成审计日志
                audit_messages = []
                
                # Log Config
                config_changes_log = []
                for item in config_changes:
                    k = item['name']
                    if "密钥" in item['type']: config_changes_log.append(f"{k}: [密钥更新]")
                    else: config_changes_log.append(f"{k}: {item['old']}→{item['new']}")
                if config_changes_log: audit_messages.append("配置变更: " + " | ".join(config_changes_log))
                
                # Log Assign
                assign_changes_log = []
                for item in assign_changes:
                    assign_changes_log.append(f"{item['feature']}: {item['old']}→{item['new']}")
                if assign_changes_log: audit_messages.append("调度变更: " + " | ".join(assign_changes_log))
                
                # Write Log
                if audit_messages:
                    write_system_log('配置保存', " || ".join(audit_messages))
                else:
                    write_system_log('配置保存', '保存了配置 (无变更)')

                st.success("已保存！")
                time.sleep(0.5) 
                st.rerun() 
            except Exception as e:
                st.error(f"❌ 保存失败: {e}")
                write_system_log('配置错误', f'保存配置失败: {e}')


# ----------------------------------------------------

def render_header(icon, title):
    st.markdown(f"## {icon} {title}")

def render_settings(engine):
    """渲染系统设置页面"""
    
    if 'operation_logs' not in st.session_state: 
        st.session_state.operation_logs = []
    
    # ----------------------------------------------------
    render_header("⚙️", "系统设置")
    
    # 提前读取当前配置
    cfg = engine.get_config_db("ai_settings", {})
    default_assignments = {k: v['default'] for k, v in FEATURE_MODELS.items()}
    assignments = engine.get_config_db("model_assignments", default_assignments)

    # 创建副本用于收集 UI 输入
    pending_cfg = cfg.copy()
    pending_assignments = assignments.copy()

    # =========================================================================
    # 1. 界面风格
    # =========================================================================
    st.subheader("🎨 界面风格")
    
    theme_options = list(THEMES.keys())
    current_theme = st.session_state.get('current_theme', "翡翠森林")
    
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
        write_system_log('界面', f'主题切换为 {curr}')
        st.rerun()
        
    
    # =========================================================================
    # 2. 模型配置与调度中心
    # =========================================================================
    st.subheader("🤖 模型配置与调度中心")
    
    provider_keys = list(MODEL_GROUPS.keys())
    selected_provider = st.session_state.get('selected_provider', provider_keys[0] if provider_keys else None)
    
    col1, col2, col3 = st.columns([1.5, 2.5, 2.5]) 

    if 'custom_provider_name' not in st.session_state:
        st.session_state.custom_provider_name = "自定义厂商"

    # --- 左侧：厂商选择 ---
    with col1:
        st.markdown("##### ① 选择厂商")
        
        def on_provider_change():
            st.session_state.selected_provider = st.session_state.provider_selector
            st.session_state.custom_model_enabled = False
            
        if selected_provider not in provider_keys: selected_provider = provider_keys[0]

        if not st.session_state.get('custom_model_enabled'):
            st.selectbox("🏭 厂商名称", provider_keys, index=provider_keys.index(selected_provider) if selected_provider in provider_keys else 0, key="provider_selector", on_change=on_provider_change)
        else:
            st.info("正在配置：自定义模型")
        
        st.markdown('<div style="height: 29px; margin-bottom: 0px;"></div>', unsafe_allow_html=True)

        if not st.session_state.get('custom_model_enabled'):
            if st.button("🛠️ 切换到自定义模型", use_container_width=True, help="启用自定义模型配置"):
                st.session_state.custom_model_enabled = True
                st.session_state.selected_provider = "Custom"
                st.rerun()
        else:
            if st.button("🔙 返回预设厂商", use_container_width=True, help="返回预设厂商列表"):
                st.session_state.custom_model_enabled = False
                st.session_state.selected_provider = provider_keys[0]
                st.rerun()

    # --- 中间 & 右侧：配置输入 ---
    
    # A. 自定义模型逻辑
    if st.session_state.get('custom_model_enabled'):
        with col2:
            st.markdown("##### ② Base URL / Key")
            
            pending_cfg['custom_model_base'] = st.text_input("🌐 Base URL", value=cfg.get('custom_model_base', ''), key="ipt_cust_base", help="Base URL 必须是 OpenAI 兼容格式。")
            pending_cfg['custom_model_key'] = st.text_input("🔑 API Key", value=cfg.get('custom_model_key', ''), type="password", key="ipt_cust_key", help="Custom 模型的 API 访问密钥。")
            pending_cfg['custom_model_enabled'] = True

        with col3:
            st.markdown("##### ③ 模型信息")
            pending_cfg['custom_model_name'] = st.text_input("💡 显示名称", value=cfg.get('custom_model_name', 'Custom'), key="ipt_cust_name", help="用于功能调度列表中的显示名称。")
            pending_cfg['custom_api_model'] = st.text_input("📝 API Model ID", value=cfg.get('custom_api_model', ''), key="ipt_cust_id", help="发送给 API 的模型名称。")
            
            st.markdown('<div style="height: 29px; margin-bottom: 0px;"></div>', unsafe_allow_html=True)
            
            if st.button("🧪 测试连接", key="btn_test_cust", use_container_width=True):
                if not pending_cfg['custom_model_key'] or not pending_cfg['custom_model_base']: st.error("请先填写 Base URL 和 Key")
                else:
                    cli = OpenAI(api_key=pending_cfg['custom_model_key'], base_url=pending_cfg['custom_model_base'])
                    ok, msg = test_model_connection(cli, pending_cfg['custom_api_model'])
                    if ok: st.success(msg)
                    else: st.error(msg)

    # B. 预设厂商逻辑
    else:
        if selected_provider and selected_provider in MODEL_GROUPS:
            group = MODEL_GROUPS[selected_provider]
            db_base = cfg.get(f"base_{selected_provider}", group['models'][group['default_key']]['base'])
            db_key = cfg.get(f"key_{selected_provider}", "")
            current_recharge = cfg.get(f"recharge_{selected_provider}", 0.0)
            
            with col2:
                st.markdown("##### ② Base URL / Key")
                new_base = st.text_input("🌐 Base URL", value=db_base, key=f"ipt_base_{selected_provider}")
                new_key = st.text_input("🔑 API Key", value=db_key, type="password", key=f"ipt_key_{selected_provider}")
                recharge_val = st.number_input("💸 余额 (¥)", min_value=0.0, value=current_recharge, step=1.0, format="%.2f", key=f"recharge_{selected_provider}_input", help="为该厂商充值的总金额（¥）。")
                
                pending_cfg[f"base_{selected_provider}"] = new_base
                pending_cfg[f"key_{selected_provider}"] = new_key
                pending_cfg[f"recharge_{selected_provider}"] = recharge_val
            
            with col3:
                st.markdown("##### ③ 模型 / 测试")
                models = group['models']
                m_keys = list(models.keys())
                test_model_key = st.selectbox("选择测试模型", m_keys, format_func=lambda x: models[x]['name'])
                
                st.markdown('<div style="height: 29px; margin-bottom: 0px;"></div>', unsafe_allow_html=True)
                
                if st.button("🧪 测试连接", key=f"btn_test_{selected_provider}", use_container_width=True):
                    if not new_key: st.error("请先填写 API Key")
                    else:
                        cli = OpenAI(api_key=new_key, base_url=new_base)
                        target_model = models[test_model_key]['api_model']
                        ok, msg = test_model_connection(cli, target_model)
                        if ok: st.success(msg)
                        else: st.error(msg)

    # --- 调度配置 ---
    st.markdown("---")
    st.markdown("##### ④ 功能模型调度 (决定各个功能使用哪个模型)")
    
    display_map = {}
    for k, v in MODEL_MAPPING.items(): display_map[v['name']] = k
    if cfg.get('custom_model_enabled'):
        c_name = cfg.get('custom_model_name', 'Custom')
        display_map[c_name] = "CUSTOM_MODEL"

    all_display_names = list(display_map.keys())

    f_cols = st.columns(2)
    
    for i, (f_key, f_info) in enumerate(FEATURE_MODELS.items()):
        col = f_cols[i % 2]
        with col:
            current_assigned_key = assignments.get(f_key, f_info['default'])
            
            current_display = "未知模型"
            if current_assigned_key == "CUSTOM_MODEL": current_display = cfg.get('custom_model_name', 'Custom')
            elif current_assigned_key in MODEL_MAPPING: current_display = MODEL_MAPPING[current_assigned_key]['name']
            
            if current_display not in all_display_names: current_display = all_display_names[0] if all_display_names else ""

            # 临时修改显示名称：将"书籍导入 - 简介/分析"改为"书籍管理-导入分析"
            feature_name = f_info['name']
            if feature_name == "书籍导入 - 简介/分析":
                feature_name = "书籍管理-导入分析"
            
            new_display = st.selectbox(
                f"**{feature_name}**", 
                all_display_names, 
                index=all_display_names.index(current_display) if current_display in all_display_names else 0,
                key=f"sel_feat_{f_key}"
            )
            selected_key = display_map.get(new_display, f_info['default'])
            pending_assignments[f_key] = selected_key

    # --- 底部保存栏 ---
    st.markdown("---")
    c_save, c_info = st.columns([3, 1])
    
    with c_save:
        if st.button("💾 保存全部配置", type="primary", use_container_width=True):
            # 传递 pending_cfg 和 pending_assignments 给弹窗
            dialog_save_settings(engine, pending_cfg, pending_assignments)
    
    with c_info:
        st.caption("提示：保存后，所有功能将立即使用新的模型配置。请确保 API Key 正确且有余额。")

    # =========================================================================
    # 系统重置与日志
    # =========================================================================
    with st.expander("🚨 危险区域：系统重置"):
        st.error("**此操作将永久删除所有数据，不可恢复！**")
        st.warning("""
        将清空以下内容：
        - 所有书籍、章节、卷册
        - 所有角色、剧情设定
        - 所有AI配置、API密钥
        - 所有日志、导出文件
        """)
        
        # 重置按钮触发确认对话框
        if st.button("🔥 执行系统重置", type="secondary", use_container_width=True):
            # 打开重置确认对话框
            dialog_reset_confirm()

    st.subheader("📋 全局系统日志")
    logs_df = pd.DataFrame()
    
    # 读取日志 (直接使用 SYSTEM_LOG_PATH，不再依赖 utils)
    if os.path.exists(SYSTEM_LOG_PATH):
        try:
            if os.path.getsize(SYSTEM_LOG_PATH) > 0:
                logs_df = pd.read_csv(SYSTEM_LOG_PATH)
                logs_df = logs_df.iloc[::-1] # 倒序显示，最新的在上面
        except Exception as e: st.error(f"日志文件读取错误: {e}")
    
    if not logs_df.empty:
        st.caption(f"系统共记录 {len(logs_df)} 条操作。下方仅显示最近 100 条。")
        df_display = logs_df.head(100).copy()
        
        # 优化显示：重命名列
        if len(df_display.columns) >= 3:
            # 兼容旧表头，强制重命名
            df_display.columns = ['时间', '操作', '详情'] + list(df_display.columns[3:])
            
        st.dataframe(
            df_display, 
            use_container_width=True, 
            height=300, 
            hide_index=True,
            column_config={
                "时间": st.column_config.TextColumn("操作时间", width="medium"),
                "操作": st.column_config.TextColumn("操作类型", width="small"),
                "详情": st.column_config.TextColumn("详细内容", width="large"),
            }
        )
        
        with open(SYSTEM_LOG_PATH, "r", encoding='utf-8-sig') as f:
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