"""Deal Desk orchestrator: offer in -> evidence report -> creator decision -> campaign -> claim-safe script.

Design rules:
  * nothing outward-facing ever happens automatically (no e-mail sent, nothing published)
  * a risky offer can only be accepted with an explicit, recorded override
  * a link from an unsafe sender is NOT opened at all (fetching it can confirm your mailbox is live);
    only our own fictional demo fixtures are read, as plain HTML, so the demo can still show the red flags
  * every step is timed and returned as a trace so the creator sees what each agent did
  * public methods are serialised with a lock: one creator, one desk, no interleaved writes
"""
import hashlib
import threading
import time
from typing import Any, Dict, List, Optional

from . import campaign as campaign_mod
from . import policy, script_agent, site_explorer
from .claims import extract_claims, verify_claims
from .fit import analyze_fit
from .memory import Memory
from .offer_parser import parse_offer
from .risk import FATAL_IDS, assess, draft_reply
from .sender_check import check_sender, rdap_age_days
from .terms import analyze_terms
from .util import host_of, registrable_domain

_SITE_KEYS = ("ok", "url", "mode", "fixture", "pages", "signals", "error", "skipped", "blocked")


class DealDeskError(Exception):
    pass


class DealDesk:
    def __init__(self, memory: Optional[Memory] = None, crawl_mode: str = "auto", check_domain_age: bool = False):
        self.memory = memory or Memory()
        self.crawl_mode = crawl_mode
        self.check_domain_age = check_domain_age
        self._lock = threading.RLock()

    # -- intake ------------------------------------------------------------------------
    def add_offer(self, raw: str, label: Optional[str] = None) -> str:
        with self._lock:
            oid = hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()[:10]
            if not self.memory.get_offer(oid):
                parsed = parse_offer(raw)
                self.memory.put_offer(oid, {"id": oid, "label": label or parsed.get("subject") or "Offer", "raw": raw,
                                            "parsed": parsed, "report": None, "decision": None, "campaign": None,
                                            "script": None})
            return oid

    # -- the check ---------------------------------------------------------------------
    def check(self, offer_id: str) -> Dict[str, Any]:
        """Run every agent. Re-checking clears any earlier decision, campaign and script for this offer
        (the ledger keeps the history), because they were based on the old evidence."""
        with self._lock:
            return self._check(offer_id)

    def _check(self, offer_id: str) -> Dict[str, Any]:
        offer = self._offer(offer_id)
        profile = self.memory.profile
        trace: List[Dict[str, Any]] = []

        def step(agent: str, fn, summarize):
            t0 = time.perf_counter()
            out = fn()
            trace.append({"agent": agent, "ms": round((time.perf_counter() - t0) * 1000), "summary": summarize(out)})
            return out

        parsed = step("Offer Parser", lambda: parse_offer(offer["raw"]),
                      lambda p: f"{p['brand'] or 'unknown brand'} - {p['terms'].get('deliverable') or 'deliverable not stated'} - "
                                f"{p['terms'].get('amount_raw') or 'fee not stated'}")
        offer["parsed"] = parsed

        age = None
        website = parsed.get("website")
        fixture = site_explorer.resolve(website)["fixture"] if website else None
        if self.check_domain_age and website and not fixture:
            age = rdap_age_days(registrable_domain(host_of(website)))
        sender = step("Sender Verifier", lambda: check_sender(parsed["sender"], parsed["body"], website, age),
                      lambda s: f"{len(s['flags'])} red flag(s)" +
                                (f", official domain {s['verified_brand_domain']}" if s["verified_brand_domain"] else ""))
        fatal = any(f["severity"] == "HIGH" and f["id"] in FATAL_IDS for f in sender["flags"])

        def crawl() -> Dict[str, Any]:
            if not website:
                return {"ok": False, "facts": [], "signals": [], "pages": [], "mode": None, "url": None,
                        "fixture": None, "error": "no website in the offer"}
            if fatal and not fixture:
                return {"ok": False, "skipped": True, "facts": [], "signals": [], "pages": [], "mode": None,
                        "url": website, "fixture": None,
                        "error": "Not visited: the sender looks unsafe, so the link was not opened."}
            # unsafe sender + our own demo fixture: read it as plain HTML only, never run scripts
            return site_explorer.crawl(website, mode="static" if fatal else self.crawl_mode)

        def crawl_summary(s: Dict[str, Any]) -> str:
            if s["ok"]:
                return (f"{len(s['pages'])} pages, {len(s['facts'])} facts ({s['mode']}"
                        f"{', HTML only: sender looked unsafe' if fatal else ''})")
            return s.get("error") or "could not check the site"
        site = step("Explorer", crawl, crawl_summary)

        brand = parsed.get("brand") or "the brand"
        claim_texts = extract_claims(parsed["body"], brand, parsed.get("talking_points"))

        def verify() -> List[Dict[str, Any]]:
            if site["ok"]:
                return verify_claims(claim_texts, site["facts"], brand)
            why = "Brand site was not visited" if site.get("skipped") else "Brand site could not be checked"
            return [dict(text=c["text"], source=c["source"], status="UNSUPPORTED", reason=why,
                         support_ratio=0.0, evidence=[], rewrite=None) for c in claim_texts]
        claims = step("Claim Verifier", verify,
                      lambda cs: (f"{len(cs)} claims: " + ", ".join(f"{n} {k.lower()}" for k, n in _count(cs).items()))
                      if cs else "no product claims found")

        terms_analysis = step("Terms Analyst", lambda: analyze_terms(parsed["terms"], profile),
                              lambda t: f"{len(t['issues'])} term(s) outside your norms, {len(t['ok'])} fine")
        fit = step("Fit Analyst",
                   lambda: analyze_fit(site["facts"], parsed["body"], profile) if not fatal else
                   {"score": None, "categories": [], "blocked": False, "label": "not assessed",
                    "reasons": ["Not assessed: the sender looks unsafe, so brand fit is moot."]},
                   lambda f: f"fit {f['label']}" + (f" ({', '.join(f['categories']) or 'category unclear'})"
                                                    if f["label"] != "not assessed" else ""))
        risk = step("Risk Aggregator", lambda: assess(sender, terms_analysis, claims, fit, site),
                    lambda r: f"{r['level']} (score {r['score']})")
        reply = draft_reply(parsed, terms_analysis, claims, profile, risk["level"])

        self.memory.record_trust(brand, website, claims, bool(site["ok"]) and not fatal)
        report = {"offer_id": offer_id, "brand": brand, "sender": sender,
                  "site": {k: site.get(k) for k in _SITE_KEYS}, "site_fact_count": len(site["facts"]),
                  "claims": claims, "terms": parsed["terms"], "terms_analysis": terms_analysis, "fit": fit,
                  "risk": risk, "reply_draft": reply, "trace": trace, "missing": parsed["missing"],
                  "facts": site["facts"] if not fatal else []}
        offer.update(report=report, decision=None, campaign=None, script=None)
        self.memory.put_offer(offer_id, offer)
        return report

    # -- the approval layer ------------------------------------------------------------
    def decide(self, offer_id: str, decision: str, override: bool = False, note: str = "") -> Dict[str, Any]:
        with self._lock:
            offer = self._offer(offer_id)
            rep = offer.get("report")
            if not rep:
                raise DealDeskError("Run the check before deciding.")
            if decision not in ("accept", "counter", "decline"):
                raise DealDeskError("decision must be accept, counter or decline")
            level = rep["risk"]["level"]
            risky = level in ("DO_NOT_ENGAGE", "HIGH")
            # Gate 1: the built-in guard. This is the floor and the policy file cannot lower it.
            if decision == "accept" and risky and not override:
                raise DealDeskError(f"Risk is {level}. Accepting needs an explicit override (override=true) "
                                    f"and is recorded in the ledger.")
            # Gate 2: the creator's own Cedar policy, which may only tighten gate 1 (see policy.py).
            verdict = policy.evaluate(decision, risk=level, override=bool(override), checked=True,
                                      creator=str(self.memory.profile.get("name") or "creator"),
                                      offer_id=offer_id,
                                      category=next(iter(rep.get("fit", {}).get("categories") or []), ""))
            if not verdict.allowed:
                raise DealDeskError(f"Refused by your own policy in policies/deal_desk.cedar. {verdict.note}"
                                    + (f" ({'; '.join(verdict.errors)})" if verdict.errors else ""))
            overridden = decision == "accept" and risky and override
            entry = self.memory.add_ledger(offer_id, rep["brand"], decision, level,
                                           (note + (f" [OVERRIDE of {level}]" if overridden else "")).strip(),
                                           policy=verdict.as_dict())
            offer["decision"] = {"decision": decision, "override": overridden, "ledger_seq": entry["seq"],
                                 "policy": verdict.as_dict()}
            offer["campaign"] = campaign_mod.build_campaign(offer, rep["claims"], self.memory.profile) \
                if decision == "accept" else None
            offer["script"] = None
            self.memory.put_offer(offer_id, offer)
            return {"decision": offer["decision"], "campaign": offer["campaign"], "ledger_entry": entry}

    # -- production --------------------------------------------------------------------
    def script(self, offer_id: str, approved_rewrites: Optional[List[int]] = None) -> Dict[str, Any]:
        with self._lock:
            offer = self._offer(offer_id)
            if not offer.get("campaign"):
                raise DealDeskError("Accept the offer first: the script is built from the campaign.")
            rep = offer["report"]
            s = script_agent.build_script(offer["campaign"], rep["claims"], self.memory.profile, approved_rewrites)
            problems = script_agent.check_script(s)
            s["guard_violations"] = problems
            if problems:
                raise DealDeskError("Script failed its safety guard: " + "; ".join(problems))
            self.memory.record_statements(rep["brand"], s["lines"])
            offer["script"] = s
            self.memory.put_offer(offer_id, offer)
            return s

    # -- helpers -----------------------------------------------------------------------
    def _offer(self, offer_id: str) -> Dict[str, Any]:
        offer = self.memory.get_offer(offer_id)
        if not offer:
            raise DealDeskError(f"Unknown offer {offer_id}")
        return offer


def _count(claims: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in claims:
        out[c["status"]] = out.get(c["status"], 0) + 1
    return out
