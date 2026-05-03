/* trader-edge frontend JS — vanilla, no framework, no AI flourishes. */

const API = "/api/v1";

const fmt = {
  pct(x, digits = 0) { return (x * 100).toFixed(digits) + "%"; },
  rs(x, digits = 2)  {
    const sign = x > 0 ? "+" : x < 0 ? "−" : "";
    return sign + "₹" + Math.abs(x).toLocaleString("en-IN", {
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
  },
  rsPlain(x, digits = 2) {
    return "₹" + x.toLocaleString("en-IN", {
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
  },
  date(s) { return s; },
};

const evClass = (x) => x > 0 ? "pos" : x < 0 ? "neg" : "";
const probClass = (p, hi = 0.55, mid = 0.35) =>
  p > hi ? "neg" : p > mid ? "warn" : "pos";

/* ---------- bootstrap ---------- */

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupAnalyze();
  setupChain();
  setupJournal();
  await loadMeta();
});

async function loadMeta() {
  try {
    const [h, s] = await Promise.all([
      fetch(`${API}/health`).then(r => r.json()),
      fetch(`${API}/symbols`).then(r => r.json()),
    ]);
    document.getElementById("provider-badge").textContent = `data: ${h.provider}`;
    document.getElementById("version-badge").textContent  = `v${h.version}`;
    const dl = document.getElementById("symbol-list");
    dl.innerHTML = s.symbols.map(x => `<option value="${x}"></option>`).join("");
  } catch (e) {
    document.getElementById("provider-badge").textContent = "data: unavailable";
  }
}

/* ---------- tabs ---------- */

function setupTabs() {
  const links = document.querySelectorAll(".topnav a");
  links.forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      const tab = a.dataset.tab;
      links.forEach(x => x.classList.toggle("active", x === a));
      document.querySelectorAll(".view").forEach(v => {
        v.classList.toggle("hidden", v.id !== `view-${tab}`);
      });
    });
  });
}

/* ---------- analyze ---------- */

