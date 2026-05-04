"""
Zucchetti Bridge Agent
Ponte tra Supabase (visitatori) e XAtlas (tornello SuperTRAX).

Installazione come Windows Service:
    pip install -r requirements.txt
    python zucchetti_agent.py install
    python zucchetti_agent.py start

Debug in foreground:
    python zucchetti_agent.py debug
"""

import configparser
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta

import psycopg2
import requests

# ── Configurazione ────────────────────────────────────────────────────────────

_dir = os.path.dirname(os.path.abspath(__file__))
_cfg_path = os.path.join(_dir, "agent_config.ini")

cfg = configparser.ConfigParser()
cfg.read(_cfg_path, encoding="utf-8")

SUPABASE_URL = cfg["supabase"]["url"]
SUPABASE_KEY = cfg["supabase"]["service_key"]  # service_role key

XATLAS_BASE = cfg["xatlas"]["base_url"]        # http://localhost:8080
XATLAS_USER = cfg["xatlas"]["username"]
XATLAS_PASS = cfg["xatlas"]["password"]

AXS_DB = dict(
    host=cfg["axs_db"]["host"],
    port=int(cfg["axs_db"].get("port", "5432")),
    dbname=cfg["axs_db"]["dbname"],
    user=cfg["axs_db"]["user"],
    password=cfg["axs_db"].get("password", ""),
)

# Valori fissi AXS_DB (da non modificare senza rigenerare il profilo)
COMPANY_ID                  = 156
EXTERNAL_COMPANY_ID         = 157
SITE_ID                     = 176
ORGANIZATIONAL_STRUCTURE_ID = 173
AUTH_GROUP_ID               = 249   # gruppo VISITATORI

