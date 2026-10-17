"""``dcasa.correo.envio``: la cola de los correos que D'CASA le manda a sus clientes, y su registro.

Al registrar un pago (cualquier camino: el botón «Pagar», Brian, la conciliación del banco) solo se ESCRIBE una fila
aquí, dentro de la misma transacción y en un savepoint: nada de HTTP ni de PDF. Si el pago se deshace, la fila se
deshace con él; si algo falla aquí, el pago sigue (``account_move_line.py``). Después el cron arma el PDF nuevo, deja el
correo en el chatter y la cola de Odoo lo manda por Resend.

Sin duplicados: ``(tipo, huella)`` es único. La huella de un pago es ``factura:saldo en centavos``; la de la bienvenida,
``bienvenida:ficha``.
"""
import logging

import psycopg2

from odoo import api, fields, models, modules
from odoo.exceptions import UserError

from .correo import centavos

_logger = logging.getLogger(__name__)

TIPOS = [('factura', 'Factura'), ('abono', 'Abono'), ('bienvenida', 'Bienvenida'),
         ('cotizacion', 'Cotización')]
ESTADOS = [('pendiente', 'Por enviar'), ('enviado', 'Enviado'), ('omitido', 'No se envió'), ('fallido', 'Falló')]
INFORME_COTIZACION = 'sale.action_report_saleorder'
# Por qué se omitió (técnico). Una bienvenida omitida por estas causas se vuelve a armar con el siguiente pago.
CAUSAS_QUE_SE_REARMAN = ('sin_correo', 'apagado')
LOTE = 20


