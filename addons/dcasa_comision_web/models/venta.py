"""Las ventas del sitio web: una fila por factura (medición SIEMPRE activa) y su paso al libro.

Gerencia quiere **medir las ventas por internet como una sucursal**: por eso cada factura pagada por completo que
sale de
un pedido online (``dcasa_base.models.venta_online``) tiene su fila aquí, **aunque todavía no haya ninguna versión de
las reglas ni porcentaje**. La fila guarda los componentes de la venta (lo vendido, descuentos, envío, ITBMS,
devoluciones, lo que cobró la pasarela) y cómo llegó y cómo se pagó. Solo con una versión vigente, además, se calcula la
comisión y se anota en el libro (``dcasa.web.movimiento``).

**Cuándo cuenta una venta**: cuando su factura queda pagada por completo (el mismo momento y la misma definición del
bono por meta: ``dcasa.nomina.meta.bono._dias_de_cobro``; «en proceso de pago» también). Los abonos a medias no cuentan.

**Solo hacia adelante**: una venta cobrada antes de que rija la primera versión se mide y NUNCA cobra.

**Un error nunca frena un cobro**: el gancho de pago corre dentro de un savepoint y con el error al registro. Cada noche
un barrido anota lo que el gancho no alcanzó y **compara el libro con la verdad** de cada venta (devoluciones, notas
aplicadas sueltas, pago revertido, factura cancelada o vuelta a borrador) asentando la diferencia como fila contraria.
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError

from . import calculo

_logger = logging.getLogger(__name__)

PAGADA = ('paid', 'in_payment')
LLAVE_DE_VENTA = 731_900_102
COMO_LLEGO = [('web', 'Compró en la página'), ('tienda', 'Cotizó en la página y pagó en la tienda'),
              ('andres', 'Con Andrés (el chat de la tienda)'), ('juan', 'Llegó por Juan y compró solo')]
FORMAS_DE_PAGO = [('pasarela', 'Pasarela de pago'), ('a_mano', 'Transferencia o Yappy (lo registra Caja)'),
                  ('en_tienda', 'En la tienda')]
LOTE = 500


class DcasaWebVenta(models.Model):
    _name = 'dcasa.web.venta'
    _description = 'Venta del sitio web (una factura)'
    _order = 'fecha_cobro desc, id desc'
    _rec_name = 'factura'

    move_id = fields.Many2one('account.move', 'Factura', readonly=True, index='btree_not_null', ondelete='set null')
    factura = fields.Char('Número de factura', readonly=True, index=True,
                          help='Copia del número: quien recibe lee la fila aunque no tenga permiso sobre facturas.')
    fecha_factura = fields.Date('Fecha de la factura', readonly=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, readonly=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    fecha_cobro = fields.Date('Cobrada el', readonly=True, index=True,
                              help='El día en que la factura quedó pagada por completo.')
    registrada_en = fields.Datetime('Anotada el', readonly=True, default=fields.Datetime.now)
    mes = fields.Date('Mes del cobro', readonly=True, index=True,
                      help='El primer día del mes (Panamá) en que se cobró: para medir mes a mes.')
    como_llego = fields.Selection(COMO_LLEGO, 'Cómo llegó', readonly=True, index=True)
    forma_pago = fields.Selection(FORMAS_DE_PAGO, 'Cómo pagó', readonly=True, index=True)
    atendida_por_vendedora = fields.Boolean(
        'Una vendedora la atendió', readonly=True,
        help='El pedido tiene vendedora asignada (por ejemplo la que lo confirmó). Sigue siendo venta online.')
    cobrada = fields.Boolean('Pagada hoy', readonly=True, index=True,
                             help='Si la factura sigue pagada por completo (un pago revertido o una factura anulada la '
                                  'apaga y se reversa lo anotado).')
    # Los componentes, en centavos (ver calculo.COMPONENTES).
    productos_centavos = fields.Integer(readonly=True)
    descuento_lineas_centavos = fields.Integer(readonly=True)
    descuento_negativas_centavos = fields.Integer(readonly=True)
    envio_centavos = fields.Integer(readonly=True)
    itbms_centavos = fields.Integer(readonly=True)
    devuelto_centavos = fields.Integer(readonly=True)
    devuelto_itbms_centavos = fields.Integer(readonly=True)
    pasarela_centavos = fields.Integer(readonly=True)
    productos = fields.Monetary('Lo vendido', compute='_compute_montos', store=True,
                                help='Los muebles vendidos por internet, sin ITBMS y con el descuento de cada línea.')
    envio = fields.Monetary('Envío', compute='_compute_montos', store=True)
    devuelto = fields.Monetary('Devuelto', compute='_compute_montos', store=True)
    # Lo que se calculó con la versión que regía al cobrar (vacío si todavía no había ninguna).
    reglas_id = fields.Many2one('dcasa.web.reglas', 'Reglas con que se calculó', readonly=True, ondelete='restrict')
    porcentaje = fields.Float('Porcentaje', readonly=True, digits=(6, 3))
    base_centavos = fields.Integer(readonly=True)
    base = fields.Monetary('Base de la comisión', compute='_compute_montos', store=True)
    comision_centavos = fields.Integer('Comisión (centavos)', compute='_compute_comision', store=True)
    comision = fields.Monetary('Comisión', compute='_compute_comision', store=True)
    movimiento_ids = fields.One2many('dcasa.web.movimiento', 'venta_id', 'Libro', readonly=True)
    estado = fields.Selection(
        [('medida', 'Solo medida'), ('comisionada', 'Con comisión'), ('revertida', 'Revertida')],
        compute='_compute_estado', search='_search_estado')

    _factura_unica = models.Constraint('UNIQUE(move_id)', 'Esa factura ya está en las ventas del sitio.')

    @api.depends('productos_centavos', 'envio_centavos', 'devuelto_centavos', 'base_centavos')
    def _compute_montos(self):
        for venta in self:
            venta.productos = venta.productos_centavos / 100.0
            venta.envio = venta.envio_centavos / 100.0
            venta.devuelto = venta.devuelto_centavos / 100.0
            venta.base = venta.base_centavos / 100.0

    @api.depends('movimiento_ids.centavos', 'movimiento_ids.tipo')
    def _compute_comision(self):
        for venta in self:
            filas = venta.movimiento_ids.filtered(lambda m: m.tipo in ('venta', 'devolucion', 'reverso'))
            venta.comision_centavos = sum(filas.mapped('centavos'))
            venta.comision = venta.comision_centavos / 100.0

    @api.depends('reglas_id', 'cobrada')
    def _compute_estado(self):
        for venta in self:
            if not venta.reglas_id:
                venta.estado = 'medida'
            elif not venta.cobrada:
                venta.estado = 'revertida'
            else:
                venta.estado = 'comisionada'

    def _search_estado(self, operator, value):
        valores = [value] if isinstance(value, str) else list(value or [])
        if operator not in ('=', 'in'):
            raise ValueError('Solo se filtra el estado por igual a.')
        partes = {'medida': [('reglas_id', '=', False)],
                  'comisionada': [('reglas_id', '!=', False), ('cobrada', '=', True)],
                  'revertida': [('reglas_id', '!=', False), ('cobrada', '=', False)]}
        dominio = []
        for valor in valores:
            dominio = ['|', *dominio, *partes[valor]] if dominio else partes[valor]
        return dominio or [('id', '=', False)]

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._('Las ventas del sitio las anota el sistema: no se editan a mano.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _no_borrar(self):
        if not self.env.su:
            raise UserError(self.env._('Las ventas del sitio no se borran.'))

    # ------------------------------------------------------------------
    # Lo que de verdad pasó con la factura (la «verdad» contra la que se compara el libro)
    # ------------------------------------------------------------------

    @api.model
    def _es_del_sitio(self, move):
        return (move.move_type == 'out_invoice' and move.state == 'posted' and not move.dcasa_historica
                and move._dcasa_factor_online().get(move.id, 0.0) > 0.0)

    @api.model
    def _componentes(self, move):
        """``({componente: centavos}, ordenes)`` de la parte online de una factura, leída de la factura tal como está
        hoy: lo vendido, los descuentos, el envío, el ITBMS, lo devuelto y lo que cobró la pasarela."""
        from odoo.addons.dcasa_invoice.models.lineas import productos_de_flete
        c = dict.fromkeys(calculo.COMPONENTES, 0)
        lineas = move.line_ids.filtered(lambda ln: ln.display_type == 'product')
        fletes = productos_de_flete(lineas.product_id)
        ordenes = self.env['sale.order']
        for linea in lineas:
            en_linea = linea.sale_line_ids.filtered(lambda sl: sl.order_id.dcasa_venta_online)
            if not en_linea:
                continue
            ordenes |= en_linea.order_id
            importe = calculo.a_centavos(-linea.balance)
            if any(sl.is_delivery for sl in en_linea) or linea.product_id in fletes:
                c['envio'] += importe
            elif importe < 0:
                c['descuento_negativas'] += -importe
            else:
                c['productos'] += importe
                if linea.discount:
                    antes = (calculo.a_centavos(linea.price_unit * linea.quantity) if linea.discount >= 100
                             else int((Decimal(importe) / (1 - Decimal(str(linea.discount)) / 100)).quantize(
                                 Decimal(1), rounding=ROUND_HALF_UP)))
                    c['descuento_lineas'] += max(antes - importe, 0)
        factor = move._dcasa_factor_online().get(move.id, 0.0)
        c['itbms'] = calculo.a_centavos(move.amount_tax_signed * factor)
        notas = self._notas_de(move)
        c['devuelto'] = calculo.a_centavos(sum(abs(n.amount_untaxed_signed) for n in notas) * factor)
        c['devuelto_itbms'] = calculo.a_centavos(sum(abs(n.amount_tax_signed) for n in notas) * factor)
        primera = ordenes.invoice_ids.filtered(
            lambda f: f.state == 'posted' and f.move_type == 'out_invoice').sorted('id')[:1]
        if primera == move:
            c['pasarela'] = calculo.a_centavos(sum(
                ordenes.transaction_ids.filtered(lambda t: t.state in ('done', 'authorized')).mapped(
                    'dcasa_comision_pasarela')))
        return c, ordenes

    @api.model
    def _notas_de(self, move):
        """Las notas de crédito publicadas que restan de esta factura: la que la revierte y la que se aplicó a ella
        aunque no esté enlazada (como en el bono por meta)."""
        Move = self.env['account.move'].sudo()
        notas = move.reversal_move_ids.filtered(lambda n: n.state == 'posted' and n.move_type == 'out_refund')
        cuentas = move.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        parciales = cuentas.matched_debit_ids | cuentas.matched_credit_ids
        for parcial in parciales:
            for otro in (parcial.debit_move_id.move_id, parcial.credit_move_id.move_id):
                if otro != move and otro.move_type == 'out_refund' and otro.state == 'posted':
                    notas |= otro
        return Move.browse(notas.ids)

    @api.model
    def _dia_de_cobro(self, move):
        dias, _notas = self.env['dcasa.nomina.meta.bono']._dias_de_cobro(move)
        return dias.get(move.id) or move.invoice_date or fields.Date.context_today(self)

    @api.model
    def _pagada(self, move):
        return move.state == 'posted' and move.move_type == 'out_invoice' and move.payment_state in PAGADA

    # ------------------------------------------------------------------
    # Cómo llegó y cómo se pagó (para medir la sucursal web)
    # ------------------------------------------------------------------

    @api.model
    def _forma_de_pago(self, ordenes):
        pagos = ordenes.transaction_ids.filtered(lambda t: t.state in ('done', 'pending', 'authorized'))
        if any(t.provider_code != 'custom' for t in pagos):
            return 'pasarela'
        if not pagos or any(t.provider_id.custom_mode == 'cash_on_delivery' for t in pagos):
            return 'en_tienda'
        return 'a_mano'

    @api.model
    def _como_llego(self, ordenes, forma):
        if any(o.dcasa_via_andres for o in ordenes):
            return 'andres'
        if any(o._dcasa_chat_antes_de_comprar()[0] for o in ordenes):
            return 'juan'
        return 'tienda' if forma == 'en_tienda' else 'web'

    @api.model
    def _atendida_por_vendedora(self, ordenes):
        juan = self.env.ref('dcasa_conversaciones.user_juan', raise_if_not_found=False)
        return any(o.user_id and o.user_id.id != SUPERUSER_ID and o.user_id != juan for o in ordenes.sudo())

    # ------------------------------------------------------------------
    # Anotar
    # ------------------------------------------------------------------

    @api.model
    def _registrar(self, move, desde_barrido=False):
        """Anota la fila de una factura del sitio pagada por completo (si todavía no está) y deja el libro al día.
        Idempotente: el gancho de pago puede llamarse más de una vez. Devuelve la fila o vacío."""
        move = move.sudo()
        if not self._es_del_sitio(move) or not self._pagada(move):
            return self.browse()
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LLAVE_DE_VENTA, move.id])
        existente = self.sudo().search([('move_id', '=', move.id)], limit=1)
        if existente:
            existente._reconciliar()
            return existente
        company = move.company_id
        dia = self._dia_de_cobro(move)
        Reglas = self.env['dcasa.web.reglas']
        reglas = Reglas._vigente_el(company, dia) if desde_barrido else Reglas._vigente(company)
        c, ordenes = self._componentes(move)
        forma = self._forma_de_pago(ordenes)
        venta = self.sudo().create({
            'move_id': move.id, 'factura': move.name, 'fecha_factura': move.invoice_date, 'company_id': company.id,
            'fecha_cobro': dia, 'mes': dia.replace(day=1), 'cobrada': True, 'forma_pago': forma,
            'como_llego': self._como_llego(ordenes, forma),
            'atendida_por_vendedora': self._atendida_por_vendedora(ordenes),
            'reglas_id': reglas.id or False, 'porcentaje': reglas.porcentaje if reglas else 0.0,
            **self._valores_de_componentes(c),
        })
        venta._reconciliar()
        return venta

    def _valores_de_componentes(self, c):
        return {f'{clave}_centavos': valor for clave, valor in c.items()}

    def _reconciliar(self):
        """Compara el libro con la verdad de cada venta y asienta la DIFERENCIA como fila contraria (o fila nueva).
        Idempotente: dos llamadas seguidas no asientan nada la segunda vez. Solo las ventas anotadas con una versión
        de las reglas mueven el libro; las que solo se midieron no cobran nunca."""
        Libro = self.env['dcasa.web.movimiento']
        for venta in self.sudo():
            self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LLAVE_DE_VENTA, venta.id])
            move = venta.move_id
            if not move:
                continue
            pagada = self._pagada(move)
            antes_devuelto, antes_cobrada = venta.devuelto_centavos, venta.cobrada
            if move.state == 'posted':
                c, _ordenes = self._componentes(move)
                venta.write({**self._valores_de_componentes(c), 'cobrada': pagada})
            else:
                c = {clave: venta[f'{clave}_centavos'] for clave in calculo.COMPONENTES}
                venta.write({'cobrada': False})
            reglas = venta.reglas_id
            if not reglas:
                continue
            base = calculo.base_de_la_venta(c, reglas.opciones())
            venta.write({'base_centavos': base})
            debe = calculo.porcentaje_de(base, reglas.porcentaje) if pagada else 0
            partes = calculo.repartir(debe, [(r.empleado_id.id, r.porcentaje) for r in reglas.reparto_ids])
            filas = Libro.sudo().search([('venta_id', '=', venta.id),
                                         ('tipo', 'in', ('venta', 'devolucion', 'reverso'))])
            asentado = {}
            for fila in filas:
                asentado[fila.empleado_id.id] = asentado.get(fila.empleado_id.id, 0) + fila.centavos
            for empleado_id in sorted(set(partes) | set(asentado)):
                diferencia = partes.get(empleado_id, 0) - asentado.get(empleado_id, 0)
                if not diferencia:
                    continue
                tipo, motivo = self._tipo_y_motivo(venta, move, diferencia, bool(filas), pagada, antes_devuelto,
                                                   antes_cobrada)
                Libro._asentar(self.env['hr.employee'].sudo().browse(empleado_id), tipo, diferencia, venta.company_id,
                               venta_id=venta.id, reglas_id=reglas.id, motivo=motivo)

    def _tipo_y_motivo(self, venta, move, diferencia, hay_filas, pagada, antes_devuelto, antes_cobrada):
        """Qué tipo de fila es la diferencia y qué motivo lleva (se lo enseña al que recibe tal cual)."""
        nombre = move.name or venta.factura
        if not hay_filas:
            return 'venta', self.env._('Venta del sitio: factura %s pagada.', nombre)
        if not pagada:
            return 'reverso', self.env._('La factura %s ya no está pagada por completo (pago revertido, anulada o '
                                         'vuelta a borrador): se reversa lo anotado.', nombre)
        if diferencia > 0 and not antes_cobrada:
            return 'venta', self.env._('La factura %s volvió a quedar pagada.', nombre)
        if diferencia < 0:
            return 'devolucion', self.env._('Devolución de lo vendido en la factura %s (nota de crédito).', nombre)
        return 'reverso', self.env._('Se deshizo una devolución de la factura %s.', nombre)

    # ------------------------------------------------------------------
    # El barrido de cada noche
    # ------------------------------------------------------------------

    @api.model
    def _barrido(self):
        """Cada noche: (a) anota las facturas del sitio pagadas que no tienen fila (un gancho que falló) y (b)
        compara el
        libro con la verdad de cada venta anotada con reglas, asentando la diferencia. Un error en una venta no frena a
        las demás y queda en el registro."""
        Move = self.env['account.move'].sudo()
        anotadas = self.sudo().search([]).move_id.ids
        pendientes = Move.search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('dcasa_historica', '=', False),
            ('payment_state', 'in', PAGADA), ('id', 'not in', anotadas),
            ('invoice_line_ids.sale_line_ids.order_id.dcasa_venta_online', '=', True)], limit=LOTE, order='id')
        nuevas = 0
        for move in pendientes:
            try:
                with self.env.cr.savepoint():
                    nuevas += bool(self._registrar(move, desde_barrido=True))
            except Exception:  # noqa: BLE001 — una factura rara no detiene a las demás
                _logger.exception('Comisión web: no se pudo anotar la factura %s en el barrido', move.name)
        revisadas = 0
        for venta in self.sudo().search([('reglas_id', '!=', False)]):
            try:
                with self.env.cr.savepoint():
                    venta._reconciliar()
                    revisadas += 1
            except Exception:  # noqa: BLE001
                _logger.exception('Comisión web: no se pudo comparar la venta %s con el libro', venta.factura)
        _logger.info('Comisión web: el barrido anotó %s ventas nuevas y comparó %s con el libro.', nuevas, revisadas)
        return nuevas, revisadas

    @api.model
    def _cron_barrido(self):
        self._barrido()
        self.env['dcasa.web.movimiento']._cron_tarifa()
