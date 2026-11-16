// Ask: posts the question to /api/ask and shows the answer with its numbered sources. Before the
// first question it shows a real earlier answer (data/example.json), labelled as such.
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const out = document.getElementById("askout"), list = document.getElementById("asksrc"), form = document.getElementById("askf"), input = document.getElementById("askq");

function render(body, q, earlier) {
  const ans = esc(body.answer).replace(/\[(\d+)\]/g, (m, n) => `<sup><a href="#src${n}" class="cite">${n}</a></sup>`);
  const src = body.sources.map(s => {
    const link = s.ticker ? `<a href="browse.html#${encodeURIComponent(s.ticker)}/${encodeURIComponent(s.risk.split(".")[1])}">${esc(s.ticker)}</a>` : "";
    const year = s.kind === "previous" ? "last year's filing" : "this year's filing";
    return `<li id="src${s.n}"><span class="src__n">${s.n}</span><div><p class="src__who">${link} · ${year} · ${esc(s.title)}</p><blockquote>${esc(s.text)}</blockquote></div></li>`;
  }).join("");
  const u = body.usage || {};
  out.innerHTML = `<p class="ask-q">${earlier ? "An earlier question: " : ""}${esc(q)}</p>
    <div class="ask-a"><p>${ans}</p></div>
    <p class="ask-meta">${esc(body.model || "")} · ${((u.ms || 0) / 1000).toFixed(1)} s · $${(u.usd || 0).toFixed(4)} · ${body.sources.length} cited sentence${body.sources.length === 1 ? "" : "s"}</p>`;
  list.innerHTML = src;
}

async function ask(q) {
  out.innerHTML = `<p class="ask-wait">Searching both years of filings…</p>`;
  list.innerHTML = "";
  try {
    const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.message || "Ask is unavailable right now.");
    render(body, q, false);
  } catch (e) {
    out.innerHTML = `<p class="ask-wait">${esc(e.message)} <a class="link" href="browse.html#?q=${encodeURIComponent(q.split(" ").slice(0, 3).join(" "))}">Search the text instead</a></p>`;
  }
}

form.addEventListener("submit", e => { e.preventDefault(); const q = input.value.trim(); if (q.length >= 8) ask(q); else input.focus(); });
document.querySelectorAll(".ask-try [data-q]").forEach(b => b.addEventListener("click", () => { input.value = b.dataset.q; ask(b.dataset.q); }));
// The example answer is written into ask.html at build time, so it shows without script.
