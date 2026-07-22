"""Simula un mensaje entrante de WhatsApp contra el webhook desplegado.

Sirve para probar los comandos/menu SIN depender de que Meta entregue los
mensajes (util mientras la app siga sin publicar). El bot procesara el
mensaje y te respondera de verdad por WhatsApp.

Uso:
    python probar_webhook.py              -> envia "Hola" (muestra el menu)
    python probar_webhook.py /estado      -> prueba un comando
    python probar_webhook.py /sin_solucionar
"""
import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://sistema-alertas-eeroinsights-claro.onrender.com/webhook"
NUMERO = "573115413088"  # debe estar en WA_RECIPIENTS para que el bot responda

texto = " ".join(sys.argv[1:]) or "Hola"

payload = {
    "entry": [{
        "changes": [{
            "value": {
                "messaging_product": "whatsapp",
                "messages": [{
                    "from": NUMERO,
                    "id": "wamid.PRUEBA",
                    "timestamp": "1700000000",
                    "type": "text",
                    "text": {"body": texto},
                }],
            }
        }]
    }]
}

print(f"Simulando mensaje de {NUMERO}: {texto!r}")
r = requests.post(URL, json=payload, timeout=90, verify=False)
print(f"HTTP {r.status_code} -> {r.text.strip()}")
print("Revisa tu WhatsApp: el bot deberia responderte.")
