"""Claim Verifier: check what the brand wants the creator to say against what the brand's own site says.

Statuses (kept deliberately conservative, and always explained):
  SUPPORTED           every number and the wording is backed by a fact captured from the brand's site
  SELF_CLAIM          the site makes the same superlative/multiplier claim but shows no evidence for it
  SITE_CITES_EVIDENCE the site makes it AND the same statement points at a study/benchmark/report
  UNSUPPORTED         a number or statement that does not appear on the site
  UNSUBSTANTIATED     a superlative or multiplier ("fastest", "2x", "doubles") the site does not even make

The numeric guard builds on Veridemo Watch's `verify_claim` (vendored in truth_set.py), with numbers compared
by value (so "$19.00" matches "19" and "50,000" matches "50000"). We never claim a statement is *true*, only
whether the brand's own published material supports it.
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from .truth_set import verify_claim

CLAIM_CUES = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:x|×|%)|\b(?:faster|fastest|best|#1|number one|leading|only|guarantee[ds]?|proven|saves?|"
    r"reduc\w+|increas\w+|improv\w+|doubl\w+|tripl\w+|trusted by|used by|award\w*|top[- ]rated|unlimited|instant\w*|"
    r"secure|private|free|supports?|works? (?:in|with)|explains?|deploy\w*|plan is|per month|regions?)\b", re.I)
SUPERLATIVE = re.compile(
    r"(?<![\w#])(?:fastest|best|#1|number one|leading|only|guarantee[ds]?|proven|top[- ]rated|doubl\w+|tripl\w+|most \w+)(?!\w)"
    r"|(?<![\w.])\d+(?:\.\d+)?\s?(?:x|×)(?!\w)", re.I)
EVIDENCE_CUE = re.compile(r"\b(?:study|benchmark|report|methodology|case study|survey|n\s?=\s?\d+|according to|audited|"
                          r"certified|SOC ?2|ISO ?27001)\b", re.I)
_NOT_A_CLAIM = re.compile(
    r"(?i)\b(?:payment|usage rights|exclusiv\w*|deadline|please|reply|record and|publish|offer:|integration in|"
    r"we'd love|we would like|thanks|regards|talking points|net \d+|fee)\b")
STOP = set("the a an and or of to in on for with is are it its it's this that these those be as at by from your you our we "
           "can will has have had was were their they them which who what how also just than then into over more most "
           "very much any all been being one".split())
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PLAN_SUBJECT = re.compile(r"(?i)^(?:it|its|it's)\b|^the [\w-]+ (?:plan|tier|package|edition)\b")
_SECONDARY_PAGE = re.compile(r"about|pricing|price|plans|privacy|terms|security|contact|careers", re.I)
_TOPIC_MAX_WORDS = 8


def _words(text: str, exclude: Set[str]) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9#+][a-z0-9#+\-]*", text.lower())
            if w not in STOP and w not in exclude and len(w) > 1]


def _brand_tokens(brand: Optional[str]) -> Set[str]:
    return {t.lower() for t in re.findall(r"\w+", brand or "")}


def _values(text: str) -> Set[float]:
    out: Set[float] = set()
    for n in _NUM.findall(text or ""):
        try:
            out.add(float(n.replace(",", "")))
        except ValueError:
            pass
    return out


def unsupported_numbers(claim: str, cited: Iterable[Dict[str, Any]]) -> List[str]:
    """Numbers in `claim` that no cited fact contains (compared by value, not by spelling)."""
    cited = list(cited)
    guard = verify_claim(claim, cited)                       # string-level guard from Veridemo Watch
    if not guard["unsupported_numbers"]:
        return []
    have: Set[float] = set()
    for f in cited:
        have |= _values(f.get("text", ""))
    return [n for n in guard["unsupported_numbers"] if _values(n) and not (_values(n) <= have)]


def lexical_support(text: str, fact_text: Any, brand: str = "", extra_stop: Iterable[str] = ()) -> float:
    """Share of the claim's content words found in the cited fact(s) (0..1). `fact_text` may be one string or several."""
    bt = _brand_tokens(brand) | set(extra_stop)
    cw = set(_words(text, bt))
    if not cw:
        return 1.0
    texts = [fact_text] if isinstance(fact_text, str) else list(fact_text)
    have: Set[str] = set()
    for t in texts:
        have |= set(_words(t, bt))
    return len(cw & have) / len(cw)


