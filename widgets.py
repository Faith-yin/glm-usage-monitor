"""
widgets.py — Tk 后端、Tooltip 悬停卡片、主详情窗口、API Key 设置
"""

import ctypes
import threading
import time
import webbrowser
from datetime import datetime

import tkinter as tk

from config import (
    CST, _get_work_area,
    _TT_BG, _TT_FG, _TT_LABEL_FG, _TT_SUB, _TT_BORDER, _TT_BAR_BG,
    _TT_HINT, _TT_SEP, _TT_ROW_SEP, _TT_SIDE, _TT_BAR_H, _TT_BASE_W, _TT_BASE_H,
    _FONT_TITLE, _FONT_LABEL, _FONT_PCT, _FONT_TIME, _FONT_HINT, _FONT_LOAD,
    load_config, save_config,
)

import api
from api import _do_refresh_inner, pct_color, do_refresh

# ── 统一 Tk 后端（单例）────────────────────────────────────
class TkBackend:
    _instance = None
    _lock     = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._ready = threading.Event()
                cls._instance._root  = None
                threading.Thread(target=cls._instance._run, daemon=True).start()
                cls._instance._ready.wait(timeout=3)
            return cls._instance

    def _run(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.geometry("0x0+0+0")
        self._ready.set()
        self._root.mainloop()

    @property
    def root(self):
        return self._root

    def schedule(self, delay_ms, fn):
        if self._root:
            self._root.after(delay_ms, fn)

def get_tk_backend():
    return TkBackend()

# ── Canvas 工具 ─────────────────────────────────────────
def _rounded_fill(canvas, x1, y1, x2, y2, r, **kw):
    canvas.create_oval(x1, y1, x1 + 2*r, y2, **kw)
    canvas.create_oval(x2 - 2*r, y1, x2, y2, **kw)
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)

def _pill_bar(parent, pct, color, bar_w):
    canvas = tk.Canvas(parent, width=bar_w, height=_TT_BAR_H,
                       bg=_TT_BG, highlightthickness=0)
    _rounded_fill(canvas, 0, 0, bar_w, _TT_BAR_H, _TT_BAR_H // 2,
                  fill=_TT_BAR_BG, outline="")
    if pct > 0:
        fill_w = max(_TT_BAR_H, int(bar_w * min(pct / 100, 1.0)))
        _rounded_fill(canvas, 0, 0, fill_w, _TT_BAR_H, _TT_BAR_H // 2,
                      fill=color, outline="")
    return canvas

