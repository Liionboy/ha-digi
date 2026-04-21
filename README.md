# ha-digi (MVP)

Integrare custom Home Assistant pentru **DIGI România** (My Account), bazată pe sesiune web autentificată.

## Status

- Versiune: `0.1.18` (MVP)
- Domeniu integrare: `digi_ro`
- Auth: login user/parolă + 2FA (SMS) sau cookie sesiune DIGI
- Brand assets (HACS/HA):
  - `icon.png` + `logo.png` în root repo
  - `custom_components/digi_ro/brand/icon.png` + `logo.png`
  - `hacs.json` configurat pentru domain `digi_ro`

---

## Ce oferă acum

Senzori pentru **ultima factură**:

- `Digi total ultima factură` (`lei`)
- `Digi rest de plată` (`lei`)
- `Digi status ultima factură`
- `Digi data ultimei facturi`
- `Digi scadență ultima factură` (dacă există în răspuns)
- `Digi invoice ID`
- `Digi număr factură`
- `Digi factură achitată` (boolean)
- `Digi are rest de plată` (boolean)
- `Digi poziții servicii factură`
- `Digi nume cont`
- `Digi adresă curentă`
- `Digi număr facturi detectate`
- `Digi facturi recente` (count + atribute pentru ultimele până la 5 facturi)

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

4. Completează (recomandat):
   - metoda `login`
   - `username` + `password`
   - cod `2FA` (SMS)
   - selectare adresă/cont
   - `Interval update (secunde)` (recomandat 1800)

   Alternativ: metoda `cookie` cu `Cookie sesiune Digi`.

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

- Dacă sesiunea expiră (sau invalidare server-side), integrarea cere reauth.
- DIGI poate schimba markup-ul HTML/flow-ul de autentificare oricând.
- 2FA depinde de endpoint-urile web Digi (fără API oficial public stabil).

---

## Card Lovelace DIGI (custom)

Fișier card inclus: `custom_components/digi_ro/www/digi-ro-card.js`

Exemplu card:

```yaml
type: custom:digi-ro-card
title: DIGI România
```

Dacă vrei alt set de entități (ex: al doilea cont), poți seta explicit:

```yaml
type: custom:digi-ro-card
sensors:
  total: sensor.digi_total_ultima_factura_2
  rest: sensor.digi_rest_de_plata_2
  status: sensor.digi_status_ultima_factura_2
  date: sensor.digi_data_ultimei_facturi_2
  due: sensor.digi_scadenta_ultima_factura_2
  paid: sensor.digi_factura_achitata_2
  account: sensor.digi_nume_cont_2
  address: sensor.digi_adresa_curenta_2
  recent: sensor.digi_facturi_recente_2
  health: sensor.digi_health_2
```

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

## Noutăți v0.1.18
- Card UI îmbunătățit: culori status, mini-graph pentru facturi recente, buton Reauth
- Compatibil în continuare cu `sensors:` pentru 2+ conturi

## Noutăți v0.1.17
- Card custom Lovelace `custom:digi-ro-card` pentru senzori DIGI
- Suport override entități în config card (util pentru al 2-lea cont)

## Noutăți v0.1.16
- Fix `sensor.digi_nume_cont` (`account_name`) pentru a evita `unknown`
- Fallback robust la extragerea numelui de cont (bulk endpoint + HTML + default safe)

## Noutăți v0.1.15
- Fix endpoint-uri reale Digi pentru 2FA/login/address select (eliminat 404 la send code)
- Tratare grațioasă pentru eroare la trimiterea codului 2FA (fără crash în flow)

## Noutăți v0.1.14
- Fix parser 2FA Digi (detectare token mai robustă)
- Evitare crash în Config Flow când metoda 2FA nu este detectată din prima

## Noutăți v0.1.13
- Login Digi cu user/parolă direct în Config Flow
- Pas 2FA (SMS) în Config Flow
- Selectare adresă/cont în Config Flow
- Stocare cookies structurate (export/import), fără cookie header manual obligatoriu

## Noutăți v0.1.12
- Detectare sesiune expirată (`DigiReauthRequired`) și trigger reauth în Home Assistant
- Pas de reauth în Config Flow pentru update cookie fără ștergere/re-adăugare integrare
- Senzor nou `Digi health` cu status `OK` / `Needs Reauth`

## Noutăți v0.1.11
- Suport multi-cont (evitare conflict `unique_id` între config entries)

## Roadmap

- [ ] Reauth flow asistat în UI
- [ ] Istoric facturi (lista completă)
- [ ] Senzori suplimentari (servicii, scadență, PDF URL)
- [ ] Cache + fallback la ultima valoare validă

---

## Disclaimer

Acest proiect este neoficial, nu este afiliat DIGI.
Folosește-l pe propria răspundere.