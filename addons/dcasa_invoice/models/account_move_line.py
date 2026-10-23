from odoo import models
from odoo.addons.dcasa_base.nombres import nombre_para_cliente

from . import lineas


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _dcasa_codigo(self):
        self.ensure_one()
        codigo = lineas.codigo_y_descripcion(self.name, self.product_id.default_code)[0]
        return lineas.codigo_a_imprimir(self.move_id.company_id, self.product_id, codigo)

    def _compute_name(self):
        """Con «Mostrar el código público…» encendido, el nombre de una línea nueva con producto no lleva la referencia
        del proveedor. Apagado, es el cálculo de Odoo de siempre."""
        sin_referencia = self.filtered(
            lambda linea: linea.product_id and linea.company_id.sudo().dcasa_mostrar_codigo_publico)
        if sin_referencia:
            super(AccountMoveLine, sin_referencia.with_context(display_default_code=False))._compute_name()
        super(AccountMoveLine, self - sin_referencia)._compute_name()

    def _dcasa_descripcion(self):
        """La descripción sin el código delante ni detrás (el código tiene su columna)."""
        self.ensure_one()
        # Va en la factura y la cotización que se lleva el cliente: en formato título (F5).
        return nombre_para_cliente(lineas.codigo_y_descripcion(self.name, self.product_id.default_code)[1])

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

    # ------------------------------------------------------------------------
    # Combos (tipo «Combo» de Odoo): el título de sección y sus piezas
    # ------------------------------------------------------------------------

    def _dcasa_es_titulo_de_combo(self):
        """True si esta línea es el título de sección que Odoo crea en la factura para un combo (su línea de venta es
        la del combo, que no lleva importe: el dinero va en las líneas de sus piezas)."""
        self.ensure_one()
        return self.display_type == 'line_section' and any(
            venta.product_type == 'combo' for venta in self.sale_line_ids)

    def _dcasa_piezas_del_combo(self):
        """Las líneas de la factura que son piezas del combo que abre este título (la cama, el colchón…)."""
        self.ensure_one()
        combos = self.sale_line_ids.filtered(lambda venta: venta.product_type == 'combo')
        return self.move_id.invoice_line_ids.filtered(
            lambda linea: linea.display_type == 'product' and any(
                venta.combo_item_id and venta.linked_line_id in combos for venta in linea.sale_line_ids))

    def get_section_subtotal(self):
        """El subtotal de un título de combo es lo que suman SUS piezas. Odoo suma todo lo que sigue hasta el
        próximo título, y con un combo seguido de otra cosa (el flete, una mesa de noche) el título cobraría de más."""
        if self._dcasa_es_titulo_de_combo():
            return sum(self._dcasa_piezas_del_combo().mapped('price_subtotal'))
        return super().get_section_subtotal()

    def get_section_total(self):
        if self._dcasa_es_titulo_de_combo():
            return sum(self._dcasa_piezas_del_combo().mapped('price_total'))
        return super().get_section_total()
