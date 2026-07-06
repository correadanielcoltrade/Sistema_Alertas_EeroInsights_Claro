"""Colector de alertas: acumula lineas y las envia consolidadas por lotes.

Las alertas son proactivas -> se mandan como PLANTILLA de WhatsApp. Cada
plantilla lleva una sola variable de cuerpo con hasta BATCH_SIZE lineas.
"""
import logging

log = logging.getLogger("batch")


class Collector:
    def __init__(self, dry_run=False):
        self.lines = []
        self.dry_run = dry_run

    def reset(self):
        self.lines = []

    def add(self, line):
        self.lines.append(line)

    def flush(self, wa, recipients, template, lang, batch_size=10):
        """Envia las lineas acumuladas en lotes, a cada destinatario."""
        if not self.lines:
            return
        lotes = [self.lines[i:i + batch_size] for i in range(0, len(self.lines), batch_size)]
        log.info("Enviando %d alertas en %d mensaje(s) a %d destinatario(s).",
                 len(self.lines), len(lotes), len(recipients))
        for lote in lotes:
            cuerpo = "\n".join(lote)
            for to in recipients:
                wa.send_template(to, template, lang, cuerpo)
        self.reset()
