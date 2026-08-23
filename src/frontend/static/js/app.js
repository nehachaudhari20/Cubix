/* Payment Defense Twin — app shell: routing, fetch helpers, shared renderers. */

window.PDT = (function () {
  const pages = {};
  let current = null;

  /* ── fetch ── */
  async function get(url) {
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  }

  async function post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  }

  /* ── formatting ── */
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  function num(v, digits = 2) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return Number(v).toFixed(digits);
  }

  function pct(v, digits = 1) {
    if (v === null || v === undefined) return "—";
    return (Number(v) * 100).toFixed(digits) + "%";
  }

  function money(v) {
    if (v === null || v === undefined) return "—";
    return "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }

  function time(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function date(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString([], {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function titleize(s) {
    return String(s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function delta(v, digits = 4) {
    if (v === null || v === undefined) return '<span class="delta flat">—</span>';
    const cls = v > 0 ? "up" : v < 0 ? "down" : "flat";
    const sign = v > 0 ? "+" : "";
    return `<span class="delta ${cls}">${sign}${Number(v).toFixed(digits)}</span>`;
  }

  /* ── syntax-highlighted JSON ── */
  function jsonView(obj) {
    const raw = JSON.stringify(obj, null, 2) || "";
    const html = esc(raw)
      .replace(/&quot;([^&]+?)&quot;(\s*:)/g, '<span class="json-key">"$1"</span>$2')
      .replace(/:\s&quot;(.*?)&quot;/g, ': <span class="json-str">"$1"</span>')
      .replace(/:\s(-?\d+\.?\d*)/g, ': <span class="json-num">$1</span>')
      .replace(/:\s(true|false)/g, ': <span class="json-bool">$1</span>')
      .replace(/:\s(null)/g, ': <span class="json-null">$1</span>');
    return `<div class="json-view">${html}</div>`;
  }

  /* ── shared bits ── */
  function chips(items, cls = "") {
    if (!items || !items.length) return '<span class="hint">none</span>';
    return `<div class="chiplist">${items
      .map((i) => `<span class="chip ${cls}">${esc(i)}</span>`)
      .join("")}</div>`;
  }

  function scoreBar(label, value, cls, threshold) {
    const v = value === null || value === undefined ? 0 : Number(value);
    const mark =
      threshold !== undefined && threshold !== null
        ? `<div class="score-threshold" style="left:${Math.min(100, threshold * 100)}%"></div>`
        : "";
    return `
      <div class="score-bar">
        <div class="score-bar-head"><span>${esc(label)}</span><b>${num(v, 3)}</b></div>
        <div class="score-track">
          <div class="score-fill ${cls}" style="width:${Math.min(100, v * 100)}%"></div>${mark}
        </div>
      </div>`;
  }

  function decisionChip(d) {
    const cls = { ALLOW: "red", CHALLENGE: "amber", BLOCK: "green", PASS: "blue" }[d] || "";
    return `<span class="chip ${cls}">${esc(d)}</span>`;
  }

  /* ── routing ── */
  function register(name, handlers) {
    pages[name] = handlers;
  }

  function route() {
    const name = (location.hash.replace("#/", "") || "overview").split("?")[0];
    const page = pages[name] ? name : "overview";

    document.querySelectorAll(".page").forEach((el) => el.classList.add("hidden"));
    const el = document.getElementById(`page-${page}`);
    if (el) el.classList.remove("hidden");

    document.querySelectorAll("#mainnav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.page === page);
    });

    if (current && pages[current] && pages[current].leave) pages[current].leave();
    current = page;
    if (pages[page] && pages[page].enter) pages[page].enter();

    window.scrollTo(0, 0);
  }

  function refresh() {
    if (current && pages[current] && pages[current].enter) pages[current].enter();
  }

  function start() {
    window.addEventListener("hashchange", route);
    const btn = document.getElementById("refresh-btn");
    if (btn) btn.addEventListener("click", refresh);
    route();
  }

  return {
    get, post, esc, num, pct, money, time, date, titleize, delta,
    jsonView, chips, scoreBar, decisionChip, register, start, refresh,
  };
})();
