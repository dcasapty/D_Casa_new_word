"""Atajos de fechas para las pantallas con periodo propio que usan vistas estándar de Odoo (presupuestos,
consolidación): «Hoy · Esta semana · Esta quincena · Este mes · Mes pasado · Este trimestre · Este año fiscal».

Son los mismos de la barra de los reportes contables (``dcasa.reporte.contable._atajos``, hora de Panamá): todos
terminan hoy, menos «Mes pasado»; la semana va de lunes a hoy; la quincena del 1 o del 16 a hoy; el trimestre y el
año fiscal siguen el cierre fiscal de la empresa. Aquí no se repite ninguna cuenta de fechas: se le pide a esa
función.

Dos usos, según la pantalla:

* **Filtrar una lista** (``periodo_atajo``): los registros cuyo periodo (``desde``–``hasta``) toca esos días. Un
  presupuesto de todo el año «toca» este mes; uno de septiembre no.
* **Llenar las fechas de un formulario** (``atajo_fechas``): al elegir un atajo se escriben el «Desde» y el «Hasta».
"""
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

ATAJOS = [('hoy', 'Hoy'), ('semana', 'Esta semana'), ('quincena', 'Esta quincena'), ('mes', 'Este mes'),
          ('mes_pasado', 'Mes pasado'), ('trimestre', 'Este trimestre'), ('ejercicio', 'Este año fiscal')]


class DcasaAtajoFechas(models.AbstractModel):
    _name = 'dcasa.atajo.fechas'
    _description = 'Atajos de fechas (hoy, semana, quincena, mes, trimestre, año fiscal)'

    # Los dos campos de fecha del modelo que hereda, en este orden: (desde, hasta).
    _dcasa_campos_periodo = ('fecha_desde', 'fecha_hasta')

    periodo_atajo = fields.Selection(
        ATAJOS, string='Periodo que cubre', compute='_compute_periodo_atajo', search='_search_periodo_atajo',
        help='Sirve para filtrar: muestra lo que cubre esos días.')
    atajo_fechas = fields.Selection(
        ATAJOS, string='Atajo de fechas', store=False,
        help='Elige uno y se llenan el «Desde» y el «Hasta». Todos terminan hoy, menos «Mes pasado».')

    @api.model
    def _dcasa_ventanas(self):
        """{clave: (desde, hasta)} de los atajos, con hoy en la zona de la persona (Panamá si no tiene una)."""
        reportes = self.env['dcasa.reporte.contable']
        return {a['clave']: (fields.Date.to_date(a['desde']), fields.Date.to_date(a['hasta']))
                for a in reportes._atajos(reportes._hoy())}

    def _compute_periodo_atajo(self):
        # Solo se usa para buscar: el valor de un registro no es una sola opción (puede tocar varias).
        self.periodo_atajo = False

    @api.model
    def _search_periodo_atajo(self, operator, value):
        if operator not in ('=', 'in'):
            raise UserError(self.env._('Este filtro solo elige uno o varios atajos de fechas.'))
        claves = [value] if operator == '=' else list(value or [])
        ventanas = self._dcasa_ventanas()
        desde, hasta = self._dcasa_campos_periodo
        partes = [Domain(desde, '<=', ventanas[c][1]) & Domain(hasta, '>=', ventanas[c][0])
                  for c in claves if c in ventanas]
        return Domain.OR(partes) if partes else Domain.FALSE

    @api.onchange('atajo_fechas')
    def _onchange_atajo_fechas(self):
        if not self.atajo_fechas:
            return
        desde, hasta = self._dcasa_ventanas()[self.atajo_fechas]
        campo_desde, campo_hasta = self._dcasa_campos_periodo
        self[campo_desde], self[campo_hasta] = desde, hasta
