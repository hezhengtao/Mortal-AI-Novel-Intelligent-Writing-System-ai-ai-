# mortal_write/run.py

import sys
import os
import time
import traceback

# ==========================================
# 0. 基础环境与日志配置
# ==========================================
USER_HOME = os.path.expanduser("~")
LOG_PATH = os.path.join(USER_HOME, "mortal_write.log")

class CriticalLogger:
    """捕获所有输出并写入日志文件"""
    def __init__(self):
        self.file = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
        self.terminal = sys.stdout 

    def write(self, message):
        try:
            self.file.write(message)
            if self.terminal: self.terminal.write(message)
        except: pass

    def flush(self):
        try:
            self.file.flush()
            if self.terminal: self.terminal.flush()
        except: pass

    def isatty(self): return False

sys.stdout = CriticalLogger()
sys.stderr = sys.stdout

print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 系统启动")
print(f"日志文件: {LOG_PATH}")

# ==========================================
# 1. 导入依赖库
# ==========================================
try:
    import threading
    import socket
    import webview
    import signal
    import json
    import ctypes
    import urllib.parse
    from ctypes import windll, Structure, c_long, byref, sizeof
except Exception as e:
    print(f"FATAL: 模块导入失败: {traceback.format_exc()}")
    sys.exit(1)

# ==========================================
# 2. 注册 AppID
# ==========================================
try:
    myappid = 'MortalWrite.Intelligent.System.Pro.Final' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception: pass

# ==========================================
# 3. Windows API 定义
# ==========================================
class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

class MONITORINFO(Structure):
    _fields_ = [("cbSize", c_long), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", c_long)]

GWL_STYLE = -16
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU     = 0x00080000 
SWP_NOZORDER     = 0x0004
SWP_NOACTIVATE   = 0x0010
SWP_FRAMECHANGED = 0x0020
MONITOR_DEFAULTTONEAREST = 0x00000002

def force_window_styles():
    """
    使用 FindWindowW 精准查找窗口，解决竞态条件问题。
    """
    target_title = "凡人智能写作系统"
    hwnd = 0
    
    # 尝试 20 次，每次间隔 0.25 秒
    for _ in range(20):
        hwnd = windll.user32.FindWindowW(None, target_title)
        if hwnd:
            break
        time.sleep(0.25)
    
    if not hwnd:
        print("Style Fix Warning: Could not find window handle.")
        return

    try:
        style = windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        style = style | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
        windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 
                                   SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | 0x0001 | 0x0002)
        print(f"Style Fix Applied to HWND: {hwnd}")
    except Exception as e:
        print(f"Style Fix Error: {e}")

# ==========================================
# 4. 全局变量
# ==========================================
original_signal = signal.signal
def patched_signal(sig, handler):
    if threading.current_thread() is threading.main_thread(): return original_signal(sig, handler)
    return None
signal.signal = patched_signal

WINDOW_INSTANCE = None 
STREAMLIT_PORT = 0  
HTTP_PORT = 0       
STREAMLIT_READY = threading.Event()
HTTP_READY = threading.Event()
ASSETS_DIR = None

# ==========================================
# 5. 路径与配置管理
# ==========================================
def find_real_path(filename):
    global ASSETS_DIR
    base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    
    paths = [
        os.path.join(base_dir, filename), 
        os.path.join(base_dir, 'mortal_write', filename),
        os.path.join(base_dir, '_internal', filename), 
        os.path.join(base_dir, '_internal', 'mortal_write', filename),
    ]
    if filename == 'assets':
        paths.extend([
            os.path.join(base_dir, 'mortal_write', 'assets'),
            os.path.join(base_dir, 'assets'),
        ])
        
    for path in paths:
        if path and os.path.exists(path):
            if filename == 'assets': ASSETS_DIR = path
            return path
    return None

def get_config_path():
    try:
        user_dir = os.path.expanduser("~")
        config_dir = os.path.join(user_dir, ".mortal_write_config")
        if not os.path.exists(config_dir): os.makedirs(config_dir)
        return os.path.join(config_dir, 'workspace_config.json')
    except: return "workspace_config.json"

