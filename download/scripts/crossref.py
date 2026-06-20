"""Crossref — API 搜索 + PDF 下载（无需浏览器）

通过 Crossref REST API 检索文献，支持关键词、年份范围筛选，
自动查找并下载 OA PDF。

用法:
  python main.py crossref "keyword | startYear endYear | count | outputDir"
  python main.py cr "keyword | startYear endYear | count | outputDir"

管道格式:
  第1段: 关键词
  第2段: 起止年份 (空格分隔, 如 "2024 2026")
  第3段: 数量 (默认 5)
  第4段: 输出目录 (默认 ./Crossref_Results)
"""

import sys
import os
import re
import json
import requests
from datetime import datetime
from urllib.parse import quote

from utils import sp, log, safe_filename, ensure_output_dir, validate_pdf, FailedRecord, clean_doi


API_BASE = "https://api.crossref.org/works"
DEFAULT_COUNT = 5
DEFAULT_OUTPUT = "./Crossref_Results"


def parse_args(args_text: str) -> dict:
    """解析 Crossref 参数

    格式: keyword | startYear endYear | count | outputDir
    注意: 第3段是 count，第4段是 outputDir（与测试报告一致的规范格式）
    """
    params = {
        "keyword": "",
        "start_year": None,
        "end_year": None,
        "count": DEFAULT_COUNT,
        "output_dir": DEFAULT_OUTPUT,
    }
    if not args_text or not args_text.strip():
        return params

    parts = [p.strip() for p in args_text.split("|")]

    if len(parts) >= 1 and parts[0]:
        params["keyword"] = parts[0]
    if len(parts) >= 2 and parts[1]:
        years = parts[1].split()
        if len(years) >= 1 and years[0].isdigit():
            params["start_year"] = int(years[0])
        if len(years) >= 2 and years[1].isdigit():
            params["end_year"] = int(years[1])
    if len(parts) >= 3 and parts[2] and parts[2].isdigit():
        params["count"] = int(parts[2])
    if len(parts) >= 4 and parts[3]:
        params["output_dir"] = parts[3]

    return params


