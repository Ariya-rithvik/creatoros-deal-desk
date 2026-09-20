"""Tests for the safety and correctness fixes found in the line-by-line review."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creatoros import server, site_explorer                                     # noqa: E402
from creatoros.campaign import build_campaign                                    # noqa: E402
from creatoros.claims import unsupported_numbers, verify_claims                  # noqa: E402
from creatoros.fit import analyze_fit                                            # noqa: E402
from creatoros.memory import Memory                                              # noqa: E402
from creatoros.netguard import is_public_url                                     # noqa: E402
from creatoros.pipeline import DealDesk                                          # noqa: E402
from creatoros.script_agent import check_script                                  # noqa: E402
from creatoros.sender_check import check_sender                                  # noqa: E402

OFFERS = ROOT / "sample_data" / "offers"


def raw(name):
    return (OFFERS / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture()
def desk(tmp_path):
    return DealDesk(Memory(tmp_path / "mem.json"), crawl_mode="static")


def fact(text, tag="p", url="file:///x/index.html", fid="f_1"):
    return {"id": fid, "text": text, "tag": tag, "url": url}


# ---- SSRF guard --------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8090/api/state", "http://localhost/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://10.0.0.5/", "http://192.168.1.1/", "http://user:pw@8.8.8.8/", "ftp://8.8.8.8/",
    "file:///C:/Windows/win.ini", "http://printer.local/", "javascript:alert(1)",
])
def test_non_public_or_odd_urls_are_refused(url):
    assert is_public_url(url)[0] is False


def test_public_ip_literal_is_allowed():
    assert is_public_url("https://8.8.8.8/")[0] is True


def test_crawler_refuses_internal_addresses():
    r = site_explorer.crawl("http://127.0.0.1:8090/", mode="static")
    assert r["ok"] is False and r["error"].startswith("blocked")


def test_redirect_to_an_internal_address_is_refused(monkeypatch):
    import httpx

    class R:
        status_code = 302
        headers = {"location": "http://127.0.0.1/admin"}
        text = ""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    with pytest.raises(ValueError, match="blocked"):
        site_explorer._fetch_public("https://8.8.8.8/")


# ---- pipeline robustness -----------------------------------------------------------
def test_offer_without_a_website_does_not_crash(desk):
    oid = desk.add_offer("From: Sam <sam@somebrand.com>\n\nWe'd like to sponsor you for $500. Net 30, written contract.", "nosite")
    rep = desk.check(oid)
    assert rep["site"]["ok"] is False and "no website" in rep["site"]["error"]
    assert any("could not be checked" in r["text"] for r in rep["risk"]["reasons"])


def test_link_from_an_unsafe_sender_is_never_opened(desk, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the crawler must not be called for an unsafe external link")
    monkeypatch.setattr(site_explorer, "crawl", boom)
    scam = raw("lumen_scam").replace("lumencIoud-creators.co", "lumencIoud-creators.net")
    rep = desk.check(desk.add_offer(scam, "scam-external"))
    assert rep["site"]["skipped"] is True and rep["risk"]["level"] == "DO_NOT_ENGAGE"
    assert not any(r["text"] == "The brand website could not be checked" for r in rep["risk"]["reasons"])


def test_rechecking_clears_the_stale_decision_campaign_and_script(desk):
    oid = desk.add_offer(raw("xyz_ai"), "x")
    desk.check(oid)
    desk.decide(oid, "accept")
    desk.script(oid)
    desk.check(oid)
    o = desk.memory.get_offer(oid)
    assert o["decision"] is None and o["campaign"] is None and o["script"] is None
    assert desk.memory.verify_ledger()["entries"] == 1          # history is kept


def test_campaign_fee_without_a_currency_has_no_none_in_it():
    parsed = {"terms": {"amount": 900.0, "currency": None}, "brand": "B", "missing": []}
    c = build_campaign({"parsed": parsed}, [], {"typical_cta": "x"})
    assert c["fee"] == "900"


# ---- claim verifier ----------------------------------------------------------------
def test_numbers_are_compared_by_value_not_spelling():
    assert unsupported_numbers("The Pro plan is $19.00 per month", [fact("$19 per month")]) == []
    assert unsupported_numbers("used by 50000 developers", [fact("Trusted by 50,000 developers")]) == []
    assert unsupported_numbers("used by 60000 developers", [fact("Trusted by 50,000 developers")]) == ["60000"]


def test_superlative_elsewhere_on_the_site_does_not_support_a_different_claim():
    facts = [fact("Fastest support response in the industry", fid="f_a"), fact("AI coding assistant", tag="h1", fid="f_b")]
    r = verify_claims([{"text": "XYZ AI is the fastest AI coding tool available", "source": "offer_text"}], facts, "XYZ AI")[0]
    assert r["status"] == "UNSUBSTANTIATED"


def test_same_claim_on_the_site_without_evidence_is_a_self_claim():
    facts = [fact("The fastest AI coding tool on the market", fid="f_a")]
    r = verify_claims([{"text": "XYZ AI is the fastest AI coding tool", "source": "offer_text"}], facts, "XYZ AI")[0]
    assert r["status"] == "SELF_CLAIM" and r["rewrite"]["action"] == "attribute"


def test_evidence_must_be_in_the_same_statement_not_anywhere_on_the_page():
    unrelated = [fact("The fastest AI coding tool on the market", fid="f_a"), fact("Read our SOC 2 report", fid="f_b")]
    r = verify_claims([{"text": "XYZ AI is the fastest AI coding tool", "source": "offer_text"}], unrelated, "XYZ AI")[0]
    assert r["status"] == "SELF_CLAIM"
    same = [fact("The fastest AI coding tool, per our benchmark report", fid="f_a")]
    r = verify_claims([{"text": "XYZ AI is the fastest AI coding tool", "source": "offer_text"}], same, "XYZ AI")[0]
    assert r["status"] == "SITE_CITES_EVIDENCE"


# ---- sender verifier ---------------------------------------------------------------
def test_unrelated_domain_containing_a_brand_string_is_not_a_lookalike():
    for s in ("Priya <p@canvasplus.io>", "x <a@cursorfree.com>", "x <a@mail.notion.com>"):
        assert not any(f["id"] == "lookalike" for f in check_sender(s, "hi", None)["flags"]), s


def test_brand_plus_scam_decoration_is_a_lookalike():
    for s in ("x <a@lumencloud-creators.net>", "x <a@nordvpn-partners.com>", "x <a@sqaurespace.com>"):
        assert any(f["id"] == "lookalike" for f in check_sender(s, "hi", None)["flags"]), s


def test_display_name_naming_a_brand_from_a_foreign_domain_is_flagged_but_not_fatal():
    fl = check_sender("Dana from Notion Partnerships <dana@agency.com>", "hi", None)["flags"]
    assert [(f["id"], f["severity"]) for f in fl] == [("display_name", "MEDIUM")]


# ---- fit ---------------------------------------------------------------------------
def test_category_keywords_are_word_bounded():
    prof = {"never_promote": [], "preferred_categories": []}
    assert analyze_fit([fact("capital gains aim high")], "", prof)["categories"] == []
    assert "developer tools" in analyze_fit([fact("Our API for developers")], "", prof)["categories"]


# ---- script guard ------------------------------------------------------------------
def _accepted_script(desk):
    oid = desk.add_offer(raw("xyz_ai"), "x")
    desk.check(oid)
    desk.decide(oid, "accept")
    return oid, desk.script(oid)


def test_swapping_a_word_in_a_verified_claim_is_caught(desk):
    _, s = _accepted_script(desk)
    line = next(l for l in s["lines"] if l["kind"] == "claim" and "Python" in l["text"])
    line["text"] = line["text"].replace("Python", "Rust")
    assert any("wording is not supported" in p for p in check_script(s))


def test_duplicate_rewrite_approvals_are_applied_once(desk):
    oid, _ = _accepted_script(desk)
    s = desk.script(oid, approved_rewrites=[0, 0, 0])
    assert sum(1 for l in s["lines"] if l["kind"] == "rewrite") == 1


def test_a_rewrite_with_a_bracket_is_marked_as_a_placeholder_for_the_creator(desk):
    oid, s0 = _accepted_script(desk)
    idx = next(e["index"] for e in s0["excluded"] if "[" in e["rewrite"]["text"])
    s = desk.script(oid, approved_rewrites=[idx])
    assert next(l for l in s["lines"] if l["kind"] == "rewrite")["placeholder"] is True


# ---- HTTP server -------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "desk", DealDesk(Memory(tmp_path / "srv.json"), crawl_mode="static"))
    return TestClient(server.app)


H = {"X-CreatorOS": "1"}


def test_get_works_and_post_without_the_header_is_refused(client):
    assert client.get("/").status_code == 200
    assert client.post("/api/reset").status_code == 403
    assert client.post("/api/reset", headers=H).status_code == 200


def test_foreign_host_header_is_refused_against_dns_rebinding(client):
    assert client.get("/api/state", headers={"host": "evil.example"}).status_code == 403


def test_oversized_offer_is_rejected(client):
    r = client.post("/api/offers", headers=H, json={"raw": "x" * 100_001})
    assert r.status_code == 422


def test_api_docs_are_not_exposed(client):
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_full_flow_over_http_and_scam_gate(client):
    ids = client.post("/api/samples", headers=H).json()["ids"]
    levels = {}
    for oid in ids:
        rep = client.post(f"/api/offers/{oid}/check", headers=H).json()
        levels[oid] = rep["risk"]["level"]
        assert "facts" not in rep
    assert sorted(levels.values()) == ["DO_NOT_ENGAGE", "LOW", "MEDIUM", "MEDIUM"]
    scam = next(o for o, lv in levels.items() if lv == "DO_NOT_ENGAGE")
    assert client.post(f"/api/offers/{scam}/decide", headers=H, json={"decision": "accept"}).status_code == 409
    ok = next(o for o, lv in levels.items() if lv == "LOW")
    assert client.post(f"/api/offers/{ok}/decide", headers=H, json={"decision": "accept"}).status_code == 200
    assert client.post(f"/api/offers/{ok}/script", headers=H, json={"approved_rewrites": []}).json()["guard_violations"] == []
    assert client.get("/api/memory").json()["ledger_check"]["ok"] is True
