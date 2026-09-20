import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creatoros.claims import extract_claims, verify_claims                    # noqa: E402
from creatoros.memory import Memory                                            # noqa: E402
from creatoros.offer_parser import parse_offer                                 # noqa: E402
from creatoros.pipeline import DealDesk, DealDeskError                         # noqa: E402
from creatoros.script_agent import check_script                                # noqa: E402
from creatoros.sender_check import check_sender                                # noqa: E402
from creatoros.site_explorer import crawl                                      # noqa: E402
from creatoros.terms import analyze_terms                                      # noqa: E402

OFFERS = ROOT / "sample_data" / "offers"


def raw(name):
    return (OFFERS / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture()
def desk(tmp_path):
    return DealDesk(Memory(tmp_path / "mem.json"), crawl_mode="static")


def ids(flags):
    return {f["id"] for f in flags}


# ---- sender verifier ---------------------------------------------------------------
def test_scam_offer_gets_the_expected_red_flags():
    p = parse_offer(raw("lumen_scam"))
    r = check_sender(p["sender"], p["body"], p["website"])
    assert {"lookalike", "upfront_fee", "odd_payment", "credential_request", "file_link", "shortener", "publish_first"} <= ids(r["flags"])


def test_capital_i_lookalike_is_caught_even_though_lowercasing_hides_it():
    r = check_sender("x <a@lumencIoud-creators.co>", "hello", None)
    assert "lookalike" in ids(r["flags"])


def test_official_brand_domain_is_verified_not_flagged():
    p = parse_offer(raw("lumen_clean"))
    r = check_sender(p["sender"], p["body"], p["website"])
    assert r["flags"] == [] and r["verified_brand_domain"] == "lumencloud.com"


def test_freemail_sender_is_flagged():
    assert "freemail" in ids(check_sender("Brand <deals@gmail.com>", "hi", None)["flags"])


# ---- parser ------------------------------------------------------------------------
def test_offer_line_beats_plan_price_when_reading_the_fee():
    p = parse_offer(raw("lumen_clean"))
    assert p["terms"]["amount"] == 900 and p["terms"]["duration_seconds"] == 45


def test_scam_fee_demand_is_not_read_as_the_offer():
    assert parse_offer(raw("lumen_scam"))["terms"]["amount"] == 3500


def test_promo_code_and_terms_are_parsed():
    p = parse_offer(raw("xyz_ai"))
    assert p["promo_code"] == "ARYA20" and p["discount_percent"] == 20
    assert p["terms"]["exclusivity_days"] == 180 and p["terms"]["net_days"] == 60


# ---- claim verifier ----------------------------------------------------------------
@pytest.fixture(scope="module")
def xyz_facts():
    r = crawl("https://xyzai.dev", mode="static")
    assert r["ok"] and r["fixture"] == "xyz_ai"
    return r["facts"]


def status_of(claims, needle):
    return next(c["status"] for c in claims if needle in c["text"])


def test_planted_claims_are_classified_correctly(xyz_facts):
    p = parse_offer(raw("xyz_ai"))
    cl = verify_claims(extract_claims(p["body"], p["brand"], p["talking_points"]), xyz_facts, p["brand"])
    assert status_of(cl, "fastest") == "UNSUBSTANTIATED"
    assert status_of(cl, "doubles") == "UNSUBSTANTIATED"
    assert status_of(cl, "50,000") == "UNSUPPORTED"
    assert status_of(cl, "$19") == "SUPPORTED"
    assert status_of(cl, "Python") == "SUPPORTED"


def test_wrong_price_is_caught_by_the_numeric_guard(xyz_facts):
    cl = verify_claims([{"text": "the Pro plan is $29 per month", "source": "offer_text"}], xyz_facts, "XYZ AI")
    assert cl[0]["status"] == "UNSUPPORTED" and "29" in cl[0]["reason"]


def test_unsupported_claim_gets_a_safe_rewrite_that_drops_the_number(xyz_facts):
    cl = verify_claims([{"text": "It doubles developer productivity", "source": "offer_text"}], xyz_facts, "XYZ AI")
    assert "2x" not in cl[0]["rewrite"]["text"] and "may vary" in cl[0]["rewrite"]["text"]


# ---- terms -------------------------------------------------------------------------
def test_terms_are_compared_with_the_creators_own_norms(tmp_path):
    prof = Memory(tmp_path / "m.json").profile
    ta = analyze_terms(parse_offer(raw("xyz_ai"))["terms"], prof)
    flagged = {i["term"] for i in ta["issues"]}
    assert {"exclusivity", "payment terms", "usage rights"} <= flagged


def test_perpetual_usage_rights_is_high_severity(tmp_path):
    prof = Memory(tmp_path / "m.json").profile
    ta = analyze_terms({"usage_perpetual": True, "usage_days": 36500, "amount": 900, "currency": "USD"}, prof)
    assert any(i["term"] == "usage rights" and i["severity"] == "HIGH" for i in ta["issues"])


# ---- pipeline / approval layer -----------------------------------------------------
def test_three_offers_get_three_different_verdicts(desk):
    levels = {n: desk.check(desk.add_offer(raw(n), n))["risk"]["level"] for n in ("xyz_ai", "lumen_scam", "lumen_clean")}
    assert levels == {"xyz_ai": "MEDIUM", "lumen_scam": "DO_NOT_ENGAGE", "lumen_clean": "LOW"}


def test_scam_cannot_be_accepted_without_override_and_override_is_recorded(desk):
    oid = desk.add_offer(raw("lumen_scam"), "scam")
    desk.check(oid)
    with pytest.raises(DealDeskError):
        desk.decide(oid, "accept")
    out = desk.decide(oid, "accept", override=True, note="testing")
    assert "OVERRIDE" in out["ledger_entry"]["note"]


def test_suspicious_sender_site_is_fetched_as_plain_html_only(desk):
    rep = desk.check(desk.add_offer(raw("lumen_scam"), "scam"))
    assert rep["site"]["mode"] == "static"
    assert rep["reply_draft"]["text"] is None            # never draft a reply to a scammer
    assert rep["facts"] == []                            # nothing from a hostile site is reused downstream


def test_nothing_is_ever_sent_automatically(desk):
    rep = desk.check(desk.add_offer(raw("xyz_ai"), "xyz"))
    assert rep["reply_draft"]["send"] is False and rep["reply_draft"]["text"]


def test_script_needs_an_accepted_offer(desk):
    oid = desk.add_offer(raw("lumen_clean"), "c")
    desk.check(oid)
    with pytest.raises(DealDeskError):
        desk.script(oid)


def test_script_invariants_hold(desk):
    oid = desk.add_offer(raw("xyz_ai"), "xyz")
    desk.check(oid)
    desk.decide(oid, "accept")
    s = desk.script(oid)
    kinds = [l["kind"] for l in s["lines"]]
    assert kinds.index("disclosure") < kinds.index("claim")
    assert any(l["placeholder"] for l in s["lines"])              # the creator's take is never invented
    spoken = " ".join(l["text"].lower() for l in s["lines"])
    assert "fastest" not in spoken and "doubles" not in spoken and "50,000" not in spoken
    assert check_script(s) == []


def test_tampering_with_a_verified_claim_is_caught_by_the_guard(desk):
    oid = desk.add_offer(raw("xyz_ai"), "xyz")
    desk.check(oid)
    desk.decide(oid, "accept")
    s = desk.script(oid)
    claim = next(l for l in s["lines"] if l["kind"] == "claim" and "$19" in l["text"])
    claim["text"] = claim["text"].replace("$19", "$9")
    assert any("not supported" in p for p in check_script(s))


def test_rewrite_requires_explicit_approval(desk):
    oid = desk.add_offer(raw("xyz_ai"), "xyz")
    desk.check(oid)
    desk.decide(oid, "accept")
    assert not any(l["kind"] == "rewrite" for l in desk.script(oid)["lines"])
    assert any(l["kind"] == "rewrite" for l in desk.script(oid, approved_rewrites=[0])["lines"])


def test_ledger_is_hash_chained_and_tampering_is_detected(desk, tmp_path):
    for n in ("xyz_ai", "lumen_clean"):
        oid = desk.add_offer(raw(n), n)
        desk.check(oid)
        desk.decide(oid, "accept")
    assert desk.memory.verify_ledger()["ok"]
    desk.memory.data["ledger"][0]["action"] = "decline"
    assert not desk.memory.verify_ledger()["ok"]


def test_trust_graph_records_claims_and_creator_statements(desk):
    oid = desk.add_offer(raw("xyz_ai"), "xyz")
    desk.check(oid)
    desk.decide(oid, "accept")
    desk.script(oid)
    node = desk.memory.trust_graph()["XYZ AI"]
    assert any(c["status"] == "UNSUBSTANTIATED" for c in node["claims"])
    assert node["creator_statements"] and all(s["source_fact"] for s in node["creator_statements"] if s["kind"] == "claim")


# ---- regressions found by the labeled eval -----------------------------------------
def test_digit_one_lookalike_is_caught():
    assert "lookalike" in ids(check_sender("Skillshare <p@skil1share-creators.com>", "hi", None)["flags"])


def test_legit_brand_asking_for_dashboard_signin_is_not_a_scam_signal():
    r = check_sender("Hana <hana@descript.com>", "Please sign in to our creator dashboard at descript.com.", None)
    assert not any(f["id"] in ("credential_request", "signin_request") for f in r["flags"])


def test_unverified_sender_asking_for_signin_is_a_medium_flag_not_fatal():
    r = check_sender("x <a@random-agency.com>", "Please sign in to our portal to see the brief.", None)
    assert [f["severity"] for f in r["flags"] if f["id"] == "signin_request"] == ["MEDIUM"]


def test_password_manager_brand_is_not_mistaken_for_a_password_request():
    r = check_sender("Kai <kai@1password.com>", "We sponsor videos about password managers.", None)
    assert "credential_request" not in ids(r["flags"])


def test_actually_asking_for_a_password_is_fatal():
    r = check_sender("x <a@promo.co>", "Send us your Google password so we can verify your channel.", None)
    assert "credential_request" in ids(r["flags"])
