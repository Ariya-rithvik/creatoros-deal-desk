# CreatorOS: phased plan

Principle: every phase must be demoable on its own and provable with a number that we measured ourselves.
We build one phase, prove it, then move on. We do not build the whole platform at once.

## Phase 0 - Deal Desk (BUILT, this repo)

Offer in -> evidence report -> creator decision -> campaign -> claim-safe sponsor script.

Acceptance (all currently met, see `tests/` and `scripts/eval_sender.py`):
* the four sample offers get the verdicts DO_NOT_ENGAGE / MEDIUM / MEDIUM / LOW
* scam accept is refused without an override; the override is ledgered
* every spoken factual line is backed by a cited fact; the creator's experience is never invented
* an offer whose domain merely neighbours a known brand is checked, not blocked
* 82 tests pass; sender regression suite 14/14 scams caught, 0/17 legit blocked (self-authored set, see README)

Second audit (2026-09-20) found five defects in this phase and fixed them; see HANDOFF.md section 2. The lesson worth
carrying into every later phase: **all five survived a green test suite because no sample offer exercised them**. New
rules need a sample that can fail, not only a test that passes.

## Phase 1 - Real offers, real data (next, 2-3 days)

Goal: replace fixtures with the creator's actual inbox and prove accuracy on data we did not write.
* Gmail read-only connector (labels: "sponsorship"); paste-in stays as the fallback
* collect 50+ real, anonymised offers (creators we know); label them; report precision/recall honestly
* Claim Verifier v2: paraphrase-aware matching (optional Gemini pass, still re-checked by the numeric guard)
* Brand verification depth: RDAP domain age on by default, official-domain registry, contact-address match
* Metric: false-block rate on real legit offers below 5%; scams caught above 90%

## Phase 2 - Creator Memory that learns (3-4 days)

* ingest the creator's back catalog (transcripts) to learn tone, hook length, CTA, sponsor placement, integration length
* "make it sound like me": script agent grounded in real past segments, not just profile phrases
* Trust Graph becomes queryable: "what have I said about brand X, and was it verified?"
* Reuse: Cutlist transcript segmentation from `agentic_cinema_hack`
* Metric: blind test, creator picks their own past segment vs generated one; target close to chance

## Phase 3 - Production (video), only after Phases 0-2 are proven

* upload -> transcript -> best takes -> sponsor insertion point -> timeline the creator reviews and approves
* B-roll via Veo 3.1 (8s clips, native audio; Gemini API, not browser automation). Non-synthetic overlays first;
  any synthetic likeness/voice only with the creator's consent and a visible label (YouTube's altered/synthetic policy)
* the AI never changes what the creator says without an explicit, per-change approval
* Reuse: `agentic_video_editing`, `production_product` (Remotion), `agentic_studio_hub`

## Phase 4 - Publish and learn

* YouTube Data API upload as PRIVATE/UNLISTED first, creator reviews, then publish. Paid-promotion flag and
  disclosure in the description are set by the checklist, not skipped.
* analytics agent: retention drop points, comment sentiment, CTA performance vs the creator's own history
* Claim-drift watch (from Veridemo Watch): re-check published claims against the brand's site on a schedule.
  Caveat from our own scan: the current detector needs plan-aware matching, claim typing and toggle-safe facts first.

## Deliberately not doing

* "AI video editor for creators": too many strong products. Video is one tool, not the product.
* Rebuilding YouTube's brand marketplace (Creator Partnerships). We sit around it and across other channels.
* Auto-sending e-mail or auto-publishing anything without the creator approving that specific action.
* Faking numbers: all figures shown in demos come from our own runs on data we label as fixture or real.

## Risks to track

| Risk | Mitigation |
|---|---|
| YouTube expands Creator Partnerships to cover verification | our edge is cross-channel e-mail impersonation + creator-specific norms + claim substantiation; watch their release notes |
| Scraping / ToS on live sites | robots.txt respect, low rate, read-only; only crawl the brand URL from the offer |
| Legal exposure from "risk" labels | wording is "your own norms" and "the brand's own site says", never "this is false" or legal advice |
| Detector false blocks hurt trust | every flag shows its evidence; override always available and ledgered |
| Small eval set | Phase 1 real-data eval before any accuracy claim |

## Demo (180 seconds)

1. Scam offer arrives. Sender Verifier flags 8 things; verdict DO_NOT_ENGAGE; accept is refused; no reply drafted.
2. Real-looking offer (XYZ AI). Real Chromium crawl; 7 claims checked; "fastest" and "doubles productivity" unsubstantiated,
   "50,000 developers" unsupported; terms exceed the creator's limits; counter-email drafted, not sent.
3. The hard one (Cursos). The domain is one letter from a brand scammers impersonate - and the company is real. The
   desk says MEDIUM, not DO_NOT_ENGAGE, and keeps checking: the site IS crawled, "no contract is needed" is raised as a
   HIGH term issue instead of a green tick, the INR fee is reported as not compared, and "the fastest way to learn to
   code, for $12 a month" is held back because the brand's own pricing page says $29 - even though the site does say
   "fastest". Accept -> the $12 never reaches the script; the claim the site really publishes does.
4. Clean offer (Lumen Cloud). LOW. Accept -> checklist -> sponsor segment with disclosure first, verified claims only,
   the creator's own take left as a placeholder.
5. Creator Memory: hash-chained ledger shows the decisions; Trust Graph shows what the creator actually said.

The number to say out loud: on the 31-offer labeled set, the detector catches 14/14 scams either way, but false blocks
on legitimate offers went from **5/17 to 0/17** once impersonation was split from coincidence. Say plainly that the set
is self-authored and that this is a before/after on a known defect, not a generalisation claim.
