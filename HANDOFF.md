# CreatorOS: handoff for a new chat

Read this file first. It is written so a fresh model (or person) can continue without the old conversation.
Companion files: `README.md` (product + safety + limits), `PLAN.md` (phases), `D:\hackathon-research\NOTEPAD.md`
(research log and idea ranking, outside this repo).

## 1. What this is, in one paragraph

**CreatorOS Deal Desk**: a local tool for a content creator who receives a sponsorship offer by e-mail. It checks the
sender for scam patterns, crawls the brand's website in real Chromium, verifies each claim the brand wants the creator
to say against the brand's OWN site, compares the commercial terms with the creator's own limits, and returns one
evidence-backed verdict (LOW / MEDIUM / HIGH / DO_NOT_ENGAGE). The creator decides (accept / counter / decline). If they
accept, it builds a campaign checklist and drafts a sponsor segment in their voice using only verified claims.
Nothing outward-facing ever happens automatically. No API keys are needed; everything is deterministic.

It is deliberately ONE vertical slice ("Phase 0") of a bigger CreatorOS vision (research, production, publishing,
analytics). The bigger parts are NOT built. See `PLAN.md`.

## 2. State right now

* Location: `D:\creatoros` (git repo, see `git log`). Python 3.14, Windows 11. Not on any remote.
* `python -m pytest` -> 61 passed. `python -m pyflakes creatoros scripts tests` -> clean.
* `python scripts/eval_sender.py` -> 11/11 scams caught, 0/12 legit offers blocked. CAVEAT: the labeled set
  (`eval/labeled_offers.json`, 23 offers) was written by us and rules were tuned on its failures. It is a regression
  suite, NOT an accuracy claim. Real data is Phase 1.
* Live UI verified end to end in a real browser: three sample offers -> MEDIUM / DO_NOT_ENGAGE / LOW; scam accept refused
  without override; override recorded in the hash-chained ledger; script has disclosure first and a placeholder for the
  creator's own experience.
* Sample brands/sites are FICTIONAL fixtures (`sample_data/`). Any other domain is crawled live.

## 3. How to run

```bash
cd D:\creatoros
pip install -r requirements.txt && python -m playwright install chromium
python -m pytest                                    # 61 tests, ~2 s
python scripts/demo.py [--static]                   # terminal demo of the 3 sample offers
python scripts/eval_sender.py                       # sender regression eval
python -m uvicorn creatoros.server:app --port 8090  # UI at http://127.0.0.1:8090  (keep bound to 127.0.0.1)
```
Env vars: `CREATOROS_CRAWL=browser|static|auto` (default auto), `CREATOROS_RDAP=1` (domain-age lookup, needs network).
State persists in `data/memory.json` (gitignored). `POST /api/reset` clears offers/ledger/trust (keeps profile).

## 4. Repo map

```
creatoros/
  util.py            domains, homoglyph "deconfuse" (capital I->l, 0->o, rn->m, vv->w), levenshtein
  netguard.py        SSRF guard: only PUBLIC http(s) addresses may be fetched
  sender_check.py    Sender Verifier: explainable red flags (each has severity, why, evidence snippet)
  offer_parser.py    e-mail -> brand, fee, deliverable, usage/exclusivity/net terms, talking points, promo code
  site_explorer.py   Explorer: real Chromium (Playwright) or static crawl -> facts via truth_set; fixtures via file://
  truth_set.py       VENDORED copy from Veridemo Watch (hashed facts, stable ids, verify_claim). Do not edit.
  claims.py          Claim Verifier: SUPPORTED / SELF_CLAIM / SITE_CITES_EVIDENCE / UNSUPPORTED / UNSUBSTANTIATED + safe rewrites
  terms.py           terms vs creator norms (profile.norms)
  fit.py             brand category vs never_promote / preferred (word-bounded regexes)
  risk.py            Risk Aggregator (visible weights) + counter-email DRAFT
  campaign.py        accepted offer -> campaign (approved/held-back claims, disclosure checklist)
  script_agent.py    sponsor segment; invariants enforced by line_supported() and check_script()
  memory.py          profile + hash-chained decision ledger + Creator Trust Graph (one JSON file, atomic writes)
  pipeline.py        DealDesk orchestrator: add_offer, check, decide, script (locked, traced)
  server.py          FastAPI + single-page UI host, with local-only guards
web/index.html       single-file UI (vanilla JS, all dynamic text HTML-escaped)
sample_data/         profile.json, offers/*.txt, sites/{xyz_ai,lumen_cloud,lookalike}, fixture_domains.json
eval/labeled_offers.json   23 labeled offers (self-authored)
scripts/             demo.py, eval_sender.py
tests/               test_deal_desk.py (core), test_hardening.py (safety + review fixes)
```

