"""Sitio web › Busca con una foto: el interruptor, los topes y cuántas búsquedas hubo (Gerencia y administradores).

Una pantalla propia (como la de Ajustes del programa de vendedores): Gerencia no entra a los Ajustes de Odoo. Los
valores viven en ``ir.config_parameter`` (``dcasa_buscar_foto.*``); al guardar, ``execute`` vuelve a comprobar
el grupo en el servidor ANTES del ``sudo()`` y avisa al borde para que las páginas guardadas (con o sin la cámara) se
vuelvan a armar.
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .buscar_foto import PARAM_ACTIVO, PARAM_TOPES, TOPES_DE_FABRICA

GRUPOS = ('dcasa_base.group_gerencia', 'base.group_system')
MAX_TOPE = 10000


def _tope(clave):
    def leer(self):
        return self.env['dcasa.buscar.foto']._dcasa_topes()[clave]
    return leer


class DcasaBuscarFotoAjustes(models.TransientModel):
    _name = 'dcasa.buscar.foto.ajustes'
    _description = 'Busca con una foto: ajustes'

    activo = fields.Boolean(
        'Busca con una foto en la tienda', default=lambda self: self.env['dcasa.buscar.foto']._dcasa_activa(),
        help='Encendido: sale el botón de la cámara en la búsqueda del sitio y en la tienda. Apagado: no sale.')
    tope_visitante_hora = fields.Integer(
        'Por visitante, en una hora', default=_tope('visitante'),
        help=f'Cuántas fotos puede buscar una misma persona en una hora. De fábrica: {TOPES_DE_FABRICA["visitante"]}.')
    tope_conexion_hora = fields.Integer(
        'Por conexión a internet, en una hora', default=_tope('conexion'),
        help='Varios teléfonos pueden salir por la misma conexión (la del operador o el wifi de un lugar): por eso es '
             f'más alto. De fábrica: {TOPES_DE_FABRICA["conexion"]}.')
    tope_dia = fields.Integer(
        'En total, por día', default=_tope('dia'),
        help=f'Entre todos los visitantes, en el día (hora de Panamá). De fábrica: {TOPES_DE_FABRICA["dia"]}.')

    busquedas_hoy = fields.Integer('Hoy', compute='_compute_uso')
    busquedas_mes = fields.Integer('Últimos 30 días', compute='_compute_uso')
    con_resultado_mes = fields.Integer('Encontraron productos', compute='_compute_uso')
    sin_resultado_mes = fields.Integer('No encontraron nada parecido', compute='_compute_uso')
    documentos_mes = fields.Integer('Parecían un documento', compute='_compute_uso')
    no_leidas_mes = fields.Integer('No se pudieron leer', compute='_compute_uso')

    def _compute_uso(self):
        Uso = self.env['dcasa.buscar.foto.uso'].sudo()
        hoy = self.env['dcasa.buscar.foto']._dcasa_inicio_del_dia()
        hace_un_mes = fields.Datetime.now() - timedelta(days=30)
        cuantos = dict(Uso._read_group([('fecha', '>=', hace_un_mes)], ['resultado'], ['__count']))
        busquedas_hoy = Uso.search_count([('fecha', '>=', hoy)])
        for ajustes in self:
            ajustes.busquedas_hoy = busquedas_hoy
            ajustes.busquedas_mes = sum(cuantos.values())
            ajustes.con_resultado_mes = cuantos.get('resultados', 0)
            ajustes.sin_resultado_mes = cuantos.get('nada', 0) + cuantos.get('otra', 0)
            ajustes.documentos_mes = cuantos.get('documento', 0)
            ajustes.no_leidas_mes = cuantos.get('no_ahora', 0)

    @api.model
    def _dcasa_exigir(self):
        if not any(self.env.user.has_group(grupo) for grupo in GRUPOS):
            raise AccessError(self.env._('Solo Gerencia y los administradores cambian «Busca con una foto».'))

    def execute(self):
        """Botón «Guardar»: interruptor y topes. Exige Gerencia o administrador en el servidor antes del ``sudo()``."""
        self._dcasa_exigir()
        self.ensure_one()
        for nombre in ('tope_visitante_hora', 'tope_conexion_hora', 'tope_dia'):
            if not 0 <= self[nombre] <= MAX_TOPE:
                raise UserError(self.env._('Cada tope va de 0 a %s (0 = nadie puede buscar).', MAX_TOPE))
        Parametro = self.env['ir.config_parameter'].sudo()
        cambia_la_pagina = bool(self.activo) != self.env['dcasa.buscar.foto']._dcasa_activa()
        Parametro.set_param(PARAM_ACTIVO, 'True' if self.activo else 'False')
        Parametro.set_param(PARAM_TOPES['visitante'], str(self.tope_visitante_hora))
        Parametro.set_param(PARAM_TOPES['conexion'], str(self.tope_conexion_hora))
        Parametro.set_param(PARAM_TOPES['dia'], str(self.tope_dia))
        if cambia_la_pagina and 'dcasa.tienda.pendiente' in self.env:
            # La cámara está en todas las páginas (la búsqueda de la cabecera): las guardadas en el borde se rehacen.
            self.env['dcasa.tienda.pendiente']._dcasa_marcar([0], 'busca con una foto')
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def cancel(self):
        """Botón «Descartar»: vuelve a abrir la pantalla con lo que rige."""
        return self.env['ir.actions.act_window']._for_xml_id('dcasa_buscar_foto.action_dcasa_buscar_foto_ajustes')

    def _compute_display_name(self):
        for ajustes in self:
            ajustes.display_name = self.env._('Busca con una foto')
