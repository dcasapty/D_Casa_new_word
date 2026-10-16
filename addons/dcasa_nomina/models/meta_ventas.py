"""Bono por meta de ventas de quien vende en la tienda (decisión del jefe, 2026-10-16).

La regla, en palabras del jefe:

* Participa quien está en un departamento marcado «Participa en la meta de ventas» (el de Ventas) y tiene usuario
  en el sistema. Lo marca Gerencia en la ficha del departamento; al instalar se marca solo el que se llama «Ventas».
* Cuenta lo que esa persona vendió (el «Vendedor» de la factura) y el cliente **ya pagó completo**: la venta cuenta en
  el mes en que caja recibió el último pago (también en los apartados), **sin ITBMS**. Las notas de crédito de esas
  ventas restan (la que la revierte y la que se aplicó a la factura, aunque no esté enlazada); la de una venta que nunca
  contó (pagada antes de que rigiera la primera meta) no resta.
* Cada venta y cada nota cuenta **una sola vez**: si su mes ya entró en una planilla, cuenta en el primer mes abierto
  después (un pago que llega tarde con fecha atrasada no se pierde), y lo que ya está en un bono cerrado no vuelve a
  contar (un pago anulado y registrado de nuevo otro mes no paga dos veces).
* Si lo cobrado del mes **llega a la meta** (30,000), el bono es el **1 % de todo** lo cobrado (con 60,000, 600). Si no
  llega, no hay bono.
* Se paga en la **primera planilla quincenal del mes siguiente**, como comisión: paga seguro social, seguro educativo
  e ISR como el salario (la contadora lo confirma, docs/NOMINA.md). Si esa planilla no la incluye (le falta salario o
  fecha de ingreso), el bono queda por pagar y entra en la siguiente primera quincena que sí la incluya.
* Cada vendedora ve **solo lo suyo** en su Inicio; nunca lo que vendió la tienda ni sus gastos.

Las cifras (meta, porcentaje y el ritmo diario de guía) viven en «Meta de ventas» (Nómina › Configuración), con
vigencia por mes: se cambian desde un mes en adelante, y un mes ya pagado no cambia.
"""
from datetime import date

from babel.dates import format_date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import calculo

GRUPO = 'dcasa_nomina.group_nomina'
# Un apartado puede completar su pago meses después de facturado: se mira hasta un año atrás.
MESES_ATRAS = 12
PARAM_INICIALIZADA = 'dcasa_nomina.meta_ventas_inicializada'


def fin_de_mes(mes):
    return mes + relativedelta(day=31)


def total_sin_itbms(*grupos):
    """Lo cobrado sin ITBMS de unas facturas y notas (las notas restan: su monto ya viene en negativo)."""
    return calculo.r2(sum(movimiento.amount_untaxed_signed for grupo in grupos for movimiento in grupo))


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dcasa_meta_ventas = fields.Boolean(
        'Participa en la meta de ventas', groups=GRUPO,
        help='Quien esté en este departamento y tenga usuario participa en el bono por meta de ventas '
             '(Nómina › Bono por meta).')

    @api.model
    def _dcasa_marcar_ventas(self):
        """La primera vez marca el departamento que se llama «Ventas» (pedido del jefe). Después lo decide Gerencia
        en la ficha del departamento: esta función no vuelve a marcar nada aunque se desmarque."""
        Param = self.env['ir.config_parameter'].sudo()
        if Param.get_param(PARAM_INICIALIZADA):
            return
        self.sudo().search([('name', '=ilike', 'ventas')]).write({'dcasa_meta_ventas': True})
        Param.set_param(PARAM_INICIALIZADA, '1')


