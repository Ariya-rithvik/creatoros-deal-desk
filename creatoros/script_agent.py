"""Script Agent: draft the sponsor segment in the creator's voice, from verified claims only.

Invariants (enforced by `check_script` and by tests):
  * every factual line cites a fact captured from the brand's own site and passes the numeric guard
  * the creator's personal experience is NEVER invented: it is a visible placeholder to fill in
  * the paid-relationship disclosure comes before any claim
  * claims that failed verification are excluded unless the creator explicitly approved a rewrite
"""
import re
from typing import Any, Dict, List, Optional

from .claims import lexical_support, unsupported_numbers

WPS = 2.6                     # spoken words per second (about 155 wpm)
_IMPERATIVE = {"deploy", "get", "use", "try", "build", "ship", "start", "write", "run", "connect"}


def _spoken(claim: str) -> str:
    c = claim.strip().rstrip(".")
    first = c.split(" ", 1)[0].lower()
    if first in _IMPERATIVE:
        return f"You can {c[0].lower() + c[1:]}."
    if re.match(r"(?i)^(explains|works|supports|completes|includes|offers|gives|lets|runs|handles)\b", c):
        return f"It {c[0].lower() + c[1:]}."
    return c[0].upper() + c[1:] + "."


def _words(s: str) -> int:
    return len(re.findall(r"\S+", s))


_GLUE = {"plan", "tier", "package", "edition"}      # words that name a price line without being facts themselves


def _facts_for(claim: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"fact_id": e["fact_id"], "url": e["url"], "fact_text": e["text"]} for e in (claim.get("evidence") or [])]


def line_supported(text: str, facts: List[Dict[str, Any]], brand: str = "") -> bool:
    """A spoken claim is allowed only if every number AND every content word comes from the cited facts."""
    texts = [f["fact_text"] for f in facts]
    cited = [{"id": f["fact_id"], "text": f["fact_text"]} for f in facts]
    return (bool(facts) and not unsupported_numbers(text, cited)
            and lexical_support(text, texts, brand, _GLUE) >= 0.999)


