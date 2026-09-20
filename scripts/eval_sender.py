"""Regression eval for the Sender Verifier on a labeled set of 31 offers (14 scam, 17 legit).

HONESTY NOTE: this set was written by the same people who wrote the rules, so it is a regression
suite, not an independent accuracy claim. Real-world performance needs real (anonymised) offers.
Some legit cases are deliberately awkward (an offer that mentions a 'gift code', a dashboard sign-in)
so the false positives it produces are visible instead of hidden.

l13-l17 are legitimate companies whose domain sits one edit from a brand scammers impersonate
(Motion/Notion, Canvas/Canva, Cursos/Cursor, Bitwarder/Bitwarden, Descripto/Descript). They were
added AFTER the detector was found to condemn all five as impersonation, so the number they produce
is a before/after on a known defect, not evidence that the detector generalises.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from creatoros.sender_check import check_sender          # noqa: E402
from creatoros.risk import FATAL_IDS                       # noqa: E402
from creatoros.offer_parser import parse_offer            # noqa: E402

data = json.loads((ROOT / "eval" / "labeled_offers.json").read_text(encoding="utf-8"))
tp = fp = tn = fn = 0
misses = []
for d in data:
    website = next(iter(parse_offer(f"From: {d['sender']}\n\n{d['body']}")["urls"]), None)
    r = check_sender(d["sender"], d["body"], website)
    fatal = any(f["severity"] == "HIGH" and f["id"] in FATAL_IDS for f in r["flags"])
    if d["scam"] and fatal: tp += 1
    elif d["scam"] and not fatal: fn += 1; misses.append(("MISSED SCAM", d["id"], [f["id"] for f in r["flags"]]))
    elif not d["scam"] and fatal: fp += 1; misses.append(("FALSE ALARM", d["id"], [f["id"] for f in r["flags"] if f["id"] in FATAL_IDS]))
    else: tn += 1
scams, legit = tp + fn, tn + fp
print(f"scams caught (DO_NOT_ENGAGE): {tp}/{scams}   legit offers wrongly blocked: {fp}/{legit}")
for m in misses:
    print(" ", *m)
