# CreatorOS Deal Desk — First Commit (AWS x WeMakeDevs, Sept 17–20 2026)

**Track: Build It** (open source, runs entirely on a local machine, no AWS account needed).
**AWS open source used: [Cedar](https://www.cedarpolicy.com/)** — the policy engine that decides what the
creator is allowed to do with an offer (`policies/deal_desk.cedar`, `creatoros/policy.py`).

---

## The problem

A creator gets an email: *"We'd love to sponsor your channel — $3,500."* Two things can go wrong, and
both are documented, not imagined:

1. **It's a scam.** Fake sponsorship emails targeting YouTube creators are a documented wave: look-alike
   domains, up-front "verification fees", publish-first payment, and "sign in to verify your channel"
   pages that take the account over
   ([Bitdefender](https://www.bitdefender.com/en-us/blog/hotforsecurity/how-fake-sponsorship-emails-are-targeting-youtube-creators)).
2. **It's real, and it still hurts them.** The creator repeats whatever the brand put in the talking
   points — "the fastest tool", "doubles your productivity", "$12 a month" — on camera, in their own
   voice. Under the FTC Endorsement Guides
   ([16 CFR 255](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-255)) the **endorser**
   can be liable for unsubstantiated claims and missing disclosure. The brand wrote the sentence; the
   creator is the one who said it.

Nobody checks this for them. YouTube's Creator Partnerships handles brand inquiries inside YouTube; as
far as we found it does not verify the brand's claims, catch impersonation arriving by email, or apply
*this particular creator's* limits. That gap is the product.

## What it does

Paste the offer in. Eleven agents run, each one explainable:

| Agent | What it does |
|---|---|
| Offer Parser | email → brand, fee, deliverable, usage rights, exclusivity, payment terms, talking points |
| Sender Verifier | look-alike domains, free-mail, fee demands, gift-card/crypto rails, publish-first, credential requests, shorteners, file-share archives |
| Explorer | crawls the brand's site in **real Chromium** into hashed, citable facts |
| Claim Verifier | each claim → SUPPORTED / SELF_CLAIM / SITE_CITES_EVIDENCE / UNSUPPORTED / UNSUBSTANTIATED, with the cited fact and a safe rewrite |
| Terms Analyst | the offer's terms vs *the creator's own* limits, from their profile |
| Fit Analyst | brand category vs their never-promote list |
| Risk Aggregator | one verdict, every point mapped to a named reason |
| **Policy Agent (Cedar)** | decides whether the creator may accept, counter or decline |
| Campaign Agent | accepted offer → deadline, approved/held-back claims, FTC disclosure checklist |
| Script Agent | sponsor segment in their voice, from verified claims only |
| Creator Memory | profile, hash-chained decision ledger, Creator Trust Graph |

The creator decides. **Nothing is ever sent or published automatically** — replies are drafts.

## Where AWS fits: Cedar

The rule *"you cannot accept a scam without an explicit override"* started life as a Python `if`. That
works, but it is invisible to the person it protects. The creator cannot read it, cannot argue with it,
and cannot add a rule of their own — *"never a gambling brand, not even if I'm tempted"* — without
editing the program.

So the decision rules moved into **Cedar**, AWS's open-source policy language, as data the creator owns:

```cedar
@id("accept_risky_only_with_override")
permit (principal, action == Action::"accept", resource)
when { resource.override == true };

@id("forbid_risky_accept_without_override")
forbid (principal, action == Action::"accept", resource)
when { (resource.risk == "HIGH" || resource.risk == "DO_NOT_ENGAGE") && resource.override == false };
```

Cedar is the right tool for three specific reasons, not because it was on the list:

* **`forbid` beats `permit`, and anything unpermitted is denied.** A safety rule written as a `forbid`
  cannot be accidentally widened by adding another policy. That is the opposite of a pile of `if`s.
* **It is deterministic and total.** No model, no API key, no network. The same offer always produces
  the same decision, which is the whole premise of the project.
* **It explains itself.** Cedar reports which policy decided, so the ledger records not just *what the
  creator decided* but *under which of their own rules* — and the UI lists the live rules by name.

**The design constraint that matters:** this layer can only ever **tighten**. The built-in guard in
`pipeline.decide()` still runs and a decision needs *both* to allow it. A wide-open policy file
(`permit (principal, action, resource);`) still cannot accept a `DO_NOT_ENGAGE` offer — there is a test
that asserts exactly that. A policy file is a place to add your own refusals, never a way to talk the
safety rules out of one. If the file won't parse, it fails **closed**; if `cedarpy` isn't installed, the
layer abstains and says so, and the built-in guard is unchanged.

## Execution: what actually works

```bash
pip install -r requirements.txt && python -m playwright install chromium
python -m pytest                                    # 100 tests
python scripts/demo.py                              # four offers, real Chromium
python scripts/eval_sender.py                       # labeled sender eval
python -m uvicorn creatoros.server:app --port 8090  # UI at http://127.0.0.1:8090
```

Four sample offers, four different outcomes: `DO_NOT_ENGAGE` / `MEDIUM` / `MEDIUM` / `LOW`. The scam
cannot be accepted without an override, and the override is written into a hash-chained ledger.

**The number we measured.** Halfway through we audited our own tool and found five ways it was lying to
the creator. The worst: the look-alike detector treated *any* domain within one or two edits of a known
brand as impersonation, so `motion.com` (a real product), `canvas.net` (Canvas LMS) and `cursos.dev`
were all rated `DO_NOT_ENGAGE` — site never crawled, no reply drafted. On our 31-offer labeled set:

| | scams caught | legitimate offers wrongly blocked |
|---|---|---|
| before the audit | 14/14 | **5/17** |
| after | 14/14 | **0/17** |

Same scam recall, false blocks gone. **Honest caveat, stated because it matters:** that labeled set is
self-authored, and the five near-miss cases were written *after* we found the defect. It is a
before/after on a known bug — not evidence the detector generalises. Real anonymised offers are the
next step, and we say so in the README rather than rounding it into an accuracy claim.

The other four defects are in `HANDOFF.md` §2, each with a regression test in `tests/test_audit_fixes.py`
that we verified **fails against the pre-fix code** before trusting it.

## What we learned

* **Cedar's evaluation model.** `forbid` beating `permit`, and default-deny, mean the safe direction is
  the easy one to write. Getting this wrong in hand-rolled `if`s is how authorization bugs happen. Also
  learned the sharp edge: Cedar numbers policies positionally, so the `@id("…")` annotations had to be
  mapped back onto `policy0, policy1, …` — and our first version counted commented-out examples as live
  rules, which both lied in the UI and shifted every reason name by one.
* **A green test suite is not evidence.** All five defects survived 61 passing tests and a clean linter.
  They survived because the tests were written from the same mental model as the code, and because **no
  sample offer exercised those paths**. The absence of a sample that *can* fail — not a missing test —
  is what let them live. We added `cursos_nearmiss.txt` for exactly that reason.
* **Fixes need the same scrutiny as the code.** Our fix for the claim checker immediately introduced a
  *new* false positive (it flagged "120 guided projects" because the number lives on a different page
  from the superlative). Only running a realistic end-to-end sample caught it.
* **Prove a regression test is real.** `git stash push -- <file>`, run the new test, watch it fail, then
  restore. A test that passes before the fix was testing nothing.

## Honest limits

We would rather be judged on these than have them found:

* The numeric guard checks a number *appears* in the cited facts, not that it belongs to the right plan.
  "Starter is $25" passes if the **Team** plan costs $25. Plan-aware matching is a known gap.
* "Supported" means *the brand's own site says it* — never that it is true.
* Claim matching is keyword-based; a paraphrase can be missed.
* Impersonation detection is bounded by a known-brands list. A brand not on that list cannot be detected
  as impersonated at all.
* A genuine typosquat using a plain single-letter substitution is now MEDIUM, not HIGH. That is the
  deliberate price of not blocking real companies; it is still surfaced and scored.
* Not legal advice. The checklist follows FTC guidance; check local rules (e.g. ASCI in India).

Sample brands and sites (`xyzai.dev`, `lumencloud.com`, `cursos.dev`, the look-alike) are **fictional
fixtures** served from `sample_data/sites`. Any other domain is crawled live.
`creatoros/truth_set.py` is a vendored, unmodified copy of a fact-engine we wrote previously — marked as
such at the top of the file. Everything else in this repository was written during the event.

## Safety, because the input is hostile

Offers are attacker-controlled text containing URLs, so: the Explorer only ever fetches **public**
addresses (loopback, private ranges, cloud metadata, credentials-in-URL and non-http schemes are refused
on the first request, every redirect and every browser sub-request); a link from an unsafe sender is
**not opened at all**; the local server refuses foreign `Host` headers and non-GET requests without the
`X-CreatorOS` header; all offer text is HTML-escaped in the UI. Each of those is a test.

**Why this is Build It and not Ship It:** the server has no login and is bound to `127.0.0.1` on
purpose — it reads a creator's private inbox. Putting it on a public URL without building authentication
first would break the thing the project is about. Deploying it is a real next step (Cognito for sign-in,
the ledger in DynamoDB, the crawler in Lambda behind a queue), but shipping it unauthenticated to win a
track would have been the wrong call.
