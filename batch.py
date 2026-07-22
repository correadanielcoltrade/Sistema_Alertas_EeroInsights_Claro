"""Colector/emisor de alertas por WhatsApp (dos plantillas).

- send_individual(params): alerta NUEVA -> plantilla INDIVIDUAL (8 variables).
- add(linea) + flush(): re-notificaciones/resueltas -> plantilla CONSOLIDADO
  (10 variables: una red por variable, {{1}}..{{10}}).

En la plantilla de Meta cada variable va sola en su propia linea, SIN numeracion
ni vinetas fijas:

    {{1}}
    {{2}}
    ...
    {{10}}

La vineta y el numero viajan DENTRO de la variable (ver FORMATO_SLOT), asi los
cupos sin usar no dejan ningun rastro; si estuvieran en el texto fijo de la
plantilla quedarian "4." o vinetas sueltas a la vista. Cada variable llega ya
armada, p. ej. "<rombo azul> 1. Daniel (23261159): Estado caida".

Meta exige que TODAS las variables declaradas lleguen con valor y rechaza las
vacias, asi que los cupos sobrantes se rellenan con un espacio de ancho cero
(U+200B): es un caracter valido para Meta pero invisible en WhatsApp, de modo
que esas lineas quedan en blanco (y WhatsApp recorta las del final).
"""
import logging

log = logging.getLogger("batch")

# Relleno invisible para las variables no usadas (ver docstring).
SLOT_VACIO = "\u200b"  # espacio de ancho cero
# Vineta + numeracion, dentro de la variable. Cambia esto para ajustar el look
# (p. ej. "{n}. {texto}" sin vineta, o "\u2022 {texto}" sin numero).
FORMATO_SLOT = "\U0001F539 {n}. {texto}"  # \U0001F539 = rombo azul
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
    def _limpiar(linea, n):
        """Arma la variable: vineta + numero + texto en una sola linea acotada.

        Meta rechaza saltos, tabs y >4 espacios seguidos dentro de una variable.
        """
        txt = " ".join(str(linea).split())
        if not txt:
            return SLOT_VACIO
        slot = FORMATO_SLOT.format(n=n, texto=txt)
        if len(slot) > MAX_SLOT_LEN:
            slot = slot[:MAX_SLOT_LEN - 1].rstrip() + "…"
        return slot

    def _empaquetar(self):
        """Parte las lineas en grupos de 'slots' redes (un mensaje por grupo).

        La numeracion arranca en 1 en cada mensaje: cada uno se lee solo.
        """
        grupos = [self.lines[i:i + self.slots] for i in range(0, len(self.lines), self.slots)]
        return [[self._limpiar(l, n) for n, l in enumerate(g, 1)] for g in grupos]

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
