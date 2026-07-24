"""Servicio WhatsApp: polling de eero (alertas consolidadas) + webhook de comandos."""
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import logging
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from apscheduler.schedulers.background import BackgroundScheduler

import config
from eero_client import EeroClient
from state import StateStore
from whatsapp_cloud import WhatsAppCloud
from batch import Collector
from alert_engine import AlertEngine
from unhealthy_engine import UnhealthyEngine
from webhook import create_app

try:
    from subscribers import SubscriberStore
except ImportError:  # psycopg2 no instalado
    SubscriberStore = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("main")


def _host_seguro(url):
    """Extrae el host de la URL de la DB sin exponer la contrasena (para el log)."""
    m = re.search(r"@([^/:?]+)", url or "")
    return m.group(1) if m else "?"


def _build_subscribers():
    """Crea el store de receptores en Postgres (o None si no hay DB configurada).

    Ojo: si DATABASE_URL existe, se devuelve el store SIEMPRE (aunque la DB este
    momentaneamente caida). Las operaciones se reintentan por-llamada, asi que la
    autogestion no queda desactivada por un fallo transitorio del arranque.
    """
    # --- Diagnostico: que ve el proceso realmente (sin exponer valores) ---
    val = os.getenv("DATABASE_URL")
    log.info("DIAG DATABASE_URL: presente=%s longitud=%s",
             val is not None, len(val) if val else 0)
    relacionadas = sorted(
        k for k in os.environ
        if any(t in k.upper() for t in ("DATA", "POSTGRES", "_DB", "DB_", "URL"))
    )
    log.info("DIAG variables de entorno relacionadas visibles: %s", relacionadas)

    if SubscriberStore is None:
        log.warning("psycopg2 no instalado: autogestion DESACTIVADA (fallback WA_RECIPIENTS).")
        return None
    if not config.DATABASE_URL:
        log.warning("Sin DATABASE_URL: autogestion DESACTIVADA (fallback WA_RECIPIENTS).")
        return None

    log.info("DATABASE_URL detectada (host=%s, sslmode=%s). Preparando receptores...",
             _host_seguro(config.DATABASE_URL), config.DB_SSLMODE)
    subs = SubscriberStore(
        config.DATABASE_URL, config.SUBSCRIBERS_SCHEMA, sslmode=config.DB_SSLMODE
    )
    # Migracion: mete los numeros de WA_RECIPIENTS que aun no esten en la tabla.
    for numero in config.WA_RECIPIENTS:
        if subs.subscribe(numero) == "nuevo":
            log.info("Migrado a receptores: %s", numero)

    activos = subs.active_numbers()
    if activos is None:
        log.warning("Autogestion ACTIVA pero la DB no respondio al arrancar "
                    "(se reintenta al usar). Revisa host/region/credenciales.")
    else:
        log.info("Autogestion ACTIVA. Receptores activos: %d.", len(activos))
    return subs


def build():
    eero = EeroClient(config.EERO_ADMIN_TOKEN, config.EERO_ORG_ID)
    store = StateStore(config.DB_PATH)
    subs = _build_subscribers()
    wa = WhatsAppCloud(
        config.WA_TOKEN, config.WA_PHONE_NUMBER_ID,
        api_version=config.WA_API_VERSION, dry_run=config.DRY_RUN,
    )

    def destinatarios():
        """Suscriptores activos de la tabla; si no hay DB o esta vacia, fallback."""
        if subs is not None:
            activos = subs.active_numbers()
            if activos:
                return activos
        return config.WA_RECIPIENTS

    collector = Collector(
        wa, destinatarios,
        config.WA_TEMPLATE_INDIVIDUAL, config.WA_TEMPLATE_INDIVIDUAL_LANG,
        config.WA_TEMPLATE_CONSOL, config.WA_TEMPLATE_CONSOL_LANG,
        budget=config.WA_BODY_BUDGET, max_count=config.WA_BATCH_MAX,
        dry_run=config.DRY_RUN,
    )
    engine = AlertEngine(
        eero, collector, store,
        insight_template=config.INSIGHT_URL_TEMPLATE,
        renotify_minutes=config.RENOTIFY_MINUTES,
    )
    unhealthy = UnhealthyEngine(
        eero, collector, store,
        insight_template=config.INSIGHT_URL_TEMPLATE,
        renotify_minutes=config.RENOTIFY_MINUTES,
    )
    return store, wa, collector, engine, unhealthy, subs


def poll_cycle(collector, engine, unhealthy):
    collector.reset()
    try:
        engine.poll_once()
    except Exception:  # noqa: BLE001
        log.exception("Error en el ciclo de caidas (se continua).")
    if config.UNHEALTHY_ENABLED:
        try:
            unhealthy.poll_once()
        except Exception:  # noqa: BLE001
            log.exception("Error en el ciclo de unhealthy (se continua).")
    collector.flush()  # envia el consolidado (las nuevas ya salieron aparte)


def main():
    store, wa, collector, engine, unhealthy, subs = build()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        poll_cycle(collector, engine, unhealthy)
        return

    activos = subs.count_active() if subs is not None else len(config.WA_RECIPIENTS)
    log.info(
        "Iniciando WhatsApp. Poll cada %d min | re-notif %d min | budget %d | DRY_RUN=%s | receptores activos=%d",
        config.POLL_MINUTES, config.RENOTIFY_MINUTES, config.WA_BODY_BUDGET,
        config.DRY_RUN, activos,
    )

    sched = BackgroundScheduler(timezone="America/Bogota")
    sched.add_job(
        poll_cycle, "interval", minutes=config.POLL_MINUTES,
        args=[collector, engine, unhealthy],
        misfire_grace_time=300, coalesce=True,
    )
    sched.start()
    poll_cycle(collector, engine, unhealthy)  # corrida inmediata

    # Servidor webhook (bloquea). Render enruta el trafico al PORT.
    app = create_app(store, wa, subs)
    from waitress import serve
    log.info("Webhook escuchando en 0.0.0.0:%d", config.PORT)
    serve(app, host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
