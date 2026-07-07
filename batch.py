"""Colector/emisor de alertas por WhatsApp.

- send_individual(bloque): envia YA un mensaje aparte (alertas NUEVAS, detallado).
- add(linea) + flush(): consolida re-notificaciones/resueltas (hasta max_count
  por mensaje, sin pasar de budget caracteres) y las envia al final del ciclo.
Ambos usan la misma plantilla (solo cambia el contenido de {{1}}).
"""
import logging

log = logging.getLogger("batch")

SEP = "\n"  # una alerta por linea en el consolidado


class Collector:
    def __init__(self, wa, recipients, template, lang,
                 budget=900, max_count=10, dry_run=False, footer_url=""):
        self.wa = wa
        self.recipients = recipients
        self.template = template
        self.lang = lang
        self.budget = budget
        self.max_count = max_count
        self.dry_run = dry_run
        self.footer_url = footer_url  # link generico al final del consolidado
        self.lines = []

    # ---- individuales (alertas nuevas, formato detallado) ----
    def send_individual(self, body):
        for to in self.recipients:
            self.wa.send_template(to, self.template, self.lang, body)

    # ---- consolidado (re-notificaciones / resueltas) ----
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
            if self.footer_url:
                cuerpo += f"\n\n👉 Ver en Insights: {self.footer_url}"
            for to in self.recipients:
                self.wa.send_template(to, self.template, self.lang, cuerpo)
        self.reset()
