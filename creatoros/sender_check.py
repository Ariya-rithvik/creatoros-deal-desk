"""Sender Verifier: explainable red-flag rules for sponsorship offers.

Every flag carries the evidence snippet that triggered it, so the creator can see *why*
and disagree. Nothing here is a black-box score. Rules follow the patterns documented for
fake-sponsorship scams: look-alike domains, free-mail senders, up-front fees, publish-first
payment, file-share / shortener links, credential requests.
"""
import re
from typing import Any, Dict, List, Optional

from .util import (deconfuse, email_domain, find_urls, host_of, levenshtein,
                   registrable_domain)

FREEMAIL = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "proton.me",
            "protonmail.com", "icloud.com", "aol.com", "mail.com", "gmx.com"}

# Official domains of brands scammers commonly impersonate. lumencloud.com is the fictional
# demo brand; the rest are real, well-known creator-sponsor brands used only for detection.
KNOWN_BRANDS: Dict[str, List[str]] = {
    "lumencloud": ["lumencloud.com"],
    "nordvpn": ["nordvpn.com"], "surfshark": ["surfshark.com"], "expressvpn": ["expressvpn.com"],
    "skillshare": ["skillshare.com"], "audible": ["audible.com"], "squarespace": ["squarespace.com"],
    "shopify": ["shopify.com"], "notion": ["notion.so", "notion.com"], "canva": ["canva.com"],
    "grammarly": ["grammarly.com"], "descript": ["descript.com"], "coursera": ["coursera.org"],
    "dropbox": ["dropbox.com"], "1password": ["1password.com"], "bitwarden": ["bitwarden.com"],
    "paypal": ["paypal.com"], "wix": ["wix.com"], "hostinger": ["hostinger.com"],
    "godaddy": ["godaddy.com"], "namecheap": ["namecheap.com"], "elevenlabs": ["elevenlabs.io"],
    "cursor": ["cursor.com"], "github": ["github.com"], "figma": ["figma.com"], "youtube": ["youtube.com"],
}
_ALL_OFFICIAL = {d for ds in KNOWN_BRANDS.values() for d in ds}

# Words scammers bolt onto a real brand name ("skillshare-creators.com").
_IMPERSONATION_TOKENS = {"creator", "creators", "partner", "partners", "partnership", "partnerships", "sponsor",
                         "sponsors", "sponsorship", "official", "team", "deals", "deal", "ads", "promo", "collab",
                         "brand", "brands", "marketing", "affiliate", "affiliates", "program", "hub", "studio"}

SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "rb.gy", "shorturl.at", "ow.ly", "goo.gl"}
FILE_SHARE = {"mega.nz", "drive.google.com", "dropbox.com", "wetransfer.com", "mediafire.com", "1drv.ms", "sendspace.com"}
DANGEROUS_EXT = re.compile(r"\.(zip|rar|7z|exe|scr|msi|iso|lnk|bat|apk|dmg)(?:\b|$)", re.I)

P_FEE = re.compile(r"(?:verification|processing|activation|registration|tax|shipping|unlock)\s+fee"
                   r"|refundable (?:deposit|fee)"
                   r"|pay (?:a|an|the)?\s?(?:one[- ]time )?\$?\d+[^.\n]{0,40}\bfee", re.I)
P_GIFTCARD = re.compile(r"gift ?cards?|crypto(?:currency)?|bitcoin|usdt|wire transfer|western union|zelle", re.I)
P_CREDS_STRONG = re.compile(
    r"sign in with google|log ?in to verify|verify your (?:channel|account|identity)"
    r"|(?:send|share|give|provide|enter|reply with)\s+(?:us\s+)?(?:your|the)\s+(?:channel\s+|account\s+|google\s+)?"
    r"(?:password|otp|2fa(?: code)?|verification code|authenticator code)", re.I)