class DcasaNominaMetaRegla(models.Model):
    _name = 'dcasa.nomina.meta.regla'
    _description = 'Meta de ventas y bono (con vigencia por mes)'
    _order = 'company_id, fecha_desde desc'

    name = fields.Char(compute='_compute_name')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    fecha_desde = fields.Date('Rige desde el mes', required=True,
                              help='Primer día del mes desde el que rige esta meta.')
    meta_mensual = fields.Monetary('Meta del mes (sin ITBMS)', required=True,
                                   help='Lo que cada vendedora tiene que cobrar en el mes para ganar el bono.')
    porcentaje = fields.Float('Bono (% de lo cobrado)', required=True, digits=(5, 2),
                              help='Si llega a la meta, el bono es este porcentaje de TODO lo cobrado en el mes.')
    meta_diaria = fields.Monetary('Ritmo diario (guía)',
                                  help='Solo se le muestra a la vendedora como guía del día; no cambia el bono.')
    notas = fields.Char()

    _una_por_mes = models.Constraint('UNIQUE(company_id, fecha_desde)', 'Ya hay una meta que rige desde ese mes.')

    @api.depends('fecha_desde', 'meta_mensual', 'porcentaje')
    def _compute_name(self):
        for regla in self:
            desde = regla.fecha_desde.strftime('%m/%Y') if regla.fecha_desde else '—'
            regla.name = self.env._('Desde %(desde)s: meta %(meta)s, bono %(pct)s %%', desde=desde,
                                    meta=f'{regla.meta_mensual:,.2f}', pct=f'{regla.porcentaje:g}')

    @api.constrains('fecha_desde', 'meta_mensual', 'porcentaje', 'meta_diaria')
    def _check_cifras(self):
        for regla in self:
            if regla.fecha_desde.day != 1:
                raise ValidationError(self.env._('La meta rige desde el primer día de un mes.'))
            if regla.meta_mensual <= 0 or regla.meta_diaria < 0:
                raise ValidationError(self.env._('La meta del mes tiene que ser mayor que cero.'))
            if not 0 < regla.porcentaje <= 100:
                raise ValidationError(self.env._('El bono es un porcentaje entre 0 y 100.'))
            pagados = self.env['dcasa.nomina.meta.bono'].sudo().search_count([
                ('company_id', '=', regla.company_id.id), ('mes', '>=', regla.fecha_desde),
                ('estado', 'in', ('en_planilla', 'pagado'))])
            if pagados:
                raise ValidationError(self.env._(
                    'Desde ese mes ya hay bonos en una planilla: la meta solo cambia hacia adelante. Crea una nueva '
                    'que rija desde el mes siguiente.'))

    @api.ondelete(at_uninstall=False)
    def _no_borrar_usadas(self):
        Bono = self.env['dcasa.nomina.meta.bono'].sudo()
        if Bono.search_count([('regla_id', 'in', self.ids), ('estado', 'in', ('en_planilla', 'pagado'))]):
            raise UserError(self.env._('Esa meta ya se usó para pagar bonos: no se borra.'))
        # Los bonos por pagar que la usaban se vuelven a calcular con la meta que quede (cada día, o al abrir el menú).
        Bono.search([('regla_id', 'in', self.ids)]).unlink()

    @api.model
    def _vigente(self, mes, company):
        return self.sudo().search([('company_id', '=', company.id), ('fecha_desde', '<=', mes)],
                                  order='fecha_desde desc', limit=1)

    @api.model
    def _inicio(self, company):
        """El primer día en que rigió una meta en ``company`` (antes no hay programa), o False."""
        return self.sudo().search([('company_id', '=', company.id)], order='fecha_desde', limit=1).fecha_desde


