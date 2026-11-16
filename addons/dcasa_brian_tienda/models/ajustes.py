"""Sitio web › Brian de la tienda: el interruptor, el presupuesto del mes, los topes, el gasto y las calificaciones.

Pantalla propia (como «Busca con una foto» y los ajustes del programa de vendedores): Gerencia no entra a los Ajustes
de Odoo. Los valores viven en ``ir.config_parameter`` (``dcasa_brian_tienda.*``) y llegan al Worker en
``GET /dcasa/juan/v1/config`` (clave ``brian_tienda``). Al guardar, ``execute`` comprueba el grupo en el servidor ANTES
del ``sudo()`` y, si cambió el interruptor, avisa al borde (la burbuja está en todas las páginas guardadas).
"""
from datetime import datetime

from odoo import api, fields, models
from odoo.addons.dcasa_conversaciones.models import publico as P
from odoo.exceptions import AccessError, UserError

from .juan import tienda_de_costos
from .pase import MAXIMOS, PARAM_ACTIVO, PARAM_AVISAR_CERRADO, PARAM_DORMIR_DE_NOCHE, PARAMS

GRUPOS = ('dcasa_base.group_gerencia', 'base.group_system')
CAMPOS = ('presupuesto_mes_usd', 'tope_sesion_hora', 'tope_red_hora', 'tope_dia', 'tope_pases_red_hora')


def _de_fabrica(clave):
    def leer(self):
        return self.env['dcasa.brian.tienda']._ajustes()[clave]
    return leer


class DcasaBrianTiendaAjustes(models.TransientModel):
    _name = 'dcasa.brian.tienda.ajustes'
    _description = 'Andrés (chat de la tienda): ajustes'

    activo = fields.Boolean(
        'Andrés en el sitio', default=lambda self: self.env['dcasa.brian.tienda']._activo(),
        help='Encendido: en el sitio sale la burbuja de Andrés en lugar de la de WhatsApp. Apagado: vuelve la de '
             'WhatsApp y Andrés no contesta.')
    avisar_cerrado = fields.Boolean(
        'Fuera del horario, avisar que la tienda está cerrada',
        default=lambda self: self.env['dcasa.brian.tienda']._avisar_cerrado(),
        help='Encendido: de noche, Andrés saluda diciendo que la tienda está cerrada y que una vendedora responde por '
             'WhatsApp en cuanto abran. Apagado (de fábrica): Andrés siempre saluda como de día y ayuda igual.')
    dormir_de_noche = fields.Boolean(
        'De noche, el robot de la burbuja duerme',
        default=lambda self: self.env['dcasa.brian.tienda']._dormir_de_noche(),
        help='Encendido (de fábrica): fuera del horario el robot de la burbuja duerme. Apagado: de noche la burbuja se '
             'porta como de día (cambia con la página y al bajar).')
    presupuesto_mes_usd = fields.Integer('Presupuesto del mes (USD)', default=_de_fabrica('presupuesto_mes_usd'))
    tope_sesion_hora = fields.Integer('Mensajes por visitante, en una hora', default=_de_fabrica('tope_sesion_hora'))
    tope_red_hora = fields.Integer('Mensajes por conexión a internet, en una hora',
                                   default=_de_fabrica('tope_red_hora'))
    tope_dia = fields.Integer('Mensajes en total, por día', default=_de_fabrica('tope_dia'))
    tope_pases_red_hora = fields.Integer('Chats nuevos por conexión, en una hora',
                                         default=_de_fabrica('tope_pases_red_hora'))

    gasto_mes = fields.Char('Gasto del mes', compute='_compute_gasto')
    calificaciones_mes = fields.Integer('Calificaciones del mes', compute='_compute_calificaciones')
    promedio_mes = fields.Char('Promedio del mes', compute='_compute_calificaciones')

    def _compute_gasto(self):
        texto = self.env._('Sin dato: el Worker de Juan no lo dijo (revisa Conexiones).')
        Cliente = self.env['dcasa.juan.cliente'].sudo()
        if Cliente.configurado():
            respuesta = Cliente.costos()
            if respuesta['conectado'] and not respuesta['error']:
                tienda = tienda_de_costos(respuesta['cuerpo'])
                if not tienda['sin_dato']:
                    texto = self.env._('%(gasto)s en %(turnos)s respuestas', gasto=P.precio_texto(tienda['usd'], False),
                                       turnos=tienda['turnos'])
        for ajustes in self:
            ajustes.gasto_mes = texto

    def _compute_calificaciones(self):
        hoy = fields.Date.context_today(self)
        resumen = self.env['dcasa.brian.tienda.calificacion'].sudo()._resumen(datetime(hoy.year, hoy.month, 1))
        promedio = (f"{str(resumen['promedio']).replace('.', ',')} de 5" if resumen['promedio'] is not None
                    else self.env._('Todavía ninguna'))
        for ajustes in self:
            ajustes.calificaciones_mes = resumen['cantidad']
            ajustes.promedio_mes = promedio

    @api.model
    def _dcasa_exigir(self):
        if not any(self.env.user.has_group(grupo) for grupo in GRUPOS):
            raise AccessError(self.env._('Solo Gerencia y los administradores cambian a Andrés, el chat de la tienda.'))

    def execute(self):
        """Botón «Guardar». Exige Gerencia o administrador en el servidor antes del ``sudo()``."""
        self._dcasa_exigir()
        self.ensure_one()
        for campo in CAMPOS:
            if not 0 <= self[campo] <= MAXIMOS[campo]:
                raise UserError(self.env._('«%(campo)s» va de 0 a %(maximo)s.', campo=self._fields[campo].string,
                                           maximo=MAXIMOS[campo]))
        Parametro = self.env['ir.config_parameter'].sudo()
        Tienda = self.env['dcasa.brian.tienda']
        # La burbuja y si el robot duerme van en el HTML de todas las páginas: si cambian, el borde las rehace.
        cambia_la_pagina = (bool(self.activo) != Tienda._activo()
                            or bool(self.dormir_de_noche) != Tienda._dormir_de_noche())
        Parametro.set_param(PARAM_ACTIVO, 'True' if self.activo else 'False')
        Parametro.set_param(PARAM_AVISAR_CERRADO, 'True' if self.avisar_cerrado else 'False')
        Parametro.set_param(PARAM_DORMIR_DE_NOCHE, 'True' if self.dormir_de_noche else 'False')
        for campo in CAMPOS:
            Parametro.set_param(PARAMS[campo], str(self[campo]))
        if cambia_la_pagina and 'dcasa.tienda.pendiente' in self.env:
            # La burbuja (o la de WhatsApp) está en todas las páginas: las guardadas en el borde se rehacen (las que
            # Odoo guarda una hora, ``website.page``, ya se olvidan con ``set_param``).
            self.env['dcasa.tienda.pendiente']._dcasa_marcar([0], 'brian de la tienda')
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def cancel(self):
        """Botón «Descartar»: vuelve a abrir la pantalla con lo que rige."""
        return self.env['ir.actions.act_window']._for_xml_id('dcasa_brian_tienda.action_dcasa_brian_tienda_ajustes')

    def _compute_display_name(self):
        for ajustes in self:
            ajustes.display_name = self.env._('Andrés, el chat de la tienda')
