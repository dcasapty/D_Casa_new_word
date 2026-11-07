# Piezas puras (sin base de datos): horario, celulares, adjuntos, vista pública y reglas de Socios para clientes.
from . import crm_reglas, horario, celulares, adjuntos, publico, reglas_clientes, conocimiento_texto, tienda, firma
from . import transaccion, panel_calculos
# Modelos.
from . import ajustes, cliente_worker, etiquetas, conversacion, mensaje, mensaje_parte, res_partner, res_users
from . import ir_attachment
from . import conocimiento, presencia, crm_lead
from . import reparto, conversacion_reparto
from . import conversacion_panel, conversacion_panel_extra, conversacion_panel_catalogo
from . import cliente_worker_panel, panel_juan, panel_reparto, telegram_consola
# Herramientas de Juan en el registro de Brian.
from . import brian_juan, herramientas_juan, herramientas_juan_cotizacion, herramientas_crm
# El origen «Chatbot» de las cotizaciones de Juan (y de sus facturas).
from . import sale_origen
# Brian lee el Resumen, el Reparto y las cotizaciones que vencen solas (2026-11-06).
from . import herramientas_conversaciones
# Solo para el entorno de prueba.
from . import ejemplos
