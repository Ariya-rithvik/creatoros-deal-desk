"""Policy Agent: the creator's decision rules, evaluated by Cedar (AWS open source).

Why this exists. The rule "you cannot accept a scam without an explicit override" was a Python `if`
inside `pipeline.decide()`. That works, but it is invisible to the person it protects: the creator
cannot read it, cannot argue with it, and cannot add a rule of their own ("never a gambling brand,
not even with an override") without editing the program. Cedar is a policy language built for exactly
this - declarative, deterministic, with `forbid` beating `permit` - so the rules move into
`policies/deal_desk.cedar` where they are data the creator owns.

SAFETY MODEL, and the only thing that really matters here: this layer can only ever TIGHTEN.
`pipeline.decide()` keeps its own guard and a decision needs BOTH to allow it. So:

  * deleting a `forbid` from the policy file unlocks nothing - the built-in guard still refuses
  * adding a `forbid` takes effect immediately
  * if the policy file exists but will not parse or evaluate, this returns DENY (fail closed), because
    a creator who wrote a rule should never silently lose it to a typo
  * if `cedarpy` is not installed at all, this ABSTAINS and says so. The built-in guard is unchanged,
    so the tool still behaves correctly; it just stops offering the extra layer.

Nothing here can approve something the built-in guard would refuse. That is deliberate: a policy file
is a place to be stricter, not a way around the safety rules.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "policies" / "deal_desk.cedar"

# Policies get positional ids (policy0, policy1, ...) in file order, so the @id("...") annotations
# in the file can be mapped back onto them for human-readable reasons.
_ID_ANNOTATION = re.compile(r'@id\("([^"]+)"\)')


@dataclass
class PolicyDecision:
    """What the policy layer concluded. `allowed` is only ever advisory-to-tighten (see module docs)."""
    allowed: bool
    engine: str                                   # "cedar" or "unavailable"
    available: bool
    reasons: List[str] = field(default_factory=list)      # named policies that decided it
    errors: List[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"allowed": self.allowed, "engine": self.engine, "available": self.available,
                "reasons": self.reasons, "errors": self.errors, "note": self.note}


def _policy_text(path: Optional[Path] = None) -> str:
    return (path or POLICY_FILE).read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """Drop Cedar `//` comments, respecting quoted strings.

    Without this, the commented-out examples at the bottom of the policy file were listed in the UI
    as if they were live rules, and uncommenting one shifted every reason name by a position.
    """
    out: List[str] = []
    for line in text.splitlines():
        in_str = False
        cut = len(line)
        i = 0
        while i < len(line):
            c = line[i]
            if c == '"' and (i == 0 or line[i - 1] != "\\"):
                in_str = not in_str
            elif not in_str and c == "/" and line[i:i + 2] == "//":
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return "\n".join(out)


def _named_ids(text: str) -> List[str]:
    """The @id names of the ACTIVE policies, in file order (Cedar numbers them policy0, policy1, ...)."""
    return _ID_ANNOTATION.findall(_strip_comments(text))


def cedar_available() -> bool:
    try:
        import cedarpy
    except ImportError:
        return False
    return cedarpy is not None


def evaluate(action: str, *, risk: str, override: bool, checked: bool, creator: str = "creator",
             offer_id: str = "offer", category: str = "", path: Optional[Path] = None) -> PolicyDecision:
    """Ask the creator's Cedar policy whether `action` is allowed on this offer."""
    try:
        from cedarpy import Decision, is_authorized
    except ImportError:
        return PolicyDecision(allowed=True, engine="unavailable", available=False,
                              note="cedarpy is not installed, so the creator's policy file was not "
                                   "consulted. The built-in guard in pipeline.decide() still applies.")

    policy_path = path or POLICY_FILE
    try:
        text = _policy_text(policy_path)
    except OSError as e:
        return PolicyDecision(allowed=False, engine="cedar", available=True,
                              errors=[f"could not read {policy_path.name}: {e}"],
                              note="Policy file unreadable, so the decision was refused. Fix the file.")

    request = {"principal": f'Creator::"{creator}"', "action": f'Action::"{action}"',
               "resource": f'Offer::"{offer_id}"', "context": {}}
    entities = [
        {"uid": {"type": "Creator", "id": creator}, "attrs": {}, "parents": []},
        {"uid": {"type": "Offer", "id": offer_id},
         "attrs": {"risk": risk, "override": bool(override), "checked": bool(checked),
                   "category": category or ""},
         "parents": []},
    ]

    try:
        result = is_authorized(request, text, entities)
    except Exception as e:                       # noqa: BLE001 - a broken policy must fail closed
        return PolicyDecision(allowed=False, engine="cedar", available=True,
                              errors=[f"policy could not be evaluated: {str(e)[:200]}"],
                              note="The policy file did not evaluate, so the decision was refused. "
                                   "Fix the file rather than removing this check.")

    names = _named_ids(text)
    reasons = []
    for r in (getattr(result.diagnostics, "reasons", None) or []):
        m = re.fullmatch(r"policy(\d+)", str(r))
        idx = int(m.group(1)) if m else None
        reasons.append(names[idx] if idx is not None and idx < len(names) else str(r))
    errors = [str(e) for e in (getattr(result.diagnostics, "errors", None) or [])]

    if errors:
        return PolicyDecision(allowed=False, engine="cedar", available=True, reasons=reasons, errors=errors,
                              note="The policy raised an error while evaluating, so the decision was refused.")

    allowed = result.decision == Decision.Allow
    return PolicyDecision(
        allowed=allowed, engine="cedar", available=True, reasons=reasons,
        note=("Allowed by your policy: " + ", ".join(reasons)) if allowed and reasons
        else ("Refused by your policy: " + ", ".join(reasons)) if reasons
        else ("Allowed by your policy." if allowed else
              "Refused: no policy in deal_desk.cedar permits this, and Cedar denies by default."))


def describe() -> Dict[str, Any]:
    """Summary for the UI: which engine is in use and which rules are loaded."""
    if not cedar_available():
        return {"engine": "unavailable", "available": False, "policies": [], "file": str(POLICY_FILE.name),
                "note": "cedarpy is not installed. Run: pip install cedarpy"}
    try:
        names = _named_ids(_policy_text())
    except OSError:
        names = []
    return {"engine": "cedar", "available": True, "policies": names, "file": str(POLICY_FILE.name),
            "note": "Evaluated by Cedar. These rules can only make the desk stricter, never more permissive."}
