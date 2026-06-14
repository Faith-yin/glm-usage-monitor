"""
config.py — 路径、常量、配置/缓存读写、开机自启、刷新间隔
"""

import ctypes
import winreg
import json
import os
import sys
import time
from datetime import timezone, timedelta

# ── 高 DPI 感知（必须在任何窗口创建前调用）──────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ── 单例检查 ────────────────────────────────────────────────
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "GLM_Usage_Monitor_v8_Tray")
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

# ── 应用目录 ────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA",
        os.path.expanduser("~")), "GLM_Monitor")
    os.makedirs(APP_DIR, exist_ok=True)
    # 迁移旧配置
    _old_dirs = [os.path.dirname(sys.executable),
                 os.path.dirname(os.path.dirname(sys.executable))]
    for _fname in ["config.json", "quota_cache.json"]:
        _new_path = os.path.join(APP_DIR, _fname)
        if not os.path.exists(_new_path):
            for _d in _old_dirs:
                _old_path = os.path.join(_d, _fname)
                if os.path.exists(_old_path):
                    try:
                        import shutil
                        shutil.copy2(_old_path, _new_path)
                    except Exception:
                        pass
                    break
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APP_DIR, "config.json")
CACHE_FILE = os.path.join(APP_DIR, "quota_cache.json")
DEBUG_FILE = os.path.join(APP_DIR, "debug_last_response.json")

API_URL = "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
DEFAULT_REFRESH_INTERVAL = 3600
CACHE_TTL = 300
CST = timezone(timedelta(hours=8))
ICON_SIZE = 64

WM_MOUSEMOVE = 0x0200
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205

# ── 配置读写 ────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if time.time() - data.get("timestamp", 0) < CACHE_TTL:
                    return data.get("limits")
        except Exception:
            pass
    return None

def save_cache(limits):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "limits": limits}, f, ensure_ascii=False)
    except Exception:
        pass

# ── 开机自启（注册表）───────────────────────────────────────
AUTOSTART_KEY_NAME = "GLM用量监控"

def _get_exe_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    else:
        import __main__ as _main
        main_file = getattr(_main, "__file__", os.path.join(APP_DIR, "main.py"))
        return f'"{sys.executable}" "{os.path.abspath(main_file)}"'

def is_autostart_enabled():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, AUTOSTART_KEY_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False

def set_autostart(enabled):
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
        if enabled:
            path = _get_exe_path()
            winreg.SetValueEx(key, AUTOSTART_KEY_NAME, 0, winreg.REG_SZ, path)
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_KEY_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass
    cfg = load_config()
    cfg["autostart"] = enabled
    save_config(cfg)

def toggle_autostart(icon, item):
    new_state = not is_autostart_enabled()
    set_autostart(new_state)
    if icon:
        icon.update_menu()

# ── 刷新间隔配置 ──────────────────────────────────────────────
def get_refresh_interval():
    cfg = load_config()
    return cfg.get("refresh_interval", DEFAULT_REFRESH_INTERVAL)

def set_refresh_interval(seconds):
    cfg = load_config()
    cfg["refresh_interval"] = seconds
    save_config(cfg)

def make_set_interval_callback(seconds):
    def callback(icon, item):
        set_refresh_interval(seconds)
        if icon:
            icon.update_menu()
    return callback

# ── Tooltip 窗口视觉常量 ──────────────────────────────────
_TT_BG       = "#FFFFFF"
_TT_FG       = "#1D1D1F"
_TT_LABEL_FG = "#232326"
_TT_SUB      = "#86868B"
_TT_BORDER   = "#D4D4D4"
_TT_BAR_BG   = "#E5E5EA"
_TT_HINT     = "#aeaeb2"
_TT_SEP      = "#E0E0E0"
_TT_ROW_SEP  = "#E0E0E0"
_TT_SIDE     = 28
_TT_BAR_H    = 9
_TT_BASE_W   = 280
_TT_BASE_H   = 260

_FONT_TITLE = ("Microsoft YaHei UI", 15, "bold")
_FONT_LABEL = ("Microsoft YaHei UI", 12, "normal")
_FONT_PCT   = ("Segoe UI",  13, "bold")
_FONT_TIME  = ("Microsoft YaHei UI", 10, "normal")
_FONT_HINT  = ("Microsoft YaHei UI", 9, "normal")
_FONT_LOAD  = ("Microsoft YaHei UI", 10, "normal")

# ── 公共工具 ────────────────────────────────────────────
def _get_work_area():
    from ctypes import wintypes
    SPI_GETWORKAREA = 48
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0,
        ctypes.byref(rect), 0)
    return rect.right, rect.bottom
