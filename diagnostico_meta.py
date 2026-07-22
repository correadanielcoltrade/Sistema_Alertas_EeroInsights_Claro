"""Diagnostico de la configuracion de WhatsApp Cloud API (Meta).

Revisa si la cuenta de WhatsApp (WABA) esta suscrita a tu app, que es lo que
hace que Meta entregue los mensajes entrantes al webhook.

Uso:
    python diagnostico_meta.py <WABA_ID> <TOKEN>

- WABA_ID: "WhatsApp Business Account ID" (Paso 1. Pruebalo / API Setup)
- TOKEN  : el mismo WA_TOKEN que tienes en Render
"""
import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API = "https://graph.facebook.com/v21.0"

if len(sys.argv) < 3:
    raise SystemExit("Uso: python diagnostico_meta.py <WABA_ID> <TOKEN>")

waba_id, token = sys.argv[1], sys.argv[2]
h = {"Authorization": f"Bearer {token}"}


def get(path, descr):
    print(f"\n=== {descr} ===")
    try:
        r = requests.get(f"{API}/{path}", headers=h, timeout=30, verify=False)
        print(f"HTTP {r.status_code}")
        print(r.text[:1200])
        return r
    except Exception as e:  # noqa: BLE001
        print("ERROR:", e)
        return None


# 1) Apps suscritas a la WABA -> aqui debe aparecer TU app
get(f"{waba_id}/subscribed_apps", "Apps suscritas a la WABA (debe salir la tuya)")

# 2) Numeros de la WABA (estado y calidad)
get(f"{waba_id}/phone_numbers", "Numeros de la WABA")

print("\n--- Como leerlo ---")
print("* Si 'subscribed_apps' sale VACIO -> Meta no entrega mensajes. Hay que suscribir la app.")
print("* Si aparece OTRA app (ej. Odoo) y no la tuya -> ese es el problema.")
print("* Si aparece tu app -> la suscripcion esta bien; el problema es otro.")
