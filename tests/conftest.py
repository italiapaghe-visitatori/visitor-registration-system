"""conftest.py per la test suite del visitor-registration-system.

Aggiunge la root del repository al sys.path cosi le suite possono importare
moduli al livello root (es. zucchetti_agent) senza pacchettizzare.
"""
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