P_SIGNIN_WEAK = re.compile(r"sign in (?:at|to)\b", re.I)      # brands do ask creators to sign in to affiliate dashboards
P_PUBLISH_FIRST = re.compile(
    r"(?:publish|post|record|upload)[^.\n]{0,60}\bfirst\b"
    r"|payment (?:is )?(?:sent|made|released) after (?:the )?(?:video|content|post|it)[^.\n]{0,20}(?:is )?(?:live|published|posted)"
    r"|pa(?:y|id|yment)\b[^.\n]{0,40}\bafter\b[^.\n]{0,20}\b(?:posting|publication|publishing)", re.I)
P_URGENT = re.compile(r"urgent|within \d+ ?hours?|limited time|slots? (?:close|are limited)|respond (?:fast|immediately|asap)"
                      r"|act now|don'?t lose", re.I)
P_CONTRACT = re.compile(r"written contract|signed (?:contract|agreement)|per the (?:signed )?agreement", re.I)


def _flag(fid: str, severity: str, title: str, why: str, evidence: str) -> Dict[str, Any]:
    return {"id": fid, "severity": severity, "title": title, "why": why, "evidence": evidence.strip()[:200]}


def _snippet(text: str, m: "re.Match") -> str:
    a, b = max(0, m.start() - 40), min(len(text), m.end() + 60)
    return re.sub(r"\s+", " ", text[a:b])


def _imitates(brand: str, labels: set) -> bool:
    """True if a sender-domain label is the brand plus scam decoration, or a near-miss spelling of it.

    Deliberately NOT a substring test: 'canvasplus.io' must not be flagged as imitating 'canva'.
    """
    for label in labels:
        parts = [p for p in re.split(r"[-_.]", label) if p]
        core = "".join(p for p in parts if p not in _IMPERSONATION_TOKENS)
        for c in {label, core, *parts}:
            if not c:
                continue
            if c == brand:
                return True
            if len(c) >= 6 and levenshtein(c, brand) <= (1 if len(c) < 9 else 2):
                return True
    return False


