"""Sci-Hub — DOI/标题/关键词搜索 + PDF 下载

使用 scihub Python 库直接下载，无需浏览器。

用法:
  python main.py scihub "10.1109/ACCESS.2023.3312345"
  python main.py scihub --doi "10.1109/ACCESS.2023.3312345"
  python main.py scihub --title "deep learning review"
  python main.py scihub --keyword "machine learning" --results 10
"""

import sys
import os
import json
import argparse
from datetime import datetime

from utils import sp, log, safe_filename, ensure_output_dir


DEFAULT_OUTPUT = "./SciHub_Results"


def search_by_doi(doi, output_dir):
    """通过 DOI 搜索并下载"""
    try:
        from scihub import SciHub
    except ImportError:
        log("SCIHUB", "scihub library not found. Install: pip install scihub")
        return None

    sh = SciHub()
    log("SCIHUB", f"Searching DOI: {doi}")
    try:
        result = sh.fetch(doi)
        if not result:
            log("SCIHUB", "No result found.")
            return None

        paper = result.get("paper", {})
        title = paper.get("title", doi)
        pdf_url = paper.get("pdf_url", "")

        log("SCIHUB", f"Title: {title[:80]}")
        if pdf_url:
            log("SCIHUB", f"PDF URL: {pdf_url}")

        # Download
        output_dir = ensure_output_dir(output_dir)
        safe_title = safe_filename(title, 80)
        filepath = os.path.join(output_dir, f"{safe_title}.pdf")

        log("SCIHUB", f"Downloading to: {filepath}")
        sh.download(doi, path=output_dir)

        # scihub library saves with its own naming, find the file
        for f in os.listdir(output_dir):
            if f.endswith(".pdf") and os.path.getsize(os.path.join(output_dir, f)) > 1000:
                actual_path = os.path.join(output_dir, f)
                log("SCIHUB", f"Saved: {actual_path} ({os.path.getsize(actual_path)//1024} KB)")
                return actual_path

        return filepath
    except Exception as e:
        log("SCIHUB", f"Error: {e}")
        return None


def search_by_title(title, output_dir):
    """通过标题搜索，先 CrossRef 找 DOI，再下载"""
    try:
        import requests
    except ImportError:
        log("SCIHUB", "requests library required.")
        return None

    log("SCIHUB", f"Searching title: {title}")
    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"query.title": title, "rows": 5},
            timeout=15,
        )
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        if not items:
            log("SCIHUB", "No DOI found.")
            return None

        for item in items:
            doi = item.get("DOI", "")
            if doi:
                log("SCIHUB", f"Found DOI: {doi}")
                return search_by_doi(doi, output_dir)

        log("SCIHUB", "No DOI found in results.")
        return None
    except Exception as e:
        log("SCIHUB", f"CrossRef error: {e}")
        return None


def search_by_keyword(keyword, num_results, output_dir):
    """通过关键词搜索，先 CrossRef 找论文列表"""
    try:
        import requests
    except ImportError:
        log("SCIHUB", "requests library required.")
        return None

    log("SCIHUB", f"Searching keyword: {keyword} (top {num_results})")
    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"query": keyword, "rows": num_results},
            timeout=15,
        )
        data = resp.json()
        items = data.get("message", {}).get("items", [])

        results = []
        for item in items:
            doi = item.get("DOI", "")
            title = (item.get("title") or [""])[0]
            year = (item.get("published-print") or item.get("published-online") or {}).get("date-parts", [[None]])[0][0]
            if doi:
                results.append({"doi": doi, "title": title, "year": year})
                log("SCIHUB", f"  [{len(results)}] {title[:60]} -> {doi}")

        # Save list
        output_dir = ensure_output_dir(output_dir)
        list_path = os.path.join(output_dir, "scihub_search_results.json")
        with open(list_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        log("SCIHUB", f"Results saved: {list_path}")

        # Ask whether to download
        log("SCIHUB", f"Press Enter to download all {len(results)} papers, Ctrl+C to cancel...")
        try:
            input()
        except KeyboardInterrupt:
            log("SCIHUB", "Cancelled.")
            return results

        for r in results:
            if r.get("doi"):
                search_by_doi(r["doi"], output_dir)

        return results
    except Exception as e:
        log("SCIHUB", f"CrossRef error: {e}")
        return None


def get_metadata(doi):
    """获取文献元数据"""
    try:
        from scihub import SciHub
    except ImportError:
        log("SCIHUB", "scihub library not found.")
        return

    sh = SciHub()
    try:
        result = sh.fetch(doi)
        if result:
            paper = result.get("paper", {})
            sp(json.dumps(paper, ensure_ascii=False, indent=2))
        else:
            log("SCIHUB", f"No metadata for DOI: {doi}")
    except Exception as e:
        log("SCIHUB", f"Error: {e}")


def main(args_text: str):
    """Sci-Hub 主入口，支持两种调用方式"""
    # Try parsing as plain DOI first
    plain = args_text.strip().strip('"\'')
    if plain.startswith("10.") and "/" in plain:
        search_by_doi(plain, DEFAULT_OUTPUT)
        return

    # CLI-style args
    parser = argparse.ArgumentParser(prog="scihub", add_help=False)
    parser.add_argument("--doi", type=str, default="")
    parser.add_argument("--title", type=str, default="")
    parser.add_argument("--keyword", type=str, default="")
    parser.add_argument("--results", type=int, default=10)
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT)
    parser.add_argument("--metadata", type=str, default="")

    try:
        parsed = parser.parse_args(args_text.split())
    except SystemExit:
        # Show usage
        sp("Sci-Hub Download Tool")
        sp("=" * 50)
        sp("Usage:")
        sp('  python main.py scihub "10.1109/ACCESS.2023.3312345"')
        sp('  python main.py scihub --doi "10.1109/ACCESS.2023.3312345"')
        sp('  python main.py scihub --title "deep learning review"')
        sp('  python main.py scihub --keyword "machine learning" --results 10')
        return

    output_dir = parsed.output

    if parsed.metadata:
        get_metadata(parsed.metadata)
    elif parsed.doi:
        search_by_doi(parsed.doi, output_dir)
    elif parsed.title:
        search_by_title(parsed.title, output_dir)
    elif parsed.keyword:
        search_by_keyword(parsed.keyword, parsed.results, output_dir)
    else:
        sp("Sci-Hub Download Tool")
        sp("=" * 50)
        sp("Usage:")
        sp('  python main.py scihub "10.1109/ACCESS.2023.3312345"')
        sp('  python main.py scihub --doi "10.1109/ACCESS.2023.3312345"')
        sp('  python main.py scihub --title "deep learning review"')
        sp('  python main.py scihub --keyword "machine learning" --results 10')


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
