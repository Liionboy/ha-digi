# ha-digi (MVP)

Custom component Home Assistant pentru Digi România (MVP) bazat pe sesiune web autenticată.

## Ce face
- Citește ultima factură din contul Digi
- Expune senzori:
  - total ultima factură
  - rest de plată
  - status
  - data facturii

## Instalare rapidă
1. Copiază `custom_components/digi_ro` în `config/custom_components/` din Home Assistant.
2. Restart Home Assistant.
3. Add Integration -> Digi România.
4. Introdu cookie-ul de sesiune Digi (din browser, după login cu SMS) și intervalul de update.

## Notă
Acesta este un MVP. Dacă sesiunea expiră (2FA), senzorii devin unavailable până la reautentificare/cookie nou.
