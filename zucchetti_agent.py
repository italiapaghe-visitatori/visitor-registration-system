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


def create_xatlas_user(badge_number: str, first_name: str, last_name: str) -> int:
    """
    Crea un utente esterno in XAtlas e assegna il badge.
    Restituisce l'ID XAtlas dell'utente creato.
    """
    start_ms, end_ms = _today_ms()
    # end_of_use fisso a 31/12/2099 come da profilo Baudo Pippo
    end_of_use_ms = 4133977199999

    identifier = f"VIS{badge_number}"  # identificatore univoco

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

    # ── Assegna tessera ───────────────────────────────────────────────────────
    # TODO: catturare l'endpoint esatto tramite DevTools su "ASSEGNA UNA TESSERA"
    # Istruzioni:
    #   1. Aprire http://192.168.2.196:8080/users/ → ESTERNI → GaInformatica
    #   2. Tab CREDENZIALI → "ASSEGNA UNA TESSERA" → inserire un badge di test
    #   3. F12 > Network > copiare il request URL e payload della chiamata POST
    #   4. Sostituire il blocco TODO sotto con la chiamata reale
    #
    # Endpoint ipotetico (da verificare):
    assign_body = {
        "userId": xatlas_id,
        "clearCode": badge_number,
        # aggiungere altri campi se richiesti dall'endpoint reale
    }
    ar = xatlas_request(
        "post",
        "/users/data/Card/create",   # <-- DA VERIFICARE con DevTools
        params=params,
        json=assign_body,
        headers={"x-requested-with": "XMLHttpRequest", "accept": "*/*"},
    )
    if ar.ok and ar.json().get("success"):
        log.info(f"Tessera {badge_number} assegnata via API (endpoint Card/create)")
    else:
        log.warning(
            f"Assegnazione tessera via API fallita ({ar.status_code}). "
            "Verificare endpoint con DevTools (vedi TODO nel codice)."
        )

    return xatlas_id


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

    TODO: eseguire la query SQL seguente su AXS_DB per trovare il nome
    corretto della tabella transazioni:

        SELECT table_name FROM information_schema.tables
        WHERE table_name ILIKE '%trans%' OR table_name ILIKE '%access%'
           OR table_name ILIKE '%transit%' OR table_name ILIKE '%passage%'
        ORDER BY table_name;

    Poi strisciare il badge di Baudo Pippo e verificare:

        SELECT * FROM <tabella_trovata> ORDER BY id DESC LIMIT 5;

    Sostituire TRANSACTION_TABLE sotto con il nome trovato.
    Verificare anche il nome esatto delle colonne (timestamp, direction, ecc.).
    """
    TRANSACTION_TABLE = "access_transaction"  # <-- DA VERIFICARE

    if not badge_codes:
        return []

    try:
        conn = psycopg2.connect(**AXS_DB)
        cur  = conn.cursor()
        placeholders = ",".join(["%s"] * len(badge_codes))
        cur.execute(
            f"""
            SELECT t.id, t.timestamp, t.direction, c.clear_code, c.user_id
            FROM {TRANSACTION_TABLE} t
            JOIN card c ON c.id = t.card_id
            WHERE t.timestamp > NOW() - INTERVAL '60 seconds'
              AND c.clear_code IN ({placeholders})
            ORDER BY t.timestamp ASC
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
                xid = create_xatlas_user(badge, fn, ln)
                sb_patch(f"visitors?id=eq.{vid}", {
                    "xatlas_status":  "active",
                    "xatlas_user_id": xid,
                })
                log.info(f"Visitor {vid} ({fn} {ln}) attivato: badge={badge} xatlas_id={xid}")
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
        badge = tx.get("clear_code")
        v     = badge_map.get(badge)
        if not v:
            continue

        vid       = v["id"]
        direction = tx.get("direction")   # valore da verificare: 0=entrata, 1=uscita?
        ts        = tx.get("timestamp")
        if not ts:
            continue
        time_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)[11:16]

        # direction = 0 o "IN" = entrata, 1 o "OUT" = uscita
        # Verificare i valori reali dopo aver trovato la tabella transazioni
        is_entry = direction in (0, "0", "IN", "E", 1)   # aggiustare dopo verifica
        is_exit  = direction in (1, "1", "OUT", "U", 2)  # aggiustare dopo verifica

        if is_entry and not v.get("entry_time"):
            try:
                sb_patch(f"visitors?id=eq.{vid}", {
                    "entry_time": time_str,
                    "visit_date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10],
                })
                log.info(f"Entrata registrata: visitor={vid} badge={badge} ora={time_str}")
            except Exception as e:
                log.error(f"Errore PATCH entry_time per visitor {vid}: {e}")

        elif is_exit:
            try:
                sb_patch(f"visitors?id=eq.{vid}", {
                    "exit_time":     time_str,
                    "xatlas_status": "checked_out",
                })
                log.info(f"Uscita registrata: visitor={vid} badge={badge} ora={time_str}")
                # Elimina utente da XAtlas → badge libero
                xid = v.get("xatlas_user_id")
                if xid:
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
