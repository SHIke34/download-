#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
download — 学术文献批量检索下载工具集 (Unified Launcher)

用法:
  python main.py <source> [args...]

支持的源:
  sl        Springer Link — OA搜索 + PDF下载
  cnki      CNKI 知网 — 筛选 + PDF/CAJ下载
  ieee      IEEE Xplore — 搜索 + PDF下载 (含 Sci-Hub 回退)
  ebsco     EBSCOhost — VPN搜索 + PDF下载
  wos       Web of Science — 期刊/OA筛选 + PDF下载
  wiley     Wiley Online Library — 搜索 + PDF下载
  scihub    Sci-Hub — DOI/标题/关键词搜索 + PDF下载
  openalex  OpenAlex — API搜索 + PDF下载
  oa        openalex 别名
  crossref  Crossref — API搜索 + PDF下载
  cr        crossref 别名
  semantic  Semantic Scholar — 搜索 + PDF下载
  ss        semantic 别名
  sd        ScienceDirect — OA搜索 + PDF下载 (VPN)
  sciencedirect  sd 的别名

示例:
  python main.py sl "reinforcement learning | 2024 2026 | relevance | 10"
  python main.py cnki "深度学习 | 2024 2026 | CSSCI,SCI | 被引 | 20"
  python main.py ieee "transformer | 2022 2025 | citations | 15"
  python main.py ebsco "FinTech | 2016 2026 | 20 | ./papers | webvpn.upc.edu.cn"
  python main.py wos "fintech | 2022 2025 | 10 | ./WoS_Results"
  python main.py openalex "large language models | 2024 2026 | Computer Science | 5"
  python main.py crossref "large language models | 2024 2026 | 5 | ./papers"
  python main.py semantic "large language models | 2024 2026 | 5 | ./papers"
  python main.py scihub "10.1109/ACCESS.2023.3312345"
  python main.py sd "fintech prediction | 2025 2026 | 5 | ./SD_Results"
"""

import sys
import os

# Ensure scripts/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def sp(*args, **kwargs):
    text = " ".join(str(a) for a in args)
    try:
        print(text, **kwargs, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode(), **kwargs, flush=True)


def show_usage():
    sp(__doc__)


def main():
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(0)

    source = sys.argv[1].lower()
    args_text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    modules = {
        "sl": "sl",
        "cnki": "cnki",
        "ieee": "ieee",
        "ebsco": "ebsco",
        "wos": "wos",
        "webofscience": "wos",
        "wiley": "wiley",
        "scihub": "scihub_dl",
        "sci-hub": "scihub_dl",
        "openalex": "openalex",
        "oa": "openalex",
        "crossref": "crossref",
        "cr": "crossref",
        "semantic": "semantic",
        "semanticscholar": "semantic",
        "ss": "semantic",
        "sd": "sciencedirect",
        "sciencedirect": "sciencedirect",
    }

    if source not in modules:
        sp(f"[ERROR] Unknown source: {source}")
        sp(f"  Available: {', '.join(sorted(modules.keys()))}")
        show_usage()
        sys.exit(1)

    module_name = modules[source]
    try:
        mod = __import__(module_name)
        mod.main(args_text)
    except ImportError as e:
        sp(f"[ERROR] Failed to load module '{module_name}': {e}")
        sp(f"  Ensure {module_name}.py exists in the scripts/ directory.")
        sys.exit(1)
    except Exception as e:
        sp(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
