# mortal_write/views/dashboard.py

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import re
from datetime import datetime 
from utils import render_header
from logic import MODEL_MAPPING
from config import DATA_DIR

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

def correct_provider_name(row):
    """
    🔥 核心修复：根据模型名称强制修正服务商显示
    解决因为使用兼容API（如OneAPI）导致 DeepSeek/Claude 被记录为 OpenAI 的问题
    """
    model = str(row['model']).lower()
    provider = str(row['provider'])
    
    # 强制映射规则 (根据模型名特征)
    if 'deepseek' in model or 'dsk' in model:
        return 'DeepSeek'
    elif 'claude' in model:
        return 'Anthropic'
    elif 'gemini' in model:
        return 'Google'
    elif 'kimi' in model or 'moonshot' in model:
        return 'Moonshot'
    elif 'hunyuan' in model:
        return 'Tencent'
    elif 'qwen' in model or 'dashscope' in model:
        return 'Alibaba'
    elif 'gpt' in model:
        return 'OpenAI'
    elif 'glm' in model:
        return 'ZhipuAI'
    
    return provider

def get_config_providers():
    """从配置中获取服务商列表"""
    providers = set()
    if MODEL_MAPPING:
        for k, v in MODEL_MAPPING.items():
            if isinstance(v, dict):
                p = v.get('provider') or v.get('vendor')
                if p: 
                    providers.add(str(p))
    return sorted(list(providers))

def simplify_role_name(role):
    """简化角色名称，用于分组和显示"""
    if not role:
        return "其他角色"
    
    role_str = str(role).lower()  # 转换为小写以便匹配
    
    # 定义关键词到分类的映射
    keywords_to_category = {
        'protagonist': '主角',
        'antagonist': '反派',
        '主角': '主角',
        '主角的': '主角相关',
        '萧炎': '主角萧炎',
        '反派': '反派',
        '反派/': '反派',
        '反派角色': '反派',
        '伙伴': '伙伴/盟友',
        '盟友': '伙伴/盟友',
        '同伴': '伙伴/盟友',
        '长辈': '长辈/导师',
        '导师': '长辈/导师',
        '父亲': '家族成员',
        '母亲': '家族成员',
        '妻子': '家族成员/伴侣',
        '伴侣': '家族成员/伴侣',
        '红颜': '重要女性角色',
        '知己': '重要女性角色',
        '女王': '重要女性角色',
        '毒体': '特殊能力者',
        '强者': '强者/高手',
        '村民': '普通角色',
        '配角': '其他配角',
        '重要配角': '重要配角',
        '重要角色': '重要角色',
        '核心': '核心角色',
        'critical': '关键角色',
        'supporting': '配角',
        'main': '主要角色',
    }
    
    # 检查是否包含关键词
    for keyword, category in keywords_to_category.items():
        if keyword in role_str:
            return category
    
    # 如果名称过长，进行截断
    if len(role_str) > 12:
        # 先尝试提取主要部分
        # 移除括号内容
        cleaned = re.sub(r'\([^)]*\)', '', role_str)
        cleaned = re.sub(r'（[^）]*）', '', cleaned)
        
        # 按分隔符分割，取第一部分
        parts = re.split(r'[/、·，,。]', cleaned)
        if parts and parts[0].strip():
            main_part = parts[0].strip()
            if len(main_part) <= 12:
                return main_part
            else:
                return main_part[:10] + '...'
        
        return role_str[:10] + '...'
    
    return role_str

def map_book_title(title, book_id_to_title):
    """映射书籍标题，将ID转换为实际书名"""
    if pd.isna(title):
        return "其他记录"
    title_str = str(title)
    
    # 如果标题是数字，尝试作为ID查找
    if title_str.isdigit():
        book_id = int(title_str)
        if book_id in book_id_to_title:
            return book_id_to_title[book_id]
    
    # 如果是已知的"历史记录"，改为更友好的名称
    if title_str.strip() == "" or title_str == "历史记录" or "历史记录" in title_str:
        return "其他记录"
    
    # 如果是其他字符串，直接返回
    return title_str

