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
import logging.handlers
import os
import random
import smtplib
import ssl
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import psycopg2
from psycopg2 import pool as _pg_pool
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

# Connection pool AXS_DB. Riusa connessioni invece di aprirne una nuova ad ogni
# query: con polling 5s + 100+ visitatori in un evento, il pattern precedente
# (psycopg2.connect ad ogni query) saturava max_connections del server PostgreSQL
# in pochi minuti.
_axs_pool: _pg_pool.SimpleConnectionPool | None = None

def _init_axs_pool() -> None:
    global _axs_pool
    if _axs_pool is None:
        _axs_pool = _pg_pool.SimpleConnectionPool(2, 10, **AXS_DB)

def axs_acquire():
    """Restituisce una connessione dal pool. Usare con `axs_release(conn)` in finally."""
    if _axs_pool is None:
        _init_axs_pool()
    return _axs_pool.getconn()

def axs_release(conn) -> None:
    """Restituisce la connessione al pool, con detection di stato sporco.

    Se la connessione ha una transazione aperta (PostgreSQL transaction_status
    INTRANS o INERROR) o è chiusa, NON la rimette nel pool (così non finisce
    a un altro caller in stato corrotto). La discardiamo con close=True.
    psycopg2.SimpleConnectionPool ricrea automaticamente una nuova conn al
    prossimo getconn.

    Best-effort: errori silenziosi (la connessione potrebbe essere già morta).
    """
    if conn is None or _axs_pool is None:
        return
    try:
        # conn.closed: 0 = aperta. != 0 = chiusa o broken.
        # transaction_status: 0=IDLE, 1=ACTIVE, 2=INTRANS, 3=INERROR, 4=UNKNOWN.
        # Vogliamo restituire al pool solo conn IDLE+aperta; altre vanno scartate.
        is_dirty = (conn.closed != 0) or (conn.info.transaction_status != 0)
    except Exception:
        is_dirty = True
    try:
        _axs_pool.putconn(conn, close=is_dirty)
    except Exception:
        try: conn.close()
        except Exception: pass

# Valori fissi AXS_DB (da non modificare senza rigenerare il profilo)
COMPANY_ID                  = 156
EXTERNAL_COMPANY_ID         = 157
SITE_ID                     = 176
ORGANIZATIONAL_STRUCTURE_ID = 173
AUTH_GROUP_ID               = 249   # gruppo VISITATORI

POLL_INTERVAL = 5    # secondi tra ogni ciclo (era 10, ridotto per latenza minima badge)
MAX_RETRIES   = 3    # tentativi prima di loggare errore e passare oltre

# ── Configurazione INVIO EMAIL (SMTP basic OPPURE Microsoft Graph M365) ─────
# Due strategie supportate, scelte in base alla sezione presente in agent_config.ini:
#
# A) SMTP classico (provider con password app — Aruba, Gmail con app password, etc.)
# [smtp]
# host = smtp.s2s.it
# port = 465
# use_ssl = true             ; true=SSL implicit (465), false=STARTTLS (587)
# username = noreply@s2s.it
# password = ************
# from_email = noreply@s2s.it
# from_name  = Eventi Service to Service
#
# B) Microsoft 365 con OAuth 2.0 (Modern Auth, raccomandato per email @s2s.it su M365)
# [m365_graph]
# tenant_id     = <UUID tenant Azure AD, es. da Entra ID overview>
# client_id     = <UUID app registration>
# client_secret = <secret valore>
# from_email    = noreply@s2s.it
# from_name     = Eventi Service to Service
#
# La sezione B vince se entrambe presenti.
EMAIL_STRATEGY = None

M365_ENABLED = "m365_graph" in cfg and cfg["m365_graph"].get("tenant_id")
if M365_ENABLED:
    M365_TENANT_ID  = cfg["m365_graph"]["tenant_id"]
    M365_CLIENT_ID  = cfg["m365_graph"]["client_id"]
    M365_CLIENT_SEC = cfg["m365_graph"]["client_secret"]
    M365_FROM_EMAIL = cfg["m365_graph"]["from_email"]
    M365_FROM_NAME  = cfg["m365_graph"].get("from_name", "Service to Service")
    EMAIL_STRATEGY  = "m365_graph"

SMTP_ENABLED = (not EMAIL_STRATEGY) and "smtp" in cfg and cfg["smtp"].get("host")
if SMTP_ENABLED:
    SMTP_HOST       = cfg["smtp"]["host"]
    SMTP_PORT       = int(cfg["smtp"].get("port", "465"))
    SMTP_USE_SSL    = cfg["smtp"].get("use_ssl", "true").strip().lower() in ("true","1","yes","on")
    SMTP_USERNAME   = cfg["smtp"]["username"]
    SMTP_PASSWORD   = cfg["smtp"]["password"]
    SMTP_FROM_EMAIL = cfg["smtp"].get("from_email", SMTP_USERNAME)
    SMTP_FROM_NAME  = cfg["smtp"].get("from_name", "Service to Service")
    EMAIL_STRATEGY  = "smtp"

# ── Throttling invio email (anti mail-bomb) ───────────────────────────────────
# Sezione opzionale [email_throttle] in agent_config.ini per regolare il rate
# di invio email QR senza ricompilare. Default conservativi sicuri per
# Microsoft 365 Graph API (limite ~30/min per service principal).
#
# [email_throttle]
# delay_secs    = 6        ; secondi tra un invio e il successivo (default 6 = ~10/min)
# jitter_pct    = 0.30     ; randomness ±30% sul delay (4.2-7.8s con default)
# batch_size    = 1        ; quante email pescare per ciclo dalla queue (era 5)
# reply_to      = tecnico.gelormini@gmail.com  ; indirizzo Reply-To opzionale
#
EMAIL_THROTTLE_DELAY  = float(cfg.get("email_throttle", "delay_secs", fallback="6"))
EMAIL_THROTTLE_JITTER = float(cfg.get("email_throttle", "jitter_pct", fallback="0.30"))
EMAIL_BATCH_SIZE      = int(cfg.get("email_throttle", "batch_size", fallback="1"))
EMAIL_REPLY_TO        = cfg.get("email_throttle", "reply_to", fallback="").strip() or None

# ── Logging ───────────────────────────────────────────────────────────────────

