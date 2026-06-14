"""
tray.py — 托盘图标、鼠标悬停检测、自动刷新、菜单、启动入口
"""

import ctypes
import threading
import time
import sys

import pystray
from PIL import Image, ImageDraw, ImageFont

from config import (
    ICON_SIZE, CST,
    get_refresh_interval,
    is_autostart_enabled, toggle_autostart,
    make_set_interval_callback,
    load_config, save_config, load_cache,
)

from api import (
    parse_limits, pct_color, hex_to_rgb,
    _do_refresh_inner, do_refresh,
)

from widgets import TooltipWindow, get_tk_backend, show_detail, set_api_key

# 全局实例
_tray_icon = None

# ── 托盘图标绘制 ──────────────────────────────────────────
def _get_font(size, bold=False):
    candidates = []
    if bold:
        candidates.append("C:/Windows/Fonts/segoeuib.ttf")
    candidates.extend([
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ])
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

def make_tray_icon(data):
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pct   = data.get("five_hour", {}).get("percentage", 0)
    color = hex_to_rgb(pct_color(pct))
    draw.ellipse([2, 2, ICON_SIZE - 2, ICON_SIZE - 2], fill=color + (230,))
    text = f"{pct}%"
    font = _get_font(18)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((ICON_SIZE - tw) // 2, (ICON_SIZE - th) // 2 - 1),
        text, fill=(255, 255, 255, 255), font=font
    )
    return img