POLL_INTERVAL = 10   # secondi tra ogni ciclo
MAX_RETRIES   = 3    # tentativi prima di loggare errore e passare oltre

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(_dir, "zucchetti_agent.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("zucchetti_agent")

# ── Supabase helpers ──────────────────────────────────────────────────────────

_sb_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def sb_get(path, params=None):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=_sb_headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def sb_patch(path, data):
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{path}", headers=_sb_headers, json=data, timeout=15)
    r.raise_for_status()
    return r.json()


# ── XAtlas session ────────────────────────────────────────────────────────────

_xatlas_session: requests.Session | None = None


def xatlas_login():
    global _xatlas_session
    s = requests.Session()
    # Prova prima l'endpoint API REST
    r = s.post(
        f"{XATLAS_BASE}/web/api/v1/login",
        json={"username": XATLAS_USER, "password": XATLAS_PASS},
        timeout=10,
    )
    if r.ok:
        _xatlas_session = s
        log.info("XAtlas login OK (API)")
        return
    # Fallback: form POST
    r = s.post(
        f"{XATLAS_BASE}/users/j_security_check",
        data={"j_username": XATLAS_USER, "j_password": XATLAS_PASS},
        allow_redirects=True,
        timeout=10,
    )
    if r.ok:
        _xatlas_session = s
        log.info("XAtlas login OK (form)")
        return
    raise RuntimeError(f"XAtlas login fallito: {r.status_code}")


def xatlas_request(method, path, **kwargs):
    global _xatlas_session
    if _xatlas_session is None:
        xatlas_login()
    url = f"{XATLAS_BASE}{path}"
    r = getattr(_xatlas_session, method)(url, timeout=15, **kwargs)
    if r.status_code == 401:
        xatlas_login()
        r = getattr(_xatlas_session, method)(url, timeout=15, **kwargs)
    return r


# ── XAtlas: crea utente esterno ───────────────────────────────────────────────

def _today_ms():
    """Restituisce (start_ms, end_ms) del giorno corrente in millisecondi epoch."""
    today = date.today()
    start = datetime(today.year, today.month, today.day, 0, 0, 0)
    end   = datetime(today.year, today.month, today.day, 23, 59, 59)
    epoch = datetime(1970, 1, 1)
    return int((start - epoch).total_seconds() * 1000), int((end - epoch).total_seconds() * 1000)


def find_card_id_by_clear_code(clear_code: str) -> int | None:
    """Cerca card.id per clear_code (numero badge) in AXS_DB."""
    try:
        conn = psycopg2.connect(**AXS_DB)
        cur = conn.cursor()
        cur.execute("SELECT id FROM card WHERE clear_code = %s LIMIT 1;", (clear_code,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        log.error(f"Errore lookup card_id per clear_code={clear_code}: {e}")
        return None


def create_xatlas_user(badge_number: str, first_name: str, last_name: str) -> tuple[int, int]:
    """
    Crea utente esterno in XAtlas e assegna la tessera.
    Restituisce (xatlas_user_id, card_id).
    """
    # 1) Verifica che la card esista in AXS_DB prima di creare l'utente
    card_id = find_card_id_by_clear_code(badge_number)
    if card_id is None:
        raise RuntimeError(
            f"Badge {badge_number} non trovato in AXS_DB. "
            "Il badge fisico deve essere già registrato in XAtlas come tessera."
        )

    # 2) Crea utente esterno
    start_ms, end_ms = _today_ms()
    end_of_use_ms = 4133977199999  # 31/12/2099 come Baudo Pippo
    identifier = f"VIS{badge_number}"

    params = {
        "_dc": int(time.time() * 1000),
        "locale": "it-IT",
        "dummies": json.dumps([{"id": 0, "name": "Qualsiasi"}]),
    }
    body = {
        "companyId": COMPANY_ID,
        "externalCompanyId": EXTERNAL_COMPANY_ID,
        "siteId": SITE_ID,
        "organizationalStructureId": ORGANIZATIONAL_STRUCTURE_ID,
        "identifier": identifier,
        "firstname": first_name,
        "lastname": last_name,
        "allowed": True,
        "enabled": True,
        "safety": True,
        "userType": 29,
        "validityStart": str(start_ms),
        "validityEnd": str(end_ms),
        "endOfUse": str(end_of_use_ms),
        "apbControl": True,
        "apbLunchControl": True,
        "userControl": True,
        "timeControl": True,
        "defaultTransitTime": True,
        "exportTransaction": True,
        "sensitive": True,
        "authGroupId": AUTH_GROUP_ID,
    }
    r = xatlas_request(
        "post",
        "/users/data/ExternalUser/create",
        params=params,
        json=body,
        headers={"x-requested-with": "XMLHttpRequest", "accept": "*/*"},
    )
    if not r.ok:
        raise RuntimeError(f"Errore creazione utente XAtlas: {r.status_code} {r.text[:200]}")
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"XAtlas create non riuscito: {data}")
    xatlas_id = data["records"][0]["id"]
    log.info(f"Utente XAtlas creato: id={xatlas_id} identifier={identifier}")

    # 3) Assegna tessera via /UserCard/assign (endpoint reale catturato con DevTools)
    ar = xatlas_request(
        "post",
        "/users/data/UserCard/assign",
        json={"userId": xatlas_id, "cardId": card_id, "userType": 29},
        headers={
            "x-requested-with": "XMLHttpRequest",
            "accept": "*/*",
            "Content-Type": "application/json;charset=UTF-8",
        },
    )
    if not ar.ok:
        # Rollback: elimina l'utente appena creato per non lasciare orfani
        try:
            delete_xatlas_user(xatlas_id)
        except Exception:
            pass
        raise RuntimeError(f"Assegnazione tessera fallita: {ar.status_code} {ar.text[:200]}")
    aj = ar.json()
    if not aj.get("success"):
        try:
            delete_xatlas_user(xatlas_id)
        except Exception:
            pass
        raise RuntimeError(f"UserCard/assign non riuscito: {aj}")
    log.info(f"Tessera {badge_number} (cardId={card_id}) assegnata a utente {xatlas_id}")

    return xatlas_id, card_id


def unassign_xatlas_card(xatlas_user_id: int, card_id: int):
    """Rimuove l'associazione utente↔tessera in XAtlas."""
    r = xatlas_request(
        "post",
        "/users/data/UserCard/remove",
        json={"userId": xatlas_user_id, "cardId": card_id, "userType": 29},
        headers={
            "x-requested-with": "XMLHttpRequest",
            "accept": "*/*",
            "Content-Type": "application/json;charset=UTF-8",
        },
    )
    if r.ok and r.json().get("success"):
        log.info(f"Tessera cardId={card_id} rimossa da utente {xatlas_user_id}")
    else:
        log.warning(f"UserCard/remove fallito: {r.status_code} {r.text[:200]}")


# ── XAtlas: elimina utente ────────────────────────────────────────────────────

def delete_xatlas_user(xatlas_id: int):
    params = {"_dc": int(time.time() * 1000), "id": xatlas_id}
    r = xatlas_request(
        "delete",
        "/users/data/ExternalUser/destroy",
        params=params,
        headers={"x-requested-with": "XMLHttpRequest"},
    )
    if r.ok:
        log.info(f"Utente XAtlas {xatlas_id} eliminato (badge libero)")
    else:
        log.warning(f"Eliminazione utente XAtlas {xatlas_id} fallita: {r.status_code}")


# ── AXS_DB: leggi transazioni ─────────────────────────────────────────────────

def get_recent_transactions(badge_codes: list[str]) -> list[dict]:
    """
    Cerca transazioni recenti (ultimi 60s) per i badge attivi.
    Tabella AXS_DB: 'transaction'. La colonna 'entry' è boolean
    (true=entrata, false=uscita), 'card_clear_code' contiene direttamente
    il numero badge senza bisogno di JOIN.
    """
    if not badge_codes:
        return []

    try:
        conn = psycopg2.connect(**AXS_DB)
        cur  = conn.cursor()
        placeholders = ",".join(["%s"] * len(badge_codes))
        cur.execute(
            f"""
            SELECT id, event_timestamp, entry, card_clear_code, card_id, user_id
            FROM transaction
            WHERE event_timestamp > NOW() - INTERVAL '60 seconds'
              AND card_clear_code IN ({placeholders})
            ORDER BY event_timestamp ASC
            """,
            badge_codes,
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        log.error(f"Errore lettura transazioni AXS_DB: {e}")
        return []


# ── Ciclo principale ──────────────────────────────────────────────────────────

def process_pending_badges():
    """Crea utenti XAtlas per i visitor con xatlas_status='pending'."""
    try:
        pending = sb_get("visitors", params={
            "xatlas_status": "eq.pending",
            "select": "id,first_name,last_name,badge_number",
        })
    except Exception as e:
        log.error(f"Errore lettura pending da Supabase: {e}")
        return

    for v in pending:
        vid   = v["id"]
        badge = v.get("badge_number")
        fn    = v.get("first_name", "")
        ln    = v.get("last_name",  "")

        if not badge:
            log.warning(f"Visitor {vid} in pending ma senza badge_number, skip")
            continue

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                xid, cid = create_xatlas_user(badge, fn, ln)
                sb_patch(f"visitors?id=eq.{vid}", {
                    "xatlas_status":  "active",
                    "xatlas_user_id": xid,
                })
                log.info(f"Visitor {vid} ({fn} {ln}) attivato: badge={badge} xatlas_id={xid} card_id={cid}")
                break
            except Exception as e:
                log.error(f"Tentativo {attempt}/{MAX_RETRIES} fallito per visitor {vid}: {e}")
                if attempt == MAX_RETRIES:
                    log.error(f"Badge {badge} non attivato dopo {MAX_RETRIES} tentativi — riproverò al prossimo ciclo")
                time.sleep(2)


def process_active_transactions():
    """Legge transazioni AXS_DB per i badge attivi e aggiorna Supabase."""
    try:
        active = sb_get("visitors", params={
            "xatlas_status": "eq.active",
            "select": "id,badge_number,xatlas_user_id,entry_time,exit_time",
        })
    except Exception as e:
        log.error(f"Errore lettura active da Supabase: {e}")
        return

    if not active:
        return

    badge_map = {v["badge_number"]: v for v in active if v.get("badge_number")}
    if not badge_map:
        return

    txns = get_recent_transactions(list(badge_map.keys()))
    for tx in txns:
        badge = tx.get("card_clear_code")
        v     = badge_map.get(badge)
        if not v:
            continue

        vid      = v["id"]
        is_entry = bool(tx.get("entry"))   # true=entrata, false=uscita
        ts       = tx.get("event_timestamp")
        if not ts:
            continue
        time_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)[11:16]

        if is_entry and not v.get("entry_time"):
            try:
                sb_patch(f"visitors?id=eq.{vid}", {
                    "entry_time": time_str,
                    "visit_date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10],
                })
                log.info(f"Entrata registrata: visitor={vid} badge={badge} ora={time_str}")
            except Exception as e:
                log.error(f"Errore PATCH entry_time per visitor {vid}: {e}")

        elif not is_entry:
            try:
                sb_patch(f"visitors?id=eq.{vid}", {
                    "exit_time":     time_str,
                    "xatlas_status": "checked_out",
                })
                log.info(f"Uscita registrata: visitor={vid} badge={badge} ora={time_str}")
                # Libera badge: prima dissocia tessera da utente, poi elimina utente
                xid = v.get("xatlas_user_id")
                if xid:
                    cid = tx.get("card_id") or find_card_id_by_clear_code(badge)
                    if cid is not None:
                        unassign_xatlas_card(xid, cid)
                    delete_xatlas_user(xid)
            except Exception as e:
                log.error(f"Errore PATCH exit_time per visitor {vid}: {e}")


def run_loop():
    log.info("Zucchetti Bridge Agent avviato")
    while True:
        try:
            process_pending_badges()
            process_active_transactions()
        except Exception as e:
            log.error(f"Errore imprevisto nel ciclo principale: {e}")
        time.sleep(POLL_INTERVAL)


# ── Windows Service ───────────────────────────────────────────────────────────

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager

    class ZucchettiService(win32serviceutil.ServiceFramework):
        _svc_name_         = "ZucchettiAgent"
        _svc_display_name_ = "Zucchetti Bridge Agent"
        _svc_description_  = "Sincronizza visitatori Supabase con tornelli XAtlas SuperTRAX"

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self._running  = True

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self._running = False
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            log.info("Service SvcDoRun avviato")
            while self._running:
                try:
                    process_pending_badges()
                    process_active_transactions()
                except Exception as e:
                    log.error(f"Errore nel service loop: {e}")
                for _ in range(POLL_INTERVAL * 10):
                    if not self._running:
                        break
                    time.sleep(0.1)

    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        run_loop()
    elif _HAS_WIN32:
        win32serviceutil.HandleCommandLine(ZucchettiService)
    else:
        # Fallback: esegui in foreground (Linux/Mac o pywin32 non installato)
        run_loop()
