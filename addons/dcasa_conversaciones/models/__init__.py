# Piezas puras (sin base de datos): horario, celulares, adjuntos, vista pública y reglas de Socios para clientes.
from . import crm_reglas, horario, celulares, adjuntos, publico, reglas_clientes, conocimiento_texto, tienda, firma
from . import transaccion, panel_calculos, avisos_texto
# Modelos.
from . import ajustes, cliente_worker, etiquetas, conversacion, mensaje, mensaje_parte, res_partner, res_users
from . import ir_attachment
from . import conocimiento, pregunta_responder, presencia, crm_lead
from . import reparto, conversacion_reparto
# Los textos de los avisos por Telegram y «de noche nadie recibe clientes» (2026-11-13).
from . import conversacion_avisos, conversacion_noche, conversacion_archivos
from . import conversacion_panel, conversacion_panel_extra, conversacion_panel_catalogo
from . import cliente_worker_panel, panel_juan, panel_reparto, telegram_consola
# Comentarios de Instagram y Facebook que atendió Juan (2026-11-12).
from . import comentario
# «Costos de IA»: anotar que Meta ya cobró y ver lo consumido desde el último pago (2026-11-12).
from . import pagos_ia
# Herramientas de Juan en el registro de Brian.
from . import brian_juan, herramientas_juan, herramientas_juan_cotizacion, herramientas_juan_envios, herramientas_crm
from . import brian_voz
# El origen «Chatbot» de las cotizaciones de Juan (y de sus facturas).
from . import sale_origen
# Brian lee el Resumen, el Reparto y las cotizaciones que vencen solas (2026-11-06).
from . import herramientas_conversaciones
# El horario de la tienda en el sitio (Visítanos y el pie), de estos mismos ajustes (2026-11-13).
from . import horario_sitio
# Solo para el entorno de prueba.
from . import ejemplos
