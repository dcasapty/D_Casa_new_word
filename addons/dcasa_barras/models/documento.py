"""El QR de la nota de entrega abre la entrega en el panel de Bodega (decisión de la dueña, 2026-10-22).

Con la cámara normal del teléfono (``/dcasa/doc/ENT/…`` redirige a ``/odoo/bodega/<id>``) y desde el Escáner: para
quien usa Inventario y si es una salida a un cliente (pendiente o ya hecha: la hecha se ve sin poder validarla). Quien
no usa Inventario, o una recepción, siguen abriendo el formulario de Odoo como siempre. El permiso de ver el documento
ya lo comprobó ``dcasa.documento`` antes de llegar aquí; el panel vuelve a exigir Inventario y que haya pago o abono.
"""
from odoo import models


class DcasaDocumento(models.AbstractModel):
    _inherit = 'dcasa.documento'

    def _dcasa_va_a_bodega(self, registro):
        return (registro._name == 'stock.picking' and registro.picking_type_code == 'outgoing'
                and self.env.user.has_group('stock.group_stock_user')
                and bool(self.env.ref('dcasa_barras.accion_bodega', raise_if_not_found=False)))

    def _dcasa_ruta_odoo(self, registro):
        if self._dcasa_va_a_bodega(registro):
            return f'/odoo/bodega/{registro.id}'
        return super()._dcasa_ruta_odoo(registro)

    def _dcasa_accion_documento(self, registro):
        if self._dcasa_va_a_bodega(registro):
            accion = self.env['ir.actions.actions']._for_xml_id('dcasa_barras.accion_bodega')
            accion['params'] = {'entrega_id': registro.id}
            return accion
        return super()._dcasa_accion_documento(registro)
