"""
dev.py — 开发模式启动器：监听源码变更，自动重启
使用方式：python dev.py
"""
import os
import sys
import time
import subprocess

WATCH_EXT = {".py"}
WATCH_DIR = os.path.dirname(os.path.abspath(__file__))
POLL_INTERVAL = 1.0  # 秒


def get_mtimes():
    """收集所有 .py 文件的修改时间"""
    mtimes = {}
    for root, _, files in os.walk(WATCH_DIR):
        # 跳过非源码目录
        if ".git" in root or "__pycache__" in root or "build" in root or "dist" in root:
            continue
        for f in files:
            if os.path.splitext(f)[1] in WATCH_EXT:
                path = os.path.join(root, f)
                try:
                    mtimes[path] = os.path.getmtime(path)
                except OSError:
                    pass
    return mtimes


def main():
    print("[dev] 启动 GLM Usage Monitor（开发模式）")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(WATCH_DIR, "main.py")],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    last_mtimes = get_mtimes()

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            if proc.poll() is not None:
                # 进程已退出
                print(f"[dev] 进程退出 (code={proc.returncode})，等待文件变更后重启...")
                proc = None
                while True:
                    time.sleep(POLL_INTERVAL)
                    new_mtimes = get_mtimes()
                    if new_mtimes != last_mtimes:
                        last_mtimes = new_mtimes
                        proc = subprocess.Popen(
                            [sys.executable, os.path.join(WATCH_DIR, "main.py")],
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        )
                        print("[dev] 已重启")
                        break
                continue

            new_mtimes = get_mtimes()
            if new_mtimes != last_mtimes:
                changed = set(new_mtimes.keys()) - set(last_mtimes.keys()) | {
                    p for p, t in new_mtimes.items()
                    if p in last_mtimes and last_mtimes[p] != t
                }
                for p in sorted(changed)[:3]:
                    print(f"[dev] 检测到变更: {os.path.relpath(p, WATCH_DIR)}")
                last_mtimes = new_mtimes
                print("[dev] 重启中...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                proc = subprocess.Popen(
                    [sys.executable, os.path.join(WATCH_DIR, "main.py")],
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
                print("[dev] 已重启")
    except KeyboardInterrupt:
        print("\n[dev] 退出")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