# ══ 窗口二：托盘悬停卡片 (TooltipWindow) ══════════════════
class TooltipWindow:
    """Apple 极简卡片：1px 边框 + Canvas 胶囊进度条 + DPI 动态缩放"""

    def __init__(self):
        self._win       = None
        self._lock      = threading.Lock()
        self._outer     = None
        self._actual_w  = _TT_BASE_W
        self._anchor_x  = 0
        self._anchor_y  = 0

    def _safe_destroy(self):
        with self._lock:
            old, self._win, self._outer = self._win, None, None
        if old:
            def _do():
                try: old.destroy()
                except Exception: pass
            try: get_tk_backend().schedule(0, _do)
            except Exception:
                try: old.destroy()
                except Exception: pass

    def is_showing(self):
        with self._lock:
            return bool(self._win and self._win.winfo_exists())

    def close(self):
        self._safe_destroy()

    @staticmethod
    def _add_shadow(win):
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            class ACCENT_POLICY(ctypes.Structure):
                _fields_ = [("AccentState", ctypes.c_int),
                            ("AccentFlags", ctypes.c_int),
                            ("AccentColor", ctypes.c_uint),
                            ("AnimationId", ctypes.c_int)]
            class WINCOMP_ATTR_DATA(ctypes.Structure):
                _fields_ = [("Attribute", ctypes.c_int),
                            ("Data", ctypes.POINTER(ACCENT_POLICY)),
                            ("SizeOfData", ctypes.c_uint)]
            accent = ACCENT_POLICY()
            accent.AccentState = 3
            accent.AccentFlags = 2
            data = WINCOMP_ATTR_DATA()
            data.Attribute = 19
            data.Data = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        except Exception:
            pass

    @staticmethod
    def _set_rounded(win):
        """为窗口设置圆角（DWM API，Windows 11 原生支持）"""
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(ctypes.c_int(DWMWCP_ROUND)),
                ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass

    def _calc_pos(self, anchor_x, anchor_y, win_w, win_h):
        sw, sh = _get_work_area()
        tx = anchor_x - (win_w // 2)
        if tx < 10:
            tx = 10
        elif tx + win_w > sw - 10:
            tx = sw - win_w - 10

        # Tooltip 始终显示在鼠标/图标上方，避免覆盖图标导致无法拖拽
        # （尤其当图标在任务栏折叠区域时，Tooltip 不能挡住图标）
        ty = anchor_y - win_h - 50
        if ty < 10:
            # 鼠标太靠近屏幕顶部，兜底显示在工作区底部
            ty = sh - win_h - 8

        return tx, ty

    def _ensure_window(self, anchor_x, anchor_y):
        """创建或复用 tooltip 窗口（仅设置宽度，高度由内容动态决定）"""
        with self._lock:
            if self._win and self._win.winfo_exists():
                # 窗口已存在时复用，不更新锚点（避免鼠标微移导致位置跳变）
                return self._win, self._outer
            # 仅在首次创建窗口时记录锚点并冻结
            self._anchor_x = anchor_x
            self._anchor_y = anchor_y
            bk = get_tk_backend()
            win = tk.Toplevel(bk.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=_TT_BORDER)

            win.geometry("1x1")
            win.update_idletasks()
            scale = win.winfo_fpixels('1i') / 96.0
            self._actual_w = int(_TT_BASE_W * scale)
            W = self._actual_w

            # 先用最小高度创建窗口，后续由 _fit_to_content 调整
            tx, ty = self._calc_pos(anchor_x, anchor_y, W, 100)
            win.geometry(f"{W}x{100}+{tx}+{ty}")
            win.resizable(False, False)
            win.update_idletasks()

            TooltipWindow._set_rounded(win)

            border_frame = tk.Frame(win, bg=_TT_BORDER, width=W)
            border_frame.pack(fill="both", expand=True)

            outer = tk.Frame(border_frame, bg=_TT_BG, width=W - 2)
            outer.pack(padx=1, pady=1)

            win.lift(); win.update_idletasks()
            TooltipWindow._add_shadow(win)
            win.attributes("-alpha", 0.0)
            def _fade_in(a=0.0):
                if not win.winfo_exists(): return
                a = min(a + 0.15, 1.0)
                win.attributes("-alpha", a)
                if a < 1.0: win.after(16, lambda: _fade_in(a))
            win.after(10, _fade_in)
            self._win, self._outer = win, outer
            return win, outer

    def _fit_to_content(self, win, outer):
        """
        内容填充完毕后调用：根据实际内容动态调整窗口尺寸并重新定位。
        解决不同 DPI / 分辨率下固定高度不够用的问题。
        """
        if not win or not win.winfo_exists():
            return
        # 让 Tk 计算所有子组件的自然尺寸
        win.update_idletasks()
        # outer 的请求高度即为内容实际需要的高度（含 padding）
        content_h = outer.winfo_reqheight()
        # 加上 border_frame 的 padx=1 + pady=1 各两边
        total_h = content_h + 2
        W = self._actual_w
        # 重新定位（锚点可能已变化）
        tx, ty = self._calc_pos(self._anchor_x, self._anchor_y, W, total_h)
        win.geometry(f"{W}x{total_h}+{tx}+{ty}")

    def show_loading(self, anchor_x, anchor_y):
        def _build():
            win, outer = self._ensure_window(anchor_x, anchor_y)
            if not win: return
            for w in outer.winfo_children(): w.destroy()

            # 标题行
            tk.Label(outer, text="GLM Coding Plan", bg=_TT_BG, fg=_TT_FG,
                     font=_FONT_TITLE, anchor="w").pack(
                     fill="x", padx=_TT_SIDE, pady=(24, 8))
            ls = tk.Frame(outer, bg=_TT_SEP, height=1)
            ls.pack(fill="x", padx=_TT_SIDE, pady=(0, 8))
            ls.pack_propagate(False)

            # 骨架屏：三行占位，与最终数据高度一致，避免加载完成后窗口跳动
            _skeleton_labels = ["每5小时", "每周", "MCP每月"]
            for idx, label in enumerate(_skeleton_labels):
                row = tk.Frame(outer, bg=_TT_BG)
                row.pack(fill="x", padx=_TT_SIDE,
                         pady=(0 if idx == 0 else 8, 0))

                top = tk.Frame(row, bg=_TT_BG)
                top.pack(fill="x")
                tk.Label(top, text=label, bg=_TT_BG, fg=_TT_LABEL_FG,
                         font=_FONT_LABEL, anchor="w").pack(side="left")
                # 占位百分比（浅色表示加载中）
                tk.Label(top, text="\u2026", bg=_TT_BG, fg=_TT_HINT,
                         font=_FONT_PCT).pack(side="right")

                bar_w = self._actual_w - 2 - 2 * _TT_SIDE
                bar = _pill_bar(row, 0, "#E5E5EA", bar_w)
                bar.pack(fill="x", pady=(5, 3))

                tk.Label(row, text="查询中\u2026", bg=_TT_BG, fg=_TT_SUB,
                         font=_FONT_TIME, anchor="w").pack(fill="x", pady=(2, 0))

                if idx < len(_skeleton_labels) - 1:
                    sep = tk.Frame(outer, bg=_TT_ROW_SEP, height=1)
                    sep.pack(fill="x", padx=_TT_SIDE, pady=(14, 0))
                    sep.pack_propagate(False)

            # 底部内边距（与 show_data 一致）
            tk.Frame(outer, bg=_TT_BG, height=20).pack(fill="x")

            self._fit_to_content(win, outer)
        get_tk_backend().schedule(0, _build)

    def show_data(self, data, anchor_x, anchor_y):
        def _build():
            win, outer = self._ensure_window(anchor_x, anchor_y)
            if not win: return
            for w in outer.winfo_children(): w.destroy()

            # 标题行：左侧标题 + 右侧更新时间
            title_row = tk.Frame(outer, bg=_TT_BG)
            title_row.pack(fill="x", padx=_TT_SIDE, pady=(24, 8))
            tk.Label(title_row, text="GLM Coding Plan", bg=_TT_BG, fg=_TT_FG,
                     font=_FONT_TITLE, anchor="w").pack(side="left")
            tk.Label(title_row, text=datetime.now(CST).strftime("%H:%M 更新"),
                     bg=_TT_BG, fg=_TT_HINT, font=_FONT_HINT, anchor="e").pack(side="right")

            # 第一条分割线
            sep1 = tk.Frame(outer, bg=_TT_SEP, height=1)
            sep1.pack(fill="x", padx=_TT_SIDE, pady=(0, 10))
            sep1.pack_propagate(False)

            rows = [
                ("每5小时", data.get("five_hour", {})),
                ("每周",    data.get("weekly",   {})),
                ("MCP每月", data.get("monthly",   {})),
            ]
            for idx, (label, d) in enumerate(rows):
                pct      = d.get("percentage", 0) if isinstance(d, dict) else 0
                reset_dt = d.get("reset_datetime", "") if isinstance(d, dict) else ""
                reset_s  = d.get("next_reset", "") if isinstance(d, dict) else ""
                color    = pct_color(pct)

                row = tk.Frame(outer, bg=_TT_BG)
                row.pack(fill="x", padx=_TT_SIDE,
                         pady=(0 if idx == 0 else 8, 0))

                top = tk.Frame(row, bg=_TT_BG)
                top.pack(fill="x")
                tk.Label(top, text=label, bg=_TT_BG, fg=_TT_LABEL_FG,
                         font=_FONT_LABEL, anchor="w").pack(side="left")
                tk.Label(top, text=f"{pct}%", bg=_TT_BG, fg=_TT_FG,
                         font=_FONT_PCT).pack(side="right")

                bar_w = self._actual_w - 2 - 2 * _TT_SIDE
                bar = _pill_bar(row, pct, color, bar_w)
                bar.pack(fill="x", pady=(5, 3))

                if reset_s and reset_dt:
                    text = f"{reset_s}（{reset_dt}）"
                elif reset_s:
                    text = reset_s
                elif reset_dt:
                    text = reset_dt
                else:
                    text = "\u2014"
                tk.Label(row, text=text, bg=_TT_BG, fg=_TT_SUB,
                         font=_FONT_TIME, anchor="w").pack(fill="x", pady=(2, 0))

                if idx < len(rows) - 1:
                    sep = tk.Frame(outer, bg=_TT_ROW_SEP, height=1)
                    sep.pack(fill="x", padx=_TT_SIDE, pady=(14, 0))
                    sep.pack_propagate(False)

            err = data.get("error", "")
            if err:
                tk.Label(outer, text=err, bg=_TT_BG, fg="#e24b4a",
                         font=_FONT_HINT, anchor="e").pack(
                         fill="x", padx=_TT_SIDE, pady=(0, 14))

            # 底部内边距
            tk.Frame(outer, bg=_TT_BG, height=20).pack(fill="x")

            self._fit_to_content(win, outer)
        get_tk_backend().schedule(0, _build)


# ── 窗口一：主常驻界面 (main_win) ────────────────────────
def _open_detail_window(data):
    backend = get_tk_backend()

    def _build_content(main_content, data):
        for w in main_content.winfo_children():
            w.destroy()
        inner = tk.Frame(main_content, bg="#FFFFFF")
        inner.pack(fill="both", expand=True, padx=20, pady=28)

        rows = [
            ("每5小时额度", data.get("five_hour", {})),
            ("每周额度",     data.get("weekly",   {})),
            ("MCP每月额度",  data.get("monthly",   {})),
        ]
        for label, d in rows:
            pct = d.get("percentage", 0) if isinstance(d, dict) else 0
            c   = pct_color(pct)
            reset     = d.get("next_reset", "") if isinstance(d, dict) else ""
            reset_dt  = d.get("reset_datetime", "") if isinstance(d, dict) else ""

            tk.Label(
                inner, text=f"{label}：{pct}%",
                font=("Microsoft YaHei UI", 11, "bold"), fg=_TT_FG,
                bg="#FFFFFF", anchor="w",
            ).pack(fill="x", pady=(14, 0))

            bar_bg = tk.Frame(inner, bg=_TT_BAR_BG, height=8)
            bar_bg.pack(fill="x", pady=(8, 4))
            if pct > 0:
                fill = tk.Frame(bar_bg, bg=c, height=8)
                fill.place(relx=0, rely=0, relwidth=min(pct / 100, 1.0), relheight=1.0)

            t = f"{reset_dt}  ·  {reset}".strip(" ·") if (reset_dt or reset) else "—"
            tk.Label(
                inner, text=t,
                font=("Microsoft YaHei UI", 9), fg=_TT_SUB,
                bg="#FFFFFF", anchor="w",
            ).pack(fill="x", pady=(2, 12))

        main_content.update_idletasks()

    def _show_loading(main_content):
        for w in main_content.winfo_children():
            w.destroy()
        tk.Label(
            main_content, text="正在查询用量…",
            font=("Microsoft YaHei UI", 12), fg=_TT_SUB,
            bg="#FFFFFF", anchor="center",
        ).pack(expand=True)
        main_content.update_idletasks()

    def _build():
        main_win = tk.Toplevel(backend.root)
        main_win.title("GLM Coding Plan 用量详情")

        # 宽度固定，高度由内容动态决定（先创建再调整）
        WIN_W = 600
        main_win.geometry(f"{WIN_W}x{1}")
        main_win.resizable(False, False)

        sw, sh = _get_work_area()
        x = max(0, (sw - WIN_W) // 2)
        y = max(0, (sh - 500) // 2)  # 初始预估高度用于居中
        main_win.geometry(f"{WIN_W}x{1}+{x}+{y}")

        main_content = tk.Frame(main_win, bg="#FFFFFF")
        main_content.pack(fill="both", expand=True, padx=16, pady=12)

        _build_content(main_content, data)

        btn_f = tk.Frame(main_win, bg="#FFFFFF", pady=16)
        btn_f.pack(fill="x")

        refresh_btn = tk.Button(
            btn_f, text="刷新数据",
            font=("Microsoft YaHei UI", 10), bg="#4CAF50", fg="white",
            padx=16, relief="flat",
        )
        refresh_btn.pack(side="left", padx=20)

        def on_refresh():
            refresh_btn.config(text="加载中…", state="disabled")
            _show_loading(main_content)

            def _run():
                _do_refresh_inner()
                def _update_ui():
                    _build_content(main_content, api._current_data)
                    refresh_btn.config(text="刷新数据", state="normal")
                    # 刷新后重新适配窗口高度
                    main_win.update_idletasks()
                    content_h = main_win.winfo_reqheight()
                    y = max(0, (sh - content_h) // 2)
                    main_win.geometry(f"{WIN_W}x{content_h}+{x}+{y}")
                backend.schedule(0, _update_ui)

            threading.Thread(target=_run, daemon=True).start()

        refresh_btn.config(command=on_refresh)

        tk.Button(
            btn_f, text="关闭", command=main_win.destroy,
            font=("Microsoft YaHei UI", 10), padx=16, relief="flat",
        ).pack(side="right", padx=20)

        # 内容全部构建完毕后，根据实际内容动态调整窗口高度并重新居中
        main_win.update_idletasks()
        content_h = main_win.winfo_reqheight()
        y = max(0, (sh - content_h) // 2)
        main_win.geometry(f"{WIN_W}x{content_h}+{x}+{y}")

        main_win.protocol("WM_DELETE_WINDOW", main_win.destroy)

    backend.schedule(0, _build)

def show_detail(icon=None, item=None):
    _open_detail_window(api._current_data)

# ── API Key 设置弹窗 ────────────────────────────────────────
def _open_key_dialog():
    backend = get_tk_backend()

    def _build():
        win = tk.Toplevel(backend.root)
        win.title("设置 API Key")
        win.resizable(False, False)

        # DPI 自适应尺寸
        win.update_idletasks()
        scale = win.winfo_fpixels('1i') / 96.0
        W, H = int(440 * scale), int(200 * scale)
        win.geometry(f"{W}x{H}")

        sw, sh = _get_work_area()
        win.geometry(f"+{max(0, (sw - W) // 2)}+{max(0, (sh - H) // 2)}")

        pady_title = int(16 * scale)
        pady_entry = int(10 * scale)
        pady_btn = int(6 * scale)

        tk.Label(win, text="请输入智谱 AI 的 API Key",
                 font=("Segoe UI", 11), fg="#333").pack(pady=(pady_title, 0))
        link_url = "https://open.bigmodel.cn/apikey/platform"
        link_row = tk.Frame(win)
        link_row.pack(pady=(3, 0))
        tk.Label(link_row, text="获取地址：",
                 font=("Segoe UI", 9), fg="#888").pack(side="left")
        link_lbl = tk.Label(link_row, text=link_url,
                            font=("Segoe UI", 9, "underline"), fg="#1a73e8",
                            cursor="hand2")
        link_lbl.pack(side="left")
        link_lbl.bind("<Button-1>", lambda e: webbrowser.open(link_url))

        entry = tk.Entry(win, width=46, font=("Segoe UI", 10), show="*")
        entry.pack(pady=pady_entry)
        # 回填已保存的 API Key
        existing_key = load_config().get("api_key", "")
        if existing_key:
            entry.insert(0, existing_key)
        entry.focus_set()
        entry.select_range(0, "end")  # 全选，方便覆盖

        result = {"key": None}

        def on_ok():
            val = entry.get().strip()
            if val:
                result["key"] = val
            win.destroy()

        def on_cancel():
            win.destroy()

        bf = tk.Frame(win)
        bf.pack(pady=pady_btn)
        tk.Button(bf, text="确定", command=on_ok, width=8,
                  font=("Segoe UI", 10), bg="#4CAF50", fg="white",
                  relief="flat").pack(side="left", padx=10)
        tk.Button(bf, text="取消", command=on_cancel, width=8,
                  font=("Segoe UI", 10), relief="flat").pack(side="left", padx=10)

        entry.bind("<Return>", lambda e: on_ok())
        win.protocol("WM_DELETE_WINDOW", on_cancel)

        def _after_close():
            if result["key"]:
                cfg = load_config()
                cfg["api_key"] = result["key"]
                save_config(cfg)
                do_refresh()
        win.after(100, _after_close)

    backend.schedule(0, _build)

def set_api_key(icon=None, item=None):
    _open_key_dialog()
