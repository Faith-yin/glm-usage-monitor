"""
GLM Coding Plan 用量监控 — 系统托盘版 v10

模块化架构：
  main.py    — 程序入口
  config.py  — 路径、常量、配置/缓存读写
  api.py     — API 查询、数据解析
  widgets.py — Tooltip 悬停卡片、主详情窗口
  tray.py    — 托盘图标、悬停检测、菜单

启动方式：python main.py
打包方式：pyinstaller --noconfirm GLM用量监控.spec
"""

from tray import start

if __name__ == "__main__":
    start()
