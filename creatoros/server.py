"""HTTP API + single-page UI for the Deal Desk.

Run:  python -m uvicorn creatoros.server:app --port 8090        (binds to 127.0.0.1 by default; keep it that way)

This is a single-user LOCAL tool with no login, so the server defends itself against web pages that try to
drive it from your browser:
  * Host allowlist  -> blocks DNS-rebinding (a hostile site resolving its name to 127.0.0.1)
  * X-CreatorOS header required on every non-GET request -> a cross-site page cannot send it without a
    CORS preflight, and we send no CORS headers, so cross-site POSTs (CSRF) are refused
Endpoints are synchronous on purpose: the Explorer drives Playwright's sync API in a worker thread.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .memory import Memory
from .pipeline import DealDesk, DealDeskError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "index.html"
MAX_OFFER_CHARS = 100_000
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}
CSRF_HEADER = "x-creatoros"
SAMPLES = [("xyz_ai", "Sponsorship: XYZ AI x Arya Builds"),
           ("lumen_scam", "URGENT: Lumen Cloud paid sponsorship"),
           ("lumen_clean", "Lumen Cloud x Arya Builds - sponsored video")]

app = FastAPI(title="CreatorOS Deal Desk", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
desk = DealDesk(Memory(), crawl_mode=os.getenv("CREATOROS_CRAWL", "auto"),
                check_domain_age=os.getenv("CREATOROS_RDAP") == "1")


@app.middleware("http")
async def local_only_guard(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Host not allowed"}, status_code=403)
    if request.method not in ("GET", "HEAD") and request.headers.get(CSRF_HEADER) != "1":
        return JSONResponse({"detail": "Missing X-CreatorOS header"}, status_code=403)
    return await call_next(request)


class NewOffer(BaseModel):
    raw: str = Field(max_length=MAX_OFFER_CHARS)
    label: Optional[str] = Field(default=None, max_length=200)


class Decision(BaseModel):
    decision: str
    override: bool = False
    note: str = Field(default="", max_length=500)


class ScriptReq(BaseModel):
    approved_rewrites: List[int] = Field(default_factory=list, max_length=50)


def _public(offer: Dict[str, Any]) -> Dict[str, Any]:
    """Offer without the (large) raw fact list."""
    o = dict(offer)
    if o.get("report"):
        o["report"] = {k: v for k, v in o["report"].items() if k != "facts"}
    return o


def _summary(o: Dict[str, Any]) -> Dict[str, Any]:
    rep = o.get("report")
    return {"id": o["id"], "label": o["label"], "brand": o["parsed"].get("brand"), "sender": o["parsed"].get("sender"),
            "risk": rep["risk"]["level"] if rep else None, "decision": (o.get("decision") or {}).get("decision")}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return WEB.read_text(encoding="utf-8")


@app.get("/api/state")
def state() -> Dict[str, Any]:
    return {"profile": desk.memory.profile, "offers": [_summary(o) for o in desk.memory.list_offers()]}


@app.post("/api/samples")
def load_samples() -> Dict[str, Any]:
    ids = []
    for name, label in SAMPLES:
        raw = (ROOT / "sample_data" / "offers" / f"{name}.txt").read_text(encoding="utf-8")
        ids.append(desk.add_offer(raw, label))
    return {"ids": ids}


@app.post("/api/offers")
def new_offer(body: NewOffer) -> Dict[str, Any]:
    if not body.raw.strip():
        raise HTTPException(400, "Paste the offer text.")
    return {"id": desk.add_offer(body.raw, body.label)}


@app.get("/api/offers/{oid}")
def get_offer(oid: str) -> Dict[str, Any]:
    o = desk.memory.get_offer(oid)
    if not o:
        raise HTTPException(404, "Unknown offer")
    return _public(o)


@app.post("/api/offers/{oid}/check")
def check(oid: str) -> Dict[str, Any]:
    try:
        rep = desk.check(oid)
    except DealDeskError as e:
        raise HTTPException(404, str(e))
    return {k: v for k, v in rep.items() if k != "facts"}


@app.post("/api/offers/{oid}/decide")
def decide(oid: str, body: Decision) -> Dict[str, Any]:
    try:
        return desk.decide(oid, body.decision, body.override, body.note)
    except DealDeskError as e:
        raise HTTPException(409, str(e))


@app.post("/api/offers/{oid}/script")
def script(oid: str, body: ScriptReq) -> Dict[str, Any]:
    try:
        return desk.script(oid, body.approved_rewrites)
    except DealDeskError as e:
        raise HTTPException(409, str(e))


@app.get("/api/memory")
def memory() -> Dict[str, Any]:
    m = desk.memory
    return {"profile": m.profile, "ledger": m.data["ledger"], "ledger_check": m.verify_ledger(), "trust": m.trust_graph()}


@app.post("/api/reset")
def reset() -> Dict[str, Any]:
    m = desk.memory
    with m.lock:
        m.data["offers"], m.data["ledger"], m.data["trust"] = {}, [], {}
        m.save()
    return {"ok": True}
