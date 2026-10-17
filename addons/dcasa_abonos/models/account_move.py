from odoo import models
from odoo.addons.dcasa_invoice.models import lineas

from . import condiciones


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------------
    # Condiciones de abono: solo lee (la factura, sus pagos y sus asientos no cambian)
    # ------------------------------------------------------------------------

    def _dcasa_abonos_registrados(self):
        """Los pagos de verdad conciliados con la factura (sin notas de crédito ni diferencias de cambio)."""
        self.ensure_one()
        return [pago for pago in self._dcasa_pagos() if not pago.get('is_refund')]

    def _dcasa_condiciones_motivo(self):
        """'' si de esta factura se pueden imprimir las condiciones de abono; si no, por qué (para el mensaje)."""
        self.ensure_one()
        if self.move_type != 'out_invoice' or self.state != 'posted':
            return self.env._('%(factura)s no es una factura de cliente publicada.', factura=self.display_name)
        if not self._dcasa_abonos_registrados():
            return self.env._('%(factura)s todavía no tiene ningún abono registrado con «Pagar».',
                              factura=self.display_name)
        return ''

    def _dcasa_condiciones_imprimible(self):
        """True si la factura puede llevar la hoja: factura de cliente publicada, con al menos un abono y con
        condiciones escritas en su empresa."""
        self.ensure_one()
        return not self._dcasa_condiciones_motivo() and bool(self.company_id._dcasa_abono_condiciones_lista())

    def _dcasa_primer_abono(self):
        """True si la factura está en su PRIMER abono: un solo pago y todavía con saldo."""
        self.ensure_one()
        return self._dcasa_es_abono() and len(self._dcasa_abonos_registrados()) == 1

    def _dcasa_condiciones_muebles(self):
        """Los muebles de la factura para la hoja: [{'codigo_publico', 'referencia', 'descripcion',
        'descripcion_cliente', 'cantidad'}].

        Fuera el flete y los servicios (si la factura no tiene nada más, van ellos) y las líneas en negativo (rebajas,
        premios): no son artículos abonados. ``codigo_publico`` es el DC-… que ve el cliente; ``referencia``, la del
        proveedor (solo para la copia de la empresa); ``descripcion_cliente`` no la repite.
        """
        self.ensure_one()
        productos = self.invoice_line_ids.filtered(
            lambda linea: linea.display_type == 'product' and linea.price_subtotal >= 0)
        muebles = productos.filtered(lambda linea: not linea._dcasa_va_aparte()) or productos
        resultado = []
        for linea in muebles:
            referencia, descripcion = lineas.codigo_y_descripcion(linea.name, linea.product_id.default_code)
            resultado.append({
                'codigo_publico': linea.product_id.dcasa_codigo_publico or '',
                'referencia': referencia,
                'descripcion': descripcion,
                'descripcion_cliente': condiciones.sin_referencia(descripcion, referencia),
                'cantidad': linea.quantity,
            })
        return resultado

    def _dcasa_condiciones_hoja(self):
        """Lo que pinta cada copia para caber en UNA hoja carta: ``{'muebles', 'faltan', 'escala'}``.

        ``muebles``: los de ``_dcasa_condiciones_muebles`` que se listan (todos, salvo una factura enorme); ``faltan``:
        cuántos quedan fuera (la hoja lo dice); ``escala``: 1, o menos si hay que achicar la tabla de los muebles
        (``condiciones.ajuste_a_una_hoja``; las condiciones nunca se achican). Las dos copias usan la misma, calculada
        con la descripción completa de la copia de la empresa (la más angosta).
        """
        self.ensure_one()
        muebles = self._dcasa_condiciones_muebles()
        escala, cuantos = condiciones.ajuste_a_una_hoja(
            [mueble['descripcion'] for mueble in muebles], self.company_id._dcasa_abono_condiciones_lista())
        return {'muebles': muebles[:cuantos], 'faltan': len(muebles) - cuantos, 'escala': escala}
