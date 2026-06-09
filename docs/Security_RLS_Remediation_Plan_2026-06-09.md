# Piano remediation RLS / PII — visitor-registration-system

**Data audit:** 2026-06-09 (sera, vigilia evento DM)
**Metodo:** workflow multi-agent deep audit (`wfxet8pv4`) — audit DB completato,
finding verificati manualmente su DB produzione via Management API.

## Contesto

SPA statica su GitHub Pages + Supabase. La **anon key è pubblica** (nel JS del
kiosk, by design). La vera linea di difesa è la **RLS**. L'audit ha trovato
policy `USING(true)` per `anon` su tabelle con PII → chiunque estragga la anon
key può scaricare dati personali senza login.

## ✅ GIÀ FIXATO (2026-06-09)

### v31 — `event_dashboard`
`REVOKE ALL FROM anon, PUBLIC` + `GRANT SELECT TO authenticated, service_role`.
La view serve solo al pannello admin (autenticato); il kiosk non la usa
(verificato 0 riferimenti). Verificato: `has_table_privilege('anon',...)=false`.

### v32 — `visitors` (column lockdown) + `visitor_movements` (revoke anon)
- **visitors**: `REVOKE SELECT FROM anon` + `GRANT SELECT (id, guest_id,
  first_name, last_name, signature, event_id, created_at) TO anon`. Bloccati
  ad anon: `document_id, document_type, consent_ip, consent_user_agent, phone,
  email, badge_number` e tutto il resto. INSERT/UPDATE-prestub anon invariati
  (le firme usano `return=minimal`, non serve SELECT per scrivere).
  **Verificato con anon key reale**: query kiosk → 200; `select=document_id`,
  `consent_ip`, `select=*` → 42501 permission denied; INSERT/UPDATE anon = true.
- **visitor_movements**: `REVOKE ALL FROM anon`. Nessun uso anon (kiosk 0 query
  reali, agente usa service_role, admin è authenticated). Verificato: anon
  `select=*` → 42501.

**Residuo noto**: la colonna `signature` resta leggibile da anon (serve per il
filtro `signature=is.null` del kiosk). Esposizione minore (immagine firma del
solo evento corrente); la chiusura completa richiede una VIEW con
`has_signature` boolean + modifica frontend → vedi sotto.

## ⚠️ DA FIXARE POST-EVENTO (con test del kiosk)

Questi NON sono stati toccati la vigilia perché sul percorso-firma critico del
kiosk: una modifica affrettata rischia di rompere l'evento. L'esposizione è
preesistente (settimane), quindi il rischio incrementale di attendere è basso;
il rischio di rompere il kiosk durante l'evento è alto.

### 1. `visitors` — `anon_select_visitors USING(true)` (HIGH, GDPR)
**Espone:** `document_id`, `document_type`, `consent_ip`, `consent_user_agent`,
`email`, `signature`, `phone` di TUTTI i visitatori di sempre, a anon.
**Esiste anche** `anon_select_today USING(created_at >= CURRENT_DATE)`.
**Vincolo kiosk:** deve leggere `id, guest_id, first_name, last_name` + flag
firma per rilevare chi ha già firmato (anche da casa, giorni prima → today-only
NON basta).
**Fix proposto:** creare VIEW `visitors_public` con SOLO le colonne necessarie
al kiosk (`id, guest_id, event_id, first_name, last_name,
(signature IS NOT NULL) AS has_signature, expected_date`-equivalente) +
`GRANT SELECT` a anon su quella; poi `DROP POLICY anon_select_visitors` e
`anon_select_today`; aggiornare frontend per leggere dalla view. **Richiede
test end-to-end del flusso firma + rilevamento pre-firmati prima del deploy.**

### 2. `guest_list` — `guest_list_anon_read USING(true)` (HIGH, GDPR)
**Espone:** nomi, email, azienda, `notes` di tutti gli ospiti di tutti gli eventi.
**Vincolo kiosk:** la lista nomi serve al dropdown "sei in elenco?".
**Fix proposto:** VIEW `guest_list_public` (id, first_name, last_name, company,
event_id, expected_date — NO email/notes) + GRANT anon su view + DROP policy
tabellare. Aggiornare `loadGuestList` nel frontend.

### 3. `visitor_movements` — `vm_select_auth USING(true)` + `vm_insert_agent` anon (HIGH)
**Espone:** tutte le timbrature IN/OUT a anon; anon può **inserire movimenti
arbitrari**.
**Vincolo:** verificare se l'agente Python usa anon o service_role per inserire
(probabilmente service_role). Se sì → `REVOKE` anon su entrambe; insert solo
service_role; select solo authenticated.

## Processo preventivo (consigliato)

- Script pre-evento che enumera `pg_policies WHERE qual='true' AND roles ~ anon`
  e blocca il GO/NO-GO se trova policy permissive nuove.
- Consolidare `schema.sql` committato allo stato reale post-fix (le migration
  v27-v30 reiteravano il GRANT anon → un redeploy le reintrodurrebbe).

## Note

- Frontend kiosk legge: `visitors?select=id,guest_id`,
  `visitors?select=guest_id,first_name,last_name`, `guest_list?select=id&...`,
  `guest_list?select=id,first_name,last_name,email,company,job_title,
  person_to_visit,visit_reason,expected_date,handoff_requested_at`.
  La view pubblica deve coprire questi campi (eccetto email se possibile —
  verificare se il match per email del lockout ne ha davvero bisogno
  server-side o si può fare diversamente).
