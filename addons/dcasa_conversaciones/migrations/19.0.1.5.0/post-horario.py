"""El horario de la tienda que dio la dueña (2026-11-13): lunes a sábado de 9:00 a. m. a 6:00 p. m. y domingo de
9:00 a. m. a 5:00 p. m. «De noche nadie recibe clientes», los seguimientos y los avisos de espera se guían por el
horario de *Ajustes de Juan*, que seguía con el de fábrica (8:00 a 17:00).

Solo se escribe si el horario sigue EXACTAMENTE como vino de fábrica (8:00 a 17:00, sin hora propia del domingo y todos
los días marcados): si Gerencia ya lo había cambiado a propósito, no se toca. Con el ORM, así queda en el historial de
Ajustes de Juan con una nota. Idempotente."""
from odoo import SUPERUSER_ID, api

DIAS = ('dia_domingo', 'dia_lunes', 'dia_martes', 'dia_miercoles', 'dia_jueves', 'dia_viernes', 'dia_sabado')
NOTA = ('Horario de la tienda puesto al día con el que dio la dueña (2026-11-13): lunes a sábado de 9:00 a. m. '
        'a 6:00 p. m. y domingo de 9:00 a. m. a 5:00 p. m. Se usa para «De noche nadie recibe clientes», los '
        'seguimientos y los avisos. Si cambia, cámbialo aquí mismo.')


def de_fabrica(ajustes):
    return (ajustes.horario_inicio == 8.0 and ajustes.horario_fin == 17.0 and not ajustes.horario_fin_domingo
            and all(ajustes[dia] for dia in DIAS))


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for ajustes in env['dcasa.juan.ajustes'].search([]):
        if not de_fabrica(ajustes):
            continue
        ajustes.write({'horario_inicio': 9.0, 'horario_fin': 18.0, 'horario_fin_domingo': 17.0})
        ajustes.message_post(body=NOTA, message_type='comment', subtype_xmlid='mail.mt_note')
