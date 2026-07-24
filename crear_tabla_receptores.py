"""Crea (una sola vez) el esquema y la tabla de receptores en Postgres.

No es obligatorio: el servicio tambien las crea solo al arrancar. Sirve para
prepararlo a mano y verificar la conexion.

Uso:
    python crear_tabla_receptores.py                 # lee DATABASE_URL del .env
    python crear_tabla_receptores.py "postgresql://usuario:pass@host:5432/db"
"""
import os
import sys

from dotenv import load_dotenv

from subscribers import SubscriberStore

load_dotenv()

dsn = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("Falta DATABASE_URL (pasala como argumento o en el .env).")

schema = os.getenv("SUBSCRIBERS_SCHEMA", "eero_insight_whatsapp")
store = SubscriberStore(dsn, schema)
print(f"OK: esquema '{schema}' y tabla receptores_de_alertas listos.")
print(f"Receptores activos actuales: {store.count_active()}")
