"""Comandos por WhatsApp: construyen respuestas de texto libre (ventana 24h).

Formato WhatsApp: *negrita*  _cursiva_ . Un solo mensaje consolidado por comando.
"""
from datetime import datetime, timezone, timedelta

COT = timezone(timedelta(hours=-5))


def help_text():
    return (
        "🤖 *Sistema de Alertas eero (WhatsApp)*\n\n"
        "Monitoreo la red cada 10 min y aviso las novedades.\n\n"
        "*Recibir alertas en este numero:*\n"
        "/suscribir - dar de alta este numero ➕\n"
        "/baja - dejar de recibir alertas ➖\n\n"
        "*Consultas:*\n"
        "/estado - resumen de novedades activas\n"
        "/soluciones - redes solucionadas hoy\n"
        "/sin_solucionar - redes pendientes (tiempo y avisos)\n"
        "/help - muestra este menu"
    )


# Palabras que activan alta/baja (con o sin '/', en mayus o minus).
ALTA = {"suscribir", "suscribirme", "alta", "suscribete", "activar"}
BAJA = {"baja", "desuscribir", "desuscribirme", "cancelar", "salir"}


def alta_text(subs, sender):
    if subs is None:
        return "⚠️ La gestion de suscripciones no esta disponible ahora mismo."
    estado = subs.subscribe(sender)
    if estado == "nuevo":
        return ("✅ *Quedaste suscrito* a las alertas de eero en este numero.\n"
                "Escribe */baja* cuando quieras dejar de recibirlas.")
    if estado == "reactivado":
        return ("✅ *Reactivamos* las alertas en este numero.\n"
                "Escribe */baja* para dejar de recibirlas.")
    if estado == "ya_activo":
        return ("ℹ️ Este numero *ya estaba suscrito*.\n"
                "Escribe */baja* para dejar de recibir alertas.")
    return "⚠️ No pude registrar la suscripcion. Intenta de nuevo en un momento."


def baja_text(subs, sender):
    if subs is None:
        return "⚠️ La gestion de suscripciones no esta disponible ahora mismo."
    estado = subs.unsubscribe(sender)
    if estado == "dado_de_baja":
        return ("✅ *Listo, te diste de baja.* Ya no recibiras alertas en este numero.\n"
                "Escribe */suscribir* para volver a activarlas.")
    if estado == "no_estaba":
        return ("ℹ️ Este numero *no estaba suscrito*.\n"
                "Escribe */suscribir* si quieres recibir alertas.")
    return "⚠️ No pude procesar la baja. Intenta de nuevo en un momento."


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


def dispatch(text, store, subs=None, sender=None):
    """Devuelve el texto de respuesta para un mensaje entrante.

    'subs' es el SubscriberStore (o None) y 'sender' el numero que escribio,
    para las altas/bajas.
    """
    raw = (text or "").strip()
    # Primera palabra, sin '/' y en minuscula (acepta "SUSCRIBIR" o "/suscribir").
    palabra = raw.split()[0].lstrip("/").lower() if raw else ""
    if palabra in ALTA:
        return alta_text(subs, sender)
    if palabra in BAJA:
        return baja_text(subs, sender)
    if not raw.startswith("/"):
        return help_text()
    cmd = raw.split()[0][1:].lower()
    if cmd == "estado":
        return estado_text(store)
    if cmd in ("soluciones", "solucionadas"):
        return soluciones_text(store)
    if cmd in ("sin_solucionar", "pendientes"):
        return sin_solucionar_text(store)
    return help_text()
