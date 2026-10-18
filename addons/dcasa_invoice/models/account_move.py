import logging
from datetime import timedelta

from odoo import api, fields, models

from . import formato, lineas

_logger = logging.getLogger(__name__)

# Plazo para terminar de pagar una factura con abonos, en DÍAS CONTINUOS desde el primer abono. Decisión de la gerencia
# (A3, 2026-10-17, docs/DECISIONES_CONTABLES.md): «30 días continuos para completar el pago; ese vencimiento lo ve el
# cliente». 0 = no vence (no se imprime ni se muestra vencimiento). Antes era ``dcasa_invoice.abono_meses`` («un mes»):
# la migración 19.0.2.4.0 lo pasa a días y lo borra.
PARAMETRO_DIAS_ABONO = 'dcasa_invoice.abono_dias'
DIAS_ABONO_POR_DEFECTO = 30
PARAMETRO_MESES_VIEJO = 'dcasa_invoice.abono_meses'
# El primer abono (la factura todavía sin pagos) es al menos la mitad del total (A3). Menos, solo Gerencia.
ANTICIPO_MINIMO = 0.5


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

    def _dcasa_abonos(self):
        """Cada pago, para imprimirlo: {'fecha', 'medio', 'monto', 'es_reverso'}, del más viejo al más nuevo."""
        self.ensure_one()
        abonos = []
        def orden(pago):
            return (pago.get('date') or self.invoice_date, pago.get('partial_id') or 0)

        for pago in sorted(self._dcasa_pagos(), key=orden):
            medio = pago.get('journal_name') or ''
            metodo = pago.get('payment_method_name') or ''
            # «Manual» / «Manual Payment» es el método genérico de Odoo: no le dice nada al cliente.
            if metodo and not metodo.lower().startswith('manual') and metodo.lower() != medio.lower():
                medio = f'{medio} · {metodo}' if medio else metodo
            abonos.append({
                'fecha': self._dcasa_fecha(pago.get('date')),
                'medio': medio,
                'monto': pago.get('amount') or 0.0,
                'es_reverso': bool(pago.get('is_refund')),
            })
        return abonos

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

    # ------------------------------------------------------------------------
    # Abonos: el cliente paga por partes la misma factura (nada cambia en la contabilidad)
    # ------------------------------------------------------------------------

    def _dcasa_es_abono(self):
        """Factura de cliente publicada con algo pagado y algo por pagar: se imprime como ABONO."""
        self.ensure_one()
        return self.move_type == 'out_invoice' and self.state == 'posted' and self.payment_state == 'partial'

    def _dcasa_dias_abono(self):
        """Días continuos para terminar de pagar un abono (``dcasa_invoice.abono_dias``; 30 de fábrica, 0 = no vence).
        Un valor que no es un número entero vale lo de fábrica (y queda en el registro)."""
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAMETRO_DIAS_ABONO)
        if valor in (None, False, ''):
            return DIAS_ABONO_POR_DEFECTO
        try:
            return max(int(str(valor).strip()), 0)
        except (TypeError, ValueError):
            _logger.warning('DCASA_ABONO el parámetro %s no es un número de días (%r): se usan %s.',
                            PARAMETRO_DIAS_ABONO, valor, DIAS_ABONO_POR_DEFECTO)
            return DIAS_ABONO_POR_DEFECTO

    @api.model
    def _dcasa_migrar_plazo_abono(self):
        """Migración 19.0.2.4.0: el plazo del abono pasa de meses (``abono_meses``) a días (``abono_dias``).

        Sin el parámetro viejo no hace nada (vale lo de fábrica: 30 días). Con él, y si todavía no hay días escritos:
        «1» (un mes, lo de antes) pasa a 30 días, la decisión de la gerencia; «0» (alguien lo apagó a mano) sigue sin
        vencer; N meses pasan a N × 30 días; algo que no es un número, a 30. Después borra el parámetro viejo para que
        no queden dos. Se puede repetir. Devuelve los días que quedaron, o ``None`` si no había nada que pasar.
        """
        icp = self.env['ir.config_parameter'].sudo()
        viejo = icp.get_param(PARAMETRO_MESES_VIEJO)
        if viejo in (None, False, ''):
            return None
        dias = icp.get_param(PARAMETRO_DIAS_ABONO)
        if dias in (None, False, ''):
            try:
                meses = max(int(str(viejo).strip()), 0)
            except (TypeError, ValueError):
                meses = None
            dias = DIAS_ABONO_POR_DEFECTO if meses is None else DIAS_ABONO_POR_DEFECTO * meses
            icp.set_param(PARAMETRO_DIAS_ABONO, str(dias))
            _logger.info('DCASA_ABONO plazo del abono: %r mes(es) → %s día(s) continuos.', viejo, dias)
        icp.set_param(PARAMETRO_MESES_VIEJO, False)
        return int(dias)

    def _dcasa_tiene_pagos(self):
        """¿La factura ya tiene algún pago (sin contar las notas de crédito aplicadas)?"""
        self.ensure_one()
        return any(not pago.get('is_refund') for pago in self._dcasa_pagos())

    def _dcasa_minimo_primer_abono(self):
        """Lo mínimo del primer abono: la mitad del total (A3), redondeado a centavos."""
        self.ensure_one()
        return self.currency_id.round(self.amount_total * ANTICIPO_MINIMO)

    def _dcasa_mensaje_primer_abono(self):
        self.ensure_one()
        return self.env._('El primer abono debe ser de al menos la mitad: %s. Si es menos, lo registra Gerencia.',
                          formato.dinero(self._dcasa_minimo_primer_abono()))

    def _dcasa_estado_abono(self):
        """Lo pagado y lo que falta de esta factura, para el papel y para «Mi cuenta» (una sola fuente de cifras).

        ``{'es_abono', 'total', 'pagado', 'saldo', 'abonos', 'inicio', 'vence', 'vencido'}``: ``abonos`` es
        ``_dcasa_abonos()``; ``inicio`` la fecha del primer pago (no cuenta una nota de crédito); ``vence`` = inicio +
        los días de plazo (``_dcasa_dias_abono``: días continuos, también si cambia el mes), solo mientras falte
        pagar. Todo lo que muestra el vencimiento de un abono (el papel de ABONO, las «Condiciones de abono», «Mi
        cuenta», los correos y Brian) sale de aquí. Solo lee: no escribe nada ni toca asientos.
        """
        self.ensure_one()
        fechas = [pago['date'] for pago in self._dcasa_pagos() if pago.get('date') and not pago.get('is_refund')]
        inicio = min(fechas) if fechas else False
        saldo = self.currency_id.round(self.amount_residual) if self.state == 'posted' else self.amount_total
        dias = self._dcasa_dias_abono()
        vence = inicio + timedelta(days=dias) if inicio and dias and saldo > 0 else False
        return {
            'es_abono': self._dcasa_es_abono(),
            'total': self.amount_total,
            'pagado': self._dcasa_pagado() if self.state == 'posted' else 0.0,
            'saldo': saldo,
            'abonos': self._dcasa_abonos() if self.state == 'posted' else [],
            'inicio': inicio,
            'vence': vence,
            'vencido': bool(vence and vence < fields.Date.context_today(self)),
        }

    def _get_report_base_filename(self):
        """El PDF de una factura en abono se llama «Abono INV/…»; el de las demás, como siempre."""
        nombre = super()._get_report_base_filename()
        if len(self) == 1 and self._dcasa_es_abono():
            return f'Abono {nombre}'.strip()
        return nombre

    def _dcasa_mostrar_pagos(self):
        """Los abonos y el saldo se imprimen en toda factura publicada que tenga algún pago."""
        self.ensure_one()
        return (self.is_invoice(include_receipts=True) and self.state == 'posted'
                and bool(self._dcasa_pagos()))

    @staticmethod
    def _dcasa_fecha(fecha):
        return fecha.strftime('%d/%m/%Y') if fecha else ''

    # ------------------------------------------------------------------------
    # Cabecera: cliente, entrega y datos del documento
    # ------------------------------------------------------------------------

    def _dcasa_entrega(self):
        """La dirección de entrega, solo si no es la misma del cliente."""
        self.ensure_one()
        entrega = self.partner_shipping_id
        return entrega if entrega and entrega != self.partner_id else self.env['res.partner']

    def _dcasa_medio_de_pago(self):
        """Con qué se pagó; si aún no se pagó, el medio previsto (si se anotó)."""
        self.ensure_one()
        return self._dcasa_formas_de_pago() or self.preferred_payment_method_line_id.name or ''

    def _dcasa_mostrar_vencimiento(self):
        self.ensure_one()
        return bool(self.invoice_date_due and self.move_type == 'out_invoice' and self.state == 'posted'
                    and not self._dcasa_is_paid())

    def _dcasa_fechas_de_pago(self):
        """[(etiqueta, valor)] de cuándo hay que pagar, para la columna de datos.

        En una factura en abono no manda la condición de pago sino el plazo del abono (``_dcasa_estado_abono``):
        «Inicio del abono» (el primer pago) y «El abono vence». En las demás, «Vence» como siempre.
        """
        self.ensure_one()
        if self._dcasa_es_abono():
            estado = self._dcasa_estado_abono()
            return [('Inicio del abono', self._dcasa_fecha(estado['inicio'])),
                    ('El abono vence', self._dcasa_fecha(estado['vence']))]
        return [('Vence', self._dcasa_fecha(self.invoice_date_due) if self._dcasa_mostrar_vencimiento() else '')]

    def _dcasa_datos(self):
        """[(etiqueta, valor)] de la columna de datos del documento; solo lo que tiene valor."""
        self.ensure_one()
        etiqueta_fecha = 'Fecha de la nota' if self.move_type == 'out_refund' else 'Fecha de factura'
        datos = [
            (etiqueta_fecha, self._dcasa_fecha(self.invoice_date)),
            *self._dcasa_fechas_de_pago(),
            ('Fecha de entrega', self._dcasa_fecha(self.delivery_date)),
            ('Pedido', self.invoice_origin),
            ('Referencia', self.ref if self.ref != self.invoice_origin else ''),
            ('Código de cliente', self.partner_id.ref),
            ('Vendedor/a', self.invoice_user_id.name if self.move_type in ('out_invoice', 'out_refund') else ''),
            ('Condiciones', self.invoice_payment_term_id.name),
            ('Medio de pago', self._dcasa_medio_de_pago()),
        ]
        return [(etiqueta, valor) for etiqueta, valor in datos if valor]

    # ------------------------------------------------------------------------
    # Líneas: muebles arriba, flete y servicios en su bloque
    # ------------------------------------------------------------------------

    def _dcasa_lineas(self, lineas_a_imprimir):
        """(principales, servicios) a partir de las líneas que el reporte ya decidió imprimir."""
        principales, servicios = lineas.separar(lineas_a_imprimir, lambda linea: linea.display_type == 'product')
        return self._dcasa_fuera_de_los_combos(principales), servicios

    def _dcasa_fuera_de_los_combos(self, principales):
        """Lo que no es una pieza de un combo pero Odoo deja debajo de su título (una mesa de noche que se vendió
        después del combo) se imprime ANTES de los combos: así no queda sangrado como si fuera parte del combo."""
        sueltas = principales.filtered(
            lambda linea: linea.display_type in ('product', 'line_note') and linea.parent_id
            and linea.parent_id._dcasa_es_titulo_de_combo()
            and linea not in linea.parent_id._dcasa_piezas_del_combo())
        return sueltas | principales

    def _dcasa_titulo_servicios(self, servicios):
        return lineas.titulo_servicios(servicios)

    def _dcasa_total_descuento(self):
        self.ensure_one()
        return lineas.total_descuento(
            self.invoice_line_ids.filtered(lambda linea: linea.display_type == 'product'), self.currency_id)

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
