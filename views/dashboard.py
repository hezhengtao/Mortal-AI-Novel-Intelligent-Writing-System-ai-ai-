

import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime 
from utils import render_header, get_sidebar_stats
from logic import MODEL_GROUPS, MODEL_MAPPING
from utils import log_operation


def parse_date_chinese(t_str):
    """将时间字符串转为 'YYYY年MM月DD日' 格式"""
    if not t_str: return "N/A"
    try:
        # 只取日期部分，忽略时间
        t_str_date_only = str(t_str).split(' ')[0]
        dt_obj = datetime.strptime(t_str_date_only, '%Y-%m-%d')
        return dt_obj.strftime('%Y年%m月%d日')
    except Exception:
        return str(t_str).split(' ')[0] # Fallback to YYYY-MM-DD

def render_dashboard(engine):
    """渲染数据看板页面"""
    db_mgr = st.session_state.db
    
    # 获取当前上下文
    current_book_id = st.session_state.get('current_book_id')
    current_book_title = None
    
    # 确定显示模式
    scope_mode = "Global" 
    
    if current_book_id:
        bk = db_mgr.query("SELECT title FROM books WHERE id=?", (current_book_id,))
        if bk:
            current_book_title = bk[0]['title']
            
    # 顶部区域
    c_head_1, c_head_2 = st.columns([3, 1])
    with c_head_1:
        render_header("📊", "创作数据中心")
    
    with c_head_2:
        if current_book_id and current_book_title:
            scope_selection = st.radio(
                "统计范围", 
                ["当前书籍", "全局汇总"], 
                index=0, 
                horizontal=True, 
                label_visibility="collapsed",
                key="dashboard_scope_selector"
            )
            if scope_selection == "当前书籍":
                scope_mode = "Book"
                st.caption(f"📍 聚焦: 《{current_book_title}》")
        
    # ==========================
    # 1. 核心指标统计
    # ==========================
    
    # 1. 永远计算全局统计 (Global Stats)
    global_stats_res = db_mgr.query("""
        SELECT count(c.id) as chap_c, sum(length(c.content)) as word_c
        FROM chapters c JOIN volumes v ON c.volume_id = v.id JOIN books b ON v.book_id = b.id
        WHERE c.content IS NOT NULL
    """)
    total_chapters_global = global_stats_res[0]['chap_c'] if global_stats_res and global_stats_res[0]['chap_c'] else 0
    word_count_global = global_stats_res[0]['word_c'] if global_stats_res and global_stats_res[0]['word_c'] else 0
    total_books_global = db_mgr.query("SELECT count(*) as c FROM books")[0]['c'] if db_mgr.query("SELECT count(*) as c FROM books") else 0
    total_chars_global = db_mgr.query("SELECT count(*) as c FROM characters")[0]['c'] if db_mgr.query("SELECT count(*) as c FROM characters") else 0

    # 2. 始终计算当前书籍章节数 (Current Book Chapters)
    total_chapters_current_book = 0
    if current_book_id:
        current_book_stats_res = db_mgr.query("""
            SELECT count(c.id) as chap_count
            FROM chapters c JOIN volumes v ON c.volume_id = v.id
            WHERE v.book_id = ? AND c.content IS NOT NULL
        """, (current_book_id,))
        total_chapters_current_book = current_book_stats_res[0]['chap_count'] if current_book_stats_res and current_book_stats_res[0]['chap_count'] else 0

    # 3. 获取资金信息
    remaining_funds, total_recharged = engine.get_remaining_funds(provider="All")

    # 4. 调整布局到 6 列
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    
    k1.metric("📚 书籍总数", total_books_global)
    k2.metric("🖋️ 总字数 (全局)", f"{word_count_global:,}")
    
    # FIX: 章节数拆分
    k3.metric("📑 章节总数 (全局)", total_chapters_global)
    k4.metric(f"📑 章节数 ({current_book_title or '未选'})", total_chapters_current_book)

    k5.metric("👥 角色总数", total_chars_global)
    
    k6.metric("💰 剩余金额 (¥)", f"¥ {remaining_funds:,.2f}", 
              delta=f"总充值: ¥ {total_recharged:,.2f}", 
              delta_color="off")
    
    # 🧹 已移除分割线 ---
    
    # ==========================
    # 2. AI 模型消耗 (当前会话)
    # ==========================
    st.subheader("💰 AI 模型消耗统计 (当前会话)")
    
    usage_data = []
    for model_key, stats in st.session_state.model_usage_stats.items():
        model_info = MODEL_MAPPING.get(model_key, {'name': model_key, 'provider': '未知'})
        if stats['cost'] > 0:
            usage_data.append({
                "厂商": model_info['provider'],
                "模型": model_info['name'],
                "输入字符": f"{stats['input']:,}",
                "输出字符": f"{stats['output']:,}",
                "总消耗 (¥)": f"¥ {stats['cost']:.4f}"
            })

    if usage_data:
        st.dataframe(pd.DataFrame(usage_data), use_container_width=True, hide_index=True)
    else:
        st.info("本会话中暂无 AI 模型使用记录。")
        
    
    # ==========================
    # 3. 趋势报表
    # ==========================
    st.subheader("💸 趋势与报表")
    
    all_providers = ["All"] + list(MODEL_GROUPS.keys())
    selected_provider_report = st.selectbox("筛选 AI 厂商", all_providers, key="report_provider_filter")

    g1, g2 = st.columns(2)
    
    with g1:
        st.subheader("📈 每日码字趋势")
        try:
            if os.path.exists("logs/usage_log.csv"):
                df = pd.read_csv("logs/usage_log.csv")
                
                # 🔥 修复 G1: 使用 .apply(lambda x: x.strftime) 解决 .dt accessor 错误
                df['day_dt'] = pd.to_datetime(df['timestamp']).dt.date
                daily = df.groupby('day_dt')['chars'].sum().reset_index()
                daily = daily.sort_values(by='day_dt')
                # 关键修复点：使用 .apply 格式化 Python date 对象
                daily['day'] = daily['day_dt'].apply(lambda x: x.strftime('%Y年%m月%d日')) 
                daily = daily.drop(columns=['day_dt'])
                
                # 🔥 图表格式已在上次改为折线图
                fig = px.line( 
                    daily, 
                    x='day', 
                    y='chars', 
                    title="每日生成字数 (全局)", 
                    markers=True, # 添加标记点
                    labels={'day': '日期', 'chars': '生成字数'} 
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            else:
                st.info("暂无数据，快去写作吧！")
        except Exception as e: 
            st.info(f"日志解析中... ({e})")
    
    with g2:
        st.subheader(f"历史花费趋势 (筛选: {selected_provider_report})")
        try:
            if os.path.exists("logs/usage_log.csv"):
                df_cost = pd.read_csv("logs/usage_log.csv")
                
                if selected_provider_report != "All":
                    df_cost = df_cost[df_cost['provider'] == selected_provider_report]
                    
                if not df_cost.empty:
                    
                    # 🔥 修复 G2: 使用 .apply(lambda x: x.strftime) 解决 .dt accessor 错误
                    df_cost['day_dt'] = pd.to_datetime(df_cost['timestamp']).dt.date
                    daily_cost = df_cost.groupby('day_dt')['cost'].sum().reset_index()
                    daily_cost = daily_cost.sort_values(by='day_dt')
                    # 关键修复点：使用 .apply 格式化 Python date 对象
                    daily_cost['day'] = daily_cost['day_dt'].apply(lambda x: x.strftime('%Y年%m月%d日'))
                    daily_cost = daily_cost.drop(columns=['day_dt'])

                    # 🛠️ 修改：添加 labels 参数实现中文显示
                    # 🚩 FIX: 隐藏工具栏
                    fig_cost = px.line(
                        daily_cost, 
                        x='day', 
                        y='cost', 
                        title="每日AI花费 (¥)", 
                        markers=True,
                        labels={'day': '日期', 'cost': '花费金额(元)'}
                    )
                    st.plotly_chart(fig_cost, use_container_width=True, config={'displayModeBar': False})
                else:
                    st.info(f"暂无 {selected_provider_report} 厂商的花费数据。")
            else:
                st.info("暂无 AI 花费日志文件。")
        except Exception as e:
             st.info(f"花费日志解析中... ({e})")

   
    
    # ==========================
    # 4. 详细统计列表
    # ==========================
    st.subheader("📋 各书详细统计表")
    
    books_data = db_mgr.query("SELECT id, title, author, created_at FROM books ORDER BY updated_at DESC")
    
    if books_data:
        table_data = []
        for b in books_data:
            stats = db_mgr.query("""
                SELECT count(c.id) as chap_c, sum(length(c.content)) as word_c
                FROM chapters c
                JOIN volumes v ON c.volume_id = v.id
                WHERE v.book_id = ?
            """, (b['id'],))
            
            c_count = stats[0]['chap_c'] if stats and stats[0]['chap_c'] else 0
            w_count = stats[0]['word_c'] if stats and stats[0]['word_c'] else 0
            
            # 🔥 修复点：使用新函数将创建时间改为 YYYY年MM月DD日 格式
            created_date = parse_date_chinese(b['created_at'])
            
            table_data.append({
                "书名": b['title'],
                "作者": b['author'],
                "章节总数": c_count,
                "总字数": w_count,
                "平均每章字数": int(w_count / c_count) if c_count > 0 else 0,
                "创建时间": created_date
            })
            
        df_books = pd.DataFrame(table_data)
        
        st.dataframe(
            df_books,
            column_config={
                "书名": st.column_config.TextColumn("书名", width="medium"),
                "章节总数": st.column_config.NumberColumn("章节数", format="%d 章"),
                "总字数": st.column_config.NumberColumn("总字数", format="%d 字"),
                "平均每章字数": st.column_config.ProgressColumn("单章规模", format="%d 字", min_value=0, max_value=5000),
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("暂无书籍数据。")

    

    # ==========================
    # 5. 分布图表 (联动)
    # ==========================
    g3, g4 = st.columns(2)
    
    with g3:
        st.subheader("🧬 角色分布")
        
        if scope_mode == "Book":
            roles_sql = "SELECT role, count(*) as c FROM characters WHERE book_id=? GROUP BY role"
            params = (current_book_id,)
            title_suffix = f"({current_book_title})"
            try:
                roles = db_mgr.query(roles_sql, params)
            except:
                roles = db_mgr.query("SELECT role, count(*) as c FROM characters GROUP BY role")
                title_suffix = "(全局)"
        else:
            roles = db_mgr.query("SELECT role, count(*) as c FROM characters GROUP BY role")
            title_suffix = "(全局)"

        if roles and len(roles) > 0:
            valid_roles = [r for r in roles if r['c'] and r['c'] > 0]
            if valid_roles:
                df_r = pd.DataFrame.from_records(valid_roles, columns=['role', 'c'])
                df_r['c'] = pd.to_numeric(df_r['c']) 
                # 🚩 FIX: 隐藏工具栏
                st.plotly_chart(
                    px.pie(
                        df_r, 
                        values='c', 
                        names='role', 
                        title=f"角色类型占比 {title_suffix}", 
                        hole=0.4,
                        labels={'role': '角色类型', 'c': '数量'}
                    ), 
                    use_container_width=True,
                    config={'displayModeBar': False}
                )
            else:
                st.info("暂无有效角色数据")
        else:
            st.info("暂无角色数据")
        
    with g4:
        if scope_mode == "Book":
            st.subheader("📑 分卷字数分布")
            vol_stats = []
            vols = db_mgr.query("SELECT id, name FROM volumes WHERE book_id=?", (current_book_id,))
            for v in vols:
                wc = db_mgr.query("SELECT sum(length(content)) as c FROM chapters WHERE volume_id=?", (v['id'],))
                count = wc[0]['c'] if wc and wc[0]['c'] else 0
                vol_stats.append({"name": v['name'], "count": count})
            
            if vol_stats and sum(d['count'] for d in vol_stats) > 0:
                df_v = pd.DataFrame(vol_stats)
                # 🚩 FIX: 隐藏工具栏
                st.plotly_chart(
                    px.pie(
                        df_v, 
                        values='count', 
                        names='name', 
                        title=f"《{current_book_title}》各卷占比", 
                        hole=0.4,
                        labels={'name': '卷名', 'count': '字数'}
                    ), 
                    use_container_width=True,
                    config={'displayModeBar': False}
                )
            else:
                st.info("本书暂无内容")
                
        else:
            st.subheader("📚 书籍字数分布")
            books_data = db_mgr.query("SELECT id, title FROM books")
            b_stats = []
            for b in books_data:
                wc = db_mgr.query(
                    "SELECT sum(length(c.content)) as c FROM chapters c JOIN volumes v ON c.volume_id = v.id WHERE v.book_id=?", 
                    (b['id'],)
                )
                count = wc[0]['c'] if wc and wc[0]['c'] else 0
                b_stats.append({"title": b['title'], "count": count})
            
            if b_stats and sum(d['count'] for d in b_stats) > 0:
                df_b = pd.DataFrame(b_stats)
                
                st.plotly_chart(
                    px.pie(
                        df_b, 
                        values='count', 
                        names='title', 
                        title="各书字数占比", 
                        hole=0.4,
                        labels={'title': '书名', 'count': '字数'}
                    ), 
                    use_container_width=True,
                    config={'displayModeBar': False}
                )
            else:
                st.info("暂无书籍内容字数")