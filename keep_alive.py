"""Mantiene despierto el servicio FREE de Render (evita que se duerma).

Render free suspende el servicio tras ~15 min sin trafico; al dormirse se
detiene el scheduler y no salen las re-notificaciones. Este script le hace
ping cada INTERVALO minutos para mantenerlo activo.

Uso:
    python keep_alive.py

Dejalo corriendo en una terminal mientras pruebas. Ctrl+C para detenerlo.
"""
import time
from datetime import datetime

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://sistema-alertas-eeroinsights-claro.onrender.com/"
INTERVALO = 120  # segundos entre pings (2 min)

print(f"Manteniendo despierto:\n  {URL}\n  ping cada {INTERVALO // 60} min. Ctrl+C para salir.\n")

while True:
    try:
        r = requests.get(URL, timeout=60, verify=False)
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  ->  HTTP {r.status_code}  ({r.text.strip()[:15]})")
    except Exception as e:  # noqa: BLE001
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  ->  ERROR: {e}")
    time.sleep(INTERVALO)
