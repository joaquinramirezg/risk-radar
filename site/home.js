// Home: the 102 tiles. A theme lights the companies that added or expanded it (ESG: struck where the
// term was dropped); a tile opens that company's new and removed risks. All counts from site/data.
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Old deep links (/#NVDA, /#eval, /#all, /#?q=) now live on browse.html.
const keep = new Set(["", "#top", "#board", "#esg", "#contact"]);
if (!keep.has(location.hash)) location.replace("browse.html" + location.hash);

const SHORT = { "Artificial intelligence": "AI", "Tariffs and trade": "tariff", "Cybersecurity": "cyber" };

Promise.all(["index", "findings", "faded"].map(n => fetch(`data/${n}.json`).then(r => r.json()))).then(([ix, fi, fa]) => {
  const grid = document.getElementById("tiles"), count = document.querySelector(".board__count"), pick = document.getElementById("pick");
  const cos = ix.companies;
  const n = cos.length;
  grid.innerHTML = cos.map((c, i) => `<button type="button" class="rr-t" style="--i:${i}" data-t="${esc(c.ticker)}" aria-pressed="false" aria-label="${esc(c.company)}">${esc(c.ticker)}</button>`).join("");
  const tiles = [...grid.children];

  function show(theme) {
    document.querySelectorAll(".board__themes button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.theme === theme)));
    if (theme === "ESG") {
      const e = fa.find(t => t.theme === "ESG"), gone = new Set(e.tickers_gone);
      tiles.forEach(t => { t.classList.toggle("is-on", false); t.classList.toggle("is-cut", gone.has(t.dataset.t)); t.classList.remove("is-kept"); });
      count.innerHTML = `<b class="num">${e.gone}</b>of the ${e.had} that named ESG dropped the term`;
      return;
    }
    const t = fi.themes.find(x => x.theme === theme), up = new Set(t.tickers_up);
    tiles.forEach(el => { el.classList.toggle("is-on", up.has(el.dataset.t)); el.classList.remove("is-cut", "is-kept"); });
    count.innerHTML = `<b class="num">${t.companies_up}</b>of ${n} added or expanded ${SHORT[theme]} risk`;
  }

  async function open(tk) {
    tiles.forEach(t => t.setAttribute("aria-pressed", String(t.dataset.t === tk)));
    const c = cos.find(x => x.ticker === tk);
    const d = await fetch(`data/${tk}.json`).then(r => r.json());
    const added = d.risks.filter(r => r.status === "new" || r.status === "split");
    const gone = d.risks.filter(r => r.status === "removed" || r.status === "merged");
    const items = [...added.map(r => `<li><ins class="rl">${esc(r.title)}</ins></li>`), ...gone.map(r => `<li><del class="rl">${esc(r.title)}</del></li>`)];
    const k = c.counts;
    pick.innerHTML = `<div class="span-6"><h3>${esc(c.company)}</h3>
        <p class="co-pick__meta">${esc(tk)} · ${k.new + k.split} new · ${k.removed + k.merged} removed · ${k.rewritten} rewritten</p>
        <a class="link" href="browse.html#${encodeURIComponent(tk)}">Read the full redline</a></div>
      <ul class="span-6 start-7">${items.slice(0, 3).join("") || `<li>No risk added or removed. ${k.rewritten + k.edited} were reworded.</li>`}</ul>`;
  }

  document.querySelectorAll(".board__themes button").forEach(b => b.addEventListener("click", () => show(b.dataset.theme)));
  grid.addEventListener("click", e => { const t = e.target.closest(".rr-t"); if (t) open(t.dataset.t); });
  show("Artificial intelligence");
  open("NVDA");
}).catch(() => {});