def check_sender(sender: str, body: str, website_url: Optional[str] = None,
                 domain_age_days: Optional[int] = None) -> Dict[str, Any]:
    """Return {flags, sender_domain, verified_brand_domain, notes}."""
    text = body or ""
    flags: List[Dict[str, Any]] = []
    notes: List[str] = []
    sdom_raw = email_domain(sender or "") or ""
    sdom = sdom_raw.lower()
    s_reg = registrable_domain(sdom)
    display = (sender or "").split("<", 1)[0] if "<" in (sender or "") else ""
    verified_official: Optional[str] = s_reg if s_reg in _ALL_OFFICIAL else None

    # 1. free-mail sender
    if s_reg in FREEMAIL:
        flags.append(_flag("freemail", "MEDIUM", "Sent from a free e-mail address",
                           "Real brand partnerships almost always come from a company domain.", sender))

    # 2. look-alike of a known brand (skipped when the sender IS an official domain)
    if sdom_raw and not verified_official:
        base = registrable_domain(deconfuse(sdom_raw)).split(".")[0]
        labels = {base, base.replace("1", "l"), base.replace("1", "i"), registrable_domain(sdom).split(".")[0]}
        for brand, officials in KNOWN_BRANDS.items():
            if _imitates(brand, labels):
                flags.append(_flag("lookalike", "HIGH", f"Domain imitates {brand}",
                                   f"'{sdom_raw}' is not an official {brand} domain "
                                   f"(official: {', '.join(officials)}) but looks like one.", sender))
                break

    # 2b. display name claims a known brand but the domain is not official
    if display and not verified_official and not any(f["id"] == "lookalike" for f in flags):
        for brand in KNOWN_BRANDS:
            if re.search(r"(?<![\w])" + re.escape(brand) + r"(?![\w])", display, re.I):
                flags.append(_flag("display_name", "MEDIUM", f"Display name says '{brand}' but the domain is not theirs",
                                   f"The sender name mentions {brand}; the address is @{s_reg}.", sender))
                break

    # 3. website vs sender mismatch
    if website_url:
        w_reg = registrable_domain(host_of(website_url))
        if sdom and s_reg not in FREEMAIL and w_reg and s_reg != w_reg:
            flags.append(_flag("domain_mismatch", "MEDIUM", "Sender domain differs from the brand website",
                               f"Email is from {s_reg} but the offer points to {w_reg}.", f"{sender} vs {website_url}"))

    # 4. money-related red flags
    for m in P_FEE.finditer(text):
        flags.append(_flag("upfront_fee", "HIGH", "Asks the creator to pay a fee",
                           "Legitimate sponsors pay creators; they do not charge verification, tax or activation fees.",
                           _snippet(text, m)))
        break
    for m in P_GIFTCARD.finditer(text):
        flags.append(_flag("odd_payment", "HIGH", "Gift-card / crypto / wire payment mentioned",
                           "Gift cards and crypto are the standard scam payment rails.", _snippet(text, m)))
        break
    if not P_CONTRACT.search(text):
        for m in P_PUBLISH_FIRST.finditer(text):
            flags.append(_flag("publish_first", "MEDIUM", "Video must go live before payment, with no contract",
                               "If the brand disappears after publication you have no recourse. Ask for a written "
                               "contract (and a deposit) first.", _snippet(text, m)))
            break

    # 5. credentials / verification requests
    m = P_CREDS_STRONG.search(text)
    if m:
        flags.append(_flag("credential_request", "HIGH", "Asks you to sign in or 'verify your channel'",
                           "Sponsor offers never need your channel or Google login. This is the account-takeover pattern.",
                           _snippet(text, m)))
    else:
        m = P_SIGNIN_WEAK.search(text)
        if m and not verified_official:
            flags.append(_flag("signin_request", "MEDIUM", "Asks you to sign in somewhere",
                               "Sign-in requests from an unverified sender deserve a check; from an official brand domain they "
                               "are normal (affiliate dashboards).", _snippet(text, m)))

    # 6. links
    seen_link = set()
    for u in find_urls(text):
        reg = registrable_domain(host_of(u))
        if reg in SHORTENERS and "shortener" not in seen_link:
            seen_link.add("shortener")
            flags.append(_flag("shortener", "MEDIUM", "Shortened link hides the real destination",
                               "Ask for the full URL.", u))
        if (reg in FILE_SHARE or DANGEROUS_EXT.search(u)) and "fileshare" not in seen_link:
            seen_link.add("fileshare")
            sev = "HIGH" if DANGEROUS_EXT.search(u) else "MEDIUM"
            flags.append(_flag("file_link", sev, "Brief delivered as a file-share link or archive",
                               "Archives and executables in 'creator kits' are a common malware vector. Do not open them.", u))

    # 7. urgency
    m = P_URGENT.search(text)
    if m:
        flags.append(_flag("urgency", "LOW", "Pressure to reply quickly",
                           "Urgency is used to stop you from checking the offer.", _snippet(text, m)))

    # 8. domain age (optional, supplied by caller)
    if domain_age_days is not None:
        if domain_age_days < 90:
            flags.append(_flag("young_domain", "HIGH", f"Brand domain is only {domain_age_days} days old",
                               "Very new domains are common in impersonation campaigns.", sdom))
        elif domain_age_days < 365:
            flags.append(_flag("young_domain", "LOW", f"Brand domain is under a year old ({domain_age_days} days)",
                               "Worth a second look, not proof of a problem.", sdom))
    else:
        notes.append("Domain age not checked (offline or lookup failed).")

    if verified_official:
        notes.append(f"Sender domain {verified_official} matches a known official domain.")
    return {"flags": flags, "sender_domain": sdom, "verified_brand_domain": verified_official, "notes": notes}


def rdap_age_days(domain: str, timeout: float = 5.0) -> Optional[int]:
    """Domain age in days via public RDAP, or None if unavailable."""
    try:
        import httpx
        from datetime import datetime, timezone
        r = httpx.get(f"https://rdap.org/domain/{domain}", timeout=timeout, follow_redirects=True)
        if r.status_code != 200:
            return None
        for ev in r.json().get("events", []):
            if ev.get("eventAction") == "registration":
                dt = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                return (datetime.now(timezone.utc) - dt).days
    except Exception:                                 # noqa: BLE001 - age is best-effort
        return None
    return None
