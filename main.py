"""Servicio WhatsApp: polling de eero (alertas consolidadas) + webhook de comandos."""
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import logging
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("main")


def build():
    eero = EeroClient(config.EERO_ADMIN_TOKEN, config.EERO_ORG_ID)
    store = StateStore(config.DB_PATH)
    wa = WhatsAppCloud(
        config.WA_TOKEN, config.WA_PHONE_NUMBER_ID,
        api_version=config.WA_API_VERSION, dry_run=config.DRY_RUN,
    )
    collector = Collector(dry_run=config.DRY_RUN)
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
    return store, wa, collector, engine, unhealthy


def poll_cycle(collector, engine, unhealthy, wa):
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
    collector.flush(
        wa, config.WA_RECIPIENTS, config.WA_TEMPLATE_NAME,
        config.WA_TEMPLATE_LANG, config.WA_BODY_BUDGET, config.WA_BATCH_MAX,
    )


def main():
    store, wa, collector, engine, unhealthy = build()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        poll_cycle(collector, engine, unhealthy, wa)
        return

    log.info(
        "Iniciando WhatsApp. Poll cada %d min | re-notif %d min | budget %d | DRY_RUN=%s | destinatarios=%d",
        config.POLL_MINUTES, config.RENOTIFY_MINUTES, config.WA_BODY_BUDGET,
        config.DRY_RUN, len(config.WA_RECIPIENTS),
    )

    sched = BackgroundScheduler(timezone="America/Bogota")
    sched.add_job(
        poll_cycle, "interval", minutes=config.POLL_MINUTES,
        args=[collector, engine, unhealthy, wa],
        misfire_grace_time=300, coalesce=True,
    )
    sched.start()
    poll_cycle(collector, engine, unhealthy, wa)  # corrida inmediata

    # Servidor webhook (bloquea). Render enruta el trafico al PORT.
    app = create_app(store, wa)
    from waitress import serve
    log.info("Webhook escuchando en 0.0.0.0:%d", config.PORT)
    serve(app, host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
