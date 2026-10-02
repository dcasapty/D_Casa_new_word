"""Cierre de mes: lista de chequeo con datos reales y fecha de bloqueo.

Cerrar un mes = revisar que todo esté (bancos conciliados, nada en borrador, balance que
cuadra) y fijar la **fecha de bloqueo** de Odoo (``res.company.fiscalyear_lock_date``) al
último día del mes: desde ese momento nadie publica ni modifica asientos de ese mes o de
antes. Opcionalmente también la de ITBMS (``tax_lock_date``) cuando la declaración ya se
presentó. Es un bloqueo «suave» de Odoo: la gerencia puede reabrir con un motivo, que
queda en el historial. El bloqueo irreversible (``hard_lock_date``) no se usa aquí: lo
decide el contador al cierre del año fiscal.
"""
from ast import literal_eval
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

GERENCIA = 'account.group_account_manager'
MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre')


def nombre_mes(dia):
    return f'{MESES[dia.month - 1].capitalize()} {dia.year}'


class DcasaCierreMes(models.Model):
    _name = 'dcasa.cierre.mes'
    _description = 'Cierre de mes contable'
    _inherit = ['mail.thread']
    _order = 'mes desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,
                                 readonly=True)
    mes = fields.Date('Mes', required=True, help='Cualquier día del mes; se guarda el día 1.',
                      default=lambda self: fields.Date.context_today(self).replace(day=1) - relativedelta(months=1))
    fecha_fin = fields.Date('Último día', compute='_compute_name', store=True)
    estado = fields.Selection([('abierto', 'Abierto'), ('cerrado', 'Cerrado')], default='abierto', required=True,
                              readonly=True, tracking=True)
    bloquear_itbms = fields.Boolean(
        'Bloquear también el ITBMS', tracking=True,
        help='Marca esto cuando la declaración de ITBMS del mes ya se presentó: nadie podrá cambiar facturas con '
             'impuesto de ese mes.')
    paso_ids = fields.One2many('dcasa.cierre.mes.paso', 'cierre_id', string='Lista de chequeo', readonly=True)
    pendientes = fields.Integer('Pendientes que impiden cerrar', compute='_compute_pendientes')
    revisado_el = fields.Datetime(readonly=True)
    cerrado_por = fields.Many2one('res.users', readonly=True, tracking=True)
    cerrado_el = fields.Datetime(readonly=True)
    motivo_reapertura = fields.Text('Motivo para reabrir')
    bloqueado_hasta = fields.Date(related='company_id.fiscalyear_lock_date', string='Bloqueado hasta')
    itbms_bloqueado_hasta = fields.Date(related='company_id.tax_lock_date', string='ITBMS bloqueado hasta')
    notas = fields.Html()

    _mes_unico = models.Constraint('UNIQUE(company_id, mes)', 'Ese mes ya tiene su cierre.')

    @api.depends('mes')
    def _compute_name(self):
        for cierre in self:
            cierre.name = nombre_mes(cierre.mes) if cierre.mes else False
            cierre.fecha_fin = cierre.mes + relativedelta(day=31) if cierre.mes else False

    @api.depends('paso_ids.estado', 'paso_ids.bloquea')
    def _compute_pendientes(self):
        for cierre in self:
            cierre.pendientes = len(cierre.paso_ids.filtered(lambda p: p.bloquea and p.estado == 'pendiente'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('mes'):
                vals['mes'] = fields.Date.to_date(vals['mes']).replace(day=1)
        cierres = super().create(vals_list)
        cierres._revisar()
        return cierres

    def write(self, vals):
        if 'mes' in vals:
            if self.filtered(lambda c: c.estado == 'cerrado'):
                raise UserError(self.env._('Un mes cerrado no cambia de fecha: reábrelo primero.'))
            vals['mes'] = fields.Date.to_date(vals['mes']).replace(day=1)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _no_borrar_cerrados(self):
        if self.filtered(lambda c: c.estado == 'cerrado'):
            raise UserError(self.env._('Un mes cerrado no se borra: reábrelo primero si hace falta.'))

    # ------------------------------------------------------------------
    # Lista de chequeo
    # ------------------------------------------------------------------

    @api.model
    def _chequeo(self, inicio, fin, company=None):
        """Pasos del cierre del mes [inicio, fin] con datos reales. También lo usa Brian.

        Cada paso: codigo, nombre, estado (listo/pendiente/aviso/info), bloquea, detalle y, si
        hay registros que revisar, modelo + dominio para abrirlos.
        """
        company = company or self.env.company
        Move = self.env['account.move']
        Reporte = self.env['dcasa.reporte.contable']
        moneda = company.currency_id
        pasos = []

        def paso(codigo, nombre, pendiente, detalle, bloquea=True, modelo=False, dominio=None, estado=None):
            pasos.append({
                'codigo': codigo, 'nombre': nombre, 'bloquea': bloquea, 'detalle': detalle,
                'estado': estado or (('pendiente' if bloquea else 'aviso') if pendiente else 'listo'),
                'modelo': modelo if pendiente else False, 'dominio': dominio or [],
            })

        dominio = [('company_id', '=', company.id), ('is_reconciled', '=', False), ('date', '<=', str(fin))]
        sin_conciliar = self.env['account.bank.statement.line'].search(dominio)
        por_banco = {}
        for linea in sin_conciliar:
            por_banco[linea.journal_id.name] = por_banco.get(linea.journal_id.name, 0) + 1
        paso('conciliacion', 'Bancos, Yappy, tarjeta y caja conciliados', len(sin_conciliar),
             ', '.join(f'{b}: {n} sin conciliar' for b, n in por_banco.items()) or 'Todo conciliado',
             modelo='account.bank.statement.line', dominio=dominio)

        for tipos, nombre in ((('out_invoice', 'out_refund'), 'Facturas de cliente en borrador'),
                              (('in_invoice', 'in_refund'), 'Facturas de proveedor en borrador'),
                              (('entry',), 'Asientos en borrador')):
            dominio = [('company_id', '=', company.id), ('move_type', 'in', tipos), ('state', '=', 'draft'),
                       ('date', '<=', str(fin))]
            cuantos = Move.search_count(dominio)
            paso(f'borrador_{tipos[0]}', nombre, cuantos,
                 f'{cuantos} en borrador: publícalos o elimínalos' if cuantos else 'Ninguno',
                 modelo='account.move', dominio=dominio)

        if 'sale.order' in self.env and self.env['sale.order'].has_access('read'):
            hasta = fields.Datetime.to_string(fields.Datetime.to_datetime(fin + timedelta(days=1)))
            dominio = [('company_id', '=', company.id), ('invoice_status', '=', 'to invoice'),
                       ('date_order', '<', hasta)]
            cuantos = self.env['sale.order'].search_count(dominio)
            paso('por_facturar', 'Ventas confirmadas por facturar', cuantos,
                 f'{cuantos} ventas sin factura (sus ingresos no están en el mes)' if cuantos else 'Ninguna',
                 bloquea=False, modelo='sale.order', dominio=dominio)

        comprobacion = Reporte.balance_comprobacion(inicio, fin)
        paso('comprobacion', 'El balance de comprobación cuadra', not comprobacion['cuadra'],
             'Debe = haber' if comprobacion['cuadra'] else 'El debe y el haber NO cuadran')
        general = Reporte.balance_general(fin)
        paso('balance', 'El balance general cuadra', not general['cuadra'],
             'Activo = pasivo + patrimonio' if general['cuadra'] else 'Activo ≠ pasivo + patrimonio')

        cobrar = Reporte._antiguedad('por_cobrar', fin)['totales']
        paso('cobros', 'Cobros vencidos revisados', cobrar['vencido'] > 0,
             f'Vencido al cierre: {moneda.format(cobrar["vencido"])} de {moneda.format(cobrar["total"])}',
             bloquea=False)
        itbms = Reporte.itbms(inicio, fin)['resumen']
        paso('itbms', 'ITBMS del mes para declarar', False,
             f'Débito {moneda.format(itbms["debito_fiscal"])} − crédito {moneda.format(itbms["credito_fiscal"])} '
             f'= {"a pagar" if itbms["a_pagar"] >= 0 else "a favor"} {moneda.format(abs(itbms["a_pagar"]))}',
             bloquea=False, estado='info')
        anterior = inicio - timedelta(days=1)
        bloqueo = company.fiscalyear_lock_date
        if not bloqueo or bloqueo < anterior:
            paso('mes_anterior', 'Meses anteriores cerrados', True,
                 f'{nombre_mes(anterior)} sigue abierto: al cerrar este mes también queda bloqueado.',
                 bloquea=False)
        return pasos

    def _revisar(self):
        for cierre in self:
            pasos = self._chequeo(cierre.mes, cierre.fecha_fin, cierre.company_id)
            cierre.paso_ids = [fields.Command.clear()] + [fields.Command.create({
                'sequence': i, 'codigo': p['codigo'], 'name': p['nombre'], 'estado': p['estado'],
                'bloquea': p['bloquea'], 'detalle': p['detalle'], 'modelo': p['modelo'] or False,
                'dominio': repr(p['dominio']) if p['modelo'] else False,
            }) for i, p in enumerate(pasos)]
            cierre.revisado_el = fields.Datetime.now()

    def action_revisar(self):
        self._revisar()
        return True

    # ------------------------------------------------------------------
    # Cerrar y reabrir
    # ------------------------------------------------------------------

    def _exigir_gerencia(self):
        if not self.env.su and not self.env.user.has_group(GERENCIA):
            raise AccessError(self.env._('Cerrar o reabrir un mes es de la gerencia contable.'))

    def action_cerrar(self):
        """Fija la fecha de bloqueo al último día del mes (y la de ITBMS si se marcó)."""
        self._exigir_gerencia()
        for cierre in self.sorted('mes'):
            if cierre.estado == 'cerrado':
                continue
            cierre._revisar()
            faltan = cierre.paso_ids.filtered(lambda p: p.bloquea and p.estado == 'pendiente')
            if faltan:
                raise UserError(self.env._('Antes de cerrar %(mes)s falta:\n%(lista)s', mes=cierre.name,
                                           lista='\n'.join(f'• {p.name}: {p.detalle}' for p in faltan)))
            company = cierre.company_id
            valores = {}
            if (company.fiscalyear_lock_date or date.min) < cierre.fecha_fin:
                valores['fiscalyear_lock_date'] = cierre.fecha_fin
            if cierre.bloquear_itbms and (company.tax_lock_date or date.min) < cierre.fecha_fin:
                valores['tax_lock_date'] = cierre.fecha_fin
            if valores:
                # La fecha de bloqueo vive en la empresa (ACL de administración): se escribe con sudo
                # DESPUÉS de comprobar el grupo de gerencia contable. Odoo valida de nuevo (conciliación).
                company.sudo().write(valores)
            cierre.write({'estado': 'cerrado', 'cerrado_por': self.env.user.id, 'cerrado_el': fields.Datetime.now(),
                          'motivo_reapertura': False})
            cierre.message_post(body=self.env._('Mes cerrado: bloqueado hasta el %s.',
                                                cierre.fecha_fin.strftime('%d/%m/%Y')))
        return True

    def action_reabrir(self):
        """Baja la fecha de bloqueo al último día del mes anterior. Pide motivo; queda en el historial."""
        self._exigir_gerencia()
        for cierre in self.sorted('mes'):
            if cierre.estado != 'cerrado':
                continue
            if not (cierre.motivo_reapertura or '').strip():
                raise UserError(self.env._('Escribe el motivo para reabrir %s (queda en el historial).', cierre.name))
            company = cierre.company_id
            if company.hard_lock_date and company.hard_lock_date >= cierre.mes:
                raise UserError(self.env._('%s tiene un bloqueo definitivo (cierre de año): no se puede reabrir.',
                                           cierre.name))
            # El bloqueo vuelve al último mes que sigue cerrado (o se quita si no queda ninguno).
            previo = self.search([('company_id', '=', company.id), ('mes', '<', cierre.mes),
                                  ('estado', '=', 'cerrado')], order='mes desc', limit=1)
            valores = {}
            if company.fiscalyear_lock_date and company.fiscalyear_lock_date >= cierre.mes:
                valores['fiscalyear_lock_date'] = previo.fecha_fin or False
            if company.tax_lock_date and company.tax_lock_date >= cierre.mes:
                previo_itbms = self.search([('company_id', '=', company.id), ('mes', '<', cierre.mes),
                                            ('estado', '=', 'cerrado'), ('bloquear_itbms', '=', True)],
                                           order='mes desc', limit=1)
                valores['tax_lock_date'] = previo_itbms.fecha_fin or False
            if valores:
                company.sudo().write(valores)
            # Un bloqueo es una sola fecha: los meses posteriores también quedan abiertos.
            posteriores = self.search([('company_id', '=', company.id), ('mes', '>=', cierre.mes),
                                       ('estado', '=', 'cerrado')])
            motivo = cierre.motivo_reapertura
            for reabierto in posteriores:
                reabierto.write({'estado': 'abierto', 'cerrado_por': False, 'cerrado_el': False})
                reabierto.message_post(body=self.env._('Mes reabierto. Motivo: %s', motivo))
        return True


class DcasaCierreMesPaso(models.Model):
    _name = 'dcasa.cierre.mes.paso'
    _description = 'Paso del cierre de mes'
    _order = 'sequence, id'

    cierre_id = fields.Many2one('dcasa.cierre.mes', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer()
    codigo = fields.Char()
    name = fields.Char('Paso', required=True)
    estado = fields.Selection([('listo', 'Listo'), ('pendiente', 'Pendiente'), ('aviso', 'Revisar'),
                               ('info', 'Informativo')], required=True)
    bloquea = fields.Boolean('Impide cerrar')
    detalle = fields.Char()
    modelo = fields.Char()
    dominio = fields.Char()

    def action_ver(self):
        """Abre los registros que hay que revisar en este paso."""
        self.ensure_one()
        if not self.modelo:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': self.name, 'res_model': self.modelo,
            'domain': literal_eval(self.dominio or '[]'), 'views': [[False, 'list'], [False, 'form']],
        }
