"""El horario de la tienda que dio la dueña (2026-11-13): lunes a sábado de 9:00 a. m. a 6:00 p. m. y domingo de
9:00 a. m. a 5:00 p. m. Es el que ahora muestra el sitio (Visítanos y el pie) y el que ya usa Juan.

Solo si los ajustes siguen con los valores de fábrica (8:00 a 17:00, el domingo igual, todos los días): si alguien
ya puso otro horario en Ajustes de Juan, no se toca.
"""
from odoo import SUPERUSER_ID, api

DE_FABRICA = {'horario_inicio': 8.0, 'horario_fin': 17.0, 'horario_fin_domingo': 0.0}
DIAS = ('dia_domingo', 'dia_lunes', 'dia_martes', 'dia_miercoles', 'dia_jueves', 'dia_viernes', 'dia_sabado')
DE_LA_DUENA = {'horario_inicio': 9.0, 'horario_fin': 18.0, 'horario_fin_domingo': 17.0}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ajustes = env['dcasa.juan.ajustes'].search([], limit=1)
    if not ajustes:
        return
    de_fabrica = all(ajustes[campo] == valor for campo, valor in DE_FABRICA.items()) and all(ajustes[d] for d in DIAS)
    if de_fabrica:
        ajustes.write(DE_LA_DUENA)
