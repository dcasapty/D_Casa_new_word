# Núcleo: registro de herramientas, política, auditoría, proveedores de IA y conversación.
from . import registro, politica, accion, uso, proveedores, conversacion, ajustes, telegram, importacion
# Herramientas por área (cada archivo agrega métodos @herramienta a brian.herramientas).
from . import herramientas_generales, herramientas_ventas, herramientas_catalogo, \
    herramientas_contabilidad, herramientas_clientes, herramientas_usuarios, herramientas_importacion, \
    herramientas_operacion
