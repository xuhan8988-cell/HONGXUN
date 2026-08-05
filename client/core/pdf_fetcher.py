"""
鸿讯 HONGXUN · 论文 PDF 下载模块
版本 1.0.0

多来源回退：Unpaywall → OpenAlex → arXiv → PMC → 出版社直连 → Sci-Hub（可选）。

设计参考 paper-fetch 的 DOI→PDF 多源回退架构：
  1. Unpaywall（OA 权威索引）— best_oa_location.url_for_pdf
  2. OpenAlex（开放学术图谱）— best_oa_location.pdf_url
  3. arXiv — 仅当 DOI 为 10.48550/arXiv.* 或无 DOI 时按标题搜索
  4. PubMed Central（PMC）— idconv 拿 PMCID → oa.fcgi 拿 PDF
  5. 出版社直连 — 低置信，仅当上游给了含 .pdf 的 landing page
  6. Sci-Hub — 仅当配置 enable_scihub=True，作为最后兜底

安全：%PDF- 魔数嗅探拒绝 HTML/CAPTCHA；流式下载 + 超时；禁代理 _session。
"""

import os
import re
import time
from datetime import datetime

from .session import _session

# ── 异常 ──────────────────────────────────────────────────
class FetchError(Exception):
    """无法从任何来源解析出 PDF 地址。"""


class DownloadError(Exception):
    """PDF 地址存在但下载失败。"""


# ── Sci-Hub 镜像（可配置启用，默认关闭） ──────────────────
SCIHUB_MIRRORS = ("sci-hub.se", "sci-hub.st", "sci-hub.ru")

_PDF_MAGIC = b"%PDF-"


def is_pdf(head_bytes: bytes) -> bool:
    """检测字节流是否为 PDF（检查 %PDF- 魔数，拒绝 HTML/CAPTCHA）。"""
    return _PDF_MAGIC in head_bytes[:512]


def filename_for(paper: dict) -> str:
    """按论文元数据生成文件名：{首作者姓}_{年份}_{短标题}.pdf"""
    title = (paper.get("title") or "").strip()
    authors = (paper.get("authors") or "").strip()
    year = ""
    pub_date = (paper.get("pub_date") or "").strip()
    m = re.search(r"(19|20)\d{2}", pub_date)
    if m:
        year = m.group(0)

    # 首作者姓：authors 通常是 "Given Family, Given Family, ..." 或 "Family, Given"
    first_author = ""
    if authors:
        first_part = authors.split(",")[0].strip()
        # 取首作者的最后一个词作为姓（兼容 "Given Family" 与 "Family, Given"）
        words = [w for w in first_part.split() if w]
        if words:
            first_author = words[-1]
    first_author = re.sub(r"[^A-Za-z0-9]", "", first_author)

    # 短标题：前 5 个词，字母数字，下划线连接
    words = re.findall(r"[A-Za-z0-9]+", title)[:5]
    short_title = "_".join(words).lower()

    base = "_".join(x for x in (first_author, year, short_title) if x)
    if not base:
        base = paper.get("id") or "paper"
    base = re.sub(r"[\\/:*?\"<>|]", "_", base)
    return f"{base}.pdf"


def _get_json(url: str, params: dict = None, timeout: int = 20) -> dict | None:
    """GET 并解析 JSON，失败返回 None。"""
    try:
        resp = _session.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


# ── 各来源解析 ────────────────────────────────────────────
def _from_unpaywall(doi: str, email: str) -> dict | None:
    """Unpaywall：best_oa_location.url_for_pdf 优先。"""
    if not doi:
        return None
    data = _get_json(f"https://api.unpaywall.org/v2/{doi}",
                     {"email": email or "691678079@qq.com"})
    if not data:
        return None
    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        return {"pdf_url": best["url_for_pdf"], "source": "unpaywall"}
    for loc in data.get("oa_locations") or []:
        if loc.get("url_for_pdf"):
            return {"pdf_url": loc["url_for_pdf"], "source": "unpaywall"}
    return None


def _from_openalex(doi: str) -> dict | None:
    """OpenAlex：best_oa_location.pdf_url。"""
    if not doi:
        return None
    data = _get_json(f"https://api.openalex.org/works/doi:{doi}")
    if not data:
        return None
    best = data.get("best_oa_location") or {}
    if best.get("pdf_url"):
        return {"pdf_url": best["pdf_url"], "source": "openalex"}
    for loc in data.get("locations") or []:
        if loc.get("pdf_url"):
            return {"pdf_url": loc["pdf_url"], "source": "openalex"}
    return None


def _from_arxiv(doi: str, title: str) -> dict | None:
    """arXiv：DOI 为 10.48550/arXiv.* 或无 DOI 时按标题查。"""
    if doi and "arxiv" not in doi.lower():
        return None
    if not title:
        return None
    try:
        resp = _session.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f'ti:"{title}"', "max_results": 3},
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        # Atom XML 里找 <link title="pdf" href="...">
        links = re.findall(r'<link[^>]*title="pdf"[^>]*href="([^"]+)"', resp.text)
        if not links:
            links = re.findall(r'<link[^>]*rel="related"[^>]*title="pdf"[^>]*href="([^"]+)"', resp.text)
        for url in links:
            if "abs/" in url:
                url = url.replace("/abs/", "/pdf/")
            return {"pdf_url": url, "source": "arxiv"}
    except Exception:
        return None
    return None


