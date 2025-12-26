# mortal_write/views/dashboard.py

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import re
import csv
import uuid
import json
import threading
from datetime import datetime 
from utils import render_header
from logic import MODEL_MAPPING
# 核心修正：引入 MODEL_GROUPS 以保持与 Settings 同步
from config import DATA_DIR, MODEL_GROUPS

# ==============================================================================
# 🛡️ 严格审计日志系统 (Dashboard 集成版)
# ==============================================================================

SYSTEM_LOG_PATH = os.path.join(DATA_DIR, "logs", "system_audit.csv")
_log_lock = threading.Lock()

def get_session_id():
    """获取或生成当前会话的唯一追踪ID"""
    if "session_trace_id" not in st.session_state:
        st.session_state.session_trace_id = str(uuid.uuid4())[:8]
    return st.session_state.session_trace_id

def log_audit_event(category, action, details, status="SUCCESS", module="DASHBOARD"):
    """
    执行严格的审计日志写入
    """
    try:
        os.makedirs(os.path.dirname(SYSTEM_LOG_PATH), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_id = get_session_id()
        
        status_map = {"SUCCESS": "成功", "WARNING": "警告", "ERROR": "错误"}
        status_cn = status_map.get(status, status)
        
        module_map = {
            "DASHBOARD": "数据看板",
            "IDEA": "灵感风暴",
            "KNOWLEDGE": "知识库", 
            "CHARACTERS": "角色管理", 
            "BOOKS": "书籍管理", 
            "WRITER": "写作终端", 
            "SETTINGS": "系统设置"
        }
        module_cn = module_map.get(module, module)

        if isinstance(details, (dict, list)):
            try: details = json.dumps(details, ensure_ascii=False)
            except: details = str(details)
            
        row = [timestamp, session_id, module_cn, category, action, status_cn, details]
        
        with _log_lock:
            file_exists = os.path.exists(SYSTEM_LOG_PATH)
            with open(SYSTEM_LOG_PATH, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if not file_exists or os.path.getsize(SYSTEM_LOG_PATH) == 0:
                    writer.writerow(['时间', '会话ID', '模块', '类别', '操作', '状态', '详情']) 
                writer.writerow(row)
    except Exception as e:
        print(f"❌ 审计日志写入失败: {e}")

# ==============================================================================
# 🛠️ 辅助函数
# ==============================================================================

def parse_date_chinese(t_str):
    """将时间字符串转为 'YYYY年MM月DD日' 格式"""
    if not t_str: return "N/A"
    try:
        t_str_date_only = str(t_str).split(' ')[0]
        dt_obj = datetime.strptime(t_str_date_only, '%Y-%m-%d')
        return dt_obj.strftime('%Y年%m月%d日')
    except Exception:
        return str(t_str).split(' ')[0]

def correct_provider_name(row, custom_model_map=None):
    """
    修正服务商名称，优先匹配自定义模型，解决自定义厂商归属错误的问题
    """
    model = str(row.get('model', '')).strip()
    provider = str(row.get('provider', '')).strip()
    
    # 1. 🔥 优先匹配自定义模型映射 (Model ID -> Custom Name)
    # 如果该模型ID存在于用户的自定义列表中，直接返回用户定义的名称作为服务商
    if custom_model_map and model in custom_model_map:
        return custom_model_map[model]
        
    # 2. 强制映射规则 (根据模型名特征) - 仅在非自定义时生效
    model_lower = model.lower()
    if 'deepseek' in model_lower or 'dsk' in model_lower: return 'DeepSeek'
    elif 'claude' in model_lower: return 'Anthropic'
    elif 'gemini' in model_lower: return 'Google'
    elif 'kimi' in model_lower or 'moonshot' in model_lower: return 'Moonshot'
    elif 'hunyuan' in model_lower: return 'Tencent'
    elif 'qwen' in model_lower or 'dashscope' in model_lower: return 'Alibaba'
    elif 'gpt' in model_lower: return 'OpenAI'
    elif 'glm' in model_lower: return 'ZhipuAI'
    
    # 3. 如果日志中 provider 不为 AI/Custom，则信任原值，否则归为 Custom
    if provider and provider.upper() not in ['AI', 'CUSTOM', 'NONE', 'NAN']:
        return provider
        
    return 'Custom'

def simplify_role_name(role):
    """简化角色名称"""
    if not role: return "其他角色"
    role_str = str(role).lower()
    
    keywords_to_category = {
        'protagonist': '主角', 'antagonist': '反派', '主角': '主角', 
        '萧炎': '主角萧炎', '反派': '反派', '伙伴': '伙伴/盟友', 
        '盟友': '伙伴/盟友', '导师': '长辈/导师', '父亲': '家族成员', 
        '母亲': '家族成员', '妻子': '家族成员/伴侣', '伴侣': '家族成员/伴侣', 
        '红颜': '重要女性角色', '毒体': '特殊能力者', '强者': '强者/高手', 
        '村民': '普通角色', '配角': '其他配角', '重要': '重要角色', 
        '核心': '核心角色', 'main': '主要角色'
    }
    
    for keyword, category in keywords_to_category.items():
        if keyword in role_str: return category
    
    if len(role_str) > 12:
        cleaned = re.sub(r'\([^)]*\)', '', role_str)
        cleaned = re.sub(r'（[^）]*）', '', cleaned)
        parts = re.split(r'[/、·，,。]', cleaned)
        if parts and parts[0].strip():
            main_part = parts[0].strip()
            return main_part[:10] + '...' if len(main_part) > 12 else main_part
        return role_str[:10] + '...'
    
    return role_str

def map_book_title(title, book_id_to_title):
    """映射书籍标题"""
    if pd.isna(title): return "其他记录"
    title_str = str(title)
    if title_str.isdigit():
        book_id = int(title_str)
        if book_id in book_id_to_title: return book_id_to_title[book_id]
    if title_str.strip() == "" or "历史记录" in title_str: return "其他记录"
    return title_str

# ==============================================================================
# 📊 主渲染逻辑
# ==============================================================================

def render_dashboard(engine):
    """渲染数据看板页面"""
    db_mgr = st.session_state.db
    log_path = os.path.join(DATA_DIR, "logs", "usage_log.csv") 
    
    render_header("📊", "创作数据中心")
    
    # 记录进入审计 (仅一次)
    if st.session_state.get("last_menu_audit") != "dashboard":
        log_audit_event("访问记录", "进入数据看板", {})
        st.session_state["last_menu_audit"] = "dashboard"
    
    # --- 0. 🔥 预加载自定义模型配置 (构建映射表) ---
    custom_model_map = {}
    custom_providers_from_settings = set()
    try:
        settings_cfg = engine.get_config_db("ai_settings", {})
        if settings_cfg.get("custom_model_list"):
            for m in settings_cfg["custom_model_list"]:
                # 映射逻辑：API Model ID (日志中的值) -> Name (用户定义的厂商名)
                if m.get("api_model") and m.get("name"):
                    custom_model_map[str(m["api_model"]).strip()] = str(m["name"]).strip()
                    custom_providers_from_settings.add(str(m["name"]).strip())
        elif settings_cfg.get("custom_model_name"):
            # 兼容旧版单模型配置
            c_name = settings_cfg.get("custom_model_name")
            c_id = settings_cfg.get("custom_api_model", "")
            if c_name and c_id:
                custom_model_map[str(c_id).strip()] = str(c_name).strip()
                custom_providers_from_settings.add(str(c_name).strip())
    except Exception as e:
        print(f"Error loading custom settings: {e}")

    # --- 1. 获取书籍列表 ---
    all_books_data = db_mgr.query("SELECT id, title FROM books ORDER BY updated_at DESC")
    book_options = {"🌍 全局汇总 (所有书籍)": None}
    for b in all_books_data:
        book_options[f"📖 {b['title']}"] = b['id']
    book_id_to_title = {b['id']: b['title'] for b in all_books_data}
    
    # --- 2. 读取日志与预处理 ---
    df_usage = pd.DataFrame()
    real_providers_in_logs = set()
    token_col = None  # 标记是否找到 token 列

    if os.path.exists(log_path):
        try:
            df_usage = pd.read_csv(log_path)
            if not df_usage.empty:
                # 智能识别 Token 列 (支持 'tokens', 'total_tokens', 'usage')
                for cand in ['tokens', 'total_tokens', 'token_count']:
                    if cand in df_usage.columns:
                        token_col = cand
                        break
                
                # 🔥 修正服务商：传入 custom_model_map
                df_usage['provider'] = df_usage.apply(
                    lambda row: correct_provider_name(row, custom_model_map), 
                    axis=1
                )
                
                # 修正书名
                if 'book_title' not in df_usage.columns: df_usage['book_title'] = "其他记录"
                else: df_usage['book_title'] = df_usage['book_title'].apply(lambda x: map_book_title(x, book_id_to_title))
                
                # 修正日期
                if 'timestamp' in df_usage.columns:
                    try:
                        df_usage['timestamp'] = df_usage['timestamp'].astype(str)
                        df_usage['timestamp_dt'] = pd.to_datetime(df_usage['timestamp'], errors='coerce', format='mixed')
                        df_usage['date'] = df_usage['timestamp_dt'].dt.date
                        df_usage['date_str'] = df_usage['date'].astype(str)
                        df_usage = df_usage.dropna(subset=['date'])
                    except:
                        df_usage['date'] = None
                        df_usage['date_str'] = None
                
                real_providers_in_logs = set(df_usage['provider'].unique())
        except Exception as e:
            st.error(f"❌ 日志读取错误: {e}")

    # --- 3. 构建厂商筛选列表 (同步 Settings + 修正后的历史日志) ---
    standard_providers = list(MODEL_GROUPS.keys())
    
    # 合并、清洗、去重
    # 注意：real_providers_in_logs 现在包含了修正后的自定义厂商名
    all_raw = set(standard_providers + list(custom_providers_from_settings) + list(real_providers_in_logs))
    final_clean = []
    for p in all_raw:
        if not p: continue
        p_str = str(p).strip()
        if not p_str or p_str.upper() == "AI": continue # 屏蔽 'AI'
        final_clean.append(p_str)
    
    final_provider_list = ["全部厂商"] + sorted(final_clean)

    # --- 4. 筛选器 UI ---
    with st.container(border=True):
        c_filt_1, c_filt_2 = st.columns(2)
        with c_filt_1:
            # 自动定位当前书籍
            curr_sess_id = st.session_state.get('current_book_id')
            def_idx = 0
            if curr_sess_id:
                ids = list(book_options.values())
                if curr_sess_id in ids: def_idx = ids.index(curr_sess_id)
            
            sel_book = st.selectbox("📚 统计范围", list(book_options.keys()), index=def_idx)
            tgt_bk_id = book_options[sel_book]
            tgt_bk_title = sel_book.replace("📖 ", "") if tgt_bk_id else None
            
            # 🔥 审计：筛选变化
            if sel_book != st.session_state.get("last_dash_book"):
                log_audit_event("视图筛选", "切换书籍范围", {"新范围": sel_book})
                st.session_state["last_dash_book"] = sel_book

        with c_filt_2:
            sel_prov = st.selectbox("🤖 服务商筛选", final_provider_list, index=0)
            
            # 🔥 审计：筛选变化
            if sel_prov != st.session_state.get("last_dash_prov"):
                log_audit_event("视图筛选", "切换服务商", {"新服务商": sel_prov})
                st.session_state["last_dash_prov"] = sel_prov

    scope_mode = "Book" if tgt_bk_id else "Global"

    # --- 5. 核心指标统计 (Metrics) ---
    # 基础统计
    g_chap = db_mgr.query("SELECT count(id) as c FROM chapters")[0]['c'] or 0
    g_word = db_mgr.query("SELECT sum(length(content)) as c FROM chapters")[0]['c'] or 0
    g_books = db_mgr.query("SELECT count(*) as c FROM books")[0]['c'] or 0
    g_char = db_mgr.query("SELECT count(*) as c FROM characters")[0]['c'] or 0

    b_chap, b_word, b_char = 0, 0, 0
    if tgt_bk_id:
        res = db_mgr.query("""
            SELECT count(c.id) as cc, sum(length(c.content)) as wc 
            FROM chapters c JOIN volumes v ON c.volume_id = v.id WHERE v.book_id = ?
        """, (tgt_bk_id,))
        if res: b_chap, b_word = res[0]['cc'] or 0, res[0]['wc'] or 0
        cr = db_mgr.query("SELECT count(*) as c FROM characters WHERE book_id=?", (tgt_bk_id,))
        if cr: b_char = cr[0]['c'] or 0

    disp_word = b_word if scope_mode == "Book" else g_word
    disp_chap = b_chap if scope_mode == "Book" else g_chap
    disp_char = b_char if scope_mode == "Book" else g_char
    rem_funds, _ = engine.get_remaining_funds(provider="All")

    # 渲染 Metrics 行
    # 如果有 token 数据，显示 7 列，否则显示 6 列
    if token_col and not df_usage.empty:
        # 计算 Token 总量 (受筛选影响)
        _df_metric = df_usage.copy()
        if scope_mode == "Book" and tgt_bk_title:
             _df_metric = _df_metric[_df_metric['book_title'] == tgt_bk_title]
        if sel_prov != "全部厂商":
             _df_metric = _df_metric[_df_metric['provider'] == sel_prov]
        total_tokens_val = _df_metric[token_col].sum() if not _df_metric.empty else 0
        
        cols = st.columns(7)
        cols[0].metric("📚 书籍总数", g_books)
        cols[1].metric("🖋️ 统计字数", f"{disp_word:,}")
        cols[2].metric("🪙 消耗Tokens", f"{int(total_tokens_val):,}") # 新增
        cols[3].metric("📑 统计章节", disp_chap) 
        cols[4].metric("👥 统计角色", disp_char)
        if scope_mode == "Book": cols[5].metric("🌍 全局字数", f"{g_word:,}")
        else: cols[5].metric("📖 平均字数", int(g_word/g_books) if g_books else 0)
        cols[6].metric("💰 剩余金额", f"¥ {rem_funds:,.2f}")
    else:
        cols = st.columns(6)
        cols[0].metric("📚 书籍总数", g_books)
        cols[1].metric("🖋️ 统计字数", f"{disp_word:,}")
        cols[2].metric("📑 统计章节", disp_chap) 
        cols[3].metric("👥 统计角色", disp_char)
        if scope_mode == "Book": cols[4].metric("🌍 全局字数", f"{g_word:,}")
        else: cols[4].metric("📖 平均字数", int(g_word/g_books) if g_books else 0)
        cols[5].metric("💰 剩余金额", f"¥ {rem_funds:,.2f}")

    st.write("") # Spacer

    # --- 6. 分布图表 ---
    g3, g4 = st.columns(2)
    with g3:
        # 角色分布
        suffix = f"({tgt_bk_title})" if scope_mode == "Book" else "(全局)"
        st.subheader(f"🧬 角色分布 {suffix}")
        
        if scope_mode == "Book":
            roles = db_mgr.query("SELECT role, count(*) as c FROM characters WHERE book_id=? GROUP BY role", (tgt_bk_id,))
        else:
            roles = db_mgr.query("SELECT role, count(*) as c FROM characters GROUP BY role")

        if roles:
            r_list = [{"类型": simplify_role_name(r['role']), "数": r['c']} for r in roles]
            r_df = pd.DataFrame(r_list).groupby("类型")['数'].sum().reset_index()
            
            if not r_df.empty:
                r_df = r_df.sort_values('数', ascending=True)
                if len(r_df) > 12: r_df = r_df.tail(12) # 取Top12
                
                fig = px.bar(r_df, y='类型', x='数', color='数', orientation='h', height=360)
                fig.update_layout(yaxis_title="", xaxis_title="数量", showlegend=False, margin=dict(l=10, r=10, t=30, b=30))
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("暂无角色数据")
        else: st.info("暂无角色数据")

    with g4:
        # 章节/字数分布
        if scope_mode == "Book":
            st.subheader(f"📑 分卷占比 {suffix}")
            v_stats = []
            if tgt_bk_id:
                vols = db_mgr.query("SELECT id, name FROM volumes WHERE book_id=?", (tgt_bk_id,))
                for v in vols:
                    c = db_mgr.query("SELECT count(id) as c FROM chapters WHERE volume_id=?", (v['id'],))[0]['c']
                    v_stats.append({"卷名": v['name'], "章节": c or 0})
            if v_stats and sum(d['章节'] for d in v_stats) > 0:
                fig = px.pie(pd.DataFrame(v_stats), values='章节', names='卷名', hole=0.4, height=360)
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("本书暂无章节")
        else:
            st.subheader("📚 书籍字数分布 (全局)")
            b_stats = []
            if all_books_data:
                for b in all_books_data:
                    c = db_mgr.query("SELECT sum(length(c.content)) as c FROM chapters c JOIN volumes v ON c.volume_id = v.id WHERE v.book_id=?", (b['id'],))[0]['c']
                    b_stats.append({"书名": b['title'], "字数": c or 0})
            if b_stats and sum(d['字数'] for d in b_stats) > 0:
                fig = px.pie(pd.DataFrame(b_stats), values='字数', names='书名', hole=0.4, height=360)
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("暂无字数数据")

    # --- 7. 趋势与消耗 ---
    st.subheader("💸 创作消耗分析")

    if not df_usage.empty and 'date' in df_usage.columns:
        df_filt = df_usage.copy()
        if scope_mode == "Book" and tgt_bk_title:
            df_filt = df_filt[df_filt['book_title'] == tgt_bk_title]
        # 🔥 筛选修复：现在 df_filt['provider'] 已经是修正后的名称，可以直接筛选
        if sel_prov != "全部厂商":
            df_filt = df_filt[df_filt['provider'] == sel_prov]

        c_tr_1, c_tr_2 = st.columns(2)
        
        # 图表 A: 每日产出 (支持切换 Token)
        with c_tr_1:
            # 动态标题
            y_col = 'chars'
            y_label = "生成字数"
            
            # 如果存在 Token 列，优先显示或提示
            if token_col:
                st.markdown("**📈 每日 Usage 趋势**")
                view_mode = st.radio("显示维度", ["字数 (Chars)", "Tokens"], horizontal=True, label_visibility="collapsed", key="chart_toggle")
                if view_mode == "Tokens":
                    y_col = token_col
                    y_label = "Tokens"
            else:
                st.markdown("**📈 每日生成量 (字数)**")

            if not df_filt.empty and y_col in df_filt.columns:
                group_col = 'date_str' if 'date_str' in df_filt else 'date'
                daily = df_filt.groupby(group_col)[y_col].sum().reset_index()
                daily.columns = ['日期', y_label]
                if not daily.empty:
                    daily = daily.sort_values('日期')
                    fig = px.line(daily, x='日期', y=y_label, markers=True)
                    # 🔥 汉化日期轴 & 限制精度到日
                    fig.update_xaxes(tickformat="%Y年%m月%d日")
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info("无数据")
            else: st.info("无数据")

        # 图表 B: 每日花费
        with c_tr_2:
            st.markdown(f"**📉 每日 AI 花费 (¥)**")
            if not df_filt.empty and 'cost' in df_filt.columns:
                # 占位符以对齐 Tab
                if token_col: st.markdown('<div style="height: 29px;"></div>', unsafe_allow_html=True)
                
                group_col = 'date_str' if 'date_str' in df_filt else 'date'
                daily_c = df_filt.groupby(group_col)['cost'].sum().reset_index()
                daily_c.columns = ['日期', '花费 (¥)']
                if not daily_c.empty:
                    daily_c = daily_c.sort_values('日期')
                    fig = px.line(daily_c, x='日期', y='花费 (¥)', markers=True, color_discrete_sequence=['#FF4B4B'])
                    # 🔥 汉化日期轴 & 限制精度到日
                    fig.update_xaxes(tickformat="%Y年%m月%d日")
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info("无数据")
            else: st.info("无数据")

        # 详细报表
        with st.expander("📊 查看详细消耗报表", expanded=True):
            if not df_filt.empty:
                t_cost = df_filt['cost'].sum()
                t_char = df_filt['chars'].sum()
                t_token = df_filt[token_col].sum() if token_col else 0
                
                # 指标栏
                if token_col:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("总消耗 (¥)", f"¥ {t_cost:.4f}")
                    m2.metric("总生成 (字)", f"{t_char:,}")
                    m3.metric("总 Tokens", f"{int(t_token):,}")
                else:
                    m1, m2 = st.columns(2)
                    m1.metric("总消耗 (¥)", f"¥ {t_cost:.4f}")
                    m2.metric("总生成 (字)", f"{t_char:,}")

                # 表格数据
                grp = ['book_title', 'provider', 'model'] if scope_mode == "Global" else ['provider', 'model']
                agg_dict = {'cost': 'sum', 'chars': 'sum'}
                if token_col: agg_dict[token_col] = 'sum'
                
                stats_v = df_filt.groupby(grp).agg(agg_dict).reset_index().sort_values('cost', ascending=False)
                
                # 重命名列
                rn = {'cost': '花费(¥)', 'chars': '字数', 'book_title': '书籍', 'provider': '厂商', 'model': '模型'}
                if token_col: rn[token_col] = 'Tokens'
                stats_v.rename(columns=rn, inplace=True)
                
                col_conf = {
                    "花费(¥)": st.column_config.NumberColumn(format="¥ %.4f"),
                    "字数": st.column_config.NumberColumn(format="%d"),
                }
                if token_col:
                    col_conf["Tokens"] = st.column_config.NumberColumn(format="%d")

                st.dataframe(stats_v, use_container_width=True, hide_index=True, column_config=col_conf)
            else: st.info("无数据")

    else:
        st.info("📂 暂无日志文件")

    # --- 8. 全局书籍表 (仅 Global) ---
    if scope_mode == "Global" and all_books_data:
        st.subheader("📋 各书统计")
        t_data = []
        for b in all_books_data:
            s = db_mgr.query("SELECT count(c.id) as cc, sum(length(c.content)) as wc FROM chapters c JOIN volumes v ON c.volume_id=v.id WHERE v.book_id=?", (b['id'],))
            created = parse_date_chinese(db_mgr.query("SELECT created_at FROM books WHERE id=?", (b['id'],))[0]['created_at'])
            t_data.append({
                "书名": b['title'], "章节": s[0]['cc'] or 0, "字数": s[0]['wc'] or 0, "创建": created
            })
        st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)