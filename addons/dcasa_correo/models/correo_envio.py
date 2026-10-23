"""``dcasa.correo.envio``: la cola de los correos que D'CASA le manda a sus clientes, y su registro.

Al registrar un pago (cualquier camino: el botón «Pagar», Brian, la conciliación del banco) solo se ESCRIBE una fila
aquí, dentro de la misma transacción y en un savepoint: nada de HTTP ni de PDF. Si el pago se deshace, la fila se
deshace con él; si algo falla aquí, el pago sigue (``account_move_line.py``). Después el cron arma el PDF nuevo, deja el
correo en el chatter y la cola de Odoo lo manda por Resend.

Sin duplicados: ``(tipo, huella)`` es único. La huella de un pago es ``factura:saldo en centavos``; la de la bienvenida,
``bienvenida:ficha``.
"""
import logging
from datetime import timedelta

import psycopg2

from odoo import api, fields, models, modules
from odoo.exceptions import UserError

from .correo import centavos

_logger = logging.getLogger(__name__)

TIPOS = [('factura', 'Factura'), ('abono', 'Abono'), ('bienvenida', 'Bienvenida'),
         ('cotizacion', 'Cotización'), ('recordatorio', 'Recordatorio de abono')]
ESTADOS = [('pendiente', 'Por enviar'), ('enviado', 'Enviado'), ('omitido', 'No se envió'), ('fallido', 'Falló')]
INFORME_COTIZACION = 'sale.action_report_saleorder'
# Por qué se omitió (técnico). Una bienvenida omitida por estas causas se vuelve a armar con el siguiente pago.
CAUSAS_QUE_SE_REARMAN = ('sin_correo', 'apagado')
# El correo de un pago que se omitió porque la factura cambió antes de armarlo (se desconcilió, llegó otro pago) vuelve
# a la cola si un pago deja esa factura otra vez con ese mismo saldo: nunca salió, así que no se duplica.
CAUSAS_DE_PAGO_QUE_SE_REARMAN = ('cambio', 'reciente')
# Veces que el cron intenta armar un correo (PDF, plantilla) antes de darlo por fallido: un tropiezo pasajero de
# wkhtmltopdf no deja al cliente sin su factura.
MAX_ARMAR = 3
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
    intentos = fields.Integer('Intentos de armarlo', default=0, readonly=True, copy=False,
                              help='Veces que no se pudo armar el correo (p. ej. el PDF). Al tercero queda «Falló».')
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
    def _crear_si_no_existe(self, valores, rearmar=()):
        """Crea el envío si su ``(tipo, huella)`` no existe todavía. Devuelve el envío nuevo o un vacío.

        ``rearmar``: si ya existe pero quedó omitido por una de esas causas (nunca salió), vuelve a «Por enviar»."""
        existente = self.search([('tipo', '=', valores['tipo']), ('huella', '=', valores['huella'])], limit=1)
        if existente:
            if existente.estado == 'omitido' and existente.causa in rearmar:
                existente.write({'estado': 'pendiente', 'causa': False, 'motivo': False, 'intentos': 0})
                return existente
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
        facturas = self.env['account.move'].sudo().browse(list(antes)).exists().filtered(
            lambda m: m.move_type == 'out_invoice')   # solo facturas de cliente (sudo: nunca se devuelven a nadie)
        for move in facturas:
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
            }, rearmar=CAUSAS_DE_PAGO_QUE_SE_REARMAN)
            if config['bienvenida']:
                nuevos |= self._encolar_bienvenida(move.commercial_partner_id)
        if nuevos:
            self.env.ref('dcasa_correo.ir_cron_dcasa_correo_cola').sudo()._trigger()
        return nuevos

    @api.model
    def _es_cliente_nuevo(self, ficha):
        """La bienvenida es SOLO para clientes nuevos (la dueña, 17/10/2026). Nuevo es la ficha que se creó después de
        instalar este módulo (``dcasa_correo.bienvenida_desde``), que no vino del sistema anterior (ni ella ni sus
        contactos), que no tiene facturas históricas y que no tiene nada de antes de esa fecha: una ficha nueva a la que
        se le fusionó la de un cliente de antes trae sus facturas, sus ventas o sus puntos viejos, y no es nueva. Sin
        esa fecha guardada, nadie es nuevo."""
        desde = self.env['dcasa.correo']._bienvenida_desde()
        if not ficha or not desde or not ficha.create_date or ficha.create_date < desde:
            return False
        fichas = self.env['res.partner'].sudo().with_context(active_test=False).search([('id', 'child_of', ficha.id)])
        if self.env['ir.model.data'].sudo().search_count([
                ('model', '=', 'res.partner'), ('res_id', 'in', fichas.ids), ('module', '=', '__import__'),
                ('name', '=like', 'dcasa\\_contacto\\_%')], limit=1):
            return False
        if fichas.filtered(lambda f: f.create_date and f.create_date < desde):
            return False
        Move = self.env['account.move'].sudo()
        if Move.search_count([
                ('move_type', 'in', ('out_invoice', 'out_refund')), ('commercial_partner_id', '=', ficha.id),
                '|', ('dcasa_historica', '=', True), ('create_date', '<', desde)], limit=1):
            return False
        if self.env['sale.order'].sudo().search_count([
                ('partner_id', 'in', fichas.ids), ('create_date', '<', desde)], limit=1):
            return False
        return not self.env['dcasa.movimiento'].sudo().search_count([
            ('partner_id', '=', ficha.id), ('create_date', '<', desde)], limit=1)

    @api.model
    def _encolar_bienvenida(self, ficha):
        """Una sola bienvenida por ficha comercial, cuando ya puede entrar a Mi cuenta (``_lista_para_bienvenida``:
        si su primera compra va en abono, con el pago que la termina). Si la anterior no salió por falta de correo (o
        porque se apagaron los correos), se vuelve a armar ahora."""
        ficha = ficha.commercial_partner_id
        if not self._es_cliente_nuevo(ficha) or not self.env['dcasa.correo']._lista_para_bienvenida(ficha):
            return self.browse()
        huella = f'bienvenida:{ficha.id}'
        # Al fusionar dos fichas, Odoo pasa los envíos de la que se borra a la que queda (partner_id), con su huella:
        # si alguna ya tuvo su bienvenida (o la tiene en camino), esta ficha no recibe otra.
        if self.search_count([('tipo', '=', 'bienvenida'), ('partner_id', '=', ficha.id), ('huella', '!=', huella),
                              ('estado', 'in', ('pendiente', 'enviado'))], limit=1):
            return self.browse()
        return self._crear_si_no_existe({'tipo': 'bienvenida', 'huella': huella, 'partner_id': ficha.id},
                                        rearmar=CAUSAS_QUE_SE_REARMAN)

    # ------------------------------------------------------------------
    # Procesar (cron, como superusuario)
    # ------------------------------------------------------------------

    @api.model
    def _procesar(self, limite=LOTE):
        """Cron: arma y deja en la cola de Odoo los correos pendientes, del más viejo al más nuevo. Cada uno en su
        savepoint y confirmado aparte: uno que falla no frena a los demás ni toca la factura. El que no se pudo armar
        se vuelve a intentar en la siguiente vuelta, hasta ``MAX_ARMAR`` veces."""
        pendientes = self.sudo().search([('estado', '=', 'pendiente')], order='id', limit=limite)
        en_prueba = modules.module.current_test
        for envio in pendientes:
            try:
                with self.env.cr.savepoint():
                    envio._procesar_uno()
            except Exception as error:  # noqa: BLE001 - un correo nunca rompe la cola ni la factura
                intentos = envio.intentos + 1
                valores = {'intentos': intentos, 'motivo': (str(error) or type(error).__name__)[:250]}
                if intentos >= MAX_ARMAR:
                    _logger.exception('DCASA_CORREO no se pudo preparar el envío %s (intento %s, se da por fallido)',
                                      envio.id, intentos)
                    valores.update({'estado': 'fallido', 'causa': 'error'})
                else:
                    _logger.warning('DCASA_CORREO no se pudo preparar el envío %s (intento %s de %s): se reintenta',
                                    envio.id, intentos, MAX_ARMAR, exc_info=True)
                envio.write(valores)
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
        config = correo._config()
        if self.tipo in ('factura', 'abono'):
            # Lo que pidió una persona («mándasela», Brian) sale; lo automático del pago, solo si sigue encendido.
            if not (self.huella or '').startswith('manual:') and not config['al_pagar']:
                return self._omitir('apagado', self.env._(
                    'Se apagó «Mandar la factura al registrar un pago» antes de enviarlo.'))
            return self._procesar_factura()
        if self.tipo == 'recordatorio':
            if not config['recordatorio']:
                return self._omitir('apagado', self.env._(
                    'Se apagó «Recordar el abono antes de que venza» antes de enviarlo.'))
            return self._procesar_recordatorio()
        if self.tipo == 'bienvenida':
            if not config['bienvenida']:
                return self._omitir('apagado', self.env._(
                    'Se apagó «Bienvenida a clientes nuevos» antes de enviarla.'))
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
        """El PDF NUEVO de la factura (con lo pagado hasta hoy): el mismo papel y el mismo nombre que «Imprimir» y
        «Enviar». Con saldo es el papel de ABONO (dcasa_invoice: título «Abono», SALDO POR PAGAR) y se llama
        «Abono INV_…pdf». No reemplaza el PDF guardado de la factura."""
        informe = self.env['account.move.send']._get_default_pdf_report_id(move)
        contenido, tipo = self.env['ir.actions.report'].with_company(move.company_id).with_context(
            force_report_rendering=True)._render_qweb_pdf(informe, [move.id])
        if tipo != 'pdf' or not contenido:
            raise UserError(self.env._('No se pudo armar el PDF de la factura %s.', move.name))
        return contenido, move._get_invoice_report_filename(report=informe)

    # ------------------------------------------------------------------
    # Recordatorio del abono (D3)
    # ------------------------------------------------------------------

    @api.model
    def _encolar_recordatorios(self):
        """Cada mañana (cron de ``dcasa_abonos``): un recordatorio por cada abono que vence en los próximos días
        (``dcasa_abonos.aviso_dias``, 5 de fábrica) y que todavía no lo recibió para ESE vencimiento. La huella es
        ``factura:vencimiento``: si el cron corre dos veces, o el abono sigue ahí mañana, no se repite. Uno que no salió
        por falta de correo vuelve a la cola si el cliente ya tiene correo y sigue dentro del plazo."""
        correo = self.env['dcasa.correo']
        if not correo._activo_para_clientes() or not correo._config()['recordatorio']:
            return self.browse()
        Move = self.env['account.move'].sudo()
        hoy = fields.Date.context_today(self)
        hasta = hoy + timedelta(days=Move._dcasa_aviso_dias())
        facturas = Move.search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                                ('payment_state', '=', 'partial'), ('dcasa_abono_vence', '>=', hoy),
                                ('dcasa_abono_vence', '<=', hasta)], order='dcasa_abono_vence, id')
        nuevos = self.browse()
        for move in facturas:
            if not self._factura_cuenta(move):
                continue
            nuevos |= self._crear_si_no_existe({
                'tipo': 'recordatorio', 'huella': f'{move.id}:{move.dcasa_abono_vence.isoformat()}',
                'saldo_centavos': centavos(move.amount_residual), 'move_id': move.id,
                'partner_id': move.commercial_partner_id.id,
            }, rearmar=CAUSAS_QUE_SE_REARMAN)
        if nuevos:
            self.env.ref('dcasa_correo.ir_cron_dcasa_correo_cola').sudo()._trigger()
        return nuevos

    def _procesar_recordatorio(self):
        correo = self.env['dcasa.correo']
        move = self.move_id.sudo()
        vence = move.dcasa_abono_vence.isoformat() if move and move.dcasa_abono_vence else ''
        if (not move or move.state != 'posted' or move.payment_state != 'partial'
                or not (self.huella or '').endswith(f':{vence}') or not vence):
            return self._omitir('cambio', self.env._(
                'El abono cambió antes de enviar el recordatorio (se pagó, se canceló o cambió el vencimiento).'))
        destino = correo._destino(move)
        if not destino:
            cliente = move.partner_id.display_name or move.commercial_partner_id.display_name
            return self._omitir('sin_correo', self.env._(
                'No se envió el recordatorio: falta el correo de %s o está mal escrito.', cliente))
        mensaje = correo._postear(move, self.env.ref('dcasa_correo.plantilla_recordatorio_abono'), destino,
                                  tipo='recordatorio', titular=self.env._('TU ABONO VENCE PRONTO'))
        self.write({'estado': 'enviado', 'message_id': mensaje.id, 'correo': destino.email_normalized,
                    'saldo_centavos': centavos(move.amount_residual), 'causa': False, 'motivo': False})
        correo._disparar_cola()
        return True

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
        if self.search_count([('tipo', '=', 'bienvenida'), ('estado', '=', 'enviado'), ('id', '!=', self.id),
                              ('correo', '=', destino.email_normalized)], limit=1):
            # Otra ficha de la misma persona (repetida) ya se la llevó: una sola bienvenida por persona.
            return self._omitir('repetida', self.env._(
                'Ese correo ya recibió la bienvenida con otra ficha (¿cliente repetido?).'))
        mensaje = correo._postear(ficha, self.env.ref('dcasa_correo.plantilla_bienvenida'), destino,
                                  tipo='bienvenida')
        self.write({'estado': 'enviado', 'message_id': mensaje.id, 'correo': destino.email_normalized,
                    'causa': False, 'motivo': False})
        correo._disparar_cola()
        return True
