"""Colector/emisor de alertas por WhatsApp (dos plantillas).

- send_individual(params): alerta NUEVA -> plantilla INDIVIDUAL (8 variables).
- add(linea) + flush(): re-notificaciones/resueltas -> plantilla CONSOLIDADO
  (1 variable con hasta max_count lineas, sin pasar de budget caracteres).
"""
import logging

log = logging.getLogger("batch")

# WhatsApp NO permite saltos de linea en las variables de plantilla, asi que
# el consolidado separa las redes con " | " (el emoji inicial marca cada una).
SEP = " | "


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
        self.max_count = max_count
        self.dry_run = dry_run
        self.lines = []

    # ---- individuales (alertas nuevas, plantilla de 8 variables) ----
    def send_individual(self, params):
        for to in self.recipients:
            self.wa.send_template(to, self.tpl_indiv, self.lang_indiv, params)

    # ---- consolidado (plantilla de 1 variable) ----
    def reset(self):
        self.lines = []

    def add(self, line):
        self.lines.append(line)

    def _empaquetar(self):
        grupos, actual, tam = [], [], 0
        for blk in self.lines:
            extra = len(blk) + len(SEP)
            if actual and (len(actual) >= self.max_count or tam + extra > self.budget):
                grupos.append(actual)
                actual, tam = [], 0
            actual.append(blk)
            tam += extra
        if actual:
            grupos.append(actual)
        return grupos

    def flush(self):
        if not self.lines:
            return
        grupos = self._empaquetar()
        log.info("Consolidado: %d alertas en %d mensaje(s) a %d destinatario(s).",
                 len(self.lines), len(grupos), len(self.recipients))
        for grupo in grupos:
            cuerpo = SEP.join(grupo)
            for to in self.recipients:
                self.wa.send_template(to, self.tpl_consol, self.lang_consol, [cuerpo])
        self.reset()
