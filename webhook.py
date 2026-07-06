"""Webhook de WhatsApp Cloud API (Flask).

GET  /webhook  -> verificacion con Meta (hub.challenge).
POST /webhook  -> recibe mensajes entrantes, ejecuta el comando y responde.
GET  /         -> healthcheck para Render.
"""
import logging

from flask import Flask, request

import config
import commands

log = logging.getLogger("webhook")


def create_app(store, wa):
    app = Flask(__name__)

    # Solo estos numeros pueden dar comandos (los del soporte). Vacio = cualquiera.
    permitidos = set(config.WA_RECIPIENTS)

    @app.get("/")
    def health():
        return "ok", 200

    @app.get("/webhook")
    def verify():
        args = request.args
        if (args.get("hub.mode") == "subscribe"
                and args.get("hub.verify_token") == config.WA_VERIFY_TOKEN):
            log.info("Webhook verificado por Meta.")
            return args.get("hub.challenge", ""), 200
        log.warning("Verificacion de webhook fallida.")
        return "forbidden", 403

    @app.post("/webhook")
    def receive():
        data = request.get_json(silent=True) or {}
        try:
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []):
                        if msg.get("type") != "text":
                            continue
                        frm = msg.get("from")
                        texto = (msg.get("text") or {}).get("body", "")
                        if permitidos and frm not in permitidos:
                            log.info("Mensaje de numero no autorizado: %s", frm)
                            continue
                        respuesta = commands.dispatch(texto, store)
                        wa.send_text(frm, respuesta)
        except Exception:  # noqa: BLE001
            log.exception("Error procesando webhook.")
        # Siempre 200 para que Meta no reintente en bucle.
        return "ok", 200

    return app
