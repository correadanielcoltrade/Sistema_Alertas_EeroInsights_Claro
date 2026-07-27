"""Comandos por WhatsApp: construyen respuestas de texto libre (ventana 24h).

Formato WhatsApp: *negrita*  _cursiva_ . Un solo mensaje consolidado por comando.
"""
import re
from datetime import datetime, timezone, timedelta

COT = timezone(timedelta(hours=-5))


def _solo_digitos(s):
    return re.sub(r"\D", "", s or "")


def help_text():
    return (
        "🤖 *Sistema de Alertas eero (WhatsApp)*\n\n"
        "Monitoreo la red cada 10 min y aviso las novedades.\n\n"
        "*Recibir alertas:*\n"
        "/suscribir - dar de alta este numero ➕\n"
        "/baja - dar de baja este numero ➖\n"
        "_Tambien: /suscribir 573001112233 para otro numero._\n\n"
        "*Consultas:*\n"
        "/estado - resumen de novedades activas\n"
        "/soluciones - redes solucionadas hoy\n"
        "/sin_solucionar - redes pendientes (tiempo y avisos)\n"
        "/help - muestra este menu"
    )


# Palabras que activan alta/baja (con o sin '/', en mayus o minus).
ALTA = {"suscribir", "suscribirme", "alta", "suscribete", "activar"}
BAJA = {"baja", "desuscribir", "desuscribirme", "cancelar", "salir"}


_NO_CONFIG = ("⚠️ La autogestion de suscripciones no esta configurada "
              "(falta la variable DATABASE_URL en el servidor).")
_DB_ERROR = ("⚠️ No pude conectar con la base de datos en este momento. "
             "Intenta de nuevo en un minuto.")


def _quien(numero, sender):
    """Texto para el numero afectado: 'este numero' si es el propio, o el numero."""
    return "este numero" if numero == sender else f"el numero {numero}"


def alta_text(subs, numero, sender):
    if subs is None:
        return _NO_CONFIG
    estado = subs.subscribe(numero)
    quien = _quien(numero, sender)
    if estado == "nuevo":
        return (f"✅ *Suscrito:* {quien} recibira las alertas de eero.\n"
                "Escribe */baja* para darlo de baja.")
    if estado == "reactivado":
        return (f"✅ *Reactivado:* {quien} vuelve a recibir alertas.\n"
                "Escribe */baja* para darlo de baja.")
    if estado == "ya_activo":
        return (f"ℹ️ {quien.capitalize()} *ya estaba suscrito*.\n"
                "Escribe */baja* para dejar de recibir alertas.")
    return _DB_ERROR


def baja_text(subs, numero, sender):
    if subs is None:
        return _NO_CONFIG
    estado = subs.unsubscribe(numero)
    quien = _quien(numero, sender)
    if estado == "dado_de_baja":
        return (f"✅ *Baja realizada:* {quien} ya no recibira alertas.\n"
                "Escribe */suscribir* para volver a activarlas.")
    if estado == "no_estaba":
        return (f"ℹ️ {quien.capitalize()} *no estaba suscrito*.\n"
                "Escribe */suscribir* para recibir alertas.")
    return _DB_ERROR


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
    unhealthy = store.all_active("unhealthy")
    criticas = [r for r in unhealthy if r["ref"] == "CRITICAL"]
    no_criticas = [r for r in unhealthy if r["ref"] != "CRITICAL"]
    partes = [
        "📊 *Estado actual*\n",
        f"🚨 Caidas activas: *{outages}*",
        f"🔴 No saludables criticas: *{len(criticas)}*",
        f"🟠 No saludables NO criticas: *{len(no_criticas)}*",
    ]
    # Las NO criticas no generan aviso; se listan aqui para tenerlas presentes.
    if no_criticas:
        partes.append("\n_No criticas (solo informativas):_")
        for r in no_criticas:
            name = r["name"] or f"Red {r['item_id']}"
            partes.append(f"• {name} ({r['item_id']})")
    return "\n".join(partes)


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
    partes = raw.split()
    # Primera palabra, sin '/' y en minuscula (acepta "SUSCRIBIR" o "/suscribir").
    palabra = partes[0].lstrip("/").lower() if partes else ""
    # Numero opcional como argumento: "/suscribir 573186388932" (para el soporte).
    # Si no se pasa, se usa el numero de quien escribe.
    arg = _solo_digitos(partes[1]) if len(partes) > 1 else ""
    objetivo = arg or sender
    if palabra in ALTA:
        return alta_text(subs, objetivo, sender)
    if palabra in BAJA:
        return baja_text(subs, objetivo, sender)
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
