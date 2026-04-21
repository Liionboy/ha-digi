class DigiRoCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: "DIGI România",
      sensors: {
        total: "sensor.digi_total_ultima_factura",
        rest: "sensor.digi_rest_de_plata",
        status: "sensor.digi_status_ultima_factura",
        date: "sensor.digi_data_ultimei_facturi",
        due: "sensor.digi_scadenta_ultima_factura",
        paid: "sensor.digi_factura_achitata",
        account: "sensor.digi_nume_cont",
        address: "sensor.digi_adresa_curenta",
        recent: "sensor.digi_facturi_recente",
        health: "sensor.digi_health",
      },
      ...config,
    };

    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  _state(entityId) {
    return this._hass?.states?.[entityId]?.state ?? "unknown";
  }

  _attrs(entityId) {
    return this._hass?.states?.[entityId]?.attributes ?? {};
  }

  _toNumber(value) {
    const n = Number(String(value ?? "").replace(",", "."));
    return Number.isFinite(n) ? n : null;
  }

  _money(value) {
    const n = this._toNumber(value);
    if (n === null) return value ?? "-";
    return new Intl.NumberFormat("ro-RO", { style: "currency", currency: "RON" }).format(n);
  }

  _statusClass() {
    const rest = this._toNumber(this._state(this._config.sensors.rest)) ?? 0;
    const health = String(this._state(this._config.sensors.health)).toLowerCase();
    if (health.includes("reauth")) return "danger";
    if (rest > 0) return "warn";
    return "ok";
  }

  _openMoreInfo(entityId) {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId },
      })
    );
  }

  _buildBars(recentAttrs) {
    const values = [];
    for (let i = 1; i <= 5; i++) {
      const amount = this._toNumber(recentAttrs[`Factura ${i} - valoare (lei)`]);
      const date = recentAttrs[`Factura ${i} - data emitere`] || `F${i}`;
      if (amount !== null) values.push({ amount, date });
    }
    if (!values.length) return "";

    const max = Math.max(...values.map((x) => x.amount), 1);
    return `
      <div class="bars">
        ${values
          .map(
            (x) => `
              <div class="bar-col">
                <div class="bar" style="height:${Math.max(8, Math.round((x.amount / max) * 72))}px"></div>
                <div class="bar-v">${Math.round(x.amount)}</div>
                <div class="bar-d">${x.date}</div>
              </div>`
          )
          .join("")}
      </div>`;
  }

  _render() {
    if (!this._hass || !this._config) return;

    const s = this._config.sensors;
    const statusClass = this._statusClass();
    const health = this._state(s.health);
    const recentAttrs = this._attrs(s.recent);

    const recentList = [];
    for (let i = 1; i <= 5; i++) {
      const issue = recentAttrs[`Factura ${i} - data emitere`];
      const amount = recentAttrs[`Factura ${i} - valoare (lei)`];
      if (!issue && !amount) continue;
      recentList.push(`<li>${issue ?? "-"} · ${amount ?? "-"} lei</li>`);
    }

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="wrap ${statusClass}">
          <div class="head">
            <div>
              <div class="title">${this._config.title}</div>
              <div class="meta">${this._state(s.account)} · ${this._state(s.address)}</div>
            </div>
            <div class="badge">${health}</div>
          </div>

          <div class="kpi">
            <div><span>Total</span><strong>${this._money(this._state(s.total))}</strong></div>
            <div><span>Rest</span><strong>${this._money(this._state(s.rest))}</strong></div>
            <div><span>Status</span><strong>${this._state(s.status)}</strong></div>
            <div><span>Scadență</span><strong>${this._state(s.due)}</strong></div>
          </div>

          ${this._buildBars(recentAttrs)}

          <div class="row">
            <div class="recent-title">Facturi recente (${this._state(s.recent)})</div>
            <button id="reauthBtn">Reauth</button>
          </div>
          <ul class="recent">${recentList.join("") || "<li>Nu există date</li>"}</ul>
        </div>
      </ha-card>
      <style>
        .wrap { padding: 14px; border-left: 4px solid transparent; }
        .wrap.ok { border-left-color: #2e7d32; }
        .wrap.warn { border-left-color: #ef6c00; }
        .wrap.danger { border-left-color: #c62828; }
        .head { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
        .title { font-size:16px; font-weight:700; }
        .meta { font-size:12px; color: var(--secondary-text-color); margin-top:2px; }
        .badge { font-size:12px; border-radius:999px; padding:3px 8px; background: var(--secondary-background-color); }
        .kpi { margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:8px; }
        .kpi div { background: var(--secondary-background-color); border-radius:10px; padding:8px; }
        .kpi span { display:block; font-size:12px; color: var(--secondary-text-color); }
        .kpi strong { font-size:14px; }
        .bars { margin-top:10px; display:flex; align-items:flex-end; gap:8px; min-height:100px; }
        .bar-col { flex:1; text-align:center; }
        .bar { width:100%; border-radius:8px 8px 2px 2px; background: linear-gradient(180deg, #4f8cff, #2459d1); }
        .bar-v { font-size:11px; margin-top:4px; }
        .bar-d { font-size:10px; color: var(--secondary-text-color); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .row { margin-top:10px; display:flex; justify-content:space-between; align-items:center; }
        .recent-title { font-size:13px; font-weight:600; }
        button { border: 0; border-radius: 8px; padding: 6px 10px; cursor: pointer; background: #1976d2; color: #fff; font-size: 12px; }
        .recent { margin:6px 0 0; padding-left:18px; font-size:12px; }
      </style>
    `;

    this.shadowRoot.getElementById("reauthBtn")?.addEventListener("click", () => {
      this._openMoreInfo(s.health);
    });
  }
}

customElements.define("digi-ro-card", DigiRoCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "digi-ro-card",
  name: "DIGI România Card",
  description: "Card DIGI cu status, mini-graph și shortcut Reauth",
});
