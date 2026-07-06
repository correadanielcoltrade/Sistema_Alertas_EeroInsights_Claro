"""Motor de redes no saludables para WhatsApp: acumula lineas concisas."""
import logging
from datetime import datetime, timezone

from eero_client import EeroAuthError
import network_labels

log = logging.getLogger("unhealthy")

SEVERITY = {"CRITICAL": ("🔴", "CRITICA"), "NON_CRITICAL": ("🟠", "NO CRITICA")}

ALERTS_ES = {
    "Wifi network conflict": "Conflicto WiFi",
    "WAN limited by ethernet speed": "WAN limitada por ethernet",
    "High channel utilization": "Alta utilizacion de canal",
    "Leaf eero outage over 5 min": "Eero secundario caido +5min",
    "Gateway eero outage over 5 min": "Eero principal caido +5min",
    "5 or more Network outages": "5+ caidas de red",
}


def _etiqueta(nid):
    label, nick = network_labels.get(nid)
    val = nick or label
    return f" [{val}]" if val else ""


class UnhealthyEngine:
    KIND = "unhealthy"

    def __init__(self, eero, collector, store, insight_template, renotify_minutes=10):
        self.eero = eero
        self.collector = collector
        self.store = store
        self.insight_template = insight_template
        self.renotify_minutes = renotify_minutes

    def _net_name(self, network_id):
        return self.eero.network_info(network_id).get("name") or f"Red {network_id}"

    def _alerts_text(self, alerts):
        if not alerts:
            return "N/D"
        return ", ".join(ALERTS_ES.get(a, a) for a in alerts)

    def _should_renotify(self, row):
        last = datetime.fromisoformat(row["last_alert"])
        return (datetime.now(timezone.utc) - last).total_seconds() / 60 >= self.renotify_minutes

    def poll_once(self):
        log.info("Consultando redes no saludables...")
        dry = getattr(self.collector, "dry_run", False)
        try:
            nets = self.eero.unhealthy_networks()
        except EeroAuthError:
            log.warning("Token fallo al consultar unhealthy (lo notifica el motor de caidas).")
            return

        activos = {str(n["network_id"]): n for n in nets if not n.get("is_deleted")}
        log.info("Redes no saludables: %d", len(activos))

        for nid, net in activos.items():
            row = self.store.get(nid, kind=self.KIND)
            es_nueva = row is None
            if es_nueva or self._should_renotify(row):
                sev = net.get("highest_severity", "")
                emoji, label = SEVERITY.get(sev, ("⚪", sev or "?"))
                name = self._net_name(nid)
                alerts = self._alerts_text(net.get("alerts"))
                estado = label if es_nueva else f"sigue {label}"
                self.collector.add(f"{emoji} {name}{_etiqueta(nid)} ({nid}): {estado} · {alerts}")
                if not dry:
                    self.store.upsert_alert(
                        nid, sev, kind=self.KIND, detalle=alerts, name=name
                    )

        for nid in self.store.all_ids(kind=self.KIND) - set(activos.keys()):
            row = self.store.get(nid, kind=self.KIND)
            name = (row["name"] if row and row["name"] else self._net_name(nid))
            self.collector.add(f"✅ {name} ({nid}): recuperada (saludable)")
            if not dry:
                self.store.record_resolution(
                    self.KIND, nid, name,
                    row["detalle"] if row else None,
                    row["first_alert"] if row else None,
                    row["alert_count"] if row else 0,
                )
                self.store.remove(nid, kind=self.KIND)
