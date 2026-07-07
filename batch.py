"""Colector de alertas: acumula lineas concisas y las envia consolidadas.

Empaca hasta 'max_count' (10) alertas por mensaje, sin pasar del limite de
caracteres de la plantilla ('budget'). Si sobran, parte en varios mensajes.
"""
import logging

log = logging.getLogger("batch")

SEP = "\n"  # una alerta por linea


class Collector:
    def __init__(self, dry_run=False):
        self.lines = []
        self.dry_run = dry_run

    def reset(self):
        self.lines = []

    def add(self, line):
        self.lines.append(line)

    def _empaquetar(self, budget, max_count):
        grupos, actual, tam = [], [], 0
        for blk in self.lines:
            extra = len(blk) + len(SEP)
            if actual and (len(actual) >= max_count or tam + extra > budget):
                grupos.append(actual)
                actual, tam = [], 0
            actual.append(blk)
            tam += extra
        if actual:
            grupos.append(actual)
        return grupos

    def flush(self, wa, recipients, template, lang, budget=900, max_count=10):
        if not self.lines:
            return
        grupos = self._empaquetar(budget, max_count)
        log.info("Enviando %d alertas en %d mensaje(s) a %d destinatario(s).",
                 len(self.lines), len(grupos), len(recipients))
        for grupo in grupos:
            cuerpo = SEP.join(grupo)
            for to in recipients:
                wa.send_template(to, template, lang, cuerpo)
        self.reset()
