# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = [('.env.example', '.'), ('assets\\app_icon.ico', 'assets')]
hiddenimports = ['sqlalchemy.sql.default_comparator', 'tiktoken_ext.openai_public', 'PySide6.QtSvg']
datas += collect_data_files('litellm')
hiddenimports += collect_submodules('llm_translate')
hiddenimports += collect_submodules('litellm')
hiddenimports += collect_submodules('tiktoken_ext')


a = Analysis(
    ['llm_translate\\gui\\main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cv2', 'pygame', 'matplotlib', 'matplotlib.backends', 'pandas', 'pytest', 'py', 'IPython', 'jupyter', 'notebook', 'fastapi', 'uvicorn', 'starlette', 'llm_translate.web', 'tkinter', '_tkinter', 'torch', 'cupy', 'dask', 'botocore', 'boto3', 'sagemaker'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LLMTranslate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LLMTranslate',
)