def make_error_icon():
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, ICON_SIZE - 2, ICON_SIZE - 2], fill=(100, 100, 100, 200))
    font = _get_font(26)
    bbox = draw.textbbox((0, 0), "?", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((ICON_SIZE - tw) // 2, (ICON_SIZE - th) // 2 - 1),
        "?", fill=(255, 255, 255, 255), font=font
    )
    return img

def _update_icon():
    global _tray_icon
    if not _tray_icon:
        return
    import api as _api
    data = _api._current_data
    has_data = any(
        data.get(k, {}).get("percentage", 0) > 0
        for k in ["five_hour", "weekly", "monthly"]
    )
    img = make_tray_icon(data) if has_data else make_error_icon()
    _tray_icon.icon = img
    _tray_icon.title = ""

# ── 悬停检测 ─────────────────────────────────────────────────
_tooltip_win = TooltipWindow()

try:
    from pystray import _win32 as _pystray_win
    from ctypes import wintypes

    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONUP = 0x0202
    WM_RBUTTONUP = 0x0205

    class HoverIcon(_pystray_win.Icon):
        HOVER_ENTER_DEBOUNCE = 0.05
        LEAVE_CHECK_INTERVAL = 0.15

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._state = "IDLE"
            self._hover_lock = threading.Lock()
            self._enter_timer = None
            self._leave_timer = None
            self._fetch_thread = None
            self._anchor_x = 0
            self._anchor_y = 0
            self._menu_visible = False

        def _on_notify(self, wparam, lparam):
            if lparam == WM_MOUSEMOVE:
                with self._hover_lock:
                    if self._menu_visible:
                        return
                    if self._state == "HOVERING":
                        self._reset_leave_timer()
                        # 跟随鼠标位置更新锚点，避免在图标按钮区域内移动时误判离开
                        pt = wintypes.POINT()
                        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                        self._anchor_x = pt.x
                        self._anchor_y = pt.y
                    elif self._state == "IDLE":
                        self._cancel_leave_timer()
                        if self._enter_timer:
                            self._enter_timer.cancel()
                        self._state = "ENTERING"
                        self._enter_timer = threading.Timer(
                            self.HOVER_ENTER_DEBOUNCE, self._trigger_enter)
                        self._enter_timer.start()
            else:
                with self._hover_lock:
                    self._cancel_enter_timer()
                    self._cancel_leave_timer()
                    if self._state != "IDLE":
                        self._state = "IDLE"
                        _tooltip_win.close()
                # TrackPopupMenu 是同步阻塞的，前后设置标记防止 timer/fetch 线程在此期间弹出 tooltip
                if lparam in (WM_RBUTTONUP,):
                    self._menu_visible = True
                super()._on_notify(wparam, lparam)
                if lparam in (WM_RBUTTONUP,):
                    self._menu_visible = False

        def _cancel_enter_timer(self):
            if self._enter_timer:
                self._enter_timer.cancel()
                self._enter_timer = None

        def _cancel_leave_timer(self):
            if self._leave_timer:
                self._leave_timer.cancel()
                self._leave_timer = None

        def _reset_leave_timer(self):
            self._cancel_leave_timer()
            self._leave_timer = threading.Timer(
                self.LEAVE_CHECK_INTERVAL, self._trigger_leave)
            self._leave_timer.start()

        def _trigger_enter(self):
            with self._hover_lock:
                self._enter_timer = None
                if self._state != "ENTERING":
                    return
                if self._menu_visible:
                    self._state = "IDLE"
                    return
                self._state = "HOVERING"
                pt = wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                self._anchor_x = pt.x
                self._anchor_y = pt.y
                self._reset_leave_timer()

            _tooltip_win.show_loading(self._anchor_x, self._anchor_y)

            def _fetch():
                # 复用 _do_refresh_inner（线程安全），不再手动 fetch/parse
                import api as _api
                _api._do_refresh_inner()

                # 等待 tooltip 窗口就绪
                for _ in range(10):
                    if _tooltip_win.is_showing():
                        break
                    time.sleep(0.1)

                import api as _api
                if _tooltip_win.is_showing():
                    if self._menu_visible:
                        _tooltip_win.close()
                    else:
                        _tooltip_win.show_data(_api._current_data, self._anchor_x, self._anchor_y)

                # 更新托盘图标
                _update_icon()

            if not self._fetch_thread or not self._fetch_thread.is_alive():
                self._fetch_thread = threading.Thread(target=_fetch, daemon=True)
                self._fetch_thread.start()

        def _trigger_leave(self):
            with self._hover_lock:
                self._leave_timer = None
                if self._state != "HOVERING":
                    return
                pt = wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                near_icon = (abs(pt.x - self._anchor_x) < 30 and
                             abs(pt.y - self._anchor_y) < 30)
                if near_icon:
                    self._reset_leave_timer()
                    return
                self._state = "IDLE"
            _tooltip_win.close()

    _IconClass = HoverIcon

except Exception:
    _IconClass = pystray.Icon

# ── 后台自动刷新 ────────────────────────────────────────────
def _auto_refresh():
    while True:
        interval = get_refresh_interval()
        time.sleep(interval)
        try:
            _do_refresh_inner()
        except Exception:
            pass

# ── 退出 ────────────────────────────────────────────────────
def quit_app(icon=None, item=None):
    _tooltip_win.close()
    if icon:
        icon.stop()
    sys.exit(0)

# ── 启动 ────────────────────────────────────────────────────
def start():
    global _tray_icon
    get_tk_backend()

    cached = load_cache()
    if cached:
        import api as _api
        _api._current_data.clear()
        _api._current_data.update(parse_limits(cached))

    menu = pystray.Menu(
        pystray.MenuItem("查看详情", show_detail, default=True),
        pystray.MenuItem("刷新数据", do_refresh),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "开机自启",
            toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
        ),
        pystray.MenuItem("刷新间隔", pystray.Menu(
            pystray.MenuItem(
                "1 分钟", make_set_interval_callback(60),
                checked=lambda item: get_refresh_interval() == 60, radio=True),
            pystray.MenuItem(
                "5 分钟", make_set_interval_callback(300),
                checked=lambda item: get_refresh_interval() == 300, radio=True),
            pystray.MenuItem(
                "10 分钟", make_set_interval_callback(600),
                checked=lambda item: get_refresh_interval() == 600, radio=True),
            pystray.MenuItem(
                "30 分钟", make_set_interval_callback(1800),
                checked=lambda item: get_refresh_interval() == 1800, radio=True),
            pystray.MenuItem(
                "1 小时", make_set_interval_callback(3600),
                checked=lambda item: get_refresh_interval() == 3600, radio=True),
            pystray.MenuItem(
                "2 小时", make_set_interval_callback(7200),
                checked=lambda item: get_refresh_interval() == 7200, radio=True),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("设置 API Key", set_api_key),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", quit_app),
    )

    init_img = make_error_icon()
    _tray_icon = _IconClass(
        name="glm_monitor",
        icon=init_img,
        title="",
        menu=menu,
    )

    threading.Thread(target=_auto_refresh, daemon=True).start()
    threading.Thread(target=_do_refresh_inner, daemon=True).start()
    _tray_icon.run()
