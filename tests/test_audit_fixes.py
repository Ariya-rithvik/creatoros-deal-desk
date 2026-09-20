"""Regression tests for defects found in the second line-by-line audit.

Each test below FAILED before its fix. They are written as the failure story, not as a
restatement of the implementation, so that a future rewrite of the rules still has to keep
the behaviour the creator actually depends on.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creatoros.claims import verify_claims                                       # noqa: E402
from creatoros.memory import Memory                                              # noqa: E402
from creatoros.offer_parser import parse_offer                                   # noqa: E402
from creatoros.script_agent import build_script, check_script                    # noqa: E402
from creatoros.sender_check import check_sender                                  # noqa: E402
from creatoros.terms import analyze_terms                                        # noqa: E402
from creatoros.util import homoglyph_key, is_doubling, is_transposition          # noqa: E402


def fact(text, tag="p", url="https://brand.example/", fid="f_1"):
    return {"id": fid, "text": text, "tag": tag, "url": url}


def flag_ids(result):
    return {f["id"] for f in result["flags"]}


def sev_of(result, fid):
    return next((f["severity"] for f in result["flags"] if f["id"] == fid), None)


# ---- 1. look-alike detection must not condemn real companies -----------------------
@pytest.mark.parametrize("sender,collides_with", [
    ("Marco <marco@motion.com>", "notion"),        # Motion is a real, widely sponsored product
    ("Dana <dana@canvas.net>", "canva"),           # Canvas LMS by Instructure
    ("Ana <ana@cursos.com>", "cursor"),            # 'cursos' is Spanish/Portuguese for 'courses'
])
def test_a_one_edit_neighbour_of_a_known_brand_is_not_treated_as_impersonation(sender, collides_with):
    r = check_sender(sender, "We would like to sponsor a video. Our budget is $2,000.")
    assert "lookalike" not in flag_ids(r), f"{sender} was condemned as imitating {collides_with}"
    # It is still worth mentioning - but as a MEDIUM 'check this', never as a fatal verdict.
    assert sev_of(r, "lookalike_near") == "MEDIUM"


@pytest.mark.parametrize("sender", [
    "Lumen <partners@lumencIoud-creators.co>",     # capital I for l
    "Notion <hi@n0tion-creators.com>",             # zero for o
    "ElevenLabs <ads@elevenlab5.com>",             # five for s
    "Squarespace <s@sqaurespace.com>",             # adjacent transposition
    "Notion <hi@nottion.com>",                     # doubled letter
    "Dropbox <p@dropbox-creators.io>",             # brand plus scam decoration
])
def test_typosquat_signatures_are_still_fatal(sender):
    assert "lookalike" in flag_ids(check_sender(sender, "hi"))
    assert sev_of(check_sender(sender, "hi"), "lookalike") == "HIGH"


def test_the_strongest_brand_match_wins_over_a_coincidental_near_miss():
    """A domain that merely neighbours one brand must not shadow an exact match on another."""
    r = check_sender("x <a@notion-partners.com>", "hi")
    assert "lookalike" in flag_ids(r) and "lookalike_near" not in flag_ids(r)


def test_confusable_helpers():
    assert homoglyph_key("elevenlab5") == homoglyph_key("elevenlabs")
    assert homoglyph_key("n0tion") == homoglyph_key("notion")
    assert homoglyph_key("motion") != homoglyph_key("notion")
    assert is_transposition("sqaurespace", "squarespace")
    assert not is_transposition("motion", "notion")
    assert is_doubling("nottion", "notion") and is_doubling("notion", "nottion")
    assert not is_doubling("canvas", "canva")


# ---- 2. "no contract" is not a contract --------------------------------------------
def test_an_offer_that_refuses_a_contract_is_not_reported_as_having_one(tmp_path):
    body = ("From: Deals <partners@brandsite.example>\n"
            "Subject: sponsorship\n\n"
            "We want to sponsor your channel for $2,000. No contract is needed, we keep it simple.\n"
            "Publish the video and payment is sent after the video is live.\n")
    terms = parse_offer(body)["terms"]
    assert terms["has_contract"] is False
    assert terms["contract_declined"] is True

    ta = analyze_terms(terms, Memory(tmp_path / "m.json").profile)
    assert not any("contract" in line.lower() for line in ta["ok"]), \
        "an offer refusing a contract was shown to the creator as a green tick"
    contract = next(i for i in ta["issues"] if i["term"] == "contract")
    assert contract["severity"] == "HIGH"


def test_an_offer_that_really_does_mention_a_contract_still_counts():
    body = "From: a <a@b.example>\n\nWe will send a written contract before you record.\n"
    terms = parse_offer(body)["terms"]
    assert terms["has_contract"] is True and terms["contract_declined"] is False


# ---- 3. a superlative on the site does not licence a number the site never shows ----
def test_a_wrong_price_inside_a_supported_superlative_is_still_caught():
    facts = [fact("Lumen Cloud is the fastest way to deploy your app", tag="h1", fid="f_a"),
             fact("Starter plan $25 per month", fid="f_b")]
    r = verify_claims([{"text": "Lumen Cloud is the fastest way to deploy your app for $9 per month",
                        "source": "talking_point"}], facts, "Lumen Cloud")[0]
    assert r["status"] == "UNSUPPORTED", "the superlative branch swallowed the unsupported price"
    assert "9" in r["reason"]
    # and the suggested wording must not repeat the invented figure back to the audience
    assert "9" not in (r["rewrite"] or {}).get("text", "")


def test_a_superlative_with_a_correct_number_is_still_only_a_self_claim():
    facts = [fact("Lumen Cloud is the fastest way to deploy, from $25 per month", tag="h1", fid="f_a")]
    r = verify_claims([{"text": "Lumen Cloud is the fastest way to deploy for $25 per month",
                        "source": "talking_point"}], facts, "Lumen Cloud")[0]
    assert r["status"] == "SELF_CLAIM"


def test_a_number_the_site_publishes_on_another_page_is_not_called_unsupported():
    """The superlative lives on the homepage, the figure it is bundled with lives elsewhere.

    Checking the number against only the superlative's own fact flagged '120 projects' as
    unsupported on a site whose homepage lists exactly that.
    """
    facts = [fact("Cursos is the fastest way to go from tutorial to a shipped project", tag="h1", fid="f_a"),
             fact("Over 120 guided projects", tag="li", fid="f_b")]
    r = verify_claims([{"text": "Cursos is the fastest way to learn, and over 120 guided projects ship with review",
                        "source": "offer_text"}], facts, "Cursos")[0]
    assert r["status"] == "SELF_CLAIM", r["reason"]


# ---- 4. the script guard must cover attributed lines, not only claim lines ----------
def test_an_attributed_rewrite_carrying_an_uncited_number_is_rejected_by_the_guard():
    """Defence in depth: even if a bad SELF_CLAIM got through verification, the guard stops it."""
    script = {
        "brand": "Lumen Cloud",
        "lines": [
            {"kind": "disclosure", "text": "This segment is a paid partnership with Lumen Cloud.",
             "source": None, "action": None, "placeholder": False},
            {"kind": "rewrite", "action": "attribute", "placeholder": False,
             "text": 'Lumen Cloud says: "it is the fastest way to deploy for $9 per month".',
             "source": {"fact_id": "f_a", "url": "https://brand.example/", "facts": [
                 {"fact_id": "f_a", "url": "https://brand.example/",
                  "fact_text": "Lumen Cloud is the fastest way to deploy, from $25 per month"}]}},
        ],
    }
    problems = check_script(script)
    assert any("does not show" in p and "9" in p for p in problems), problems


def test_an_attributed_rewrite_backed_by_its_fact_passes():
    script = {
        "brand": "Lumen Cloud",
        "lines": [
            {"kind": "disclosure", "text": "This segment is a paid partnership with Lumen Cloud.",
             "source": None, "action": None, "placeholder": False},
            {"kind": "rewrite", "action": "attribute", "placeholder": False,
             "text": 'Lumen Cloud says: "it is the fastest way to deploy for $25 per month".',
             "source": {"fact_id": "f_a", "url": "https://brand.example/", "facts": [
                 {"fact_id": "f_a", "url": "https://brand.example/",
                  "fact_text": "Lumen Cloud is the fastest way to deploy, from $25 per month"}]}},
        ],
    }
    assert check_script(script) == []


def test_an_approved_attribution_carries_its_evidence_onto_the_line(tmp_path):
    facts = [fact("Lumen Cloud is the fastest way to deploy, from $25 per month", tag="h1", fid="f_a")]
    claims = verify_claims([{"text": "Lumen Cloud is the fastest way to deploy for $25 per month",
                             "source": "talking_point"}], facts, "Lumen Cloud")
    s = build_script({"brand": "Lumen Cloud", "deliverable": "45-second integration"},
                     claims, Memory(tmp_path / "m.json").profile, approved_rewrites=[0])
    line = next(l for l in s["lines"] if l["kind"] == "rewrite")
    assert line["action"] == "attribute" and line["source"]["facts"], \
        "an attributed line reached the creator with no evidence attached to it"
    assert check_script(s) == []


# ---- 5. a fee the tool cannot compare must say so ----------------------------------
def test_a_non_usd_fee_is_reported_as_unchecked_rather_than_silently_skipped(tmp_path):
    profile = Memory(tmp_path / "m.json").profile
    ta = analyze_terms({"amount": 60000.0, "currency": "INR", "duration_seconds": 60,
                        "exclusivity_days": 0, "net_days": 30, "usage_days": 30}, profile)
    fee = next((i for i in ta["issues"] if i["term"] == "fee"), None)
    assert fee is not None, "an INR fee was neither compared nor mentioned - silence reads as approval"
    assert "not compared" in fee["ask"] or "not in USD" in fee["ask"]


# ---- 6. the whole thing, end to end, on the sample that exercises all of the above --
def test_the_near_miss_sample_is_checked_rather_than_blocked_and_holds_the_wrong_price(tmp_path):
    """One offer that used to fail four different ways at once.

    Old behaviour: DO_NOT_ENGAGE on a coincidental domain neighbour, so the site was never
    crawled; 'no contract' shown as a green tick; the wrong price waved through inside a
    superlative; the INR fee silently unexamined.
    """
    from creatoros.pipeline import DealDesk

    desk = DealDesk(Memory(tmp_path / "m.json"), crawl_mode="static")
    raw = (ROOT / "sample_data" / "offers" / "cursos_nearmiss.txt").read_text(encoding="utf-8")
    oid = desk.add_offer(raw, "cursos")
    rep = desk.check(oid)

    assert rep["risk"]["level"] == "MEDIUM", "a one-edit domain neighbour is not a scam verdict"
    assert rep["site"]["ok"], "the brand site must still be crawled and checked"
    assert {f["id"] for f in rep["sender"]["flags"]} == {"lookalike_near"}

    priced = next(c for c in rep["claims"] if "$12" in c["text"])
    assert priced["status"] == "UNSUPPORTED" and "12" in priced["reason"]

    terms = {i["term"]: i for i in rep["terms_analysis"]["issues"]}
    assert terms["contract"]["severity"] == "HIGH"
    assert terms["fee"]["severity"] == "LOW"

    # accepted without an override (it is not risky), and the wrong price never reaches the script
    desk.decide(oid, "accept")
    s = desk.script(oid)
    assert s["guard_violations"] == []
    assert not any("$12" in l["text"] for l in s["lines"]), "the unsupported price reached the script"
    assert any("$12" in e["text"] for e in s["excluded"])
    # the claim the site really does publish is still usable
    assert any("120 guided projects" in l["text"] for l in s["lines"] if l["kind"] == "claim")
