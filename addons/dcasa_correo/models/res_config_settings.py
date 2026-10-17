"""Ajustes › Correo a clientes. No existe ningún campo para la clave de Resend: vive solo en el servidor."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .correo import (
    NOMBRE,
    P_A_CLIENTES,
    P_AL_PAGAR,
    P_BIENVENIDA,
    P_NOMBRE,
    P_REMITENTE,
    P_RESPONDER_A,
    REMITENTE,
    RESPONDER_A,
    correo_valido,
)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_correo_remitente = fields.Char(
        'Remitente', config_parameter=P_REMITENTE, default=REMITENTE,
        help='La dirección desde la que salen los correos. Tiene que ser del dominio verificado en Resend; no '
             'necesita buzón.')
    dcasa_correo_nombre = fields.Char('Nombre del remitente', config_parameter=P_NOMBRE, default=NOMBRE)
    dcasa_correo_responder_a = fields.Char(
        'Las respuestas llegan a', config_parameter=P_RESPONDER_A, default=RESPONDER_A,
        help='Si el cliente contesta el correo, la respuesta llega aquí.')
    dcasa_correo_a_clientes = fields.Boolean(
        'Enviar correos a clientes', config_parameter=P_A_CLIENTES,
        help='Apagado (así viene): no sale ningún correo a clientes. El correo de prueba sí sale, solo al equipo.')
    dcasa_correo_al_pagar = fields.Boolean(
        'Mandar la factura al registrar un pago', config_parameter=P_AL_PAGAR,
        help='En cuanto se registra un pago, al cliente le llega su factura en PDF (si queda saldo, como abono).')
    dcasa_correo_bienvenida = fields.Boolean(
        'Bienvenida a clientes nuevos', config_parameter=P_BIENVENIDA,
        help='Una sola vez, cuando ya puede entrar a Mi cuenta (con su primera compra pagada): cómo entrar a ver sus '
             'compras, sus pagos y sus puntos. Solo a clientes creados desde que se instaló el correo; a los de antes '
             'no se les manda.')
    dcasa_correo_estado = fields.Char('Estado del correo', compute='_compute_dcasa_correo_estado')
    dcasa_correo_bienvenida_desde = fields.Char('Clientes nuevos desde', compute='_compute_dcasa_correo_estado')

    def _compute_dcasa_correo_estado(self):
        correo = self.env['dcasa.correo'].sudo()
        estado = correo._estado()
        desde = correo._bienvenida_desde()
        texto_desde = fields.Datetime.context_timestamp(self, desde).strftime('%d/%m/%Y') if desde else ''
        for ajustes in self:
            ajustes.dcasa_correo_estado = estado
            ajustes.dcasa_correo_bienvenida_desde = texto_desde

    @api.constrains('dcasa_correo_remitente', 'dcasa_correo_responder_a')
    def _check_dcasa_correo_direcciones(self):
        for ajustes in self:
            for direccion in (ajustes.dcasa_correo_remitente, ajustes.dcasa_correo_responder_a):
                if direccion and not correo_valido(direccion):
                    raise ValidationError(self.env._(
                        '«%s» no es un correo completo. Debe verse así: ventas@dcasapty.com.', direccion))

    def action_dcasa_correo_prueba(self):
        """Guarda los ajustes y manda un correo de prueba a quien pulsa el botón (solo administradores)."""
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Solo un administrador manda el correo de prueba.'))
        if self:
            self.ensure_one()
            self.set_values()
        destino = self.env['dcasa.correo'].sudo()._enviar_prueba(self.env.user)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Correo de prueba'),
                'message': self.env._('Listo: Resend lo recibió para %s. Revisa la bandeja de entrada (y la de spam).',
                                      destino),
                'type': 'success',
                'sticky': False,
            },
        }
