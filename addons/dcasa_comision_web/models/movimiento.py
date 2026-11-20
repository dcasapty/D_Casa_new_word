"""EL LIBRO de la comisión del sitio web: la única verdad sobre lo que se le debe a cada persona.

Mismas reglas del libro del programa de vendedores (``dcasa.vend.movimiento``), con dinero en vez de puntos:

* una fila por persona y por hecho, en **centavos enteros**; el **saldo es la suma de las filas** y no vive en ningún
  otro sitio (no hay columna de saldo);
* una fila **no se edita ni se borra**, ni con ``sudo()`` ni por RPC: una corrección es **otra fila con la cifra
  contraria, su motivo y su autor**;
* **una sola puerta de entrada**: ``_asentar``;
* el mes de Panamá en que se anota se guarda calculado y **no se mueve nunca**: lo que se anota en noviembre queda en
  noviembre para siempre.

Tipos: ``venta`` (lo que le toca por una venta que quedó pagada), ``devolucion`` (resta por una nota de crédito),
``reverso`` (resta o repone cuando un pago se cae o vuelve, o una factura se anula), ``tarifa`` (la tarifa fija de cada
periodo), ``ajuste`` (a mano, solo Gerencia y Nómina, siempre con motivo) y ``liquidacion`` (lo que se manda a pagar al
aprobar una liquidación; negativo).

``concepto`` separa los dos conceptos que define Gerencia: ``comision`` (el porcentaje por cada venta online) y
``tarifa`` (la tarifa fija por mantener la plataforma). Ninguno es salario (decisión de Gerencia).
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

ZONA = 'America/Panama'
TIPOS = [('venta', 'Venta'), ('devolucion', 'Devolución'), ('reverso', 'Reverso'), ('tarifa', 'Tarifa fija'),
         ('ajuste', 'Ajuste'), ('liquidacion', 'Liquidación')]
CONCEPTOS = [('comision', 'Porcentaje de las ventas'), ('tarifa', 'Tarifa fija')]
CONCEPTO_DE = {'venta': 'comision', 'devolucion': 'comision', 'tarifa': 'tarifa'}
# Lo máximo que cabe en una fila del libro (centavos, entero de 32 bits): más que eso no se puede anotar.
MAXIMO_CENTAVOS = 2_147_483_647


def dia_de_panama(momento):
    """El día (hora de Panamá) de un instante en UTC sin zona. Un año extremo (0001, 9999) no se puede pasar de zona sin
    desbordar: ahí se devuelve el día tal cual (nunca un error de Python sin traducir)."""
    try:
        return pytz.utc.localize(momento).astimezone(pytz.timezone(ZONA)).date()
    except (OverflowError, ValueError):
        return momento.date()


def mes_de_panama(momento):
    """El primer día del mes (hora de Panamá) de un instante en UTC sin zona."""
    return dia_de_panama(momento).replace(day=1)


def inicio_del_dia_en_utc(dia):
    """Las 00:00 de Panamá de ``dia``, en UTC sin zona (como guarda Odoo)."""
    return pytz.timezone(ZONA).localize(datetime.combine(dia, time.min)).astimezone(pytz.utc).replace(tzinfo=None)


def empieza_periodo(periodo, dia):
    """¿``dia`` es el primer día de un periodo de la tarifa? Mes: el 1; quincena: el 1 y el 16; semana: el lunes."""
    if periodo == 'mensual':
        return dia.day == 1
    if periodo == 'quincenal':
        return dia.day in (1, 16)
    return dia.weekday() == 0


class DcasaWebMovimiento(models.Model):
    _name = 'dcasa.web.movimiento'
    _description = 'Libro de la comisión del sitio web'
    _order = 'ocurrido_en desc, id desc'
    _rec_name = 'motivo'

    empleado_id = fields.Many2one('hr.employee', 'Persona', required=True, readonly=True, index=True,
                                  ondelete='restrict')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, readonly=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    tipo = fields.Selection(TIPOS, required=True, readonly=True, index=True)
    concepto = fields.Selection(CONCEPTOS, required=True, readonly=True, index=True)
    centavos = fields.Integer('Centavos', required=True, readonly=True)
    monto = fields.Monetary(compute='_compute_monto', store=True, currency_field='currency_id')
    ocurrido_en = fields.Datetime('Anotado el', required=True, readonly=True, default=fields.Datetime.now, index=True)
    mes = fields.Date('Mes (Panamá)', required=True, readonly=True, index=True,
                      help='El mes de Panamá en que se anotó. No se mueve nunca.')
    venta_id = fields.Many2one('dcasa.web.venta', 'Venta del sitio', readonly=True, index='btree_not_null',
                               ondelete='restrict')
    reglas_id = fields.Many2one('dcasa.web.reglas', 'Reglas', readonly=True, ondelete='restrict')
    periodo_inicio = fields.Date('Periodo de la tarifa', readonly=True,
                                 help='En la tarifa fija: el primer día del periodo que cubre.')
    liquidacion_id = fields.Many2one('dcasa.web.liquidacion', 'Liquidación', readonly=True, index='btree_not_null',
                                     ondelete='restrict')
    reversa_id = fields.Many2one('dcasa.web.movimiento', 'Anula a', readonly=True, ondelete='restrict')
    motivo = fields.Char(readonly=True)
    autor = fields.Char(required=True, readonly=True, help="Quién lo anotó, o «sistema» si fue automático.")

    _centavos_no_cero = models.Constraint('CHECK(centavos <> 0)', 'Una fila de cero no dice nada: no se anota.')
    _reversa_unica = models.Constraint('UNIQUE(reversa_id)', 'Esa fila ya fue anulada.')
    _tarifa_una_vez = models.UniqueIndex(
        '(empleado_id, company_id, periodo_inicio) WHERE tipo = \'tarifa\'',
        message='La tarifa de ese periodo ya se anotó para esa persona.')

    @api.depends('centavos')
    def _compute_monto(self):
        for fila in self:
            fila.monto = fila.centavos / 100.0

    @api.constrains('tipo', 'motivo', 'concepto')
    def _check_motivo(self):
        for fila in self:
            if fila.tipo in ('ajuste', 'reverso', 'devolucion') and not (fila.motivo or '').strip():
                raise ValidationError(self.env._('Un ajuste, una devolución o un reverso lleva motivo.'))
            esperado = CONCEPTO_DE.get(fila.tipo)
            if esperado and fila.concepto != esperado:
                raise ValidationError(self.env._('El concepto de esa fila no corresponde a su tipo.'))

    def write(self, vals):
        raise UserError(self.env._(
            'El libro no se edita: una corrección es otra fila con la cifra contraria y su motivo.'))

    def unlink(self):
        raise UserError(self.env._(
            'El libro no se borra: una corrección es otra fila con la cifra contraria y su motivo.'))

    @api.model
    def _asentar(self, empleado, tipo, centavos, company, autor='sistema', **extra):
        """Escribe una fila. ÚNICO camino de entrada al libro."""
        if abs(centavos) > MAXIMO_CENTAVOS:
            raise UserError(self.env._(
                'Esa cifra es demasiado grande para anotarla en el libro (llega hasta %s).',
                f'{MAXIMO_CENTAVOS / 100:,.2f}'))
        ocurrido = extra.pop('ocurrido_en', None) or fields.Datetime.now()
        concepto = extra.pop('concepto', None) or CONCEPTO_DE.get(tipo) or 'comision'
        return self.sudo().create({
            'empleado_id': empleado.id, 'company_id': company.id, 'tipo': tipo, 'concepto': concepto,
            'centavos': centavos, 'autor': autor, 'ocurrido_en': ocurrido, 'mes': mes_de_panama(ocurrido), **extra})

    def _contraria(self, motivo, autor='sistema', **extra):
        """Anula esta fila con otra de la cifra contraria (un solo reverso por fila)."""
        self.ensure_one()
        return self._asentar(self.empleado_id, 'liquidacion' if self.tipo == 'liquidacion' else 'reverso',
                             -self.centavos, self.company_id, autor, concepto=self.concepto, motivo=motivo,
                             reversa_id=self.id, venta_id=self.venta_id.id, liquidacion_id=self.liquidacion_id.id,
                             **extra)

    # ------------------------------------------------------------------
    # Saldos: siempre la suma del libro
    # ------------------------------------------------------------------

    @api.model
    def _saldos(self, empleados, hasta=None, company=None):
        """``{(empleado_id, concepto): centavos}``: lo que se le debe a cada persona por concepto, sumando el libro. Con
        ``hasta`` (fecha de Panamá): solo lo anotado hasta ese día; las liquidaciones ya hechas se descuentan siempre
        (lo que se mandó a pagar ya no se debe, sea cual sea el periodo que se mire)."""
        dominio = [('empleado_id', 'in', empleados.ids)]
        if company:
            dominio.append(('company_id', '=', company.id))
        saldos = {}
        propias = self.sudo()._read_group(
            dominio + [('tipo', '!=', 'liquidacion')] + self._hasta_el_dia(hasta), ['empleado_id', 'concepto'],
            ['centavos:sum'])
        liquidadas = self.sudo()._read_group(dominio + [('tipo', '=', 'liquidacion')], ['empleado_id', 'concepto'],
                                             ['centavos:sum'])
        for lote in (propias, liquidadas):
            for empleado, concepto, suma in lote:
                clave = (empleado.id, concepto)
                saldos[clave] = saldos.get(clave, 0) + suma
        return saldos

    @api.model
    def _hasta_el_dia(self, hasta):
        """El dominio «anotado hasta ese día (incluido, hora de Panamá)»."""
        if not hasta or hasta.year > 2200:
            return []
        fin = pytz.timezone(ZONA).localize(datetime.combine(hasta, time.min) + timedelta(days=1))
        return [('ocurrido_en', '<', fin.astimezone(pytz.utc).replace(tzinfo=None))]

    # ------------------------------------------------------------------
    # La tarifa fija: se anota el primer día de cada periodo
    # ------------------------------------------------------------------

    @api.model
    def _cron_tarifa(self, hoy=None):
        """Anota la tarifa fija de cada periodo que ya empezó y todavía no está en el libro, repartida entre quienes
        reciben. Se anota el primer día del periodo (mes, quincena o semana) con la versión que regía el día anterior:
        un cambio de tarifa rige hacia adelante y la primera tarifa de una versión es la del primer periodo que
        empieza DESPUÉS del día en que rige (con el día, no con la hora que se tecleó). Idempotente (un índice único por
        persona y periodo); nunca paga: solo anota."""
        from . import calculo
        hoy = hoy or fields.Date.context_today(self.with_context(tz=ZONA))
        Reglas = self.env['dcasa.web.reglas'].sudo()
        anotadas = 0
        for company in Reglas.search([]).company_id:
            versiones = Reglas._versiones_desde(company)
            if not versiones.filtered('tarifa_fija'):
                continue
            hechas = {(f.empleado_id.id, f.periodo_inicio) for f in self.sudo().search([
                ('company_id', '=', company.id), ('tipo', '=', 'tarifa')])}
            dia = dia_de_panama(versiones[0].rige_desde)
            while dia <= hoy:
                # La tarifa de un periodo es de la versión que ya regía el día ANTERIOR: la primera tarifa de una
                # versión es la del primer periodo que empieza DESPUÉS de su día (no depende de la hora tecleada).
                rige = versiones._de_este_dia(dia - timedelta(days=1))
                if rige and rige.tarifa_fija and empieza_periodo(rige.tarifa_periodo, dia):
                    partes = calculo.repartir(calculo.a_centavos(rige.tarifa_fija),
                                              [(r.empleado_id.id, r.porcentaje) for r in rige.reparto_ids])
                    for empleado_id, centavos in partes.items():
                        if centavos and (empleado_id, dia) not in hechas:
                            self._asentar(self.env['hr.employee'].sudo().browse(empleado_id), 'tarifa', centavos,
                                          company, periodo_inicio=dia, reglas_id=rige.id,
                                          motivo=self.env._('Tarifa fija por mantener la plataforma, desde %s.',
                                                            dia.strftime('%d/%m/%Y')))
                            anotadas += 1
                dia += timedelta(days=1)
        return anotadas


CANDADO_NUMERACION = 1
CANDADO_LIQUIDACIONES = 2


class DcasaWebCandado(models.Model):
    """Una fila por cosa que no se puede hacer dos veces a la vez (aprobar una liquidación, numerar una versión).

    Odoo corre en REPEATABLE READ: un candado de aviso (``pg_advisory_xact_lock``) no basta, porque quien espera ya
    tiene su «foto» de la base de antes y, al soltarse el candado, decide con datos viejos (dos liquidaciones
    sobre el mismo
    saldo se aprobaban a la vez y el saldo quedaba en negativo). Aquí quien entra **escribe** la fila: si otra
    transacción la cambió después de su foto, PostgreSQL le da un error de serialización y Odoo repite la operación con
    una foto nueva; si no, ya ve todo lo que alguien confirmó antes."""
    _name = 'dcasa.web.candado'
    _description = 'Candado de la comisión web'
    _log_access = False

    clave = fields.Integer(required=True, index=True)
    vueltas = fields.Integer(default=0)

    _clave_unica = models.Constraint('UNIQUE(clave)', 'Cada candado tiene una sola fila.')

    @api.model
    def _tomar(self, clave):
        """Toma el candado ``clave`` hasta el final de la transacción (y la obliga a repetirse si se adelantaron)."""
        self.env.cr.execute('UPDATE dcasa_web_candado SET vueltas = vueltas + 1 WHERE clave = %s', [clave])
        if not self.env.cr.rowcount:       # no debería pasar: los datos del módulo ya traen las dos filas
            self.env.cr.execute('INSERT INTO dcasa_web_candado (clave, vueltas) VALUES (%s, 1) ON CONFLICT DO NOTHING',
                                [clave])