def extract_claims(body: str, brand: str, talking_points: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Sentences (and talking points) that read as product claims."""
    brand_tokens = _brand_tokens(brand)
    out: List[Dict[str, str]] = []
    seen = set()

    def add(text: str, source: str) -> None:
        t = re.sub(r"\s+", " ", text).strip(" .;")
        if len(t) < 8 or t.lower() in seen:
            return
        seen.add(t.lower())
        out.append({"text": t, "source": source})

    for tp in talking_points or []:
        add(tp, "talking_point")

    flat = re.sub(r"\n\s*[-•*]\s+.*", "", body)          # bullet lines are handled as talking points
    for s in re.split(r"(?<=[.!?])\s+|\n+", flat):
        for part in re.split(r",\s+and\s+(?=(?:it|the|we|our|they)\b)|;\s+", s, flags=re.I):
            p = part.strip()
            if not p or _NOT_A_CLAIM.search(p):
                continue
            about_product = bool(brand_tokens & set(re.findall(r"\w+", p.lower()))) or bool(_PLAN_SUBJECT.match(p))
            if about_product and CLAIM_CUES.search(p):
                add(p, "offer_text")
    return out


def _match_facts(claim: str, facts: List[Dict[str, Any]], brand_tokens: Set[str], k: int = 3) -> List[Dict[str, Any]]:
    cw = set(_words(claim, brand_tokens))
    scored = []
    for f in facts:
        fw = set(_words(f.get("text", ""), brand_tokens))
        ov = cw & fw
        if ov:
            scored.append((len(ov) / (len(fw) ** 0.25 + 1), len(ov), f))
    scored.sort(key=lambda t: (-t[1], -t[0]))
    return [f for _, _, f in scored[:k]]


def _topic(facts: List[Dict[str, Any]]) -> str:
    """What the product does, from the homepage headline (not the About/Pricing page headings)."""
    h1s = [f for f in facts if f.get("tag") == "h1"]
    home = [f for f in h1s if not _SECONDARY_PAGE.search(f.get("url", "").rsplit("/", 1)[-1])]
    for f in home or h1s:
        t = f["text"]
        t = t.split(":", 1)[1].strip() if ":" in t else t
        return t if len(t.split()) <= _TOPIC_MAX_WORDS else "this kind of work"
    return "this kind of work"


def safe_rewrite(claim: str, status: str, brand: str, topic: str) -> Optional[Dict[str, Any]]:
    """Honest alternative wording for a claim that could not be verified (never applied without approval)."""
    if status in ("SUPPORTED", "SITE_CITES_EVIDENCE"):
        return None
    if status == "SELF_CLAIM":
        return {"action": "attribute", "requires_personal_use": False,
                "text": f"{brand} says: \"{claim.rstrip('.')}\".",
                "note": "Attribute it to the brand instead of stating it as fact."}
    if re.search(r"(?i)(?<![\w#])(fastest|best|#1|number one|leading|top[- ]rated|only)(?!\w)", claim):
        return {"action": "rewrite", "requires_personal_use": True,
                "text": f"{brand} is one of the tools I've tried for {topic}. [Add your own concrete result here]",
                "note": "A superlative needs comparative evidence. Only say what you personally saw."}
    if SUPERLATIVE.search(claim):
        return {"action": "rewrite", "requires_personal_use": False,
                "text": f"{brand} is designed to help with {topic}. Your results may vary.",
                "note": "The multiplier/percentage has no source. Drop the number."}
    if _NUM.search(claim):
        return {"action": "ask_brand", "requires_personal_use": False, "text": None,
                "note": "Ask the brand for the source of this number before quoting it, or leave it out."}
    return {"action": "ask_brand", "requires_personal_use": False, "text": None,
            "note": "Not found on the brand's site. Ask for proof or leave it out."}


def verify_claims(claims: List[Dict[str, str]], facts: List[Dict[str, Any]], brand: str) -> List[Dict[str, Any]]:
    brand_tokens = _brand_tokens(brand)
    topic = _topic(facts)
    results = []
    for c in claims:
        text = c["text"]
        cited = _match_facts(text, facts, brand_tokens)
        cw = set(_words(text, brand_tokens))
        cited_words: Set[str] = set()
        for f in cited:
            cited_words |= set(_words(f["text"], brand_tokens))
        ratio = (len(cw & cited_words) / len(cw)) if cw else 0.0
        bad_numbers = unsupported_numbers(text, cited)
        sups = [m.group(0) for m in SUPERLATIVE.finditer(text)]

        if sups:
            # Does the site make THIS claim? A fact must contain the same superlative AND share topic words
            # with the claim (a "fastest support" line elsewhere must not count as support for "fastest tool").
            sup_words = set(_words(" ".join(sups), brand_tokens))
            topic_words = cw - sup_words
            repeating = [f for f in facts
                         if any(re.search(r"(?<![\w#.])" + re.escape(s.lower()) + r"(?!\w)", f["text"].lower()) for s in sups)
                         and (not topic_words or topic_words & set(_words(f["text"], brand_tokens)))]
            if repeating:
                lexical, cited = cited, repeating[:3]
                # The site repeating a superlative says NOTHING about a number in the same sentence.
                # Without this re-check, "the fastest way to deploy, for $9 a month" was filed as a
                # SELF_CLAIM against a site that says $25, and the suggested rewrite then quoted the
                # $9 straight back to the audience. An unsupported number outranks the superlative.
                # Numbers are checked against BOTH fact sets: the superlative usually lives on the
                # homepage while the figure it is bundled with lives on the pricing page, and checking
                # only the superlative's own fact would flag a number the site really does publish.
                bad_numbers = unsupported_numbers(text, cited + [f for f in lexical if f not in cited])
                if bad_numbers:
                    status = "UNSUPPORTED"
                    reason = (f"The site makes this claim, but these numbers in it are not on the site: "
                              f"{', '.join(bad_numbers)}.")
                else:
                    has_ev = any(EVIDENCE_CUE.search(f["text"]) for f in repeating)
                    status = "SITE_CITES_EVIDENCE" if has_ev else "SELF_CLAIM"
                    reason = ("The site makes this claim and points at evidence. Check that source before quoting."
                              if has_ev else "The site makes this claim but shows no study, benchmark or source.")
            else:
                status = "UNSUBSTANTIATED"
                reason = "A superlative/multiplier that the brand's own site does not even make."
        elif bad_numbers:
            status = "UNSUPPORTED"
            reason = f"Numbers not found on the brand's site: {', '.join(bad_numbers)}."
        elif cited and ratio >= 0.5:
            status = "SUPPORTED"
            reason = "Backed by the brand's own published page."
        else:
            status = "UNSUPPORTED"
            reason = "Not found on the brand's site."

        results.append({
            "text": text, "source": c["source"], "status": status, "reason": reason,
            "support_ratio": round(ratio, 2),
            "evidence": [{"fact_id": f["id"], "text": f["text"], "url": f["url"]} for f in cited]
                        if status in ("SUPPORTED", "SITE_CITES_EVIDENCE", "SELF_CLAIM") else [],
            "rewrite": safe_rewrite(text, status, brand or "the brand", topic),
        })
    return results
