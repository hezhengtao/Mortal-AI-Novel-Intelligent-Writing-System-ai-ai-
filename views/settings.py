# mortal_write/views/settings.py

import streamlit as st
import json
import time
import pandas as pd 
import os
import shutil 
import csv
import uuid
import threading
from datetime import datetime

# 核心修正：从 config 导入配置和 DATA_DIR
from config import (
    THEMES, 
    MODEL_GROUPS, 
    FEATURE_MODELS, 
    MODEL_MAPPING, 
    AVAILABLE_MODELS,
    DATA_DIR
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
# 🛡️ 核心修复：严格审计日志系统 (Strict Audit Logging)
# ==============================================================================

SYSTEM_LOG_PATH = os.path.join(DATA_DIR, "logs", "system_audit.csv")
_log_lock = threading.Lock() # 线程锁，防止并发写入冲突

def get_session_id():
    """获取或生成当前会话的唯一追踪ID"""
    if "session_trace_id" not in st.session_state:
        st.session_state.session_trace_id = str(uuid.uuid4())[:8]
    return st.session_state.session_trace_id

def log_audit_event(category, action, details, status="SUCCESS", module="SETTINGS"):
    """
    执行严格的审计日志写入
    :param category: 操作类别 (e.g., "配置变更", "系统重置")
    :param action: 具体动作 (e.g., "更新模型API Key")
    :param details: 详细内容 (支持 Dict/List 自动转 JSON 字符串)
    :param status: 操作状态 (SUCCESS / WARNING / ERROR)
    :param module: 所属模块
    """
    try:
        os.makedirs(os.path.dirname(SYSTEM_LOG_PATH), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_id = get_session_id()
        
        # 汉化状态码
        status_map = {
            "SUCCESS": "成功",
            "WARNING": "警告",
            "ERROR": "错误"
        }
        status_cn = status_map.get(status, status)
        
        # 汉化模块名
        module_map = {
            "SETTINGS": "系统设置",
            "WRITER": "写作终端",
            "DASHBOARD": "数据看板"
        }
        module_cn = module_map.get(module, module)

        # 序列化复杂对象
        if isinstance(details, (dict, list)):
            try: details = json.dumps(details, ensure_ascii=False)
            except: details = str(details)
            
        row = [timestamp, session_id, module_cn, category, action, status_cn, details]
        
        # 使用线程锁确保原子写入
        with _log_lock:
            file_exists = os.path.exists(SYSTEM_LOG_PATH)
            with open(SYSTEM_LOG_PATH, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # 🔥 汉化表头
                if not file_exists or os.path.getsize(SYSTEM_LOG_PATH) == 0:
                    writer.writerow(['时间', '会话ID', '模块', '类别', '操作', '状态', '详情']) 
                writer.writerow(row)
    except Exception as e:
        print(f"❌ 审计日志写入失败: {e}")

# 兼容旧接口，重定向到新审计系统
def write_system_log(action, details):
    log_audit_event("常规操作", action, details)

# ==============================================================================
# ℹ️ 厂商优缺点详细说明 (纯文案展示)
# ==============================================================================
PROVIDER_INFO = {
    "OpenAI": "🌟 **行业标杆**：逻辑推理最强，适合复杂剧情。需魔法上网。",
    "DeepSeek": "🚀 **国产之光**：中文理解极强，推理能力(R1)出色，性价比极高。",
    "Moonshot": "📚 **Kimi**：支持超长上下文，适合整书分析与阅读。",
    "Qwen": "🇨🇳 **通义千问**：阿里出品，各项能力均衡，支持大规模上下文。",
    "SiliconFlow": "⚡ **硅基流动**：极速聚合 Qwen, Llama, DeepSeek 等开源模型。",
    "Claude": "🧠 **拟人度高**：文笔细腻，适合角色扮演和情感描写。",
    "Ollama": "🏠 **本地运行**：隐私安全，无费用，依赖本地算力。",
    "Custom": "🛠️ **自由扩展**：连接任何兼容 OpenAI 协议的 API。"
}

# ----------------------------------------------------
# 逻辑层辅助
# ----------------------------------------------------
def _refresh_system_config(engine):
    try:
        from logic import load_and_update_model_config
        load_and_update_model_config(engine)
    except ImportError: pass

def test_model_connection(client, model_name):
    try:
        if not model_name: return False, "❌ 未提供模型名称"
        if not client.api_key: return False, "❌ API Key 缺失"
        start_time = time.time()
        response = client.chat.completions.create(
            model=model_name, messages=[{"role": "user", "content": "Hi"}], max_tokens=5, timeout=10
        )
        elapsed = time.time() - start_time
        if response.choices: return True, f"✅ 连接成功 ({elapsed:.2f}s)"
        else: return False, "❌ 无内容返回"
    except Exception as e: return False, f"❌ 错误: {str(e)}"

def _perform_full_reset(db_mgr):
    try:
        db_mgr.execute("DELETE FROM configs")
        for table in ["books", "volumes", "chapters", "characters", "plots", "book_categories", "categories"]:
            try: db_mgr.execute(f"DELETE FROM {table}")
            except: pass
        if os.path.exists(DATA_DIR):
            for sub in ["logs", "images", "html", "exports", "relations", "ideas"]:
                p = os.path.join(DATA_DIR, sub)
                if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True); os.makedirs(p, exist_ok=True) 
                elif os.path.isfile(p): os.remove(p)
        for k in list(st.session_state.keys()):
            if k not in ['db']: del st.session_state[k]
        
        log_audit_event("系统维护", "全量重置", "删除了所有数据库内容及缓存文件", status="WARNING")
        return True, "✅ 重置成功！"
    except Exception as e:
        log_audit_event("系统维护", "全量重置失败", str(e), status="ERROR")
        return False, f"⚠️ 重置失败: {e}"

# --- 🚨 重置确认弹窗 ---
@dialog_decorator("⚠️ 危险操作：系统重置")
def dialog_reset_confirm():
    st.error("**数据将被永久删除且无法恢复！**")
    st.warning(f"操作追踪 ID: {get_session_id()}") # 显示追踪ID增加威慑力
    confirm_text = st.text_input("输入 '确认重置' 继续:", key="reset_confirm_text")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔥 确认重置", type="primary", disabled=(confirm_text!="确认重置"), width="stretch"):
            ok, msg = _perform_full_reset(st.session_state.db)
            if ok: st.success(msg); time.sleep(2); st.session_state.current_menu="dashboard"; st.rerun()
            else: st.error(msg)
    with c2:
        if st.button("取消", width="stretch"): st.rerun()

# ==============================================================================
# 🛠️ 自定义模型编辑/添加弹窗 (纯净版)
# ==============================================================================
@dialog_decorator("🛠️ 配置自定义模型", width="large")
def dialog_edit_custom_model(engine, model_data=None, index=-1):
    settings = engine.get_config_db("ai_settings", {})
    model_list = settings.get("custom_model_list", [])
    
    is_new = (index == -1)
    if model_data is None: model_data = {"name": "", "base": "", "key": "", "api_model": ""}
    
    st.caption("手动配置兼容 OpenAI 协议的模型。")
    
    c1, c2 = st.columns(2)
    with c1:
        new_name = st.text_input("💡 显示名称", value=model_data.get("name", ""), placeholder="例如: My-Model")
        new_base = st.text_input("🌐 Base URL", value=model_data.get("base", ""), placeholder="https://api.example.com/v1")
    with c2:
        new_api_id = st.text_input("📝 API Model ID", value=model_data.get("api_model", ""), placeholder="gpt-4o")
        new_key = st.text_input("🔑 API Key", value=model_data.get("key", ""), type="password")

    if st.button("🔌 测试连接", width="stretch"):
        if not new_key or not new_base: st.error("需填写 Key 和 Base URL")
        else:
            with st.spinner("连接中..."):
                cli = OpenAI(api_key=new_key, base_url=new_base)
                ok, msg = test_model_connection(cli, new_api_id)
                if ok: st.success(msg)
                else: st.error(msg)
    
    b1, b2 = st.columns(2)
    with b1:
        if st.button("取消", width="stretch"): st.rerun()
    with b2:
        if st.button("💾 保存", type="primary", width="stretch"):
            if not new_name or not new_base:
                st.error("名称和 Base URL 必填")
                return
            new_entry = {"name": new_name, "base": new_base, "key": new_key, "api_model": new_api_id}
            
            # 审计：汉化键名并脱敏
            audit_entry = {
                "模型名称": new_name,
                "API地址": new_base,
                "密钥": "******",
                "模型ID": new_api_id
            }
            
            if is_new:
                if any(m['name'] == new_name for m in model_list):
                    st.error("名称已存在")
                    return
                model_list.append(new_entry)
                log_audit_event("模型管理", "新建自定义模型", audit_entry)
            else:
                model_list[index] = new_entry
                log_audit_event("模型管理", "更新自定义模型", audit_entry)
            
            settings["custom_model_list"] = model_list
            engine.set_config_db("ai_settings", settings)
            st.session_state.temp_custom_models = model_list
            st.success("已保存"); time.sleep(0.5); st.rerun()

# --- 💾 保存配置确认弹窗 ---
@dialog_decorator("💾 确认保存配置", width="large")
def dialog_save_settings(engine, cfg, assignments):
    old_cfg = engine.get_config_db("ai_settings", {})
    old_assign = engine.get_config_db("model_assignments", {})
    
    config_changes = []
    # 差异对比逻辑
    for k, v in cfg.items():
        if k == 'custom_model_list': continue 
        old_v = old_cfg.get(k, "")
        if str(v) != str(old_v):
            display_old = "空" if old_v == "" else str(old_v)
            display_new = "空" if v == "" else str(v)
            change_type = "⚙️ 通用"
            
            # 敏感信息脱敏显示
            if "key" in k.lower(): 
                change_type = "🔑 密钥"
                display_old="******"
                display_new="******"
            elif "base" in k.lower(): change_type = "🌐 地址"
            elif "recharge" in k.lower(): change_type = "💰 余额"
            
            # 🔥 汉化配置差异详情
            config_changes.append({
                "配置项": k, 
                "类型": change_type, 
                "旧值": display_old, 
                "新值": display_new
            })

    assign_changes = []
    display_map = {}
    for k, v in MODEL_MAPPING.items(): display_map[k] = v['name']
    
    for m in cfg.get('custom_model_list', []): 
        display_map[f"CUSTOM::{m['name']}"] = m['name']
    
    for feat_key, new_model_key in assignments.items():
        old_model_key = old_assign.get(feat_key, "")
        if str(new_model_key) != str(old_model_key):
            old_name = display_map.get(old_model_key, old_model_key)
            new_name = display_map.get(new_model_key, new_model_key)
            feat_name = FEATURE_MODELS[feat_key]['name']
            if feat_name == "书籍导入 - 简介/分析": feat_name = "书籍管理-导入分析"
            
            # 🔥 汉化调度差异详情
            assign_changes.append({ 
                "功能场景": feat_name, 
                "原模型": old_name, 
                "新模型": new_name 
            })

    st.markdown("""<div style="background-color:#f0f2f6;padding:10px;border-radius:5px;border-left:4px solid #ffbd45;"><small>⚠️ 请核对以下变更。保存后立即生效。</small></div>""", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.metric("配置变更", f"{len(config_changes)}项"); c2.metric("调度变更", f"{len(assign_changes)}项")
    
    st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
    with st.container(height=300, border=True):
        t1, t2 = st.tabs(["配置详情", "调度详情"])
        with t1:
            if not config_changes: st.info("无变动")
            else: 
                for i in config_changes: st.write(f"**{i['配置项']}**: {i['旧值']} → **{i['新值']}**"); st.divider()
        with t2:
            if not assign_changes: st.info("无变动")
            else:
                for i in assign_changes: st.write(f"**{i['功能场景']}**: {i['原模型']} → **{i['新模型']}**"); st.divider()

    st.markdown('<div style="height: 15px;"></div>', unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    with b1: 
        if st.button("取消", width="stretch"): st.rerun()
    with b2:
        if st.button("✅ 确认并保存", type="primary", width="stretch"):
            engine.set_config_db("ai_settings", cfg)
            engine.set_config_db("model_assignments", assignments)
            _refresh_system_config(engine) 
            
            # 🔥 严格审计：记录具体的 Diff 数据（汉化 Key）
            audit_details = {
                "配置变更详情": config_changes,
                "调度变更详情": assign_changes
            }
            log_audit_event("配置管理", "保存系统设置", audit_details)
            
            st.success("已保存！"); time.sleep(0.5); st.rerun()

def render_header(icon, title):
    st.markdown(f"## {icon} {title}")

# ==============================================================================
# 🎨 渲染设置页面 (纯净版 + 恢复说明)
# ==============================================================================
def render_settings(engine):
    
    if 'operation_logs' not in st.session_state: st.session_state.operation_logs = []
    
    render_header("⚙️", "系统设置")
    
    # 1. 读取配置
    cfg = engine.get_config_db("ai_settings", {})
    default_assignments = {k: v['default'] for k, v in FEATURE_MODELS.items()}
    assignments = engine.get_config_db("model_assignments", default_assignments)
    pending_cfg = cfg.copy()
    pending_assignments = assignments.copy()

    # 初始化 Custom List
    if 'custom_model_list' not in pending_cfg:
        pending_cfg['custom_model_list'] = []
        if pending_cfg.get('custom_model_name'):
            pending_cfg['custom_model_list'].append({
                "name": pending_cfg.get('custom_model_name'),
                "base": pending_cfg.get('custom_model_base'),
                "key": pending_cfg.get('custom_model_key', ''),
                "api_model": pending_cfg.get('custom_api_model', '')
            })

    if 'temp_custom_models' not in st.session_state or \
       len(st.session_state.temp_custom_models) != len(pending_cfg['custom_model_list']):
        st.session_state.temp_custom_models = pending_cfg['custom_model_list'].copy()

    # =========================================================================
    # 界面风格
    # =========================================================================
    st.subheader("🎨 界面风格")
    theme_options = list(THEMES.keys())
    current_theme = st.session_state.get('current_theme', "翡翠森林")
    if current_theme not in theme_options: current_theme = theme_options[0]
    
    curr = st.selectbox("选择主题", theme_options, index=theme_options.index(current_theme), label_visibility="collapsed")
    if curr != st.session_state.current_theme:
        st.session_state.current_theme = curr; 
        log_audit_event('界面', f'切换主题', f"从 {st.session_state.current_theme} 切换到 {curr}")
        st.rerun()

    # =========================================================================
    # 模型配置中心
    # =========================================================================
    st.subheader("🤖 模型配置与调度中心")
    
    PROVIDER_CUSTOM_KEY = "🛠️ 自定义模型库"
    
    # 构建厂商列表: 仅 原生(config.py) + 自定义库
    all_provider_keys = list(MODEL_GROUPS.keys()) + [PROVIDER_CUSTOM_KEY]
    
    col_main_1, col_main_2 = st.columns([1.5, 4])

    # --- 左侧：厂商选择 ---
    with col_main_1:
        st.markdown("##### ① 选择厂商") 
        
        default_idx = 0
        if 'selected_provider_ui' in st.session_state:
            try: default_idx = all_provider_keys.index(st.session_state.selected_provider_ui)
            except: default_idx = 0
            
        selected_provider_ui = st.selectbox(
            "厂商列表", 
            all_provider_keys, 
            index=default_idx,
            key="provider_selector_main"
        )
        st.session_state.selected_provider_ui = selected_provider_ui
        
        # 显示 Info (恢复逻辑)
        st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
        
        info_text = None
        # 1. 尝试直接匹配
        if selected_provider_ui in PROVIDER_INFO:
            info_text = PROVIDER_INFO[selected_provider_ui]
        # 2. 尝试处理 "Custom"
        elif selected_provider_ui == PROVIDER_CUSTOM_KEY:
             info_text = PROVIDER_INFO.get("Custom")
        # 3. 尝试模糊匹配 (例如处理中文名差异)
        else:
            for k, v in PROVIDER_INFO.items():
                if k in selected_provider_ui: # 比如 "Aliyun (Qwen)" 包含 "Qwen"
                    info_text = v
                    break
        
        if info_text:
            st.info(info_text, icon="ℹ️")

    # --- 右侧：内容区域 ---
    with col_main_2:
        
        # A. 自定义模型库 (管理已添加的模型)
        if selected_provider_ui == PROVIDER_CUSTOM_KEY:
            st.markdown("##### ② 管理私有模型")
            
            model_list = st.session_state.temp_custom_models
            
            if not model_list:
                st.container(border=True).info("暂无模型，请点击下方按钮手动添加。")
            else:
                for idx, m in enumerate(model_list):
                    with st.container(border=True):
                        c_info, c_ops = st.columns([3, 1])
                        with c_info:
                            st.markdown(f"**{m.get('name')}**")
                            st.caption(f"ID: `{m.get('api_model')}`")
                        with c_ops:
                            b_edit, b_del = st.columns(2)
                            with b_edit:
                                if st.button("✏️", key=f"c_edit_{idx}", help="编辑"):
                                    dialog_edit_custom_model(engine, m, idx)
                            with b_del:
                                if st.button("🗑️", key=f"c_del_{idx}", help="删除"):
                                    name = model_list[idx]['name']
                                    model_list.pop(idx)
                                    pending_cfg["custom_model_list"] = model_list
                                    engine.set_config_db("ai_settings", pending_cfg)
                                    st.session_state.temp_custom_models = model_list
                                    log_audit_event("模型管理", "删除自定义模型", {"模型名称": name}, status="WARNING")
                                    st.rerun()
            
            if st.button("➕ 添加新模型", width="stretch"):
                dialog_edit_custom_model(engine, None, -1)

        # B. 原生厂商 (config.py 中的)
        elif selected_provider_ui in MODEL_GROUPS:
            provider_key = selected_provider_ui
            group = MODEL_GROUPS[provider_key]
            st.markdown(f"##### ② 配置 {provider_key}")
            
            db_base = cfg.get(f"base_{provider_key}", group['models'][group['default_key']]['base'])
            db_key = cfg.get(f"key_{provider_key}", "")
            current_recharge = cfg.get(f"recharge_{provider_key}", 0.0)

            c_in1, c_in2, c_in3 = st.columns([2, 2, 1.5])
            with c_in1:
                new_base = st.text_input("Base URL", value=db_base, key=f"ipt_base_{provider_key}")
            with c_in2:
                new_key = st.text_input("API Key", value=db_key, type="password", key=f"ipt_key_{provider_key}")
            with c_in3:
                recharge_val = st.number_input("余额 (¥)", min_value=0.0, value=current_recharge, step=1.0, format="%.2f", key=f"recharge_{provider_key}_input")

            pending_cfg[f"base_{provider_key}"] = new_base
            pending_cfg[f"key_{provider_key}"] = new_key
            pending_cfg[f"recharge_{provider_key}"] = recharge_val
            
            st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
            
            # 优化测试区域布局
            t_c1, t_c2, t_c3 = st.columns([1.5, 1, 1.5])    
            with t_c1:
                models = group['models']
                m_keys = list(models.keys())
                test_model_key = st.selectbox("选择模型", m_keys, format_func=lambda x: models[x]['name'])
            with t_c2:
                # 28px 占位符确保对齐
                st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
                if st.button("🧪 测试连接", key=f"btn_test_{provider_key}", width="stretch"):
                    if not new_key: st.error("请填写 Key")
                    else:
                        cli = OpenAI(api_key=new_key, base_url=new_base)
                        ok, msg = test_model_connection(cli, models[test_model_key]['api_model'])
                        if ok: st.success(msg)
                        else: st.error(msg)

    # =========================================================================
    # 同步与调度列表
    # =========================================================================
    pending_cfg['custom_model_list'] = st.session_state.temp_custom_models

    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)
    st.markdown("##### ③ 功能模型调度")
    
    display_map = {} 
    name_to_key_map = {} 
    for k, v in MODEL_MAPPING.items(): 
        display_map[k] = v['name']
        name_to_key_map[v['name']] = k
    
    for m in pending_cfg.get('custom_model_list', []):
        m_name = m.get('name', 'Unknown')
        if not m_name: continue
        # 🔥 修复：这里必须用 CUSTOM:: (双冒号)
        full_key = f"CUSTOM::{m_name}"
        display_name = f"🟢 {m_name}"
        display_map[full_key] = display_name
        name_to_key_map[display_name] = full_key

    if cfg.get('custom_model_name'):
         display_map["CUSTOM_MODEL"] = f"⚠️ {cfg.get('custom_model_name')} (旧)"

    all_display_names = list(name_to_key_map.keys())

    f_cols = st.columns(2)
    for i, (f_key, f_info) in enumerate(FEATURE_MODELS.items()):
        col = f_cols[i % 2]
        with col:
            current_assigned_key = assignments.get(f_key, f_info['default'])
            if current_assigned_key in display_map:
                current_display = display_map[current_assigned_key]
            # 🔥 修复：保持对双冒号的兼容读取
            elif current_assigned_key.startswith("CUSTOM::"):
                check_name = current_assigned_key.split("::")[1]
                found = False
                for dn in all_display_names:
                    if check_name in dn:
                        current_display = dn; found = True; break
                if not found: current_display = all_display_names[0] if all_display_names else ""
            else:
                current_display = all_display_names[0] if all_display_names else ""

            feature_name = f_info['name']
            if feature_name == "书籍导入 - 简介/分析": feature_name = "书籍管理-导入分析"
            
            new_display = st.selectbox(
                f"**{feature_name}**", 
                all_display_names, 
                index=all_display_names.index(current_display) if current_display in all_display_names else 0,
                key=f"sel_feat_{f_key}"
            )
            pending_assignments[f_key] = name_to_key_map.get(new_display, f_info['default'])

    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)
    c_save, c_info = st.columns([3, 1])
    with c_save:
        if st.button("💾 保存调度与厂商设置", type="primary", width="stretch"):
            dialog_save_settings(engine, pending_cfg, pending_assignments)
    with c_info:
        st.caption("提示：自定义模型的增删改已实时保存。此按钮主要用于保存调度配置。")

    with st.expander("🚨 危险区域：系统重置"):
        if st.button("🔥 执行系统重置", type="secondary", width="stretch"):
            dialog_reset_confirm()

    st.subheader("📋 系统安全审计日志")
    st.caption(f"当前会话追踪 ID: {get_session_id()}")
    logs_df = pd.DataFrame()
    if os.path.exists(SYSTEM_LOG_PATH) and os.path.getsize(SYSTEM_LOG_PATH) > 0:
        try:
            logs_df = pd.read_csv(SYSTEM_LOG_PATH).iloc[::-1].head(100)
            st.dataframe(logs_df, width="stretch", height=300, hide_index=True)
        except: pass
    else:
        st.info("暂无审计日志")