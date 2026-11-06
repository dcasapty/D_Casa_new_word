# Núcleo: registro de herramientas, política, auditoría, proveedores de IA y conversación.
from . import registro, politica, accion, uso, proveedores, conversacion, ajustes, telegram, importacion
# Herramientas por área (cada archivo agrega métodos @herramienta a brian.herramientas).
from . import herramientas_generales, herramientas_ventas, herramientas_catalogo, \
    herramientas_contabilidad, herramientas_clientes, herramientas_usuarios, herramientas_importacion, \
    herramientas_fe, herramientas_operacion, herramientas_vendedores, herramientas_guia, herramientas_estadisticas, \
    herramientas_bodega_nomina, \
    herramientas_combos, \
    herramientas_decisiones
# Brian al día (2026-11-06): las pantallas propias, Sofía y Meta (módulos que dcasa_brian no exige).
from . import herramientas_pantallas, herramientas_asistentes, herramientas_meta
