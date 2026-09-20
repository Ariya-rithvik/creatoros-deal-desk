"""Campaign Agent: turn an accepted offer into a workspace with a compliance checklist.

Only claims that were verified against the brand's own site enter the approved list. Everything
else is held back with the reason, so a creator cannot accidentally repeat a brand's unproven claim.
"""
from typing import Any, Dict, List

from .offer_parser import days_until


def build_campaign(offer: Dict[str, Any], claims: List[Dict[str, Any]], profile: Dict[str, Any]) -> Dict[str, Any]:
    parsed = offer["parsed"]
    t = parsed["terms"]
    approved = [c for c in claims if c["status"] in ("SUPPORTED", "SITE_CITES_EVIDENCE")]
    attributed = [c for c in claims if c["status"] == "SELF_CLAIM"]
    blocked = [c for c in claims if c["status"] in ("UNSUBSTANTIATED", "UNSUPPORTED")]
    left = days_until(t.get("deadline"))

    checklist = [
        {"id": "yt_flag", "text": "Turn on YouTube's 'Includes paid promotion' setting when you upload.", "done": False},
        {"id": "spoken", "text": "Say the paid relationship out loud at the start of the sponsored segment and show it on screen.", "done": False},
        {"id": "desc", "text": "Put a plain disclosure at the top of the description (above the 'show more' fold).", "done": False},
        {"id": "claims", "text": "Use only the approved claims below. Anything held back needs the brand's evidence or your own honest rewrite.", "done": False},
        {"id": "terms", "text": "Get the fee, payment date, usage rights and exclusivity in writing before you record.", "done": False},
    ]
    if parsed.get("promo_code"):
        checklist.append({"id": "promo", "text": f"Mention code {parsed['promo_code']} and say if you earn a commission on it.", "done": False})

    questions: List[str] = []
    for c in blocked:
        questions.append(f"Source for: \"{c['text']}\"")
    for k in parsed.get("missing", []):
        questions.append(f"Not stated in the offer: {k.replace('_', ' ')}")

    return {
        "brand": parsed.get("brand"),
        "website": parsed.get("website"),
        "deliverable": t.get("deliverable"),
        "fee": (f"{(t.get('currency') or '').strip()} {t['amount']:,.0f}".strip() if t.get("amount") else None),
        "deadline": t.get("deadline"),
        "days_left": left,
        "cta": parsed.get("cta") or profile.get("typical_cta"),
        "promo_code": parsed.get("promo_code"),
        "discount_percent": parsed.get("discount_percent"),
        "talking_points": parsed.get("talking_points", []),
        "approved_claims": [{"text": c["text"], "evidence": c["evidence"]} for c in approved],
        "attribute_only": [{"text": c["text"], "rewrite": c["rewrite"]} for c in attributed],
        "held_back": [{"text": c["text"], "status": c["status"], "reason": c["reason"], "rewrite": c["rewrite"]} for c in blocked],
        "disclosure_checklist": checklist,
        "open_questions": questions,
        "note": "Not legal advice. The FTC Endorsement Guides apply to US audiences; check local rules "
                "(for example ASCI guidelines in India) for yours.",
    }
