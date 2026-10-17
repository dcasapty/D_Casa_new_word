"""Brian también manda por correo la factura o la cotización (docs/LEEME_PRIMERO.md §4: todo lo nuevo, Brian lo usa)."""
from odoo import models
from odoo.addons.dcasa_brian.models.herramientas_contabilidad import FACTURACION, PARAM_FACTURA
from odoo.addons.dcasa_brian.models.herramientas_ventas import PARAM_VENTA
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.exceptions import UserError

VENTAS = ('sales_team.group_sale_salesman',)


class BrianHerramientasCorreo(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @herramienta(
        nombre='enviar_factura_por_correo',
        descripcion="Le manda al cliente su factura publicada en PDF por correo, con la marca de D'CASA. Si todavía "
                    'debe algo, sale como abono: lo que pagó, lo que le falta y hasta cuándo.',
        parametros={'factura': PARAM_FACTURA}, requeridos=['factura'],
        nivel='construccion', categoria='contabilidad', grupos=FACTURACION,
        ejemplos=['mándale por correo la factura INV/2026/00012', 'envíale a Ana su factura por correo'],
    )
    def _h_enviar_factura_por_correo(self, factura):
        movimiento = self._b_factura(factura, dominio=[('move_type', '=', 'out_invoice')])
        try:
            envio = movimiento._dcasa_correo_enviar_factura()
        except UserError as error:
            raise BrianError(error.args[0] if error.args else str(error)) from None
        return {'mensaje': f'Listo: la factura {movimiento.name} sale por correo en unos minutos, con su PDF.',
                'correo_a': movimiento._dcasa_correo_destino().email_normalized or '',
                'tipo': envio.tipo}

    @herramienta(
        nombre='enviar_cotizacion_por_correo',
        descripcion="Le manda al cliente la cotización (borrador o enviada) en PDF por correo, con la marca de "
                    "D'CASA. Si estaba en borrador, pasa a «Enviada»; no se confirma.",
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENTAS,
        ejemplos=['mándale la cotización S00012 por correo'],
    )
    def _h_enviar_cotizacion_por_correo(self, venta):
        orden = self._b_venta(venta)
        try:
            envio = orden._dcasa_correo_enviar_cotizacion()
        except UserError as error:
            raise BrianError(error.args[0] if error.args else str(error)) from None
        return {'mensaje': f'Listo: la cotización {orden.name} sale por correo en unos minutos, con su PDF.',
                'correo_a': envio.correo or '', 'estado': orden.state}
