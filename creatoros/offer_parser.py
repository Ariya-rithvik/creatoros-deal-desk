"""Offer Parser: turn a raw sponsorship e-mail into structured fields.

Best-effort and explicit about what it could not find (`missing`). Deterministic; an LLM can be
layered on later, but the demo and tests must not depend on one.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

from .sender_check import FILE_SHARE, SHORTENERS
from .util import find_urls, host_of, registrable_domain

_MONEY = re.compile(
    r"(?P<cur>USD|US\$|\$|€|£|₹|INR|EUR|GBP)\s?(?P<amt>\d[\d,]*(?:\.\d+)?)"
    r"|(?P<amt2>\d[\d,]*(?:\.\d+)?)\s?(?P<cur2>USD|dollars|INR|rupees|EUR|GBP)", re.I)
_CUR_MAP = {"$": "USD", "US$": "USD", "USD": "USD", "DOLLARS": "USD", "€": "EUR", "EUR": "EUR",
            "£": "GBP", "GBP": "GBP", "₹": "INR", "INR": "INR", "RUPEES": "INR"}
_DUR = re.compile(r"(\d+)\s*(day|week|month|year)s?", re.I)
_DELIV = re.compile(r"(?P<n>\d{1,3})[- ]?(?:sec(?:ond)?s?|s)\b[^.\n]{0,25}?"
                    r"(?P<kind>integration|mention|ad|segment|spot|placement|shout-?out)", re.I)
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def split_email(raw: str) -> Dict[str, str]:
    """Split 'From:/Subject:' headers from the body."""
    sender, subject, body_lines, in_headers = "", "", [], True
    for line in (raw or "").splitlines():
        if in_headers:
            m = re.match(r"(?i)^(from|subject|to|date)\s*:\s*(.*)$", line)
            if m:
                key, val = m.group(1).lower(), m.group(2).strip()
                if key == "from":
                    sender = val
                elif key == "subject":
                    subject = val
                continue
            if not line.strip():
                in_headers = False
                continue
            in_headers = False
        body_lines.append(line)
    return {"sender": sender, "subject": subject, "body": "\n".join(body_lines).strip()}


def _days(text: str) -> Optional[int]:
    m = _DUR.search(text or "")
    return int(m.group(1)) * _UNIT_DAYS[m.group(2).lower()] if m else None


def _line_with(body: str, *keys: str) -> Optional[str]:
    for line in body.splitlines():
        if any(k in line.lower() for k in keys):
            return line.strip()
    return None


def _amount(body: str) -> Optional[Dict[str, Any]]:
    """The offered fee: prefer an 'Offer:' line, else a sentence about sponsoring/paying that is not a fee demand."""
    lines = body.splitlines()
    explicit = [l for l in lines if re.match(r"(?i)^\s*offer\s*:", l)]            # an 'Offer:' line always wins
    candidates = [l for l in lines if re.search(r"(?i)\boffer\b|sponsor|pay you|compensation|budget|for \$", l)
                  and not re.search(r"(?i)\bfee\b|deposit|\bplan\b|per month|/month", l)]
    for line in explicit + candidates:
        m = _MONEY.search(line)
        if m:
            cur = (m.group("cur") or m.group("cur2") or "").upper()
            amt = float((m.group("amt") or m.group("amt2")).replace(",", ""))
            return {"amount": amt, "currency": _CUR_MAP.get(cur, cur), "raw": m.group(0)}
    return None


def _brand(subject: str, sender: str, body: str) -> Optional[str]:
    pats = [r"promote\s+([A-Z][\w.]*(?:\s[A-Z][\w.]*){0,2})", r"(?:We at|from)\s+([A-Z]\w*(?:\s[A-Z]\w*){0,2})\s*\(",
            r"about\s+([A-Z]\w*(?:\s[A-Z]\w*){0,2})\s*\("]
    for p in pats:
        m = re.search(p, body)
        if m:
            return m.group(1).strip().rstrip(",.")
    m = re.search(r"^(?:sponsorship:\s*)?([A-Z][\w ]+?)\s+x\s+", subject or "")
    if m:
        return m.group(1).strip()
    m = re.match(r"\s*([^<]+?)\s*<", sender or "")
    return m.group(1).strip() if m else None


def parse_offer(raw: str) -> Dict[str, Any]:
    parts = split_email(raw)
    body, sender, subject = parts["body"], parts["sender"], parts["subject"]
    urls = find_urls(body)
    website = next((u for u in urls if registrable_domain(host_of(u)) not in SHORTENERS | FILE_SHARE), None)

    terms: Dict[str, Any] = {}
    amt = _amount(body)
    terms["amount"] = amt["amount"] if amt else None
    terms["currency"] = amt["currency"] if amt else None
    terms["amount_raw"] = amt["raw"] if amt else None

    m = _DELIV.search(body)
    terms["duration_seconds"] = int(m.group("n")) if m else None
    terms["deliverable"] = (f"{m.group('n')}-second {m.group('kind').lower()}" if m
                            else ("dedicated video" if re.search(r"(?i)dedicated video", body) else None))

    line = _line_with(body, "usage", "whitelist", "licen", "reposting")
    terms["usage_perpetual"] = bool(line and re.search(r"(?i)perpetual|in perpetuity|forever|unlimited", line))
    terms["usage_days"] = 36500 if terms["usage_perpetual"] else (_days(line) if line else None)

    line = _line_with(body, "exclusiv")
    if line and re.search(r"(?i)\bno exclusiv", line):
        terms["exclusivity_days"] = 0
    else:
        terms["exclusivity_days"] = _days(line) if line else None

    line = _line_with(body, "payment terms", "net ", "paid within", "payment is", "payment will")
    terms["net_days"] = None
    if line:
        n = re.search(r"(?i)net\s?(\d+)|within\s(\d+)\s*days", line)
        if n:
            terms["net_days"] = int(n.group(1) or n.group(2))
    terms["pay_after_publication"] = bool(re.search(r"(?i)after (?:the )?(?:video|content|post)[^.\n]{0,20}(?:goes |is )?(?:live|published|posted)", body))
    terms["has_contract"] = bool(re.search(r"(?i)written contract|signed contract|contract", body))
    terms["deposit"] = bool(re.search(r"(?i)deposit|upfront|up-front|advance payment|50% upfront", body))

    m = re.search(r"(?i)(?:deadline|publish by|by)\s*:?\s*(\d{4}-\d{2}-\d{2})", body)
    terms["deadline"] = m.group(1) if m else None

    talking: List[str] = []
    grab = False
    for line in body.splitlines():
        if re.match(r"(?i)^\s*talking points\s*:?", line):
            grab = True
            continue
        if grab:
            if re.match(r"^\s*[-•*]\s+", line):
                talking.append(re.sub(r"^\s*[-•*]\s+", "", line).strip())
            elif line.strip():
                grab = False

    cta_quote = re.search(r"(?i)(?:mention|say)\s+[\"“']([^\"”']{3,60})[\"”']", body)
    promo = re.search(r"\b(?i:code|coupon)\s+[\"']?([A-Z0-9]{3,14})\b", body)
    disc = re.search(r"(?i)(\d{1,2})%\s*off", body)
    mentions_disclosure = bool(re.search(r"(?i)paid partnership|disclos|#ad\b|sponsored", body))

    parsed = {
        "sender": sender, "subject": subject, "body": body,
        "brand": _brand(subject, sender, body), "website": website, "urls": urls,
        "terms": terms, "talking_points": talking,
        "cta": cta_quote.group(1) if cta_quote else None,
        "promo_code": promo.group(1) if promo else None,
        "discount_percent": int(disc.group(1)) if disc else None,
        "brand_mentions_disclosure": mentions_disclosure,
    }
    parsed["missing"] = [k for k in ("amount", "deliverable", "usage_days", "exclusivity_days", "net_days", "deadline")
                         if terms.get(k) is None]
    return parsed


def days_until(iso: Optional[str], today: Optional[date] = None) -> Optional[int]:
    if not iso:
        return None
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return (date(y, m, d) - (today or date.today())).days
    except ValueError:
        return None