def load_workspace_config():
    try:
        config_path = get_config_path()
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                path = data.get("workspace_path", "")
                if path and os.path.exists(path):
                    return path
                else:
                    return ""
    except Exception: pass
    return ""

def find_free_port(start=8501):
    p = start
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('localhost', p)) != 0: return p
        except: return p
        p += 1

# ==========================================
# 6. 后台服务线程
# ==========================================
def run_streamlit_thread():
    global STREAMLIT_PORT
    main_py = find_real_path("main.py")
    if not main_py:
        print("ERROR: main.py not found")
        return

    try: from streamlit.web import cli as stcli
    except ImportError: return
    
    threading.Thread(target=_check_streamlit_ready, daemon=True).start()
    
    os.environ["STREAMLIT_SERVER_PORT"] = str(STREAMLIT_PORT)
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none" 
    os.environ["STREAMLIT_THEME_BASE"] = "light"
    os.environ["STREAMLIT_TOOLBAR_MODE"] = "minimal"
    
    sys.argv = [
        "streamlit", "run", main_py, 
        "--server.port", str(STREAMLIT_PORT), 
        "--global.developmentMode=false", 
        "--server.headless=true", 
        "--server.fileWatcherType=none", 
        "--server.runOnSave=false",
        "--client.toolbarMode=minimal"
    ]
    try: stcli.main()
    except SystemExit: pass
    except Exception as e: print(f"Streamlit Error: {e}")

def _check_streamlit_ready():
    start = time.time()
    while not STREAMLIT_READY.is_set():
        if time.time() - start > 60: break
        if STREAMLIT_PORT > 0:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    if s.connect_ex(('localhost', STREAMLIT_PORT)) == 0:
                        STREAMLIT_READY.set()
                        break
            except: pass
        time.sleep(0.5)

def run_http_thread():
    global HTTP_PORT
    if not ASSETS_DIR: return
    import http.server
    import socketserver
    os.chdir(ASSETS_DIR)
    Handler = http.server.SimpleHTTPRequestHandler
    Handler.log_message = lambda *args, **kwargs: None
    try:
        with socketserver.TCPServer(("", HTTP_PORT), Handler) as httpd:
            HTTP_READY.set()
            httpd.serve_forever()
    except: pass

