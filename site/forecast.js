// Forecast: the 102 tiles shaded by each company's chance that its next 10-K adds or escalates the
// chosen theme (data/forecast.json). Once a company's 10-K is scored (data/forecast_score.json),
// its tile shows whether the theme was added. Every number comes from those files.
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SHORT = {
  "Artificial intelligence": "AI", "Tariffs and trade": "Tariffs", "Cybersecurity": "Cyber", "China": "China",
  "Export controls": "Export controls", "Climate": "Climate", "Interest rates and credit": "Rates and credit",
  "Government shutdown and spending": "Shutdown",
};
const pct = p => `${Math.round(100 * p)}%`;
const opt = n => fetch(`data/${n}.json`).then(r => (r.ok ? r.json() : null)).catch(() => null);

Promise.all(["index", "forecast", "forecast_score"].map(opt)).then(([ix, fc, sc]) => {
  if (!ix || !fc) return;
  const status = document.getElementById("fc-status");
  status.textContent = fc.status === "frozen"
    ? `Frozen ${fc.frozen}, before any of these 10-Ks were filed`
    : "Draft · freezes before January 31, 2027";

  const grid = document.getElementById("tiles"), count = document.querySelector(".board__count"), pick = document.getElementById("pick");
  const by = new Map(fc.forecasts.map(f => [`${f.ticker}|${f.theme}`, f]));
  const done = new Map((sc?.resolved || []).map(r => [`${r.ticker}|${r.theme}`, r.y]));
  const cos = ix.companies;
  grid.innerHTML = cos.map((c, i) => `<button type="button" class="rr-t fc-t" style="--i:${i}" data-t="${esc(c.ticker)}" aria-pressed="false">${esc(c.ticker)}</button>`).join("");
  const tiles = [...grid.children];
  const themes = document.getElementById("fc-themes");
  themes.innerHTML = fc.themes.map(t => `<button type="button" data-theme="${esc(t)}" aria-pressed="false">${esc(SHORT[t] || t)}</button>`).join("");
  let theme = fc.themes[0];

  function show(t) {
    theme = t;
    themes.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.theme === t)));
    let likely = 0;
    tiles.forEach(el => {
      const f = by.get(`${el.dataset.t}|${t}`), y = done.get(`${el.dataset.t}|${t}`);
      el.classList.toggle("is-none", !f);
      el.dataset.b = f ? String(Math.min(4, Math.floor(f.p * 5))) : "";
      el.dataset.y = y === undefined ? "" : String(y);
      el.setAttribute("aria-label", `${el.dataset.t}: ${f ? pct(f.p) : "not forecast"}${y === undefined ? "" : y ? ", added" : ", not added"}`);
      if (f && f.p >= 0.5) likely++;
    });
    const n = new Set(fc.forecasts.map(f => f.ticker)).size;
    count.innerHTML = `<b class="num">${likely}</b>of ${n} companies are more likely than not to add or escalate ${esc(SHORT[t] || t)} risk`;
  }

  function open(tk) {
    tiles.forEach(el => el.setAttribute("aria-pressed", String(el.dataset.t === tk)));
    const c = cos.find(x => x.ticker === tk);
    const f = by.get(`${tk}|${theme}`);
    const head = pick.querySelector("div"), why = pick.querySelector(".fc-why");
    if (!f) {
      head.innerHTML = `<p class="co-pick__name">${esc(c.company)}</p><p class="co-pick__meta">${esc(tk)} · not forecast</p>`;
      why.textContent = "Its next 10-K came out before the forecast was made, so there is nothing left to forecast.";
      return;
    }
    head.innerHTML = `<p class="co-pick__name">${esc(c.company)}</p><p class="co-pick__meta">${esc(tk)} · ${esc(SHORT[theme] || theme)} ${pct(f.p)} · base rate ${pct(f.b0)}</p>`;
    why.textContent = `Moved most because ${f.reason}.`;
  }

  // The hero card: one company's chance on every theme (the likeliest company for the first theme).
  const top = fc.forecasts.filter(f => f.theme === fc.themes[0]).sort((a, b) => b.p - a.p)[0];
  const showcase = by.has(`NVDA|${fc.themes[0]}`) ? "NVDA" : top.ticker;
  const card = document.getElementById("fc-card");
  const rows = fc.themes.map(t => by.get(`${showcase}|${t}`)).filter(Boolean);
  card.innerHTML = `<p class="ladder__k">${esc(cos.find(x => x.ticker === showcase).company)} · chance its next 10-K adds or escalates</p>`
    + rows.map(r => `<div class="ladder__row"><span>${esc(SHORT[r.theme] || r.theme)}</span><i style="--v:${Math.round(100 * r.p)}%"></i><b>${pct(r.p)}</b></div>`).join("")
    + `<p class="fc-card__why">${esc(SHORT[rows[0].theme])}: moved most because ${esc(rows[0].reason)}.</p>`;

  themes.addEventListener("click", e => { const b = e.target.closest("button"); if (b) { show(b.dataset.theme); open(pick.dataset.t); } });
  grid.addEventListener("click", e => { const t = e.target.closest(".rr-t"); if (t) { pick.dataset.t = t.dataset.t; open(t.dataset.t); } });
  show(theme);
  // The backtest by theme: the model's Brier score next to the base rate's (shorter bar is better).
  const bt = fc.backtest.by_theme || {};
  const worst = Math.max(...Object.values(bt).map(v => Math.max(v.model, v.B0)), 0.01);
  document.getElementById("fc-bt").innerHTML = `<p class="ladder__k">Brier score by theme, last year's 10-Ks · the line marks each theme's share</p>`
    + fc.themes.filter(t => bt[t]).map(t => `<div class="ladder__row fc-bt"><span>${esc(SHORT[t] || t)}</span>`
      + `<i style="--v:${Math.round(100 * bt[t].model / worst)}%;--m:${Math.round(100 * bt[t].B0 / worst)}%"></i>`
      + `<b>${bt[t].model.toFixed(2)}</b></div>`).join("");

  pick.dataset.t = showcase;
  open(showcase);
});
