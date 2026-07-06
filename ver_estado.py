"""Muestra el contenido de la base de estado (alertas.db).

Uso:
    python ver_estado.py            # lee alertas.db en esta carpeta
    python ver_estado.py ruta.db    # lee otra ruta
"""
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "alertas.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
print(f"Base de datos: {db}\n")

# Alertas activas (caidas y unhealthy)
try:
    rows = conn.execute(
        "SELECT kind, item_id, ref, first_alert, last_alert, alert_count "
        "FROM tracked ORDER BY kind, last_alert"
    ).fetchall()
except sqlite3.OperationalError:
    rows = []

print(f"=== Alertas activas ({len(rows)}) ===")
if not rows:
    print("  (ninguna)")
for r in rows:
    tipo = "CAIDA" if r["kind"] == "outage" else "UNHEALTHY"
    print(
        f"  [{tipo}] red {r['item_id']} | ref={r['ref']} "
        f"| avisos={r['alert_count']} | ultimo={r['last_alert']}"
    )

# Banderas del sistema (ej. token caido)
try:
    flags = conn.execute("SELECT clave, valor FROM sistema").fetchall()
except sqlite3.OperationalError:
    flags = []

print(f"\n=== Banderas del sistema ({len(flags)}) ===")
if not flags:
    print("  (ninguna)")
for f in flags:
    print(f"  {f['clave']} = {f['valor']}")

conn.close()
