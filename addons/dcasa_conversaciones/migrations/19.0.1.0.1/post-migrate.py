"""Primer mensaje corto (decisión de la dueña, 2026-10-09).

Los textos de bienvenida y privacidad viven en el registro de ajustes, así que cambiar el valor por defecto no toca
una base que ya existe. Solo se reemplazan si todavía son los textos propuestos originalmente: lo que alguien ya
editó en Ajustes no se pisa.
"""
BIENVENIDA_VIEJA = (
    "Hola, soy el asistente automático del equipo de D'CASA. Te ayudo con camas, colchones y muebles, "
    "y con el programa Socios. Si prefieres hablar con una persona, escríbeme *persona* y te atiende "
    "una vendedora."
)
PRIVACIDAD_VIEJA = (
    "Esta conversación la atiende un asistente automático con inteligencia artificial, y lo que "
    "escribes se envía a nuestro proveedor de IA y a WhatsApp o la red por la que nos escribes para "
    "poder responderte. Se guarda en el sistema de D'CASA mientras seas cliente. Puedes pedir una "
    "persona o que borremos tus datos cuando quieras. Más en dcasapty.com/privacidad."
)
BIENVENIDA_NUEVA = (
    "Hola, soy el asistente automático de D'CASA. Si prefieres hablar con una persona, escríbeme "
    "*persona* y te atiende una vendedora."
)


def migrate(cr, version):
    cr.execute(
        'UPDATE dcasa_juan_ajustes SET mensaje_bienvenida = %s WHERE mensaje_bienvenida = %s',
        [BIENVENIDA_NUEVA, BIENVENIDA_VIEJA])
    cr.execute(
        "UPDATE dcasa_juan_ajustes SET texto_privacidad_corto = '' WHERE texto_privacidad_corto = %s",
        [PRIVACIDAD_VIEJA])