# ==========================================
# 7. 前后端交互 API
# ==========================================
class Api:
    def __init__(self): 
        self._is_maximized = False
        self._is_fullscreen = False
        self._video_ended = False
        self._app_loaded = False
        self._workspace_confirmed = False
        self._restore_rect = None

    def signal_video_ended(self): self._video_ended = True
    def signal_app_loaded(self): self._app_loaded = True
    
    def app_ready_trigger(self):
        self._app_loaded = True
        self.try_fade_to_app()

    def select_folder(self):
        try:
            if not WINDOW_INSTANCE: return None
            dlg_type = getattr(webview, 'FOLDER_DIALOG', 2) 
            result = WINDOW_INSTANCE.create_file_dialog(dlg_type, allow_multiple=False)
            if result and len(result) > 0: return result[0]
        except: pass
        return None
    
    def save_workspace_config(self, path):
        try:
            config_path = get_config_path()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump({"workspace_path": path}, f, ensure_ascii=False)
        except: pass

    def enter_system(self):
        self._workspace_confirmed = True
        
    def change_workspace(self):
        path = self.select_folder()
        if path:
            self.save_workspace_config(path)
            encoded_path = urllib.parse.quote(path)
            new_url = f"http://localhost:{STREAMLIT_PORT}/?workspace={encoded_path}"
            WINDOW_INSTANCE.evaluate_js(f"""
                document.getElementById('loading-overlay').style.display = 'flex';
                document.getElementById('loading-overlay').style.opacity = '1';
                document.getElementById('app-frame').src = '{new_url}';
            """)

    def try_fade_to_app(self):
        if self._video_ended and self._workspace_confirmed: 
            WINDOW_INSTANCE.evaluate_js("""
                const m = document.getElementById('workspace-modal');
                m.style.opacity = 0;
                setTimeout(()=>{ m.style.display='none'; }, 500);
                const s = document.getElementById('splash-container');
                s.style.transition='opacity 0.8s ease-in-out';
                s.style.opacity=0;
                setTimeout(()=>{s.style.visibility='hidden'}, 800);
                const l = document.getElementById('loading-overlay');
                l.style.transition='opacity 0.8s ease-in-out';
                l.style.opacity = 0;
                setTimeout(()=>{ l.style.display='none'; }, 800);
                document.getElementById('app-container').style.opacity=1;
            """)

    def minimize(self):
        if WINDOW_INSTANCE: WINDOW_INSTANCE.minimize()
    
    def _save_restore_rect(self, hwnd):
        if not self._is_maximized and not self._is_fullscreen:
            rect = RECT()
            windll.user32.GetWindowRect(hwnd, byref(rect))
            self._restore_rect = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def _apply_window_rect(self, hwnd, mode):
        if mode == 'restore':
            if self._restore_rect:
                x, y, w, h = self._restore_rect
                windll.user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_NOZORDER)
            else:
                windll.user32.SetWindowPos(hwnd, 0, 100, 100, 1280, 800, SWP_NOZORDER)
            return

        monitor = windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = sizeof(MONITORINFO)
        windll.user32.GetMonitorInfoW(monitor, byref(mi))

        if mode == 'max':
            target_rect = mi.rcWork
        else:
            target_rect = mi.rcMonitor

        w_left = target_rect.left
        w_top = target_rect.top
        w_width = target_rect.right - target_rect.left
        w_height = target_rect.bottom - target_rect.top
        windll.user32.SetWindowPos(hwnd, 0, w_left, w_top, w_width, w_height, SWP_NOZORDER)

    def toggle_maximize(self):
        """最大化/还原切换，并通知前端更新图标"""
        try:
            hwnd = windll.user32.FindWindowW(None, "凡人智能写作系统")
            if not hwnd: return

            if self._is_maximized:
                # 还原
                self._apply_window_rect(hwnd, 'restore')
                self._is_maximized = False
                # 通知前端：改为单方框图标 (false = 不处于最大化)
                if WINDOW_INSTANCE: WINDOW_INSTANCE.evaluate_js("updateMaximizeIcon(false)")
            else:
                # 最大化
                self._save_restore_rect(hwnd)
                self._apply_window_rect(hwnd, 'max')
                self._is_maximized = True
                self._is_fullscreen = False 
                # 通知前端：改为双方框图标 (true = 处于最大化)
                if WINDOW_INSTANCE: WINDOW_INSTANCE.evaluate_js("updateMaximizeIcon(true)")
        except Exception as e:
            if WINDOW_INSTANCE: WINDOW_INSTANCE.maximize()

    def toggle_fullscreen(self):
        try:
            hwnd = windll.user32.FindWindowW(None, "凡人智能写作系统")
            if not hwnd: return

            if self._is_fullscreen:
                self._apply_window_rect(hwnd, 'restore')
                self._is_fullscreen = False
            else:
                self._save_restore_rect(hwnd)
                self._apply_window_rect(hwnd, 'full')
                self._is_fullscreen = True
                self._is_maximized = False
            
            # 全屏切换时，将最大化按钮重置为“最大化”样式（单方框）
            if WINDOW_INSTANCE: WINDOW_INSTANCE.evaluate_js("updateMaximizeIcon(false)")
        except: pass
    
    def close(self):
        if WINDOW_INSTANCE: WINDOW_INSTANCE.destroy()

