"""Las reglas de la comisión del sitio web, por versión (decisión de Gerencia, 2026-11-19).

Cada versión dice, desde cuándo rige: el porcentaje de cada venta online, la tarifa fija (con cada cuánto se anota),
cómo se arma la base (cinco interruptores, cada uno con su ejemplo en pantalla) y quiénes reciben, con su reparto
(suma 100 %). Una versión **no se edita ni se borra**: un cambio es una versión nueva, y solo rige hacia adelante
(mismo patrón del programa de vendedores, ``dcasa.vend.reglas``). Lo ya anotado en el libro nunca se recalcula.

**El módulo nace sin ninguna versión, sin porcentaje y sin tarifa**: no hay cifras de fábrica. Sin versión que rija,
el sistema solo mide las ventas del sitio. Con porcentaje y tarifa vacíos (0) la versión es una pausa.

El día de la PRIMERA versión es también el día desde el que una venta online deja de ser de una vendedora (bono por
meta, Inicio y programa de vendedores): ``sale.order._dcasa_online_desde`` (``models/sale_order.py``).
"""
from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import calculo
from .movimiento import CANDADO_NUMERACION, MAXIMO_CENTAVOS, ZONA, dia_de_panama

GRUPO = 'dcasa_nomina.group_nomina'
# Un objeto, no ``True``: el contexto que llega por RPC es JSON y nunca puede traerlo.
CREANDO_VERSION = object()
CLAVE_CREANDO = 'dcasa_comision_web_creando_version'
CLAVE_ANULANDO = 'dcasa_comision_web_anulando_version'
ANULANDO = object()
# Lo que solo escribe el botón «Anular»: ni al crear ni por el contexto.
CAMPOS_DEL_SISTEMA = ('anulada', 'anulada_por', 'anulada_el')

PERIODOS = [('mensual', 'Cada mes'), ('quincenal', 'Cada quincena'), ('semanal', 'Cada semana')]

# Las posiciones de cada interruptor, con las palabras con que se le explican a administración.
ITBMS = [('sin', 'Antes del ITBMS (recomendado)'), ('con', 'Después del ITBMS')]
ENVIO = [('sin', 'No cuenta el envío (recomendado)'), ('con', 'Cuenta el envío')]
DESCUENTOS = [('despues', 'Después de descuentos (recomendado)'), ('antes', 'Antes de descuentos (precio de lista)')]
DEVOLUCIONES = [('resta', 'Se resta lo devuelto (recomendado)'), ('no_resta', 'No se resta lo devuelto')]
PASARELA = [('no_resta', 'No se resta la pasarela (recomendado)'), ('resta', 'Se resta lo que cobra la pasarela')]

# El ejemplo con números de mentira que se ve al cambiar un interruptor (centavos).
EJEMPLO = {'productos': 100000, 'descuento_lineas': 0, 'descuento_negativas': 10000, 'envio': 5000, 'itbms': 9000,
           'devuelto': 20000, 'devuelto_itbms': 1800, 'pasarela': 3000}


# Lo más que cabe en una cifra de dinero de una versión (la tarifa y el tope se anotan en el libro, en centavos enteros
# de 32 bits).
LIMITE_DE_DINERO = MAXIMO_CENTAVOS / 100


def dinero(centavos):
    return f'${centavos / 100:,.2f}'


