# 3-minute demo video script

Judging weights the video on: what it does + **where AWS fits**. Both are below. Keep it under 3:00.

**Before you hit record**

```bash
cd D:\creatoros
python -m uvicorn creatoros.server:app --port 8090
```
Open `http://127.0.0.1:8090`, click **Load sample offers**, then **Reset** so the ledger starts empty.
Have a second window on `policies/deal_desk.cedar`. Say "I" not "we" if you built it solo.

---

### 0:00–0:25 — The problem (say it over the inbox screen)

> A creator gets an email: "we'd love to sponsor you, $3,500." Two things can go wrong. It can be a
> scam — fake sponsorship emails targeting YouTubers are a documented wave. Or it's real, and the
> creator repeats the brand's talking points on camera — "the fastest tool", "$12 a month" — and under
> the FTC Endorsement Guides, **the endorser** is the one liable for claims they can't back up.
> Nobody checks this for them. That's what I built.

### 0:25–1:00 — The scam offer

Click **Lumen Cloud / DO NOT ENGAGE**.

> Eight red flags, each with the evidence that triggered it. The domain is `lumencIoud-creators.co` —
> that's a **capital I** pretending to be an L. It asks for a $49 verification fee, payment by gift
> card, and a sign-in to "verify your channel". Verdict: do not engage.

Tick nothing, click **Accept**. It refuses.

> It won't let me accept it. And notice the brand's website was **never opened** — clicking a link from
> a sender like this confirms your mailbox is live, so the crawler doesn't touch it.

### 1:00–1:50 — The hard one (this is the interesting case)

Click **Cursos / MEDIUM**.

> This is the case that made me audit my own tool. `cursos.dev` is one letter from `cursor.com`. My
> first version called that impersonation and blocked it — along with `motion.com` and `canvas.net`,
> which are **real companies**. So now it separates proof from coincidence: a typosquat signature is
> fatal, a one-edit neighbour is a MEDIUM "check this" and the desk keeps working.

Scroll to the claims table.

> It crawled the brand's site in real Chromium. The brand wants me to say *"Cursos is the fastest way
> to learn to code, for $12 a month."* The site **does** say "fastest" — but its pricing page says
> **$29**. Held back, with the reason. A superlative the site repeats doesn't vouch for a number it
> never publishes.

Scroll to terms.

> And the offer says "no contract is needed" — my earlier version read the word "contract" and showed
> that as a green tick. Now it's a HIGH warning.

### 1:50–2:25 — Where AWS fits: Cedar

Show `policies/deal_desk.cedar`, then the **Creator Memory** tab.

> The rule "you can't accept a scam without an explicit override" used to be a Python `if` — invisible
> to the person it protects. It's now **Cedar**, AWS's open-source policy engine, in a file the creator
> owns. Cedar fits because `forbid` beats `permit` and anything unpermitted is denied, so a safety rule
> can't be accidentally widened — and it's fully deterministic: no model, no API key, no network.

Point at the ledger's **Allowed by** column.

> Every decision is hash-chained and records **which of my own rules** allowed it.
> And the key constraint: this layer can only ever **tighten**. The built-in guard still runs and both
> have to agree — so even a wide-open policy file can't accept that scam. There's a test for exactly that.

### 2:25–3:00 — The number, and the honest part

Run `python scripts/eval_sender.py` on screen.

> On a 31-offer labelled set: 14 out of 14 scams caught, and false blocks on legitimate offers went from
> **5 out of 17 to 0 out of 17** after the audit. Same recall, the false alarms gone.
>
> Being straight about it: that set is one I wrote, and the near-miss cases were added **after** I found
> the bug — so it's a before/after on a known defect, not proof it generalises. Real anonymised offers
> are the next step, and the README says so.
>
> 100 tests. Nothing is ever sent or published automatically. The creator decides — the desk just makes
> sure they're deciding on evidence.

---

**If you're short on time, cut:** the terms/contract beat at 1:40 and the ledger close-up. Never cut
the Cedar section (it's a scored criterion) or the honest caveat at the end.
