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

try:
    from subscribers import SubscriberStore
except ImportError:  # psycopg2 no instalado
    SubscriberStore = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("main")


def _build_subscribers():
    """Crea el store de receptores en Postgres (o None si no hay DB)."""
    if not config.DATABASE_URL or SubscriberStore is None:
        log.warning("Sin DATABASE_URL: se usa WA_RECIPIENTS como lista fija.")
        return None
    try:
        subs = SubscriberStore(config.DATABASE_URL, config.SUBSCRIBERS_SCHEMA)
    except Exception:  # noqa: BLE001
        log.exception("No se pudo conectar a Postgres; se usa WA_RECIPIENTS.")
        return None
    # Migracion: mete los numeros de WA_RECIPIENTS que aun no esten en la tabla.
    for numero in config.WA_RECIPIENTS:
        estado = subs.subscribe(numero)
        if estado == "nuevo":
            log.info("Migrado a receptores: %s", numero)
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
