"""Risk Aggregator: one honest verdict from every signal, with the reasons attached.

Levels: DO_NOT_ENGAGE (looks like a scam or takeover attempt) > HIGH > MEDIUM > LOW.
The weights are visible here and every point in the score maps to a named reason, so the
creator can see and challenge exactly why an offer was rated the way it was.
"""
from typing import Any, Dict, List

SEV_W = {"HIGH": 40, "MEDIUM": 15, "LOW": 5}
TERM_W = {"HIGH": 20, "MEDIUM": 5, "LOW": 2}
CLAIM_W = {"UNSUBSTANTIATED": 6, "UNSUPPORTED": 6, "SELF_CLAIM": 3}
FATAL_IDS = {"lookalike", "upfront_fee", "odd_payment", "credential_request", "file_link", "young_domain"}


def assess(sender: Dict[str, Any], terms_analysis: Dict[str, Any], claims: List[Dict[str, Any]],
           fit: Dict[str, Any], site: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    reasons: List[Dict[str, Any]] = []
    fatal = False

    for f in sender.get("flags", []):
        w = SEV_W[f["severity"]]
        score += w
        reasons.append({"source": "sender", "points": w, "text": f["title"]})
        if f["severity"] == "HIGH" and f["id"] in FATAL_IDS:
            fatal = True
    for i in terms_analysis.get("issues", []):
        w = TERM_W[i["severity"]]
        score += w
        reasons.append({"source": "terms", "points": w, "text": f"{i['term']}: {i['offered']} ({i['norm']})"})
    for c in claims:
        w = CLAIM_W.get(c["status"], 0)
        if w:
            score += w
            reasons.append({"source": "claims", "points": w, "text": f"{c['status'].lower()}: \"{c['text'][:70]}\""})
    for s in site.get("signals", []):
        if s["level"] == "bad":
            score += 30
            fatal = True
            reasons.append({"source": "site", "points": 30, "text": s["text"]})
        elif s["level"] == "warn":
            score += 4
            reasons.append({"source": "site", "points": 4, "text": s["text"]})
    if not site.get("ok") and not site.get("skipped"):
        score += 10
        reasons.append({"source": "site", "points": 10, "text": "The brand website could not be checked"})
    if fit.get("blocked"):
        score += 50
        reasons.append({"source": "fit", "points": 50, "text": fit["reasons"][0]})

    if fatal:
        level = "DO_NOT_ENGAGE"
    elif score >= 50:
        level = "HIGH"
    elif score >= 20:
        level = "MEDIUM"
    else:
        level = "LOW"

    actions = {
        "DO_NOT_ENGAGE": "Do not reply, click any link, or open any attachment. Report it as phishing. If you want to "
                         "check whether the brand is real, contact it through the official website, never through this email.",
        "HIGH": "Do not accept as written. Decline, or send the counter below and wait for clear answers.",
        "MEDIUM": "Reasonable to pursue, but counter first: get evidence for the flagged claims and fix the terms.",
        "LOW": "Looks clean. You can accept; the checklist below keeps the campaign compliant.",
    }
    reasons.sort(key=lambda r: -r["points"])
    return {"level": level, "score": score, "reasons": reasons, "recommended_action": actions[level]}


def draft_reply(offer: Dict[str, Any], terms_analysis: Dict[str, Any], claims: List[Dict[str, Any]],
                profile: Dict[str, Any], level: str) -> Dict[str, Any]:
    """A counter e-mail. It is only ever a draft: CreatorOS never sends anything on its own."""
    if level == "DO_NOT_ENGAGE":
        return {"send": False, "text": None, "note": "No reply drafted: do not engage with this sender."}
    brand = offer.get("brand") or "your team"
    lines = [f"Hi {brand} team,", "", "Thanks for reaching out. I'm interested, and before I commit I need a few things:", ""]
    n = 1
    for c in claims:
        if c["status"] in ("UNSUBSTANTIATED", "UNSUPPORTED", "SELF_CLAIM"):
            lines.append(f"{n}. Please share the source for \"{c['text'].rstrip('.')}\". I can only say what I can back up, "
                         f"and I'll need to phrase it as my own experience otherwise.")
            n += 1
    for i in terms_analysis.get("issues", []):
        if i["severity"] in ("MEDIUM", "HIGH", "LOW") and i["ask"]:
            lines.append(f"{n}. {i['term'].capitalize()}: {i['ask']}")
            n += 1
    lines.append(f"{n}. Please confirm the paid partnership will be disclosed as required (I'll use YouTube's paid-promotion "
                 f"setting and say it in the video).")
    lines += ["", "Happy to move quickly once these are settled.", "", f"{profile.get('name', 'Creator')}"]
    return {"send": False, "text": "\n".join(lines), "note": "Draft only. Review and send it yourself."}
