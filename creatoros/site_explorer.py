"""Explorer: crawl a brand's website and turn it into checkable facts.

Real Chromium (Playwright) by default; a static HTML fallback exists for tests and environments
without a browser. Facts are built with Veridemo Watch's `extract_truth_set` (vendored), so every
fact has a stable id (url + selector) and a content hash.

Demo fixtures: fictional domains listed in sample_data/fixture_domains.json are served from local
HTML files (loaded via file://). Every other domain is crawled live.
"""
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from . import truth_set as ts
from .netguard import is_public_url
from .util import host_of, registrable_domain

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MAP = ROOT / "sample_data" / "fixture_domains.json"
SITES_DIR = ROOT / "sample_data" / "sites"

ts.MAX_FACTS_PER_PAGE = 300      # a brand site is small; do not truncate
ts.MAX_FACTS_TOTAL = 600

_INTERESTING = re.compile(r"about|pricing|price|plans|security|privacy|terms|contact|features|product|company|trust", re.I)

_JS = r"""
() => {
  const out = [], seen = new Set();
  const path = (el) => { const parts=[]; let e=el;
    while (e && e.nodeType===1 && parts.length<12) {
      let i=1, s=e; while ((s=s.previousElementSibling)) if (s.tagName===e.tagName) i++;
      parts.unshift(e.tagName.toLowerCase()+':nth-of-type('+i+')'); e=e.parentElement; }
    return parts.join(' > '); };
  for (const el of document.body.querySelectorAll('*')) {
    const tag = el.tagName.toLowerCase();
    if (['script','style','noscript','svg','path','head'].includes(tag)) continue;
    const txt = (el.innerText||'').replace(/\s+/g,' ').trim();
    if (!txt || txt.length>180 || el.children.length>4) continue;
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    const vis = r.width>0 && r.height>0 && cs.visibility!=='hidden' && cs.display!=='none';
    const sel = path(el); if (seen.has(sel)) continue; seen.add(sel);
    out.push({tag_name: tag, text: txt, css_selector: sel, is_visible: vis});
  }
  const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({href: a.href, text: (a.innerText||'').trim()}));
  return {elements: out, links: links, title: document.title};
}
"""


