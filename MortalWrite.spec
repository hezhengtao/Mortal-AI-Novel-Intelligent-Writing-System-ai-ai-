# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata
import sys
import os

block_cipher = None

# =========================================================
# 1. 智能路径检测
# =========================================================
# 获取当前 spec 文件所在的目录作为项目根目录
project_root = os.path.abspath(os.getcwd())

# 假设源码在 'mortal_write' 文件夹下
source_root = os.path.join(project_root, 'mortal_write')

# 尝试定位入口文件 run.py
script_path = os.path.join(source_root, 'run.py')
if not os.path.exists(script_path):
    # 如果找不到，尝试项目根目录下的 run.py
    script_path = os.path.join(project_root, 'run.py')
    source_root = project_root # 如果入口在根目录，源码根目录也调整为根目录

# 打印路径供调试
print(f"Project Root: {project_root}")
print(f"Source Root: {source_root}")
print(f"Entry Script: {script_path}")

# =========================================================
# 2. 资源配置
# =========================================================

# 定位 pay 文件夹 (假设在 assets/pay 下)
# 如果你的 pay 文件夹在其他位置，请修改这里
pay_folder = os.path.join(source_root, 'assets', 'pay')

# 构建 datas 列表
my_datas = [
    (os.path.join(source_root, 'main.py'), 'mortal_write'),
    (os.path.join(source_root, 'database.py'), 'mortal_write'),
    (os.path.join(source_root, 'config.py'), 'mortal_write'),
    (os.path.join(source_root, 'logic.py'), 'mortal_write'),
    (os.path.join(source_root, 'utils.py'), 'mortal_write'),
    (os.path.join(source_root, 'views'), 'mortal_write/views'),
    (os.path.join(source_root, 'assets'), 'mortal_write/assets'),
    
    # 将 pay 文件夹映射到 EXE 内部的根目录 'pay'
    # 这样在 donate.py 中就可以通过 os.path.join(sys._MEIPASS, 'pay', 'ali.png') 访问
    (pay_folder, 'pay'), 
]

# =========================================================
# 3. 依赖与隐式导入
# =========================================================
metadata_packages = [
    'streamlit', 'tqdm', 'regex', 'requests', 'packaging', 
    'filelock', 'numpy', 'altair'
]
for pkg in metadata_packages:
    try: 
        my_datas += copy_metadata(pkg)
    except Exception as e: 
        print(f"Warning: Could not copy metadata for {pkg}: {e}")

my_hiddenimports = [
    'streamlit', 'streamlit.web.cli', 'webview', 'PIL', 'PIL.ImageTk', 
    'sqlite3', 'pandas', 'plotly', 'pyvis', 'engineio.async_drivers.threading',
    'ntplib', 'openai'
]

st_hiddenimports = collect_submodules('streamlit')
st_datas = collect_data_files('streamlit')
my_datas += st_datas
my_hiddenimports += st_hiddenimports

# =========================================================
# 4. 分析与打包
# =========================================================
a = Analysis(
    [script_path],
    pathex=[project_root],
    binaries=[],
    datas=my_datas,
    hiddenimports=my_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MortalWrite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # 设置为 True 可以看到报错信息，发布时设为 False
    icon=os.path.join(source_root, 'assets', 'app.ico') if os.path.exists(os.path.join(source_root, 'assets', 'app.ico')) else None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MortalWrite'
)