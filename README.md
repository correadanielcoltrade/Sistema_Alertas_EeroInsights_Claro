# Sistema de Alertas Eero → WhatsApp (Cloud API)

Versión WhatsApp del bot. Monitorea eero cada 10 min y envía **alertas
consolidadas** por WhatsApp, y **responde comandos** (webhook).

- **Alerta NUEVA** → **mensaje individual detallado** (Red, Tipo, Problemas,
  Ocurrencias, Última) — sale aparte, de inmediato.
- **Re-notificaciones y resueltas** → **consolidadas** en formato conciso (1 línea por
  alerta), hasta `WA_BATCH_MAX` (10) por mensaje sin pasar de `WA_BODY_BUDGET`
  caracteres; si sobran, se parten en varios mensajes.
- Todo usa la **misma plantilla** (solo cambia el contenido de `{{1}}`).
- **Comandos** (`/estado`, `/soluciones`, `/sin_solucionar`, `/actualizar_labels`, `/help`)
  → llegan por **webhook** y se responden con **texto libre** (ventana de 24h).

## Arquitectura
Un solo servicio (Render Web Service):
- `APScheduler` en segundo plano → poll de eero → alertas consolidadas por plantilla.
- Servidor **Flask** (`/webhook`) → recibe mensajes de Meta → ejecuta el comando → responde.

## Requisitos en Meta (WhatsApp Cloud API)
1. **App** con producto WhatsApp + número verificado.
2. **Phone Number ID** y **token permanente** (System User).
3. **Plantilla aprobada** (categoría *Utility*) con **una variable de cuerpo**:
   ```
   Alertas de red eero 👇

   {{1}}

   Se volvera a notificar en 10 min si sigue asi.
   ```
   Anota su **nombre** (`WA_TEMPLATE_NAME`) e **idioma** (`WA_TEMPLATE_LANG`, ej. `es`).
   > El link a Insights lo agrega el bot dentro de `{{1}}` (específico por red en las
   > alertas nuevas, genérico en el consolidado). Por eso ya no va fijo en la plantilla.
4. **Números destino** (`WA_RECIPIENTS`).
5. Una palabra secreta para el webhook (`WA_VERIFY_TOKEN`, la inventas tú).

> Nota: las variables de plantilla no admiten más de 4 saltos de línea seguidos y el
> cuerpo tiene límite de ~1024 caracteres. Por eso las alertas van concisas y de a 10.

## Configuración local
1. Copia `.env.example` a `.env` y complétalo.
2. ```bash
   python -m venv .venv
   .venv/Scripts/activate
   pip install -r requirements.txt
   ```
3. Prueba sin enviar (`DRY_RUN=true`):
   ```bash
   python main.py once     # un ciclo (imprime las alertas consolidadas)
   ```

## Despliegue en Render (Web Service)
- **Build:** `pip install -r requirements.txt`
- **Start:** `python main.py`
- **Variables de entorno:** las del `.env` (con `DRY_RUN=false`, `DB_PATH=/var/data/alertas.db`).
- **Disco persistente** montado en `/var/data` (para conservar `alertas.db`).
- Render te da una **URL pública** → esa es la del webhook: `https://TU-APP.onrender.com/webhook`.

## Conectar el webhook en Meta (después de desplegar)
1. En Meta → WhatsApp → Configuración → **Webhook**:
   - **Callback URL:** `https://TU-APP.onrender.com/webhook`
   - **Verify token:** el mismo valor de `WA_VERIFY_TOKEN`.
2. **Suscribe** el campo **messages**.
3. Envía un mensaje al número → el bot responde con el menú.

## Notas
- WhatsApp Cloud es **1 a 1** (no hay grupos): las alertas van a cada número de `WA_RECIPIENTS`.
- Cada mensaje de plantilla **tiene costo**; por eso van consolidados.
- Los comandos solo los atienden los números en `WA_RECIPIENTS` (seguridad).
