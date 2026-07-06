"""Estado persistente (SQLite): re-notificaciones e historial de resoluciones.

Tabla 'tracked' (kind, item_id): alertas ACTIVAS. kind='outage' para caidas,
kind='unhealthy' para redes no saludables (una red puede estar en ambas).
Tabla 'resueltas': historial de novedades ya solucionadas (para /soluciones).
"""
import sqlite3
import threading
from datetime import datetime, timezone, timedelta


class StateStore:
    def __init__(self, db_path="alertas.db"):
        # check_same_thread=False: APScheduler ejecuta el sondeo en otro hilo.
        # El candado serializa los accesos para que sea seguro entre hilos.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracked (
                    kind        TEXT NOT NULL,
                    item_id     TEXT NOT NULL,
                    ref         TEXT,
                    detalle     TEXT,
                    name        TEXT,
                    first_alert TEXT,
                    last_alert  TEXT,
                    alert_count INTEGER DEFAULT 0,
                    PRIMARY KEY (kind, item_id)
                )
                """
            )
            # Migracion para BDs antiguas: agrega columnas nuevas si faltan.
            for col in ("detalle TEXT", "name TEXT"):
                try:
                    self.conn.execute(f"ALTER TABLE tracked ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass
            # Historial de novedades resueltas.
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resueltas (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind        TEXT,
                    item_id     TEXT,
                    name        TEXT,
                    detalle     TEXT,
                    first_alert TEXT,
                    resolved_at TEXT,
                    alert_count INTEGER
                )
                """
            )
            # Banderas del sistema (ej. token caido).
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS sistema (clave TEXT PRIMARY KEY, valor TEXT)"
            )
            self.conn.commit()

    # ---------- banderas ----------

    def get_flag(self, clave):
        with self._lock:
            cur = self.conn.execute("SELECT valor FROM sistema WHERE clave=?", (clave,))
            row = cur.fetchone()
            return row["valor"] if row else None

    def set_flag(self, clave, valor):
        with self._lock:
            self.conn.execute(
                "INSERT INTO sistema (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (clave, str(valor)),
            )
            self.conn.commit()

    def clear_flag(self, clave):
        with self._lock:
            self.conn.execute("DELETE FROM sistema WHERE clave=?", (clave,))
            self.conn.commit()

    # ---------- seguimiento de alertas activas ----------

    def get(self, item_id, kind="outage"):
        with self._lock:
            cur = self.conn.execute(
                "SELECT * FROM tracked WHERE kind=? AND item_id=?", (kind, str(item_id))
            )
            return cur.fetchone()

    def all_ids(self, kind="outage"):
        with self._lock:
            cur = self.conn.execute("SELECT item_id FROM tracked WHERE kind=?", (kind,))
            return {row["item_id"] for row in cur.fetchall()}

    def all_active(self, kind=None):
        """Filas completas de alertas activas (todas, o de un kind)."""
        with self._lock:
            if kind:
                cur = self.conn.execute(
                    "SELECT * FROM tracked WHERE kind=? ORDER BY first_alert", (kind,)
                )
            else:
                cur = self.conn.execute("SELECT * FROM tracked ORDER BY kind, first_alert")
            return cur.fetchall()

    def upsert_alert(self, item_id, ref=None, kind="outage", detalle=None, name=None):
        """Registra o actualiza un item cuando se acaba de notificar."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self.conn.execute(
                "SELECT 1 FROM tracked WHERE kind=? AND item_id=?", (kind, str(item_id))
            )
            if cur.fetchone():
                self.conn.execute(
                    "UPDATE tracked SET last_alert=?, alert_count=alert_count+1, "
                    "ref=?, detalle=?, name=? WHERE kind=? AND item_id=?",
                    (now, ref, detalle, name, kind, str(item_id)),
                )
            else:
                self.conn.execute(
                    "INSERT INTO tracked "
                    "(kind, item_id, ref, detalle, name, first_alert, last_alert, alert_count) "
                    "VALUES (?,?,?,?,?,?,?,1)",
                    (kind, str(item_id), ref, detalle, name, now, now),
                )
            self.conn.commit()

    def remove(self, item_id, kind="outage"):
        with self._lock:
            self.conn.execute(
                "DELETE FROM tracked WHERE kind=? AND item_id=?", (kind, str(item_id))
            )
            self.conn.commit()

    # ---------- historial de resoluciones ----------

    def record_resolution(self, kind, item_id, name, detalle, first_alert, alert_count):
        """Guarda una novedad resuelta (con la hora de solucion)."""
        now = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        with self._lock:
            self.conn.execute(
                "INSERT INTO resueltas "
                "(kind, item_id, name, detalle, first_alert, resolved_at, alert_count) "
                "VALUES (?,?,?,?,?,?,?)",
                (kind, str(item_id), name, detalle, first_alert, now, alert_count),
            )
            # Limpieza: conserva solo lo de los ultimos 30 dias.
            self.conn.execute("DELETE FROM resueltas WHERE resolved_at < ?", (cutoff,))
            self.conn.commit()

    def resolutions_since(self, iso_time):
        """Novedades resueltas desde iso_time (ISO UTC), en orden cronologico."""
        with self._lock:
            cur = self.conn.execute(
                "SELECT * FROM resueltas WHERE resolved_at >= ? ORDER BY resolved_at",
                (iso_time,),
            )
            return cur.fetchall()
