from odoo import models

from . import lineas


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _dcasa_codigo(self):
        self.ensure_one()
        return lineas.codigo_y_descripcion(self.name, self.product_id.default_code)[0]

    def _dcasa_descripcion(self):
        """La descripción sin el código delante ni detrás (el código tiene su columna)."""
        self.ensure_one()
        return lineas.codigo_y_descripcion(self.name, self.product_id.default_code)[1]

    def _dcasa_es_servicio(self):
        self.ensure_one()
        return lineas.es_servicio(self.product_id)

    def _dcasa_es_flete(self):
        self.ensure_one()
        return lineas.es_flete(self.product_id)

    def _dcasa_va_aparte(self):
        """True si la línea se imprime en el bloque de flete y servicios. Otros módulos lo afinan."""
        self.ensure_one()
        return lineas.es_servicio(self.product_id)

    def _dcasa_impuestos(self):
        self.ensure_one()
        return lineas.etiqueta_impuestos(self.tax_ids)

    def _dcasa_etiqueta(self):
        """Un distintivo corto junto a la descripción («Premio Socios D'CASA»). Otros módulos lo llenan."""
        self.ensure_one()
        return ''
