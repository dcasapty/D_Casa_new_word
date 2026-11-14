"""El horario de la tienda para el sitio (Visítanos y el pie): sale de UN solo lugar, los Ajustes de Juan.

``website_dcasa`` no puede depender de ``dcasa_conversaciones`` (es al revés), así que aquí queda un gancho,
``website._dcasa_horario_tienda()``, que devuelve las filas del horario y que ``dcasa_conversaciones`` llena con
``horario_inicio``, ``horario_fin``, ``horario_fin_domingo`` y los días de sus ajustes. Sin ese módulo el gancho
devuelve una lista vacía y el sitio no muestra horario: no se inventa. Tampoco se inventan feriados.

Las funciones de aquí son puras (sin base de datos). Días: 0 = domingo … 6 = sábado, como en los Ajustes de Juan.
"""
from odoo import models

NOMBRES_DIA = ('domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado')
CORTOS_DIA = ('dom.', 'lun.', 'mar.', 'mié.', 'jue.', 'vie.', 'sáb.')
# En Panamá la semana se lee de lunes a domingo.
ORDEN_SEMANA = (1, 2, 3, 4, 5, 6, 0)
DOMINGO = 0
CERRADO = 'Cerrado'


def hora_amable(valor):
    """9.0 → «9:00 a. m.», 18.5 → «6:30 p. m.», 12.0 → «12:00 p. m.» (hora de Panamá, como en los carteles)."""
    minutos = round(float(valor) * 60)
    hora, minuto = divmod(minutos, 60)
    sufijo = 'a. m.' if hora < 12 else 'p. m.'
    hora12 = hora % 12 or 12
    return f'{hora12}:{minuto:02d} {sufijo}'


def _nombre_grupo(dias, nombres):
    """[1, 2, 3, 4, 5, 6] → «lunes a sábado»; [6, 0] → «sábado y domingo»; [3] → «miércoles»."""
    if len(dias) == 1:
        return nombres[dias[0]]
    if len(dias) == 2:
        return f'{nombres[dias[0]]} y {nombres[dias[1]]}'
    return f'{nombres[dias[0]]} a {nombres[dias[-1]]}'


def filas_horario(inicio, fin, dias, fin_domingo=None):
    """Las filas de la tabla: ``[{'dias': 'Lunes a sábado', 'horas': '9:00 a. m. a 6:00 p. m.', 'corto': …}, …]``.

    Junta los días seguidos (de lunes a domingo) que tienen el mismo horario; un día que no abre dice «Cerrado».
    ``fin_domingo`` vacío (0 o None) = el domingo cierra a la misma hora que los demás.
    """
    dias = set(dias or ())
    if not dias or not 0 <= inicio < fin <= 24 or (fin_domingo and not inicio < fin_domingo <= 24):
        return []   # un horario que no cuadra no se publica (los Ajustes de Juan ya lo validan)
    por_dia = []
    for dia in ORDEN_SEMANA:
        if dia not in dias:
            por_dia.append((dia, None))
            continue
        cierre = fin_domingo if dia == DOMINGO and fin_domingo else fin
        por_dia.append((dia, (inicio, cierre)))
    grupos = []
    for dia, horas in por_dia:
        if grupos and grupos[-1][1] == horas:
            grupos[-1][0].append(dia)
        else:
            grupos.append(([dia], horas))
    filas = []
    for dias_grupo, horas in grupos:
        texto = f'{hora_amable(horas[0])} a {hora_amable(horas[1])}' if horas else CERRADO
        largo = _nombre_grupo(dias_grupo, NOMBRES_DIA)
        corto = _nombre_grupo(dias_grupo, CORTOS_DIA)
        corto = corto[:1].upper() + corto[1:]
        filas.append({'dias': largo[:1].upper() + largo[1:], 'horas': texto,
                      'corto': f'{corto} {texto}' if horas else f'{corto} cerrado'})
    return filas


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_horario_tienda(self):
        """Gancho: las filas del horario de la tienda (``filas_horario``). Vacío = no se sabe y no se muestra nada.
        ``dcasa_conversaciones`` lo llena con el horario de los Ajustes de Juan."""
        return []