class DcasaWebReglas(models.Model):
    _name = 'dcasa.web.reglas'
    _description = 'Reglas de la comisión del sitio web (una versión)'
    _order = 'rige_desde desc, numero desc'
    _rec_name = 'nombre'

    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    numero = fields.Integer('Versión', readonly=True, index=True)
    nombre = fields.Char(compute='_compute_nombre')
    rige_desde = fields.Datetime(
        'Rige desde', required=True, default=fields.Datetime.now, index=True,
        help='Rige desde el INICIO de ese día (hora de Panamá), y solo desde entonces: lo cobrado ese día ya cuenta '
             'para el sitio y deja de ser de las vendedoras. No se acepta un día que ya pasó. Una versión nueva manda '
             'desde su fecha en adelante sobre todas las anteriores (la última que se guardó): si otra ya '
             'programada tiene una fecha más lejana, queda tapada hasta que se anule. Lo ya anotado no se recalcula.')
    estado = fields.Selection([('programada', 'Programada'), ('tapada', 'Tapada'), ('vigente', 'Rige ahora'),
                               ('anterior', 'Reemplazada'), ('anulada', 'Anulada')], compute='_compute_estado')
    tapada_por_id = fields.Many2one(
        'dcasa.web.reglas', 'Tapada por', compute='_compute_tapada',
        help='Otra versión, guardada después, que rige desde el mismo día o antes: manda sobre esta desde su fecha en '
             'adelante, así que esta nunca va a regir (a menos que se anule la otra).')
    aviso_tapada = fields.Char('Aviso de versión tapada', compute='_compute_tapada')
    tapa_a_ids = fields.Many2many(
        'dcasa.web.reglas', string='Tapa a', compute='_compute_tapada',
        help='Las versiones programadas más lejanas, guardadas antes, que esta deja tapadas: ya no van a regir.')
    aviso_tapa = fields.Char('Aviso al tapar otra versión', compute='_compute_tapada')
    anulada = fields.Boolean('Anulada', readonly=True, copy=False, index=True,
                             help='Una versión que todavía no rige se puede anular (con motivo) si se puso mal; nunca '
                                  'se borra. Una anulada no rige nunca.')
    motivo_anulacion = fields.Char('Motivo de la anulación', copy=False)
    anulada_por = fields.Many2one('res.users', 'Anulada por', readonly=True, copy=False)
    anulada_el = fields.Datetime('Anulada el', readonly=True, copy=False)
    porcentaje = fields.Float(
        'Porcentaje de cada venta del sitio', digits=(6, 3),
        help='El porcentaje fijo de lo vendido por internet. No es un bono por meta: se paga aunque no se llegue a '
             'ninguna meta. Déjalo en 0 si por ahora no hay porcentaje (las ventas se miden igual).')
    tarifa_fija = fields.Monetary(
        'Tarifa fija por mantener la plataforma', help='Un monto fijo que sale siempre de la empresa. Déjalo en 0 si '
                                                       'no hay tarifa.')
    tope_ajuste = fields.Monetary(
        'Tope de un ajuste a mano',
        help='Lo máximo (en un sentido o en otro) que se puede anotar en un solo ajuste a mano en el libro. Déjalo en '
             '0 si no quieres tope: solo se rechaza lo que no es un número o no cabe en el libro. Es una decisión de '
             'Gerencia: el sistema no trae ninguna cifra.')
    tarifa_periodo = fields.Selection(PERIODOS, 'La tarifa se anota', required=True, default='mensual',
                                      help='Cada cuánto se anota la tarifa fija: el primer día de cada mes, de cada '
                                           'quincena (días 1 y 16) o de cada semana (lunes).')
    base_itbms = fields.Selection(ITBMS, 'ITBMS', required=True, default='sin')
    base_envio = fields.Selection(ENVIO, 'Envío', required=True, default='sin')
    base_descuentos = fields.Selection(DESCUENTOS, 'Descuentos', required=True, default='despues')
    base_devoluciones = fields.Selection(DEVOLUCIONES, 'Devoluciones', required=True, default='resta')
    base_pasarela = fields.Selection(PASARELA, 'Comisión de la pasarela', required=True, default='no_resta')
    reparto_ids = fields.One2many('dcasa.web.reparto', 'reglas_id', 'Quiénes reciben')
    motivo = fields.Char('Motivo del cambio', help='Se ve en el historial. Es opcional, pero ayuda.')
    autor = fields.Char('Quién lo guardó', readonly=True)
    ejemplo_html = fields.Html('Un ejemplo con números de mentira', compute='_compute_ejemplo', sanitize=False)

    # ------------------------------------------------------------------
    # Cómputos
    # ------------------------------------------------------------------

    @api.depends('numero')
    def _compute_nombre(self):
        for version in self:
            version.nombre = self.env._('Versión %s', version.numero) if version.numero else self.env._('Versión nueva')

    @api.depends('rige_desde', 'company_id', 'anulada', 'numero')
    def _compute_estado(self):
        ahora = fields.Datetime.now()
        for version in self:
            vigente = self._vigente(version.company_id, ahora) if version.id else self.browse()
            if version.anulada:
                version.estado = 'anulada'
            elif not version.id or not version.rige_desde or dia_de_panama(version.rige_desde) > dia_de_panama(ahora):
                version.estado = 'tapada' if version._tapada_por() else 'programada'
            else:
                version.estado = 'vigente' if version == vigente else 'anterior'

    def _tapada_por(self):
        """La primera versión guardada DESPUÉS de esta (no anulada) que rige desde el mismo día o antes: desde su fecha
        manda ella (``_de_este_dia``), así que esta no rige nunca mientras la otra no se anule. Vacío si no la tapa
        ninguna."""
        self.ensure_one()
        if not self.id or self.anulada or not self.rige_desde:
            return self.browse()
        dia = dia_de_panama(self.rige_desde)
        posteriores = self.sudo().search([('company_id', '=', self.company_id.id), ('anulada', '=', False),
                                          ('numero', '>', self.numero)], order='numero')
        return posteriores.filtered(lambda v: dia_de_panama(v.rige_desde) <= dia)[:1]

    def _tapa_a(self):
        """Las versiones programadas para más adelante, guardadas ANTES, que esta deja tapadas: rigen desde el mismo
        día o después, y desde su fecha manda esta (la última que se guardó). Vale también para una versión nueva que
        todavía no se guarda: la pantalla lo avisa mientras se escribe la fecha."""
        self.ensure_one()
        if self.anulada or not self.rige_desde:
            return self.browse()
        dia = dia_de_panama(self.rige_desde)
        hoy = dia_de_panama(fields.Datetime.now())
        dominio = [('company_id', '=', (self.company_id or self.env.company).id), ('anulada', '=', False)]
        if self.id:
            dominio.append(('numero', '<', self.numero))
        antes = self.sudo().search(dominio)
        return antes.filtered(lambda v: dia_de_panama(v.rige_desde) >= dia and dia_de_panama(v.rige_desde) > hoy)

    @api.depends('rige_desde', 'company_id', 'anulada', 'numero')
    def _compute_tapada(self):
        for version in self:
            tapada, tapa = version._tapada_por(), version._tapa_a()
            version.tapada_por_id = tapada
            version.tapa_a_ids = tapa
            version.aviso_tapada = self.env._(
                'Esta versión nunca va a regir: la versión %(otra)s, guardada después, manda desde el %(dia)s. '
                'Si no era lo que querías, anula una de las dos.', otra=tapada.numero,
                dia=dia_de_panama(tapada.rige_desde).strftime('%d/%m/%Y')) if tapada else False
            numeros = sorted(tapa.mapped('numero'))
            if len(numeros) > 1:
                version.aviso_tapa = self.env._(
                    'Esta versión tapa a las versiones %(otras)s, que estaban programadas para más adelante: esas ya '
                    'no van a regir (se pueden anular).',
                    otras=' y '.join([', '.join(map(str, numeros[:-1])), str(numeros[-1])]))
            else:
                version.aviso_tapa = self.env._(
                    'Esta versión tapa a la versión %(otra)s, que estaba programada para más adelante: esa ya no va a '
                    'regir (se puede anular).', otra=numeros[0]) if numeros else False

    def _opciones(self):
        """Los interruptores de la base, como los lee ``calculo.base_de_la_venta``."""
        self.ensure_one()
        return {clave: self[clave] for clave in calculo.OPCIONES}

    @api.depends('porcentaje', 'base_itbms', 'base_envio', 'base_descuentos', 'base_devoluciones', 'base_pasarela')
    def _compute_ejemplo(self):
        """Muestra, con números de mentira, qué entra y qué no en la base con los interruptores como están ahora. Es
        solo para entender: ninguna de estas cifras es de la empresa."""
        for version in self:
            op = version._opciones()
            c = EJEMPLO
            filas = [
                ('Un mueble vendido', c['productos'], '+', True, 'Siempre cuenta.'),
                ('Descuento o premio ya aplicado', c['descuento_negativas'], '−', op['base_descuentos'] == 'despues',
                 'Se resta si el porcentaje se calcula después de los descuentos.'),
                ('Cobro de envío', c['envio'], '+', op['base_envio'] == 'con', 'Se suma solo si cuenta el envío.'),
                ('ITBMS (el impuesto)', c['itbms'], '+', op['base_itbms'] == 'con',
                 'Se suma solo si el porcentaje se calcula con el ITBMS.'),
                ('El cliente devolvió', calculo.devuelto_en_la_base(c, {**op, 'base_devoluciones': 'resta'}),
                 '−', op['base_devoluciones'] == 'resta', 'Se resta si las devoluciones restan.'),
                ('La pasarela cobró', c['pasarela'], '−', op['base_pasarela'] == 'resta',
                 'Se resta solo si se resta lo que cobra la pasarela.'),
            ]
            cuerpo = Markup('').join(
                Markup('<tr><td>{}</td><td class="text-end">{}{}</td><td><strong>{}</strong> '
                       '<span class="text-muted">{}</span></td></tr>').format(
                    nombre, signo, dinero(monto), 'Entra' if entra else 'No entra', nota)
                for nombre, monto, signo, entra, nota in filas)
            base = calculo.base_de_la_venta(c, op)
            if version.porcentaje:
                comision = calculo.porcentaje_de(base, version.porcentaje)
                cierre = Markup('<p>Con tu porcentaje ({} %) la comisión de este ejemplo sería <strong>{}</strong>.</p>'
                                ).format(f'{version.porcentaje:g}', dinero(comision))
            else:
                cierre = Markup('<p class="text-muted">Escribe el porcentaje para ver cuánto sería la comisión de '
                                'este ejemplo.</p>')
            version.ejemplo_html = Markup(
                '<div class="o_dcasa_ejemplo"><p><strong>Ejemplo con números de mentira</strong>, solo para entender: '
                'no son cifras de la empresa.</p>'
                '<table class="table table-sm"><tbody>{}</tbody></table>'
                '<p>La base de este ejemplo es <strong>{}</strong>.</p>{}</div>').format(cuerpo, dinero(base), cierre)

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------

    @api.constrains('porcentaje', 'tarifa_fija', 'tope_ajuste', 'reparto_ids')
    def _check_cifras(self):
        for version in self:
            if not 0 <= version.porcentaje <= 100:
                raise ValidationError(self.env._('El porcentaje va de 0 a 100.'))
            if version.tarifa_fija < 0:
                raise ValidationError(self.env._('La tarifa fija no puede ser negativa.'))
            if version.tope_ajuste < 0:
                raise ValidationError(self.env._('El tope de un ajuste no puede ser negativo (0 es sin tope).'))
            reparto = version.reparto_ids
            if (version.porcentaje > 0 or version.tarifa_fija > 0) and not reparto:
                raise ValidationError(self.env._(
                    'Elige quiénes reciben la comisión (empleados de Nómina) y cuánto le toca a cada quien.'))
            if reparto and not calculo.suma_cien(reparto.mapped('porcentaje')):
                total = sum(reparto.mapped('porcentaje'))
                raise ValidationError(self.env._(
                    'El reparto tiene que sumar 100 %%: ahora suma %s %%. Ajusta lo que le toca a cada quien.',
                    f'{total:g}'))
            if len(reparto.empleado_id) != len(reparto):
                raise ValidationError(self.env._('Una persona sale una sola vez en el reparto.'))
            if reparto and not version._hay_quien_apruebe():
                raise ValidationError(self.env._(
                    'Para poder aprobar las liquidaciones tiene que haber al menos una persona de Gerencia o de Nómina '
                    'que NO figure entre quienes reciben (quien cobra no aprueba lo suyo). Crea el usuario de quien '
                    'va a aprobar (por ejemplo Gerencia general) antes de guardar esta versión.'))

    def _hay_quien_apruebe(self):
        """¿Queda al menos un usuario de Gerencia o de Nómina, de verdad una persona, que no cobre en esta versión?"""
        self.ensure_one()
        receptores = self.reparto_ids.empleado_id
        ligados = self.env['dcasa.web.reparto']._usuarios_de(receptores)
        candidatos = self.env['res.users'].sudo().search([('share', '=', False), ('id', '!=', SUPERUSER_ID)])
        return any(u.has_group(GRUPO) and u.id not in ligados for u in candidatos)

    # ------------------------------------------------------------------
    # La versión no se edita ni se borra; solo rige hacia adelante
    # ------------------------------------------------------------------

    def write(self, vals):
        anulando = self.env.context.get(CLAVE_ANULANDO)
        if anulando is not None and anulando is ANULANDO:
            return super().write(vals)
        if set(vals) <= {'motivo_anulacion'} and all(
                v.estado in ('programada', 'tapada') and not v.anulada for v in self):
            return super().write(vals)
        raise UserError(self.env._(
            'Una versión de las reglas no se edita: un cambio se hace guardando una versión nueva. Si todavía no rige '
            'y se puso mal, se puede anular.'))

    @api.ondelete(at_uninstall=False)
    def _no_borrar(self):
        raise UserError(self.env._(
            'Una versión de las reglas no se borra: un error se corrige guardando una versión nueva (o anulando la '
            'que todavía no rige).'))

    def action_anular(self):
        """Anula una versión que TODAVÍA NO RIGE (se puso con el año o el día equivocado): no se borra, queda con su
        motivo y quién la anuló, y deja de contar. Una que ya rige no se anula: se guarda una nueva."""
        self.check_access('write')
        if not self.env.user.has_group(GRUPO):
            raise UserError(self.env._('Solo Gerencia y quien administra la nómina anulan una versión.'))
        for version in self:
            if version.anulada or version.estado not in ('programada', 'tapada'):
                raise UserError(self.env._('Solo se anula una versión que todavía no rige.'))
            if not (version.motivo_anulacion or '').strip():
                raise UserError(self.env._('Escribe el motivo de la anulación.'))
            if self.env['dcasa.web.venta'].sudo().search_count([('reglas_id', '=', version.id)], limit=1):
                raise UserError(self.env._('Esta versión ya se usó para calcular una venta: no se puede anular.'))
            version.sudo().with_context(**{CLAVE_ANULANDO: ANULANDO}).write({
                'anulada': True, 'anulada_por': self.env.user.id, 'anulada_el': fields.Datetime.now()})
        return True

    @api.model
    def default_get(self, fields_list):
        """Una versión nunca nace anulada: ni un valor ni un ``default_*`` del contexto (que llega por RPC)."""
        valores = super().default_get(fields_list)
        for clave in CAMPOS_DEL_SISTEMA:
            if clave in valores:
                valores[clave] = False
        return valores

    @api.model
    def _validar_cifras_crudas(self, vals):
        """Las cifras que llegan de afuera (por RPC cualquiera manda ``nan``, ``inf``, un texto o un 1e30) se rechazan
        con un mensaje claro ANTES de que Odoo intente redondearlas y falle con un error de Python sin traducir (cuarta
        revisión adversarial, 2026-11-20). Un tope de 1e30 se guardaba y rompía después todos los ajustes."""
        for campo in ('porcentaje', 'tarifa_fija', 'tope_ajuste'):
            if campo not in vals:
                continue
            numero = calculo.numero_finito(vals[campo])
            etiqueta = self._fields[campo].string
            if numero is None:
                raise UserError(self.env._(
                    '«%s» no es un número válido: escribe una cifra, por ejemplo 25.50.', etiqueta))
            if campo == 'porcentaje':
                if not 0 <= numero <= 100:
                    raise ValidationError(self.env._('El porcentaje va de 0 a 100.'))
            elif abs(numero) > LIMITE_DE_DINERO:
                raise UserError(self.env._(
                    '«%(campo)s» es demasiado grande para el libro (llega hasta %(maximo)s). Revisa los ceros.',
                    campo=etiqueta, maximo=f'{LIMITE_DE_DINERO:,.2f}'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._validar_cifras_crudas(vals)
        ahora = fields.Datetime.now()
        # Quien guarda escribe el candado: dos versiones a la vez no sacan el mismo número (REPEATABLE READ).
        self.env['dcasa.web.candado']._tomar(CANDADO_NUMERACION)
        self.env.cr.execute('SELECT COALESCE(MAX(numero), 0) FROM dcasa_web_reglas')
        ultimo_numero = self.env.cr.fetchone()[0]
        for vals in vals_list:
            for clave in CAMPOS_DEL_SISTEMA:
                vals.pop(clave, None)
            desde = fields.Datetime.to_datetime(vals.get('rige_desde')) or ahora
            # Rige desde el INICIO de ese día de Panamá: hoy vale (aunque el formulario se haya abierto hace rato).
            if dia_de_panama(desde) < dia_de_panama(ahora):
                raise UserError(self.env._(
                    'Un cambio solo rige hacia adelante: no se puede poner una fecha que ya pasó.'))
            ultimo_numero += 1
            vals.update(numero=ultimo_numero, rige_desde=desde, autor=self.env.user.name)
        # Los renglones del reparto solo se crean aquí, junto con su versión.
        versiones = super(DcasaWebReglas, self.with_context(**{CLAVE_CREANDO: CREANDO_VERSION})).create(vals_list)
        # Lo cobrado HOY antes de guardar esta versión también es del sitio (rige desde el inicio del día): no se queda
        # sin dueño ni con la vendedora (el corte es el mismo para las dos).
        self.env['dcasa.web.venta']._atribuir_a_las_reglas()
        return versiones

    # ------------------------------------------------------------------
    # Qué versión rige
    # ------------------------------------------------------------------

    @api.model
    def _vigente(self, company, ahora=None):
        """La versión que rige en ``ahora`` (o ahora mismo) para ``company``; vacío si todavía no hay ninguna."""
        ahora = ahora or fields.Datetime.now()
        return self._vigente_el(company, dia_de_panama(ahora))

    def _de_este_dia(self, dia):
        """De estas versiones, la que rige el día ``dia`` (fecha de Panamá): **la última que se guardó** (no anulada)
        entre las que ya empezaron ese día o antes. Una versión nueva manda desde su fecha en adelante sobre todas las
        anteriores, aunque alguna se haya guardado antes con una fecha más lejana (esa queda tapada hasta que se
        anule) y aunque dos caigan el mismo día (gana la última guardada, no la de la hora más tardía)."""
        for version in self.sorted('numero', reverse=True):
            if not version.anulada and dia_de_panama(version.rige_desde) <= dia:
                return version
        return self.browse()

    @api.model
    def _vigente_el(self, company, dia):
        """La versión que regía el día ``dia`` (fecha de Panamá), según ``_de_este_dia``. **Una sola regla de corte, por
        día de cobro, para todos** (decisión del 2026-11-19): el día en que rige, todo lo cobrado ese día cuenta para el
        sitio y para nadie de las vendedoras; lo cobrado un día antes sigue como siempre para las vendedoras y nunca
        para el sitio."""
        return self.sudo().search([('company_id', '=', company.id), ('anulada', '=', False)])._de_este_dia(dia)

    @api.model
    def _vigente_para_cobro(self, company, dia):
        """La versión que le toca a una venta cobrada el día ``dia``: la que regía ese día, pero **nunca la de un día
        que todavía no llega**. Quien registra un pago teclea su fecha: un pago con fecha de dentro de 10 días no puede
        escoger una versión programada para entonces (tercera revisión, 2026-11-20): se calcula con la de hoy."""
        hoy = fields.Date.context_today(self.with_context(tz=ZONA))
        return self._vigente_el(company, min(dia, hoy))

    @api.model
    def _primera(self, company):
        """La primera versión que se guardó (rija ya o no): marca desde cuándo una venta online deja de ser de las
        vendedoras."""
        return self.sudo().search([('company_id', '=', company.id), ('anulada', '=', False)],
                                  order='rige_desde, numero', limit=1)

    @api.model
    def _versiones_desde(self, company):
        return self.sudo().search([('company_id', '=', company.id), ('anulada', '=', False)],
                                  order='rige_desde, numero')

    def action_nueva_version(self):
        """El botón «Nueva versión»: abre el formulario con lo que rige hoy ya escrito (la cabecera de una lista llama
        con la lista de ids, que puede venir vacía)."""
        return self._accion_nueva_version()

    def _accion_nueva_version(self):
        """Abre el formulario de una versión nueva con lo que rige hoy ya escrito: quien cambia una cosa no tiene que
        volver a escribir las demás."""
        vigente = self._vigente(self.env.company)
        contexto = {}
        if vigente:
            contexto = {
                'default_porcentaje': vigente.porcentaje, 'default_tarifa_fija': vigente.tarifa_fija,
                'default_tope_ajuste': vigente.tope_ajuste,
                'default_tarifa_periodo': vigente.tarifa_periodo,
                **{f'default_{clave}': vigente[clave] for clave in calculo.OPCIONES},
                'default_reparto_ids': [(0, 0, {'empleado_id': r.empleado_id.id, 'porcentaje': r.porcentaje,
                                                'sequence': r.sequence}) for r in vigente.reparto_ids],
            }
        accion = self.env['ir.actions.actions']._for_xml_id('dcasa_comision_web.accion_reglas_nueva')
        accion['context'] = contexto
        return accion


class DcasaWebReparto(models.Model):
    _name = 'dcasa.web.reparto'
    _description = 'Reparto de la comisión del sitio web (una persona en una versión)'
    _order = 'sequence, id'

    reglas_id = fields.Many2one('dcasa.web.reglas', required=True, index=True, ondelete='restrict')
    sequence = fields.Integer(default=10, help='El orden decide a quién se le da primero un centavo que sobra.')
    empleado_id = fields.Many2one('hr.employee', 'Persona', required=True, ondelete='restrict',
                                  domain="[('dcasa_en_planilla', '=', True)]",
                                  help='Empleados que están en Nómina. La lista no depende del departamento.')
    porcentaje = fields.Float('Le toca (%)', required=True, digits=(5, 2))
    company_id = fields.Many2one(related='reglas_id.company_id', store=True, index=True)
    usuario_ids = fields.Many2many(
        'res.users', 'dcasa_web_reparto_usuario_rel', 'reparto_id', 'usuario_id', 'Usuarios de esta persona',
        readonly=True, copy=False,
        help='Los usuarios ligados a la ficha de la persona el día en que se guardó esta versión. Quedan fijos: '
             'cambiar la ficha después no deja a quien cobra aprobar su propia liquidación.')
    currency_id = fields.Many2one(related='company_id.currency_id')
    por_pagar_comision = fields.Monetary(
        'Por pagar: porcentaje', compute='_compute_saldos',
        help='Lo que se le debe por el porcentaje de las ventas (la suma de su libro).')
    por_pagar_tarifa = fields.Monetary('Por pagar: tarifa fija', compute='_compute_saldos')

    _porcentaje_valido = models.Constraint('CHECK(porcentaje > 0 AND porcentaje <= 100)',
                                           'A cada persona le toca más de 0 y hasta 100 %.')

    @api.constrains('empleado_id', 'reglas_id')
    def _check_empleado(self):
        for linea in self:
            empleado = linea.empleado_id
            if not empleado.dcasa_en_planilla:
                raise ValidationError(self.env._(
                    '%s no está en Nómina. Los que reciben se eligen entre los empleados de Nómina.', empleado.name))
            if empleado.company_id and empleado.company_id != linea.reglas_id.company_id:
                raise ValidationError(self.env._('%s es de otra empresa.', empleado.name))

    @api.depends('empleado_id', 'company_id')
    def _compute_saldos(self):
        saldos = self.env['dcasa.web.movimiento']._saldos(self.empleado_id)
        for linea in self:
            linea.por_pagar_comision = saldos.get((linea.empleado_id.id, 'comision'), 0) / 100.0
            linea.por_pagar_tarifa = saldos.get((linea.empleado_id.id, 'tarifa'), 0) / 100.0

    @api.model
    def _usuarios_de(self, empleados):
        """``{id de usuario}`` de las personas de ``empleados``: los que su ficha nombra hoy (usuario o contacto de
        trabajo) y los que tenía ligados cuando se guardó cualquier versión del reparto donde figuró."""
        empleados = empleados.sudo().with_context(active_test=False)
        usuarios = set(empleados.user_id.ids)
        contactos = empleados.work_contact_id
        if contactos:
            usuarios |= set(self.env['res.users'].sudo().with_context(active_test=False).search(
                [('partner_id', 'in', contactos.ids)]).ids)
        usuarios |= set(self.sudo().search([('empleado_id', 'in', empleados.ids)]).usuario_ids.ids)
        return usuarios

    @api.model
    def _accion_quienes_reciben(self):
        """Nómina › Comisión del sitio web › Quiénes reciben: la lista de la versión que rige hoy."""
        vigente = self.env['dcasa.web.reglas']._vigente(self.env.company)
        accion = self.env['ir.actions.actions']._for_xml_id('dcasa_comision_web.accion_reparto')
        accion['domain'] = [('reglas_id', '=', vigente.id)] if vigente else [('id', '=', False)]
        return accion

    def action_cambiar_quienes_reciben(self):
        """Abre una versión nueva con lo de hoy ya escrito, para cambiar solo quiénes reciben."""
        return self.env['dcasa.web.reglas']._accion_nueva_version()

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(CLAVE_CREANDO) is not CREANDO_VERSION:
            raise UserError(self.env._(
                'El reparto no se agrega a una versión ya guardada: guarda una versión nueva con el reparto nuevo.'))
        for vals in vals_list:
            if 'porcentaje' in vals and calculo.numero_finito(vals['porcentaje']) is None:
                raise UserError(self.env._(
                    'Lo que le toca a cada persona no es un número válido: escribe una cifra, por ejemplo 60.'))
        lineas = super().create(vals_list)
        for linea in lineas:
            # Se congelan los usuarios ligados HOY a la ficha (no se editan: ver ``write``).
            linea.sudo().with_context(**{CLAVE_CREANDO: CREANDO_VERSION}).usuario_ids = [
                fields.Command.set(sorted(self._usuarios_de(linea.empleado_id)))]
        return lineas

    def write(self, vals):
        if self.env.context.get(CLAVE_CREANDO) is CREANDO_VERSION and set(vals) == {'usuario_ids'}:
            return super().write(vals)
        raise UserError(self.env._('El reparto de una versión no se edita: guarda una versión nueva.'))

    @api.ondelete(at_uninstall=False)
    def _no_borrar(self):
        raise UserError(self.env._('El reparto de una versión no se borra: guarda una versión nueva.'))
