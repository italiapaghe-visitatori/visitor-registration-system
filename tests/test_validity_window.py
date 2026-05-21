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


# --- 1) Fallback walk-in: event_id is None -------------------------------
def test_walk_in_fallback_when_event_id_none():
    """event_id None -> deve usare _today_ms() invariato (fallback walk-in)."""
    expected = za._today_ms()
    result = za.event_window_ms(None)
    assert result == expected


# --- 2) Evento futuro: pool preparato in anticipo ------------------------
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


# --- 3) Evento OGGI: start=oggi, end=oggi+7 ------------------------------
def test_event_today_end_today_plus_7():
    fake_today = date(2026, 6, 3)
    event_row = {"event_end_date": "2026-06-03", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        start_ms, end_ms = za.event_window_ms("evt-today")

    end_dt = _ms_to_rome_dt(end_ms)
    assert end_dt.date() == date(2026, 6, 10)
    assert (end_dt.hour, end_dt.minute, end_dt.second) == (23, 59, 59)


# --- 4) Evento multi-giorno ----------------------------------------------
def test_event_multi_day_uses_event_end_date():
    fake_today = date(2026, 6, 1)
    event_row = {"event_end_date": "2026-06-05", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        _, end_ms = za.event_window_ms("evt-multiday")

    assert _ms_to_rome_dt(end_ms).date() == date(2026, 6, 12)  # 2026-06-05 + 7


# --- 5) Evento chiuso: fail-fast -----------------------------------------
def test_event_closed_raises_runtime_error():
    event_row = {"event_end_date": "2026-06-03",
                 "closed_at": "2026-06-03T18:00:00+02:00"}
    with patch.object(za, "sb_get", return_value=[event_row]):
        with pytest.raises(RuntimeError, match="chiuso"):
            za.event_window_ms("evt-closed")


# --- 6) Evento scaduto (event_end nel passato): fail-fast ----------------
def test_event_in_past_raises_runtime_error():
    fake_today = date(2026, 6, 10)
    event_row = {"event_end_date": "2026-06-03", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        with pytest.raises(RuntimeError, match="scaduto"):
            za.event_window_ms("evt-past")


# --- 7) Evento non trovato: fail-fast ------------------------------------
def test_event_not_found_raises_runtime_error():
    with patch.object(za, "sb_get", return_value=[]):
        with pytest.raises(RuntimeError, match="non trovato"):
            za.event_window_ms("evt-missing")


# --- 8) Lookup Supabase fallisce (rete down): fail-fast ------------------
def test_event_lookup_failure_raises_runtime_error():
    def _boom(*args, **kwargs):
        raise ConnectionError("simulated network outage")
    with patch.object(za, "sb_get", side_effect=_boom):
        with pytest.raises(RuntimeError, match="lookup events fallito"):
            za.event_window_ms("evt-anything")


# --- 9) event_end_date mancante o NULL: fail-fast ------------------------
def test_event_without_end_date_raises_runtime_error():
    event_row = {"event_end_date": None, "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]):
        with pytest.raises(RuntimeError, match="event_end_date"):
            za.event_window_ms("evt-no-enddate")


# --- 10) DST: evento a fine ottobre (cambio ora legale) ------------------
def test_dst_october_event_window_uses_europe_rome():
    """Bound a 23:59:59 LOCALE Europe/Rome anche attraverso cambio DST.

    DST 2026 in Italia: ultima domenica di ottobre = 2026-10-25 (CEST -> CET).
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
    # In novembre l'offset Europe/Rome e UTC+1 (CET, fine DST)
    assert end_dt.utcoffset() == timedelta(hours=1)


# --- 11) Anno bisestile / fine mese --------------------------------------
def test_leap_year_boundary():
    fake_today = date(2028, 2, 29)
    event_row = {"event_end_date": "2028-02-29", "closed_at": None}
    with patch.object(za, "sb_get", return_value=[event_row]), \
         patch.object(za, "_today_rome", return_value=fake_today):
        _, end_ms = za.event_window_ms("evt-leap")

    assert _ms_to_rome_dt(end_ms).date() == date(2028, 3, 7)


# --- 12) _today_ms() resta tz-explicit Europe/Rome -----------------------
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


# --- 13) Guardia statica VIS-only nel sorgente ---------------------------
def test_source_contains_vis_only_assertion():
    """Difesa in profondita: il sorgente DEVE contenere l'asserzione VIS-only.

    Questo test scatta se una modifica futura rimuove la guardia hardcoded
    che protegge i dipendenti -- e un canarino statico, non un controllo runtime."""
    import os
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    src_path = os.path.join(repo_root, "zucchetti_agent.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert 'assert identifier.startswith("VIS")' in src, \
        "Asserzione VIS-only mancante in create_xatlas_user (regressione di sicurezza)"
