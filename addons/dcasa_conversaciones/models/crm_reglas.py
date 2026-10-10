"""Reglas FIJAS del CRM que se ajusta solo: funciones PURAS (sin base de datos, sin reloj, sin IA).

Todo lo que mueve una oportunidad por su cuenta sale de aquí y de hechos que Odoo ya sabe (una cotización enviada, una
factura pagada, cuánto hace que el cliente no escribe). Nada depende de lo que la IA «opine»: así el resultado se puede
probar, explicar y apagar. Ver ``docs/CRM_AUTOMATICO.md``.

Temperatura (``1`` frío · ``2`` tibio · ``3`` caliente): los valores se ordenan como texto, así «Mayor temperatura
primero» funciona con un simple orden descendente.
"""
from dataclasses import dataclass

FRIO, TIBIO, CALIENTE = '1', '2', '3'
TEMPERATURAS = [(FRIO, 'Frío'), (TIBIO, 'Tibio'), (CALIENTE, 'Caliente')]
NOMBRE_TEMPERATURA = dict(TEMPERATURAS)

# Puntos por hecho. Quien cotizó o dijo para cuándo lo quiere está comprando; escribir seguido y hace poco suma menos.
PUNTOS = {'cotizacion': 3, 'cuando': 2, 'zona': 1, 'reciente': 1, 'constante': 1, 'persona': 1}
UMBRAL_CALIENTE = 5
UMBRAL_TIBIO = 3

HORAS_RECIENTE = 48            # «escribió hace poco»
MENSAJES_CONSTANTE = 4         # «escribe seguido»: 4 o más mensajes del cliente en los últimos 7 días
DIAS_CONSTANTE = 7
DIAS_PARA_TIBIO_COMO_MUCHO = 7   # sin mensajes del cliente en más de 7 días: como mucho tibio…
DIAS_PARA_FRIO = 14              # …y en más de 14 días, frío

MINIMO_DIAS_PARA_PERDIDA = 14   # los seguimientos (5 h y 5 días) terminan antes
MAX_TEXTO_DATO = 80   # zona de entrega y «para cuándo»: texto corto, sin direcciones exactas

FRASES = {
    'cotizacion': 'pidió cotización',
    'cuando': 'dijo para cuándo lo quiere',
    'zona': 'dijo su zona de entrega',
    'reciente': 'escribió hace poco',
    'constante': 'escribe seguido',
    'persona': 'lo atiende una persona',
}


@dataclass(frozen=True)
class Hechos:
    """Lo que Odoo sabe de una oportunidad en este momento."""
    cotizacion: bool = False                 # hay una cotización ligada, enviada o confirmada
    cuando: bool = False                     # el cliente dijo para cuándo lo quiere
    zona: bool = False                       # el cliente dijo su zona de entrega
    horas_sin_escribir: float | None = None  # desde el último mensaje del CLIENTE (None = nunca escribió)
    mensajes_semana: int = 0                 # mensajes del cliente en los últimos 7 días
    atiende_persona: bool = False            # una vendedora tiene la conversación


def hechos_que_suman(hechos):
    """Las claves de ``PUNTOS`` que cumple ``hechos``, en orden de peso."""
    cumple = {
        'cotizacion': hechos.cotizacion,
        'cuando': hechos.cuando,
        'zona': hechos.zona,
        'reciente': hechos.horas_sin_escribir is not None and hechos.horas_sin_escribir <= HORAS_RECIENTE,
        'constante': hechos.mensajes_semana >= MENSAJES_CONSTANTE,
        'persona': hechos.atiende_persona,
    }
    return [clave for clave in PUNTOS if cumple[clave]]


def temperatura(hechos):
    """``(nivel, motivo)``: la temperatura de la oportunidad y por qué, en una frase para quien la lea.

    Se enfría con el tiempo: sin mensajes del cliente en más de 7 días, como mucho tibio; en más de 14, frío.
    """
    claves = hechos_que_suman(hechos)
    total = sum(PUNTOS[c] for c in claves)
    nivel = CALIENTE if total >= UMBRAL_CALIENTE else TIBIO if total >= UMBRAL_TIBIO else FRIO
    motivo = ', '.join(FRASES[c] for c in claves) or 'sin señales de compra todavía'
    dias = None if hechos.horas_sin_escribir is None else hechos.horas_sin_escribir / 24
    if dias is not None and dias > DIAS_PARA_FRIO:
        nivel = FRIO
        motivo += f'; no escribe hace {int(dias)} días'
    elif dias is not None and dias > DIAS_PARA_TIBIO_COMO_MUCHO:
        if nivel == CALIENTE:
            nivel = TIBIO
        motivo += f'; no escribe hace {int(dias)} días'
    return nivel, motivo


def limpiar_dato(texto):
    """Un dato que dijo el cliente (zona, para cuándo): una línea de texto plano, con tope. ``''`` si no sirve."""
    limpio = ' '.join(str(texto or '').split())
    if not any(c.isalnum() for c in limpio):
        return ''
    return limpio[:MAX_TEXTO_DATO]


def toca_perder(dias_sin_movimiento, dias_maximos, la_trabaja_una_persona):
    """¿Se archiva por «sin respuesta»? Solo con hechos, nunca por lo que la IA interprete.

    * ``dias_maximos`` es el ajuste de Gerencia (0 = nunca; si no, 14 o más: así los seguimientos, que terminan en
      menos de una semana, ya se hicieron).
    * ``dias_sin_movimiento``: desde el último mensaje de la conversación, de quien sea.
    * Si una vendedora la tiene (una tarea pendiente, la conversación en sus manos, un pedido confirmado sin pagar),
      no se archiva: eso lo decide ella.
    """
    if not dias_maximos or dias_maximos <= 0 or dias_sin_movimiento is None or la_trabaja_una_persona:
        return False
    return dias_sin_movimiento >= dias_maximos
