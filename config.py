"""Carga y valida la configuracion desde variables de entorno (.env)."""
import os
import sys
from dotenv import load_dotenv

# Junto al .exe si esta empaquetado, si no junto a este archivo.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))


def _get(name, default=None, required=False):
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"Falta la variable requerida '{name}' (revisa el .env).")
    return val


def _list(name):
    raw = _get(name, "") or ""
    return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]


# --- Eero ---
EERO_ADMIN_TOKEN = _get("EERO_ADMIN_TOKEN", required=True)
EERO_ORG_ID = _get("EERO_ORG_ID", "self")

# --- Polling ---
POLL_MINUTES = int(_get("POLL_MINUTES", "10"))
RENOTIFY_MINUTES = int(_get("RENOTIFY_MINUTES", "10"))

# --- Link Insights ---
INSIGHT_URL_TEMPLATE = _get(
    "INSIGHT_URL_TEMPLATE", "https://insight.eero.com/networks/{network_id}"
)

# --- WhatsApp Cloud API (Meta) ---
WA_TOKEN = _get("WA_TOKEN")                     # token permanente (System User)
WA_PHONE_NUMBER_ID = _get("WA_PHONE_NUMBER_ID")  # id del numero emisor
WA_API_VERSION = _get("WA_API_VERSION", "v21.0")
# Plantilla aprobada para las alertas proactivas (1 variable de cuerpo).
WA_TEMPLATE_NAME = _get("WA_TEMPLATE_NAME", "alertas_eero")
WA_TEMPLATE_LANG = _get("WA_TEMPLATE_LANG", "es")
# Numeros destino de las alertas (coma-separados, solo digitos con indicativo).
WA_RECIPIENTS = _list("WA_RECIPIENTS")
# Token que TU inventas para verificar el webhook con Meta.
WA_VERIFY_TOKEN = _get("WA_VERIFY_TOKEN", "cambia_esta_palabra")

# Cuantas alertas por mensaje consolidado (plantilla).
BATCH_SIZE = int(_get("BATCH_SIZE", "10"))

# --- Monitoreo unhealthy en tiempo real ---
UNHEALTHY_ENABLED = _get("UNHEALTHY_ENABLED", "true").lower() in ("1", "true", "yes", "si")

# --- General ---
DRY_RUN = _get("DRY_RUN", "true").lower() in ("1", "true", "yes", "si")
DB_PATH = _get("DB_PATH", os.path.join(BASE_DIR, "alertas.db"))
PORT = int(_get("PORT", "10000"))  # Render inyecta PORT
