"""Motor de caidas para WhatsApp: bloques detallados (envio consolidado)."""
import logging
from datetime import datetime, timezone, timedelta

from eero_client import parse_geo_ip, EeroAuthError
import network_labels

log = logging.getLogger("engine")

REASONS = {
    "CONN_DOWN_NO_LINK": "Sin enlace fisico",
    "CONN_DOWN_NO_INTERNET": "Sin Internet",
    "CONN_DOWN_DHCP": "Falla DHCP",
    "CONN_DOWN_PPPOE": "Falla PPPoE",
    "GATEWAY_DOWN": "Gateway caido",
    "POWER_LOSS": "Posible corte de energia",
}


def _fmt_dt(iso_str):
    if not iso_str:
        return "N/D"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S (COT)")
    except (ValueError, AttributeError):
        return iso_str


def _duration_text(start_iso):
    if not start_iso:
        return "N/D"
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - start).total_seconds() // 60)
        return f"{mins} min" if mins < 60 else f"{mins // 60}h {mins % 60}m"
    except (ValueError, AttributeError):
        return "N/D"


def _con_etiqueta(nid, name):
    label, nick = network_labels.get(nid)
    val = nick or label
    return f"{name} [{val}]" if val else name


class AlertEngine:
    def __init__(self, eero, collector, store, insight_template, renotify_minutes=10):
        self.eero = eero
        self.collector = collector
        self.store = store
        self.insight_template = insight_template
        self.renotify_minutes = renotify_minutes

    def _net_name(self, network_id):
        return self.eero.network_info(network_id).get("name") or f"Red {network_id}"

    def _reason_for(self, outage):
        try:
            detalle = self.eero.outage_detail(outage["network_id"], outage["start_time"])
            if detalle:
                code = detalle[-1].get("reason")
                if code:
                    return REASONS.get(code, code)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo obtener detalle de %s: %s", outage["network_id"], e)
        return "Sin motivo reportado"

    def _should_renotify(self, row):
        last = datetime.fromisoformat(row["last_alert"])
        return (datetime.now(timezone.utc) - last).total_seconds() / 60 >= self.renotify_minutes

    def _detallado(self, outage, reason, name):
        nid = outage["network_id"]
        geo = parse_geo_ip(outage.get("geo_ip"))
        ubic = ", ".join(x for x in [geo.get("city"), geo.get("regionName")] if x) or "N/D"
        isp = geo.get("isp") or "N/D"
        return (
            f"🚨 ALERTA - Red CAIDA\n\n"
            f"🌐 Red: {_con_etiqueta(nid, name)} (ID {nid})\n"
            f"📍 Ubicacion: {ubic}\n"
            f"🏢 Operador: {isp}\n"
            f"⛔ Motivo: {reason}\n"
            f"🕒 Inicio: {_fmt_dt(outage.get('start_time'))}\n"
            f"⏱️ Duracion: {_duration_text(outage.get('start_time'))}"
        )

    def _conciso(self, outage, name):
        # En el consolidado NO se muestran motivo ni duracion (solo van en el
        # mensaje individual detallado de la caida).
        nid = outage["network_id"]
        return f"🚨 {_con_etiqueta(nid, name)} ({nid}): sigue caida"

    def poll_once(self):
        log.info("Consultando interrupciones de red...")
        dry = getattr(self.collector, "dry_run", False)
        try:
            outages = self.eero.networks_with_outages()
        except EeroAuthError as e:
            self._handle_token_failure(e)
            return

        if not dry and self.store.get_flag("token_fail"):
            self.collector.add("✅ Token de eero restablecido. Monitoreo reanudado.")
            self.store.clear_flag("token_fail")

        activas = {str(o["network_id"]): o for o in outages if o.get("end_time") is None}
        log.info("Caidas activas: %d", len(activas))

        for nid, outage in activas.items():
            row = self.store.get(nid)
            es_nueva = row is None
            if es_nueva:
                name = self._net_name(nid)
                reason = self._reason_for(outage)
                self.collector.send_individual(self._detallado(outage, reason, name))
            elif self._should_renotify(row):
                name = self._net_name(nid)
                reason = self._reason_for(outage)  # se guarda como detalle (p. ej. /soluciones)
                self.collector.add(self._conciso(outage, name))
            else:
                continue
            if not dry:
                self.store.upsert_alert(nid, outage.get("start_time"), detalle=reason, name=name)

        for nid in self.store.all_ids() - set(activas.keys()):
            row = self.store.get(nid)
            name = (row["name"] if row and row["name"] else self._net_name(nid))
            self.collector.add(f"✅ {name} ({nid}): recuperada")
            if not dry:
                self.store.record_resolution(
                    "outage", nid, name,
                    row["detalle"] if row else None,
                    row["first_alert"] if row else None,
                    row["alert_count"] if row else 0,
                )
                self.store.remove(nid)

    def _handle_token_failure(self, err):
        log.error("Token de eero fallo: %s", err)
        dry = getattr(self.collector, "dry_run", False)
        if dry or not self.store.get_flag("token_fail"):
            self.collector.add("⚠️ Token de eero invalido (401/403). Renovar login de eero.")
            if not dry:
                self.store.set_flag("token_fail", "1")
        else:
            log.info("Token sigue fallando (ya se notifico).")
