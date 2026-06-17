"""EBSCOhost — VPN 搜索 + 同行评审筛选 + PDF 下载

通过 Chrome DevTools Protocol (WebSocket) 连接已打开的 Chrome，
经学校 WebVPN 访问 EBSCOhost，执行高级搜索并批量下载 PDF。

用法:
  python main.py ebsco "keyword | startYear endYear | count | outputDir | vpnDomain"
"""

import json
import os
import re
import sys
import time
import base64
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from utils import sp, log, safe_filename, ensure_output_dir, FailedRecord


DEFAULT_COUNT = 10
DEFAULT_OUTPUT = "./EBSCO_Results"


def parse_args(args_text: str) -> dict:
    """解析 EBSCO 专有参数

    格式: keyword | startYear endYear | count | outputDir | vpnDomain
    """
    params = {
        "keyword": "",
        "start_year": 2016,
        "end_year": 2026,
        "count": DEFAULT_COUNT,
        "output_dir": DEFAULT_OUTPUT,
        "vpn_domain": "",
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
    if len(parts) >= 3 and parts[2].isdigit():
        params["count"] = int(parts[2])
    if len(parts) >= 4 and parts[3]:
        params["output_dir"] = parts[3]
    if len(parts) >= 5 and parts[4]:
        params["vpn_domain"] = parts[4]

    return params


class ChromeCDP:
    """极简 Chrome DevTools Protocol 客户端 (WebSocket)"""

    def __init__(self, port=9222):
        self.port = port
        self.ws = None
        self._msg_id = 0

    def connect(self, tab_filter=None):
        import websocket
        tabs = json.loads(urllib.request.urlopen(f"http://localhost:{self.port}/json").read())
        if not tabs:
            raise RuntimeError("No Chrome tabs found.")

        valid_tabs = [t for t in tabs if t.get("url") and t.get("webSocketDebuggerUrl")]
        if not valid_tabs:
            raise RuntimeError("No valid tabs.")

        target = None
        if tab_filter:
            target = next((t for t in valid_tabs if tab_filter(t)), None)
        if not target:
            target = next((t for t in valid_tabs if not t["url"].startswith("chrome://")), valid_tabs[0])

        ws_url = target["webSocketDebuggerUrl"]
        log("EBSCO", f"Connecting to Chrome tab: {target.get('title', '')[:40]}")
        self.ws = websocket.create_connection(ws_url, timeout=30)
        return self

    def send(self, method, params=None):
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self._msg_id:
                return resp.get("result", {})

    def evaluate(self, js_expr, await_promise=False, timeout=15):
        params = {"expression": js_expr, "returnByValue": True}
        if await_promise:
            params["awaitPromise"] = True
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": "Runtime.evaluate", "params": params}
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(min(5, deadline - time.time()))
            try:
                resp = json.loads(self.ws.recv())
                if resp.get("id") == self._msg_id:
                    return resp.get("result", {}).get("value")
            except:
                break
        return None

    def navigate(self, url):
        return self.send("Page.navigate", {"url": url})

    def close(self):
        if self.ws:
            self.ws.close()


class EBSCODownloader:
    """EBSCO 下载器"""

    def __init__(self, cdp, output_dir, vpn_domain=""):
        self.cdp = cdp
        self.output_dir = output_dir
        self.vpn_domain = vpn_domain
        self.ebsco_domain = ""
        os.makedirs(output_dir, exist_ok=True)

    def detect_vpn_domain(self):
        if self.vpn_domain:
            return self.vpn_domain
        try:
            tabs = json.loads(urllib.request.urlopen(f"http://localhost:{self.cdp.port}/json").read())
            for tab in tabs:
                url = tab.get("url", "")
                if "webvpn." in url or ".vpn." in url:
                    parsed = urllib.parse.urlparse(url)
                    self.vpn_domain = parsed.hostname or ""
                    log("EBSCO", f"Detected VPN domain: {self.vpn_domain}")
                    return self.vpn_domain
        except Exception:
            pass
        log("EBSCO", "Could not auto-detect VPN domain.")
        return ""

    def resolve_ebsco_domain(self):
        if self.ebsco_domain:
            return self.ebsco_domain
        if self.vpn_domain:
            self.ebsco_domain = f"research-ebsco-com-443.{self.vpn_domain}"
        else:
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://localhost:{self.cdp.port}/json").read())
                for tab in tabs:
                    url = tab.get("url", "")
                    if "ebsco" in url.lower() and "webvpn" in url.lower():
                        parsed = urllib.parse.urlparse(url)
                        self.ebsco_domain = parsed.hostname or ""
                        break
            except Exception:
                pass
            if not self.ebsco_domain:
                self.ebsco_domain = "research-ebsco-com-443.webvpn.upc.edu.cn"
                log("EBSCO", f"Using default domain: {self.ebsco_domain}")
        log("EBSCO", f"EBSCO domain: {self.ebsco_domain}")
        return self.ebsco_domain

    def navigate_to_ebsco(self):
        domain = self.resolve_ebsco_domain()
        url = f"https://{domain}/c/dmjzjj/search/advanced/filters"
        log("EBSCO", "Opening EBSCO advanced search...")
        self.cdp.navigate(url)
        time.sleep(4)

    def check_vpn_login(self):
        for _ in range(30):
            time.sleep(2)
            title = self.cdp.evaluate("document.title") or ""
            body = self.cdp.evaluate("document.body ? document.body.innerText.substring(0,500) : ''") or ""

            if "sign_in" in (self.cdp.evaluate("window.location.href") or "").lower():
                log("EBSCO", "VPN login page detected. Please log in manually in Chrome.")
                continue

            if "EBSCOhost" in title or "搜索" in body:
                log("EBSCO", "VPN session active. EBSCO loaded.")
                return True

            if "webvpn" in (self.cdp.evaluate("window.location.href") or "").lower() and "sign_in" in body:
                log("EBSCO", "VPN login required. Please log in manually.")

        log("EBSCO", "Timeout: Could not verify VPN login.")
        return False

    def search(self, keyword, start_year, end_year):
        log("EBSCO", f"Searching: {keyword} ({start_year}-{end_year})")
        self.navigate_to_ebsco()

        self.cdp.evaluate(
            "var ta=document.getElementById('search-autocomplete-1-input');"
            "if(ta){ta.focus();ta.value='';'ok'}else'no'"
        )
        self.cdp.send("Input.insertText", {"text": keyword})
        time.sleep(1)

        # Peer-reviewed
        self.cdp.evaluate(
            "var labels=Array.from(document.querySelectorAll('label'));"
            "var pr=labels.find(function(l){return l.textContent.trim()==='学术（同行评审）期刊'});"
            "if(pr){pr.click();'clicked'}else'no'"
        )
        # Last 10 years
        self.cdp.evaluate(
            "var labels=Array.from(document.querySelectorAll('label'));"
            "var dt=labels.find(function(l){return l.textContent.trim()==='过去 10 年'});"
            "if(dt){dt.click();'clicked'}else'no'"
        )
        time.sleep(0.5)
        # Search button
        self.cdp.evaluate(
            "var btns=Array.from(document.querySelectorAll('button'));"
            "var sb=btns.find(function(b){return(b.textContent||'').trim()==='搜索'});"
            "if(sb){sb.click();'clicked'}else'no'"
        )
        time.sleep(5)

    def get_article_list(self):
        articles_json = self.cdp.evaluate("""
            var cards = document.querySelectorAll('[class*=search-result]');
            var articles = [];
            var seen = {};
            cards.forEach(function(c) {
                var link = c.querySelector('a[href*="search/details"]');
                if (link && link.href) {
                    var m = link.href.match(/\\/details\\/([a-z0-9]+)/);
                    var title = (link.textContent || '').trim();
                    if (m && !seen[m[1]]) {
                        seen[m[1]] = true;
                        articles.push({id: m[1], title: title.substring(0, 120)});
                    }
                }
            });
            JSON.stringify(articles);
        """)
        articles = json.loads(articles_json) if articles_json else []
        log("EBSCO", f"Found {len(articles)} articles")
        return articles

    def get_pdf_url(self, record_id):
        url = self.cdp.evaluate(
            f"""
            fetch('/linkprocessor/v2-pdf-full-text?recordId={record_id}&sourceRecordId={record_id}&profileIdentifier=dmjzjj&intent=view&type=pdfLink')
            .then(function(r) {{ return r.json(); }})
            .then(function(data) {{ return data.url || ''; }})
            .catch(function(e) {{ return ''; }});
            """,
            await_promise=True,
            timeout=20,
        )
        return url or ""

    def download_paper(self, pdf_url, filepath):
        self.cdp.send("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": os.path.abspath(self.output_dir),
        })
        self.cdp.navigate(pdf_url)
        time.sleep(6)

        result = self.cdp.send("Page.printToPDF", {
            "printBackground": True,
            "preferCSSPageSize": True,
        })
        pdf_data = result.get("data", "")
        if not pdf_data or len(pdf_data) < 80000:
            return False

        pdf_bytes = base64.b64decode(pdf_data)
        with open(filepath, "wb") as f:
            f.write(pdf_bytes)
        return True

    def batch_download(self, articles, target_count, failed):
        downloaded = []
        for i, article in enumerate(articles):
            if len(downloaded) >= target_count:
                break

            rec_id = article["id"]
            title = article.get("title", f"article_{rec_id}") or f"article_{rec_id}"
            safe_title = safe_filename(title, 50).replace(" ", "_")
            fname = f"{len(downloaded)+1:02d}_{safe_title}.pdf"
            fpath = os.path.join(self.output_dir, fname)

            log("EBSCO", f"  [{len(downloaded)+1}/{target_count}] {title[:50]}...")

            domain = self.resolve_ebsco_domain()
            self.cdp.navigate(f"https://{domain}/c/dmjzjj/search/details/{rec_id}")
            time.sleep(3)

            pdf_url = self.get_pdf_url(rec_id)
            if not pdf_url:
                failed.add(title=title, source="EBSCO", reason=f"No PDF URL from linkprocessor API (recordId={rec_id})")
                log("EBSCO", "  no PDF available")
                continue

            success = self.download_paper(pdf_url, fpath)
            if success:
                sz = os.path.getsize(fpath)
                downloaded.append({"file": fname, "title": title, "size_kb": round(sz / 1024)})
                log("EBSCO", f"  ✓ {sz//1024}KB [{len(downloaded)}/{target_count}]")
            else:
                failed.add(title=title, link=pdf_url, source="EBSCO", reason="Download failed (small/empty PDF via printToPDF)")
                log("EBSCO", "  ✗ download failed")
            time.sleep(2)

        return downloaded