## 5. Data flow (what `DealDesk.check()` does)

1. Offer Parser -> `parsed` {sender, subject, body, brand, website, terms{...}, talking_points, cta, promo_code, missing}
2. Sender Verifier -> flags[]. `fatal` = any HIGH flag whose id is in `risk.FATAL_IDS`
   (lookalike, upfront_fee, odd_payment, credential_request, file_link, young_domain).
3. Explorer -> facts. If `fatal` and the domain is NOT a fixture, the site is NOT visited (`site.skipped=True`).
   Fixtures for unsafe senders are read as static HTML.
4. Claim Verifier -> claims[] each {text, source, status, reason, support_ratio, evidence[{fact_id,text,url}], rewrite}
5. Terms Analyst, Fit Analyst (skipped when fatal), Risk Aggregator, draft reply (None when DO_NOT_ENGAGE)
6. Report stored on the offer; Trust Graph updated. Re-checking clears decision/campaign/script (ledger keeps history).
Then `decide()` (accept needs `override=true` for HIGH/DO_NOT_ENGAGE, recorded in ledger) -> `script()`.

HTTP API (all POSTs need header `X-CreatorOS: 1`): GET `/api/state`, POST `/api/samples`, POST `/api/offers`,
GET `/api/offers/{id}`, POST `/api/offers/{id}/check|decide|script`, GET `/api/memory`, POST `/api/reset`.

## 6. Invariants (each is a test; do not weaken them)

* Nothing is sent or published automatically; replies are drafts. No reply is drafted for DO_NOT_ENGAGE.
* Risky accept requires explicit override and is ledgered. Ledger is hash-chained; tampering is detected.
* Explorer fetches only public addresses (first request, redirects, browser sub-requests). Unsafe-sender links are not opened.
* Server: Host allowlist (DNS rebinding), `X-CreatorOS` header on non-GET (CSRF), no API docs, size caps.
* Script: disclosure before any claim; every spoken factual line's numbers AND content words come from its cited facts;
  untraceable lines are dropped with a warning; the creator's experience is a visible placeholder, never invented;
  flagged claims are excluded unless the creator approves a specific rewrite.
* Offer text is hostile input: HTML-escape everything in the UI.

## 7. Known limits (be honest about these)

* Numeric guard checks a number appears in the cited facts, NOT that it belongs to the right plan ("Starter $25" passes if
  Team costs $25). Plan-aware matching is a known gap.
* Claim matching is keyword-based; paraphrases can be missed. "Supported" means the brand's own site says it, not that it is true.
* Terms parsing is regex-based. Fit uses keyword categories. Lookalike detection uses a known-brands list (`KNOWN_BRANDS`)
  plus impersonation-decoration tokens; it can miss brands not in the list.
* DNS rebinding between the guard check and the browser request is only partly mitigated (host results are cached).
* Eval set is self-authored (see section 2).

## 8. Decisions and why (so they are not relitigated)

* User's north star: build something MORE necessary as AI agents get more capable, that a better prompt cannot replicate;
  filters: real pain, actually unsolved, needs agents (observe/reason/act/wait/recheck), portfolio edge, 180-second demo,
  measurable outcome. Every idea was run through these plus "who suffers / what happens today / why not existing / why
  agents / can we prove it in 180 s".
