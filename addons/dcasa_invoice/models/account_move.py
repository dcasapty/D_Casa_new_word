from odoo import models

from . import formato


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------------
    # Pago: un bloque sobrio y verídico, no un sello de goma
    # ------------------------------------------------------------------------

    def _dcasa_is_paid(self):
        """True si la factura está saldada (pagada o en proceso de pago)."""
        self.ensure_one()
        return self.is_invoice(include_receipts=True) and self.payment_state in ('paid', 'in_payment')

    def _dcasa_pagos(self):
        """Los pagos conciliados con la factura (sin diferencias de cambio)."""
        self.ensure_one()
        widget = self.sudo().invoice_payments_widget or {}
        return [pago for pago in widget.get('content', []) if not pago.get('is_exchange')]

    def _dcasa_last_payment_date(self):
        """Fecha del último pago conciliado."""
        self.ensure_one()
        fechas = [pago['date'] for pago in self._dcasa_pagos() if pago.get('date')]
        return max(fechas) if fechas else False

    def _dcasa_formas_de_pago(self):
        """Los diarios con que se pagó («Efectivo», «Banco General»…), sin repetir."""
        self.ensure_one()
        nombres = []
        for pago in self._dcasa_pagos():
            nombre = pago.get('journal_name')
            if nombre and nombre not in nombres:
                nombres.append(nombre)
        return ' y '.join(nombres)

    def _dcasa_pagado(self):
        self.ensure_one()
        return self.currency_id.round(self.amount_total - self.amount_residual)

    @staticmethod
    def _dcasa_fecha(fecha):
        return fecha.strftime('%d/%m/%Y') if fecha else ''

    # ------------------------------------------------------------------------
    # Textos del documento
    # ------------------------------------------------------------------------

    def _dcasa_idioma_factura(self):
        """Las facturas de D'CASA salen en español aunque el contacto tenga otro idioma."""
        self.ensure_one()
        activos = dict(self.env['res.lang'].get_installed())
        return 'es_419' if 'es_419' in activos else self.partner_id.lang

    def _dcasa_monto_en_letras(self):
        self.ensure_one()
        singular, plural = formato.MONEDAS.get(self.currency_id.name, (None, None))
        if not singular:
            return self.amount_total_words
        return formato.monto_en_letras(self.amount_total, singular, plural)

    def _dcasa_precios_con_itbms(self):
        """True si los precios de las líneas ya incluyen el ITBMS (así se venden en la tienda)."""
        self.ensure_one()
        impuestos = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product').tax_ids
        return bool(impuestos) and all(impuesto.price_include for impuesto in impuestos)

    def _dcasa_nota_de_impuesto(self):
        """Lo que aclara las columnas de precio: «con ITBMS», «sin ITBMS» o nada si no hay impuesto."""
        self.ensure_one()
        if not self.invoice_line_ids.tax_ids:
            return ''
        return 'con ITBMS' if self._dcasa_precios_con_itbms() else 'sin ITBMS'

    def _dcasa_narracion(self):
        """Términos y notas con los enlaces apuntando al sitio público, nunca a localhost."""
        self.ensure_one()
        return self.company_id._dcasa_sin_enlaces_locales(self.narration)

    def _dcasa_mostrar_referencia_pago(self):
        """La referencia para pagar sobra en una factura que ya está pagada."""
        self.ensure_one()
        return (self.move_type in ('out_invoice', 'in_refund') and bool(self.payment_reference)
                and not self._dcasa_is_paid())
