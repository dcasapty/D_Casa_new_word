"""La nota de entrega con el código público (solo con el interruptor de la empresa encendido; apagado, todo igual).

La nota de entrega imprime el nombre de cada producto («[referencia] Nombre») y, debajo, la descripción de la entrega
que Odoo guardó al crearla, que casi siempre es ese mismo nombre con la referencia del proveedor. Con el interruptor
encendido ``o`` se arma con el contexto ``dcasa_codigo_publico``: el nombre sale con el código público y la descripción
se limpia de la referencia del proveedor, así esta nunca aparece en el papel.
"""
from odoo import models

from . import lineas
from .producto import CLAVE_CONTEXTO


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _dcasa_para_imprimir(self):
        """La entrega tal como se imprime: con el código público en vez de la referencia, si la empresa lo pide."""
        self.ensure_one()
        if self.company_id.dcasa_mostrar_codigo_publico:
            return self.with_context(**{CLAVE_CONTEXTO: True, 'display_default_code': False})
        return self


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_report_description_picking(self):
        """La descripción de la entrega sin repetir el nombre; con el código público activo, sin la referencia."""
        if not self.env.context.get(CLAVE_CONTEXTO):
            return super()._get_report_description_picking()
        self.ensure_one()
        descripcion = lineas.quitar_referencia_delante(self.description_picking, self.product_id.default_code)
        nombre = self.product_id.name or ''
        if nombre and descripcion.startswith(nombre):
            descripcion = descripcion.removeprefix(nombre).strip()
        return descripcion


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _get_aggregated_properties(self, move_line=False, move=False):
        propiedades = super()._get_aggregated_properties(move_line=move_line, move=move)
        if self.env.context.get(CLAVE_CONTEXTO):
            propiedades['description'] = (move or move_line.move_id)._get_report_description_picking()
        return propiedades
