# hooks/hook-streamlit.py
from PyInstaller.utils.hooks import copy_metadata

# 收集 streamlit 的元数据，否则打包后会报 distribution not found 错误
datas = copy_metadata('streamlit')