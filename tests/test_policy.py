"""Tests for the Cedar policy layer (AWS open source) that governs the creator's decisions.

The property that matters most is the last one: a policy file can make the desk STRICTER, and can
never make it more permissive than the built-in guard. A policy language is a place to add your own
refusals, not a way to talk the safety rules out of a refusal.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creatoros import policy                                                     # noqa: E402
from creatoros.memory import Memory                                              # noqa: E402
from creatoros.pipeline import DealDesk, DealDeskError                           # noqa: E402

OFFERS = ROOT / "sample_data" / "offers"
cedar_only = pytest.mark.skipif(not policy.cedar_available(), reason="cedarpy is not installed")


def raw(name):
    return (OFFERS / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture()
def desk(tmp_path):
    return DealDesk(Memory(tmp_path / "mem.json"), crawl_mode="static")


# ---- the policy file itself ---------------------------------------------------------
@cedar_only
@pytest.mark.parametrize("action,risk,override,expected", [
    ("accept", "LOW", False, True),
    ("accept", "MEDIUM", False, True),
    ("accept", "HIGH", False, False),
    ("accept", "DO_NOT_ENGAGE", False, False),
    ("accept", "HIGH", True, True),
    ("accept", "DO_NOT_ENGAGE", True, True),
    ("counter", "DO_NOT_ENGAGE", False, True),
    ("decline", "DO_NOT_ENGAGE", False, True),
])
def test_the_shipped_policy_matches_the_built_in_guard(action, risk, override, expected):
    d = policy.evaluate(action, risk=risk, override=override, checked=True)
    assert d.allowed is expected, d.note
    assert d.engine == "cedar"


@cedar_only
def test_an_unchecked_offer_cannot_be_accepted():
    assert policy.evaluate("accept", risk="LOW", override=False, checked=False).allowed is False


@cedar_only
def test_the_decision_names_the_rule_that_decided_it():
    d = policy.evaluate("accept", risk="DO_NOT_ENGAGE", override=False, checked=True)
    assert "forbid_risky_accept_without_override" in d.reasons


@cedar_only
def test_only_live_rules_are_listed_not_the_commented_examples():
    """The file ends with commented-out examples; showing them as active would be a lie,
    and it shifts the name of every reason Cedar reports."""
    listed = policy.describe()["policies"]
    assert "accept_when_risk_is_acceptable" in listed
    assert not any(n.startswith("my_rule_") for n in listed), listed


# ---- failure modes ------------------------------------------------------------------
@cedar_only
def test_a_broken_policy_file_fails_closed(tmp_path):
    bad = tmp_path / "broken.cedar"
    bad.write_text("permit (principal, action, resource) when { this is not cedar", encoding="utf-8")
    d = policy.evaluate("accept", risk="LOW", override=False, checked=True, path=bad)
    assert d.allowed is False and d.errors, "a policy that will not parse must not silently allow"


@cedar_only
def test_a_missing_policy_file_fails_closed(tmp_path):
    d = policy.evaluate("accept", risk="LOW", override=False, checked=True, path=tmp_path / "gone.cedar")
    assert d.allowed is False and d.errors


@cedar_only
def test_an_empty_policy_denies_because_cedar_denies_by_default(tmp_path):
    empty = tmp_path / "empty.cedar"
    empty.write_text("// no rules at all\n", encoding="utf-8")
    assert policy.evaluate("accept", risk="LOW", override=False, checked=True, path=empty).allowed is False


def test_without_cedarpy_the_layer_abstains_rather_than_blocking(monkeypatch):
    """If the optional dependency is absent the tool must still work; the built-in guard covers it."""
    import builtins
    real_import = builtins.__import__

    def no_cedar(name, *a, **k):
        if name == "cedarpy":
            raise ImportError("simulated: cedarpy not installed")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_cedar)
    d = policy.evaluate("accept", risk="DO_NOT_ENGAGE", override=False, checked=True)
    assert d.allowed is True and d.available is False and d.engine == "unavailable"


# ---- the property that matters: tightening only -------------------------------------
@cedar_only
def test_a_stricter_policy_really_does_block_an_otherwise_acceptable_offer(desk, tmp_path, monkeypatch):
    strict = tmp_path / "strict.cedar"
    strict.write_text(
        '@id("accept_when_risk_is_acceptable")\n'
        'permit (principal, action == Action::"accept", resource)\n'
        'when { resource.risk == "LOW" || resource.risk == "MEDIUM" };\n'
        '@id("my_rule_only_low_risk")\n'
        'forbid (principal, action == Action::"accept", resource)\n'
        'unless { resource.risk == "LOW" };\n', encoding="utf-8")
    monkeypatch.setattr(policy, "POLICY_FILE", strict)

    oid = desk.add_offer(raw("cursos_nearmiss"), "cursos")
    assert desk.check(oid)["risk"]["level"] == "MEDIUM"      # the built-in guard would allow this
    with pytest.raises(DealDeskError, match="your own policy"):
        desk.decide(oid, "accept")


@cedar_only
def test_a_permissive_policy_cannot_unlock_what_the_built_in_guard_refuses(desk, tmp_path, monkeypatch):
    """The whole safety argument for having a policy file at all."""
    wide_open = tmp_path / "open.cedar"
    wide_open.write_text('@id("allow_everything")\npermit (principal, action, resource);\n', encoding="utf-8")
    monkeypatch.setattr(policy, "POLICY_FILE", wide_open)

    assert policy.evaluate("accept", risk="DO_NOT_ENGAGE", override=False, checked=True).allowed is True

    oid = desk.add_offer(raw("lumen_scam"), "scam")
    assert desk.check(oid)["risk"]["level"] == "DO_NOT_ENGAGE"
    with pytest.raises(DealDeskError, match="explicit override"):
        desk.decide(oid, "accept")                            # still refused, by the built-in guard


@cedar_only
def test_the_ledger_records_which_rule_allowed_the_decision(desk):
    oid = desk.add_offer(raw("lumen_clean"), "clean")
    desk.check(oid)
    out = desk.decide(oid, "accept")
    assert out["decision"]["policy"]["engine"] == "cedar"
    assert "accept_when_risk_is_acceptable" in out["ledger_entry"]["policy"]["reasons"]
    assert desk.memory.verify_ledger()["ok"] is True