# ==========================================
# 8. 主程序逻辑
# ==========================================
def master_logic(window, api):
    t_st = threading.Thread(target=run_streamlit_thread, daemon=True)
    t_st.start()
    
    threading.Thread(target=force_window_styles).start()
    
    HTTP_READY.wait(timeout=10)
    
    if HTTP_READY.is_set():
        js_load_video = """
        const v = document.getElementById('splash-video');
        const t = document.getElementById('loading-text-container');
        const c = document.getElementById('splash-container');
        if(v) {
            v.src = '/splash.mp4';
            v.oncanplay = function() {
                setTimeout(() => {
                    t.style.opacity = '1';
                    t.style.letterSpacing = '12px'; 
                    t.style.filter = 'blur(0px)';
                    t.style.transform = 'scale(1)';
                    t.style.animation = 'finalFadeOut 3.0s forwards linear';
                    c.style.animation = 'finalFadeIn 3.0s forwards linear';
                    setTimeout(() => { v.muted = false; v.play().catch(e => { v.muted = true; v.play(); }); }, 50);
                    setTimeout(() => { t.style.display = 'none'; }, 3000);
                }, 2200); 
            };
            v.onerror = function() { setTimeout(() => { t.style.opacity = 0; checkUrlAndShowWorkspace(); pywebview.api.signal_video_ended(); }, 2000); };
        } else { setTimeout(() => { t.style.opacity = 0; checkUrlAndShowWorkspace(); pywebview.api.signal_video_ended(); }, 2000); }
        """
        window.evaluate_js(js_load_video)
    else: 
        window.evaluate_js("setTimeout(() => { checkUrlAndShowWorkspace(); }, 2000);")
        api.signal_video_ended()

