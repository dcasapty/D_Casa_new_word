"""La factura de Odoo frente a la factura electrónica de la DGI.

* Con la FE apagada (o sin PAC) nada de esto corre: ``_l10n_pa_fe_aplica`` es False.
* Encendida: antes de publicar se validan los datos fiscales y, si falta algo, la factura NO
  se publica y se dice qué falta; al publicar nace su ``dcasa.fe.documento`` en la cola.
* Una factura con documento enviado, autorizado o en contingencia no vuelve a borrador ni
  se cancela en Odoo: se anula ante la DGI o se corrige con nota de crédito.
"""
import base64
from datetime import timedelta

from markupsafe import Markup

from odoo import fields, models
from odoo.addons.dcasa_invoice.models import formato
from odoo.exceptions import UserError

from . import catalogos as C

TIPOS_FE = ('out_invoice', 'out_refund')
# Panamá no tiene horario de verano: UTC-5 todo el año.
OFFSET_PANAMA = timedelta(hours=-5)
TOLERANCIA = 0.005
# Documentos que existen ante la DGI (o van camino de existir): la factura ya no se toca.
VIVOS = ('por_enviar', 'enviado', 'autorizado', 'contingencia')


def fecha_dgi(momento):
    """datetime UTC (naive, como lo guarda Odoo) → '2026-10-02T09:15:00-05:00'."""
    return (momento + OFFSET_PANAMA).strftime('%Y-%m-%dT%H:%M:%S-05:00')


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_pa_fe_documento_ids = fields.One2many('dcasa.fe.documento', 'move_id', string='Documento electrónico')
    l10n_pa_fe_estado = fields.Selection(
        related='l10n_pa_fe_documento_ids.estado', string='Estado FE (DGI)')

    # ------------------------------------------------------------------
    # Flujo de publicación
    # ------------------------------------------------------------------

    def _l10n_pa_fe_aplica(self):
        self.ensure_one()
        return (self.move_type in TIPOS_FE and self.journal_id.type == 'sale'
                and self.company_id._l10n_pa_fe_operando())

    def _post(self, soft=True):
        aplicables = self.filtered(lambda m: m._l10n_pa_fe_aplica())
        for move in aplicables:
            problemas = move._l10n_pa_fe_problemas()
            if problemas:
                raise UserError(self.env._(
                    'La factura %(factura)s no se puede emitir como factura electrónica. Falta corregir:\n- %(lista)s',
                    factura=move.name or move.partner_id.display_name, lista='\n- '.join(problemas)))
        publicados = super()._post(soft=soft)
        for move in publicados & aplicables:
            self.env['dcasa.fe.documento'].sudo()._crear_para(move)
        return publicados

    def _l10n_pa_fe_bloquea_cambios(self, estados):
        bloqueados = self.l10n_pa_fe_documento_ids.filtered(lambda d: d.estado in estados)
        if bloqueados:
            raise UserError(self.env._(
                '%s ya tiene documento electrónico ante la DGI: no vuelve a borrador ni se cancela. '
                'Corrígela con una nota de crédito o anúlala desde su documento electrónico.',
                ', '.join(bloqueados.move_id.mapped('name'))))

    def button_draft(self):
        # button_cancel de Odoo pasa por button_draft: ahí una FE anulada sí deja seguir.
        cancelando = self.env.context.get('l10n_pa_fe_cancelando')
        self.sudo()._l10n_pa_fe_bloquea_cambios(VIVOS if cancelando else VIVOS + ('anulado',))
        return super().button_draft()

    def button_cancel(self):
        # Anulada ante la DGI (la venta no ocurrió): ya se puede cancelar en Odoo.
        self.sudo()._l10n_pa_fe_bloquea_cambios(VIVOS)
        return super(AccountMove, self.with_context(l10n_pa_fe_cancelando=True)).button_cancel()

    # ------------------------------------------------------------------
    # Validaciones previas (en español, todas de una vez)
    # ------------------------------------------------------------------

    def _l10n_pa_fe_lineas(self):
        return self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')

    def _l10n_pa_fe_problemas(self):
        """Lista de lo que falta para emitir; vacía si se puede."""
        self.ensure_one()
        return (self._l10n_pa_fe_problemas_emisor() + self._l10n_pa_fe_problemas_receptor()
                + self._l10n_pa_fe_problemas_lineas())

    def _l10n_pa_fe_problemas_emisor(self):
        company, problemas = self.company_id, []
        _ = self.env._
        if not company.vat:
            problemas.append(_('La empresa no tiene RUC.'))
        if not company.l10n_pa_dv:
            problemas.append(_('La empresa no tiene DV.'))
        if not company.street:
            problemas.append(_('La empresa no tiene dirección.'))
        if not company.partner_id._l10n_pa_fe_ubicacion():
            problemas.append(_('La empresa no tiene completa su ubicación DGI (código, corregimiento, distrito '
                               'y provincia).'))
        if not self.journal_id.l10n_pa_fe_punto:
            problemas.append(_('El diario %s no tiene punto de facturación.', self.journal_id.name))
        if self.currency_id.name != 'USD':
            problemas.append(_('La factura electrónica se emite en dólares (USD), no en %s.', self.currency_id.name))
        if self.currency_id.compare_amounts(self.amount_total, 0) <= 0:
            problemas.append(_('El total tiene que ser mayor que cero.'))
        return problemas

    def _l10n_pa_fe_problemas_receptor(self):
        _ = self.env._
        cliente = self.partner_id.commercial_partner_id
        tipo = self.partner_id._l10n_pa_fe_tipo_receptor()
        problemas = []
        if tipo in (C.RECEPTOR_CONTRIBUYENTE, C.RECEPTOR_GOBIERNO):
            if not cliente.vat:
                problemas.append(_('El cliente %s no tiene RUC.', cliente.display_name))
            if not cliente.l10n_pa_dv:
                problemas.append(_('El cliente %s no tiene DV del RUC.', cliente.display_name))
            if not cliente.street:
                problemas.append(_('El cliente %s no tiene dirección.', cliente.display_name))
            if not cliente._l10n_pa_fe_ubicacion():
                problemas.append(_('El cliente %s no tiene completa su ubicación DGI (código, corregimiento, '
                                   'distrito y provincia).', cliente.display_name))
        elif tipo == C.RECEPTOR_EXTRANJERO:
            if not cliente.vat:
                problemas.append(_('El cliente extranjero %s no tiene pasaporte o número tributario (campo RUC).',
                                   cliente.display_name))
            if not cliente.country_id:
                problemas.append(_('El cliente extranjero %s no tiene país.', cliente.display_name))
        return problemas

    def _l10n_pa_fe_problemas_lineas(self):
        _ = self.env._
        problemas = []
        gobierno = self.partner_id._l10n_pa_fe_tipo_receptor() == C.RECEPTOR_GOBIERNO
        lineas = self._l10n_pa_fe_lineas()
        if not lineas:
            problemas.append(_('La factura no tiene líneas de producto.'))
        for linea in lineas:
            nombre = linea.product_id.display_name or linea.name or '?'
            impuestos = linea.tax_ids
            if len(impuestos) != 1 or not impuestos._l10n_pa_fe_codigo_itbms():
                problemas.append(_('«%s» necesita exactamente un impuesto ITBMS (0 %%, 7 %%, 10 %% o 15 %%); '
                                   'si es exento, ponle el ITBMS 0 %% exento.', nombre))
            if linea.currency_id.compare_amounts(linea.price_subtotal, 0) < 0 or linea.quantity <= 0:
                problemas.append(_('«%s» tiene cantidad o importe negativo: usa el descuento %% de la línea.', nombre))
            if gobierno and not linea.product_id.product_tmpl_id.l10n_pa_cpbs:
                problemas.append(_('«%s» no tiene código CPBS (obligatorio al facturarle al Gobierno).', nombre))
        if lineas and abs(sum(lineas.mapped('price_total')) - self.amount_total) > TOLERANCIA:
            problemas.append(_('La suma de las líneas no cuadra con el total por redondeo del ITBMS: '
                               'el redondeo de impuestos debe ser «por línea».'))
        return problemas

    # ------------------------------------------------------------------
    # Datos del documento (dict neutro para generador.generar_xml)
    # ------------------------------------------------------------------

    def _l10n_pa_fe_tipo_documento(self):
        """(tipo iDoc, documento al que hace referencia o vacío)."""
        self.ensure_one()
        vacio = self.env['dcasa.fe.documento']
        if self.move_type == 'out_invoice':
            return C.DOC_FACTURA, vacio
        original = self.reversed_entry_id.l10n_pa_fe_documento_ids.filtered(lambda d: d.estado == 'autorizado')
        if original:
            return C.DOC_NC_REFERENCIA, original[:1]
        return C.DOC_NC_GENERICA, vacio

    def _l10n_pa_fe_datos(self, doc):
        self.ensure_one()
        emisor = self._l10n_pa_fe_emisor()
        receptor = self._l10n_pa_fe_receptor()
        items = self._l10n_pa_fe_items(receptor['tipo'])
        gen = {
            'iAmb': doc.ambiente, 'iTpEmis': doc.tipo_emision, 'iDoc': doc.tipo_documento,
            'dNroDF': doc.numero, 'dPtoFacDF': doc.punto, 'dSeg': doc.seguridad,
            'dFechaEm': fecha_dgi(doc.fecha_emision),
            'iNatOp': C.NATURALEZA['venta'] if doc.tipo_documento == C.DOC_FACTURA else C.NATURALEZA['devolucion'],
            'iTipoOp': '1', 'iDest': '1',
            'iFormCAFE': self.company_id.l10n_pa_fe_forma_cafe, 'iEntCAFE': self.company_id.l10n_pa_fe_entrega_cafe,
            'dEnvFE': '1', 'iProGen': '1',
            'iTipoTranVenta': '1' if doc.tipo_documento == C.DOC_FACTURA else None,
            'dInfEmFE': self.env._('Documento Odoo %s', self.name),
        }
        if doc.tipo_emision == C.EMISION_CONTINGENCIA:
            gen['dFechaCont'] = fecha_dgi(doc.contingencia_inicio)
            gen['dMotCont'] = (doc.contingencia_motivo or '')[:C.MOTIVO_MAX]
        referencias = []
        if doc.referencia_id:
            referencias.append({'emisor': emisor, 'cufe': doc.referencia_id.cufe,
                                'fecha': fecha_dgi(doc.referencia_id.fecha_emision)})
        cufe = C.cufe(doc.tipo_documento, emisor['tipo_ruc'], emisor['ruc'], emisor['dv'], emisor['sucursal'],
                      doc.fecha_emision + OFFSET_PANAMA, doc.numero, doc.punto, doc.tipo_emision, doc.ambiente,
                      doc.seguridad)
        return {'version': C.VERSION_FORMATO, 'cufe': cufe, 'gen': gen, 'emisor': emisor, 'receptor': receptor,
                'referencias': referencias, 'items': items, 'totales': self._l10n_pa_fe_totales(items)}

    def _l10n_pa_fe_emisor(self):
        company = self.company_id
        direccion = ', '.join(p for p in (company.street, company.street2, company.city) if p)
        return {
            'tipo_ruc': company.l10n_pa_fe_tipo_ruc, 'ruc': company.vat.strip(), 'dv': company.l10n_pa_dv.zfill(2),
            'nombre': company.name[:200], 'sucursal': company.l10n_pa_fe_sucursal or '0000',
            'coordenadas': company.l10n_pa_fe_coordenadas, 'direccion': direccion[:100],
            'ubicacion': company.partner_id._l10n_pa_fe_ubicacion(),
            'telefonos': [formato.telefono_fmt(company.phone)] if company.phone else [],
            'correos': [company.email] if company.email else [],
        }

    def _l10n_pa_fe_receptor(self):
        cliente = self.partner_id.commercial_partner_id
        tipo = self.partner_id._l10n_pa_fe_tipo_receptor()
        receptor = {
            'tipo': tipo, 'nombre': (cliente.name or '')[:200] or None,
            'direccion': ', '.join(p for p in (cliente.street, cliente.street2, cliente.city) if p)[:100] or None,
            'telefonos': [formato.telefono_fmt(cliente.phone)] if cliente.phone else [],
            'correos': [cliente.email] if cliente.email else [],
            'pais': (cliente.country_id.code or 'PA'),
        }
        if tipo == C.RECEPTOR_EXTRANJERO:
            receptor.update(id_extranjero=cliente.vat, pais_extranjero=cliente.country_id.name)
        elif cliente.vat and cliente.l10n_pa_dv:
            receptor.update(tipo_ruc=self.partner_id._l10n_pa_fe_tipo_ruc(), ruc=cliente.vat.strip(),
                            dv=cliente.l10n_pa_dv.zfill(2), ubicacion=cliente._l10n_pa_fe_ubicacion())
        return receptor

    def _l10n_pa_fe_items(self, tipo_receptor):
        items = []
        for secuencia, linea in enumerate(self._l10n_pa_fe_lineas(), start=1):
            impuesto = linea.tax_ids[:1]
            unitario = impuesto.compute_all(linea.price_unit, currency=None, quantity=1.0,
                                            product=linea.product_id, partner=self.partner_id)['total_excluded']
            items.append({
                'secuencia': secuencia,
                'descripcion': (linea.name or linea.product_id.display_name or '')[:500],
                'codigo': (linea.product_id.default_code or '')[:20] or None,
                'cantidad': linea.quantity,
                'cpbs': linea.product_id.product_tmpl_id.l10n_pa_cpbs if tipo_receptor == C.RECEPTOR_GOBIERNO
                else None,
                'precio_unitario': unitario,
                'descuento_unitario': unitario * (linea.discount or 0.0) / 100.0,
                'precio_item': linea.price_subtotal,
                'valor_total': linea.price_total,
                'tasa': impuesto._l10n_pa_fe_codigo_itbms(),
                'itbms': self.currency_id.round(linea.price_total - linea.price_subtotal),
            })
        return items

    def _l10n_pa_fe_totales(self, items):
        total = self.amount_total
        totales = {
            'neto': self.amount_untaxed, 'itbms': self.amount_tax, 'gravado': self.amount_tax,
            'descuento': self.currency_id.round(sum(i['descuento_unitario'] * i['cantidad'] for i in items)),
            'total': total, 'recibido': total, 'vuelto': 0.0, 'nro_items': len(items),
            'total_items': sum(i['valor_total'] for i in items),
        }
        plazos = self.line_ids.filtered(lambda line: line.display_type == 'payment_term').sorted('date_maturity')
        a_plazo = self.move_type == 'out_invoice' and any(
            line.date_maturity and line.date_maturity > (self.invoice_date or fields.Date.today()) for line in plazos)
        if a_plazo:
            totales.update(tiempo_pago=C.PAGO_A_PLAZO,
                           formas_pago=[{'codigo': C.FORMA_PAGO_CREDITO, 'valor': total}],
                           plazos=[{'secuencia': n, 'fecha': fecha_dgi(fields.Datetime.to_datetime(line.date_maturity)
                                                                       - OFFSET_PANAMA),
                                    'valor': abs(line.amount_currency)} for n, line in enumerate(plazos, start=1)])
        else:
            totales.update(tiempo_pago=C.PAGO_INMEDIATO, formas_pago=self._l10n_pa_fe_formas_pago(total))
        return totales

    def _l10n_pa_fe_formas_pago(self, total):
        """Por diario de los pagos ya conciliados; si aún no hay pagos, la forma por defecto de la empresa."""
        formas = {}
        for pago in self._dcasa_pagos():
            diario = self.env['account.move'].browse(pago.get('move_id')).exists().journal_id
            codigo = diario.l10n_pa_fe_forma_pago or self.company_id.l10n_pa_fe_forma_pago
            clave = (codigo, diario.name if codigo == C.FORMA_PAGO_OTRO else None)
            formas[clave] = formas.get(clave, 0.0) + (pago.get('amount') or 0.0)
        if not formas or abs(sum(formas.values()) - total) > TOLERANCIA:
            codigo = self.company_id.l10n_pa_fe_forma_pago or '02'
            return [{'codigo': codigo, 'valor': total,
                     'descripcion': self.env._('Otro') if codigo == C.FORMA_PAGO_OTRO else None}]
        return [{'codigo': codigo, 'descripcion': descripcion, 'valor': valor}
                for (codigo, descripcion), valor in formas.items()]

    # ------------------------------------------------------------------
    # Para la factura impresa (dcasa_invoice)
    # ------------------------------------------------------------------

    def _l10n_pa_fe_impreso(self):
        """El documento que se imprime: autorizado o emitido en contingencia. Vacío si no hay."""
        self.ensure_one()
        return self.sudo().l10n_pa_fe_documento_ids.filtered(
            lambda d: d.estado in ('autorizado', 'contingencia') and d.cufe)[:1]

    def _l10n_pa_fe_qr_src(self):
        """La imagen del QR como data URI (wkhtmltopdf no tiene que pedir nada al servidor)."""
        self.ensure_one()
        doc = self._l10n_pa_fe_impreso()
        if not doc.qr:
            return ''
        png = self.env['ir.actions.report'].barcode('QR', doc.qr, width=160, height=160)
        return Markup('data:image/png;base64,') + base64.b64encode(png).decode()

    def _l10n_pa_fe_url_consulta(self):
        self.ensure_one()
        doc = self._l10n_pa_fe_impreso()
        return f'{C.URL_CUFE.get(doc.ambiente or "1", C.URL_CUFE["1"])}{doc.cufe}' if doc else ''

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    def action_l10n_pa_fe_procesar(self):
        """«Enviar a la DGI ahora»: el mismo paso que hace la cola, sin esperar al cron."""
        return self.l10n_pa_fe_documento_ids.action_procesar()
