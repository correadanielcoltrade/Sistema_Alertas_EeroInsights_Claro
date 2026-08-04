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

# --- Redes excluidas (testing/prueba) ---
# IDs de red a IGNORAR por completo (separados por coma). Sirve para las redes de
# prueba de eero Insights que se caen a proposito y no deben alertar. Se ignoran en
# caidas y en no saludables: no notifican, no cuentan en /estado y se limpian del
# store en silencio (sin aviso de "recuperada"). Para volver a incluir una red,
# quita su ID de aqui y redespliega. Los IDs se comparan como texto.
EXCLUDED_NETWORK_IDS = set(_list("EXCLUDED_NETWORK_IDS"))

# --- Link Insights ---
INSIGHT_URL_TEMPLATE = _get(
    "INSIGHT_URL_TEMPLATE", "https://insight.eero.com/networks/{network_id}"
)
# URL generica (sin id) para el consolidado, derivada de la plantilla.
INSIGHT_BASE = INSIGHT_URL_TEMPLATE.split("/{")[0]

# --- WhatsApp Cloud API (Meta) ---
WA_TOKEN = _get("WA_TOKEN")                     # token permanente (System User)
WA_PHONE_NUMBER_ID = _get("WA_PHONE_NUMBER_ID")  # id del numero emisor
WA_API_VERSION = _get("WA_API_VERSION", "v21.0")
# Dos plantillas aprobadas:
#  - Individual (8 variables): para cada alerta NUEVA.
#  - Consolidado (10 variables): una red por variable, para re-notificaciones/resueltas.
WA_TEMPLATE_INDIVIDUAL = _get("WA_TEMPLATE_INDIVIDUAL", "alerta_individual")
WA_TEMPLATE_INDIVIDUAL_LANG = _get("WA_TEMPLATE_INDIVIDUAL_LANG", "es")
WA_TEMPLATE_CONSOL = _get("WA_TEMPLATE_CONSOL", "recordatorio_consolidado")
WA_TEMPLATE_CONSOL_LANG = _get("WA_TEMPLATE_CONSOL_LANG", "es")
# Numeros destino de las alertas (coma-separados, solo digitos con indicativo).
# Ahora es solo un FALLBACK: la lista real vive en la tabla de receptores
# (autogestion por WhatsApp). Se usa si no hay DATABASE_URL o la tabla esta vacia.
WA_RECIPIENTS = _list("WA_RECIPIENTS")

# --- Receptores de alertas (Postgres, autogestion alta/baja por WhatsApp) ---
# Cadena de conexion de Render (External Database URL). Si falta, se usa
# WA_RECIPIENTS como antes.
DATABASE_URL = _get("DATABASE_URL")
SUBSCRIBERS_SCHEMA = _get("SUBSCRIBERS_SCHEMA", "eero_insight_whatsapp")
# Modo SSL para Postgres. 'require' sirve para la URL interna y externa de
# Render. Si la interna diera problema de SSL, se puede poner 'prefer' o
# 'disable' sin tocar codigo.
DB_SSLMODE = _get("DB_SSLMODE", "require")
# Token que TU inventas para verificar el webhook con Meta.
WA_VERIFY_TOKEN = _get("WA_VERIFY_TOKEN", "cambia_esta_palabra")

# Consolidado: WA_BATCH_MAX = numero de variables de la plantilla (una red por
# variable). Debe coincidir con la plantilla aprobada en Meta.
WA_BATCH_MAX = int(_get("WA_BATCH_MAX", "10"))
WA_BODY_BUDGET = int(_get("WA_BODY_BUDGET", "900"))

# --- Envio automatico (proactivo) a Meta ---
# Meta COBRA por los mensajes proactivos (plantillas: alertas, re-notificaciones,
# reporte diario, cierres). Cuando alguien le ESCRIBE al bot se abre una ventana
# de 24h de respuesta gratis (texto libre). Sin presupuesto aprobado, esto va en
# FALSE: el sistema sigue sondeando y actualizando su estado, pero NO envia nada
# solo; el equipo consulta las alertas por el menu (opciones 1 y 2). Para reactivar
# el envio automatico cuando haya presupuesto: ALERTAS_PUSH_ENABLED=true.
ALERTAS_PUSH_ENABLED = _get("ALERTAS_PUSH_ENABLED", "false").lower() in ("1", "true", "yes", "si")

# --- Reporte diario de redes no saludables ---
# Las redes no saludables NO se notifican en tiempo real: son un reporte que solo
# cambia una vez al dia. Se envia UN consolidado por WhatsApp en la manana y se
# consultan con /estado el resto del dia. (Las CAIDAS si siguen en tiempo real.)
UNHEALTHY_ENABLED = _get("UNHEALTHY_ENABLED", "true").lower() in ("1", "true", "yes", "si")
# Hora local (America/Bogota) del envio del reporte diario.
UNHEALTHY_REPORT_HOUR = int(_get("UNHEALTHY_REPORT_HOUR", "9"))
# Si es true, el reporte matutino incluye SOLO las criticas (las no criticas
# quedan solo en /estado). Por defecto false = incluye todas.
UNHEALTHY_REPORT_CRITICAL_ONLY = _get(
    "UNHEALTHY_REPORT_CRITICAL_ONLY", "false").lower() in ("1", "true", "yes", "si")

# --- General ---
DRY_RUN = _get("DRY_RUN", "true").lower() in ("1", "true", "yes", "si")
DB_PATH = _get("DB_PATH", os.path.join(BASE_DIR, "alertas.db"))
PORT = int(_get("PORT", "10000"))  # Render inyecta PORT