if __name__ == '__main__':
    try:
        find_real_path('assets')
        if not ASSETS_DIR: raise FileNotFoundError("ASSETS_DIR not found")
        
        HTTP_PORT = find_free_port(8000)
        STREAMLIT_PORT = find_free_port(8501) 
        
        last_path = load_workspace_config()
        print(f"Loaded Last Workspace: {last_path}")

        html_content = f"""
        <!DOCTYPE html><html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <style>
                @font-face {{ font-family: 'Longyin'; src: url('/Longyin.ttf') format('truetype'); }}
                * {{ margin: 0; padding: 0; box-sizing: border-box; user-select: none; }} 
                body, html {{ width:100%; height:100%; overflow:hidden; background-color:#000000; font-family: 'Longyin', system-ui, sans-serif; }}
                #splash-container {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 9998; opacity: 0; background-color: #000; pointer-events: none; }}
                #loading-text-container {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 10000; background-color: #000; color: #fff; font-size: 6em; display: flex; align-items: center; justify-content: center; opacity: 0; pointer-events: none; animation: fadeInText 2.0s cubic-bezier(0.1, 0, 0, 1) forwards; }}
                @keyframes fadeInText {{ 0% {{ opacity: 0; letter-spacing: 50px; filter: blur(30px); transform: scale(1.05); }} 100% {{ opacity: 1; letter-spacing: 12px; filter: blur(0px); transform: scale(1); }} }}
                @keyframes finalFadeOut {{ from {{ opacity: 1; letter-spacing: 12px; filter: blur(0px); transform: scale(1); }} to {{ opacity: 0; letter-spacing: 12px; filter: blur(5px); transform: scale(1); }} }}
                @keyframes finalFadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
                #splash-video {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
                #workspace-modal {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 10001; background-color: rgba(0, 0, 0, 0.6); display: flex; flex-direction: column; justify-content: center; align-items: center; opacity: 0; pointer-events: none; color: white; backdrop-filter: blur(5px); transition: opacity 0.5s ease; }}
                .ws-content {{ width: 450px; text-align: center; }}
                .ws-title {{ font-size: 2.2em; margin-bottom: 40px; letter-spacing: 4px; color: #eee; }}
                .ws-path-box {{ border: 1px solid #444; padding: 15px; margin-bottom: 30px; font-family: sans-serif; font-size: 14px; color: #aaa; background: rgba(255,255,255,0.05); border-radius: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .ws-btn-group {{ display: flex; gap: 20px; justify-content: center; }}
                .ws-btn {{ padding: 10px 30px; border: 1px solid #666; background: transparent; color: #ccc; font-family: 'Longyin', sans-serif; font-size: 1.3em; cursor: pointer; transition: all 0.3s; border-radius: 4px; }}
                .ws-btn:hover {{ border-color: #fff; color: #fff; background: rgba(255,255,255,0.1); }}
                .ws-btn.primary {{ border-color: #fff; background: #fff; color: #000; }}
                .ws-btn.primary:hover {{ background: #ddd; }}
                #loading-overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 9998; background-color: #000000; display: none; flex-direction: column; justify-content: center; align-items: center; opacity: 0; transition: opacity 0.5s ease; }}
                .spinner {{ width: 50px; height: 50px; border: 4px solid #333; border-top: 4px solid #fff; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 20px; }}
                .loading-text {{ font-family: sans-serif; color: #aaa; font-size: 1.0em; letter-spacing: 1px; }}
                
                #parent-controls {{ position: fixed; top: 0; left: 0; width: 100%; height: 32px; z-index: 99999; opacity: 1; background-color: #f9f9f9; display: flex; justify-content: space-between; align-items: center; pointer-events: none; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
                .titlebar-title {{ padding-left: 12px; font-family: sans-serif; font-size: 14px; color: #333; -webkit-app-region: drag; pointer-events: auto; flex-grow: 1; }}
                .titlebar-buttons {{ pointer-events: auto; display: flex; flex-shrink: 0; }} 
                .titlebar-button {{ display: flex; justify-content: center; align-items: center; width: 46px; height: 32px; cursor: pointer; transition: background-color 0.2s; position: relative; }}
                .titlebar-button:hover {{ background-color: #e5e5e5; }} 
                #close-btn:hover {{ background-color: #e81123; }} #close-btn:hover svg path {{ stroke: #fff; }}
                
                #app-container {{ position: absolute; top: 32px; left: 0; width: 100%; height: calc(100% - 32px); background-color: #000000; z-index: 1; opacity: 0; }}
            </style>
            <script>
                function checkUrlAndShowWorkspace() {{
                    const params = new URLSearchParams(window.location.search);
                    const pathFromUrl = params.get('workspace');
                    const displayBox = document.getElementById('selected-path-text');
                    if (pathFromUrl && pathFromUrl.length > 1 && pathFromUrl !== "null" && pathFromUrl !== "undefined") {{ 
                        displayBox.innerText = pathFromUrl; 
                        handleEnterSystem(); 
                    }} else {{ 
                        if (displayBox.innerText === '' || displayBox.innerText === 'null') displayBox.innerText = '请选择目录'; 
                        showWorkspaceSelector();
                    }}
                }}
                function showWorkspaceSelector() {{ document.getElementById('workspace-modal').style.opacity = "1"; document.getElementById('workspace-modal').style.pointerEvents = "auto"; }}
                function handleSelectFolder() {{ pywebview.api.select_folder().then(function(path) {{ if (path) document.getElementById('selected-path-text').innerText = path; }}); }}
                function handleEnterSystem() {{ 
                    const path = document.getElementById('selected-path-text').innerText;
                    if (!path || path === '请选择目录' || path.length < 2) {{ alert("请先选择一个有效的创作空间目录"); return; }}
                    let targetSrc = 'http://localhost:{STREAMLIT_PORT}/';
                    pywebview.api.save_workspace_config(path); 
                    targetSrc = 'http://localhost:{STREAMLIT_PORT}/?workspace=' + encodeURIComponent(path); 
                    document.getElementById('loading-overlay').style.display = 'flex';
                    document.getElementById('loading-overlay').style.opacity = '1';
                    document.getElementById('app-frame').src = targetSrc;
                    pywebview.api.enter_system(); 
                }}
                function onAppFrameLoad() {{ setTimeout(function() {{ pywebview.api.app_ready_trigger(); }}, 1500); }}
                function onVideoEnded() {{ pywebview.api.signal_video_ended(); checkUrlAndShowWorkspace(); }}
                
                // --- 图标更新逻辑 ---
                function updateMaximizeIcon(isMaximized) {{
                    const btnSvg = document.getElementById('max-restore-svg');
                    if (!btnSvg) return;
                    if (isMaximized) {{
                        // 显示还原图标 (重叠矩形)
                        btnSvg.innerHTML = '<path d="M2.5,2.5 L2.5,9.5 L9.5,9.5 L9.5,2.5 Z M2.5,2.5 L2.5,0.5 L9.5,0.5 L9.5,2.5" fill="none" stroke="transparent" /><path d="M2.1,2.1 h7.8 v7.8 h-7.8 v-7.8 Z M2.1,2.1 v-2 h9 v9 h-2" stroke="#333" fill="none" />';
                    }} else {{
                        // 显示最大化图标 (单矩形)
                        btnSvg.innerHTML = '<rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="#333" stroke-width="1"></rect>';
                    }}
                }}
            </script>
        </head>
        <body>
            <div id="loading-text-container">凡人智能写作系统</div>
            <div id="splash-container"><video id="splash-video" onended="onVideoEnded()"></video></div>
            <div id="workspace-modal">
                <div class="ws-content">
                    <div class="ws-title">请选择创作空间</div>
                    <div class="ws-path-box" id="selected-path-text">{last_path if last_path else ""}</div> 
                    <div class="ws-btn-group"><button class="ws-btn" onclick="handleSelectFolder()">浏览目录</button><button class="ws-btn primary" onclick="handleEnterSystem()">进入系统</button></div>
                </div>
            </div>
            <div id="loading-overlay"><div class="spinner"></div><div class="loading-text">正在初始化系统...</div></div>
            <div id="app-container"><iframe id="app-frame" sandbox="allow-forms allow-scripts allow-same-origin allow-popups allow-downloads allow-modals" style="width:100%;height:100%;border:none;background-color:#000;" onload="onAppFrameLoad()"></iframe></div>
            
            <div id="parent-controls">
                <div class="titlebar-title">凡人智能写作系统</div>
                <div class="titlebar-buttons">
                    <div class="titlebar-button" title="全屏模式" onclick="pywebview.api.toggle_fullscreen()">
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#333" stroke-width="1.5"><path d="M2 5V2h3M14 5V2h-3M2 11v3h3M14 11v3h-3"></path></svg>
                    </div>
                    <div class="titlebar-button" title="切换工作区" onclick="pywebview.api.change_workspace()">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                    </div>
                    <div class="titlebar-button" title="最小化" onclick="pywebview.api.minimize()">
                        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M0,5 L10,5" stroke="#333" stroke-width="1"></path></svg>
                    </div>
                    
                    <div class="titlebar-button" title="最大化/还原" onclick="pywebview.api.toggle_maximize()">
                        <svg id="max-restore-svg" width="10" height="10" viewBox="0 0 10 10">
                            <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="#333" stroke-width="1"></rect>
                        </svg>
                    </div>
                    
                    <div class="titlebar-button" id="close-btn" title="关闭" onclick="pywebview.api.close()">
                        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M0,0 L10,10 M10,0 L0,10" stroke="#333" stroke-width="1.5"></path></svg>
                    </div>
                </div>
            </div>
        </body></html>
        """
        
        index_path = os.path.join(ASSETS_DIR, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        t_http = threading.Thread(target=run_http_thread, daemon=True); t_http.start()
        api = Api()
        
        encoded_path = urllib.parse.quote(last_path) if last_path else ""
        window_url = f'http://localhost:{HTTP_PORT}/index.html?t={int(time.time())}&workspace={encoded_path}'
        
        try: screen = webview.screens[0]; w, h = 1280, 800; x, y = int((screen.width - w) / 2), int((screen.height - h) / 2)
        except: w, h, x, y = 1280, 800, None, None
        
        WINDOW_INSTANCE = webview.create_window("凡人智能写作系统", url=window_url, width=w, height=h, x=x, y=y, frameless=True, js_api=api, background_color='#000000', resizable=True)
        webview.start(master_logic, (WINDOW_INSTANCE, api), gui='edgechromium', debug=False)

    except Exception as e:
        print(f"MAIN CRASH: {e}")
        time.sleep(10)