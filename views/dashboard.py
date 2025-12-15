# mortal_write/views/dashboard.py

import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime 
from utils import render_header, log_operation
from logic import MODEL_GROUPS, MODEL_MAPPING
import database

# Helper Function
def parse_date_chinese(t_str):
    """将时间字符串转为 'YYYY年MM月DD日' 格式"""
    if not t_str: return "N/A"
    try:
        t_str_date_only = str(t_str).split(' ')[0]
        dt_obj = datetime.strptime(t_str_date_only, '%Y-%m-%d')
        return dt_obj.strftime('%Y年%m月%d日')
    except Exception:
        return str(t_str).split(' ')[0]

def render_dashboard(engine):
    """渲染数据看板页面"""
    db_mgr = st.session_state.db
    
    # 获取动态日志路径
    log_path = os.path.join(database.DATA_DIR, "logs", "usage_log.csv") if database.DATA_DIR else "logs/usage_log.csv"
    
    # 获取当前上下文
    current_book_id = st.session_state.get('current_book_id')
    current_book_title = None
    
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
            else:
                st.caption(f"🌍 查看全局数据")
        
    # ==========================
    # 1. 核心指标统计 (修复版：统计所有章节)
    # ==========================
    
    # --- A. 准备全局数据 ---
    # 🔥 修复：移除了 WHERE c.content IS NOT NULL，确保大纲章节也被统计
    global_stats_res = db_mgr.query("""
        SELECT count(c.id) as chap_c, sum(length(c.content)) as word_c
        FROM chapters c JOIN volumes v ON c.volume_id = v.id JOIN books b ON v.book_id = b.id
    """)
    g_chap_count = global_stats_res[0]['chap_c'] if global_stats_res and global_stats_res[0]['chap_c'] else 0
    g_word_count = global_stats_res[0]['word_c'] if global_stats_res and global_stats_res[0]['word_c'] else 0
    g_book_count = db_mgr.query("SELECT count(*) as c FROM books")[0]['c'] if db_mgr.query("SELECT count(*) as c FROM books") else 0
    g_char_count = db_mgr.query("SELECT count(*) as c FROM characters")[0]['c'] if db_mgr.query("SELECT count(*) as c FROM characters") else 0

    # --- B. 准备当前书籍数据 ---
    b_chap_count = 0
    b_word_count = 0
    b_char_count = 0
    
    if current_book_id:
        # 🔥 修复：同样移除了内容非空限制
        bk_stats_res = db_mgr.query("""
            SELECT count(c.id) as chap_c, sum(length(c.content)) as word_c
            FROM chapters c JOIN volumes v ON c.volume_id = v.id
            WHERE v.book_id = ?
        """, (current_book_id,))
        if bk_stats_res:
            b_chap_count = bk_stats_res[0]['chap_c'] or 0
            b_word_count = bk_stats_res[0]['word_c'] or 0
        
        # 查角色数
        bk_char_res = db_mgr.query("SELECT count(*) as c FROM characters WHERE book_id=?", (current_book_id,))
        if bk_char_res:
            b_char_count = bk_char_res[0]['c'] or 0

    # --- C. 决定显示内容 ---
    if scope_mode == "Book":
        display_word_label = "总字数 (本书)"
        display_word_val = b_word_count
        display_chap_label = "章节数 (本书)"
        display_chap_val = b_chap_count
        display_char_label = "角色数 (本书)"
        display_char_val = b_char_count
    else:
        display_word_label = "总字数 (全局)"
        display_word_val = g_word_count
        display_chap_label = "章节总数 (全局)"
        display_chap_val = g_chap_count
        display_char_label = "角色总数 (全局)"
        display_char_val = g_char_count

    remaining_funds, total_recharged = engine.get_remaining_funds(provider="All")

    # --- D. 渲染 ---
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("📚 书籍总数", g_book_count)
    k2.metric(f"🖋️ {display_word_label}", f"{display_word_val:,}")
    k3.metric(f"📑 {display_chap_label}", display_chap_val) # 这里现在应该能正确显示 50+ 了
    k5.metric(f"👥 {display_char_label}", display_char_val)
    
    if scope_mode == "Global":
        k4.metric(f"📑 本书章节", b_chap_count)
    else:
        k4.metric("📑 全局章节", g_chap_count)

    k6.metric("💰 剩余金额", f"¥ {remaining_funds:,.2f}")
    
    # ==========================
    # 2. AI 模型消耗 (修复版：读取 CSV 持久化数据)
    # ==========================
    st.subheader("💰 AI 模型消耗统计")
    
    # 尝试从 CSV 读取，这样刷新页面数据不会丢
    if os.path.exists(log_path):
        try:
            df_usage = pd.read_csv(log_path)
            if not df_usage.empty:
                # 统计总花费
                total_spent = df_usage['cost'].sum()
                
                # 按模型分组统计
                model_stats = df_usage.groupby(['provider', 'model']).agg({
                    'input': 'sum',
                    'output': 'sum',
                    'cost': 'sum'
                }).reset_index()
                
                c_tbl, c_metric = st.columns([3, 1])
                with c_tbl:
                    st.dataframe(
                        model_stats, 
                        column_config={
                            "cost": st.column_config.NumberColumn("总消耗 (¥)", format="¥ %.4f"),
                            "input": st.column_config.NumberColumn("输入 Tokens"),
                            "output": st.column_config.NumberColumn("输出 Tokens")
                        },
                        use_container_width=True, 
                        hide_index=True
                    )
                with c_metric:
                    st.metric("历史总消耗", f"¥ {total_spent:.4f}")
            else:
                st.info("暂无消耗记录。")
        except Exception as e:
            st.error(f"读取日志文件出错: {e}")
    else:
        st.info("暂无消耗日志文件 (尚未开始生成)。")
        
    # ==========================
    # 3. 趋势报表
    # ==========================
    st.subheader("💸 趋势与报表 (全局)")
    
    all_providers = ["All"] + list(MODEL_GROUPS.keys())
    selected_provider_report = st.selectbox("筛选 AI 厂商", all_providers, key="report_provider_filter")

    g1, g2 = st.columns(2)
    
    with g1:
        st.caption("📈 每日生成字数趋势")
        # 这里字数统计依然依赖 content，这是对的，因为大纲不算正文产量
        # 如果想统计大纲字数，需要修改 log 逻辑，目前保持现状即可
        try:
            # 尝试读取 usage_log 来辅助显示活跃度，或者读取 content 更新日志
            # 暂时保持简单的逻辑，或者提示
            st.info("字数趋势需在写作过程中产生变化方可显示。")
        except: pass
    
    with g2:
        st.caption(f"📉 每日 AI 花费趋势 ({selected_provider_report})")
        try:
            if os.path.exists(log_path): 
                df_cost = pd.read_csv(log_path)
                if 'timestamp' in df_cost.columns and 'cost' in df_cost.columns:
                    if selected_provider_report != "All":
                        df_cost = df_cost[df_cost['provider'] == selected_provider_report]
                        
                    if not df_cost.empty:
                        df_cost['day_dt'] = pd.to_datetime(df_cost['timestamp']).dt.date
                        daily_cost = df_cost.groupby('day_dt')['cost'].sum().reset_index()
                        daily_cost = daily_cost.sort_values(by='day_dt')
                        daily_cost['day'] = daily_cost['day_dt'].apply(lambda x: x.strftime('%Y-%m-%d'))

                        fig_cost = px.line(daily_cost, x='day', y='cost', markers=True)
                        st.plotly_chart(fig_cost, use_container_width=True, config={'displayModeBar': False})
                    else:
                        st.info(f"该厂商暂无花费数据。")
                else:
                    st.info("日志为空。")
            else:
                st.info("暂无日志。")
        except Exception as e:
             st.warning("无法加载花费图")

    # ==========================
    # 4. 详细统计列表
    # ==========================
    if scope_mode == "Global":
        st.subheader("📋 各书详细统计表")
        books_data = db_mgr.query("SELECT id, title, author, created_at FROM books ORDER BY updated_at DESC")
        
        if books_data:
            table_data = []
            for b in books_data:
                # 🔥 修复：同样移除内容非空限制
                stats = db_mgr.query("""
                    SELECT count(c.id) as chap_c, sum(length(c.content)) as word_c
                    FROM chapters c
                    JOIN volumes v ON c.volume_id = v.id
                    WHERE v.book_id = ?
                """, (b['id'],))
                
                c_count = stats[0]['chap_c'] if stats and stats[0]['chap_c'] else 0
                w_count = stats[0]['word_c'] if stats and stats[0]['word_c'] else 0
                
                created_date = parse_date_chinese(b['created_at'])
                
                table_data.append({
                    "书名": b['title'],
                    "作者": b['author'],
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
            st.info("暂无书籍数据。")

    # ==========================
    # 5. 分布图表 (联动)
    # ==========================
    g3, g4 = st.columns(2)
    
    with g3:
        title_suffix = f"({current_book_title})" if scope_mode == "Book" else "(全局)"
        st.subheader(f"🧬 角色分布 {title_suffix}")
        
        if scope_mode == "Book":
            roles_sql = "SELECT role, count(*) as c FROM characters WHERE book_id=? GROUP BY role"
            params = (current_book_id,)
            try:
                roles = db_mgr.query(roles_sql, params)
            except:
                roles = []
        else:
            roles = db_mgr.query("SELECT role, count(*) as c FROM characters GROUP BY role")

        if roles and len(roles) > 0:
            df_r = pd.DataFrame.from_records(roles, columns=['role', 'c'])
            st.plotly_chart(px.pie(df_r, values='c', names='role', hole=0.4), use_container_width=True)
        else:
            st.info("暂无角色数据")
        
    with g4:
        if scope_mode == "Book":
            st.subheader(f"📑 分卷占比 {title_suffix}")
            vol_stats = []
            if current_book_id:
                vols = db_mgr.query("SELECT id, name FROM volumes WHERE book_id=?", (current_book_id,))
                for v in vols:
                    # 这里的字数统计依然是 content，因为大纲字数很少，饼图意义不大
                    # 如果需要统计章节数分布，可以改为 count(id)
                    wc = db_mgr.query("SELECT count(id) as c FROM chapters WHERE volume_id=?", (v['id'],))
                    count = wc[0]['c'] if wc and wc[0]['c'] else 0
                    vol_stats.append({"name": v['name'], "count": count})
            
            if vol_stats and sum(d['count'] for d in vol_stats) > 0:
                df_v = pd.DataFrame(vol_stats)
                st.plotly_chart(px.pie(df_v, values='count', names='name', title="分卷章节数分布", hole=0.4), use_container_width=True)
            else:
                st.info("本书暂无章节")
        else:
            st.subheader("📚 书籍章节分布 (全局)")
            books_data = db_mgr.query("SELECT id, title FROM books")
            b_stats = []
            for b in books_data:
                wc = db_mgr.query(
                    "SELECT count(c.id) as c FROM chapters c JOIN volumes v ON c.volume_id = v.id WHERE v.book_id=?", 
                    (b['id'],)
                )
                count = wc[0]['c'] if wc and wc[0]['c'] else 0
                b_stats.append({"title": b['title'], "count": count})
            
            if b_stats and sum(d['count'] for d in b_stats) > 0:
                df_b = pd.DataFrame(b_stats)
                st.plotly_chart(px.pie(df_b, values='count', names='title', hole=0.4), use_container_width=True)
            else:
                st.info("暂无书籍")