class DcasaCorreoEnvio(models.Model):
    _name = 'dcasa.correo.envio'
    _description = 'Correo a un cliente'
    _order = 'id desc'
    _rec_name = 'huella'

    tipo = fields.Selection(TIPOS, required=True, readonly=True, index=True)
    move_id = fields.Many2one('account.move', string='Factura', readonly=True, index='btree_not_null',
                              ondelete='set null')
    order_id = fields.Many2one('sale.order', string='Cotización', readonly=True, index='btree_not_null',
                               ondelete='set null')
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True, index=True, ondelete='set null')
    huella = fields.Char(required=True, readonly=True, index=True,
                         help='Lo que hace único a este correo: el mismo pago no se manda dos veces.')
    saldo_centavos = fields.Integer('Saldo al registrarlo (centavos)', readonly=True)
    estado = fields.Selection(ESTADOS, default='pendiente', required=True, readonly=True, index=True)
    causa = fields.Char(readonly=True, help='Código técnico de por qué no se envió.')
    motivo = fields.Char(readonly=True)
    correo = fields.Char('Enviado a', readonly=True)
    message_id = fields.Many2one('mail.message', string='Mensaje', readonly=True, ondelete='set null')
    entrega = fields.Char('Entrega', compute='_compute_entrega',
                          help='Lo que dice la cola de correo de Odoo: por enviar, enviado o el error de Resend.')

    _tipo_huella_unica = models.Constraint('UNIQUE(tipo, huella)', 'Ese correo ya está en la cola.')

    @api.depends('message_id', 'estado')
    def _compute_entrega(self):
        etiquetas = dict(self.env['mail.notification']._fields['notification_status'].selection)
        for envio in self:
            avisos = envio.sudo().message_id.notification_ids.filtered(lambda n: n.notification_type == 'email')
            if envio.estado != 'enviado' or not avisos:
                envio.entrega = ''
                continue
            aviso = avisos[:1]
            texto = etiquetas.get(aviso.notification_status, aviso.notification_status or '')
            if aviso.notification_status in ('exception', 'bounce') and aviso.failure_reason:
                texto = f'{texto}: {aviso.failure_reason.strip().splitlines()[-1][:200]}'
            envio.entrega = texto

    # ------------------------------------------------------------------
    # Encolar (dentro de la transacción del pago: solo filas, nada más)
    # ------------------------------------------------------------------

    @api.model
    def _crear_si_no_existe(self, valores):
        """Crea el envío si su ``(tipo, huella)`` no existe todavía. Devuelve el envío nuevo o un vacío."""
        if self.search_count([('tipo', '=', valores['tipo']), ('huella', '=', valores['huella'])], limit=1):
            return self.browse()
        try:
            with self.env.cr.savepoint():
                envio = self.create(valores)
                envio.flush_recordset()
        except psycopg2.IntegrityError:
            return self.browse()   # otro proceso lo encoló al mismo tiempo
        return envio

    @api.model
    def _factura_cuenta(self, move):
        return (move.move_type == 'out_invoice' and move.state == 'posted' and not move.dcasa_historica
                and move.currency_id.compare_amounts(move.amount_total, 0) > 0)

    @api.model
    def _hubo_pago(self, move, lineas):
        """¿Entre lo que se acaba de conciliar con la factura hay un pago o un movimiento de banco? (Una nota de
        crédito aplicada baja el saldo, pero no es un pago: no manda correo.)"""
        propias = move.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        contrapartes = (propias.matched_credit_ids.credit_move_id | propias.matched_debit_ids.debit_move_id) & lineas
        return any(linea.move_id.origin_payment_id or linea.move_id.statement_line_id for linea in contrapartes)

    @api.model
    def _encolar_pagos(self, antes, lineas):
        """El gancho del pago: ``antes`` es ``{factura: saldo antes de conciliar}``; ``lineas``, lo conciliado."""
        correo = self.env['dcasa.correo']
        config = correo._config()
        if not correo._activo_para_clientes() or not config['al_pagar']:
            return self.browse()
        nuevos = self.browse()
        for move in self.env['account.move'].sudo().browse(list(antes)).exists():
            if not self._factura_cuenta(move):
                continue
            if move.currency_id.compare_amounts(move.amount_residual, antes[move.id]) >= 0:
                continue
            if not self._hubo_pago(move, lineas):
                continue
            saldo = move.amount_residual
            tipo = 'abono' if move.currency_id.compare_amounts(saldo, 0) > 0 else 'factura'
            nuevos |= self._crear_si_no_existe({
                'tipo': tipo, 'huella': f'{move.id}:{centavos(saldo)}', 'saldo_centavos': centavos(saldo),
                'move_id': move.id, 'partner_id': move.commercial_partner_id.id,
            })
            if config['bienvenida']:
                nuevos |= self._encolar_bienvenida(move.commercial_partner_id)
        if nuevos:
            self.env.ref('dcasa_correo.ir_cron_dcasa_correo_cola').sudo()._trigger()
        return nuevos

    @api.model
    def _es_cliente_nuevo(self, ficha):
        """La bienvenida es SOLO para clientes nuevos (la dueña, 17/10/2026). Nuevo es la ficha que se creó después de
        instalar este módulo (``dcasa_correo.bienvenida_desde``), que no vino del sistema anterior y que no tiene
        facturas históricas. Sin esa fecha guardada, nadie es nuevo."""
        desde = self.env['dcasa.correo']._bienvenida_desde()
        if not ficha or not desde or not ficha.create_date or ficha.create_date < desde:
            return False
        if self.env['ir.model.data'].sudo().search_count([
                ('model', '=', 'res.partner'), ('res_id', '=', ficha.id), ('module', '=', '__import__'),
                ('name', '=like', 'dcasa\\_contacto\\_%')], limit=1):
            return False
        return not self.env['account.move'].sudo().search_count(
            [('commercial_partner_id', '=', ficha.id), ('dcasa_historica', '=', True)], limit=1)

    @api.model
    def _encolar_bienvenida(self, ficha):
        """Una sola bienvenida por ficha comercial. Si la anterior no salió por falta de correo (o porque se apagaron
        los correos), se vuelve a armar ahora."""
        ficha = ficha.commercial_partner_id
        if not self._es_cliente_nuevo(ficha):
            return self.browse()
        huella = f'bienvenida:{ficha.id}'
        existente = self.search([('tipo', '=', 'bienvenida'), ('huella', '=', huella)], limit=1)
        if existente:
            if existente.estado == 'omitido' and existente.causa in CAUSAS_QUE_SE_REARMAN:
                existente.write({'estado': 'pendiente', 'causa': False, 'motivo': False})
                return existente
            return self.browse()
        return self._crear_si_no_existe({'tipo': 'bienvenida', 'huella': huella, 'partner_id': ficha.id})

    # ------------------------------------------------------------------
    # Procesar (cron, como superusuario)
    # ------------------------------------------------------------------

    @api.model
    def _procesar(self, limite=LOTE):
        """Cron: arma y deja en la cola de Odoo los correos pendientes, del más viejo al más nuevo. Cada uno en su
        savepoint y confirmado aparte: uno que falla no frena a los demás ni toca la factura."""
        pendientes = self.sudo().search([('estado', '=', 'pendiente')], order='id', limit=limite)
        en_prueba = modules.module.current_test
        for envio in pendientes:
            try:
                with self.env.cr.savepoint():
                    envio._procesar_uno()
            except Exception as error:  # noqa: BLE001 - un correo nunca rompe la cola ni la factura
                _logger.exception('DCASA_CORREO no se pudo preparar el envío %s', envio.id)
                envio.write({'estado': 'fallido', 'causa': 'error',
                             'motivo': (str(error) or type(error).__name__)[:250]})
            if not en_prueba:
                self.env['ir.cron']._commit_progress(1)
        if len(pendientes) == limite:
            self.env.ref('dcasa_correo.ir_cron_dcasa_correo_cola').sudo()._trigger()
        return len(pendientes)

    def _omitir(self, causa, motivo):
        self.write({'estado': 'omitido', 'causa': causa, 'motivo': motivo})

    def _procesar_uno(self):
        self.ensure_one()
        correo = self.env['dcasa.correo']
        if not correo._activo_para_clientes():
            return self._omitir('apagado', self.env._('Se apagaron los correos antes de enviarlo.'))
        if self.tipo in ('factura', 'abono'):
            return self._procesar_factura()
        if self.tipo == 'bienvenida':
            return self._procesar_bienvenida()
        return self._omitir('tipo', self.env._('Este tipo de correo no pasa por la cola.'))

    def _procesar_factura(self):
        correo = self.env['dcasa.correo']
        move = self.move_id.sudo()
        if not move or move.state != 'posted' or centavos(move.amount_residual) != self.saldo_centavos:
            return self._omitir('cambio', self.env._(
                'La factura cambió después del pago (se canceló, volvió a borrador o cambió su saldo): no se manda '
                'un correo viejo.'))
        if self.search_count([('move_id', '=', move.id), ('estado', '=', 'pendiente'), ('id', '>', self.id),
                              ('tipo', 'in', ('factura', 'abono'))], limit=1):
            return self._omitir('reciente', self.env._('Se mandó el más reciente de esta factura.'))
        destino = correo._destino(move)
        if not destino:
            cliente = move.partner_id.display_name or move.commercial_partner_id.display_name
            nota = self.env._('No se envió por correo: falta el correo de %s o está mal escrito.', cliente)
            move.message_post(body=nota, message_type='comment', subtype_xmlid='mail.mt_note')
            return self._omitir('sin_correo', nota)
        pdf, nombre = self._pdf_factura(move)
        mensaje = correo._postear(move, self.env.ref('dcasa_correo.plantilla_factura'), destino,
                                  [(nombre, pdf)], tipo=self.tipo)
        self.write({'estado': 'enviado', 'message_id': mensaje.id, 'correo': destino.email_normalized,
                    'causa': False, 'motivo': False})
        correo._disparar_cola()
        return True

    def _pdf_factura(self, move):
        """El PDF NUEVO de la factura (con lo pagado hasta hoy). No reemplaza el PDF guardado de la factura."""
        informe = self.env['account.move.send']._get_default_pdf_report_id(move)
        contenido, tipo = self.env['ir.actions.report'].with_company(move.company_id).with_context(
            force_report_rendering=True)._render_qweb_pdf(informe, [move.id])
        if tipo != 'pdf' or not contenido:
            raise UserError(self.env._('No se pudo armar el PDF de la factura %s.', move.name))
        numero = (move.name or '').replace('/', '-')
        if self.tipo == 'abono':
            hoy = fields.Date.context_today(self).strftime('%d-%m-%Y')
            return contenido, f'Abono {numero} {hoy}.pdf'
        return contenido, f'Factura {numero}.pdf'

    def _procesar_bienvenida(self):
        correo = self.env['dcasa.correo']
        ficha = self.partner_id.sudo()
        if not ficha:
            return self._omitir('cambio', self.env._('La ficha del cliente ya no existe.'))
        if ficha.dcasa_socio_estado == 'suspendido':
            return self._omitir('suspendido', self.env._('El cliente está suspendido en el programa de Socios.'))
        destino = correo._destino(ficha)
        if not destino:
            return self._omitir('sin_correo', self.env._(
                'Falta el correo de %s o está mal escrito.', ficha.display_name))
        mensaje = correo._postear(ficha, self.env.ref('dcasa_correo.plantilla_bienvenida'), destino,
                                  tipo='bienvenida')
        self.write({'estado': 'enviado', 'message_id': mensaje.id, 'correo': destino.email_normalized,
                    'causa': False, 'motivo': False})
        correo._disparar_cola()
        return True