def main(args_text: str):
    """EBSCO 主流程"""
    params = parse_args(args_text)
    keyword = params["keyword"]
    if not keyword:
        log("EBSCO", "Keyword is required.")
        print("Enter search keyword (e.g. FinTech): ", end="")
        keyword = input().strip()
        if not keyword:
            log("EBSCO", "No keyword provided, exiting.")
            return
        params["keyword"] = keyword

    output_dir = ensure_output_dir(params["output_dir"])

    log("EBSCO", f"Keyword: {params['keyword']}")
    log("EBSCO", f"Year: {params['start_year']}-{params['end_year']} | Count: {params['count']} | Output: {output_dir}")
    log("EBSCO", f"VPN domain: {params['vpn_domain'] or '(auto-detect)'}")

    try:
        cdp = ChromeCDP().connect()
    except Exception as e:
        log("EBSCO", f"Cannot connect to Chrome: {e}")
        log("EBSCO", 'Ensure Chrome running with: --remote-debugging-port=9222 --remote-allow-origins=*')
        return

    cdp.send("Page.enable")
    cdp.send("Runtime.enable")

    downloader = EBSCODownloader(cdp, output_dir, params["vpn_domain"])
    downloader.detect_vpn_domain()

    log("EBSCO", "Navigating to EBSCO...")
    downloader.navigate_to_ebsco()
    if not downloader.check_vpn_login():
        log("EBSCO", "VPN login uncertain, proceeding anyway...")

    log("EBSCO", "Searching...")
    downloader.search(params["keyword"], params["start_year"], params["end_year"])

    log("EBSCO", "Extracting article list...")
    articles = downloader.get_article_list()
    if not articles:
        log("EBSCO", "No articles found.")
        cdp.close()
        return

    for a in articles[:10]:
        sp(f"  [{a['id']}] {a['title'][:60]}")

    log("EBSCO", f"Downloading up to {params['count']} papers...")
    failed = FailedRecord()
    results = downloader.batch_download(articles, params["count"], failed)

    log("EBSCO", f"Done! Downloaded {len(results)} papers to {os.path.abspath(output_dir)}")
    if failed.count > 0:
        xlsx = failed.save_xlsx(output_dir)
        log("EBSCO", f"Failed records saved: {xlsx} ({failed.count} papers)")
    for r in results:
        sp(f"  {r['file']}  ({r['size_kb']} KB)")

    # Save metadata
    meta = {
        "keyword": params["keyword"],
        "year_range": f"{params['start_year']}-{params['end_year']}",
        "download_time": datetime.now(timezone.utc).isoformat(),
        "papers": results,
    }
    meta_path = os.path.join(output_dir, "papers_list.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log("EBSCO", f"Metadata saved to {meta_path}")

    cdp.close()


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