function setupAnalyze() {
  document.getElementById("analyze-form").addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      symbol: fd.get("symbol"),
      entry: Number(fd.get("entry")),
      target: Number(fd.get("target")),
      stop: Number(fd.get("stop")),
      horizon_days: Number(fd.get("horizon_days")),
      quantity: Number(fd.get("quantity")),
    };
    const panel = document.getElementById("result-panel");
    panel.innerHTML = `<h2 class="rule">Result</h2><p class="loading">computing…</p>`;
    const submitBtn = e.target.querySelector("button");
    submitBtn.disabled = true;
    try {
      const r = await fetch(`${API}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "request failed" }));
        panel.innerHTML = `<h2 class="rule">Result</h2><p class="neg">${escape(err.detail || "error")}</p>`;
        return;
      }
      renderAnalysis(panel, await r.json());
    } catch (e) {
      panel.innerHTML = `<h2 class="rule">Result</h2><p class="neg">Network error: ${escape(e.message)}</p>`;
    } finally {
      submitBtn.disabled = false;
    }
  });
}

function renderAnalysis(panel, v) {
  const req = v.request;
  const ev = v.ev_realworld.net_ev_per_share;
  const total = ev * req.quantity;
  const verdictWord =
    ev > 0.5 ? "EDGE PRESENT" :
    ev > 0   ? "MARGINAL"     :
               "NO EDGE";

  panel.innerHTML = `
    <h2 class="rule">${escape(req.symbol)} long bracket &middot;
      ${fmt.rsPlain(req.entry)} → ${fmt.rsPlain(req.target)} /
      ${fmt.rsPlain(req.stop)} &middot; ${req.horizon_days}d</h2>

    <div class="headline">
      <div class="cell">
        <div class="label">Verdict</div>
        <div class="value ${evClass(ev)}">${verdictWord}</div>
      </div>
      <div class="cell">
        <div class="label">Net EV / share</div>
        <div class="value ${evClass(ev)}">${fmt.rs(ev)}</div>
      </div>
      <div class="cell">
        <div class="label">For ${req.quantity}q</div>
        <div class="value ${evClass(total)}">${fmt.rs(total)}</div>
      </div>
    </div>

    <h3 class="section">Noise stop check</h3>
    <dl class="kv">
      <dt>Realized vol (annualized)</dt>
        <dd>${fmt.pct(v.noise.sigma_realized_annual, 1)}</dd>
      <dt>P(stop hit by noise alone)</dt>
        <dd class="${probClass(v.noise.p_stop_hit_noise)}">${fmt.pct(v.noise.p_stop_hit_noise)}</dd>
      <dt>Noise-safe stop (~30%)</dt>
        <dd>${fmt.rsPlain(v.noise.min_safe_stop)}</dd>
    </dl>

    <h3 class="section">Options-chain oracle &middot; expiry ${v.implied.expiry}</h3>
    <dl class="kv">
      <dt>ATM implied vol</dt><dd>${fmt.pct(v.implied.atm_iv, 1)}</dd>
      <dt>IV at target</dt><dd>${fmt.pct(v.implied.iv_at_target, 1)}</dd>
      <dt>IV at stop</dt><dd>${fmt.pct(v.implied.iv_at_stop, 1)}</dd>
      <dt>P(touch target)</dt>
        <dd>${fmt.pct(v.implied.p_touch_target)} <span class="muted">(real-world ~${fmt.pct(v.implied.p_touch_target_realworld)})</span></dd>
      <dt>P(touch stop)</dt>
        <dd class="${probClass(v.implied.p_touch_stop)}">${fmt.pct(v.implied.p_touch_stop)} <span class="muted">(real-world ~${fmt.pct(v.implied.p_touch_stop_realworld)})</span></dd>
    </dl>

    <h3 class="section">Who hits first &middot; Monte Carlo at implied vol</h3>
    <dl class="kv">
      <dt>P(target first)</dt><dd class="pos">${fmt.pct(v.joint.p_target_first)}</dd>
      <dt>P(stop first)</dt><dd class="neg">${fmt.pct(v.joint.p_stop_first)}</dd>
      <dt>P(neither in horizon)</dt><dd>${fmt.pct(v.joint.p_neither)}</dd>
      <dt>Expected exit</dt><dd>day ${v.joint.expected_exit_days.toFixed(1)}</dd>
    </dl>

    <h3 class="section">Expected value</h3>
    <dl class="kv">
      <dt>Headline R:R</dt><dd>${v.ev_riskneutral.headline_rr.toFixed(2)} : 1</dd>
      <dt>True R:R (joint)</dt><dd>${v.ev_riskneutral.true_rr.toFixed(2)} : 1</dd>
      <dt>EV (risk-neutral)</dt>
        <dd class="${evClass(v.ev_riskneutral.net_ev_per_share)}">${fmt.rs(v.ev_riskneutral.net_ev_per_share)} / share</dd>
      <dt>EV (real-world, VRP-adjusted)</dt>
        <dd class="${evClass(v.ev_realworld.net_ev_per_share)}">${fmt.rs(v.ev_realworld.net_ev_per_share)} / share</dd>
    </dl>

    ${v.notes.length ? `
      <div class="notes">
        <ul>${v.notes.map(n => `<li>${escape(n)}</li>`).join("")}</ul>
      </div>` : ""}

    ${v.suggestions.length ? `
      <h3 class="section">Alternatives</h3>
      <ol class="suggestions">
        ${v.suggestions.map((s, i) => `
          <li>
            <span class="idx">${(i + 1).toString().padStart(2, "0")}</span>
            <div>
              <div class="label">${escape(s.label)}</div>
              <div class="detail">${escape(s.detail)}</div>
            </div>
          </li>
        `).join("")}
      </ol>
    ` : ""}
  `;
}

/* ---------- chain ---------- */

function setupChain() {
  document.getElementById("chain-form").addEventListener("submit", async e => {
    e.preventDefault();
    const sym = document.getElementById("csymbol").value.trim().toUpperCase();
    const out = document.getElementById("chain-result");
    out.innerHTML = `<p class="loading">fetching ${escape(sym)}…</p>`;
    try {
      const r = await fetch(`${API}/chain/${encodeURIComponent(sym)}`);
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "not found" }));
        out.innerHTML = `<p class="neg">${escape(err.detail)}</p>`;
        return;
      }
      const ch = await r.json();
      const rows = ch.rows.map(r => {
        const atm = Math.abs(r.strike - ch.spot) < (ch.spot * 0.005);
        return `<tr class="${atm ? "atm" : ""}">
          <td>${r.strike.toFixed(2)}</td>
          <td>${r.call_bid.toFixed(2)}</td>
          <td>${r.call_ask.toFixed(2)}</td>
          <td>${r.call_oi.toLocaleString("en-IN")}</td>
          <td>${r.put_bid.toFixed(2)}</td>
          <td>${r.put_ask.toFixed(2)}</td>
          <td>${r.put_oi.toLocaleString("en-IN")}</td>
        </tr>`;
      }).join("");
      out.innerHTML = `
        <p class="muted">${escape(ch.symbol)} &middot; spot ${fmt.rsPlain(ch.spot)} &middot; expiry ${ch.expiry}</p>
        <table class="data">
          <thead><tr>
            <th>Strike</th><th>CE Bid</th><th>CE Ask</th><th>CE OI</th>
            <th>PE Bid</th><th>PE Ask</th><th>PE OI</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>`;
    } catch (e) {
      out.innerHTML = `<p class="neg">Network error: ${escape(e.message)}</p>`;
    }
  });
}

/* ---------- journal ---------- */

function setupJournal() {
  document.getElementById("journal-form").addEventListener("submit", async e => {
    e.preventDefault();
    const days = document.getElementById("jdays").value;
    const out = document.getElementById("journal-result");
    out.innerHTML = `<p class="loading">scoring…</p>`;
    try {
      const r = await fetch(`${API}/journal?days=${encodeURIComponent(days)}`);
      const j = await r.json();
      const wr = j.win_rate;
      const exp = j.expectancy;
      const pf = j.profit_factor;
      out.innerHTML = `
        <div class="headline">
          <div class="cell">
            <div class="label">Trades (W / L)</div>
            <div class="value">${j.n_trades}<span class="muted"> &nbsp;${j.n_winners}/${j.n_losers}</span></div>
          </div>
          <div class="cell">
            <div class="label">Win rate</div>
            <div class="value ${wr >= 0.5 ? "pos" : "neg"}">${fmt.pct(wr)}</div>
          </div>
          <div class="cell">
            <div class="label">Expectancy / trade</div>
            <div class="value ${evClass(exp)}">${fmt.rs(exp)}</div>
          </div>
        </div>

        <dl class="kv">
          <dt>Average winner</dt><dd class="pos">${fmt.rs(j.avg_win)}</dd>
          <dt>Average loser</dt><dd class="neg">${fmt.rs(j.avg_loss)}</dd>
          <dt>Profit factor</dt><dd class="${pf >= 1 ? "pos" : "neg"}">${pf.toFixed(2)}</dd>
          <dt>Median hold (winners)</dt><dd>${j.median_winner_hold_days.toFixed(0)}d</dd>
          <dt>Median hold (losers)</dt><dd>${j.median_loser_hold_days.toFixed(0)}d</dd>
        </dl>

        ${j.leaks.length ? `
          <div class="notes">
            <ul>${j.leaks.map(l => `<li>${escape(l)}</li>`).join("")}</ul>
          </div>` : ""}

        ${j.trades.length ? renderTradesTable(j.trades) : ""}
      `;
    } catch (e) {
      out.innerHTML = `<p class="neg">Network error: ${escape(e.message)}</p>`;
    }
  });
}

function renderTradesTable(trades) {
  const rows = trades.map(t => {
    const pnlCls = t.pnl == null ? "muted" : t.pnl > 0 ? "pos" : "neg";
    return `<tr>
      <td style="text-align:left">${escape(t.symbol)}</td>
      <td style="text-align:left">${escape(t.side)}</td>
      <td>${t.entry_date}</td>
      <td>${t.exit_date || "—"}</td>
      <td>${t.entry_price.toFixed(2)}</td>
      <td>${t.exit_price ? t.exit_price.toFixed(2) : "—"}</td>
      <td>${t.quantity}</td>
      <td class="${pnlCls}">${t.pnl == null ? "open" : fmt.rs(t.pnl)}</td>
    </tr>`;
  }).join("");
  return `
    <h3 class="section">Recent trades</h3>
    <table class="data">
      <thead><tr>
        <th style="text-align:left">Sym</th><th style="text-align:left">Side</th>
        <th>Entry date</th><th>Exit date</th>
        <th>Entry</th><th>Exit</th><th>Qty</th><th>P&amp;L</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ---------- helpers ---------- */

function escape(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
