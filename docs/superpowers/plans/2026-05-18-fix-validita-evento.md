# B1 — Fix validità XAtlas legata a data evento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire la finestra di validità "giorno-corrente" degli utenti XAtlas con una finestra legata alla data dell'evento Supabase, mantenendo zero impatto sui dipendenti e zero modifiche al DB/frontend.

**Architecture:** Aggiungere una funzione `event_window_ms(event_id)` in `zucchetti_agent.py` che risolve `(today_Rome, event_end_date + 7gg)` via lookup Supabase con politica fail-fast su anomalie. Estendere `create_xatlas_user` con un nuovo parametro `event_id` (default None per backward-compat) e aggiornare i 3 call site (`process_pending_badges`, `process_pool_preparation`, `process_pool_walkin_recreate`) perché propaghino l'event_id dal record Supabase corrispondente. Aggiungere asserzione VIS-only e logging strutturato come reti di sicurezza. **Niente migration DB, niente frontend, niente consolle Zucchetti.**

**Tech Stack:** Python 3.11+, `zoneinfo` (stdlib), `pytest` + `unittest.mock` per test, `psycopg2` e `requests` già presenti come dipendenze del file.

**Riferimento spec:** [`docs/superpowers/specs/2026-05-18-fix-validita-evento-design.md`](../specs/2026-05-18-fix-validita-evento-design.md)

**STOP CONDITION:** Il piano si ferma al commit del branch feature. Push, merge in master e deploy sul Windows Service `ZucchettiAgent` richiedono OK esplicito utente in una sessione separata.

---

## File Structure

**Modificati:**
- `zucchetti_agent.py` — aggiunge `_ROME`, `_today_rome()`, `event_window_ms()`; aggiorna `_today_ms()` tz-explicit; modifica `create_xatlas_user()` (firma + asserzione VIS-only + log + delega a `event_window_ms`); aggiorna SELECT/call in `process_pending_badges`, `process_pool_preparation`, `process_pool_walkin_recreate`.

**Creati:**
- `tests/__init__.py` — file vuoto, rende `tests/` un package.
- `tests/conftest.py` — aggiunge la root del progetto a `sys.path` per importare `zucchetti_agent`.
- `tests/test_validity_window.py` — test unitari della nuova funzione + guardie.

**Toccati zero:** tutto il resto (`admin/`, `frontend/`, `supabase/`, edge functions, altri script).

---

## Task 0: Preflight — branch, ambiente, conferme

**Files:**
- Nessuno modificato. Solo verifiche e setup repo.

- [ ] **Step 1: Verifica directory di lavoro pulita**

Run:
```bash
git status
```
Expected: branch `master`, working tree clean (oppure solo file ignorati). Se ci sono modifiche pending, fermarsi e chiedere all'utente.

- [ ] **Step 2: Crea branch feature dal master aggiornato**

Run:
```bash
git fetch origin
git checkout master
git pull --ff-only origin master
git checkout -b feat/b1-validita-evento
```
Expected: nuovo branch `feat/b1-validita-evento` checked out. Se `git pull` fallisce per conflitti locali, fermarsi e chiedere all'utente.

- [ ] **Step 3: Verifica Python e pytest disponibili**

Run:
```bash
python --version
python -m pytest --version
```
Expected: Python 3.11 o superiore; pytest 7.x o superiore. Se pytest mancante, installalo nell'ambiente locale dello sviluppatore:
```bash
python -m pip install --user pytest
```

- [ ] **Step 4: Verifica `zoneinfo` disponibile (Python 3.9+ stdlib)**

Run:
```bash
python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Europe/Rome'))"
```
Expected: stampa `Europe/Rome` senza errori. Se ImportError su Windows, installare `tzdata`:
```bash
python -m pip install --user tzdata
```

- [ ] **Step 5: Conferma struttura attuale di `zucchetti_agent.py`**

Run:
```bash
python -c "import zucchetti_agent as za; print(za._today_ms(), za.create_xatlas_user.__name__)"
```
Expected: stampa una tupla `(start_ms, end_ms)` e `create_xatlas_user`. Se ImportError per moduli mancanti (es. `psycopg2`), proseguire comunque — i test useranno mock, e l'agente reale gira in produzione su un altro ambiente.

Se l'import fallisce per `psycopg2`/`requests` mancanti localmente:
```bash
python -m pip install --user psycopg2-binary requests
```

---

