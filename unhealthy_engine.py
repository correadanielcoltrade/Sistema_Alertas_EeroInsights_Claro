"""Motor de redes no saludables para WhatsApp.

Alerta NUEVA -> mensaje individual detallado. Re-notificacion / resuelta ->
linea concisa que se consolida.
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
    "Leaf eero outage over 5 min": "Eero secundario caido +5min",
    "Gateway eero outage over 5 min": "Eero principal caido +5min",
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

    def _detallado(self, net):
        nid = str(net["network_id"])
        emoji, label = SEVERITY.get(net.get("highest_severity", ""), ("⚪", "?"))
        return (
            f"{emoji} ALERTA - Red NO SALUDABLE ({label})\n\n"
            f"🌐 Red: {_con_etiqueta(nid, self._net_name(nid))} (ID {nid})\n"
            f"🏠 Tipo: {net.get('network_type', 'N/D')}\n"
            f"⚠️ Problemas: {self._alerts_text(net.get('alerts'))}\n"
            f"🔢 Ocurrencias (24h): {net.get('count', 'N/D')}\n"
            f"🕒 Ultima: {_fmt_dt(net.get('last_occurrence'))}"
        )

    def _conciso(self, net):
        nid = str(net["network_id"])
        emoji, label = SEVERITY.get(net.get("highest_severity", ""), ("⚪", "?"))
        name = _con_etiqueta(nid, self._net_name(nid))
        return f"{emoji} {name} ({nid}): sigue {label} · {self._alerts_text(net.get('alerts'))}"

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
            if es_nueva:
                self.collector.send_individual(self._detallado(net))  # detallado, aparte
            elif self._should_renotify(row):
                self.collector.add(self._conciso(net))                # conciso, consolidado
            else:
                continue
            if not dry:
                self.store.upsert_alert(
                    nid, net.get("highest_severity"), kind=self.KIND,
                    detalle=self._alerts_text(net.get("alerts")), name=self._net_name(nid),
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
