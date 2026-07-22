"""Colector/emisor de alertas por WhatsApp (dos plantillas).

- send_individual(params): alerta NUEVA -> plantilla INDIVIDUAL (8 variables).
- add(linea) + flush(): re-notificaciones/resueltas -> plantilla CONSOLIDADO
  (10 variables: una red por variable, {{1}}..{{10}}).

En la plantilla de Meta cada variable va en su propia linea, p. ej.:

    1. {{1}}
    2. {{2}}
    ...
    10. {{10}}

y cada una llega con el formato "Nombre (network_id): Estado caida".
Los espacios sobrantes se rellenan con "-" (Meta rechaza variables vacias).
"""
import logging

log = logging.getLogger("batch")

# Relleno para las variables no usadas del mensaje.
SLOT_VACIO = "-"
# Tope por variable (Meta rechaza el cuerpo si se pasa de ~1024 en total).
MAX_SLOT_LEN = 90


class Collector:
    def __init__(self, wa, recipients,
                 tpl_indiv, lang_indiv, tpl_consol, lang_consol,
                 budget=900, max_count=10, dry_run=False):
        self.wa = wa
        self.recipients = recipients
        self.tpl_indiv = tpl_indiv
        self.lang_indiv = lang_indiv
        self.tpl_consol = tpl_consol
        self.lang_consol = lang_consol
        self.budget = budget
        # Numero de variables de la plantilla consolidada (una red por variable).
        self.slots = max_count
        self.dry_run = dry_run
        self.lines = []

    # ---- individuales (alertas nuevas, plantilla de 8 variables) ----
    def send_individual(self, params):
        for to in self.recipients:
            self.wa.send_template(to, self.tpl_indiv, self.lang_indiv, params)

    # ---- consolidado (plantilla de 'slots' variables) ----
    def reset(self):
        self.lines = []

    def add(self, line):
        self.lines.append(line)

    @staticmethod
    def _limpiar(linea):
        """Una sola linea, sin saltos ni dobles espacios, y acotada."""
        txt = " ".join(str(linea).split())
        if len(txt) > MAX_SLOT_LEN:
            txt = txt[:MAX_SLOT_LEN - 1].rstrip() + "…"
        return txt or SLOT_VACIO

    def _empaquetar(self):
        """Parte las lineas en grupos de 'slots' redes (un mensaje por grupo)."""
        limpias = [self._limpiar(l) for l in self.lines]
        return [limpias[i:i + self.slots] for i in range(0, len(limpias), self.slots)]

    def flush(self):
        if not self.lines:
            return
        grupos = self._empaquetar()
        log.info("Consolidado: %d alertas en %d mensaje(s) a %d destinatario(s).",
                 len(self.lines), len(grupos), len(self.recipients))
        for grupo in grupos:
            # Siempre se envian las 'slots' variables: Meta exige todas.
            params = grupo + [SLOT_VACIO] * (self.slots - len(grupo))
            for to in self.recipients:
                self.wa.send_template(to, self.tpl_consol, self.lang_consol, params)
        self.reset()
