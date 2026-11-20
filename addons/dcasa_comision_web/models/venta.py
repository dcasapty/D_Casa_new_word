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
import hashlib
import logging
from decimal import ROUND_HALF_UP, Decimal

from odoo import SUPERUSER_ID, api, fields, models, modules, tools
from odoo.exceptions import ConcurrencyError, UserError
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY

from . import calculo
from .movimiento import dia_de_panama

_logger = logging.getLogger(__name__)
# Choques de concurrencia que Odoo repite solo (con una foto nueva de la base): nunca se tragan.
CONCURRENCIA = (ConcurrencyError, *PG_CONCURRENCY_EXCEPTIONS_TO_RETRY)

PAGADA = ('paid', 'in_payment')
LLAVE_DE_VENTA = 731_900_102          # una sola llave por venta (reconciliar)
LLAVE_DE_CREACION = 731_900_104       # anotar la venta de una factura por primera vez
COMO_LLEGO = [('web', 'Página'), ('tienda', 'Pagó en tienda'), ('andres', 'Andrés'), ('juan', 'Juan')]
FORMAS_DE_PAGO = [('pasarela', 'Pasarela'), ('a_mano', 'Transferencia o Yappy'), ('en_tienda', 'En la tienda')]
LOTE = 200


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
    creado_por_id = fields.Many2one('res.users', 'Carrito abierto por', readonly=True,
                                    help='Quién abrió el carrito de la página (dcasa_creada_por_id del pedido).')
    tocada_por_id = fields.Many2one('res.users', 'Lo cambió el equipo', readonly=True,
                                    help='La última persona del equipo que cambió el cliente o las líneas del pedido '
                                         '(dcasa_tocada_por_id del pedido).')
    creado_por_personal = fields.Boolean(
        'Carrito de alguien del equipo', readonly=True, index=True,
        help='Una persona del equipo (un usuario interno, no un visitante ni el asistente Juan) abrió el carrito o '
             'cambió su cliente o sus líneas. Cotizar en la página y pagar en la tienda SÍ cuenta (decisión de '
             'Gerencia): esto es la vigilancia para ver quién lo hace.')
    cobro_atrasado = fields.Boolean(
        'Cobro con fecha atrasada', readonly=True, index=True,
        help='La fecha del pago es de dos días o más antes del día en que se anotó la venta. El día de cobro lo '
             'teclea quien registra el pago y decide si la venta es del sitio o de una vendedora: esto es la '
             'vigilancia para verlo (los bloqueos contables del periodo lo frenan, si existen).')
    cobro_adelantado = fields.Boolean(
        'Cobro con fecha futura', readonly=True, index=True,
        help='La fecha del pago es posterior al día en que se anotó la venta. Una fecha futura no escoge una versión '
             'de las reglas que todavía no rige: la venta se calcula con la versión de HOY. Es la vigilancia para ver '
             'quién teclea pagos con fecha adelantada.')
    nota_sin_producto = fields.Boolean(
        'Una nota trae líneas sin producto', readonly=True, index=True,
        help='Una nota de crédito de esta factura trae líneas sin producto (escritas a mano): no se puede saber si '
             'devuelven un mueble o el envío, así que se restan de lo vendido. Revísala: si devolvía solo el envío, la '
             'base queda más baja de lo que debería.')
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
    devuelto_envio_centavos = fields.Integer(readonly=True)
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
    huella = fields.Char('Huella de la factura', readonly=True, copy=False,
                         help='Resumen de lo que la factura era la última vez que se comparó con el libro (estado, '
                              'pago, notas de crédito y conciliaciones): armar y aprobar solo recomponen las ventas '
                              'cuya huella cambió. Interna.')
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
                  'comisionada': ['&', ('reglas_id', '!=', False), ('cobrada', '=', True)],
                  'revertida': ['&', ('reglas_id', '!=', False), ('cobrada', '=', False)]}
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
        productos_de_envio = self.env['product.product']      # los que esta factura cobró como envío
        for linea in lineas:
            en_linea = linea.sale_line_ids.filtered(lambda sl: sl.order_id.dcasa_venta_online)
            if not en_linea:
                continue
            ordenes |= en_linea.order_id
            importe = calculo.a_centavos(-linea.balance)
            if any(sl.is_delivery for sl in en_linea) or linea.product_id in fletes:
                c['envio'] += importe
                productos_de_envio |= linea.product_id
            elif importe < 0 and any(sl.is_downpayment for sl in en_linea):
                # El anticipo que se resta en la factura final ya se contó en la factura del anticipo: resta de lo
                # vendido en las dos posiciones del interruptor de descuentos (no es un descuento de precio).
                c['productos'] += importe
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
        lineas_de_notas = self.env['account.move.line'].browse()
        for nota in notas:
            lineas_de_notas |= nota.line_ids.filtered(lambda ln: ln.display_type == 'product')
        # Una línea de la nota es de envío si su producto es flete o es el mismo con que la factura cobró el envío.
        fletes_devueltos = productos_de_flete(lineas_de_notas.product_id) | productos_de_envio
        devuelto = devuelto_envio = 0.0
        for nota, fraccion in notas.items():
            de_envio = sum(abs(ln.balance) for ln in nota.line_ids
                           if ln.display_type == 'product' and ln.product_id in fletes_devueltos)
            devuelto += (abs(nota.amount_untaxed_signed) - de_envio) * fraccion
            devuelto_envio += de_envio * fraccion
        c['devuelto'] = calculo.a_centavos(devuelto * factor)
        c['devuelto_envio'] = calculo.a_centavos(devuelto_envio * factor)
        c['devuelto_itbms'] = calculo.a_centavos(sum(abs(n.amount_tax_signed) * fr for n, fr in notas.items()) * factor)
        primera = ordenes.invoice_ids.filtered(
            lambda f: f.state == 'posted' and f.move_type == 'out_invoice').sorted('id')[:1]
        if primera == move:
            c['pasarela'] = calculo.a_centavos(sum(
                ordenes.transaction_ids.filtered(lambda t: t.state in ('done', 'authorized')).mapped(
                    'dcasa_comision_pasarela')))
        return c, ordenes

    @api.model
    def _notas_de(self, move):
        """``{nota: fracción}``: las notas de crédito publicadas que restan de esta factura y qué parte de cada una le
        toca. La que la revierte cuenta entera; la que se aplicó suelta (sin enlazar), solo por lo que de verdad se
        aplicó a ESTA factura: una nota de 600 repartida entre dos facturas resta 600 en total, no 600 en cada una."""
        Move = self.env['account.move'].sudo()
        notas = {n: 1.0 for n in move.reversal_move_ids.filtered(
            lambda n: n.state == 'posted' and n.move_type == 'out_refund')}
        cuentas = move.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        aplicado = {}
        for parcial in cuentas.matched_debit_ids | cuentas.matched_credit_ids:
            otra = parcial.debit_move_id if parcial.credit_move_id in cuentas else parcial.credit_move_id
            nota = Move.browse(otra.move_id.id)
            if nota != move and nota.move_type == 'out_refund' and nota.state == 'posted' and nota not in notas:
                aplicado[nota] = aplicado.get(nota, 0.0) + parcial.amount
        for nota, monto in aplicado.items():
            total = abs(nota.amount_total_signed)
            notas[nota] = min(1.0, monto / total) if total else 0.0
        return notas

    @api.model
    def _hay_nota_sin_producto(self, move):
        """¿Alguna nota de crédito que resta de esta factura trae líneas sin producto? No se puede saber si devuelven un
        mueble o el envío: se restan de lo vendido (decisión de la segunda revisión) y aquí se avisa."""
        return any(ln.display_type == 'product' and not ln.product_id
                   for nota in self._notas_de(move) for ln in nota.line_ids)

    @api.model
    def _dia_de_cobro(self, move):
        dias, _notas = self.env['dcasa.nomina.meta.bono']._dias_de_cobro(move)
        return dias.get(move.id) or move.invoice_date or fields.Date.context_today(self)

    @api.model
    def _hoy(self):
        """Hoy, fecha de Panamá (no la del servidor)."""
        return fields.Date.context_today(self.with_context(tz='America/Panama'))

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
    def _es_del_equipo(self, ordenes):
        """¿Alguien del equipo (un usuario interno) abrió el carrito de estos pedidos o cambió su cliente o sus líneas?
        El asistente Juan y los visitantes son usuarios de portal o públicos: no cuentan como del equipo."""
        ordenes = ordenes.sudo()
        return bool(ordenes.dcasa_creada_por_id.filtered(lambda u: not u.share) or ordenes.dcasa_tocada_por_id)

    @api.model
    def _atendida_por_vendedora(self, ordenes):
        juan = self.env.ref('dcasa_conversaciones.user_juan', raise_if_not_found=False)
        return any(o.user_id and o.user_id.id != SUPERUSER_ID and o.user_id != juan for o in ordenes.sudo())

    # ------------------------------------------------------------------
    # Anotar
    # ------------------------------------------------------------------

    @api.model
    def _registrar(self, move):
        """Anota la fila de una factura del sitio pagada por completo (si todavía no está) y deja el libro al día.
        Idempotente: el gancho de pago puede llamarse más de una vez. Devuelve la fila o vacío."""
        move = move.sudo()
        if not self._es_del_sitio(move) or not self._pagada(move):
            return self.browse()
        existente = self.sudo().search([('move_id', '=', move.id)], limit=1)
        if existente:
            existente._reconciliar()
            return existente
        # La venta todavía no existe: se cuida que dos cobros a la vez no la creen dos veces (y, por si acaso, la fila
        # es única por factura). Una vez creada, toda la comparación con el libro usa la llave de la VENTA.
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LLAVE_DE_CREACION, move.id])
        existente = self.sudo().search([('move_id', '=', move.id)], limit=1)
        if existente:
            existente._reconciliar()
            return existente
        company = move.company_id
        dia = self._dia_de_cobro(move)
        # El corte es el DÍA DE COBRO (hora de Panamá), igual que para las vendedoras, pero un pago con fecha futura
        # no escoge una versión que todavía no rige: ver ``reglas._vigente_para_cobro``.
        reglas = self.env['dcasa.web.reglas']._vigente_para_cobro(company, dia)
        c, ordenes = self._componentes(move)
        forma = self._forma_de_pago(ordenes)
        venta = self.sudo().create({
            'move_id': move.id, 'factura': move.name, 'fecha_factura': move.invoice_date, 'company_id': company.id,
            'fecha_cobro': dia, 'mes': dia.replace(day=1), 'cobrada': True, 'forma_pago': forma,
            'como_llego': self._como_llego(ordenes, forma),
            'atendida_por_vendedora': self._atendida_por_vendedora(ordenes),
            'cobro_atrasado': (self._hoy() - dia).days >= 2, 'cobro_adelantado': dia > self._hoy(),
            'nota_sin_producto': self._hay_nota_sin_producto(move),
            'creado_por_id': ordenes[:1].dcasa_creada_por_id.id or False,
            'tocada_por_id': ordenes.dcasa_tocada_por_id[:1].id or False,
            'creado_por_personal': self._es_del_equipo(ordenes),
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
        de las reglas mueven el libro; las que solo se midieron no cobran nunca.

        **Un re-cobro** (se canceló el pago y se registró otra vez, o se repuso con otra fecha) cambia el día en que la
        factura quedó pagada: la venta cierra lo anotado con la versión anterior (un reverso, asiento contrario) y se
        calcula de nuevo con la fecha y la versión que rigen ese día (``_cobrar_otra_vez``)."""
        Libro = self.env['dcasa.web.movimiento']
        huellas = self.sudo()._huellas()
        dias, _notas = self.env['dcasa.nomina.meta.bono']._dias_de_cobro(self.sudo().move_id)
        for venta in self.sudo():
            move = venta.move_id
            self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LLAVE_DE_VENTA, venta.id])
            pagada = self._pagada(move) if move else False       # una factura borrada ya no está cobrada
            antes_devuelto, antes_cobrada = venta.devuelto_centavos, venta.cobrada
            if move and move.state == 'posted':
                c, _ordenes = self._componentes(move)
                self._escribir_si_cambio(venta, {**self._valores_de_componentes(c), 'cobrada': pagada,
                                                 'huella': huellas.get(venta.id),
                                                 'nota_sin_producto': self._hay_nota_sin_producto(move)})
            else:
                c = {clave: venta[f'{clave}_centavos'] for clave in calculo.COMPONENTES}
                self._escribir_si_cambio(venta, {'cobrada': False, 'huella': huellas.get(venta.id)})
            recobro = None
            dia_real = dias.get(move.id) if move else None
            if pagada and dia_real and dia_real != venta.fecha_cobro:
                recobro = dia_real
                if self._cobrar_otra_vez(venta, dia_real):
                    antes_cobrada = False
            reglas = venta.reglas_id
            if not reglas:
                continue
            base = calculo.base_de_la_venta(c, reglas._opciones())
            self._escribir_si_cambio(venta, {'base_centavos': base})
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
                                                   antes_cobrada, recobro)
                Libro._asentar(self.env['hr.employee'].sudo().browse(empleado_id), tipo, diferencia, venta.company_id,
                               venta_id=venta.id, reglas_id=reglas.id, motivo=motivo)

    def _cobrar_otra_vez(self, venta, dia):
        """La factura de ``venta`` quedó pagada por completo otro día (``dia``): se canceló el pago y se registró otra
        vez, o se repuso o se corrigió con otra fecha. El día de cobro decide qué versión de las reglas le toca y de
        quién es la venta (el bono de las vendedoras ya usa el día en vivo): si aquí se quedara el día viejo, la venta
        saldría de nadie o de las dos partes.

        La venta se refresca (fecha, mes, versión, porcentaje y señales de fecha). Si la versión que rige ese día es
        OTRA, antes se cierra lo anotado con la anterior con una fila contraria por persona (el libro nunca se edita ni
        se borra, y lo que ya se haya liquidado o pagado no se toca: queda un saldo en contra que se compensa con lo
        nuevo); el resto de ``_reconciliar`` la anota otra vez con las reglas de ese día. Si es la misma versión, el
        libro no se mueve. Devuelve si cerró algo."""
        Libro = self.env['dcasa.web.movimiento']
        reglas = self.env['dcasa.web.reglas']._vigente_para_cobro(venta.company_id, dia)
        cerro = False
        if reglas != venta.reglas_id:
            asentado = {}
            for fila in Libro.sudo().search([('venta_id', '=', venta.id),
                                             ('tipo', 'in', ('venta', 'devolucion', 'reverso'))]):
                asentado[fila.empleado_id.id] = asentado.get(fila.empleado_id.id, 0) + fila.centavos
            for empleado_id, centavos in sorted(asentado.items()):
                if centavos:
                    Libro._asentar(self.env['hr.employee'].sudo().browse(empleado_id), 'reverso', -centavos,
                                   venta.company_id, venta_id=venta.id, reglas_id=venta.reglas_id.id or False,
                                   motivo=self.env._(
                                       'La factura %(factura)s se cobró otra vez el %(dia)s: se cierra lo anotado con '
                                       'la versión anterior y se calcula de nuevo con las reglas de ese día.',
                                       factura=venta.factura, dia=dia.strftime('%d/%m/%Y')))
                    cerro = True
        hoy = self._hoy()
        self._escribir_si_cambio(venta, {
            'fecha_cobro': dia, 'mes': dia.replace(day=1), 'reglas_id': reglas.id or False,
            'porcentaje': reglas.porcentaje if reglas else 0.0,
            'cobro_atrasado': venta.cobro_atrasado or (hoy - dia).days >= 2, 'cobro_adelantado': dia > hoy})
        return cerro

    @api.model
    def _escribir_si_cambio(self, venta, valores):
        """Escribe solo lo que cambió (no un UPDATE a cada fila cada vez que se compara)."""
        cambios = {clave: valor for clave, valor in valores.items() if venta[clave] != valor}
        if cambios:
            venta.write(cambios)

    def _huellas(self):
        """``{id de venta: huella}`` de lo que de verdad pasa hoy con cada factura (estado, estado de pago, notas de
        crédito con el producto de cada línea, conciliaciones con su fecha y lo que cobró la pasarela), en UNA consulta
        para todas. Dos huellas iguales quieren decir que la factura no cambió desde la última comparación con el
        libro (si la pasarela guarda su cobro después del pago, la huella lo ve y armar no paga de más)."""
        if not self.ids:
            return {}
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT v.id, COALESCE(m.state, ''), COALESCE(m.payment_state, ''),
                   COALESCE((SELECT string_agg(n.id::text || ':' || n.state || ':' || n.amount_untaxed_signed::text
                                               || ':' || n.amount_tax_signed::text || ':' || COALESCE((
                                                   SELECT string_agg(COALESCE(nl.product_id, 0)::text, '.'
                                                                     ORDER BY nl.id)
                                                     FROM account_move_line nl
                                                    WHERE nl.move_id = n.id AND nl.display_type = 'product'), ''),
                                               ',' ORDER BY n.id)
                               FROM account_move n
                              WHERE n.reversed_entry_id = m.id AND n.move_type = 'out_refund'), ''),
                   COALESCE((SELECT string_agg(p.id::text || ':' || p.amount::text || ':' || p.max_date::text, ','
                                               ORDER BY p.id)
                               FROM account_move_line l
                               JOIN account_partial_reconcile p ON p.debit_move_id = l.id OR p.credit_move_id = l.id
                              WHERE l.move_id = m.id), ''),
                   COALESCE((SELECT string_agg(t.id::text || ':' || t.state || ':'
                                               || COALESCE(t.dcasa_comision_pasarela, 0)::text, ',' ORDER BY t.id)
                               FROM payment_transaction t
                              WHERE t.state IN ('done', 'authorized') AND t.id IN (
                                    SELECT x.transaction_id
                                      FROM account_move_line l
                                      JOIN sale_order_line_invoice_rel r ON r.invoice_line_id = l.id
                                      JOIN sale_order_line sl ON sl.id = r.order_line_id
                                      JOIN sale_order_transaction_rel x ON x.sale_order_id = sl.order_id
                                     WHERE l.move_id = m.id)), '')
              FROM dcasa_web_venta v
              LEFT JOIN account_move m ON m.id = v.move_id
             WHERE v.id IN %s""", [tuple(self.ids)])
        return {fila[0]: hashlib.md5('|'.join(fila[1:]).encode()).hexdigest() for fila in self.env.cr.fetchall()}

    def _tipo_y_motivo(self, venta, move, diferencia, hay_filas, pagada, antes_devuelto, antes_cobrada, recobro=None):
        """Qué tipo de fila es la diferencia y qué motivo lleva (se lo enseña al que recibe tal cual)."""
        nombre = move.name or venta.factura
        if not hay_filas:
            return 'venta', self.env._('Venta del sitio: factura %s pagada.', nombre)
        if recobro and pagada and diferencia > 0:
            return 'venta', self.env._(
                'La factura %(factura)s se cobró otra vez el %(dia)s: se anota con las reglas de ese día '
                '(versión %(version)s).', factura=nombre, dia=recobro.strftime('%d/%m/%Y'),
                version=venta.reglas_id.numero)
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
    def _confirmar_lote(self):
        """Confirma lo hecho hasta aquí (el barrido nocturno suelta así los candados de cada lote en vez de retenerlos
        todos hasta el final). En las pruebas no confirma nada (una sola transacción)."""
        if not (tools.config['test_enable'] or modules.module.current_test):
            self.env.cr.commit()

    @api.model
    def _atribuir_a_las_reglas(self):
        """Las ventas que se midieron sin reglas pero cuyo DÍA DE COBRO ya cae en una versión: un cobro de las 8 de la
        mañana, anotado antes de que Gerencia guardara esa mañana la primera versión, que rige desde el inicio de ese
        día. Para las vendedoras esa venta ya no cuenta (corte por día de cobro); si aquí no se atribuyera al sitio, no
        sería de nadie. Idempotente; solo toca lo cobrado el día en que rige una versión o después."""
        Reglas = self.env['dcasa.web.reglas']
        atribuidas = 0
        for company in Reglas.sudo().search([('anulada', '=', False)]).company_id:
            primera = Reglas._primera(company)
            if not primera:
                continue
            for venta in self.sudo().search([
                    ('company_id', '=', company.id), ('reglas_id', '=', False), ('cobrada', '=', True),
                    ('fecha_cobro', '>=', dia_de_panama(primera.rige_desde))]):
                reglas = Reglas._vigente_para_cobro(company, venta.fecha_cobro)
                if not reglas:
                    continue
                try:
                    with self.env.cr.savepoint():
                        venta.write({'reglas_id': reglas.id, 'porcentaje': reglas.porcentaje})
                        venta._reconciliar()
                        atribuidas += 1
                except CONCURRENCIA:
                    raise
                except Exception:  # noqa: BLE001 — una venta rara no detiene a las demás
                    _logger.exception('Comisión web: no se pudo atribuir la venta %s a las reglas', venta.factura)
        return atribuidas

    @api.model
    def _poner_al_dia(self):
        """Compara con la verdad las ventas con comisión (también las «apagadas»: un pago que se repuso por una vía sin
        gancho, o una factura vuelta a borrador y publicada otra vez, vuelven a pagar) cuya factura CAMBIÓ desde la
        última vez (un pago revertido, repuesto, una factura anulada, borrada o con una nota de crédito nueva): lo usan,
        antes de sumar un centavo, cada liquidación al armarse o aprobarse. Mirar si algo cambió cuesta una sola
        consulta para todas (``_huellas``); solo se recomponen las que cambiaron. Devuelve cuántas se miraron. El
        barrido de cada noche sigue comparando todas.

        Un choque de concurrencia (otra transacción tocó lo mismo) se vuelve a lanzar: Odoo repite la operación con una
        foto nueva de la base. Tragárselo dejaba armar y aprobar con datos viejos."""
        self._atribuir_a_las_reglas()
        ventas = self.sudo().search([('reglas_id', '!=', False)])
        actuales = ventas._huellas()
        for venta in ventas.filtered(lambda v: v.huella != actuales.get(v.id)):
            try:
                with self.env.cr.savepoint():
                    venta._reconciliar()
            except CONCURRENCIA:
                raise
            except Exception:  # noqa: BLE001
                _logger.exception('Comisión web: no se pudo comparar la venta %s con el libro', venta.factura)
        return len(ventas)

    @api.model
    def _barrido(self):
        """Cada noche: (a) anota las facturas del sitio pagadas que no tienen fila (un gancho que falló) y (b) compara
        el libro con la verdad de cada venta anotada con reglas, asentando la diferencia. Un error en una venta no
        frena a las demás y queda en el registro. Va por lotes (``LOTE`` ventas) y confirma cada uno."""
        Move = self.env['account.move'].sudo()
        nuevas, intentadas = 0, set()
        while True:
            anotadas = self.sudo().search([]).move_id.ids
            pendientes = Move.search([
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('dcasa_historica', '=', False),
                ('payment_state', 'in', PAGADA), ('id', 'not in', list(set(anotadas) | intentadas)),
                ('invoice_line_ids.sale_line_ids.order_id.dcasa_venta_online', '=', True)], limit=LOTE, order='id')
            hechas = 0
            intentadas |= set(pendientes.ids)
            for move in pendientes:
                try:
                    with self.env.cr.savepoint():
                        hechas += bool(self._registrar(move))
                except CONCURRENCIA:
                    raise
                except Exception:  # noqa: BLE001 — una factura rara no detiene a las demás
                    _logger.exception('Comisión web: no se pudo anotar la factura %s en el barrido', move.name)
            nuevas += hechas
            self._confirmar_lote()
            if not pendientes:
                break
        self._atribuir_a_las_reglas()
        self._confirmar_lote()
        revisadas = 0
        ids = self.sudo().search([('reglas_id', '!=', False)], order='id').ids
        for desde in range(0, len(ids), LOTE):
            for venta in self.sudo().browse(ids[desde:desde + LOTE]):
                try:
                    with self.env.cr.savepoint():
                        venta._reconciliar()
                        revisadas += 1
                except CONCURRENCIA:
                    raise
                except Exception:  # noqa: BLE001
                    _logger.exception('Comisión web: no se pudo comparar la venta %s con el libro', venta.factura)
            self._confirmar_lote()
        _logger.info('Comisión web: el barrido anotó %s ventas nuevas y comparó %s con el libro.', nuevas, revisadas)
        return nuevas, revisadas

    @api.model
    def _cron_barrido(self):
        self._barrido()
        self.env['dcasa.web.movimiento']._cron_tarifa()
