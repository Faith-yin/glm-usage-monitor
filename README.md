# GLM Usage Monitor

[English](README_EN.md) | 中文

轻量级 Windows 系统托盘工具，实时监控 [智谱 AI](https://open.bigmodel.cn) GLM Coding Plan 的用量配额，悬停即查、一目了然。

![主窗口](images/主窗口.png) 
![悬浮窗口](images/悬浮窗口.png)

## 功能特性

- **悬停即查** — 鼠标悬停托盘图标，弹出极简卡片显示三项额度（5 小时 / 每周 / MCP 每月）
- **颜色指示** — 托盘图标实时显示 5 小时额度百分比，绿 / 橙 / 红三色直观反映用量
- **重置倒计时** — 每项额度附带重置时间，提前规划使用节奏
- **自动刷新** — 支持 1 分钟~2 小时可配置刷新间隔，后台静默更新
- **缓存兜底** — 网络异常时自动展示最近一次缓存数据
- **开机自启** — 一键开启 / 关闭，通过注册表实现
- **详情窗口** — 左键双击托盘图标打开详情面板，手动刷新
- **单实例运行** — 互斥锁防止重复启动

## 安装

### 方式一：直接下载（推荐）

前往 [Releases](../../releases) 下载最新版 `GLM用量监控.exe`，双击运行即可。

### 方式二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/你的用户名/glm-usage-monitor.git
cd glm-usage-monitor

# 安装依赖
pip install -r requirements.txt

# 复制配置模板并填入 API Key
cp config.example.json config.json
# 编辑 config.json，填入你的智谱 API Key

# 启动
python main.py
```

## 快速开始

1. 启动后右键托盘图标 → **设置 API Key**
2. 在 [智谱开放平台](https://open.bigmodel.cn/usercenter/apikeys) 获取 API Key 并粘贴
3. 鼠标悬停托盘图标即可查看用量

## 使用说明

| 操作 | 效果 |
|------|------|
| 悬停托盘图标 | 弹出悬浮卡片，显示三项额度 |
| 左键双击托盘图标 | 打开详情窗口 |
| 右键托盘图标 | 打开菜单（刷新 / 自启 / 间隔 / API Key / 退出） |

### 配置文件

首次运行会在程序目录生成 `config.json`：

```json
{
  "api_key": "你的智谱 API Key",
  "refresh_interval": 3600,
  "autostart": true
}
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `api_key` | 智谱 AI API Key | — |
| `refresh_interval` | 自动刷新间隔（秒） | 3600（1 小时） |
| `autostart` | 是否开机自启 | false |

## 项目结构

```
glm-usage-monitor/
├── main.py              # 程序入口
├── config.py            # 路径、常量、配置/缓存读写、开机自启
├── api.py               # API 查询、数据解析、全局状态
├── widgets.py           # 悬浮卡片、详情窗口、API Key 设置弹窗
├── tray.py              # 托盘图标、悬停检测、自动刷新、菜单
├── config.example.json  # 配置模板
├── requirements.txt     # Python 依赖
├── GLM用量监控.spec     # PyInstaller 打包配置
├── 启动.bat             # 打包后快捷启动脚本
├── images/              # 截图
└── LICENSE              # MIT 许可证
```

## 技术栈

- **Python 3** + Tkinter（UI）
- [pystray](https://github.com/moses-palmer/pystray)（系统托盘）
- [Pillow](https://python-pillow.org/)（图标绘制）
- [requests](https://docs.python-requests.org/)（API 请求）
- [PyInstaller](https://pyinstaller.org/)（打包为 exe）

## 打包

```bash
pyinstaller --noconfirm GLM用量监控.spec
```

产物位于 `dist/GLM用量监控.exe`。

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'Add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

## 许可证

[MIT License](LICENSE)

## 致谢

- 数据来源：[智谱 AI 开放平台](https://open.bigmodel.cn)
