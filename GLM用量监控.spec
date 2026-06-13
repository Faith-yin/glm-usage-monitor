# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# 显式收集 PIL（Pillow）的全部子模块、数据文件与二进制，避免运行时缺失
datas_pil, binaries_pil, hiddenimports_pil = collect_all('PIL')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries_pil,
    datas=datas_pil,
    hiddenimports=hiddenimports_pil + ['PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont',
                                       'pystray', 'pystray._win32', 'pystray._util',
                                       'requests', 'requests.models', 'requests.adapters',
                                       'urllib3', 'urllib3.util.retry', 'charset_normalizer',
                                       'certifi',
                                       'config', 'api', 'widgets', 'tray'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GLM用量监控',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
