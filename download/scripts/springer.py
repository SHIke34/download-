"""Springer Link (同步版) — 搜索 + 期刊限定 + 批量下载 PDF

通过 Playwright CDP (sync_api) 操作 Springer Link。
支持期刊 ID 筛选、年份范围、翻页抓取、expect_download 下载 PDF。

用法:
  python main.py springer "keyword | journalId | startYear endYear | count | outputDir"
"""

import sys
import time
import os
import re
import json
import urllib.parse

from utils import sp, log, safe_filename, ensure_output_dir, FailedRecord


DEFAULT_COUNT = 10
DEFAULT_OUTPUT = "./Springer_Results"


def parse_args(args_text: str) -> dict:
    """解析 Springer (同步版) 参数

    格式: keyword | journalId | startYear endYear | count | outputDir
    journalId 可选
    """
    params = {
        "keyword": "",
        "journal_id": None,
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
        # 可能是 journal_id (纯数字) 或年份对
        if re.match(r"^\d+$", parts[1]):
            params["journal_id"] = parts[1]
        else:
            years = parts[1].split()
            if len(years) >= 2 and years[0].isdigit() and years[1].isdigit():
                params["start_year"] = int(years[0])
                params["end_year"] = int(years[1])
    if len(parts) >= 3 and parts[2]:
        year_match = re.match(r"(\d{4})\s+(\d{4})$", parts[2])
        if year_match:
            params["start_year"] = int(year_match.group(1))
            params["end_year"] = int(year_match.group(2))
        elif parts[2].isdigit():
            params["count"] = int(parts[2])
    if len(parts) >= 4 and parts[3] and parts[3].isdigit():
        params["count"] = int(parts[3])
    if len(parts) >= 5 and parts[4]:
        params["output_dir"] = parts[4]

    return params


def build_search_url(keyword, journal_id=None, start_year=None, end_year=None):
    """构建 Springer Link 搜索 URL"""
    params = {
        "query": keyword,
        "facet-content-type": '"Article"',
    }
    if journal_id:
        params["facet-journal-id"] = journal_id
    if start_year:
        params["date-facet-mode"] = "between"
        params["facet-start-year"] = str(start_year)
        params["facet-end-year"] = str(end_year) if end_year else str(start_year)
    return f"https://link.springer.com/search?{urllib.parse.urlencode(params)}"


def connect_browser():
    """连接到已打开的 Chrome (CDP 9222)"""
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    page = context.new_page()
    return p, browser, context, page


def extract_articles_from_page(page):
    """从当前搜索结果页提取文章列表"""
    return page.evaluate("""
    () => {
        const articles = [];
        // 策略1: 新版 data-test 属性
        const items = document.querySelectorAll('[data-test="article-list-item"], [data-test="result-item"]');
        items.forEach(item => {
            const titleEl = item.querySelector('[data-test="title"], h3 a, h3.c-card__title a, a[data-track="click"]');
            if (!titleEl || !titleEl.innerText) return;
            const href = titleEl.href || '';
            const doiMatch = href.match(/\\/article\\/(10\\.[\\d]+\\/[^?#]+)/);
            const doi = doiMatch ? doiMatch[1] : '';
            articles.push({
                title: (titleEl.innerText || '').trim(),
                url: href,
                doi: doi,
            });
        });
        // 策略2: 经典列表
        if (articles.length === 0) {
            const rows = document.querySelectorAll('#results-list li, .app-article-list-row');
            rows.forEach(item => {
                const titleEl = item.querySelector('.app-article-list-row__title a, h3.c-card__title a');
                if (!titleEl || !titleEl.innerText) return;
                const href = titleEl.href || '';
                const doiMatch = href.match(/\\/article\\/(10\\.[\\d]+\\/[^?#]+)/);
                articles.push({
                    title: (titleEl.innerText || '').trim(),
                    url: href,
                    doi: doiMatch ? doiMatch[1] : '',
                });
            });
        }
        // 去重
        const seen = new Set();
        return articles.filter(a => {
            if (seen.has(a.doi)) return false;
            if (a.doi) seen.add(a.doi);
            return a.title.length > 5;
        });
    }
    """)


def has_next_page(page):
    return page.evaluate("""
    () => {
        const btn = document.querySelector('a[data-test="next"], a.next, .pagination .next a, a[rel="next"]');
        if (!btn) return false;
        const c = btn.className || '';
        const pc = (btn.parentElement && btn.parentElement.className) || '';
        return !c.includes('disabled') && !pc.includes('disabled');
    }
    """)


def go_next_page(page):
    page.evaluate("""
    () => {
        const btn = document.querySelector('a[data-test="next"], a.next, .pagination .next a, a[rel="next"]');
        if (btn) btn.click();
    }
    """)


def get_articles(page, count, max_pages=20):
    """翻页抓取文章列表"""
    all_articles, seen = [], set()
    for pg in range(max_pages):
        articles = extract_articles_from_page(page)
        for art in articles:
            if art["doi"] and art["doi"] not in seen:
                seen.add(art["doi"])
                all_articles.append(art)
                if len(all_articles) >= count:
                    return all_articles[:count]

        if not has_next_page(page):
            break
        go_next_page(page)
        time.sleep(3)
    return all_articles[:count]


def download_pdfs(context, articles, output_dir, failed):
    """批量下载 PDF"""
    success, fail_count = 0, 0
    for idx, art in enumerate(articles):
        title = art["title"]
        doi = art["doi"]
        log("SPRINGER", f"[{idx+1}/{len(articles)}] {title[:60]}")

        if not doi:
            failed.add(title=title, source="SpringerLink(sync)", reason="No DOI")
            log("SPRINGER", "  ✗ No DOI, skip")
            fail_count += 1
            continue

        pdf_url = f"https://link.springer.com/content/pdf/{doi}.pdf"
        try:
            tab = context.new_page()
            tab.set_default_timeout(60000)
            safe_name = safe_filename(title, 100)
            filepath = os.path.join(output_dir, f"{safe_name}.pdf")

            with tab.expect_download(timeout=60000) as download_info:
                tab.goto(pdf_url, wait_until="load", timeout=30000)
                time.sleep(2)

                # 检查是否有下载按钮
                has_btn = tab.evaluate("""
                () => {
                    const btns = document.querySelectorAll('a[data-test="download-link"], a[data-track="download"], a.download-link, #download-btn');
                    for (const b of btns) {
                        if ((b.innerText || '').includes('Download') || b.href.endsWith('.pdf')) {
                            b.click(); return true;
                        }
                    }
                    return false;
                }
                """)

            try:
                download = download_info.value
                download.save_as(filepath)
                log("SPRINGER", f"  ✓ {os.path.basename(filepath)}")
                success += 1
            except Exception:
                log("SPRINGER", "  ⚠ Download timeout, trying page print...")
                try:
                    tab.pdf(path=filepath)
                    log("SPRINGER", f"  ✓ {os.path.basename(filepath)} (print)")
                    success += 1
                except:
                    failed.add(title=title, doi=doi, link=pdf_url, source="SpringerLink(sync)", reason="Download failed (expect_download + print both failed)")
                    log("SPRINGER", "  ✗ Failed")
                    fail_count += 1

            tab.close()
            time.sleep(2)
        except Exception as e:
            failed.add(title=title, doi=doi, link=pdf_url, source="SpringerLink(sync)", reason=str(e)[:80])
            log("SPRINGER", f"  ✗ Error: {str(e)[:80]}")
            fail_count += 1

    log("SPRINGER", f"Done: {success} success, {fail_count} failed")
    return success, fail_count


def main(args_text: str):
    """Springer (同步版) 主流程"""
    params = parse_args(args_text)
    keyword = params["keyword"]
    if not keyword:
        log("SPRINGER", "Keyword required.")
        return

    output_dir = ensure_output_dir(params["output_dir"])
    log("SPRINGER", f"Keyword: {keyword} | Count: {params['count']} | Output: {output_dir}")

    p, browser, context, page = connect_browser()
    try:
        search_url = build_search_url(keyword, params["journal_id"], params["start_year"], params["end_year"])
        log("SPRINGER", f"Search URL: {search_url}")
        page.goto(search_url, wait_until="load", timeout=60000)
        time.sleep(3)

        articles = get_articles(page, params["count"])
        if not articles:
            log("SPRINGER", "No articles found.")
            return

        log("SPRINGER", f"Found {len(articles)} articles:")
        for i, art in enumerate(articles):
            sp(f"  {i+1}. {art['title'][:60]}")

        # Save list
        list_path = os.path.join(output_dir, "Springer_列表.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(f"Springer Link 检索结果\n关键词: {keyword}\n共 {len(articles)} 篇\n{'='*60}\n\n")
            for i, art in enumerate(articles):
                f.write(f"{i+1}. {art['title']}\n   DOI: {art['doi']}\n   URL: {art['url']}\n\n")
        log("SPRINGER", f"List saved: {list_path}")

        log("SPRINGER", "Press Enter to download, Ctrl+C to cancel...")
        try:
            input()
        except KeyboardInterrupt:
            log("SPRINGER", "Cancelled.")
            return

        failed_rec = FailedRecord()
        download_pdfs(context, articles, output_dir, failed_rec)
        if failed_rec.count > 0:
            xlsx = failed_rec.save_xlsx(output_dir)
            log("SPRINGER", f"Failed records saved: {xlsx} ({failed_rec.count} papers)")
    finally:
        page.close()
        browser.close()
        p.stop()


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
