# ha-digi (MVP)

Integrare custom Home Assistant pentru **DIGI România** (My Account), bazată pe sesiune web autentificată.

## Status

- Versiune: `0.1.0` (MVP)
- Domeniu integrare: `digi_ro`
- Auth: cookie de sesiune DIGI (login deja făcut în browser, inclusiv SMS/2FA)

---

## Ce oferă acum

Senzori pentru **ultima factură**:

- `Digi total ultima factură` (`lei`)
- `Digi rest de plată` (`lei`)
- `Digi status ultima factură`
- `Digi data ultimei facturi`

Atribute utile:
- `invoice_id`
- `attribution`

---

## Instalare

1. Copiază folderul:
   - `custom_components/digi_ro`
   în Home Assistant la:
   - `<config>/custom_components/digi_ro`

2. Restart Home Assistant.

3. Mergi la:
   - **Settings → Devices & Services → Add Integration**
   - caută **Digi România**

4. Completează:
   - `Cookie sesiune Digi`
   - `Interval update (secunde)` (recomandat 1800)

---

## Cum iei cookie-ul de sesiune Digi (metoda recomandată)

> Important: fă întâi login normal pe https://www.digi.ro (cu SMS/2FA dacă e activ)

### Chrome / Edge / Brave (exact)

1. Deschide `https://www.digi.ro/my-account/invoices`
2. Apasă `F12` → tab **Network**
3. Dă refresh paginii
4. Click pe request-ul:
   - `invoices/details?invoice_id=...` (ideal), sau
   - `/my-account/invoices`
5. În dreapta: **Headers** → **Request Headers**
6. Copiază valoarea header-ului **cookie**

Exemplu:
- minim: `DGROSESSV3PRI=...`
- complet (dacă minim nu merge): `name=value; name2=value2; ...`

7. Pune această valoare în integrare, câmpul `Cookie sesiune Digi`.

### Observație
Dacă primești eroare de sesiune, recopiază cookie-ul din request-ul `invoices/details` (de obicei e cel mai sigur).

---

## Cum funcționează (tehnic)

Flux MVP:

1. GET `/my-account/invoices` pentru a extrage `invoice_id`
2. POST `/my-account/invoices/details?invoice_id=...`
3. Parse HTML și extragere:
   - total
   - rest
   - status
   - data facturii

---

## Limitări cunoscute

- Dacă sesiunea expiră (sau invalidare server-side), senzorii devin `unavailable` până actualizezi cookie-ul.
- DIGI poate schimba markup-ul HTML/flow-ul de autentificare oricând.
- MVP-ul nu implementează încă re-login automat cu 2FA.

---

## Troubleshooting

### 1) Integrarea apare, dar senzorii sunt unavailable
- Cookie expirat sau incomplet
- Refă login pe Digi și actualizează cookie-ul în integrare

### 2) Nu extrage corect total/rest
- DIGI a schimbat structura HTML
- Deschide issue cu un fragment anonim de răspuns HTML din invoices/details

### 3) Update prea des
- Evită intervale foarte mici (sub 300 sec)
- Recomandat: 900-3600 sec

---

## Roadmap

- [ ] Reauth flow asistat în UI
- [ ] Istoric facturi (lista completă)
- [ ] Senzori suplimentari (servicii, scadență, PDF URL)
- [ ] Cache + fallback la ultima valoare validă

---

## Disclaimer

Acest proiect este neoficial, nu este afiliat DIGI.
Folosește-l pe propria răspundere.