def build_script(campaign: Dict[str, Any], claims: List[Dict[str, Any]], profile: Dict[str, Any],
                 approved_rewrites: Optional[List[int]] = None) -> Dict[str, Any]:
    brand = campaign.get("brand") or "the sponsor"
    lo, hi = (profile.get("norms", {}).get("integration_seconds") or [35, 55])
    offered = None
    try:
        offered = int(str(campaign.get("deliverable") or "").split("-")[0])
    except ValueError:
        pass
    target = min(max(offered or hi, lo), hi)
    budget = int(target * WPS)
    phrases = profile.get("signature_phrases") or ["okay so here's the thing"]

    lines: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def add(kind: str, text: str, source=None, needs_approval=False, placeholder=False, action=None):
        lines.append({"kind": kind, "text": text, "source": source, "action": action,
                      "needs_approval": needs_approval, "placeholder": placeholder})

    # 1. transition + 2. disclosure (always before any claim)
    add("transition", f"{phrases[0].capitalize()}: this part of the video is sponsored by {brand}.")
    add("disclosure", f"That's a paid partnership, so I'll be upfront about it. {brand} is paying me for this segment.")

    # 3. verified claims (talking points first because the brand asked for them)
    ranked = sorted([c for c in claims if c["status"] in ("SUPPORTED", "SITE_CITES_EVIDENCE")],
                    key=lambda c: (c["source"] != "talking_point", -c.get("support_ratio", 0)))
    reserved = sum(_words(l["text"]) for l in lines) + 24 + 14      # placeholder + CTA
    used = reserved
    included = 0
    for c in ranked:
        text = _spoken(c["text"])
        w = _words(text)
        cited = _facts_for(c)
        if not line_supported(text, cited, brand):
            warnings.append(f"Left out a claim whose wording could not be traced to the brand's site: {c['text']}")
            continue
        if used + w > budget:
            continue
        first = cited[0]
        add("claim", text, source={"fact_id": first["fact_id"], "url": first["url"], "fact_text": first["fact_text"],
                                   "facts": cited})
        used += w
        included += 1
    if included == 0:
        warnings.append("No verified claims fit. Check the brand's site or ask them for material to quote.")

    # optional approved rewrites (creator-approved wording for flagged claims)
    held = [c for c in claims if c["status"] in ("UNSUBSTANTIATED", "UNSUPPORTED", "SELF_CLAIM") and c.get("rewrite")
            and c["rewrite"].get("text")]
    for idx in sorted(set(approved_rewrites or [])):
        if 0 <= idx < len(held):
            txt = held[idx]["rewrite"]["text"]
            cited = _facts_for(held[idx])
            # Carry the evidence onto the line so check_script can re-verify it independently.
            src = ({"fact_id": cited[0]["fact_id"], "url": cited[0]["url"],
                    "fact_text": cited[0]["fact_text"], "facts": cited} if cited else None)
            add("rewrite", txt, source=src, placeholder="[" in txt,  # bracketed text is for the creator to fill in
                action=held[idx]["rewrite"].get("action"))
            if held[idx]["rewrite"].get("requires_personal_use"):
                warnings.append(f"Rewrite {idx} contains a personal-experience placeholder you must fill in honestly.")

    # 4. the creator's own experience: never invented
    add("experience", f"[YOUR TAKE: what did you actually try with {brand}? One concrete thing you saw, in your own words.]",
        placeholder=True)

    # 5. CTA
    cta = (campaign.get("cta") or profile.get("typical_cta") or "Link is in the description").strip().rstrip(".!")
    code = f" Use code {campaign['promo_code']}." if campaign.get("promo_code") else ""
    add("cta", f"{cta}.{code}")

    t = 0.0
    for l in lines:
        words = 24 if l["placeholder"] else _words(l["text"])      # the creator's own take is budgeted, not free
        d = max(2.0, words / WPS)
        l["start"], l["end"] = round(t, 1), round(t + d, 1)
        t += d
    return {
        "brand": brand, "target_seconds": target, "estimated_seconds": round(t, 1), "lines": lines,
        "excluded": [{"index": i, "text": c["text"], "status": c["status"], "reason": c["reason"], "rewrite": c["rewrite"]}
                     for i, c in enumerate(held)],
        "warnings": warnings,
        "placement_hint": f"Insert after your problem statement (roughly 35-45% into the video), keeping it to {target}s "
                          f"like your usual integrations ({lo}-{hi}s).",
        "requires_creator_approval": True,
    }


def check_script(script: Dict[str, Any]) -> List[str]:
    """Return invariant violations (empty list means the script is safe to hand to the creator)."""
    problems: List[str] = []
    seen_disclosure = False
    for l in script["lines"]:
        if l["kind"] == "disclosure":
            seen_disclosure = True
        # An "attribute" rewrite quotes the brand's own sentence back to the audience, so it may keep
        # the brand's WORDING - but a figure in it is still a figure the creator says out loud, and
        # the guard used to look only at `claim` lines. Saying 'Brand says "$9 a month"' when the
        # site says $25 is exactly the mistake this tool exists to prevent.
        if l["kind"] == "rewrite" and l.get("action") == "attribute":
            if not seen_disclosure:
                problems.append(f"attributed claim before disclosure: {l['text']}")
            facts = (l.get("source") or {}).get("facts") or []
            bad = unsupported_numbers(l["text"], [{"id": f["fact_id"], "text": f["fact_text"]} for f in facts])
            if bad or not facts:
                problems.append(f"attributed claim states numbers the brand's site does not show: {l['text']}"
                                + (f" (numbers not found: {', '.join(bad)})" if bad else " (no cited fact)"))
        if l["kind"] == "claim":
            if not seen_disclosure:
                problems.append(f"claim before disclosure: {l['text']}")
            src = l.get("source")
            if not src:
                problems.append(f"claim without a source fact: {l['text']}")
                continue
            facts = src.get("facts") or [{"fact_id": src["fact_id"], "url": src.get("url"), "fact_text": src["fact_text"]}]
            if not line_supported(l["text"], facts, script.get("brand", "")):
                bad = unsupported_numbers(l["text"], [{"id": f["fact_id"], "text": f["fact_text"]} for f in facts])
                problems.append(f"claim not supported by its cited facts: {l['text']}"
                                + (f" (numbers not found: {', '.join(bad)})" if bad else " (wording is not supported)"))
    if not any(l["kind"] == "disclosure" for l in script["lines"]):
        problems.append("no disclosure line")
    return problems
