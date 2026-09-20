# CreatorOS Deal Desk

**Your AI team behind every sponsorship.** A creator gets a brand offer. Before they trust it, the Deal Desk
checks the sender, crawls the brand's website in a real browser, verifies every claim the brand wants the creator
to say against the brand's own published material, compares the terms with the creator's own limits, and returns
an evidence report. The creator decides. If they accept, it builds a campaign checklist and drafts a sponsor
segment in their voice, using only claims that were verified.

This is the first vertical slice of the larger CreatorOS plan (see `PLAN.md`). Video generation, editing,
publishing and analytics are deliberately **not** built yet.

## Why this problem

* Fake sponsorship offers are a documented wave: look-alike domains, up-front "verification fees", publish-first
  payment, "verify your channel" sign-ins that take over the account
  ([Bitdefender](https://www.bitdefender.com/en-us/blog/hotforsecurity/how-fake-sponsorship-emails-are-targeting-youtube-creators)).
* Creators carry legal responsibility for what they say: the FTC Endorsement Guides
  ([ftc.gov](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking),
  [16 CFR 255](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-255)) say endorsers can be liable for
  unsubstantiated performance claims and missing disclosures.
* YouTube's Creator Partnerships handles brand inquiries inside YouTube. It does not (as far as we found) verify
  the brand's claims, catch impersonation arriving by e-mail, or apply *your* personal limits. That is the gap.

## Run it

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m pytest                       # 100 tests
python scripts/demo.py                 # terminal demo, real Chromium (add --static for no browser)
python -m uvicorn creatoros.server:app --port 8090   # then open http://127.0.0.1:8090
python scripts/eval_sender.py          # regression eval on 31 labeled offers
```

No API key is needed. Everything is deterministic, so results are repeatable and every verdict is explainable.

## The agents (what each one does)

| Agent | Module | Job |
|---|---|---|
| Offer Parser | `offer_parser.py` | e-mail -> brand, fee, deliverable, usage rights, exclusivity, payment terms, talking points |
| Sender Verifier | `sender_check.py` | look-alike domains (I/l, 0/o, rn/m, 1/l, digit-for-letter, transposition, doubled letter), free-mail, fee demands, gift cards/crypto, publish-first, credential requests, shorteners, file-share/archives |
| Explorer | `site_explorer.py` | real Chromium crawl of the brand site into hashed, citable facts |
| Claim Verifier | `claims.py` | each claim -> SUPPORTED / SELF_CLAIM / UNSUPPORTED / UNSUBSTANTIATED, with the cited fact and a safe rewrite |
| Terms Analyst | `terms.py` | terms vs the creator's own norms (exclusivity, Net days, usage rights, rate card) |
| Fit Analyst | `fit.py` | brand category vs the creator's never-promote list |
| Risk Aggregator | `risk.py` | one verdict (LOW / MEDIUM / HIGH / DO_NOT_ENGAGE), every point mapped to a named reason, plus a counter-email draft |
| Policy Agent | `policy.py` | the creator's own decision rules, written in **Cedar** (`policies/deal_desk.cedar`) and evaluated by AWS's open-source policy engine |
| Campaign Agent | `campaign.py` | accepted offer -> deadline, approved/held-back claims, disclosure checklist |
| Script Agent | `script_agent.py` | sponsor segment in the creator's voice from verified claims only |
| Creator Memory | `memory.py` | profile, hash-chained decision ledger, Creator Trust Graph |

## Safety design (each one is a test)

* Nothing outward-facing happens automatically: no e-mail is sent, nothing is published. Replies are drafts.
* The Explorer only ever fetches **public** internet addresses (`netguard.py`): loopback, private ranges, link-local/cloud
  metadata, local hostnames, credentials-in-URL and non-http(s) schemes are refused, on the first request, on every
  redirect, and on every sub-request the browser makes (SSRF protection; offers are attacker-controlled input).
* A link from an unsafe sender is **not opened at all** (opening it can confirm your mailbox is live).
* The local server refuses foreign `Host` headers (DNS rebinding) and any non-GET request without the `X-CreatorOS`
  header (CSRF), exposes no API docs, and caps input sizes. Keep it bound to 127.0.0.1: there is no login.
* A risky offer can only be accepted with an explicit override, and the override is recorded in the ledger.
* The decision rules also live in `policies/deal_desk.cedar`, as **Cedar** policies the creator can read and edit.
  That layer can only ever **tighten**: `pipeline.decide()` keeps its own guard and a decision needs both to allow it,
  so a wide-open policy file still cannot accept a `DO_NOT_ENGAGE` offer (there is a test for exactly that). A policy
  file that will not parse fails **closed**; if `cedarpy` is not installed the layer abstains and says so, and the
  built-in guard is unchanged. The ledger records which named rule allowed each decision.
* No reply is drafted for a suspected scam. Only our own fictional demo fixtures are read for such offers, as plain HTML with no scripts.
* The script never invents the creator's experience: that line is a visible placeholder.
* The disclosure line always comes before any claim; every factual line cites facts from the brand's site, and every
  number AND every content word of it must come from those facts (`line_supported`); a line that cannot be traced is
  left out of the draft with a warning, and tampering with a line is caught by `check_script`.
* Claims that failed verification are excluded unless the creator approves a specific rewrite. An approved rewrite that
  **attributes** a claim to the brand ("Lumen Cloud says: ...") carries the brand's wording but is still checked for
  numbers: the guard used to inspect only `claim` lines, so an attributed line could speak a figure the brand's site
  never publishes.
* The decision ledger is hash-chained, so editing history is detectable.
* All offer text is HTML-escaped in the UI, because offers can be hostile.

## What is real and what is a fixture

* The four sample offers and the sites `xyzai.dev`, `lumencloud.com`, `cursos.dev` and the look-alike domain are
  **fictional demo fixtures**, served from `sample_data/sites` (loaded with `file://` into real Chromium). Any other
  domain is crawled live.
* Brand names in `sender_check.KNOWN_BRANDS` are used only to detect impersonation.

## Honest limits

* `scripts/eval_sender.py` is a **regression suite**, not an accuracy claim: the labeled set (31 offers) was written
  by the same people who wrote the rules, and several rules were tuned on failures it exposed. Real performance needs
  real, anonymised offers. Current run: **14/14 scams caught, 0/17 legitimate offers wrongly blocked**. The same set
  against the previous detector: 14/14 scams caught, **5/17 legitimate offers wrongly blocked** - five real companies
  (Motion, Canvas, Cursos, Bitwarder, Descripto) condemned as impersonating a brand they merely neighbour. That
  before/after is a fixed defect, not proof the detector generalises.
* Impersonation is now reported in two strengths, because collapsing them was the cause of those five false blocks:
  a **typosquat signature** (the brand exactly once scam decoration is stripped, homoglyphs resolved, one adjacent
  transposition, or one doubled letter) is HIGH and stops the offer; a bare **one-edit neighbour** is MEDIUM, says so
  in plain words, and lets the check continue. `motion.com` is one edit from `notion.com` and is a real company.
* Claim checking uses keyword matching plus a numeric guard. It tells you whether the brand's *own* site supports a
  statement, never whether the statement is true. Paraphrased claims can be missed.
* The numeric guard checks that a number appears in the cited facts, not that it belongs to the right plan: "Starter is
  $25 per month" would pass if the Team plan costs $25. Plan-aware matching is a known gap (same class of weakness our
  claim-drift scan found in Veridemo Watch).
* A superlative the brand's site also makes does **not** vouch for a number bundled with it. "The fastest way to deploy,
  for $9 a month" is held back when the site says $25, even though the site does say "fastest". Numbers are checked
  against both the facts that match the claim's wording and the facts that repeat the superlative, so a figure the site
  publishes on another page still counts; a figure it publishes nowhere does not.
* The fee is only compared with the rate card when both are in USD. A fee in another currency is reported as
  **not compared** rather than passed over in silence.
* Brand-fit uses keyword categories. Terms parsing is regex-based and can miss unusual phrasing.
* Domain age (RDAP) is optional (`CREATOROS_RDAP=1`) and needs network access.
* Not legal advice. The disclosure checklist follows FTC guidance; check local rules (e.g. ASCI in India).

## Reused from your other projects

`creatoros/truth_set.py` is a vendored copy of Veridemo Watch's fact engine (hashed facts, stable ids and the
numeric-support guard `verify_claim`). The crawler follows the pattern proven in the claim-drift scan. The original
projects were not modified.
