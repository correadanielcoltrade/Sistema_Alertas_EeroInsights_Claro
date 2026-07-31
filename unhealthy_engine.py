"""Motor de redes no saludables para WhatsApp: REPORTE DIARIO.

Las redes no saludables son un reporte que solo cambia una vez al dia, asi que NO
se notifican en tiempo real. `daily_report()` corre una vez al dia (job programado):
- Agrega al collector las redes con problema (todas, o solo criticas segun config)
  para enviar UN mensaje consolidado.
- Refresca el snapshot que consulta /estado (agrega/actualiza las actuales y marca
  como resueltas las que ya no aparecen).

Las CAIDAS (AlertEngine) siguen notificando/re-notificando en tiempo real aparte.
"""
import logging
from datetime import datetime, timezone, timedelta

from eero_client import EeroAuthError
import network_labels

log = logging.getLogger("unhealthy")

SEVERITY = {"CRITICAL": ("🔴", "CRITICA"), "NON_CRITICAL": ("🟠", "NO CRITICA")}

ALERTS_ES = {
    "Wifi network conflict": "Conflicto WiFi",
    "WAN limited by ethernet speed": "WAN limitada por ethernet",
    "High channel utilization": "Alta utilizacion de canal",
    "Leaf eero outage over 5 min": "eero secundario caido +5min",
    "Gateway eero outage over 5 min": "eero principal caido +5min",
    "5 or more Network outages": "5+ caidas de red",
}


def _fmt_dt(iso_str):
    if not iso_str:
        return "N/D"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S (COT)")
    except (ValueError, AttributeError):
        return iso_str


def _con_etiqueta(nid, name):
    label, nick = network_labels.get(nid)
    val = nick or label
    return f"{name} [{val}]" if val else name


class UnhealthyEngine:
    KIND = "unhealthy"

    def __init__(self, eero, collector, store, insight_template,
                 excluded=None, critical_only=False):
        self.eero = eero
        self.collector = collector
        self.store = store
        self.insight_template = insight_template
        # IDs de red (texto) a ignorar por completo: redes de prueba.
        self.excluded = set(excluded or ())
        # Si True, el reporte solo incluye criticas (las no criticas solo en /estado).
        self.critical_only = critical_only

    def _net_name(self, network_id):
        return self.eero.network_info(network_id).get("name") or f"Red {network_id}"

    def _alerts_text(self, alerts):
        if not alerts:
            return "N/D"
        return ", ".join(ALERTS_ES.get(a, a) for a in alerts)

    def _conciso(self, net):
        nid = str(net["network_id"])
        _, label = SEVERITY.get(net.get("highest_severity", ""), ("⚪", "?"))
        name = _con_etiqueta(nid, self._net_name(nid))
        return f"{name} ({nid}): Estado {label}"

    def daily_report(self, send=True):
        """Genera el reporte diario y refresca el snapshot del store.

        send=True: agrega las redes al collector (para enviar el consolidado).
        send=False: solo refresca el snapshot del store (para /estado), sin enviar
        (se usa al arrancar si el snapshot esta vacio).
        """
        log.info("Reporte diario de redes no saludables (send=%s)...", send)
        dry = getattr(self.collector, "dry_run", False)
        try:
            nets = self.eero.unhealthy_networks()
        except EeroAuthError:
            log.warning("Token fallo al consultar unhealthy (reporte diario).")
            return

        activos = {str(n["network_id"]): n for n in nets if not n.get("is_deleted")}
        if self.excluded:
            antes = len(activos)
            activos = {nid: n for nid, n in activos.items() if nid not in self.excluded}
            if antes != len(activos):
                log.info("Reporte diario: %d red(es) de prueba excluidas.", antes - len(activos))
        log.info("Redes no saludables (reporte diario): %d", len(activos))

        # Criticas primero en el consolidado (van arriba del mensaje).
        def _orden(item):
            return 0 if item[1].get("highest_severity") == "CRITICAL" else 1

        for nid, net in sorted(activos.items(), key=_orden):
            critica = net.get("highest_severity") == "CRITICAL"
            if send and (critica or not self.critical_only):
                self.collector.add(self._conciso(net))
            if not dry:
                # Solo rastreo (bump=False): no infla el contador de avisos.
                self.store.upsert_alert(
                    nid, net.get("highest_severity"), kind=self.KIND,
                    detalle=self._alerts_text(net.get("alerts")),
                    name=self._net_name(nid), bump=False,
                )

        # Redes que ya no estan: se marcan resueltas y se quitan del snapshot.
        for nid in self.store.all_ids(kind=self.KIND) - set(activos.keys()):
            if not dry:
                if nid not in self.excluded:
                    row = self.store.get(nid, kind=self.KIND)
                    name = (row["name"] if row and row["name"] else self._net_name(nid))
                    self.store.record_resolution(
                        self.KIND, nid, name,
                        row["detalle"] if row else None,
                        row["first_alert"] if row else None,
                        row["alert_count"] if row else 0,
                    )
                self.store.remove(nid, kind=self.KIND)
