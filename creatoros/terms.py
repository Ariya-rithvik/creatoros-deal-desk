"""Terms Analyst: compare the offer's commercial terms with the creator's own norms.

The creator's norms live in Creator Memory (profile.norms), not in the code, so the same engine
protects a creator who accepts 6-month exclusivity and one who never does.
"""
from typing import Any, Dict, List


def _issue(term: str, severity: str, offered: str, norm: str, ask: str) -> Dict[str, str]:
    return {"term": term, "severity": severity, "offered": offered, "norm": norm, "ask": ask}


def analyze_terms(terms: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    norms = profile.get("norms", {})
    issues: List[Dict[str, str]] = []
    ok: List[str] = []

    # exclusivity
    ex, max_ex = terms.get("exclusivity_days"), norms.get("max_exclusivity_days")
    if ex is None:
        issues.append(_issue("exclusivity", "LOW", "not stated", "ask", "Confirm in writing whether any exclusivity applies."))
    elif max_ex is not None and ex > max_ex:
        issues.append(_issue("exclusivity", "MEDIUM", f"{ex} days", f"your limit is {max_ex} days",
                             f"Reduce exclusivity to {max_ex} days, or price it in (longer exclusivity should pay more)."))
    else:
        ok.append(f"Exclusivity: {'none' if ex == 0 else f'{ex} days'} (within your limit)")

    # payment terms
    net, max_net = terms.get("net_days"), norms.get("max_net_days")
    if net is None:
        issues.append(_issue("payment terms", "LOW", "not stated", "ask", "Get the payment date and method in writing."))
    elif max_net is not None and net > max_net:
        issues.append(_issue("payment terms", "MEDIUM", f"Net {net}", f"your limit is Net {max_net}",
                             f"Ask for Net {max_net}, or a 50% deposit on signing."))
    else:
        ok.append(f"Payment: Net {net} (within your limit)")

    # usage rights
    us, max_us = terms.get("usage_days"), norms.get("max_usage_days")
    if terms.get("usage_perpetual"):
        issues.append(_issue("usage rights", "HIGH", "perpetual / unlimited", f"your limit is {max_us} days",
                             "Never grant perpetual rights for a flat fee. Cap it and charge for extensions."))
    elif us is None:
        issues.append(_issue("usage rights", "LOW", "not stated", "ask", "Ask what the brand may do with the video after publishing."))
    elif max_us is not None and us > max_us:
        issues.append(_issue("usage rights", "MEDIUM", f"{us} days", f"your limit is {max_us} days",
                             f"Limit usage rights to {max_us} days, then license on request."))
    else:
        ok.append(f"Usage rights: {us} days (within your limit)")

    # fee vs rate card
    amt, cur, dur = terms.get("amount"), terms.get("currency"), terms.get("duration_seconds")
    rate60 = (norms.get("rate_card_usd") or {}).get("integration_60s")
    if amt is None:
        issues.append(_issue("fee", "MEDIUM", "not stated", "ask", "No fee is stated. Get the amount before doing any work."))
    elif cur == "USD" and rate60:
        expected = rate60 * (dur / 60.0) if dur else rate60
        if amt < 0.7 * expected:
            issues.append(_issue("fee", "MEDIUM", f"${amt:,.0f}", f"your rate is about ${expected:,.0f}",
                                 f"Counter at ${expected:,.0f}."))
        else:
            ok.append(f"Fee ${amt:,.0f} is at or above your rate (about ${expected:,.0f})")
    elif rate60:
        # Silently skipping this left a creator paid in INR or EUR with NO fee analysis and no
        # explanation, which reads as approval. Say that the comparison was not made.
        issues.append(_issue("fee", "LOW", f"{cur or 'unknown currency'} {amt:,.0f}", "your rate card is in USD",
                             f"This offer is not in USD, so it was not compared with your rate card "
                             f"(about ${rate60:,.0f} per 60s). Convert it and check the fee yourself."))

    # contract / who pays first
    if terms.get("contract_declined"):
        issues.append(_issue("contract", "HIGH", "the offer says no contract is needed", "written contract first",
                             "An offer that volunteers that there is no contract is giving you no recourse. "
                             "Ask for a written agreement before you record anything, or decline."))
    elif terms.get("pay_after_publication") and not terms.get("has_contract"):
        issues.append(_issue("contract", "MEDIUM", "payment only after publication, no contract", "written contract first",
                             "Ask for a written contract and a deposit before you record anything."))
    elif terms.get("has_contract"):
        ok.append("A written contract is mentioned")

    # length vs the creator's usual integration
    lo_hi = norms.get("integration_seconds")
    if dur and lo_hi and not (lo_hi[0] <= dur <= lo_hi[1]):
        issues.append(_issue("length", "LOW", f"{dur}s", f"your usual integration is {lo_hi[0]}-{lo_hi[1]}s",
                             f"Propose {lo_hi[1]}s so it fits your usual pacing."))
    return {"issues": issues, "ok": ok}