def _from_pmc(doi: str) -> dict | None:
    """PubMed Central：idconv 拿 PMCID → oa.fcgi 拿 PDF。"""
    if not doi:
        return None
    data = _get_json("https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
                     {"ids": doi, "format": "json"}, timeout=20)
    if not data or not data.get("records"):
        return None
    rec = data["records"][0]
    pmcid = rec.get("pmcid")
    if not pmcid:
        return None
    oa = _get_json("https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi",
                   {"id": pmcid, "format": "json"}, timeout=20)
    if oa and oa.get("records"):
        href = oa["records"][0].get("href")
        if href:
            url = href if href.startswith("http") else f"https://www.ncbi.nlm.nih.gov{href}"
            return {"pdf_url": url, "source": "pmc"}
    return None


def _from_publisher(doi: str) -> dict | None:
    """出版社直连：仅当上游给了含 .pdf 的 landing page（低置信，不强求）。"""
    if not doi:
        return None
    try:
        resp = _session.get(f"https://doi.org/{doi}",
                            timeout=20, allow_redirects=True)
        if resp.status_code != 200:
            return None
        m = re.search(r'href="([^"]+\.pdf[^"]*)"', resp.text)
        if m:
            return {"pdf_url": m.group(1), "source": "publisher"}
    except Exception:
        return None
    return None


def _from_scihub(doi: str, title: str) -> dict | None:
    """Sci-Hub：逐个镜像尝试，10s 超时。仅合法来源失败后调用。"""
    query = doi or title
    if not query:
        return None
    for host in SCIHUB_MIRRORS:
        try:
            resp = _session.get(f"https://{host}/{query}", timeout=10)
            if resp.status_code != 200:
                continue
            # 页面里嵌入的 pdf 链接：location.replace('...pdf')
            m = re.search(r"location\.replace\(['\"]([^'\"]+?\.pdf[^'\"]*?)['\"]\)",
                          resp.text, re.IGNORECASE)
            if not m:
                m = re.search(r'href="([^"]+?\.pdf[^"]*)"', resp.text, re.IGNORECASE)
            if m:
                url = m.group(1)
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = f"https://{host}" + url
                return {"pdf_url": url, "source": "scihub"}
        except Exception:
            continue
    return None


def fetch_pdf_url(doi: str, title: str = "", config: dict = None) -> dict | None:
    """按回退链解析 PDF 地址。config: pdf_config.load_pdf_config() 的结果。

    返回 {"pdf_url", "source"}；全部失败返回 None。
    """
    config = config or {}
    doi = (doi or "").strip()

    chain = [
        ("unpaywall", lambda: _from_unpaywall(doi, config.get("unpaywall_email", ""))),
        ("openalex", lambda: _from_openalex(doi)),
        ("arxiv", lambda: _from_arxiv(doi, title)),
        ("pmc", lambda: _from_pmc(doi)),
        ("publisher", lambda: _from_publisher(doi)),
    ]
    for name, fn in chain:
        try:
            r = fn()
        except Exception:
            r = None
        if r and r.get("pdf_url"):
            return r

    # Sci-Hub 最后兜底（默认关闭）
    if config.get("enable_scihub"):
        try:
            r = _from_scihub(doi, title)
        except Exception:
            r = None
        if r and r.get("pdf_url"):
            return r

    return None


def download_pdf(pdf_url: str, dest_dir: str, paper: dict,
                 progress_callback=None) -> dict:
    """下载 PDF 到 dest_dir。返回 {"path": 绝对路径}。失败抛 DownloadError。"""
    os.makedirs(dest_dir, exist_ok=True)
    fname = filename_for(paper)
    local_path = os.path.join(dest_dir, fname)

    try:
        resp = _session.get(pdf_url, stream=True, timeout=60)
        if resp.status_code != 200:
            raise DownloadError(f"HTTP {resp.status_code}")
        total = int(resp.headers.get("content-length", 0))

        received = 0
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                if received == 0:
                    # 首块嗅探 %PDF- 魔数
                    head = chunk[:512]
                    if not is_pdf(head):
                        raise DownloadError("下载到的不是 PDF 文件（可能被跳转到登录页）")
                f.write(chunk)
                received += len(chunk)
                if progress_callback and total:
                    progress_callback(received, total)

        if received == 0:
            raise DownloadError("下载内容为空")
        if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            raise DownloadError("下载文件为空")
        return {"path": local_path}
    except DownloadError:
        _cleanup_partial(local_path)
        raise
    except Exception as e:
        _cleanup_partial(local_path)
        raise DownloadError(f"下载失败: {e}")


def _cleanup_partial(path: str):
    """清理下载失败留下的不完整文件。"""
    try:
        if os.path.exists(path) and os.path.getsize(path) == 0:
            os.remove(path)
    except Exception:
        pass


def open_pdf(path: str) -> bool:
    """用系统默认程序打开 PDF。Windows: os.startfile；macOS: open。"""
    if not path or not os.path.exists(path):
        return False
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            import subprocess
            subprocess.Popen(["open", path])
        return True
    except Exception:
        return False
