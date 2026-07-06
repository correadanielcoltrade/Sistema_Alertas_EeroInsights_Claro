"""Envio por WhatsApp Cloud API (Meta).

- send_template(): mensajes PROACTIVOS (alertas). Requiere plantilla aprobada.
- send_text(): texto libre. Solo funciona dentro de la ventana de 24h que se
  abre cuando el usuario te escribe (respuestas a comandos).
"""
import logging

import requests

log = logging.getLogger("whatsapp")


class WhatsAppCloud:
    def __init__(self, token, phone_number_id, api_version="v21.0", dry_run=True):
        self.token = token
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _post(self, payload, descr):
        if self.dry_run:
            log.info("[DRY_RUN] WhatsApp %s -> %s", descr, payload.get("to"))
            print("\n" + "=" * 60)
            print(f"[DRY_RUN] {descr} a {payload.get('to')}:")
            body = payload.get("text", {}).get("body")
            if body is None and payload.get("template"):
                comps = payload["template"].get("components", [])
                body = comps[0]["parameters"][0]["text"] if comps else "(plantilla)"
            print(body)
            print("=" * 60 + "\n")
            return True
        try:
            r = self.session.post(self.url, json=payload, timeout=30)
            if r.status_code >= 400:
                log.error("WhatsApp %s fallo (%s): %s", descr, r.status_code, r.text[:500])
                return False
            log.info("WhatsApp %s enviado a %s", descr, payload.get("to"))
            return True
        except requests.RequestException as e:
            log.error("WhatsApp %s error: %s", descr, e)
            return False

    def send_template(self, to, template_name, lang, body_text):
        """Envia una plantilla con una sola variable de cuerpo ({{1}})."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": body_text}],
                    }
                ],
            },
        }
        return self._post(payload, "plantilla")

    def send_text(self, to, text):
        """Texto libre (solo dentro de la ventana de 24h)."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": True, "body": text},
        }
        return self._post(payload, "texto")