def search_works(params):
    """通过 Crossref API 搜索文献"""
    filters = []
    if params["start_year"]:
        filters.append(f"from-pub-date:{params['start_year']}-01-01")
    if params["end_year"]:
        filters.append(f"until-pub-date:{params['end_year']}-12-31")

    query_params = {
        "query": params["keyword"],
        "rows": min(params["count"] * 3, 50),
        "sort": "relevance",
        "order": "desc",
    }
    if filters:
        query_params["filter"] = ",".join(filters)

    log("CROSSREF", f"Query: {params['keyword']}")
    log("CROSSREF", f"Year: {params['start_year']}-{params['end_year']}")
    log("CROSSREF", f"Target count: {params['count']}")

    try:
        resp = requests.get(API_BASE, params=query_params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        log("CROSSREF", f"Fetched {len(items)} works")

        papers = []
        for r in items:
            doi = r.get("DOI", "")
            title = (r.get("title") or [""])[0]
            year = (r.get("published-print") or r.get("published-online") or r.get("created") or {}).get("date-parts", [[None]])[0][0]
            authors = [a.get("family", "") for a in (r.get("author") or []) if a.get("family")]
            # Check OA status
            is_oa = r.get("is-referenced-by-count", 0) > 0

            # Try to find PDF URL from link field
            pdf_url = ""
            for link in r.get("link") or []:
                if link.get("content-type") in ("application/pdf", "unspecified") and link.get("URL"):
                    pdf_url = link["URL"]
                    break

            papers.append({
                "title": title,
                "doi": doi,
                "year": year,
                "authors": ", ".join(authors[:5]),
                "cited": r.get("is-referenced-by-count", 0),
                "pdf_url": pdf_url,
            })

        # Year filtering (API may not filter precisely)
        if params["start_year"] and params["end_year"]:
            filtered = [p for p in papers if p["year"] and params["start_year"] <= p["year"] <= params["end_year"]]
            log("CROSSREF", f"After year filter: {len(filtered)} papers")
            return filtered[:params["count"]]

        return papers[:params["count"]]
    except Exception as e:
        log("CROSSREF", f"API error: {e}")
        return []


def find_oa_pdf(doi, title):
    """尝试从多个来源获取 OA PDF"""
    # Unpaywall API (uses email as required param)
    try:
        email = "research@example.com"
        url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            oa_loc = data.get("best_oa_location", {}) or {}
            if oa_loc.get("pdf_url"):
                return oa_loc["pdf_url"]
            if oa_loc.get("url_for_pdf"):
                return oa_loc["url_for_pdf"]
    except Exception:
        pass

    # Direct publisher PDF URL pattern
    if doi:
        return f"https://doi.org/{doi}"

    return ""


def download_pdf(pdf_url, title, doi, index, output_dir):
    """下载单篇 PDF"""
    if not pdf_url:
        return None

    try:
        resp = requests.get(pdf_url, timeout=60,
                            headers={"User-Agent": "Mozilla/5.0"},
                            allow_redirects=True)
        if resp.status_code != 200:
            log("CROSSREF", f"  HTTP {resp.status_code}")
            return None

        safe = safe_filename(title, 80).replace(" ", "_") or f"paper_{index}"
        fname = f"{index:02d}_{safe}.pdf"
        fpath = os.path.join(output_dir, fname)

        with open(fpath, "wb") as f:
            f.write(resp.content)

        ok, msg = validate_pdf(fpath)
        if ok:
            log("CROSSREF", f"  [OK] {fname} ({len(resp.content)//1024} KB)")
            return fpath
        else:
            os.remove(fpath)
            log("CROSSREF", f"  {msg}")
            return None
    except Exception as e:
        log("CROSSREF", f"  error: {e}")
        return None


def main(args_text: str):
    """主流程"""
    params = parse_args(args_text)

    if not params["keyword"]:
        log("CROSSREF", "Keyword required.")
        sp("Usage: python main.py crossref \"keyword | startYear endYear | count | outputDir\"")
        return

    output_dir = ensure_output_dir(params["output_dir"])
    log("CROSSREF", f"Target count: {params['count']} | Output: {output_dir}")

    papers = search_works(params)

    if not papers:
        log("CROSSREF", "No papers found.")
        return

    log("CROSSREF", f"\nResults ({len(papers)} papers):")
    for i, p in enumerate(papers, 1):
        sp(f"  {i:2d}. [{p.get('year','?')}] {p['title'][:70]}")
        if p.get("doi"):
            sp(f"      DOI: {p['doi']}")

    # Save metadata
    meta_path = os.path.join(output_dir, "papers_list.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    log("CROSSREF", f"List saved: {meta_path}")

    # Try to find and download PDFs
    failed = FailedRecord()
    downloaded = 0
    for i, p in enumerate(papers, 1):
        log("CROSSREF", f"  [{i}/{len(papers)}] {p['title'][:50]}")
        pdf_url = p.get("pdf_url", "") or find_oa_pdf(p.get("doi", ""), p.get("title", ""))
        if not pdf_url and p.get("doi"):
            pdf_url = f"https://doi.org/{p['doi']}"

        if pdf_url:
            result = download_pdf(pdf_url, p["title"], p.get("doi", ""), i, output_dir)
            if result:
                downloaded += 1
            else:
                failed.add(title=p["title"], doi=p.get("doi", ""), link=pdf_url, source="Crossref", reason="Download failed")
        else:
            failed.add(title=p["title"], doi=p.get("doi", ""), source="Crossref", reason="No PDF URL found")

    log("CROSSREF", f"Done! {downloaded}/{len(papers)} PDFs downloaded to {output_dir}")
    if failed.count > 0:
        xlsx = failed.save_xlsx(output_dir)
        log("CROSSREF", f"Failed records: {xlsx} ({failed.count} papers)")


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
