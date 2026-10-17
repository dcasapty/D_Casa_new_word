"""El interruptor «Cada vendedora ve solo sus documentos» (pedido de la dueña, 2026-10-17).

La dueña: «así como está funciona bien, pero lo que queremos implementar es una restricción, así que si el día de
mañana esto genera algún problema operativo se puede retroceder fácilmente». Viene encendido. Apagado, todas las
vendedoras vuelven a ver todo como antes, sin tocar a ninguna persona (``res.users._dcasa_poner_restriccion``).

Está en dos pantallas con el mismo dato:

* Ajustes › Ventas (``res.config.settings``): los administradores.
* Ventas › Configuración › Permisos de las vendedoras (``dcasa.permisos.vendedoras``): Gerencia, que no entra a los
  Ajustes de Odoo y así solo ve este interruptor.

Las dos llaman a ``_dcasa_poner_restriccion``, que vuelve a comprobar el permiso en el servidor: nada que llegue del
navegador es de confianza.
"""
from odoo import api, fields, models

ETIQUETA = 'Cada vendedora ve solo sus documentos'
AYUDA = ('Encendido: cada vendedora ve solo sus cotizaciones, pedidos, facturas, notas de crédito y cobros, y los que '
         'no tienen vendedora (para que alguien los atienda). Caja y Gerencia ven todo. Apagado: todas ven todo, como '
         'antes. Vale al momento y no cambia el rol de nadie.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_solo_lo_suyo = fields.Boolean(ETIQUETA, help=AYUDA)

    @api.model
    def get_values(self):
        valores = super().get_values()
        valores['dcasa_solo_lo_suyo'] = self.env['res.users']._dcasa_restriccion_activa()
        return valores

    def set_values(self):
        super().set_values()
        for ajustes in self:
            # Sin cambio no hace nada (ni pide permiso): guardar otro ajuste no lo toca.
            if ajustes.dcasa_solo_lo_suyo != self.env['res.users']._dcasa_restriccion_activa():
                self.env['res.users']._dcasa_poner_restriccion(ajustes.dcasa_solo_lo_suyo)


class DcasaPermisosVendedoras(models.TransientModel):
    _name = 'dcasa.permisos.vendedoras'
    _description = 'Qué documentos ve cada vendedora'

    solo_lo_suyo = fields.Boolean(
        ETIQUETA, help=AYUDA, default=lambda self: self.env['res.users']._dcasa_restriccion_activa())

    def action_guardar(self):
        """Botón «Guardar»: el permiso lo comprueba ``_dcasa_poner_restriccion`` (Gerencia o administrador)."""
        self.ensure_one()
        cambio = self.env['res.users']._dcasa_poner_restriccion(self.solo_lo_suyo)
        if not cambio:
            mensaje = self.env._('No cambió nada.')
        elif self.solo_lo_suyo:
            mensaje = self.env._('Listo: cada vendedora ve solo sus documentos (y los que no tienen vendedora).')
        else:
            mensaje = self.env._('Listo: todas las vendedoras ven todos los documentos, como antes.')
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': mensaje, 'next': {'type': 'ir.actions.act_window_close'}},
        }