# ==============================================================================
# 📊 主渲染逻辑
# ==============================================================================

def render_dashboard(engine):
    """渲染数据看板页面"""
    db_mgr = st.session_state.db
    log_path = os.path.join(DATA_DIR, "logs", "usage_log.csv") 
    
    # ==========================
    # 0. 顶部布局与筛选器 (Layout & Filters)
    # ==========================
    render_header("📊", "创作数据中心")
    
    # 获取所有书籍用于下拉列表
    all_books_data = db_mgr.query("SELECT id, title FROM books ORDER BY updated_at DESC")
    
    # 构建书籍选项: {显示名称: 书籍ID}
    # ID 为 None 代表全局
    book_options = {"🌍 全局汇总 (所有书籍)": None}
    for b in all_books_data:
        book_options[f"📖 {b['title']}"] = b['id']
    
    # 创建书籍ID到名称的映射
    book_id_to_title = {b['id']: b['title'] for b in all_books_data}
    
    # 预处理日志以获取真实存在的服务商
    df_usage = pd.DataFrame()
    real_providers = set()
    if os.path.exists(log_path):
        try:
            df_usage = pd.read_csv(log_path)
            if not df_usage.empty:
                # 预处理：修正服务商名称
                df_usage['provider'] = df_usage.apply(correct_provider_name, axis=1)
                
                # 预处理：处理书名 - 映射书籍ID到书籍名称
                if 'book_title' not in df_usage.columns:
                    df_usage['book_title'] = "其他记录"
                else:
                    df_usage['book_title'] = df_usage['book_title'].apply(
                        lambda x: map_book_title(x, book_id_to_title)
                    )
                
                # 预处理：时间 - 确保正确提取日期
                if 'timestamp' in df_usage.columns:
                    try:
                        # 确保 timestamp 列是字符串类型
                        df_usage['timestamp'] = df_usage['timestamp'].astype(str)
                        
                        # 转换为 datetime
                        df_usage['timestamp_dt'] = pd.to_datetime(
                            df_usage['timestamp'], 
                            errors='coerce',
                            format='mixed'
                        )
                        
                        # 提取日期部分（精确到日），并转换为字符串格式，避免毫秒显示
                        df_usage['date'] = df_usage['timestamp_dt'].dt.date
                        # 转换为字符串格式，确保只显示年月日
                        df_usage['date_str'] = df_usage['date'].astype(str)
                        
                        # 删除转换失败的行
                        initial_count = len(df_usage)
                        df_usage = df_usage.dropna(subset=['date'])
                        
                    except Exception as time_error:
                        df_usage['date'] = None
                        df_usage['date_str'] = None
                else:
                    df_usage['date'] = None
                    df_usage['date_str'] = None
                    
                real_providers = set(df_usage['provider'].unique())
        except Exception as e:
            st.error(f"❌ 日志读取错误: {e}")

    # 获取配置中的服务商和日志中的服务商
    config_providers = get_config_providers()
    
    # 合并服务商列表：配置中的服务商 + 日志中实际出现的服务商
    # 这样既可以看到配置中的选项，也能看到实际使用过的
    combined_providers = set(config_providers).union(real_providers)
    final_provider_list = ["全部厂商"] + sorted(list(combined_providers))

    # --- 筛选器 UI 容器 ---
    with st.container(border=True):
        col_filter_1, col_filter_2 = st.columns(2)
        
        with col_filter_1:
            # 默认选中当前 Session 中的书（如果存在）
            curr_sess_id = st.session_state.get('current_book_id')
            default_idx = 0
            if curr_sess_id:
                # 查找对应的 index
                titles = list(book_options.keys())
                ids = list(book_options.values())
                if curr_sess_id in ids:
                    default_idx = ids.index(curr_sess_id)

            selected_book_label = st.selectbox(
                "📚 统计范围 (书籍选择)", 
                list(book_options.keys()), 
                index=default_idx,
                help="选择特定书籍查看详情，或选择全局汇总"
            )
            target_book_id = book_options[selected_book_label]
            target_book_title = None
            if target_book_id:
                # 从 label 中提取纯标题用于日志筛选 (去除 "📖 " 前缀)
                target_book_title = selected_book_label.replace("📖 ", "")

        with col_filter_2:
            selected_provider = st.selectbox(
                "🤖 服务商筛选 (趋势/消耗)", 
                final_provider_list,
                index=0,
                help="筛选特定 AI 服务商的消耗记录"
            )

    # 确定当前模式
    scope_mode = "Book" if target_book_id else "Global"

    # ==========================
    # 1. 核心指标统计 (Metrics)
    # ==========================
    
    # A. 准备数据
    g_chap_count = db_mgr.query("SELECT count(id) as c FROM chapters")[0]['c'] or 0
    g_word_count = db_mgr.query("SELECT sum(length(content)) as c FROM chapters")[0]['c'] or 0
    g_book_count = db_mgr.query("SELECT count(*) as c FROM books")[0]['c'] or 0
    g_char_count = db_mgr.query("SELECT count(*) as c FROM characters")[0]['c'] or 0

    # 本书数据 (如果选中)
    b_chap_count = 0
    b_word_count = 0
    b_char_count = 0
    if target_book_id:
        b_res = db_mgr.query("""
            SELECT count(c.id) as chap_c, sum(length(c.content)) as word_c 
            FROM chapters c JOIN volumes v ON c.volume_id = v.id 
            WHERE v.book_id = ?
        """, (target_book_id,))
        if b_res:
            b_chap_count = b_res[0]['chap_c'] or 0
            b_word_count = b_res[0]['word_c'] or 0
        
        bc_res = db_mgr.query("SELECT count(*) as c FROM characters WHERE book_id=?", (target_book_id,))
        if bc_res: b_char_count = bc_res[0]['c'] or 0

    # 显示标签
    display_word = b_word_count if scope_mode == "Book" else g_word_count
    display_chap = b_chap_count if scope_mode == "Book" else g_chap_count
    display_char = b_char_count if scope_mode == "Book" else g_char_count
    
    remaining_funds, _ = engine.get_remaining_funds(provider="All")

    # B. 渲染指标
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("📚 书籍总数", g_book_count)
    k2.metric("🖋️ 统计字数", f"{display_word:,}")
    k3.metric("📑 统计章节", display_chap) 
    k4.metric("👥 统计角色", display_char)
    
    if scope_mode == "Book":
        k5.metric("🌍 全局字数", f"{g_word_count:,}")
    else:
        k5.metric("📖 书籍平均字数", int(g_word_count/g_book_count) if g_book_count else 0)

    k6.metric("💰 剩余金额", f"¥ {remaining_funds:,.2f}")

    # ==========================
    # 2. 分布图表 (Charts)
    # ==========================
    
    st.write("")  # 添加一点间距
    
    g3, g4 = st.columns(2)
    
    with g3:
        # 角色分布图 - 使用更智能的名称简化和分组
        suffix = f"({target_book_title})" if scope_mode == "Book" else "(全局)"
        st.subheader(f"🧬 角色分布 {suffix}")
        
        if scope_mode == "Book":
            roles = db_mgr.query("SELECT role, count(*) as c FROM characters WHERE book_id=? GROUP BY role", (target_book_id,))
        else:
            roles = db_mgr.query("SELECT role, count(*) as c FROM characters GROUP BY role")

        if roles:
            # 简化角色名称
            simplified_roles = []
            for r in roles:
                simplified_role = simplify_role_name(r['role'])
                simplified_roles.append({"角色类型": simplified_role, "数量": r['c']})
            
            # 合并相同的简化角色类型
            role_dict = {}
            for item in simplified_roles:
                role_type = item["角色类型"]
                count = item["数量"]
                if role_type in role_dict:
                    role_dict[role_type] += count
                else:
                    role_dict[role_type] = count
            
            # 转换为DataFrame
            df_r = pd.DataFrame([
                {"角色类型": k, "数量": v} for k, v in role_dict.items()
            ])
            
            # 使用水平条形图
            if len(df_r) > 0:
                # 按数量排序
                df_r = df_r.sort_values('数量', ascending=True)  # 升序，这样最高的在顶部
                
                # 限制显示的数量，避免过多导致拥挤
                max_display = 12
                if len(df_r) > max_display:
                    # 只显示数量最多的前max_display个
                    df_r_display = df_r.sort_values('数量', ascending=False).head(max_display)
                    df_r_display = df_r_display.sort_values('数量', ascending=True)  # 重新排序用于显示
                else:
                    df_r_display = df_r
                
                # 创建水平条形图
                fig = px.bar(
                    df_r_display, 
                    y='角色类型', 
                    x='数量',
                    color='数量',
                    color_continuous_scale='Viridis',
                    orientation='h',  # 水平条形图
                    title="角色类型分布",
                    height=380  # 设置固定高度
                )
                
                # 调整布局 - 更紧凑的布局
                fig.update_layout(
                    yaxis_title="角色类型",
                    xaxis_title="数量",
                    showlegend=False,
                    margin=dict(l=120, r=20, t=40, b=40),  # 调整边距
                    yaxis={
                        'categoryorder': 'total ascending',
                        'tickfont': dict(size=10)  # 减小y轴标签字体
                    },
                    xaxis={
                        'tickfont': dict(size=9)  # 减小x轴标签字体
                    }
                )
                
                # 添加数值标签
                fig.update_traces(texttemplate='%{x}', textposition='outside')
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 如果角色数量超过显示限制，显示提示
                if len(df_r) > max_display:
                    st.caption(f"仅显示数量最多的前 {max_display} 类角色（共 {len(df_r)} 类）")
            else:
                st.info("暂无角色数据")
        else:
            st.info("暂无角色数据")
        
    with g4:
        # 章节/字数分布图
        if scope_mode == "Book":
            st.subheader(f"📑 分卷占比 {suffix}")
            vol_stats = []
            if target_book_id:
                vols = db_mgr.query("SELECT id, name FROM volumes WHERE book_id=?", (target_book_id,))
                for v in vols:
                    wc = db_mgr.query("SELECT count(id) as c FROM chapters WHERE volume_id=?", (v['id'],))
                    count = wc[0]['c'] if wc and wc[0]['c'] else 0
                    vol_stats.append({"卷名": v['name'], "章节数": count})
            if vol_stats and sum(d['章节数'] for d in vol_stats) > 0:
                df_v = pd.DataFrame(vol_stats)
                # 创建饼图，设置相同高度
                fig = px.pie(df_v, values='章节数', names='卷名', hole=0.4, height=380)
                fig.update_layout(
                    margin=dict(t=40, b=40, l=40, r=40),  # 设置相似的边距
                    showlegend=True
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("本书暂无章节")
        else:
            st.subheader("📚 书籍字数分布 (全局)")
            books_data = db_mgr.query("SELECT id, title FROM books")
            b_stats = []
            for b in books_data:
                wc = db_mgr.query(
                    "SELECT sum(length(c.content)) as c FROM chapters c JOIN volumes v ON c.volume_id = v.id WHERE v.book_id=?", 
                    (b['id'],)
                )
                count = wc[0]['c'] if wc and wc[0]['c'] else 0
                b_stats.append({"书名": b['title'], "总字数": count})
            if b_stats and sum(d['总字数'] for d in b_stats) > 0:
                df_b = pd.DataFrame(b_stats)
                # 创建饼图，设置相同高度
                fig = px.pie(df_b, values='总字数', names='书名', hole=0.4, height=380)
                fig.update_layout(
                    margin=dict(t=40, b=40, l=40, r=40),  # 设置相似的边距
                    showlegend=True
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("暂无字数数据")

    # ==========================
    # 3. 趋势与消耗 (Trends)
    # ==========================
    st.subheader("💸 创作趋势与消耗")

    if not df_usage.empty and 'date' in df_usage.columns and not df_usage['date'].isna().all():
        # 3.1 筛选数据
        df_filtered = df_usage.copy()
        
        # 筛选 A: 书籍
        if scope_mode == "Book" and target_book_title:
            df_filtered = df_filtered[df_filtered['book_title'] == target_book_title]
            
            # 如果没找到数据，给个柔性提示
            if df_filtered.empty:
                st.warning(f"⚠️ 日志中未找到《{target_book_title}》的专属记录（可能是旧版日志或未产生消耗）。")
        
        # 筛选 B: 服务商
        if selected_provider != "全部厂商":
            df_filtered = df_filtered[df_filtered['provider'] == selected_provider]

        # 3.2 渲染图表
        col_trend_1, col_trend_2 = st.columns(2)

        # 图表 A: 每日产出
        with col_trend_1:
            st.markdown("**📈 每日生成量 (字数)**")
            if not df_filtered.empty and 'date' in df_filtered.columns and 'chars' in df_filtered.columns:
                # 使用字符串格式的日期，避免毫秒显示
                if 'date_str' in df_filtered.columns and not df_filtered['date_str'].isna().all():
                    # 按字符串日期分组
                    daily_chars = df_filtered.groupby('date_str')['chars'].sum().reset_index()
                    daily_chars.columns = ['日期', '生成量']
                else:
                    # 备用方案：使用日期对象
                    daily_chars = df_filtered.groupby('date')['chars'].sum().reset_index()
                    daily_chars.columns = ['日期', '生成量']
                    # 将日期转换为字符串格式
                    daily_chars['日期'] = daily_chars['日期'].astype(str)
                
                if not daily_chars.empty:
                    # 按日期排序
                    daily_chars = daily_chars.sort_values('日期')
                    
                    # 创建趋势图
                    fig = px.line(
                        daily_chars, 
                        x='日期', 
                        y='生成量', 
                        markers=True,
                        title="每日生成量趋势"
                    )
                    
                    # 优化布局
                    fig.update_layout(
                        xaxis_title="日期",
                        yaxis_title="生成字数",
                        hovermode="x unified",
                        xaxis={'type': 'category'}  # 将x轴设置为分类类型，避免时间格式解析
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("当前筛选条件下无生成量数据")
            else:
                st.info("缺少必要的列: 'date' 或 'chars'")

        # 图表 B: 每日花费
        with col_trend_2:
            prov_label = selected_provider if selected_provider != "全部厂商" else "所有厂商"
            st.markdown(f"**📉 每日 AI 花费 (¥) - {prov_label}**")
            if not df_filtered.empty and 'date' in df_filtered.columns and 'cost' in df_filtered.columns:
                # 使用字符串格式的日期，避免毫秒显示
                if 'date_str' in df_filtered.columns and not df_filtered['date_str'].isna().all():
                    # 按字符串日期分组
                    daily_cost = df_filtered.groupby('date_str')['cost'].sum().reset_index()
                    daily_cost.columns = ['日期', '花费 (¥)']
                else:
                    # 备用方案：使用日期对象
                    daily_cost = df_filtered.groupby('date')['cost'].sum().reset_index()
                    daily_cost.columns = ['日期', '花费 (¥)']
                    # 将日期转换为字符串格式
                    daily_cost['日期'] = daily_cost['日期'].astype(str)
                
                if not daily_cost.empty:
                    # 按日期排序
                    daily_cost = daily_cost.sort_values('日期')
                    
                    fig = px.line(
                        daily_cost, 
                        x='日期', 
                        y='花费 (¥)', 
                        markers=True, 
                        color_discrete_sequence=['#FF4B4B'],
                        title=f"每日花费趋势 - {prov_label}"
                    )
                    
                    # 优化布局
                    fig.update_layout(
                        xaxis_title="日期",
                        yaxis_title="花费 (¥)",
                        hovermode="x unified",
                        xaxis={'type': 'category'}  # 将x轴设置为分类类型，避免时间格式解析
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("当前筛选条件下无花费数据")
            else:
                st.info("缺少必要的列: 'date' 或 'cost'")
        
        # 3.3 详细表格
        with st.expander("📊 查看详细模型消耗报表", expanded=True):
            if not df_filtered.empty:
                total_spent = df_filtered['cost'].sum()
                total_chars = df_filtered['chars'].sum()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("总消耗", f"¥ {total_spent:.4f}")
                with col2:
                    st.metric("总生成量", f"{total_chars:,} 字")

                # 根据模式决定分组字段
                if scope_mode == "Global":
                    group_cols = ['book_title', 'provider', 'model']
                else:
                    group_cols = ['provider', 'model']
                    
                stats_view = df_filtered.groupby(group_cols).agg({
                    'cost': 'sum', 
                    'chars': 'sum'
                }).reset_index()
                
                stats_view = stats_view.sort_values(by='cost', ascending=False)
                
                rename_map = {
                    'book_title': '书籍名称', 
                    'provider': '服务商', 
                    'model': '模型名称', 
                    'cost': '总花费(¥)', 
                    'chars': '总字数'
                }
                stats_view.rename(columns=rename_map, inplace=True)
                
                st.dataframe(
                    stats_view, 
                    use_container_width=True, 
                    hide_index=True, 
                    column_config={
                        "总花费(¥)": st.column_config.NumberColumn(format="¥ %.4f"),
                        "总字数": st.column_config.NumberColumn(format="%d"),
                    }
                )
                
                # 显示一些统计数据
                st.caption(f"共 {len(df_filtered)} 条记录，平均每字成本: ¥ {total_spent/total_chars:.6f}" if total_chars > 0 else "无字数数据")
            else:
                st.info("无数据。")
    elif not df_usage.empty:
        st.warning("⚠️ 日志文件存在，但缺少日期信息或日期转换失败")
    else:
        st.info("📂 暂无日志文件 (尚未开始 AI 生成)。")

    # ==========================
    # 4. 全局书籍列表 (仅 Global 模式显示)
    # ==========================
    if scope_mode == "Global":
        st.subheader("📋 各书详细统计表")
        
        if all_books_data:
            table_data = []
            for b in all_books_data:
                stats = db_mgr.query("""
                    SELECT count(c.id) as chap_c, sum(length(c.content)) as word_c
                    FROM chapters c
                    JOIN volumes v ON c.volume_id = v.id
                    WHERE v.book_id = ?
                """, (b['id'],))
                
                c_count = stats[0]['chap_c'] if stats and stats[0]['chap_c'] else 0
                w_count = stats[0]['word_c'] if stats and stats[0]['word_c'] else 0
                
                created_date = parse_date_chinese(db_mgr.query("SELECT created_at FROM books WHERE id=?", (b['id'],))[0]['created_at'])
                
                table_data.append({
                    "书名": b['title'],
                    "章节总数": c_count,
                    "总字数": w_count,
                    "平均每章": int(w_count / c_count) if c_count > 0 else 0,
                    "创建时间": created_date
                })
                
            df_books = pd.DataFrame(table_data)
            st.dataframe(
                df_books,
                column_config={
                    "书名": st.column_config.TextColumn("书名", width="medium"),
                    "章节总数": st.column_config.NumberColumn("章节数", format="%d 章"),
                    "总字数": st.column_config.NumberColumn("总字数", format="%d 字"),
                    "平均每章": st.column_config.ProgressColumn("单章规模", format="%d 字", min_value=0, max_value=5000),
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("暂无书籍。")