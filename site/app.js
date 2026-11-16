// Risk Radar front end: static, no build step, no dependencies.
"use strict";
(() => {
  const view = document.getElementById("view");
  const ORDER = ["new", "split", "removed", "merged", "rewritten", "edited", "unchanged"];
  const LABEL = { new: "new", split: "split off", removed: "removed", merged: "merged", rewritten: "rewritten", edited: "edited", unchanged: "unchanged" };
  let INDEX = null, FINDINGS = null, theme = null, chartAll = false, coAll = false, coQuery = "";
  const cache = {};

  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const yr = d => d.slice(0, 4);
  const CT = { new_exposure: "new exposure", escalated: "escalated", de_escalated: "de-escalated", boilerplate: "boilerplate" };
  const ctTag = r => r.change ? `<span class="ct ct-${r.change.label}">${CT[r.change.label]}</span>` : "";
  const pill = (st, n) => `<span class="pill st-${st}">${n != null ? `<span class="num">${n}</span> ` : ""}${LABEL[st]}</span>`;

  async function getJSON(path) {
    if (!cache[path]) {
      cache[path] = fetch(path).then(r => { if (!r.ok) throw new Error(path + " " + r.status); return r.json(); });
    }
    return cache[path];
  }

  function themeChart() {
    const cos = INDEX.companies.map(c => ({ t: c.ticker, a: c.themes.previous[theme], b: c.themes.current[theme] }))
      .sort((x, y) => (y.b - y.a) - (x.b - x.a) || y.b - x.b)
      .filter((c, i, all) => chartAll || i < 12 || i >= all.length - 3);
    const max = Math.max(1, ...cos.flatMap(c => [c.a, c.b]));
    const W = 760, row = 22, top = 26, left = 64, right = 70, H = top + cos.length * row + 8;
    const x = v => left + (W - left - right) * v / max;
    const ticks = [0, Math.round(max / 2), max];
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Mentions of ${esc(theme)} per company, last filing and this filing">`;
    ticks.forEach(t => {
      s += `<line x1="${x(t)}" x2="${x(t)}" y1="${top - 6}" y2="${H - 4}" stroke="var(--rule)" stroke-width="1"/>`;
      s += `<text x="${x(t)}" y="${top - 12}" fill="var(--ink-2)" font-size="11" font-family="var(--f-mono)" text-anchor="middle">${t}</text>`;
    });
    cos.forEach((c, i) => {
      const y = top + i * row + row / 2, up = c.b > c.a, down = c.b < c.a;
      const col = up ? "var(--ins)" : down ? "var(--del)" : "var(--ink-2)";
      s += `<text x="${left - 10}" y="${y + 4}" fill="var(--ink)" font-size="12" font-weight="600" font-family="var(--f-mono)" text-anchor="end">${esc(c.t)}</text>`;
      s += `<line x1="${x(c.a)}" x2="${x(c.b)}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="2"/>`;
      s += `<circle cx="${x(c.a)}" cy="${y}" r="4" fill="var(--sheet)" stroke="var(--ink-2)" stroke-width="1.5"/>`;
      s += `<circle cx="${x(c.b)}" cy="${y}" r="4.5" fill="${col}"/>`;
      s += `<text x="${x(Math.max(c.a, c.b)) + 10}" y="${y + 4}" fill="${col}" font-size="11.5" font-family="var(--f-mono)">${c.a} → ${c.b}</text>`;
    });
    // The same numbers as a table, for screen readers.
    const rows = cos.map(c => `<tr><th scope="row">${esc(c.t)}</th><td>${c.a}</td><td>${c.b}</td></tr>`).join("");
    return s + `</svg><table class="sr-only"><caption>Mentions of ${esc(theme)}</caption><thead><tr><th scope="col">Company</th><th scope="col">Previous filing</th><th scope="col">Latest filing</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  const pct = (a, b) => Math.round(100 * a / Math.max(1, b));

  function findingHTML(t, n, open = false, lead = "") {
    const ex = t.examples.map(e => `<li>
        <div class="who"><a href="#${esc(e.ticker)}/${esc(e.id)}">${esc(e.ticker)}</a>${pill(e.status)}${e.label ? `<span class="ct ct-${e.label}">${CT[e.label]}</span>` : ""}<span>${esc(e.title)}</span></div>
        <blockquote>“${esc(e.sentence)}”</blockquote></li>`).join("");
    const others = t.tickers_up.filter(tk => !t.examples.some(e => e.ticker === tk));
    return `<details class="finding"${open ? " open" : ""}>
      <summary><h3>${esc(lead || t.theme)}</h3><span class="count num">${t.companies_up} of ${n}</span>
        <span class="meter" aria-hidden="true"><span style="width:${pct(t.companies_up, n)}%"></span></span>
        <span class="sub">companies added new or escalated language on ${esc(t.theme.toLowerCase())} (${t.risks_up} risk factors)${t.companies_down ? `; ${t.companies_down} cut or softened some` : ""}.</span></summary>
      <ul class="ex">${ex}${others.length ? `<li class="more">Also: ${others.map(tk => `<a href="#${esc(tk)}">${esc(tk)}</a>`).join(", ")}</li>` : ""}</ul>
    </details>`;
  }

  // One plain sentence per headline theme. Counts come from findings.json, never typed here.
  const LEAD = {
    "Artificial intelligence": "AI went from a footnote to a risk almost everyone names",
    "Tariffs and trade": "Tariffs are back in the risk factors",
    "Cybersecurity": "Cyber risk keeps growing",
  };

  const ASK_TRY = [
    "Which companies worry about tariffs on imports from China?",
    "What changed in Nvidia's export control risk this year?",
    "How does JPMorgan describe the risk of a cyberattack?",
  ];

  function askHTML() {
    return `<section class="ask" aria-labelledby="askh">
      <div class="section-head"><h2 id="askh">Ask the filings</h2><a href="#eval">How often it is right</a></div>
      <form id="askf" class="askf" autocomplete="off">
        <input id="askq" class="search" type="text" maxlength="300" placeholder="Ask about any S&amp;P 100 company's risks" aria-label="Your question">
        <button type="submit" class="showall">Ask</button>
      </form>
      <div class="chips ask-try">${ASK_TRY.map(q => `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
      <div id="askout" aria-live="polite"></div>
      <p class="chart-note">Answers come only from the risk factor sections of these filings, and every claim links to the sentence it rests on. An answer that cites anything the search did not return is blocked before you see it.</p>
    </section>`;
  }

  async function runAsk(q) {
    const out = view.querySelector("#askout");
    out.innerHTML = `<p class="empty">Searching the filings…</p>`;
    let body;
    try {
      const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.message || "Ask is unavailable right now.");
    } catch (e) {
      out.innerHTML = `<p class="empty">${esc(e.message)} <a href="#?q=${encodeURIComponent(q.split(" ").slice(0, 3).join(" "))}">Search the text instead</a>.</p>`;
      return;
    }
    const ans = esc(body.answer).replace(/\[(\d+)\]/g, (m, n) => `<sup><a href="#src${n}" class="cite" data-src="${n}">${n}</a></sup>`);
    const src = body.sources.map(s => `<li id="src${s.n}"><div class="who"><b class="num">${s.n}</b>${s.ticker ? `<a href="#${esc(s.ticker)}/${esc(s.risk.split(".")[1])}">${esc(s.ticker)}</a>` : ""}${s.status ? pill(s.status) : ""}<span>${s.kind === "previous" ? "Last year: " : ""}${esc(s.title)}</span></div><blockquote>“${esc(s.text)}”</blockquote></li>`).join("");
    out.innerHTML = `<div class="answer"><p>${ans}</p>${src ? `<ol class="ex srcs">${src}</ol>` : ""}
      <p class="chart-note num">${esc(body.model)} · ${(body.usage.ms / 1000).toFixed(1)} s · $${body.usage.usd.toFixed(4)}${body.cached ? " · answered before" : ""}</p></div>`;
    out.querySelectorAll("a.cite").forEach(a => a.addEventListener("click", e => {
      e.preventDefault();
      out.querySelector(`#src${a.dataset.src}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }));
  }

  function wireAsk() {
    const f = view.querySelector("#askf"), i = view.querySelector("#askq");
    if (!f) return;
    f.addEventListener("submit", e => { e.preventDefault(); if (i.value.trim().length >= 8) runAsk(i.value.trim()); });
    view.querySelectorAll(".ask-try [data-q]").forEach(b => b.addEventListener("click", () => { i.value = b.dataset.q; runAsk(b.dataset.q); }));
  }

  function renderHome() {
    const lg = document.querySelector(".legend"); if (lg) lg.hidden = true;
    document.title = "Risk Radar: what America's biggest companies are worried about";
    const F = FINDINGS, n = F.companies;
    const top = F.themes.filter(t => LEAD[t.theme]).map((t, k) => findingHTML(t, n, false, LEAD[t.theme])).join("");
    const rest = F.themes.filter(t => !LEAD[t.theme]).map(t => findingHTML(t, n)).join("");
    view.innerHTML = `<div style="display:grid;gap:40px">
      ${askHTML()}
      <section class="findings" aria-labelledby="fi"><div class="section-head"><h2 id="fi">This year's three biggest shifts</h2><a href="#eval">How accurate is this?</a></div>${top}</section>
      <section class="findings" aria-labelledby="mo"><div class="section-head"><h2 id="mo">Also moving</h2></div>${rest}</section>
      <p class="home-links"><a class="showall" href="#all">Browse all ${INDEX.companies.length} companies</a> <a class="showall" href="#all">Search the full text</a> <a class="showall" href="#eval">How we know it's right</a></p>
    </div>`;
    wireAsk();
  }

  // "How we know it's right": every number comes from data/eval.json (api/_tools/eval.mjs).
  const P = x => `${Math.round(100 * x)}%`;
  const CI = m => `<span class="num">${P(m.mean)}</span> <span class="ci num">(${P(m.lo)} to ${P(m.hi)})</span>`;

  async function renderEval() {
    document.title = "How we know it's right · Risk Radar";
    const E = await getJSON("data/eval.json");
    const M = E.models["claude-haiku-5-5-low"], R = E.retrieval;
    const rung = (k, label, note) => `<tr><th scope="row">${label}</th><td>${CI(R[k].r5)}</td><td class="num">${R[k].mrr.mean.toFixed(2)}</td><td>${note}</td></tr>`;
    const unans = M.declined_when_unanswerable;
    const fails = E.failures.map(f => `<li><div class="who"><b>${esc(f.verdict)}</b><span>${f.retrieved_gold ? "search found the right risk factor" : "search missed the right risk factor"}</span></div>
      <p class="q">${esc(f.question)}</p><blockquote>${esc(f.answer)}</blockquote>${f.reason ? `<p class="chart-note">Grader: ${esc(f.reason)}</p>` : ""}</li>`).join("");
    view.innerHTML = `<div style="display:grid;gap:36px">
      <button class="back" id="back" type="button">← Back</button>
      <header class="co-head"><h1>How we know it's right</h1>
        <p class="chart-note">${E.golden.n} test questions with known answers, ${E.golden.n - E.golden.answerable} of them deliberately unanswerable, run through the same search and agent that answer questions on this site.</p></header>
      <section class="tally num" aria-label="Headline numbers">
        <span><b>${P(M.correct.mean)}</b>answers correct</span>
        <span><b>${unans.mean * unans.n} of ${unans.n}</b>unanswerable questions declined</span>
        <span><b>${M.rejected_by_citation_check}</b>answers citing text the search never returned</span>
        <span><b>$${M.usd_per_answer.toFixed(4)}</b>per answer</span>
        <span><b>${(M.p50_ms / 1000).toFixed(1)} s</b>typical answer time</span>
      </section>
      <section style="display:grid;gap:12px"><h2>Answers</h2>
        <table class="acc"><thead><tr><th>Measure</th><th>Result (95% interval)</th></tr></thead><tbody>
          <tr><th scope="row">Correct, graded against the reference answer</th><td>${CI(M.correct)}</td></tr>
          <tr><th scope="row">Correct or partly correct</th><td>${CI(M.correct_or_partial)}</td></tr>
          <tr><th scope="row">Declined a question it could have answered</th><td>${CI(M.abstained_when_answerable)}</td></tr>
          <tr><th scope="row">Citations that point to the right risk factor</th><td>${CI(M.citation_precision)}</td></tr>
          <tr><th scope="row">Slowest 5% of answers</th><td class="num">${(M.p95_ms / 1000).toFixed(1)} s or faster</td></tr>
        </tbody></table>
        <p class="chart-note">Model: Claude Haiku 5.5 at low effort, the cheapest option, chosen because it already clears the bar. Running all ${E.golden.n} questions, grading included, cost $${E.eval_cost_usd.toFixed(2)}. A citation counts as off target when it points to a different risk factor than the one the question was written from, even if that sentence also supports the answer, so this measure undercounts.</p>
      </section>
      <section style="display:grid;gap:12px"><h2>Search</h2>
        <table class="acc"><thead><tr><th>Search method</th><th>Right risk factor in top 5</th><th>MRR</th><th></th></tr></thead><tbody>
          ${rung("bm25", "Keywords only (BM25)", "")}
          ${rung("dense", "Meaning only (bge-small embeddings)", "")}
          ${rung("hybrid", "Both, fused (RRF)", "")}
          ${rung("hybrid_company", "Both, limited to the company named", "what the agent does")}
        </tbody></table>
        <p class="chart-note">Scored over ${R.hybrid.r5.n} answerable questions. Fusing the two methods beats keywords alone (nDCG@10 up ${R.paired.hybrid_minus_bm25_ndcg.mean.toFixed(2)}, interval ${R.paired.hybrid_minus_bm25_ndcg.lo.toFixed(2)} to ${R.paired.hybrid_minus_bm25_ndcg.hi.toFixed(2)}); its edge over meaning-only search is within the noise. Limiting to the named company adds the most (${R.paired.company_filter_ndcg.mean.toFixed(2)}).</p>
      </section>
      <section style="display:grid;gap:12px"><h2>Every answer that was not fully correct</h2>
        <ol class="ex fails">${fails}</ol>
        <p class="chart-note">Pattern: both wrong answers and the one wrong refusal came from searches that missed the right risk factor, and the agent then said, correctly for what it had read, that the filings did not say. Several "partial" grades are for details the grader could not check against the cited sentences, because it sees only the reference answer.</p>
      </section>
      <section style="display:grid;gap:10px"><h2>What to keep in mind</h2>
        <p>The test questions and reference answers were written by Claude (Opus 5.5) from risk factors sampled at random, one per company, not by a person. Answers were graded by a second model (Claude Sonnet 5.5) against those references, and that grader has not been checked against human grades. With ${E.golden.answerable} answerable questions, differences smaller than about ten points are not meaningful. Each row of the test set and every graded answer are in the repository.</p>
      </section>
    </div>`;
    view.querySelector("#back").addEventListener("click", () => { location.hash = ""; });
    window.scrollTo(0, 0);
  }

  function findingsHTML() {
    if (!FINDINGS) return "";
    const F = FINDINGS, st = F.statuses, cl = F.change_labels;
    const n = F.companies;
    const rows = F.themes.map(t => findingHTML(t, n)).join("");
    const movers = F.movers.map(m => `<li><a href="#${esc(m.ticker)}"><b>${esc(m.ticker)}</b><span class="num">${m.up}</span></a></li>`).join("");
    return `<section class="findings" aria-labelledby="fi">
      <div class="section-head"><h2 id="fi">What moved across ${n} companies</h2></div>
      <p class="tally num"><span><b>${F.risks_current.toLocaleString()}</b>risk factors this year</span>
        <span><b>${(st.new || 0) + (st.split || 0)}</b>new or split off</span>
        <span><b>${(st.removed || 0) + (st.merged || 0)}</b>removed or merged</span>
        <span><b>${cl.new_exposure || 0}</b>edits adding a new exposure</span>
        <span><b>${cl.escalated || 0}</b>escalated</span>
        <span><b>${cl.de_escalated || 0}</b>softened</span></p>
      ${rows}
      <div class="section-head"><h2 style="font-size:18px">Most new, split off or escalated risks</h2></div>
      <ul class="movers">${movers}</ul>
    </section>`;
  }

  function renderBrowse() {
    const lg = document.querySelector(".legend"); if (lg) lg.hidden = false;
    document.title = "All companies · Risk Radar";
    const up = INDEX.companies.filter(c => c.themes.current[theme] > c.themes.previous[theme]).length;
    const q = coQuery.trim().toLowerCase();
    const sorted = INDEX.companies.slice().sort((a, b) =>
      (b.counts.new + b.counts.removed) - (a.counts.new + a.counts.removed) || b.counts.rewritten - a.counts.rewritten
    ).filter(c => !q || c.ticker.toLowerCase().startsWith(q) || c.company.toLowerCase().includes(q));
    const shown = q || coAll ? sorted : sorted.slice(0, 24);
    const cards = shown.map(c => {
      const items = c.new_titles.map(t => `<li class="n">${esc(t)}</li>`).concat(c.removed_titles.map(t => `<li class="r">${esc(t)}</li>`));
      return `<a class="co" href="#${esc(c.ticker)}">
        <div class="co-top"><span class="co-tk">${esc(c.ticker)}</span><span class="co-name">${esc(c.company)}</span></div>
        <div class="co-pills">${["new", "split", "removed", "merged", "rewritten", "edited"].filter(k => c.counts[k]).map(k => pill(k, c.counts[k])).join("")}</div>
        ${items.length ? `<ul>${items.slice(0, 4).join("")}</ul>` : `<p class="quiet">No risks added or removed. ${c.counts.unchanged} of ${c.current.risks} unchanged word for word.</p>`}
      </a>`;
    }).join("");
    const nAll = INDEX.companies.length;
    view.innerHTML = `
      <div style="display:grid;gap:44px">
      ${searchBox("", "all")}
      ${findingsHTML()}
      <section class="themes" aria-labelledby="th">
        <div class="section-head"><h2 id="th">How often each company mentions a theme</h2>
          <div class="chips" role="group" aria-label="Theme">${INDEX.themes.map(t => `<button class="chip" type="button" aria-pressed="${t === theme}" data-theme-name="${esc(t)}">${esc(t)}</button>`).join("")}</div>
        </div>
        <div class="chart">${themeChart()}</div>
        <p class="chart-note"><span class="num">${up}</span> of ${nAll} companies mention ${esc(theme.toLowerCase())} more often in their latest risk factors. Hollow dot: previous filing. Solid dot: latest. ${chartAll ? "" : "Showing the 12 biggest increases and 3 biggest decreases."}</p>
        <button class="showall" type="button" id="chartall">${chartAll ? "Show fewer" : `Show all ${nAll}`}</button>
      </section>
      <section aria-labelledby="co" style="display:grid;gap:14px"><div class="section-head"><h2 id="co">Companies, most changed first</h2>
          <input class="search" id="coq" type="search" placeholder="Find a ticker or company" aria-label="Find a ticker or company" value="${esc(coQuery)}"></div>
        <div class="companies">${cards || `<p class="empty">No company matches “${esc(coQuery)}”.</p>`}</div>
        ${!q && !coAll && sorted.length > 24 ? `<button class="showall" type="button" id="coall">Show all ${sorted.length}</button>` : ""}
      </section></div>`;
    view.querySelectorAll("[data-theme-name]").forEach(b => b.addEventListener("click", () => {
      theme = b.dataset.themeName;
      try { localStorage.setItem("rr-theme", theme); } catch (e) {}
      renderBrowse();
    }));
    wireSearch();
    view.querySelector("#chartall").addEventListener("click", () => { chartAll = !chartAll; renderBrowse(); });
    const all = view.querySelector("#coall");
    if (all) all.addEventListener("click", () => { coAll = true; renderBrowse(); });
    const qi = view.querySelector("#coq");
    qi.addEventListener("input", () => {
      coQuery = qi.value;
      renderBrowse();
      const n = view.querySelector("#coq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length);
    });
  }

  function riskBody(r) {
    if (r.diff) {
      const html = r.diff.map(([op, t]) => op === "+" ? `<ins>${esc(t)}</ins>` : op === "-" ? `<del>${esc(t)}</del>` : esc(t)).join("");
      const ot = r.old_title && r.old_title !== r.title ? `<div class="old-title">Last year's title: ${esc(r.old_title)}</div>` : "";
      return `<div class="doc">${ot}${html}</div>`;
    }
    const txt = r.status === "new" || r.status === "split" ? `<ins>${esc(r.body)}</ins>` : r.status === "removed" || r.status === "merged" ? `<del>${esc(r.body)}</del>` : esc(r.body);
    const pct = Math.round((r.reuse || 0) * 100);
    const link = r.status === "split" ? `<div class="old-title">Split off from last year's risk: ${esc(r.link_title)} (${pct}% of its phrases reused)</div>`
      : r.status === "merged" ? `<div class="old-title">Folded into this year's risk: ${esc(r.link_title)} (${pct}% of its phrases reused)</div>` : "";
    return `<div class="doc">${link}${txt}</div>`;
  }

  async function renderCompany(tk, target, term, cut) {
    const meta = INDEX.companies.find(c => c.ticker === tk);
    if (!meta) { location.hash = ""; return; }
    view.innerHTML = `<p class="empty">Loading ${esc(tk)}…</p>`;
    const d = await getJSON(`data/${tk}.json`);
    document.title = `${tk} · Risk Radar`;
    let show = new Set(["new", "split", "removed", "merged", "rewritten"]);
    const tr = target && d.risks.find(r => r.id === target);
    if (tr) show.add(tr.status);
    const total = d.risks.length;
    const draw = () => {
      const firstNew = d.risks.find(r => r.status === "new");
      const byCat = new Map();
      d.risks.filter(r => show.has(r.status)).forEach(r => {
        const k = r.category || "Uncategorized";
        if (!byCat.has(k)) byCat.set(k, []);
        byCat.get(k).push(r);
      });
      const list = [...byCat].map(([cat, rs]) => `<section class="cat"><h2>${esc(cat)}</h2>${rs.map(r =>
        `<details class="risk${r === tr ? " target" : ""}" id="r-${esc(r.id || "")}" data-st="${r.status}"${r === (tr || firstNew) ? " open" : ""}>
          <summary>${pill(r.status)}<span class="tt"><span class="t">${esc(r.title)}</span>${ctTag(r)}</span></summary>
          ${r.change ? `<div class="why"><b>What changed, per the classifier:</b> ${esc(r.change.reason)}</div>` : ""}
          ${riskBody(r)}
          ${r.match ? `<div class="meta num">match ${r.match.toFixed(2)} · ${Math.round(r.ratio * 100)}% of the words unchanged</div>` : ""}
        </details>`).join("")}</section>`).join("");
      view.querySelector("#risks").innerHTML = list || `<p class="empty">Nothing in this view. Pick another status above.</p>`;
      view.querySelectorAll("[data-st-filter]").forEach(b => b.setAttribute("aria-pressed", show.has(b.dataset.stFilter)));
    };
    view.innerHTML = `
      <div style="display:grid;gap:22px">
      <button class="back" type="button" id="back">← All companies</button>
      <div class="co-head">
        <span class="eyebrow">${esc(d.company)}</span>
        <h1 tabindex="-1">${esc(d.ticker)}: ${d.counts.new} new, ${d.counts.removed} removed, ${d.counts.rewritten} rewritten</h1>
        <div class="filings num">
          <span>Latest: fiscal ${yr(d.current.period_end)} · ${d.current.risks} risks · <a href="${esc(d.current.url)}" target="_blank" rel="noopener">filing on EDGAR</a></span>
          <span>Previous: fiscal ${yr(d.previous.period_end)} · ${d.previous.risks} risks · <a href="${esc(d.previous.url)}" target="_blank" rel="noopener">filing on EDGAR</a></span>
        </div>
        <div class="bar" role="img" aria-label="Share of risks by status">${ORDER.map(k => d.counts[k] ? `<span class="b-${k}" style="width:${100 * d.counts[k] / total}%"></span>` : "").join("")}</div>
      </div>
      <div class="chips" role="group" aria-label="Show risks that are">${ORDER.map(k => `<button class="chip" type="button" data-st-filter="${k}" aria-pressed="false">${LABEL[k]} <span class="num">${d.counts[k]}</span></button>`).join("")}</div>
      <div id="risks" style="display:grid;gap:18px"></div></div>`;
    view.querySelector("#back").addEventListener("click", () => { location.hash = ""; });
    view.querySelectorAll("[data-st-filter]").forEach(b => b.addEventListener("click", () => {
      const k = b.dataset.stFilter; show.has(k) ? show.delete(k) : show.add(k); draw();
    }));
    draw();
    const el = tr && view.querySelector(`#r-${tr.id}`);
    const mk = el && (term ? markTerm(el, term, cut) : markSentence(el, tr.id));
    // Move focus to the new page so keyboard and screen-reader users land on it.
    (el ? el.querySelector("summary") : view.querySelector(".co-head h1")).focus({ preventScroll: true });
    if (mk) mk.scrollIntoView({ block: "center" }); else if (el) el.scrollIntoView({ block: "start" }); else window.scrollTo(0, 0);
  }

  // Mark the sentence a front-page finding quoted, so the link lands on it.
  function markSentence(el, id) {
    const ex = FINDINGS && FINDINGS.themes.flatMap(t => t.examples).find(e => e.id === id);
    if (!ex) return null;
    const sent = ex.sentence.replace(/…$/, "");
    return markIn(el, false, full => { const at = full.indexOf(sent); return at < 0 ? null : [at, sent.length]; });
  }

  // Mark the first place a searched phrase appears: in this year's text, or
  // in the struck-out text when the search was for what was cut.
  function markTerm(el, term, cut) {
    const re = new RegExp((/^\w/.test(term) ? "\\b" : "") + reEsc(term).replace(/\s+/g, "\\s+"), "i");
    return markIn(el, cut, full => { const m = re.exec(full); return m ? [m.index, m[0].length] : null; });
  }

  function markIn(el, inDel, find) {
    // This year's text is every text node outside <del>; last year's cuts are
    // the nodes inside it. Mark each node's share of the match, so it can
    // straddle kept and added words.
    const doc = el.querySelector(".doc");
    const nodes = [];
    const walk = document.createTreeWalker(doc, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.parentElement.closest(".old-title")) continue;
      if (!!n.parentElement.closest("del") === inDel) nodes.push(n);
    }
    const full = nodes.map(n => n.data).join(inDel ? " " : "");
    const found = find(full);
    if (!found) return null;
    const [at, len] = found, sent = { length: len };
    let pos = 0, first = null;
    for (const n of nodes) {
      const a = Math.max(at, pos), b = Math.min(at + sent.length, pos + n.data.length);
      const len = n.data.length;
      if (a < b) {
        const r = document.createRange();
        r.setStart(n, a - pos); r.setEnd(n, b - pos);
        const m = document.createElement("mark");
        r.surroundContents(m);
        first = first || m;
      }
      pos += len + (inDel ? 1 : 0);
    }
    return first;
  }


  // Full-text search over every risk factor. The file is fetched the first
  // time someone searches, so the front page stays small.
  const MODES = { all: "Mentions", added: "In added text", cut: "In struck text" };
  // Suggestions, each in the view where it says something: what was written
  // in this year (agentic, the 2025 tax law, stablecoins) and what was cut.
  const TRY = [["agentic", "added"], ["One Big Beautiful Bill", "added"], ["stablecoin", "added"],
    ["COVID", "cut"], ["ESG", "cut"], ["tariff", "all"]];
  let SEARCH = null, searchTimer = 0;
  const loadSearch = () => SEARCH || (SEARCH = getJSON("data/search.json"));
  const reEsc = q => q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const searchHash = (q, mode) => "#?" + new URLSearchParams(mode === "all" ? { q } : { q, in: mode });

  function searchBox(q, mode) {
    const n = INDEX.companies.reduce((a, c) => a + c.current.risks, 0);
    return `<form class="fts" role="search" id="fts">
      <label for="ftq">Search all ${n.toLocaleString()} risk factors</label>
      <div class="fts-row">
        <input id="ftq" type="search" autocomplete="off" spellcheck="false" placeholder="A word or phrase, such as tariff" value="${esc(q)}">
        <div class="chips" role="group" aria-label="Show risk factors that">${Object.entries(MODES).map(([k, v]) =>
          `<button class="chip" type="button" data-mode="${k}" aria-pressed="${k === mode}">${v}</button>`).join("")}</div>
      </div>
      <p class="hint">Every result is a quote from the filing and opens on the full blackline. Added and struck text are the blue and red words of that blackline, so a reworded sentence counts as both. Try ${TRY.map(([t, m]) => `<button type="button" data-try="${esc(t)}" data-try-mode="${m}">${esc(t)}</button>${m === "all" ? "" : ` <span>(${MODES[m].toLowerCase()})</span>`}`).join(", ")}.</p>
    </form>`;
  }

  function wireSearch() {
    const form = view.querySelector("#fts");
    if (!form) return;
    const input = form.querySelector("#ftq");
    form.addEventListener("submit", e => e.preventDefault());
    const mode = () => form.querySelector("[data-mode][aria-pressed=true]").dataset.mode;
    const go = (now) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        const q = input.value.trim();
        const h = q ? searchHash(q, mode()) : "#all";
        if (location.hash !== h) history.replaceState(null, "", h);
        if (q) return renderSearch(q, mode());
        renderBrowse();
        const i = view.querySelector("#ftq");
        i.focus();
      }, now ? 0 : 220);
    };
    input.addEventListener("input", () => go(false));
    input.addEventListener("focus", loadSearch, { once: true });
    form.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => {
      form.querySelectorAll("[data-mode]").forEach(x => x.setAttribute("aria-pressed", x === b));
      if (input.value.trim()) go(true);
    }));
    form.querySelectorAll("[data-try]").forEach(b => b.addEventListener("click", () => {
      input.value = b.dataset.try;
      form.querySelectorAll("[data-mode]").forEach(x => x.setAttribute("aria-pressed", x.dataset.mode === b.dataset.tryMode));
      go(true);
    }));
  }

  // The sentence around a match, trimmed, with the match marked.
  function snippet(text, at, len) {
    let a = Math.max(text.lastIndexOf(". ", at), text.lastIndexOf("\n", at), text.lastIndexOf("•", at));
    a = a < 0 ? 0 : a + 1;
    let b = text.indexOf(". ", at + len);
    b = b < 0 ? text.length : b + 1;
    let pre = text.slice(a, at).trimStart(), post = text.slice(at + len, b).trimEnd();
    if (pre.length > 180) pre = "…" + pre.slice(-180).replace(/^\S*\s/, "");
    if (post.length > 220) post = post.slice(0, 220).replace(/\s\S*$/, "") + "…";
    return `${esc(pre)}<mark>${esc(text.substr(at, len))}</mark>${esc(post)}`;
  }

  function findIn(r, re, mode) {
    if (mode === "cut") {
      for (const t of r.d || []) { re.lastIndex = 0; const m = re.exec(t); if (m) return snippet(t, m.index, m[0].length); }
      return null;
    }
    if (r.s === "removed" || r.s === "merged") return null;
    re.lastIndex = 0;
    for (let m = re.exec(r.x); m; m = re.exec(r.x)) {
      if (mode === "all" || (r.a || []).some(([a, b]) => m.index >= a && m.index < b)) return snippet(r.x, m.index, m[0].length);
      if (!m[0].length) re.lastIndex++;
    }
    return null;
  }

  async function renderSearch(q, mode) {
    if (!view.querySelector("#fts")) {
      view.innerHTML = `<div style="display:grid;gap:22px">
        <button class="back" type="button" id="back">← Front page</button>
        ${searchBox(q, mode)}<p class="sr-only" id="hits-live" aria-live="polite"></p><div class="hits" id="hits"></div></div>`;
      view.querySelector("#back").addEventListener("click", () => { location.hash = ""; });
      wireSearch();
      const i = view.querySelector("#ftq");
      i.focus(); i.setSelectionRange(i.value.length, i.value.length);
    }
    let out = view.querySelector("#hits");
    if (!out) {
      // Typed into the front-page box: keep the box, swap what is under it.
      const form = view.querySelector("#fts");
      form.parentElement.querySelectorAll(":scope > :not(#fts)").forEach(n => n.remove());
      form.insertAdjacentHTML("beforebegin", `<button class="back" type="button" id="back">← Front page</button>`);
      view.querySelector("#back").addEventListener("click", () => { location.hash = ""; });
      form.insertAdjacentHTML("afterend", `<p class="sr-only" id="hits-live" aria-live="polite"></p><div class="hits" id="hits"></div>`);
      out = view.querySelector("#hits");
    }
    view.querySelectorAll("[data-mode]").forEach(x => x.setAttribute("aria-pressed", x.dataset.mode === mode));
    document.title = `“${q}” · Risk Radar`;
    out.innerHTML = `<p class="empty">Searching…</p>`;
    const S = await loadSearch();
    if (view.querySelector("#ftq").value.trim() !== q) return;
    const word = /^\w/.test(q) ? "\\b" : "";
    const re = new RegExp(word + reEsc(q).replace(/\s+/g, "\\s+"), "gi");
    const by = new Map();
    let total = 0;
    for (const r of S.risks) {
      const snip = findIn(r, re, mode);
      if (!snip) continue;
      total++;
      if (!by.has(r.t)) by.set(r.t, []);
      by.get(r.t).push({ r, snip });
    }
    const n = INDEX.companies.length;
    const groups = [...by].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
    const term = encodeURIComponent(q) + (mode === "cut" ? "/cut" : "");
    const hit = ({ r, snip }) => `<a class="hit${mode === "cut" ? " cut" : ""}" href="#${esc(r.t)}/${esc(r.i)}/${term}">
        <span class="ht">${pill(r.s)}${r.c ? `<span class="ct ct-${r.c}">${CT[r.c]}</span>` : ""}<span>${esc(r.h)}</span></span>
        <q>${snip}</q></a>`;
    const what = { all: "mention", added: "added text that mentions", cut: "struck text that mentioned" }[mode];
    view.querySelector("#hits-live").textContent = total
      ? `${by.size} companies, ${total} risk factors.` : "No results.";
    out.innerHTML = total ? `<p class="hits-sum"><b class="num">${by.size}</b> of ${n} companies ${what} “${esc(q)}”${mode === "all" ? "" : " this year"}, in <b class="num">${total}</b> risk factor${total === 1 ? "" : "s"}.</p>
      ${groups.map(([tk, hs]) => `<section class="hit-co">
        <div><span class="co-tk"><a href="#${esc(tk)}">${esc(tk)}</a></span><span class="co-n">${esc(S.companies[tk])} · ${hs.length} risk factor${hs.length === 1 ? "" : "s"}</span></div>
        ${hs.slice(0, 2).map(hit).join("")}
        ${hs.length > 2 ? `<details><summary>${hs.length - 2} more at ${esc(tk)}</summary>${hs.slice(2).map(hit).join("")}</details>` : ""}
      </section>`).join("")}`
      : `<p class="empty">No risk factor ${mode === "all" ? "mentions" : mode === "added" ? "added text that mentions" : "struck text that mentioned"} “${esc(q)}”${mode === "all" ? "" : " this year"}.${mode !== "all" ? ` <a href="${searchHash(q, "all")}">See every mention</a>.` : ""}</p>`;
  }

  function route() {
    const lg = document.querySelector(".legend"); if (lg) lg.hidden = false;
    const h = location.hash.slice(1);
    if (h.startsWith("?")) {
      const p = new URLSearchParams(h.slice(1));
      const q = (p.get("q") || "").trim(), mode = MODES[p.get("in")] ? p.get("in") : "all";
      if (q) {
        if (view.querySelector("#ftq")?.value.trim() !== q) view.innerHTML = "";
        return renderSearch(q, mode).catch(fail);
      }
    }
    const [tk, target, term, side] = h.split("/").map(x => { try { return decodeURIComponent(x); } catch (e) { return x; } });
    (tk === "eval" ? renderEval() : tk === "all" ? Promise.resolve(renderBrowse()) : tk && !h.startsWith("?") ? renderCompany(tk, target, term, side === "cut") : Promise.resolve(renderHome())).catch(fail);
  }
  function fail(err) {
      view.innerHTML = `<p class="empty">Could not load the data (${esc(err.message)}). Reload the page to try again.</p>`;
  }

  Promise.all([getJSON("data/index.json"), getJSON("data/findings.json").catch(() => null)]).then(([ix, fi]) => {
    INDEX = ix;
    FINDINGS = fi;
    const sk = (ix.skipped || []).length;
    const skl = document.getElementById("skipped");
    if (skl && sk) skl.innerHTML = `Left out: ${ix.skipped.map(x => `${esc(x.company)} (${esc(x.reason)})`).join("; ")}.`;
    let saved = null;
    try { saved = localStorage.getItem("rr-theme"); } catch (e) {}
    theme = ix.themes.includes(saved) ? saved : ix.themes[0];
    window.addEventListener("hashchange", route);
    route();
  }).catch(err => { view.innerHTML = `<p class="empty">Could not load the data (${esc(err.message)}).</p>`; });
})();