def _fixtures() -> Dict[str, str]:
    try:
        d = json.loads(FIXTURE_MAP.read_text(encoding="utf-8"))
        return {k.lower(): v for k, v in d.items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def resolve(url: str) -> Dict[str, Any]:
    """Return {fetch_url, fixture} where fixture is the local site slug for demo domains."""
    host = host_of(url)
    fx = _fixtures()
    slug = fx.get(host) or fx.get(registrable_domain(host))
    if slug and (SITES_DIR / slug).is_dir():
        return {"fetch_url": (SITES_DIR / slug / "index.html").resolve().as_uri(), "fixture": slug}
    return {"fetch_url": url, "fixture": None}


def _pick_subpages(base_url: str, links: List[Dict[str, str]], limit: int) -> List[str]:
    base = urlparse(base_url)
    picked: List[str] = []
    for l in links:
        href = l.get("href") or ""
        u = urlparse(href)
        same = (u.scheme == "file" and base.scheme == "file" and Path(u.path).parent == Path(base.path).parent) or \
               (u.scheme in ("http", "https") and registrable_domain(u.hostname or "") == registrable_domain(base.hostname or ""))
        if not same or href.split("#")[0] == base_url.split("#")[0] or href in picked:
            continue
        if _INTERESTING.search(href) or _INTERESTING.search(l.get("text", "")):
            picked.append(href.split("#")[0])
        if len(picked) >= limit:
            break
    return list(dict.fromkeys(picked))


def _signals(pages: List[Dict[str, Any]], facts: List[Dict[str, Any]],
             links: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    blob = " ".join(f["text"] for f in facts).lower()
    urls = " ".join(p["url"].lower() for p in pages) + " " + " ".join(p.get("title", "").lower() for p in pages)
    urls += " " + " ".join((l.get("href", "") + " " + l.get("text", "")).lower() for l in (links or []))
    sig: List[Dict[str, str]] = []

    def add(ok: bool, good: str, bad: str, bad_level: str = "warn"):
        sig.append({"level": "ok" if ok else bad_level, "text": good if ok else bad})

    add(bool(re.search(r"about", urls)), "Has an About page", "No About page found")
    add(bool(re.search(r"pricing|plans|price", urls)), "Has a pricing page", "No pricing page found", "info")
    add(bool(re.search(r"privacy|terms", urls)), "Has a privacy policy or terms", "No privacy policy or terms found")
    entity = None
    for f in facts:                                  # a footer line such as "(c) 2026 XYZ Technologies Pvt Ltd"
        m = re.match(r"^(?:©|&copy;)\s*\d{4}\s+(.{3,80})$", f["text"])
        if m:
            entity = m.group(1).strip().rstrip(".")
            break
    add(bool(entity), f"Legal entity shown: {entity}" if entity else "", "No company legal name shown")
    contact = re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", " ".join(f["text"] for f in facts))
    if contact:
        sig.append({"level": "ok", "text": f"Contact address on the site: @{contact[0]}"})
    if re.search(r"sign in with google|verify your channel|log ?in to (?:receive|verify)|enter your (?:password|otp)", blob):
        sig.append({"level": "bad", "text": "The site asks visitors to sign in or 'verify your channel' (account-takeover pattern)"})
    if re.search(r"claim yours within|limited slots|within \d+ hours", blob):
        sig.append({"level": "warn", "text": "The site uses countdown / scarcity pressure"})
    return sig


def crawl(url: str, mode: str = "auto", max_pages: int = 4, timeout_ms: int = 25000) -> Dict[str, Any]:
    """Crawl `url`. mode: 'browser' | 'static' | 'auto' (browser, falling back to static)."""
    started = time.time()
    res = resolve(url)
    result: Dict[str, Any] = {"ok": False, "url": url, "fetch_url": res["fetch_url"], "fixture": res["fixture"],
                              "pages": [], "facts": [], "signals": [], "mode": None, "error": None}
    if not res["fixture"]:
        ok, why = is_public_url(url)
        if not ok:
            result["error"] = f"blocked: {why}"
            result["blocked"] = True
            return result
    crawl_data: Optional[Dict[str, Any]] = None
    if mode in ("browser", "auto"):
        try:
            crawl_data = _crawl_browser(res["fetch_url"], max_pages, timeout_ms)
            result["mode"] = "browser"
        except Exception as e:                      # noqa: BLE001 - fall back, but remember why
            result["error"] = f"browser: {str(e)[:120]}"
            if mode == "browser":
                return result
    if crawl_data is None:
        try:
            crawl_data = _crawl_static(res["fetch_url"], max_pages)
            result["mode"] = "static"
            result["error"] = None if crawl_data["pages"] else result["error"]
        except Exception as e:                      # noqa: BLE001
            result["error"] = f"{result['error'] or ''} static: {str(e)[:120]}".strip()
            return result
    if not crawl_data["pages"]:
        result["error"] = result["error"] or "no pages could be loaded"
        return result
    facts = ts.extract_truth_set({"pages": [{"url": p["url"], "elements": p["elements"]} for p in crawl_data["pages"]]})
    result.update(ok=True, pages=[{"url": p["url"], "title": p["title"]} for p in crawl_data["pages"]],
                  facts=facts, signals=_signals(crawl_data["pages"], facts, crawl_data.get("links")), seconds=round(time.time() - started, 1))
    return result


def _route_guard(route) -> None:
    """Abort any browser request that is not public http(s) (or one of our own fixture files)."""
    url = route.request.url
    if url.startswith(("data:", "about:")):
        route.continue_()
    elif url.startswith("file:"):
        local = Path(urlparse(url).path.lstrip("/") if re.match(r"^/[A-Za-z]:", urlparse(url).path) else urlparse(url).path)
        try:
            inside = SITES_DIR.resolve() in local.resolve().parents
        except OSError:
            inside = False
        route.continue_() if inside else route.abort()
    elif is_public_url(url)[0]:
        route.continue_()
    else:
        route.abort()


def _fetch_public(url: str, max_redirects: int = 3, max_bytes: int = 2_000_000) -> str:
    """GET a public page, checking every redirect hop against the network guard."""
    import httpx
    for _ in range(max_redirects + 1):
        ok, why = is_public_url(url)
        if not ok:
            raise ValueError(f"blocked: {why}")
        r = httpx.get(url, timeout=15, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 CreatorOS-DealDesk"})
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        r.raise_for_status()
        return r.text[:max_bytes]
    raise ValueError("too many redirects")


def _crawl_browser(fetch_url: str, max_pages: int, timeout_ms: int) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright
    pages: List[Dict[str, Any]] = []
    all_links: List[Dict[str, str]] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            ctx = b.new_context(locale="en-US", viewport={"width": 1280, "height": 1800},
                                accept_downloads=False, service_workers="block")
            ctx.route("**/*", _route_guard)
            pg = ctx.new_page()
            queue, seen = [fetch_url], set()
            while queue and len(pages) < max_pages:
                u = queue.pop(0)
                if u in seen:
                    continue
                seen.add(u)
                try:
                    pg.goto(u, timeout=timeout_ms, wait_until="domcontentloaded")
                    pg.wait_for_timeout(600 if u.startswith("file:") else 2500)
                    data = pg.evaluate(_JS)
                except Exception:
                    if not pages:
                        raise
                    continue
                pages.append({"url": u, "title": data["title"], "elements": data["elements"]})
                if len(pages) == 1:
                    all_links = data["links"]
                    queue += _pick_subpages(u, data["links"], max_pages - 1)
        finally:
            b.close()
    return {"pages": pages, "links": all_links}


def _crawl_static(fetch_url: str, max_pages: int) -> Dict[str, Any]:
    from bs4 import BeautifulSoup

    def load(u: str) -> str:
        if u.startswith("file:"):
            return Path(urlparse(u).path.lstrip("/") if re.match(r"^/[A-Za-z]:", urlparse(u).path) else urlparse(u).path).read_text(encoding="utf-8")
        return _fetch_public(u)

    def parse(u: str):
        soup = BeautifulSoup(load(u), "html.parser")
        for t in soup(["script", "style", "noscript", "svg"]):
            t.decompose()
        els = []
        for el in soup.find_all(True):
            if el.name in ("html", "head", "body", "title", "meta"):
                continue
            txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if not txt or len(txt) > 180 or len(el.find_all(True, recursive=False)) > 4:
                continue
            chain, cur = [], el
            while cur is not None and getattr(cur, "name", None) and cur.name != "[document]":
                sibs = [s for s in cur.parent.find_all(cur.name, recursive=False)] if cur.parent else [cur]
                chain.append(f"{cur.name}:nth-of-type({sibs.index(cur) + 1 if cur in sibs else 1})")
                cur = cur.parent
            els.append({"tag_name": el.name, "text": txt, "css_selector": " > ".join(reversed(chain)), "is_visible": True})
        links = [{"href": urljoin(u, a["href"]), "text": a.get_text(" ", strip=True)} for a in soup.find_all("a", href=True)]
        return {"url": u, "title": (soup.title.string if soup.title else "") or "", "elements": els}, links

    first, links = parse(fetch_url)
    pages = [first]
    for u in _pick_subpages(fetch_url, links, max_pages - 1):
        try:
            pages.append(parse(u)[0])
        except Exception:                          # noqa: BLE001
            continue
    return {"pages": pages, "links": links}
