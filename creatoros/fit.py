"""Fit Analyst: does this brand belong on this creator's channel?

Keyword categories over the brand's own site text plus the offer. Deliberately simple and
transparent; the creator's never-promote list lives in Creator Memory. Patterns are word-bounded so
'api' does not match 'capital' and 'ai' does not match 'aim'.
"""
import re
from typing import Any, Dict, List

CATEGORIES: Dict[str, List[str]] = {
    "developer tools": [r"\bdevelopers?\b", r"\bcoding\b", r"\bcode editor\b", r"\bapis?\b", r"\bsdk\b", r"\bgithub\b",
                        r"\bdeploy\w*", r"\bgit repository\b", r"\bvs code\b"],
    "ai": [r"\bai\b", r"\bartificial intelligence\b", r"\bllm\b", r"\bcopilot\b", r"\bmachine learning\b"],
    "cloud": [r"\bcloud\b", r"\bhosting\b", r"\bservers?\b", r"\bdata cent(?:er|re)s?\b"],
    "laptops": [r"\blaptops?\b", r"\bnotebook pc\b", r"\bultrabook\b"],
    "gambling": [r"\bcasino\b", r"\bbetting\b", r"\bsportsbook\b", r"\bpoker\b", r"\bslot machines?\b", r"\bgambl\w*"],
    "supplements": [r"\bsupplements?\b", r"\bnootropics?\b", r"\bfat burner\b", r"\bdetox tea\b"],
    "crypto": [r"\bcrypto(?:currency)?\b", r"\bbitcoin\b", r"\bairdrop\b", r"\bnft\b"],
    "loans": [r"\bpayday loans?\b", r"\bpersonal loans?\b", r"\bcredit card offers?\b", r"\bforex\b"],
    "adult": [r"\badult content\b", r"\bporn\w*", r"\bescorts?\b"],
}


def analyze_fit(site_facts: List[Dict[str, Any]], offer_text: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    text = (" ".join(f["text"] for f in site_facts) + " " + (offer_text or "")).lower()
    found = [c for c, pats in CATEGORIES.items() if any(re.search(p, text) for p in pats)]
    never = [c for c in profile.get("never_promote", []) if c in found]
    preferred = [c for c in profile.get("preferred_categories", []) if c in found]
    reasons: List[str] = []
    score = 50
    if never:
        # A never-promote hit is absolute. Letting a preferred-category bonus add points back on top
        # of it published a score of 50 next to the label "blocked", which reads as a contradiction.
        score = 0
        reasons.append(f"Category on your never-promote list: {', '.join(never)}")
    elif preferred:
        score = min(100, score + 20 * len(preferred[:2]) + 10)
        reasons.append(f"Matches your preferred categories: {', '.join(preferred)}")
    if not found:
        reasons.append("Could not tell what category this brand is in. Check manually.")
    label = "blocked" if never else ("good" if score >= 70 else "unclear")
    return {"score": score, "categories": found, "blocked": bool(never), "label": label, "reasons": reasons}
