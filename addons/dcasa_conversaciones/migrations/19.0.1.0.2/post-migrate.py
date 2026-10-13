"""Juan se presenta como «Juan de D'CASA» (decisión de la dueña, 2026-10-09, noche).

El saludo vive en el registro de ajustes, así que cambiar el valor por defecto no toca una base que ya existe. Solo se
reemplaza si todavía es el texto anterior (el propuesto originalmente): lo que alguien ya editó en Ajustes no se pisa.
"""
BIENVENIDA_ANTERIOR = (
    "Hola, soy el asistente automático de D'CASA. Si prefieres hablar con una persona, escríbeme "
    "*persona* y te atiende una vendedora."
)
BIENVENIDA_NUEVA = "Hola, soy Juan de D'CASA."


def migrate(cr, version):
    cr.execute(
        'UPDATE dcasa_juan_ajustes SET mensaje_bienvenida = %s WHERE mensaje_bienvenida = %s',
        [BIENVENIDA_NUEVA, BIENVENIDA_ANTERIOR])
