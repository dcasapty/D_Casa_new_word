"""Cada cambio del código de barras de un producto queda en el historial de etiquetas, venga de donde venga.

Sin esto el historial solo vería lo que se hace desde el Escáner › Asignar: si alguien borra o cambia el código en la
ficha del producto, o se aplica la asignación desde la referencia, o se elimina el producto, la etiqueta quedaría
«libre» en vez de «retirada» y escanearla diría «no existe». No cambia permisos ni valores: solo anota.

El Escáner pasa el motivo por el contexto (``dcasa_etiqueta_retiro`` y ``dcasa_etiqueta_alta``).
"""
from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        if 'barcode' not in vals:
            return super().write(vals)
        antes = {producto.id: producto.barcode or '' for producto in self}
        resultado = super().write(vals)
        contexto = self.env.context
        barras = self.env['dcasa.barras']
        for producto in self:
            viejo, nuevo = antes[producto.id], producto.barcode or ''
            if viejo.upper() == nuevo.upper():
                continue
            if viejo:
                barras._anotar_etiqueta(
                    viejo, 'retirada', producto,
                    contexto.get('dcasa_etiqueta_retiro') or self.env._("Cambiada en la ficha del producto"))
            if nuevo:
                barras._anotar_etiqueta(nuevo, 'asignada', producto, contexto.get('dcasa_etiqueta_alta') or '')
        return resultado

    def unlink(self):
        barras = self.env['dcasa.barras']
        for producto in self.filtered('barcode'):
            barras._anotar_etiqueta(producto.barcode, 'retirada', producto, self.env._("El producto se eliminó"))
        return super().unlink()
