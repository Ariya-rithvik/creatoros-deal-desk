"""Creator Memory: the persistent state every agent reads from.

Holds three things:
  profile  - who the creator is, what they refuse, their norms (rates, exclusivity limits, tone)
  ledger   - append-only, hash-chained record of every decision the creator made (tamper-evident)
  trust    - the Creator Trust Graph: brand -> claims -> evidence -> what the creator actually said

Stored as one JSON file, written atomically.
"""
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "sample_data" / "profile.json"


def _hash(prev: str, entry: Dict[str, Any]) -> str:
    payload = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


class Memory:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else ROOT / "data" / "memory.json"
        self.lock = threading.RLock()
        self.data: Dict[str, Any] = {"profile": None, "offers": {}, "ledger": [], "trust": {}}
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        if not self.data.get("profile"):
            self.data["profile"] = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
            self.save()

    # -- persistence -------------------------------------------------------------------
    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, indent=1, ensure_ascii=False)
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)

    # -- profile -----------------------------------------------------------------------
    @property
    def profile(self) -> Dict[str, Any]:
        return self.data["profile"]

    def set_profile(self, profile: Dict[str, Any]) -> None:
        with self.lock:
            self.data["profile"] = profile
            self.save()

    # -- offers ------------------------------------------------------------------------
    def put_offer(self, offer_id: str, offer: Dict[str, Any]) -> None:
        with self.lock:
            self.data["offers"][offer_id] = offer
            self.save()

    def get_offer(self, offer_id: str) -> Optional[Dict[str, Any]]:
        return self.data["offers"].get(offer_id)

    def list_offers(self) -> List[Dict[str, Any]]:
        return list(self.data["offers"].values())

    # -- decision ledger (hash chained) -----------------------------------------------
    def add_ledger(self, offer_id: str, brand: str, action: str, risk: str, note: str = "",
                   policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Append a decision. `policy` records which Cedar rules allowed it, so the audit trail says
        not just what the creator decided but under which version of their own rules."""
        with self.lock:
            led = self.data["ledger"]
            prev = led[-1]["hash"] if led else "genesis"
            entry = {"seq": len(led) + 1, "ts": int(time.time()), "offer_id": offer_id, "brand": brand,
                     "action": action, "risk": risk, "note": note, "policy": policy or {}, "prev_hash": prev}
            entry["hash"] = _hash(prev, {k: v for k, v in entry.items() if k != "hash"})
            led.append(entry)
            self.save()
            return entry

    def verify_ledger(self) -> Dict[str, Any]:
        prev = "genesis"
        for i, e in enumerate(self.data["ledger"]):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev_hash") != prev or _hash(prev, body) != e.get("hash"):
                return {"ok": False, "first_bad_index": i, "entries": len(self.data["ledger"])}
            prev = e["hash"]
        return {"ok": True, "first_bad_index": None, "entries": len(self.data["ledger"])}

    # -- trust graph -------------------------------------------------------------------
    def record_trust(self, brand: str, website: Optional[str], claims: List[Dict[str, Any]], site_ok: bool) -> None:
        with self.lock:
            node = self.data["trust"].setdefault(brand, {"website": website, "claims": [], "creator_statements": []})
            node["website"] = website
            node["checked_at"] = int(time.time())
            node["site_checked"] = site_ok
            node["claims"] = [{"claim": c["text"], "status": c["status"], "reason": c["reason"],
                               "evidence": c.get("evidence", [])} for c in claims]
            self.save()

    def record_statements(self, brand: str, lines: List[Dict[str, Any]]) -> None:
        with self.lock:
            node = self.data["trust"].setdefault(brand, {"website": None, "claims": [], "creator_statements": []})
            node["creator_statements"] = [{"text": l["text"], "kind": l["kind"],
                                           "source_fact": (l.get("source") or {}).get("fact_id")} for l in lines
                                          if l["kind"] in ("claim", "rewrite")]
            self.save()

    def trust_graph(self) -> Dict[str, Any]:
        return self.data["trust"]