class DcasaNominaMetaBono(models.Model):
    _name = 'dcasa.nomina.meta.bono'
    _description = 'Bono por meta de ventas (una persona, un mes)'
    _order = 'mes desc, empleado_id'

    empleado_id = fields.Many2one('hr.employee', 'Colaborador', required=True, index=True, readonly=True,
                                  ondelete='restrict')
    user_id = fields.Many2one('res.users', 'Usuario', readonly=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    mes = fields.Date('Mes', required=True, readonly=True, index=True)
    regla_id = fields.Many2one('dcasa.nomina.meta.regla', 'Meta aplicada', readonly=True, ondelete='restrict')
    meta = fields.Monetary('Meta', readonly=True)
    porcentaje = fields.Float('Bono (%)', readonly=True, digits=(5, 2))
    cobrado = fields.Monetary('Cobrado en el mes (sin ITBMS)', readonly=True)
    cumplio = fields.Boolean('Llegó a la meta', readonly=True)
    monto = fields.Monetary('Bono', readonly=True)
    factura_ids = fields.Many2many('account.move', 'dcasa_meta_bono_factura_rel', 'bono_id', 'move_id',
                                   'Facturas que cuentan', readonly=True)
    nota_ids = fields.Many2many('account.move', 'dcasa_meta_bono_nota_rel', 'bono_id', 'move_id',
                                'Notas de crédito que restan', readonly=True)
    linea_id = fields.Many2one('dcasa.nomina.linea', 'Línea de planilla', readonly=True, index=True,
                               ondelete='set null')
    # Sale de la planilla en la que está (sin guardarse: una planilla borrada o cancelada lo suelta sola).
    estado = fields.Selection([('abierto', 'Por pagar'), ('en_planilla', 'En planilla'), ('pagado', 'Pagado')],
                              compute='_compute_estado', search='_search_estado')
    actualizado = fields.Datetime('Calculado el', readonly=True)

    _uno_por_mes = models.Constraint('UNIQUE(empleado_id, mes)', 'Cada persona tiene un solo bono por mes.')

    ESTADOS_PLANILLA = {'pagado': ('confirmada', 'pagada'), 'en_planilla': ('borrador', 'calculada')}

    def _search_estado(self, operator, value):
        valores = [value] if isinstance(value, str) else list(value or [])
        if operator not in ('=', 'in'):
            raise UserError(self.env._('Solo se filtra el estado del bono por igual a.'))
        dominio = []
        for valor in valores:
            if valor == 'abierto':
                parte = ['|', ('linea_id', '=', False), ('linea_id.planilla_id.estado', '=', 'cancelada')]
            else:
                parte = [('linea_id.planilla_id.estado', 'in', self.ESTADOS_PLANILLA.get(valor, ()))]
            dominio = ['|', *dominio, *parte] if dominio else parte
        return dominio or [('id', '=', False)]

    @api.depends('linea_id', 'linea_id.planilla_id.estado')
    def _compute_estado(self):
        for bono in self:
            estado_planilla = bono.linea_id.planilla_id.estado
            if estado_planilla in ('confirmada', 'pagada'):
                bono.estado = 'pagado'
            elif estado_planilla in ('borrador', 'calculada'):
                bono.estado = 'en_planilla'
            else:
                bono.estado = 'abierto'

    # ------------------------------------------------------------------
    # Lo cobrado
    # ------------------------------------------------------------------

    @api.model
    def _participantes(self, company):
        return self.env['hr.employee'].sudo().search([
            ('company_id', '=', company.id), ('department_id.dcasa_meta_ventas', '=', True),
            ('user_id', '!=', False)])

    @api.model
    def _dias_de_cobro(self, facturas):
        """``({factura_id: día}, {nota_id: {factura_id}})``.

        El día en que cada factura quedó pagada completa: su última conciliación (pago o nota de crédito), nunca antes
        de la factura; las que todavía deben algo no salen. Y las notas de crédito que se aplicaron a cada una. Sale de
        una sola lectura de las conciliaciones (no del cuadro de pagos factura por factura)."""
        pagadas = facturas.filtered(lambda f: f.payment_state in ('paid', 'in_payment'))
        if not pagadas:
            return {}, {}
        parciales = self.env['account.partial.reconcile'].sudo().search_fetch(
            ['|', ('debit_move_id.move_id', 'in', pagadas.ids), ('credit_move_id.move_id', 'in', pagadas.ids)],
            ['debit_move_id', 'credit_move_id', 'max_date', 'exchange_move_id'])
        diferencias_de_cambio = parciales.exchange_move_id
        dias, notas = {}, {}
        for parcial in parciales:
            for propia, otra in ((parcial.debit_move_id, parcial.credit_move_id),
                                 (parcial.credit_move_id, parcial.debit_move_id)):
                factura, contraparte = propia.move_id, otra.move_id
                if factura not in pagadas or contraparte in diferencias_de_cambio:
                    continue
                dia = max(parcial.max_date, factura.invoice_date or date.min)
                dias[factura.id] = max(dias.get(factura.id, date.min), dia)
                if contraparte.move_type == 'out_refund':
                    notas.setdefault(contraparte.id, set()).add(factura.id)
        return dias, notas

    @api.model
    def _lo_que_cuenta(self, user, company, hasta):
        """Lo de ``user`` que ya cuenta hasta ``hasta`` (incluido): ``({factura: día}, {nota: día})``.

        * Factura: suya (el «Vendedor»), publicada, no histórica y pagada completa desde que rige la primera meta; su
          día es el del pago completo. Se mira hasta MESES_ATRAS atrás (un apartado puede tardar).
        * Nota de crédito: la que revierte una de esas facturas o se aplicó a ella. Su día es el de la nota o, si llegó
          antes de completarse el pago, el del pago completo. La de una venta que nunca contó no resta."""
        inicio = self.env['dcasa.nomina.meta.regla']._inicio(company)
        if not inicio or hasta < inicio:
            return {}, {}
        Move = self.env['account.move'].sudo()
        tope = hasta.replace(day=1) - relativedelta(months=MESES_ATRAS)
        comun = [('state', '=', 'posted'), ('company_id', '=', company.id)]
        facturas = Move.search(comun + [
            ('move_type', '=', 'out_invoice'), ('invoice_user_id', '=', user.id), ('dcasa_historica', '=', False),
            ('payment_state', 'in', ('paid', 'in_payment')),
            ('invoice_date', '>=', tope), ('invoice_date', '<=', hasta)])
        directas = Move.search(comun + [
            ('move_type', '=', 'out_refund'), ('reversed_entry_id.invoice_user_id', '=', user.id),
            ('reversed_entry_id.dcasa_historica', '=', False), ('date', '>=', tope), ('date', '<=', hasta)])
        dias, aplicadas = self._dias_de_cobro(facturas | directas.reversed_entry_id)

        def contada(factura):
            dia = dias.get(factura.id)
            return dia if dia and inicio <= dia else False

        cuentan = {f: dias[f.id] for f in facturas if contada(f) and dias[f.id] <= hasta}
        notas = {}
        for nota in directas | Move.browse(list(aplicadas)):
            if nota.state != 'posted' or nota.company_id != company or nota.date > hasta:
                continue
            ventas = nota.reversed_entry_id or Move.browse(aplicadas.get(nota.id, ()))
            completas = [contada(v) for v in ventas if contada(v)]
            if not completas:
                continue
            dia = max(nota.date, *completas)
            if dia <= hasta:
                notas[nota] = dia
        return cuentan, notas

    @api.model
    def _del_mes(self, empleado, user, mes, company, hasta=None):
        """Lo que cuenta para el bono de ``empleado`` en ``mes`` (hasta ``hasta``): ``({factura: día}, {nota: día})``.

        Cada venta y cada nota cuenta una sola vez: en el mes de su día o, si ese mes ya está cerrado para esta persona
        (su bono ya entró en una planilla), en el primer mes abierto después. Lo que ya está en un bono cerrado no
        vuelve a contar (un pago anulado y registrado de nuevo otro mes, por ejemplo)."""
        fin = fin_de_mes(mes)
        hasta = min(hasta or fin, fin)
        cerrados = self.sudo().search([('empleado_id', '=', empleado.id), ('mes', '!=', mes),
                                       ('estado', 'in', ('en_planilla', 'pagado'))])
        meses_cerrados = set(cerrados.mapped('mes'))
        ya_contado = cerrados.factura_ids | cerrados.nota_ids

        def de_este_mes(dia):
            cuenta_en = dia.replace(day=1)
            while cuenta_en in meses_cerrados:
                cuenta_en += relativedelta(months=1)
            return cuenta_en == mes

        cuentan, notas = self._lo_que_cuenta(user, company, hasta)
        return ({f: d for f, d in cuentan.items() if f not in ya_contado and de_este_mes(d)},
                {n: d for n, d in notas.items() if n not in ya_contado and de_este_mes(d)})

    # ------------------------------------------------------------------
    # El bono de un mes
    # ------------------------------------------------------------------

    @api.model
    def _calcular(self, empleado, mes, company):
        """El bono de ``empleado`` en ``mes`` (se crea o se pone al día). Un bono que ya entró en una planilla no
        cambia (se recalcula solo al volver a calcular esa planilla). Sin meta que rija ese mes, no hay bono."""
        mes = mes.replace(day=1)
        bono = self.sudo().search([('empleado_id', '=', empleado.id), ('mes', '=', mes)], limit=1)
        if bono.estado in ('en_planilla', 'pagado'):
            return bono
        regla = self.env['dcasa.nomina.meta.regla']._vigente(mes, company)
        user = empleado.user_id or bono.user_id
        if not regla or not user:
            return bono
        facturas, notas = self._del_mes(empleado, user, mes, company)
        total = total_sin_itbms(facturas, notas)
        cumplio = total >= regla.meta_mensual
        valores = {
            'user_id': user.id, 'regla_id': regla.id, 'meta': regla.meta_mensual,
            'porcentaje': regla.porcentaje, 'cobrado': total, 'cumplio': cumplio,
            'monto': calculo.porcentaje(total, regla.porcentaje) if cumplio else 0.0,
            'factura_ids': [fields.Command.set([f.id for f in facturas])],
            'nota_ids': [fields.Command.set([n.id for n in notas])],
            'actualizado': fields.Datetime.now(),
        }
        if bono:
            bono.sudo().write(valores)
            return bono
        return self.sudo().create({'empleado_id': empleado.id, 'company_id': company.id, 'mes': mes, **valores})

    @api.model
    def _actualizar(self, company, meses):
        """Pone al día los bonos de ``meses`` de quienes participan (los pagados no cambian)."""
        for empleado in self._participantes(company):
            for mes in meses:
                self._calcular(empleado, mes, company)

    @api.model
    def _cron_actualizar(self):
        """Cada día: el mes en curso y el anterior, para que Gerencia los vea al día en Nómina › Bono por meta."""
        hoy = fields.Date.context_today(self.with_context(tz='America/Panama'))
        mes = hoy.replace(day=1)
        for company in self.env['dcasa.nomina.meta.regla'].sudo().search([]).company_id:
            self._actualizar(company, [mes - relativedelta(months=1), mes])

    @api.model
    def _accion_bonos(self):
        """Nómina › Bono por meta: pone al día el mes en curso y el anterior y abre la lista."""
        hoy = fields.Date.context_today(self.with_context(tz='America/Panama'))
        mes = hoy.replace(day=1)
        for company in self.env.companies:
            self._actualizar(company, [mes - relativedelta(months=1), mes])
        accion = self.env['ir.actions.actions']._for_xml_id('dcasa_nomina.accion_meta_bonos_lista')
        return accion

    # ------------------------------------------------------------------
    # Lo que ve la vendedora en su Inicio (solo lo suyo)
    # ------------------------------------------------------------------

    @api.model
    def _para_inicio(self, user, hoy):
        """La tarjeta «Tu meta del mes» de ``user``, o None si no participa.

        Decisión de la dueña (2026-10-16): la vendedora ve SOLO cuánto lleva en porcentaje y unas palabras de ánimo.
        Nada de dinero: ni la meta, ni el porcentaje del bono, ni lo cobrado, ni lo que falta, ni el ritmo del día. Por
        eso esas cifras ni siquiera salen del servidor (no se pueden ver tampoco en las herramientas del navegador)."""
        company = self.env.company
        empleado = self._participantes(company).filtered(lambda e: e.user_id == user)[:1]
        if not empleado:
            return None
        mes = hoy.replace(day=1)
        regla = self.env['dcasa.nomina.meta.regla']._vigente(mes, company)
        if not regla:
            return None
        facturas, notas = self._del_mes(empleado, user, mes, company, hasta=hoy)
        cobrado = max(total_sin_itbms(facturas, notas), 0.0)
        cumplio = cobrado >= regla.meta_mensual
        avance_real = int(round(cobrado / regla.meta_mensual * 100.0))
        nombre_mes = format_date(mes, 'MMMM', locale='es')
        return {
            'mes': nombre_mes,
            # La barra se llena hasta el 100 %; el número dice cuánto lleva de verdad (puede pasar del 100 %).
            'avance': round(min(cobrado / regla.meta_mensual * 100.0, 100.0), 1),
            'avance_real': avance_real,
            'cumplio': cumplio,
            'animo': self._animo(avance_real, cumplio),
            'ventas': self._mis_ventas(facturas, notas, nombre_mes),
        }

    def _mis_ventas(self, facturas, notas, nombre_mes):
        """El botón «Ver mis ventas» de la tarjeta (pedido de la dueña, 2026-10-16): abre las ventas que suman al
        porcentaje de este mes (las facturas cobradas completas y las notas de crédito que restan), solo las suyas.
        Sin permiso para ver facturas, no hay botón."""
        Move = self.env['account.move']
        if not Move.has_access('read'):
            return None
        vista = self.env.ref('account.view_out_invoice_tree', raise_if_not_found=False)
        return {'accion': {
            'name': self.env._('Mis ventas de %s', nombre_mes),
            'res_model': 'account.move',
            'domain': [('id', 'in', sorted(m.id for m in (*facturas, *notas)))],
            'vista_lista': vista.id if vista else False,
        }}

    def _animo(self, avance, cumplio):
        """Unas palabras de ánimo según lo que lleva de la meta (pedido de la dueña, 2026-10-16). Con la voz de la
        marca: tuteo, sin gritos ni cifras inventadas."""
        if cumplio:
            return self.env._('¡Lo lograste! Meta cumplida: lo que sigas cobrando este mes también suma a tu bono.')
        if avance >= 90:
            return self.env._('¡Ya casi! Te falta muy poco para tu bono.')
        if avance >= 50:
            return self.env._('¡Vas muy bien! Ya cruzaste la mitad del camino.')
        if avance > 0:
            return self.env._('Vas sumando. Paso a paso se llega a la meta.')
        return self.env._('Arranca el mes: cada venta cobrada te acerca a tu bono.')
