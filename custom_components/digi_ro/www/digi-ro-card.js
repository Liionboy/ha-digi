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

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  _state(entityId) {
    return this._hass?.states?.[entityId]?.state ?? "unknown";
  }

  _attrs(entityId) {
    return this._hass?.states?.[entityId]?.attributes ?? {};
  }

  _money(entityId) {
    const raw = this._state(entityId);
    const n = Number(String(raw).replace(",", "."));
    if (!Number.isFinite(n)) return raw;
    return new Intl.NumberFormat("ro-RO", { style: "currency", currency: "RON" }).format(n);
  }

  _render() {
    if (!this._hass || !this._config) return;

    const s = this._config.sensors;
    const recentAttrs = this._attrs(s.recent);
    const health = this._state(s.health);
    const healthClass = String(health).toLowerCase().includes("reauth") ? "bad" : "ok";

    const recent = [];
    for (let i = 1; i <= 5; i++) {
      const issue = recentAttrs[`Factura ${i} - data emitere`];
      const amount = recentAttrs[`Factura ${i} - valoare (lei)`];
      if (!issue && !amount) continue;
      recent.push(`<li>${issue ?? "-"} • ${amount ?? "-"} lei</li>`);
    }

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="wrap">
          <div class="head">
            <div class="title">${this._config.title}</div>
            <div class="badge ${healthClass}">${health || "OK"}</div>
          </div>
          <div class="meta">${this._state(s.account)} · ${this._state(s.address)}</div>

          <div class="grid">
            <div><span>Total</span><strong>${this._money(s.total)}</strong></div>
            <div><span>Rest</span><strong>${this._money(s.rest)}</strong></div>
            <div><span>Status</span><strong>${this._state(s.status)}</strong></div>
            <div><span>Achitată</span><strong>${this._state(s.paid)}</strong></div>
            <div><span>Data</span><strong>${this._state(s.date)}</strong></div>
            <div><span>Scadență</span><strong>${this._state(s.due)}</strong></div>
          </div>

          <div class="recent-title">Facturi recente (${this._state(s.recent)})</div>
          <ul class="recent">${recent.join("") || "<li>Nu există date</li>"}</ul>
        </div>
      </ha-card>
      <style>
        .wrap { padding: 14px; }
        .head { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
        .title { font-weight:600; font-size:16px; }
        .badge { font-size:12px; padding:3px 8px; border-radius:999px; }
        .badge.ok { background:#1f7a1f22; color:#1f7a1f; }
        .badge.bad { background:#c6282822; color:#c62828; }
        .meta { color: var(--secondary-text-color); font-size: 12px; margin-bottom: 10px; }
        .grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
        .grid div { background: var(--secondary-background-color); border-radius:10px; padding:8px; }
        .grid span { display:block; font-size:12px; color: var(--secondary-text-color); }
        .grid strong { font-size:14px; }
        .recent-title { margin-top:12px; font-size:13px; font-weight:600; }
        .recent { margin:6px 0 0; padding-left:18px; font-size:12px; }
      </style>
    `;
  }
}

customElements.define("digi-ro-card", DigiRoCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "digi-ro-card",
  name: "DIGI România Card",
  description: "Card simplu pentru senzori ha-digi",
});