* Killed: ClaimBack (insurance appeals: Counterforce Health is free and adding voice), Saakshi (UPI already handles it).
* Evidence-sprinted candidates: OSS proof-gated intake (ranked #1 on the north star), ghost-network phone audit,
  Medicaid paperwork-loss prevention, blind-user accessible agent handoff, creator claim-drift. See NOTEPAD.md.
* CreatorOS was chosen by the user. We scoped it to Deal Desk because (a) fake sponsor offers are documented
  (Bitdefender) and creators are liable for unsubstantiated claims (FTC Endorsement Guides / 16 CFR 255), and (b) it reuses the
  user's existing agents (Explorer, fact engine, claim guard) and (c) it is provable in one demo. YouTube Creator
  Partnerships exists, so we do NOT rebuild a brand marketplace.
* Video generation (Veo 3.1: 8-second clips; Gemini API only, never browser automation of the Gemini web app), editing,
  publishing, analytics are Phase 3-4 and deliberately not built. AI must never change what the creator says without
  per-change approval; synthetic voice/likeness needs consent and a visible label (YouTube altered/synthetic policy).
* Claim-drift watch (auto-detect stale claims in published videos) was PARKED: our own scan of real YouTube review videos was
  incomplete (YouTube blocked transcript requests after 24; we stopped, did not evade) and showed the Veridemo Watch detector
  flagged 94% of price claims (unusable) and needs plan-aware matching, claim typing, toggle-safe facts, time-awareness.
  Only 1 of 6 price-quoting videos was stale with real traffic (both stale ones were >2 years old). Inconclusive on pain.
* Winner patterns worth copying (Amazon/Google/Gemma hackathons): a specific painful domain, a measured number, honest
  limits, deterministic guardrails around the model. CALL-E and All Things Agentic were saturated with
  "consent gate / verify the call / governed fleet" projects: verification is the default stack, NOT an edge.

## 9. Open questions for the user

1. WHICH HACKATHON is this for (name, deadline, theme)? Asked several times, never answered. It decides whether Phase 1
   (real-data eval) or Phase 3 (video) comes next, and how to pitch (developer/agent-infra vs human-impact).
2. Are there real anonymised sponsor offers (or a creator willing to share some) for the Phase 1 eval?
3. Push to a remote? None configured.

## 10. Next steps (suggested order)

1. Phase 1: real offers + real eval (target: false-block <5% on real legit offers, scams caught >90%). Gmail read-only
   connector optional; paste-in already works.
2. Plan-aware claim matching (plan name -> its own price), then optional Gemini paraphrase pass re-checked by the guard.
3. Phase 2: learn the creator's voice from back-catalog transcripts (reuse Cutlist segmentation in `D:\agentic_cinema_hack`).
4. Only then Phase 3 (video) and Phase 4 (publish/analytics).
Demo script (180 s) is at the bottom of `PLAN.md`.

## 11. Related projects on D:\ (reused or reusable; none were modified)

`D:\veridemo-watch` (source of truth_set.py, the claim-drift detector, MCP harness), `D:\demo` (Veridemo), `D:\agentic_cinema_hack`
(Cutlist: transcript segmentation + clip scoring), `D:\agentic_video_editing`, `D:\production_product` / `D:\ade` (Remotion),
`D:\agentic_studio_hub`, `D:\orchestrate` + `D:\ADIP-agent-audit` (ADIP Explorer/Knowledge-Graph agents), `D:\gpt_hackathon` and
`D:\stripe_recovery` (Recovery Agent uplift logic), `D:\calle_hack\{scar,earned-call}`, `D:\hackathon_gemma`
(NurtureLink, Gemma 4), `D:\worldagentsevrywhere` (Capability Engine), `D:\chatgpthack\proofpass`. Portfolio summary:
`D:\saakshi\PROJECT_PORTFOLIO.md`. Research log: `D:\hackathon-research\NOTEPAD.md`; the claim-drift scan scripts:
`D:\hackathon-research\scan\`.

## 12. Environment gotchas learned the hard way

* Shell quoting: long heredocs and `python - <<EOF` patch scripts with backslashes corrupted files twice (a stray `\x08`
  backspace ended up inside a regex). Prefer the Write/Edit tools; run `python -m pyflakes` and the tests after patching.
* Windows Python cannot read `/d/...` paths; use relative paths or `D:\...` from Python.
* pytest needs `--basetemp=data/.pytest_tmp` (already in `pytest.ini`); the system temp folder is locked down.
* Restart uvicorn after code changes (no reload). Port 8090. Kill via PowerShell `Get-NetTCPConnection -LocalPort 8090`.
* The browser pane can be hidden, so screenshots/clicks time out; drive/verify the UI with the JavaScript tool instead.
* Reddit is blocked in both search and browser tools; Quora is behind a login wall (do not create accounts).
  YouTube rate-limits transcript scraping (IpBlocked) and archive.org returns 429: back off, never evade.
* `pip install` works; Playwright Chromium is installed. There is no GEMINI_API_KEY in the environment.
* Sample date context: today in the session was 2026-09-20 (campaign `days_left` depends on the real clock).
