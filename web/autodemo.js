/* Auto-demo driver: the Deal Desk clicks through its own demo so you can just narrate.
 *
 * Use it:
 *   1. open http://127.0.0.1:8090 in your browser
 *   2. start your screen recorder (Windows: Win+Alt+R, or OBS)
 *   3. press F12 -> Console, paste this whole file, press Enter
 *   4. talk over it, following DEMO_SCRIPT.md
 *
 * It only clicks the buttons a person would click. It sends nothing and decides nothing on its own:
 * the one accept it performs is the clean Lumen Cloud offer, which the desk rates LOW anyway.
 *
 * Controls while it runs:  __demo.pause()   __demo.resume()   __demo.stop()
 * Slower/faster overall:   __demo.start(1.3)  (1.0 = the timings below, higher = slower)
 */
(() => {
  const S = { paused: false, stopped: false, rate: 1, t0: 0, cues: [] };
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // Subtitles are captured from the real run, so they cannot drift out of sync with the recording.
  const stamp = s => {
    const ms = Math.max(0, Math.round(s * 1000));
    const h = String(Math.floor(ms / 3600000)).padStart(2, '0');
    const m = String(Math.floor(ms / 60000) % 60).padStart(2, '0');
    const sec = String(Math.floor(ms / 1000) % 60).padStart(2, '0');
    return `${h}:${m}:${sec},${String(ms % 1000).padStart(3, '0')}`;
  };

  async function hold(ms) {
    const until = Date.now() + ms * S.rate;
    while (Date.now() < until) {
      if (S.stopped) throw new Error('__demo stopped');
      await sleep(60);
      while (S.paused && !S.stopped) await sleep(120);
    }
  }

  function banner(text, seconds) {
    let el = document.getElementById('__demoBanner');
    if (!el) {
      el = document.createElement('div');
      el.id = '__demoBanner';
      el.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:99999;' +
        'background:#111;color:#fff;padding:10px 18px;border-radius:999px;font:600 14px/1.4 system-ui,sans-serif;' +
        'box-shadow:0 6px 24px rgba(0,0,0,.35);max-width:80vw;text-align:center;opacity:0;transition:opacity .25s';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.opacity = '1';
    if (seconds) setTimeout(() => { el.style.opacity = '0'; }, seconds * 1000);

    const at = (Date.now() - S.t0) / 1000;
    const prev = S.cues[S.cues.length - 1];
    if (prev && prev.end > at) prev.end = at;          // never overlap the cue before it
    S.cues.push({ at, end: at + (seconds || 4), text });
  }

  const offerByRisk = risk =>
    Array.from(document.querySelectorAll('.offer'))
      .find(b => (b.querySelector('.pill') || {}).textContent === risk);

  // Two of the samples are both "Lumen Cloud" (the scam impersonates the real one), so pick by the
  // subject line, not the brand name, or step 3 re-selects the scam.
  const offerByLabel = fragment =>
    Array.from(document.querySelectorAll('.offer'))
      .find(b => b.textContent.toLowerCase().includes(fragment.toLowerCase()));

  async function scrollTo(match, ms = 1600) {
    const el = Array.from(document.querySelectorAll('#desk h3, #desk h2'))
      .find(h => h.textContent.toLowerCase().includes(match.toLowerCase()));
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); await hold(ms); }
  }

  async function run() {
    banner('Loading the inbox...', 3);
    const load = document.getElementById('btnSamples');
    if (load && !document.querySelector('.offer')) { load.click(); await hold(2500); }

    // --- 1. the scam -------------------------------------------------------------------
    banner('1/4  The scam offer', 4);
    (offerByRisk('DO NOT ENGAGE') || offerByLabel('URGENT')).click();
    await hold(1500);
    const check = document.getElementById('btnCheck');
    if (check) { check.click(); await hold(6000); }
    await scrollTo('Sender and links', 6000);
    banner('Eight red flags, each with its evidence. Capital I posing as an L.', 6);
    await hold(3000);
    await scrollTo('Your decision', 2500);
    const acc = document.getElementById("bAccept");
    if (acc) { banner('Accepting a scam: refused.', 5); acc.click(); await hold(4000); }

    // --- 2. the near-miss (the interesting one) ----------------------------------------
    banner('2/4  One letter from a real brand - and a real company', 5);
    offerByLabel('Cursos').click();
    await hold(1500);
    document.getElementById('btnCheck')?.click();
    await hold(7000);
    await scrollTo('Sender and links', 4500);
    banner('MEDIUM, not blocked. The site still gets crawled.', 5);
    await scrollTo('Claims the brand', 7000);
    banner('Site says "fastest" - but its pricing page says $29, not $12. Held back.', 7);
    await hold(2500);
    await scrollTo('Terms vs your norms', 5000);
    banner('"No contract is needed" is a HIGH warning, not a green tick.', 5);
    await hold(2500);

    // --- 3. the clean offer, accepted --------------------------------------------------
    banner('3/4  A clean offer', 4);
    const clean = offerByRisk('LOW') || offerByLabel('sponsored video');
    clean.click();
    await hold(1500);
    document.getElementById('btnCheck')?.click();
    await hold(7000);
    await scrollTo('Your decision', 2500);
    document.getElementById("bAccept")?.click();
    await hold(4000);
    banner('Accepted. Checklist and a claim-safe script.', 5);
    await scrollTo('Campaign', 4000);
    const script = document.getElementById("bScript");
    if (script) { script.click(); await hold(5000); }
    banner('Disclosure first. Verified claims only. Your own take stays a placeholder.', 6);
    await hold(3000);

    // --- 4. Cedar + the ledger ---------------------------------------------------------
    banner('4/4  Where AWS fits: your rules, in Cedar', 5);
    document.getElementById('tabMem').click();
    await hold(3500);
    banner('Live Cedar rules, and which one allowed each decision.', 7);
    window.scrollTo({ top: 400, behavior: 'smooth' });
    await hold(6000);
    banner('Done. 14/14 scams caught, false blocks 5/17 -> 0/17.', 8);
  }

  window.__demo = {
    start(rate = 1) {
      S.rate = rate; S.stopped = false; S.paused = false; S.t0 = Date.now(); S.cues = [];
      run().catch(e => { if (!String(e).includes('stopped')) console.error(e); banner('demo stopped', 2); });
    },
    /* Subtitles for the run that just finished, timed against it.
       __demo.srt()          -> downloads creatoros-demo.srt, ready to upload to YouTube
       __demo.srt(12)        -> shifts every cue 12s later, if your recording has an intro first */
    srt(offset = 0) {
      const body = S.cues.map((c, i) =>
        `${i + 1}\n${stamp(c.at + offset)} --> ${stamp(c.end + offset)}\n${c.text}\n`).join('\n');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([body], { type: 'text/plain' }));
      a.download = 'creatoros-demo.srt';
      a.click();
      console.log(body);
      return `${S.cues.length} cues, ${Math.round(S.cues[S.cues.length - 1]?.end || 0)}s`;
    },
    pause() { S.paused = true; banner('paused', 2); },
    resume() { S.paused = false; banner('resumed', 2); },
    stop() { S.stopped = true; },
  };

  console.log('%cAuto-demo ready.', 'font-weight:bold');
  console.log('Run __demo.start()  |  __demo.start(1.4) for slower  |  __demo.pause() / .resume() / .stop()');
  // A single start. index.html sets window.__demoRate before loading this file; calling
  // start() a second time from there left the first run alive (start resets the stop flag),
  // so two demos raced and every caption was emitted twice.
  window.__demo.start(window.__demoRate || 1);
})();
