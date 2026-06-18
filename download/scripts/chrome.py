#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chrome 启动/检测/连接工具
快速检查 Chrome CDP 状态，未启动则自动启动。

用法:
  python chrome.py        # 检测并启动Chrome CDP
  python chrome.py check  # 只检测不启动
"""

import os
import subprocess
import sys
import time
import urllib.request
import json

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CDP_PORT = 9222
USER_DATA_DIR = r"C:\chrome-profile"


def is_chrome_cdp_running():
    """检测 Chrome CDP 是否在运行"""
    try:
        req = urllib.request.Request(f"http://localhost:{CDP_PORT}/json/version")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            print(f"  ✅ Chrome CDP 运行中: {data.get('Browser', '?')}")
            return True
    except Exception:
        return False


def start_chrome():
    """启动 Chrome 调试模式"""
    if not os.path.exists(CHROME_PATH):
        print(f"  ❌ 找不到 Chrome: {CHROME_PATH}")
        return False

    cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={USER_DATA_DIR}",
        "--new-window",
        "about:blank",
    ]

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  🚀 Chrome 启动中... (port {CDP_PORT})")

        # 等待 CDP 就绪
        for _ in range(20):
            time.sleep(1)
            if is_chrome_cdp_running():
                return True
        print("  ⚠️ Chrome 已启动但 CDP 未就绪，请手动确认")
        return False
    except Exception as e:
        print(f"  ❌ 启动失败: {e}")
        return False


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"

    print("=" * 50)
    print("Chrome CDP 管理器")
    print("=" * 50)

    if mode == "check":
        if is_chrome_cdp_running():
            print("  Chrome 已就绪，可直接连接")
            return 0
        else:
            print("  Chrome CDP 未运行")
            return 1

    # 默认模式：检测 → 启动
    if is_chrome_cdp_running():
        print("  ✅ Chrome 已就绪")
        return 0

    print("  ⚠️ Chrome CDP 未运行，正在启动...")
    if start_chrome():
        print("  ✅ Chrome 启动成功")
        return 0
    else:
        print("  ❌ Chrome 启动失败，请手动启动:")
        print(f'     "{CHROME_PATH}" --remote-debugging-port={CDP_PORT} --remote-allow-origins=* --user-data-dir="{USER_DATA_DIR}"')
        return 1


if __name__ == "__main__":
    sys.exit(main())
