"""Colector de alertas: acumula bloques detallados y los envia consolidados.

Como la plantilla de WhatsApp tiene limite de ~1024 caracteres, se empaquetan
cuantos bloques quepan bajo 'budget' por mensaje; si no caben todos, se parte
en varios mensajes (plantillas).
"""
import logging

log = logging.getLogger("batch")

SEP = "\n\n"  # linea en blanco entre alertas


class Collector:
    def __init__(self, dry_run=False):
        self.lines = []
        self.dry_run = dry_run

    def reset(self):
        self.lines = []

    def add(self, block):
        self.lines.append(block)

    def _empaquetar(self, budget):
        grupos, actual, tam = [], [], 0
        for blk in self.lines:
            extra = len(blk) + len(SEP)
            if actual and tam + extra > budget:
                grupos.append(actual)
                actual, tam = [], 0
            actual.append(blk)
            tam += extra
        if actual:
            grupos.append(actual)
        return grupos

    def flush(self, wa, recipients, template, lang, budget=750):
        if not self.lines:
            return
        grupos = self._empaquetar(budget)
        log.info("Enviando %d alertas en %d mensaje(s) a %d destinatario(s).",
                 len(self.lines), len(grupos), len(recipients))
        for grupo in grupos:
            cuerpo = SEP.join(grupo)
            for to in recipients:
                wa.send_template(to, template, lang, cuerpo)
        self.reset()
