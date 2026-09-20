"""Terminal demo of the Deal Desk vertical slice (no server needed).

    python scripts/demo.py            # real Chromium crawl
    python scripts/demo.py --static   # no browser, plain HTML crawl
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from creatoros.memory import Memory                       # noqa: E402
from creatoros.pipeline import DealDesk, DealDeskError    # noqa: E402

mode = "static" if "--static" in sys.argv else "auto"
desk = DealDesk(Memory(Path(tempfile.mkdtemp()) / "demo_memory.json"), crawl_mode=mode)
BAR = "-" * 78

for name in ("lumen_scam", "xyz_ai", "cursos_nearmiss", "lumen_clean"):
    raw = (ROOT / "sample_data" / "offers" / f"{name}.txt").read_text(encoding="utf-8")
    oid = desk.add_offer(raw, name)
    rep = desk.check(oid)
    print(f"\n{BAR}\n{name}: {rep['risk']['level']}  (score {rep['risk']['score']})\n{BAR}")
    for t in rep["trace"]:
        print(f"  {t['agent']:<16}{t['ms']:>6} ms  {t['summary']}")
    for f in rep["sender"]["flags"]:
        print(f"  [{f['severity']:<6}] {f['title']}")
    for c in rep["claims"]:
        print(f"  claim {c['status']:<16} {c['text'][:60]}")
    print("  ->", rep["risk"]["recommended_action"][:110])
    try:
        desk.decide(oid, "accept")
    except DealDeskError as e:
        print("  accept refused:", str(e)[:90])
        continue
    s = desk.script(oid)
    print("  ACCEPTED. Sponsor segment:")
    for l in s["lines"]:
        print(f"    {l['start']:>5}s {l['kind']:<10} {l['text'][:80]}")
print(f"\nLedger chain intact: {desk.memory.verify_ledger()['ok']}")
