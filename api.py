"""
api.py — API 查询、数据解析、全局状态
"""

import json
import os
import time
import threading
from datetime import datetime

import requests

from config import (
    API_URL, APP_DIR, DEBUG_FILE, CST,
    load_config, load_cache, save_cache,
)

# ── 全局状态 ────────────────────────────────────────────────
_current_data = {
    "five_hour": {"percentage": 0, "next_reset": "", "reset_datetime": ""},
    "weekly":   {"percentage": 0, "next_reset": "", "reset_datetime": ""},
    "monthly":   {"percentage": 0, "next_reset": "", "reset_datetime": ""},
    "error":     "等待查询",
}

# ── 调试 ─────────────────────────────────────────────────
def _save_debug_text(text, tag="error"):
    try:
        path = os.path.join(APP_DIR, f"debug_{tag}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass

# ── API 查询 ─────────────────────────────────────────────
def fetch_quota(api_key):
    headers = {
        "Authorization": api_key,
        "Accept-Language": "en-US,en",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(API_URL, headers=headers, timeout=10)
        if resp.status_code != 200:
            _save_debug_text(f"HTTP {resp.status_code}: {resp.text[:500]}", "http_error")
            return None
        data = resp.json()
        try:
            with open(DEBUG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return data.get("data", {}).get("limits") or data.get("limits")
    except Exception as e:
        _save_debug_text(f"fetch_quota exception: {type(e).__name__}: {e}", "fetch_error")
        return None

# ── 时间格式化 ──────────────────────────────────────────
def format_reset_time(reset_ts):
    if not reset_ts:
        return ""
    diff_s = int((reset_ts - time.time() * 1000) / 1000)
    if diff_s <= 0:
        return "已重置"
    if diff_s < 3600:
        return f"{diff_s // 60}min 后重置"
    if diff_s < 86400:
        h, m = diff_s // 3600, (diff_s % 3600) // 60
        if m:
            return f"{h}h {m}min 后重置"
        return f"{h}h 后重置"
    d, h = diff_s // 86400, (diff_s % 86400) // 3600
    if h:
        return f"{d}d {h}h 后重置"
    return f"{d}d 后重置"

_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def format_reset_datetime(reset_ts):
    if not reset_ts:
        return ""
    dt = datetime.fromtimestamp(reset_ts / 1000, tz=CST)
    now = datetime.now(CST)
    wd = _WEEKDAY_CN[dt.weekday()]
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime(f"%m-%d {wd} %H:%M")

# ── 数据解析 ────────────────────────────────────────────

# API 返回的 (type, unit) 组合 → 内部 key 的映射
# 基于 https://open.bigmodel.cn/api/monitor/usage/quota/limit 实际返回结构
_QUOTA_TYPE_MAP = {
    ("TOKENS_LIMIT", 3): "five_hour",   # 每5小时额度
    ("TOKENS_LIMIT", 6): "weekly",      # 每周额度
    ("TIME_LIMIT",   5): "monthly",     # MCP 每月额度
}


def parse_limits(limits):
    """
    解析 API 返回的 limits 数组，按 (type, unit) 组合精确匹配到
    five_hour / weekly / monthly，不依赖数组索引顺序。
    """
    empty = {"percentage": 0, "next_reset": "", "reset_datetime": ""}
    result = {
        "five_hour": dict(empty),
        "weekly":   dict(empty),
        "monthly":  dict(empty),
        "error":     "",
    }
    if not limits or not isinstance(limits, list):
        result["error"] = "无数据"
        return result

    for item in limits:
        qtype = item.get("type")
        unit = item.get("unit")
        key = _QUOTA_TYPE_MAP.get((qtype, unit))
        if key:
            pct = round(item.get("percentage", 0))
            ts = item.get("nextResetTime")
            result[key] = {
                "percentage":     pct,
                "next_reset":      format_reset_time(ts),
                "reset_datetime":  format_reset_datetime(ts),
            }

    return result

def pct_color(pct):
    if pct >= 80:
        return "#FF3B30"
    elif pct >= 50:
        return "#FF9500"
    elif pct >= 0:
        return "#34C759"
    return "#34C759"

def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))

# ── 数据刷新 ────────────────────────────────────────────
_refresh_lock = threading.Lock()

def _do_refresh_inner():
    """执行一次数据刷新（线程安全），返回 True 表示刷新成功"""
    global _current_data
    api_key = load_config().get("api_key", "")
    if not api_key:
        with _refresh_lock:
            _current_data["error"] = "未设置 API Key"
        return False

    limits = fetch_quota(api_key)
    with _refresh_lock:
        if limits:
            save_cache(limits)
            _current_data.update(parse_limits(limits))
            _current_data["error"] = ""
            return True
        else:
            cached = load_cache()
            if cached:
                _current_data.update(parse_limits(cached))
                _current_data["error"] = "显示缓存数据"
            else:
                _current_data["error"] = "查询失败，无缓存"
            return False

def get_current_data():
    """返回当前数据的浅拷贝（线程安全）"""
    with _refresh_lock:
        return dict(_current_data)

def do_refresh(icon=None, item=None):
    threading.Thread(target=_do_refresh_inner, daemon=True).start()