## Task 1: Scaffolding directory `tests/`

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Crea `tests/__init__.py` vuoto**

```python
```

(File vuoto. Solo per rendere `tests/` un package Python.)

- [ ] **Step 2: Crea `tests/conftest.py` con path setup**

```python
"""conftest.py per la test suite del visitor-registration-system.

Aggiunge la root del repository al sys.path così le suite possono importare
moduli al livello root (es. zucchetti_agent) senza pacchettizzare.
"""
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
```

- [ ] **Step 3: Verifica che la suite tests/ possa importare zucchetti_agent**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); import zucchetti_agent; print('import OK', hasattr(zucchetti_agent, '_today_ms'))"
```
Expected: `import OK True`.

- [ ] **Step 4: Commit scaffolding**

Run:
```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: scaffold tests/ directory + conftest path setup"
```
Expected: 1 commit creato con 2 file aggiunti.

---

## Task 2: Test failing — `event_window_ms` (TDD: rosso)

**Files:**
- Create: `tests/test_validity_window.py`

- [ ] **Step 1: Scrivi il file di test completo (tutti i casi del piano in un solo file)**

```python
"""Unit test per la funzione event_window_ms e per il fallback _today_ms.

Spec di riferimento: docs/superpowers/specs/2026-05-18-fix-validita-evento-design.md

Strategia:
- Tutte le call a Supabase (`sb_get`) sono mockate.
- Tutte le call al wall-clock (`_today_rome`) sono mockate per test deterministici.
- Verifica che i bound restituiti, interpretati come epoch ms, corrispondano a
  datetime in Europe/Rome alle ore 00:00:00 (start) e 23:59:59 (end).
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

import zucchetti_agent as za


ROME = ZoneInfo("Europe/Rome")


def _ms_to_rome_dt(ms):
    """Helper: converte epoch ms in datetime Europe/Rome tz-aware."""
    return datetime.fromtimestamp(ms / 1000, tz=ROME)


# ─── 1) Fallback walk-in: event_id is None ─────────────────────────────────
def test_walk_in_fallback_when_event_id_none():
    """event_id None -> deve usare _today_ms() invariato (fallback walk-in)."""
    expected = za._today_ms()
    result = za.event_window_ms(None)
    assert result == expected


# ─── 2) Evento futuro: pool preparato in anticipo ──────────────────────────
def test_future_event_validity_ends_at_event_end_plus_7():
    """Evento fra alcuni giorni: end = event_end + 7gg @ 23:59:59 Europe/Rome."""
    fake_today = date(2026, 5, 25)
    event_row = {"event_end_date": "2026-06-03", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        start_ms, end_ms = za.event_window_ms("evt-future")

    start_dt = _ms_to_rome_dt(start_ms)
    end_dt = _ms_to_rome_dt(end_ms)
    assert start_dt.date() == date(2026, 5, 25)
    assert (start_dt.hour, start_dt.minute, start_dt.second) == (0, 0, 0)
    assert end_dt.date() == date(2026, 6, 10)  # 2026-06-03 + 7gg
    assert (end_dt.hour, end_dt.minute, end_dt.second) == (23, 59, 59)


# ─── 3) Evento OGGI: start=oggi, end=oggi+7 ────────────────────────────────
def test_event_today_end_today_plus_7():
    fake_today = date(2026, 6, 3)
    event_row = {"event_end_date": "2026-06-03", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        start_ms, end_ms = za.event_window_ms("evt-today")

    end_dt = _ms_to_rome_dt(end_ms)
    assert end_dt.date() == date(2026, 6, 10)
    assert (end_dt.hour, end_dt.minute, end_dt.second) == (23, 59, 59)


# ─── 4) Evento multi-giorno ────────────────────────────────────────────────
def test_event_multi_day_uses_event_end_date():
    fake_today = date(2026, 6, 1)
    event_row = {"event_end_date": "2026-06-05", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        _, end_ms = za.event_window_ms("evt-multiday")

    assert _ms_to_rome_dt(end_ms).date() == date(2026, 6, 12)  # 2026-06-05 + 7


# ─── 5) Evento chiuso: fail-fast ───────────────────────────────────────────
def test_event_closed_raises_runtime_error():
    event_row = {"event_end_date": "2026-06-03",
                 "closed_at": "2026-06-03T18:00:00+02:00"}
    with patch.object(za, "sb_get", return_value=[event_row]):
        with pytest.raises(RuntimeError, match="chiuso"):
            za.event_window_ms("evt-closed")


# ─── 6) Evento scaduto (event_end nel passato): fail-fast ──────────────────
def test_event_in_past_raises_runtime_error():
    fake_today = date(2026, 6, 10)
    event_row = {"event_end_date": "2026-06-03", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        with pytest.raises(RuntimeError, match="scaduto"):
            za.event_window_ms("evt-past")


# ─── 7) Evento non trovato: fail-fast ──────────────────────────────────────
def test_event_not_found_raises_runtime_error():
    with patch.object(za, "sb_get", return_value=[]):
        with pytest.raises(RuntimeError, match="non trovato"):
            za.event_window_ms("evt-missing")


# ─── 8) Lookup Supabase fallisce (rete down): fail-fast ────────────────────
def test_event_lookup_failure_raises_runtime_error():
    def _boom(*args, **kwargs):
        raise ConnectionError("simulated network outage")
    with patch.object(za, "sb_get", side_effect=_boom):
        with pytest.raises(RuntimeError, match="lookup events fallito"):
            za.event_window_ms("evt-anything")


# ─── 9) event_end_date mancante o NULL: fail-fast ──────────────────────────
def test_event_without_end_date_raises_runtime_error():
    event_row = {"event_end_date": None, "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]):
        with pytest.raises(RuntimeError, match="event_end_date"):
            za.event_window_ms("evt-no-enddate")


# ─── 10) DST: evento a fine ottobre (cambio ora legale) ────────────────────
def test_dst_october_event_window_uses_europe_rome():
    """Bound a 23:59:59 LOCALE Europe/Rome anche attraverso cambio DST.

    DST 2026 in Italia: ultima domenica di ottobre = 2026-10-25 (CEST → CET).
    Evento fine 2026-10-25 + 7gg = 2026-11-01 (in CET).
    """
    fake_today = date(2026, 10, 24)
    event_row = {"event_end_date": "2026-10-25", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        _, end_ms = za.event_window_ms("evt-dst")

    end_dt = _ms_to_rome_dt(end_ms)
    assert end_dt.date() == date(2026, 11, 1)
    assert (end_dt.hour, end_dt.minute, end_dt.second) == (23, 59, 59)
    # In novembre l'offset Europe/Rome è UTC+1 (CET, fine DST)
    assert end_dt.utcoffset() == timedelta(hours=1)


# ─── 11) Anno bisestile / fine mese ────────────────────────────────────────
def test_leap_year_boundary():
    fake_today = date(2028, 2, 29)
    event_row = {"event_end_date": "2028-02-29", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        _, end_ms = za.event_window_ms("evt-leap")

    assert _ms_to_rome_dt(end_ms).date() == date(2028, 3, 7)


# ─── 12) _today_ms() resta tz-explicit Europe/Rome ─────────────────────────
def test_today_ms_is_europe_rome_anchored():
    """_today_ms() ritorna una finestra di OGGI in Europe/Rome,
    indipendentemente dal fuso del sistema su cui gira."""
    fake_today = date(2026, 5, 25)
    with patch.object(za, "_today_rome", return_value=fake_today):
        start_ms, end_ms = za._today_ms()

    start_dt = _ms_to_rome_dt(start_ms)
    end_dt = _ms_to_rome_dt(end_ms)
    assert start_dt.date() == date(2026, 5, 25)
    assert (start_dt.hour, start_dt.minute, start_dt.second) == (0, 0, 0)
    assert end_dt.date() == date(2026, 5, 25)
    assert (end_dt.hour, end_dt.minute, end_dt.second) == (23, 59, 59)


# ─── 13) Guardia statica VIS-only nel sorgente ─────────────────────────────
def test_source_contains_vis_only_assertion():
    """Difesa in profondità: il sorgente DEVE contenere l'asserzione VIS-only.

    Questo test scatta se una modifica futura rimuove la guardia hardcoded
    che protegge i dipendenti — è un canarino statico, non un controllo runtime."""
    import os
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    src_path = os.path.join(repo_root, "zucchetti_agent.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert 'assert identifier.startswith("VIS")' in src, \
        "Asserzione VIS-only mancante in create_xatlas_user (regressione di sicurezza)"
```

- [ ] **Step 2: Run pytest → verifica che fallisca per funzione mancante**

Run:
```bash
python -m pytest tests/test_validity_window.py -v
```
Expected: tutti i test che usano `za.event_window_ms` o `za._today_rome` falliscono con `AttributeError: module 'zucchetti_agent' has no attribute 'event_window_ms'`. Il test `test_source_contains_vis_only_assertion` fallisce con AssertionError. **Questo è l'esito atteso del rosso TDD.**

- [ ] **Step 3: Commit del test rosso**

Run:
```bash
git add tests/test_validity_window.py
git commit -m "test: aggiungi test rossi per event_window_ms (TDD step 1)"
```

---

## Task 3: Implementazione `event_window_ms` (TDD: verde)

**Files:**
- Modify: `zucchetti_agent.py` — top-level (subito sopra `_today_ms`, riga ~303)

- [ ] **Step 1: Verifica gli import esistenti**

Apri `zucchetti_agent.py` e cerca le righe di import in cima. Conferma che sia presente:
```python
from datetime import date, datetime, timedelta, timezone
```

Se `timedelta` o `timezone` mancano, aggiungili. Se manca `zoneinfo`, vai allo Step 2.

- [ ] **Step 2: Aggiungi import zoneinfo (se non presente)**

Cerca in cima al file la sezione import. Trova la riga `from datetime import ...` e subito sotto aggiungi:
```python
from zoneinfo import ZoneInfo
```

- [ ] **Step 3: Sostituisci la funzione `_today_ms` esistente con la versione tz-explicit + aggiungi `_today_rome` ed `event_window_ms`**

Trova nel file la funzione attuale (righe ~301-309):
```python
# ── XAtlas: crea utente esterno ───────────────────────────────────────────────

def _today_ms():
    """Restituisce (start_ms, end_ms) del giorno corrente in millisecondi epoch."""
    today = date.today()
    start = datetime(today.year, today.month, today.day, 0, 0, 0)
    end   = datetime(today.year, today.month, today.day, 23, 59, 59)
    epoch = datetime(1970, 1, 1)
    return int((start - epoch).total_seconds() * 1000), int((end - epoch).total_seconds() * 1000)
```

Sostituiscila con:
```python
# ── XAtlas: crea utente esterno ───────────────────────────────────────────────

_ROME = ZoneInfo("Europe/Rome")


def _today_rome():
    """Restituisce la data corrente ancorata al fuso Europe/Rome.

    Indipendente dal fuso del sistema operativo: protegge da configurazioni
    server errate (es. server con TZ=UTC) che causerebbero shift di validità.
    Patchabile nei test per scenari deterministici.
    """
    return datetime.now(_ROME).date()


def _today_ms():
    """Finestra (oggi 00:00, oggi 23:59:59) in epoch ms, ancorata Europe/Rome.

    Usata come fallback per walk-in senza event_id (visitor non legato a evento
    gestito). Per visitor legati a evento, l'agente usa event_window_ms().
    """
    today = _today_rome()
    start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=_ROME)
    end   = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=_ROME)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def event_window_ms(event_id):
    """Finestra validità XAtlas legata alla data dell'evento.

    Spec: docs/superpowers/specs/2026-05-18-fix-validita-evento-design.md

    Politica:
    - event_id is None -> _today_ms() (fallback walk-in legacy, comportamento invariato)
    - altrimenti lookup events su Supabase:
        - evento non trovato      -> raise RuntimeError (fail-fast, retry ciclo dopo)
        - evento chiuso           -> raise RuntimeError (fail-fast, no provisioning)
        - event_end_date passato  -> raise RuntimeError (fail-fast, evento scaduto)
        - altrimenti:
            start = oggi 00:00:00 Europe/Rome
            end   = max(event_end + 7gg, oggi + 1gg) 23:59:59 Europe/Rome
    """
    if event_id is None:
        return _today_ms()

    try:
        rows = sb_get("events", params={
            "id":     f"eq.{event_id}",
            "select": "event_end_date,closed_at",
            "limit":  "1",
        })
    except Exception as e:
        raise RuntimeError(
            f"event_window_ms: lookup events fallito per event_id={event_id}: {e}"
        )

    if not rows:
        raise RuntimeError(
            f"event_window_ms: event_id={event_id} non trovato in events"
        )

    event = rows[0]
    if event.get("closed_at") is not None:
        raise RuntimeError(
            f"event_window_ms: event_id={event_id} è chiuso "
            f"(closed_at={event['closed_at']}), no provisioning"
        )

    event_end_str = event.get("event_end_date")
    if not event_end_str:
        raise RuntimeError(
            f"event_window_ms: event_id={event_id} senza event_end_date valorizzato"
        )

    today = _today_rome()
    event_end = date.fromisoformat(event_end_str)

    if event_end < today:
        raise RuntimeError(
            f"event_window_ms: event_id={event_id} scaduto "
            f"(event_end_date={event_end} < oggi {today})"
        )

    candidate_end = max(event_end + timedelta(days=7), today + timedelta(days=1))

    start_dt = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=_ROME)
    end_dt   = datetime(candidate_end.year, candidate_end.month, candidate_end.day,
                        23, 59, 59, tzinfo=_ROME)
    return int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)
```

- [ ] **Step 4: Run pytest per il blocco `event_window_ms` + `_today_ms`**

Run:
```bash
python -m pytest tests/test_validity_window.py -v -k "not vis_only"
```
Expected: tutti i test funzionali passano (PASS). Il test `test_source_contains_vis_only_assertion` è escluso dal `-k` (sarà soddisfatto in Task 4).

Se qualche test fallisce, leggere l'output, correggere l'implementazione **senza toccare i test**.

- [ ] **Step 5: Commit**

Run:
```bash
git add zucchetti_agent.py
git commit -m "feat(agent): event_window_ms tz-anchored Europe/Rome (closes B1 core)"
```

---

## Task 4: Asserzione VIS-only in `create_xatlas_user`

**Files:**
- Modify: `zucchetti_agent.py:524-651` (funzione `create_xatlas_user`)

- [ ] **Step 1: Localizza il punto di inserimento**

Apri `zucchetti_agent.py` e cerca dentro `create_xatlas_user` la riga (~547):
```python
    identifier = f"VIS{badge_number}"
```

- [ ] **Step 2: Aggiungi l'asserzione subito dopo**

Sostituisci:
```python
    identifier = f"VIS{badge_number}"

    # IDEMPOTENZA: se l'agente è crashato dopo INSERT user_identifier ma prima
```

Con:
```python
    identifier = f"VIS{badge_number}"
    # Difesa in profondità: garantisce che l'agente non possa creare utenti
    # XAtlas fuori dal namespace VIS, anche dopo modifiche future al codice.
    # Vedi spec B1, sezione "Asserzioni e vincoli di sicurezza".
    assert identifier.startswith("VIS"), \
        f"REFUSED: tentativo di creare utente non-VIS, identifier={identifier!r}"

    # IDEMPOTENZA: se l'agente è crashato dopo INSERT user_identifier ma prima
```

- [ ] **Step 3: Run il test della guardia statica**

Run:
```bash
python -m pytest tests/test_validity_window.py::test_source_contains_vis_only_assertion -v
```
Expected: PASS.

- [ ] **Step 4: Run tutta la suite — tutto verde**

Run:
```bash
python -m pytest tests/test_validity_window.py -v
```
Expected: tutti i test passano.

- [ ] **Step 5: Commit**

Run:
```bash
git add zucchetti_agent.py
git commit -m "feat(agent): asserzione VIS-only hardcoded in create_xatlas_user"
```

---

## Task 5: Modifica firma `create_xatlas_user` + delega a `event_window_ms` + logging

**Files:**
- Modify: `zucchetti_agent.py:524` (firma) + riga ~545 (delega) + nuovo log INFO

- [ ] **Step 1: Cambia la firma della funzione**

Cerca la riga (~524):
```python
def create_xatlas_user(badge_number: str, first_name: str, last_name: str) -> tuple[int, int]:
```

Sostituiscila con:
```python
def create_xatlas_user(badge_number: str, first_name: str, last_name: str,
                      event_id: str | None = None) -> tuple[int, int]:
```

- [ ] **Step 2: Aggiorna la docstring (subito dopo la firma)**

Sostituisci la docstring esistente:
```python
    """
    Crea utente esterno in XAtlas e assegna la tessera.
    Restituisce (xatlas_user_id, card_id).
    """
```

Con:
```python
    """
    Crea utente esterno in XAtlas e assegna la tessera.

    Argomenti:
      badge_number: numero badge stampato sul cartoncino (sarà l'identifier VIS<badge>).
      first_name, last_name: nome reale dell'ospite (o "Pool"/"Badge<n>" per spare pool).
      event_id: ID dell'evento Supabase a cui il visitor è legato. Se None, l'utente
        XAtlas riceve validità di un giorno (fallback walk-in legacy). Se valorizzato,
        la validità è (oggi, event_end_date + 7gg) — vedi event_window_ms.

    Restituisce (xatlas_user_id, card_id).

    Solleva RuntimeError fail-fast se event_id è valorizzato ma l'evento è non trovato,
    chiuso, o scaduto. Il chiamante deve catturare e lasciare il visitor in stato pending
    per il retry al ciclo successivo dell'agente.
    """
```

- [ ] **Step 3: Sostituisci la riga 545 — delega a event_window_ms**

Cerca (~riga 545, dentro `create_xatlas_user`):
```python
    # 2) Crea utente esterno (con idempotenza: salta se identifier già esistente)
    start_ms, end_ms = _today_ms()
```

Sostituiscila con:
```python
    # 2) Crea utente esterno (con idempotenza: salta se identifier già esistente)
    start_ms, end_ms = event_window_ms(event_id)
```

- [ ] **Step 4: Aggiungi log strutturato dopo il calcolo della finestra**

Subito dopo la riga `start_ms, end_ms = event_window_ms(event_id)` (la riga che hai appena modificato), aggiungi:
```python
    # Log strutturato: tracciabilità validità per audit post-incidente
    start_iso = datetime.fromtimestamp(start_ms / 1000, tz=_ROME).isoformat()
    end_iso   = datetime.fromtimestamp(end_ms / 1000, tz=_ROME).isoformat()
    log.info(
        f"create_xatlas_user: identifier=VIS{badge_number} "
        f"validity={start_iso}..{end_iso} "
        f"event_id={event_id or 'WALK-IN'}"
    )
    end_of_use_ms = 4133977199999  # 31/12/2099 come Baudo Pippo
```

Verifica che la riga successiva `end_of_use_ms = 4133977199999` esista già nel file e NON la dupplichi — se è già lì rimuovila dal blocco che stai inserendo. (Il blocco originale aveva `end_of_use_ms` definito poco sotto: verifica e tieni una sola occorrenza.)

- [ ] **Step 5: Run tutti i test — verde**

Run:
```bash
python -m pytest tests/test_validity_window.py -v
```
Expected: tutti i test passano. Se qualcosa fallisce, è probabilmente per l'`end_of_use_ms` duplicato — sistemare e ri-runnare.

- [ ] **Step 6: Smoke test import in Python**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); import zucchetti_agent as za; print(za.create_xatlas_user.__doc__[:50]); print(za.event_window_ms.__name__)"
```
Expected: stampa l'inizio della docstring nuova e il nome `event_window_ms`.

- [ ] **Step 7: Commit**

Run:
```bash
git add zucchetti_agent.py
git commit -m "feat(agent): create_xatlas_user accetta event_id + log strutturato"
```

---

## Task 6: Aggiorna call site 1 — `process_pending_badges`

**Files:**
- Modify: `zucchetti_agent.py:749-783` (funzione `process_pending_badges`)

- [ ] **Step 1: Aggiorna il SELECT Supabase per includere `event_id`**

Cerca dentro `process_pending_badges` (~riga 752-755):
```python
        pending = sb_get("visitors", params={
            "xatlas_status": "eq.pending",
            "select": "id,first_name,last_name,badge_number",
        })
```

Sostituiscila con:
```python
        pending = sb_get("visitors", params={
            "xatlas_status": "eq.pending",
            "select": "id,first_name,last_name,badge_number,event_id",
        })
```

- [ ] **Step 2: Passa event_id alla chiamata `create_xatlas_user`**

Cerca (~riga 772):
```python
                xid, cid = create_xatlas_user(badge, fn, ln)
```

Sostituiscila con:
```python
                eid = v.get("event_id")
                xid, cid = create_xatlas_user(badge, fn, ln, event_id=eid)
```

- [ ] **Step 3: Verifica sintassi (compile check)**

Run:
```bash
python -m py_compile zucchetti_agent.py
```
Expected: nessun output (compilazione OK). Errori di sintassi vanno corretti subito.

- [ ] **Step 4: Run tutti i test — verde**

Run:
```bash
python -m pytest tests/ -v
```
Expected: tutti i test passano (i test di Task 2 mockano `sb_get` quindi non interagiscono con questa modifica).

- [ ] **Step 5: Commit**

Run:
```bash
git add zucchetti_agent.py
git commit -m "feat(agent): process_pending_badges propaga event_id"
```

---

## Task 7: Aggiorna call site 2 — `process_pool_preparation`

**Files:**
- Modify: `zucchetti_agent.py:786-820` (funzione `process_pool_preparation`)

- [ ] **Step 1: Verifica che il SELECT già contenga event_id (no modifica)**

Cerca (~riga 791-795):
```python
        pending = sb_get("badge_pool", params={
            "status": "eq.preparing",
            "select": "id,badge_number,event_id",
            "limit": "10",
        })
```
Atteso: `event_id` già presente nel SELECT (è il caso in cui il SELECT era già OK). Se manca per qualche ragione, aggiungilo.

- [ ] **Step 2: Passa event_id alla chiamata `create_xatlas_user`**

Cerca (~riga 811):
```python
            xid, cid = create_xatlas_user(badge, "Pool", f"Badge{badge}")
```

Sostituiscila con:
```python
            xid, cid = create_xatlas_user(badge, "Pool", f"Badge{badge}",
                                          event_id=p.get("event_id"))
```

- [ ] **Step 3: Compile check + test**

Run:
```bash
python -m py_compile zucchetti_agent.py
python -m pytest tests/ -v
```
Expected: nessun errore di compilazione, tutti i test passano.

- [ ] **Step 4: Commit**

Run:
```bash
git add zucchetti_agent.py
git commit -m "feat(agent): process_pool_preparation propaga event_id"
```

---

## Task 8: Aggiorna call site 3 — `process_pool_walkin_recreate`

**Files:**
- Modify: `zucchetti_agent.py:1126-1218` (funzione `process_pool_walkin_recreate`)

- [ ] **Step 1: Aggiorna il SELECT Supabase per includere `event_id`**

Cerca (~riga 1142-1148):
```python
        rows = sb_get("visitors", params={
            "xatlas_user_id": "not.is.null",
            "xatlas_renamed": "is.false",
            "xatlas_status":  "eq.active",
            "select": "id,first_name,last_name,xatlas_user_id,badge_number",
            "limit": "5",
        })
```

Sostituiscila con:
```python
        rows = sb_get("visitors", params={
            "xatlas_user_id": "not.is.null",
            "xatlas_renamed": "is.false",
            "xatlas_status":  "eq.active",
            "select": "id,first_name,last_name,xatlas_user_id,badge_number,event_id",
            "limit": "5",
        })
```

- [ ] **Step 2: Passa event_id alla chiamata `create_xatlas_user`**

Cerca (~riga 1200):
```python
            new_xid, new_cid = create_xatlas_user(badge, fn, ln)
```

Sostituiscila con:
```python
            new_xid, new_cid = create_xatlas_user(badge, fn, ln,
                                                  event_id=v.get("event_id"))
```

- [ ] **Step 3: Compile check + test**

Run:
```bash
python -m py_compile zucchetti_agent.py
python -m pytest tests/ -v
```
Expected: nessun errore di compilazione, tutti i test passano.

- [ ] **Step 4: Commit**

Run:
```bash
git add zucchetti_agent.py
git commit -m "feat(agent): process_pool_walkin_recreate propaga event_id"
```

---

## Task 9: Self-check finale — diff completo, asserzioni difensive, smoke test import

**Files:**
- Nessuno modificato. Solo verifiche.

- [ ] **Step 1: Diff completo branch vs master**

Run:
```bash
git log master..HEAD --oneline
git diff master...HEAD --stat
```
Expected: 6-7 commit con messaggi chiari. Lo stat dovrebbe mostrare modifiche a `zucchetti_agent.py` (linee aggiunte) e creazione di `tests/__init__.py`, `tests/conftest.py`, `tests/test_validity_window.py`.

- [ ] **Step 2: Conta riferimenti `_today_ms` per assicurarsi che nessun call site critico lo usi più (eccetto event_window_ms fallback e create_xatlas_user è ora `event_window_ms`)**

Run:
```bash
grep -n "_today_ms" zucchetti_agent.py
```
Expected: 2 occorrenze:
- una nella definizione di `_today_ms()` stessa
- una dentro `event_window_ms` come fallback (`if event_id is None: return _today_ms()`)

Se ci sono altri call site di `_today_ms` rimasti nel codice produttivo (es. dentro `create_xatlas_user`), è un bug del piano — segnalalo all'utente e fermati.

- [ ] **Step 3: Conta i punti che chiamano `create_xatlas_user` e verifica tutti passino `event_id`**

Run:
```bash
grep -n "create_xatlas_user(" zucchetti_agent.py
```
Expected: 4 occorrenze:
- la definizione (`def create_xatlas_user(...)`)
- 3 call site, tutti con `event_id=...` esplicito

Se uno dei 3 call site non passa `event_id`, è un bug — segnalalo e fermati.

- [ ] **Step 4: Run completo test suite + verbose**

Run:
```bash
python -m pytest tests/ -v
```
Expected: **tutti** i test (13) passano. Se qualcuno fallisce, debug — NON modificare i test, modificare l'implementazione.

- [ ] **Step 5: Smoke test import — il modulo si carica senza errori**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); import zucchetti_agent; print('import OK'); print('event_window_ms:', zucchetti_agent.event_window_ms is not None); print('today_rome:', zucchetti_agent._today_rome is not None)"
```
Expected: 3 righe di output `import OK`, `event_window_ms: True`, `today_rome: True`.

- [ ] **Step 6: Conferma branch e commit**

Run:
```bash
git status
git log feat/b1-validita-evento --oneline | head -10
```
Expected: branch `feat/b1-validita-evento` checked out, working tree clean, ~6-7 commit di feature presenti.

- [ ] **Step 7: NON push e NON merge — fermarsi qui**

**STOP.** Non eseguire `git push`, `git merge`, `gh pr create`, né alcuna azione che propaghi il branch a master o al server. Riferire all'utente:
- branch creato e tutto verde locale
- numero di commit + sintesi
- chiedere OK per `git push origin feat/b1-validita-evento` separatamente
- chiedere OK per il deploy sul Windows Service `ZucchettiAgent` separatamente
- la procedura di refresh utenti pre-deploy (UPDATE `xatlas_renamed=false`) va eseguita SOLO dopo deploy avvenuto + smoke test + canary verde

---

## Self-Review (esegui dopo aver scritto il piano, prima di iniziare le task)

**1. Spec coverage**

| Sezione spec | Task corrispondente | OK |
|---|---|---|
| Nuova funzione `event_window_ms(event_id)` | Task 3 | ✅ |
| `_today_ms()` invariato come fallback | Task 3 (mantenuto, tz-explicit) | ✅ |
| Politica fail-fast unitaria (non trovato/chiuso/scaduto) | Task 2 (test) + Task 3 (impl) | ✅ |
| Walk-in con event_id=None → fallback | Task 2 (test) + Task 3 (impl) | ✅ |
| Modifica firma `create_xatlas_user` + param event_id default None | Task 5 | ✅ |
| Asserzione `assert identifier.startswith("VIS")` | Task 4 | ✅ |
| Logging strutturato (identifier, validity_start/end, event_id) | Task 5 | ✅ |
| Timezone esplicito Europe/Rome | Task 3 (`_ROME`, `_today_rome`) | ✅ |
| `process_pending_badges` SELECT + call passano event_id | Task 6 | ✅ |
| `process_pool_preparation` call passa event_id | Task 7 | ✅ |
| `process_pool_walkin_recreate` SELECT + call passano event_id | Task 8 | ✅ |
| Test pytest per tutti gli scenari della formula | Task 2 (13 test) | ✅ |
| Stop prima del deploy | Task 9 step 7 | ✅ |
| Niente migration DB | Vincolo: nessun file `supabase/` modificato | ✅ |
| Niente frontend | Vincolo: nessun file `admin/`/`frontend/` modificato | ✅ |

**2. Placeholder scan**

Cercato pattern: nessuno `TBD`, `TODO`, `implementare dopo`, "handle edge cases" senza codice, "similar to Task N", "fill in details". Tutti gli step contengono codice/comandi completi.

**3. Type consistency**

| Symbol | Task in cui appare | Note |
|---|---|---|
| `event_window_ms` | Task 2 (test), 3 (impl), 5 (uso) | Sempre uguale |
| `_today_rome` | Task 2 (test patch), 3 (impl) | Sempre uguale |
| `_today_ms` | Task 2 (test invariato), 3 (impl invariato funzionalmente, tz-explicit) | Firma immutata |
| `create_xatlas_user(..., event_id=None)` | Task 5 (firma), 6/7/8 (call) | Default None consistente |
| `_ROME` | Task 3 (def), 5 (uso log), test (uso indiretto) | Sempre uguale |

Tutto consistente.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-fix-validita-evento.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch fresh subagent per task, review tra task, iterazione rapida.

**2. Inline Execution** — Esegui task in questa sessione usando executing-plans, batch execution con checkpoint.

Quale approccio?