# Log rotation: 10 MB max per file, mantieni 5 backup (totale max ~50 MB).
# Senza rotation, zucchetti_agent.log cresce indefinitamente: con polling 5s
# su 30 giorni = ~17k cicli/giorno = file di centinaia di MB → riempie il
# disco del PC S2S in qualche mese.
_log_path = os.path.join(_dir, "zucchetti_agent.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            _log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        ),
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


AGENT_VERSION = "1.5.2-email-throttle"


def update_heartbeat(notes: str | None = None):
    """Aggiorna il timestamp di vita dell'agente su Supabase.
    Best-effort: errori silenziosi (non vogliamo bloccare il loop principale)."""
    try:
        payload = {
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "agent_version": AGENT_VERSION,
        }
        if notes is not None:
            payload["notes"] = notes
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/agent_status?id=eq.1",
            headers=_sb_headers,
            json=payload,
            timeout=5,
        )
    except Exception:
        pass


# ── XAtlas session ────────────────────────────────────────────────────────────

_xatlas_session: requests.Session | None = None


def xatlas_login():
    """
    Login XAtlas via form POST a /web/login.
    Step 1: GET /web/login per ottenere JSESSIONID iniziale
    Step 2: POST credenziali (form-urlencoded) → 302 redirect a /web/apps se OK
    """
    global _xatlas_session
    s = requests.Session()
    # 1) GET pagina login per cookie JSESSIONID
    s.get(f"{XATLAS_BASE}/web/login", timeout=10)
    # 2) POST credenziali
    r = s.post(
        f"{XATLAS_BASE}/web/login",
        data={
            "username": XATLAS_USER,
            "password": XATLAS_PASS,
            "submit":   "Accedi",
        },
        allow_redirects=False,
        timeout=10,
    )
    # Login OK = 302 redirect verso /web/apps (o comunque NON verso /login)
    if r.status_code in (302, 303):
        loc = r.headers.get("Location", "")
        if "login" not in loc.lower():
            _xatlas_session = s
            log.info(f"XAtlas login OK → {loc}")
            return
        raise RuntimeError(f"XAtlas login: credenziali rifiutate (redirect a {loc})")
    raise RuntimeError(f"XAtlas login fallito: status={r.status_code}")


def xatlas_request(method, path, **kwargs):
    """Wrapper di requests.Session.{get,post,...} con re-login automatico.

    Resilienza:
    - 401 → invalido la sessione e ri-faccio login (token scaduto).
    - ConnectionError / Timeout → invalido la sessione (server XAtlas potrebbe
      essersi riavviato e non riconosce più il JSESSIONID) e riprovo UNA volta
      dopo nuovo login. Senza questo, una sessione "zombie" causerebbe stall di
      ~45min (15s × MAX_RETRIES × N badge in coda) finché qualcuno la riavvia
      manualmente.
    """
    global _xatlas_session
    if _xatlas_session is None:
        xatlas_login()
    url = f"{XATLAS_BASE}{path}"
    try:
        r = getattr(_xatlas_session, method)(url, timeout=15, **kwargs)
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError) as e:
        log.warning(f"XAtlas {method.upper()} {path} fallita ({type(e).__name__}: {e}), re-login e retry…")
        _xatlas_session = None
        xatlas_login()
        r = getattr(_xatlas_session, method)(url, timeout=15, **kwargs)
    if r.status_code == 401:
        _xatlas_session = None
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


def _find_external_user_by_identifier(identifier: str) -> int | None:
    """Cerca user_identifier.id per identifier (es. VIS241026).

    ORDER BY id DESC: in caso di duplicati storici (creati prima del fix
    idempotenza), prende il più recente — riducibile a "stesso utente"
    dal punto di vista dell'agente. Senza ORDER BY, PostgreSQL può tornare
    record in ordine arbitrario tra esecuzioni → comportamento instabile.
    """
    conn = None
    try:
        conn = axs_acquire()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id FROM user_identifier WHERE identifier = %s ORDER BY id DESC LIMIT 1;",
            (identifier,),
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception as e:
        log.error(f"Errore lookup user_identifier {identifier}: {e}")
        return None
    finally:
        if conn is not None:
            axs_release(conn)


