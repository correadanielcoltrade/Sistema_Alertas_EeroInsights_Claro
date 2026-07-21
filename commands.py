"""Comandos por WhatsApp: construyen respuestas de texto libre (ventana 24h).

Formato WhatsApp: *negrita*  _cursiva_ . Un solo mensaje consolidado por comando.
"""
from datetime import datetime, timezone, timedelta

COT = timezone(timedelta(hours=-5))


def help_text():
    return (
        "🤖 *Sistema de Alertas eero (WhatsApp)*\n\n"
        "Monitoreo la red cada 10 min y aviso las novedades.\n\n"
        "*Comandos:*\n"
        "/estado - resumen de novedades activas\n"
        "/soluciones - redes solucionadas hoy\n"
        "/sin_solucionar - redes pendientes (tiempo y avisos)\n"
        "/help - muestra este menu"
    )


def _fmt_local(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(COT).strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return iso or "N/D"


def _dur(a, b):
    try:
        m = int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() // 60)
        return f"{m} min" if m < 60 else f"{m // 60}h {m % 60}m"
    except (ValueError, TypeError):
        return "N/D"


def _start_of_today_utc():
    inicio = datetime.now(COT).replace(hour=0, minute=0, second=0, microsecond=0)
    return inicio.astimezone(timezone.utc).isoformat()


def estado_text(store):
    outages = len(store.all_ids("outage"))
    unhealthy = len(store.all_ids("unhealthy"))
    return (
        "📊 *Estado actual*\n\n"
        f"🚨 Caidas activas: *{outages}*\n"
        f"🔴🟠 Redes no saludables: *{unhealthy}*"
    )


def soluciones_text(store):
    rows = store.resolutions_since(_start_of_today_utc())
    if not rows:
        return "✅ *Soluciones del dia*\n\nHoy no se ha resuelto ninguna novedad."
    partes = [f"✅ *Soluciones del dia* ({len(rows)})\n"]
    for r in rows:
        name = r["name"] or f"Red {r['item_id']}"
        tipo = "Caida" if r["kind"] == "outage" else "No saludable"
        partes.append(
            f"• *{name}* ({r['item_id']}) · {tipo}\n"
            f"  Solucionada: {_fmt_local(r['resolved_at'])} · "
            f"Duro: {_dur(r['first_alert'], r['resolved_at'])} · Avisos: {r['alert_count']}\n"
            f"  {r['detalle'] or '-'}"
        )
    return "\n".join(partes)


def sin_solucionar_text(store):
    rows = store.all_active()
    if not rows:
        return "⏳ *Redes sin solucionar*\n\nNo hay redes pendientes. 🎉"
    now = datetime.now(timezone.utc).isoformat()
    partes = [f"⏳ *Redes sin solucionar* ({len(rows)})\n"]
    for r in rows:
        name = r["name"] or f"Red {r['item_id']}"
        tipo = "Caida" if r["kind"] == "outage" else "No saludable"
        partes.append(
            f"• *{name}* ({r['item_id']}) · {tipo}\n"
            f"  Lleva: {_dur(r['first_alert'], now)} · Avisos: {r['alert_count']}\n"
            f"  {r['detalle'] or '-'}"
        )
    return "\n".join(partes)


def dispatch(text, store):
    """Devuelve el texto de respuesta para un mensaje entrante."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return help_text()
    cmd = text.split()[0][1:].lower()
    if cmd == "estado":
        return estado_text(store)
    if cmd in ("soluciones", "solucionadas"):
        return soluciones_text(store)
    if cmd in ("sin_solucionar", "pendientes"):
        return sin_solucionar_text(store)
    return help_text()
