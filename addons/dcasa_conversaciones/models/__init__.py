# Piezas puras (sin base de datos): horario, celulares, adjuntos, vista pública y reglas de Socios para clientes.
from . import horario, celulares, adjuntos, publico, reglas_clientes, conocimiento_texto, tienda, firma
from . import transaccion, panel_calculos
# Modelos.
from . import ajustes, cliente_worker, etiquetas, conversacion, mensaje, res_partner, res_users, ir_attachment
from . import conocimiento, presencia
from . import conversacion_panel, conversacion_panel_extra, conversacion_panel_catalogo
from . import cliente_worker_panel, panel_juan
# Herramientas de Juan en el registro de Brian.
from . import brian_juan, herramientas_juan
# Solo para el entorno de prueba.
from . import ejemplos