def find_card_id_by_clear_code(clear_code: str) -> int | None:
    """Cerca card.id per clear_code (numero badge) in AXS_DB."""
    conn = None
    try:
        conn = axs_acquire()
        cur = conn.cursor()
        cur.execute("SELECT id FROM card WHERE clear_code = %s LIMIT 1;", (clear_code,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception as e:
        log.error(f"Errore lookup card_id per clear_code={clear_code}: {e}")
        return None
    finally:
        if conn is not None:
            axs_release(conn)


def ensure_card_free(card_id: int) -> bool:
    """
    Verifica che la card non sia già assegnata. Se ha user_id che punta
    a un utente NON esistente (orfano), libera automaticamente la card.
    Se la card è assegnata a un utente reale, NON la tocca → ritorna False.
    Inoltre estende la validità della card se è scaduta (1900 → 2100).

    Pattern try/finally garantisce che la conn sia sempre rilasciata al pool,
    anche se cur.close() solleva eccezione (raro ma possibile su connessioni
    rotte). Su exception path, conn.rollback() libera anche il lock FOR UPDATE.
    """
    conn = None
    cur = None
    try:
        conn = axs_acquire()
        cur  = conn.cursor()
        # FOR UPDATE OF c: locka la riga della card per la durata della
        # transazione. Se 2 segretarie cercano di assegnare lo stesso badge
        # in parallelo, la seconda aspetta che la prima committi (e poi vede
        # owner_id valorizzato → ritorna False, no double-assign).
        cur.execute(
            """
            SELECT c.user_id, u.identifier, c.validity_end
            FROM card c
            LEFT JOIN user_identifier u ON u.id = c.user_id
            WHERE c.id = %s
            FOR UPDATE OF c;
            """,
            (card_id,),
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return False
        owner_id, owner_identifier, validity_end = row

        # Estendi validità se scaduta o sta per scadere (entro 1 mese)
        if validity_end is None or validity_end < datetime.now() + timedelta(days=30):
            cur.execute(
                """
                UPDATE card
                SET validity_start = '1900-01-01 00:00:00',
                    validity_end   = '2100-12-31 23:59:59'
                WHERE id = %s;
                """,
                (card_id,),
            )
            log.info(f"Card {card_id}: validità estesa a 1900→2100 (era {validity_end})")

        if owner_id is None:
            conn.commit()
            return True  # già libera

        if owner_identifier is None:
            # user_id punta a utente non esistente → orfano, libera
            cur.execute("UPDATE card SET user_id = NULL WHERE id = %s;", (card_id,))
            conn.commit()
            log.info(f"Card {card_id}: liberata da user_id orfano {owner_id}")
            return True

        # Utente reale: non liberare
        conn.commit()
        log.warning(
            f"Card {card_id} è assegnata a {owner_identifier} (id={owner_id}), "
            "non liberata automaticamente. Risolvere manualmente."
        )
        return False

    except Exception as e:
        log.error(f"Errore ensure_card_free({card_id}): {e}")
        if conn is not None:
            try: conn.rollback()
            except Exception: pass
        return False
    finally:
        if cur is not None:
            try: cur.close()
            except Exception: pass
        if conn is not None:
            axs_release(conn)


def find_or_create_card_id(clear_code: str) -> int | None:
    """
    Cerca card.id per clear_code. Se non esiste la crea automaticamente
    con user_id=NULL (libera, pronta per assegnazione).
    Validità: oggi → 31/12/2099 (long-term, riutilizzabile).
    Card_format_id: 204 (125_Zucchetti, come Baudo Pippo).
    """
    existing = find_card_id_by_clear_code(clear_code)
    if existing is not None:
        return existing

    if not clear_code or not clear_code.isdigit() or not (3 <= len(clear_code) <= 12):
        log.error(f"clear_code non valido per auto-creazione: '{clear_code}'")
        return None

    log.info(f"Card {clear_code} non esiste in AXS_DB → auto-creazione (user_id=NULL)")
    conn = None
    try:
        conn = axs_acquire()
        conn.autocommit = False
        cur = conn.cursor()

        # Validità lunghissima come Baudo Pippo (sempre attiva, riutilizzabile)
        validity_start = datetime(1900, 1, 1, 0, 0, 0)
        validity_end   = datetime(2100, 12, 31, 23, 59, 59)

        # 1) INSERT card (user_id=NULL → libera)
        # Tutti i campi primitivi richiesti da Hibernate Card entity:
        #   object_type=47 (tipo entity Card), object_version=0 (init),
        #   card_type=1 (Zucchetti), use_card_authorizations=true (come Baudo)
        cur.execute(
            """
            INSERT INTO card (
                id, clear_code, card_type, enabled, user_id, site, default_auth_group_id,
                use_card_authorizations, validity_start, validity_end,
                log_insert, log_update, record_version,
                lost, destroyed, scheduled_presence,
                object_type, object_version,
                escort_required, escort_capable, emitted,
                control_selector, selector_operator
            )
            VALUES (
                nextval('card_id_seq'), %s, 1, true, NULL, %s, %s,
                true, %s, %s,
                NOW(), NOW(), 1,
                false, false, false,
                47, 0,
                false, false, false,
                false, false
            )
            RETURNING id;
            """,
            (clear_code, SITE_ID, AUTH_GROUP_ID, validity_start, validity_end),
        )
        new_card_id = cur.fetchone()[0]

        # 2) INSERT card_code (formato 204 = 125_Zucchetti, obbligatorio per il tornello)
        cur.execute(
            """
            INSERT INTO card_code (
                card_id, code, edition, object_version, card_format_id, log_update, record_version
            )
            VALUES (%s, %s, 0, 0, 204, NOW(), 1);
            """,
            (new_card_id, clear_code),
        )

        conn.commit()
        cur.close()
        log.info(f"Card auto-creata: clear_code={clear_code} id={new_card_id}")
        return new_card_id

    except Exception as e:
        log.error(f"Errore auto-creazione card {clear_code}: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if conn:
            axs_release(conn)


def create_xatlas_user(badge_number: str, first_name: str, last_name: str) -> tuple[int, int]:
    """
    Crea utente esterno in XAtlas e assegna la tessera.
    Restituisce (xatlas_user_id, card_id).
    """
    # 1) Trova card o creala se non esiste (sempre con user_id=NULL)
    card_id = find_or_create_card_id(badge_number)
    if card_id is None:
        raise RuntimeError(
            f"Impossibile ottenere card_id per badge {badge_number} "
            "(lookup fallito e auto-creazione non riuscita)"
        )

    # 1b) Verifica che la card sia libera (auto-libera se orfana, fallisce se utente reale)
    if not ensure_card_free(card_id):
        raise RuntimeError(
            f"Card {badge_number} (id={card_id}) è già assegnata a un utente reale. "
            "Liberarla manualmente prima di riprovare."
        )

    # 2) Crea utente esterno (con idempotenza: salta se identifier già esistente)
    start_ms, end_ms = _today_ms()
    end_of_use_ms = 4133977199999  # 31/12/2099 come Baudo Pippo
    identifier = f"VIS{badge_number}"

    # IDEMPOTENZA: se l'agente è crashato dopo INSERT user_identifier ma prima
    # di PATCH visitors.xatlas_status='active', al restart riprocessa lo stesso
    # visitor. Senza questo check, creerebbe un secondo utente VIS{badge}
    # duplicato → tornello confuso. Check PRE-create: se identifier esiste
    # già → riusa quel xatlas_id e salta la POST /create.
    existing_xatlas_id = _find_external_user_by_identifier(identifier)
    if existing_xatlas_id is not None:
        xatlas_id = existing_xatlas_id
        log.info(f"Utente XAtlas {identifier} già esistente (id={xatlas_id}), riuso (skip create)")
    else:
        params = {
            "_dc": int(time.time() * 1000),
            "locale": "it-IT",
            "dummies": json.dumps([{"id": 0, "name": "Qualsiasi"}]),
        }
        short_name = f"{last_name} {first_name}".strip()  # formato come Baudo Pippo
        body = {
            "companyId": COMPANY_ID,
            "externalCompanyId": EXTERNAL_COMPANY_ID,
            "siteId": SITE_ID,
            "organizationalStructureId": ORGANIZATIONAL_STRUCTURE_ID,
            "identifier": identifier,
            "firstname": first_name,
            "lastname":  last_name,
            "shortName": short_name,
            "name":      first_name,
            "surname":   last_name,
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
        if r.ok:
            data = r.json()
            if data.get("success"):
                xatlas_id = data["records"][0]["id"]
                log.info(f"Utente XAtlas creato: id={xatlas_id} identifier={identifier}")
            else:
                raise RuntimeError(f"XAtlas create non riuscito: {data}")
        else:
            # Race condition fallback: se nel frattempo un altro processo l'ha
            # creato (vincolo univoco), recuperalo dal DB invece di fallire.
            if "vincolo univoco" in r.text or "external_users" in r.text or "duplic" in r.text.lower():
                existing_id = _find_external_user_by_identifier(identifier)
                if existing_id:
                    xatlas_id = existing_id
                    log.info(f"Utente XAtlas {identifier} appena creato da altro processo (id={xatlas_id}), riuso")
                else:
                    raise RuntimeError(f"Utente esiste ma non lo trovo via DB: {r.status_code}")
            else:
                raise RuntimeError(f"Errore creazione utente XAtlas: {r.status_code} {r.text[:200]}")

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
        try:
            delete_xatlas_user(xatlas_id)
        except Exception:
            pass
        raise RuntimeError(f"Assegnazione tessera fallita: {ar.status_code} {ar.text[:200]}")
    # /UserCard/assign può rispondere 200 con body vuoto (= successo) oppure JSON
    body = ar.text.strip()
    if body:
        try:
            aj = ar.json()
            if not aj.get("success", True):
                try:
                    delete_xatlas_user(xatlas_id)
                except Exception:
                    pass
                raise RuntimeError(f"UserCard/assign non riuscito: {aj}")
        except ValueError:
            log.info(f"UserCard/assign risposta non-JSON ma 200 OK, considero successo: {body[:80]}")
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
    if not r.ok:
        log.warning(f"UserCard/remove fallito: {r.status_code} {r.text[:200]}")
        return
    body = r.text.strip()
    if body:
        try:
            if not r.json().get("success", True):
                log.warning(f"UserCard/remove non riuscito: {r.text[:200]}")
                return
        except ValueError:
            pass  # 200 OK senza JSON = successo
    log.info(f"Tessera cardId={card_id} rimossa da utente {xatlas_user_id}")


# ── XAtlas: elimina utente ────────────────────────────────────────────────────

def delete_xatlas_user(xatlas_id: int):
    """Elimina utente esterno XAtlas via POST (convention ExtJS, NON DELETE)."""
    r = xatlas_request(
        "post",
        "/users/data/ExternalUser/destroy",
        json={"id": xatlas_id, "userType": 29},
        headers={
            "x-requested-with": "XMLHttpRequest",
            "accept": "*/*",
            "Content-Type": "application/json;charset=UTF-8",
        },
    )
    if r.ok:
        try:
            ok_flag = r.json().get("success", False)
        except Exception:
            ok_flag = True
        if ok_flag:
            log.info(f"Utente XAtlas {xatlas_id} eliminato (badge libero)")
            return
    log.warning(f"Eliminazione utente XAtlas {xatlas_id} fallita: {r.status_code} {r.text[:200]}")


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

    conn = None
    cur = None
    try:
        conn = axs_acquire()
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
        return rows
    except Exception as e:
        log.error(f"Errore lettura transazioni AXS_DB: {e}")
        return []
    finally:
        if cur is not None:
            try: cur.close()
            except Exception: pass
        if conn is not None:
            axs_release(conn)


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


def process_pool_preparation():
    """Pre-attiva i badge nel pool: crea utenti VIS{badge} generici e assegna le card.
    Status: preparing -> available. L'admin poi associa il badge a un visitatore al volo
    (modale Walk-in dal pool) senza ulteriore lavoro dell'agente."""
    try:
        pending = sb_get("badge_pool", params={
            "status": "eq.preparing",
            "select": "id,badge_number,event_id",
            "limit": "10",  # max 10 per ciclo per non saturare XAtlas API
        })
    except Exception as e:
        log.warning(f"process_pool_preparation: lettura pool fallita: {e}")
        return

    if not pending:
        return

    log.info(f"process_pool_preparation: trovati {len(pending)} badge da pre-attivare")
    for p in pending:
        pid   = p["id"]
        badge = p.get("badge_number")
        if not badge:
            continue
        try:
            # Identifier "POOL{badge}" per distinguere da utenti VIS normali
            xid, cid = create_xatlas_user(badge, "Pool", f"Badge{badge}")
            sb_patch(f"badge_pool?id=eq.{pid}", {
                "status":         "available",
                "xatlas_user_id": xid,
                "card_id":        cid,
                "activated_at":   datetime.now(timezone.utc).isoformat(),
            })
            log.info(f"Pool badge {badge} pre-attivato: pool_id={pid} xatlas={xid} card={cid}")
        except Exception as e:
            log.error(f"Pool badge {badge} (pool_id={pid}) attivazione fallita: {e}")


def is_event_open(event_id):
    """Ritorna True se l'evento esiste e non è ancora chiuso."""
    if not event_id:
        return False
    try:
        rows = sb_get("events", params={
            "id": f"eq.{event_id}",
            "select": "id,closed_at",
        })
        if not rows:
            return False
        return rows[0].get("closed_at") is None
    except Exception as e:
        log.warning(f"is_event_open({event_id}): {e}")
        return False


def record_movement(visitor_id, event_id, ts_iso, direction, badge, tx_id=None):
    """Append-only log delle timbrature in visitor_movements (prova legale).

    Idempotente: usa on_conflict=raw_transaction_id + ignore-duplicates per
    evitare doppioni quando l'agente rilegge le stesse transazioni AXS_DB ad
    ogni ciclo (window overlap)."""
    try:
        body = {
            "visitor_id":   visitor_id,
            "event_id":     event_id,
            "timestamp":    ts_iso,
            "direction":    direction,
            "badge_number": badge,
            "source":       "xatlas",
        }
        if tx_id is not None:
            body["raw_transaction_id"] = tx_id
            url = f"{SUPABASE_URL}/rest/v1/visitor_movements?on_conflict=raw_transaction_id"
            headers = {**_sb_headers, "Prefer": "resolution=ignore-duplicates,return=minimal"}
        else:
            url = f"{SUPABASE_URL}/rest/v1/visitor_movements"
            headers = _sb_headers
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if not r.ok and r.status_code != 409:
            log.warning(f"record_movement HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.warning(f"record_movement fallito: {e}")


def process_active_transactions():
    """Legge transazioni AXS_DB per i badge attivi e aggiorna Supabase.

    Comportamento differenziato in base a visitor.event_id:
    - Se visitor è in un evento ancora aperto: ogni timbratura registrata in
      visitor_movements (prova legale), aggiorna entry/exit_time, ma NON archivia
      al primo exit (i rientri sono attesi). Badge resta attivo per tutto l'evento.
    - Altrimenti (giorni normali): comportamento attuale. Primo exit = checked_out
      + libera badge.
    """
    try:
        active = sb_get("visitors", params={
            "xatlas_status": "eq.active",
            "select": "id,badge_number,xatlas_user_id,entry_time,exit_time,event_id,xatlas_renamed",
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
        eid      = v.get("event_id")
        is_entry = bool(tx.get("entry"))   # true=entrata, false=uscita
        ts       = tx.get("event_timestamp")
        tx_id    = tx.get("id")
        if not ts:
            continue
        time_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)[11:16]
        ts_iso   = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

        # Sempre traccia il movimento (prova legale completa)
        record_movement(vid, eid, ts_iso, "entry" if is_entry else "exit", badge, tx_id)

        if is_entry:
            try:
                patch = {}
                # Prima entrata: imposta entry_time + visit_date
                if not v.get("entry_time"):
                    patch["entry_time"] = time_str
                    patch["visit_date"] = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
                # Rientro durante evento attivo: reset exit_time (è dentro adesso)
                if eid and is_event_open(eid) and v.get("exit_time"):
                    patch["exit_time"] = None
                    log.info(f"Rientro evento: visitor={vid} badge={badge} ora={time_str}")
                if patch:
                    sb_patch(f"visitors?id=eq.{vid}", patch)
                    if "entry_time" in patch:
                        log.info(f"Entrata registrata: visitor={vid} badge={badge} ora={time_str}")
            except Exception as e:
                log.error(f"Errore PATCH entry per visitor {vid}: {e}")

        else:
            # Uscita: comportamento dipende da evento attivo
            event_open = eid and is_event_open(eid)
            # Walk-in dal pool ancora da rinominare: NON archiviare, NON cancellare
            # l'utente XAtlas (lo userà process_pool_walkin_recreate per il delete+create).
            # Anche se non c'è evento aperto, lasciamo lo stato active perché il visitor
            # ha bisogno di essere ricreato col nome reale prima di chiudere.
            pending_recreate = (v.get("xatlas_renamed") is False)
            try:
                if event_open:
                    # In evento: solo aggiorna exit_time, NON archiviare, NON liberare badge.
                    # Il visitor potrebbe rientrare (pausa pranzo/sigaretta/auto).
                    sb_patch(f"visitors?id=eq.{vid}", {"exit_time": time_str})
                    log.info(f"Uscita evento (no archive): visitor={vid} badge={badge} ora={time_str}")
                elif pending_recreate:
                    # Walk-in pool non ancora rinominato: solo aggiorna exit_time, lascia active.
                    # Il recreate lo gestirà al prossimo ciclo.
                    sb_patch(f"visitors?id=eq.{vid}", {"exit_time": time_str})
                    log.info(f"Uscita pre-recreate (no archive): visitor={vid} badge={badge} ora={time_str}")
                else:
                    # Giorno normale (no evento, no pool pending): comportamento attuale.
                    sb_patch(f"visitors?id=eq.{vid}", {
                        "exit_time":     time_str,
                        "xatlas_status": "checked_out",
                    })
                    log.info(f"Uscita registrata: visitor={vid} badge={badge} ora={time_str}")
                    xid = v.get("xatlas_user_id")
                    if xid:
                        cid = tx.get("card_id") or find_card_id_by_clear_code(badge)
                        if cid is not None:
                            unassign_xatlas_card(xid, cid)
                        delete_xatlas_user(xid)
            except Exception as e:
                log.error(f"Errore PATCH exit per visitor {vid}: {e}")


def startup_catchup():
    """
    All'avvio dell'agente, recupera eventuali transazioni mancate
    per i visitatori active mentre il servizio era fermo.
    Cerca fino a 24 ore indietro.

    IMPORTANTE: prima di processare le transazioni, esegue process_pool_walkin_recreate
    per assicurarsi che i walk-in pool pending abbiano l'utente XAtlas col nome reale.
    Altrimenti un exit catchup potrebbe archiviare e cancellare il vecchio user pool
    prima che il recreate abbia avuto modo di intervenire.
    """
    try:
        process_pool_walkin_recreate()
    except Exception as e:
        log.warning(f"Catchup: process_pool_walkin_recreate fallito: {e}")

    try:
        active = sb_get("visitors", params={
            "xatlas_status": "eq.active",
            "select": "id,badge_number,xatlas_user_id,entry_time,exit_time,first_name,last_name,xatlas_renamed,event_id",
        })
    except Exception as e:
        log.error(f"Catchup: errore lettura active: {e}")
        return

    if not active:
        return

    log.info(f"Catchup: controllo {len(active)} visitatori attivi per transazioni mancate")

    for v in active:
        badge = v.get("badge_number")
        vid   = v["id"]
        if not badge:
            continue

        try:
            conn = axs_acquire()
            cur  = conn.cursor()
            cur.execute(
                """
                SELECT id, event_timestamp, entry, card_id
                FROM transaction
                WHERE card_clear_code = %s
                  AND event_timestamp > NOW() - INTERVAL '24 hours'
                ORDER BY event_timestamp ASC;
                """,
                (badge,),
            )
            rows = cur.fetchall()
            cur.close()
            axs_release(conn)
        except Exception as e:
            log.error(f"Catchup: errore query badge {badge}: {e}")
            continue

        for tx_id, ts, is_entry, card_id in rows:
            time_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)[11:16]

            if is_entry and not v.get("entry_time"):
                try:
                    sb_patch(f"visitors?id=eq.{vid}", {
                        "entry_time": time_str,
                        "visit_date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10],
                    })
                    log.info(f"Catchup ENTRATA: visitor={vid} ({v.get('first_name')} {v.get('last_name')}) badge={badge} ora={time_str}")
                    v["entry_time"] = time_str
                except Exception as e:
                    log.error(f"Catchup PATCH entry_time visitor={vid}: {e}")

            elif not is_entry:
                try:
                    eid = v.get("event_id")
                    event_open = eid and is_event_open(eid)
                    pending_recreate = (v.get("xatlas_renamed") is False)
                    if event_open or pending_recreate:
                        # Evento aperto o walk-in pool non ancora ricreato:
                        # NON archiviare, NON cancellare l'utente XAtlas.
                        sb_patch(f"visitors?id=eq.{vid}", {"exit_time": time_str})
                        reason = "evento aperto" if event_open else "pool pre-recreate"
                        log.info(f"Catchup USCITA (no archive, {reason}): visitor={vid} ({v.get('first_name')} {v.get('last_name')}) badge={badge} ora={time_str}")
                        break
                    # Caso normale: archiviazione + libera badge
                    sb_patch(f"visitors?id=eq.{vid}", {
                        "exit_time":     time_str,
                        "xatlas_status": "checked_out",
                    })
                    log.info(f"Catchup USCITA: visitor={vid} ({v.get('first_name')} {v.get('last_name')}) badge={badge} ora={time_str}")
                    xid = v.get("xatlas_user_id")
                    if xid:
                        cid = card_id or find_card_id_by_clear_code(badge)
                        if cid:
                            unassign_xatlas_card(xid, cid)
                        delete_xatlas_user(xid)
                    break  # uscita registrata, stop
                except Exception as e:
                    log.error(f"Catchup uscita (PATCH/cleanup XAtlas) visitor={vid}: {e}")


_last_midnight_cleanup_date = None

def midnight_cleanup_stale_visitors():
    """Una volta al giorno (dopo mezzanotte), archivia automaticamente i visitor 'active'
    creati in giorni precedenti e ancora 'fuori' (entry_time popolato, exit_time popolato,
    nessun rientro) — quindi sono persone che hanno timbrato ieri e non sono tornate.
    Salta se l'evento è ancora aperto: in quel caso aspettiamo la chiusura manuale."""
    global _last_midnight_cleanup_date
    today = date.today()
    # Esegui solo una volta per giorno
    if _last_midnight_cleanup_date == today:
        return
    # Esegui solo dopo le 00:30 (lasciamo margine per timbrature in coda)
    now = datetime.now()
    if now.hour == 0 and now.minute < 30:
        return

    try:
        # Visitor active con visit_date < oggi e exit_time già popolato (sono usciti ieri o prima)
        ymd = today.strftime("%Y-%m-%d")
        rows = sb_get("visitors", params={
            "xatlas_status": "eq.active",
            "visit_date": f"lt.{ymd}",
            "exit_time": "not.is.null",
            "select": "id,event_id,first_name,last_name,visit_date",
            "limit": "100",
        })
    except Exception as e:
        log.warning(f"midnight_cleanup: lettura fallita: {e}")
        return

    if not rows:
        _last_midnight_cleanup_date = today
        return

    # Filtra: salta visitor di eventi ancora aperti
    to_archive = []
    for v in rows:
        eid = v.get("event_id")
        if eid and is_event_open(eid):
            continue  # evento ancora aperto, l'operatore archivierà alla chiusura
        to_archive.append(v)

    if not to_archive:
        _last_midnight_cleanup_date = today
        return

    log.info(f"midnight_cleanup: archivio {len(to_archive)} visitor stale del giorno precedente")
    for v in to_archive:
        try:
            sb_patch(f"visitors?id=eq.{v['id']}", {"xatlas_status": "checked_out"})
            log.info(f"midnight_cleanup: archiviato {v['first_name']} {v['last_name']} (id={v['id']}, visit_date={v.get('visit_date')})")
        except Exception as e:
            log.warning(f"midnight_cleanup PATCH fallito per visitor {v['id']}: {e}")

    _last_midnight_cleanup_date = today


def process_pool_walkin_recreate():
    """Per i visitatori venuti dal pool (xatlas_user_id != NULL + xatlas_renamed=false),
    SOSTITUISCE l'utente XAtlas pool ('Pool BadgeXXX') con uno nuovo dal nome reale.

    Il display tornello SuperTRAX legge da una cache locale che si aggiorna SOLO via
    NET9x sync — e il sync NET9x è triggerato SOLO da chiamate API XAtlas (create/assign),
    NON da UPDATE SQL diretto. Per questo serve delete+recreate, non un semplice rename.

    Sequenza per ogni walk-in:
      1) unassign card dal vecchio user pool
      2) delete vecchio user pool (libera l'identifier VIS{badge})
      3) create nuovo user con nome reale + assign card (single call)
      4) PATCH visitor + badge_pool con nuovo xatlas_user_id

    Limite 5 visitor per ciclo per non saturare le API XAtlas (operazione pesante)."""
    try:
        rows = sb_get("visitors", params={
            "xatlas_user_id": "not.is.null",
            "xatlas_renamed": "is.false",
            "xatlas_status":  "eq.active",
            "select": "id,first_name,last_name,xatlas_user_id,badge_number",
            "limit": "5",
        })
    except Exception as e:
        log.warning(f"process_pool_walkin_recreate: lettura fallita: {e}")
        return

    if not rows:
        return

    log.info(f"process_pool_walkin_recreate: {len(rows)} walk-in da ricreare per nome al tornello")
    for v in rows:
        vid     = v["id"]
        old_xid = v.get("xatlas_user_id")
        fn      = (v.get("first_name") or "").strip()
        ln      = (v.get("last_name")  or "").strip()
        badge   = v.get("badge_number")

        # Skip se manca qualcosa di essenziale (e marca come renamed per evitare loop)
        if not (old_xid and fn and ln and badge):
            try: sb_patch(f"visitors?id=eq.{vid}", {"xatlas_renamed": True})
            except Exception: pass
            continue

        # Skip se è ancora un placeholder pool (first_name='Pool')
        if fn.lower() == "pool":
            try: sb_patch(f"visitors?id=eq.{vid}", {"xatlas_renamed": True})
            except Exception: pass
            continue

        try:
            card_id = find_card_id_by_clear_code(badge)
            if card_id is None:
                log.warning(f"recreate vid={vid}: card {badge} non trovata, skip")
                sb_patch(f"visitors?id=eq.{vid}", {"xatlas_renamed": True})
                continue

            # Step 1: unassign card dal vecchio user pool (libera la card)
            try:
                unassign_xatlas_card(old_xid, card_id)
                log.debug(f"recreate vid={vid}: card {card_id} unassigned da old_xid={old_xid}")
            except Exception as e:
                log.warning(f"recreate vid={vid}: unassign old_xid={old_xid}: {e}")
                # prosegui: magari era già unassigned

            # Step 2: delete vecchio user pool (libera identifier VIS{badge})
            try:
                delete_xatlas_user(old_xid)
                log.debug(f"recreate vid={vid}: old_xid={old_xid} deleted")
            except Exception as e:
                log.warning(f"recreate vid={vid}: delete old_xid={old_xid}: {e}")
                # prosegui: il create sotto userà _find_external_user_by_identifier

            # Step 3: create nuovo user con nome reale + assign card (single call)
            new_xid, new_cid = create_xatlas_user(badge, fn, ln)

            # Step 4: PATCH visitor + badge_pool con nuovo xatlas_user_id
            sb_patch(f"visitors?id=eq.{vid}", {
                "xatlas_user_id": new_xid,
                "xatlas_renamed": True,
            })
            try:
                sb_patch(f"badge_pool?xatlas_user_id=eq.{old_xid}", {
                    "xatlas_user_id": new_xid
                })
            except Exception as e:
                log.warning(f"recreate vid={vid}: PATCH badge_pool: {e}")

            log.info(f"Walk-in pool RICREATO: vid={vid} {ln} {fn} badge={badge} old_xid={old_xid} -> new_xid={new_xid}")

        except Exception as e:
            log.error(f"recreate vid={vid} {fn} {ln} badge={badge}: {e}")
            # Non marca renamed=true, l'agente riproverà al prossimo ciclo


# ── M365 GRAPH (Modern Authentication via OAuth client_credentials) ──────────
_m365_token_cache = {"token": None, "expires_at": 0, "next_retry_at": 0, "consecutive_failures": 0}

def _m365_get_token():
    """Ottiene un access token M365 via client_credentials flow.

    Resilienza:
    - Cache in memoria (token validità ~1h, refresh 5 min prima della scadenza).
    - Se il token endpoint fallisce, NON spamma retry: salta il prossimo tentativo
      con backoff esponenziale (60s, 120s, 240s, max 600s). Senza, l'email_queue
      worker tentava 5 email/ciclo × 12 cicli/min = 60 errori/min nel log,
      saturando il file e bloccando le altre operazioni.
    - Token cache invalidata (None) su errore così non torna un token già scaduto.
    """
    now = time.time()
    # Cache valida → torna subito
    if _m365_token_cache["token"] and _m365_token_cache["expires_at"] > now + 60:
        return _m365_token_cache["token"]
    # Backoff: se ho fallito di recente, aspetta prima di riprovare
    if _m365_token_cache["next_retry_at"] > now:
        wait_s = int(_m365_token_cache["next_retry_at"] - now)
        raise RuntimeError(f"M365 token: backoff attivo, riprovo tra {wait_s}s (failures consecutivi: {_m365_token_cache['consecutive_failures']})")
    try:
        r = requests.post(
            f"https://login.microsoftonline.com/{M365_TENANT_ID}/oauth2/v2.0/token",
            data={
                "grant_type":    "client_credentials",
                "client_id":     M365_CLIENT_ID,
                "client_secret": M365_CLIENT_SEC,
                "scope":         "https://graph.microsoft.com/.default",
            },
            timeout=15,
        )
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        # Token request fallita: invalida cache, calcola next_retry con exp backoff
        _m365_token_cache["token"] = None
        _m365_token_cache["consecutive_failures"] += 1
        backoff_s = min(60 * (2 ** (_m365_token_cache["consecutive_failures"] - 1)), 600)
        _m365_token_cache["next_retry_at"] = now + backoff_s
        log.warning(
            f"M365 token request fallita ({type(e).__name__}: {e}). "
            f"Backoff {backoff_s}s (failures consecutivi: {_m365_token_cache['consecutive_failures']})"
        )
        raise
    # Successo: reset backoff
    _m365_token_cache["token"]                 = j["access_token"]
    _m365_token_cache["expires_at"]            = now + int(j.get("expires_in", 3600)) - 300
    _m365_token_cache["next_retry_at"]         = 0
    _m365_token_cache["consecutive_failures"]  = 0
    return _m365_token_cache["token"]


def _m365_graph_send(to_email, to_name, subject, body_html):
    """Invia un'email via Microsoft Graph API (sendMail).
    L'app deve avere permission 'Mail.Send' (Application) con admin consent.
    Ritorna (ok, error)."""
    try:
        token = _m365_get_token()
        recipients = [{"emailAddress": {"address": to_email}}]
        if to_name:
            recipients[0]["emailAddress"]["name"] = to_name
        message = {
            "subject": subject,
            "body":    {"contentType": "HTML", "content": body_html},
            "toRecipients": recipients,
            "from": {"emailAddress": {"address": M365_FROM_EMAIL, "name": M365_FROM_NAME}},
        }
        # Reply-To (opzionale): se configurato in [email_throttle], imposta un
        # indirizzo umano dove l'ospite possa rispondere → segnale "transazionale"
        # legittimo, riduce probabilità di classificazione bulk dai filtri spam.
        if EMAIL_REPLY_TO:
            message["replyTo"] = [{"emailAddress": {"address": EMAIL_REPLY_TO}}]
        # Headers identificativi (anti pattern bulk/spam): X-Mailer dichiara
        # l'origine, X-Priority normale, X-VRS-Agent traccia il mittente
        # software. Graph API li accetta come internetMessageHeaders custom
        # (prefix X- obbligatorio).
        message["internetMessageHeaders"] = [
            {"name": "X-Mailer",   "value": f"S2S-VisitorRegistration/{AGENT_VERSION}"},
            {"name": "X-Priority", "value": "3"},
            {"name": "X-VRS-Agent","value": "zucchetti-bridge"},
        ]
        body = {"message": message, "saveToSentItems": "false"}
        r = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{M365_FROM_EMAIL}/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=20,
        )
        if r.status_code in (200, 202):
            return True, None
        return False, f"Graph API HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)[:500]


def _smtp_send(to_email, to_name, subject, body_html):
    """Invia un'email via SMTP usando le credenziali configurate.
    Ritorna (ok: bool, error: str|None)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = formataddr((SMTP_FROM_NAME, SMTP_FROM_EMAIL))
    msg["To"]      = formataddr((to_name or "", to_email))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    try:
        if SMTP_USE_SSL:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as srv:
                srv.login(SMTP_USERNAME, SMTP_PASSWORD)
                srv.sendmail(SMTP_FROM_EMAIL, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as srv:
                srv.ehlo()
                srv.starttls(context=ssl.create_default_context())
                srv.ehlo()
                srv.login(SMTP_USERNAME, SMTP_PASSWORD)
                srv.sendmail(SMTP_FROM_EMAIL, [to_email], msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)[:500]


def _send_email(to_email, to_name, subject, body_html):
    """Wrapper unico: usa la strategia configurata (m365_graph o smtp)."""
    if EMAIL_STRATEGY == "m365_graph":
        return _m365_graph_send(to_email, to_name, subject, body_html)
    if EMAIL_STRATEGY == "smtp":
        return _smtp_send(to_email, to_name, subject, body_html)
    return False, "Nessuna strategia email configurata (manca [smtp] o [m365_graph] in agent_config.ini)"


def process_email_queue():
    """Processa email_queue: invio QR personali ai partecipanti.
    Strategia: M365 Graph API (Modern Auth) o SMTP basic, scelta da config.

    Anti mail-bomb (v1.5.2):
    - batch_size = 1 per ciclo (era 5) → niente burst all'interno del loop
    - delay EMAIL_THROTTLE_DELAY ± jitter tra email successive nello stesso batch
    - per default 96 email vengono spedite in ~10 minuti a ~10/min (sotto soglia
      throttling M365 di 30/min e pattern simil-umano per filtri anti-spam EOP)
    """
    if not EMAIL_STRATEGY:
        return  # nessuna config email → silenzio (l'admin lo deve configurare a mano)
    try:
        rows = sb_get("email_queue", params={
            "status": "eq.pending",
            "select": "id,guest_id,event_id,to_email,to_name,subject,body_html,attempts",
            "order":  "scheduled_at.asc",
            "limit":  str(EMAIL_BATCH_SIZE),
        })
    except Exception as e:
        log.warning(f"process_email_queue: lettura coda fallita: {e}")
        return

    if not rows:
        return

    log.info(f"process_email_queue: {len(rows)} email da inviare (throttle={EMAIL_THROTTLE_DELAY}s±{int(EMAIL_THROTTLE_JITTER*100)}%)")
    for idx, r in enumerate(rows):
        eid = r["id"]
        # Marca status='sending' per evitare doppio invio se due cicli si sovrappongono
        try:
            sb_patch(f"email_queue?id=eq.{eid}", {"status": "sending"})
        except Exception:
            pass
        attempts = int(r.get("attempts") or 0) + 1
        ok, err = _send_email(r["to_email"], r.get("to_name"), r["subject"], r["body_html"])
        if ok:
            try:
                sb_patch(f"email_queue?id=eq.{eid}", {
                    "status":   "sent",
                    "sent_at":  datetime.now(timezone.utc).isoformat(),
                    "attempts": attempts,
                    "error":    None,
                })
                log.info(f"Email QR inviata: id={eid} to={r['to_email']}")
            except Exception as e:
                log.warning(f"PATCH email_queue {eid} dopo send OK: {e}")
        else:
            # Se < 3 tentativi, riporta a pending; altrimenti marca failed
            new_status = "failed" if attempts >= 3 else "pending"
            try:
                sb_patch(f"email_queue?id=eq.{eid}", {
                    "status":   new_status,
                    "attempts": attempts,
                    "error":    err,
                })
                log.warning(f"Email QR fallita ({attempts}/3): id={eid} to={r['to_email']} err={err[:120]}")
            except Exception as e:
                log.warning(f"PATCH email_queue {eid} dopo send FAIL: {e}")
        # Throttle inter-email: aspetta prima di inviare la prossima del batch
        # (no delay dopo l'ultima del batch — basterà il POLL_INTERVAL del loop)
        if idx < len(rows) - 1 and EMAIL_THROTTLE_DELAY > 0:
            jitter = EMAIL_THROTTLE_DELAY * EMAIL_THROTTLE_JITTER
            wait = EMAIL_THROTTLE_DELAY + random.uniform(-jitter, jitter)
            time.sleep(max(0.5, wait))


def cleanup_archived_visitors():
    """Libera badge per visitor archiviati (xatlas_status=checked_out) ma con
    xatlas_user_id ancora valorizzato. Tipicamente succede dopo chiusura evento
    massiva dall'admin: i record passano a checked_out, l'agente al ciclo
    successivo libera le card e cancella gli utenti VIS* da XAtlas."""
    try:
        rows = sb_get("visitors", params={
            "xatlas_status": "eq.checked_out",
            "xatlas_user_id": "not.is.null",
            # Skip visitor con xatlas_renamed=false: il recreate è in corso o è
            # fallito al ciclo precedente. Non interferire, sennò si perde il dato.
            "xatlas_renamed": "is.true",
            "select": "id,xatlas_user_id,badge_number",
            "limit": "20",  # max 20 per ciclo per non saturare XAtlas API
        })
    except Exception as e:
        log.warning(f"cleanup_archived_visitors: lettura Supabase fallita: {e}")
        return

    if not rows:
        return

    log.info(f"cleanup_archived_visitors: trovati {len(rows)} visitor da liberare")
    for v in rows:
        vid = v["id"]
        xid = v.get("xatlas_user_id")
        badge = v.get("badge_number")
        try:
            cid = find_card_id_by_clear_code(badge) if badge else None
            if xid and cid is not None:
                try:
                    unassign_xatlas_card(xid, cid)
                except Exception as e:
                    log.warning(f"unassign_xatlas_card({xid},{cid}) per visitor {vid}: {e}")
            if xid:
                try:
                    delete_xatlas_user(xid)
                except Exception as e:
                    log.warning(f"delete_xatlas_user({xid}) per visitor {vid}: {e}")
            sb_patch(f"visitors?id=eq.{vid}", {"xatlas_user_id": None})
            log.info(f"cleanup: badge {badge} liberato per visitor {vid} (xatlas_user {xid})")
        except Exception as e:
            log.error(f"cleanup_archived_visitors visitor {vid}: {e}")


def run_loop():
    log.info(f"Zucchetti Bridge Agent avviato (v{AGENT_VERSION})")
    log.info(f"Strategia email: {EMAIL_STRATEGY or 'NESSUNA (configurare [smtp] o [m365_graph] in agent_config.ini)'}")
    update_heartbeat(notes="started")
    startup_catchup()
    while True:
        try:
            process_pending_badges()
            process_pool_preparation()
            # IMPORTANTE: recreate prima delle transazioni e cleanup, altrimenti
            # un exit + cleanup possono cancellare l'utente XAtlas pool prima che
            # il recreate abbia potuto sostituirlo col nome reale.
            process_pool_walkin_recreate()
            process_active_transactions()
            cleanup_archived_visitors()
            midnight_cleanup_stale_visitors()
            process_email_queue()
            update_heartbeat()
        except Exception as e:
            log.error(f"Errore imprevisto nel ciclo principale: {e}")
            update_heartbeat(notes=f"error: {str(e)[:200]}")
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
            log.info(f"Service SvcDoRun avviato (v{AGENT_VERSION})")
            log.info(f"Strategia email: {EMAIL_STRATEGY or 'NESSUNA (configurare [smtp] o [m365_graph] in agent_config.ini)'}")
            update_heartbeat(notes="service started")
            try:
                startup_catchup()
            except Exception as e:
                log.error(f"Catchup all'avvio fallito: {e}")
            while self._running:
                try:
                    process_pending_badges()
                    process_pool_preparation()
                    # IMPORTANTE: recreate prima di transactions/cleanup
                    process_pool_walkin_recreate()
                    process_active_transactions()
                    cleanup_archived_visitors()
                    midnight_cleanup_stale_visitors()
                    process_email_queue()
                    update_heartbeat()
                except Exception as e:
                    log.error(f"Errore nel service loop: {e}")
                    update_heartbeat(notes=f"error: {str(e)[:200]}")
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
