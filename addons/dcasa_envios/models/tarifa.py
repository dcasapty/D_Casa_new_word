"""La tarifa de envíos vigente (una sola) y sus cargos aparte.

* Solo Gerencia y los administradores la cambian y la aprueban (el permiso del modelo y, además, el servidor).
* «Aprobada» lleva quién y cuándo, y lo pone siempre el servidor (aunque alguien mande otra cosa por RPC). Cualquier
  cambio de la fórmula o de los cargos la devuelve a revisión: mientras no esté aprobada, la pantalla dice «Tarifa en
  revisión: estos precios todavía no se usan con clientes» y Brian lo dice también.
* El historial queda en el chatter (cada campo con seguimiento y un mensaje por cada cambio de cargos).
* «Subir o bajar todo en %» (``ajuste_pct`` y los botones de ±5 %) mueve la tarifa base completa (salida, km y
  mínimo) y los cargos marcados «sube con el %».
* No trae cifras de fábrica: los precios los pone Gerencia o el archivo que carga (el repositorio es público).

Punto de entrada para la web y Juan (mañana): :meth:`cotizar_km` y :meth:`cotizar_lugar`; ver docs/ENVIOS.md.
"""
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..motor import tarjeta as motor_tarjeta
from ..motor.tarifa import COMO_SE_COBRA, Tarifa
from ..motor.texto import dinero, js_round, km_txt

AVISO_EN_REVISION = 'Tarifa en revisión: estos precios todavía no se usan con clientes.'
CAMPOS_FORMULA = ('minimo', 'ancla_a_km', 'ancla_a_precio', 'ancla_b_km', 'ancla_b_precio', 'ancla_b_nombre',
                  'ajuste_pct', 'paso', 'modo', 'max_km')
CAMPOS_DE_LA_APROBACION = ('aprobada', 'aprobada_por', 'aprobada_el')
PASOS = [('1', '$1'), ('5', '$5'), ('10', '$10'), ('0', 'No redondear')]
AJUSTE_MIN, AJUSTE_MAX = -90.0, 300.0
MAX_KM = 2000


class EnvioTarifa(models.Model):
    _name = 'dcasa.envio.tarifa'
    _inherit = ['mail.thread']
    _description = 'Tarifa de envíos'

    name = fields.Char('Nombre', required=True, default='Tarifa de envíos')
    unica = fields.Boolean(default=True, readonly=True)
    minimo = fields.Float('Mínimo (cerca de la tienda)', tracking=True)
    ancla_a_km = fields.Float('Precio a … km', tracking=True, help='Kilómetros del primer punto.')
    ancla_a_precio = fields.Float('… cuesta', tracking=True)
    ancla_b_km = fields.Float('Precio a … km (lejos)', tracking=True, help='Kilómetros del segundo punto.')
    ancla_b_precio = fields.Float('… cuesta (lejos)', tracking=True)
    ancla_b_nombre = fields.Char('Nombre del segundo punto', tracking=True,
                                 help='Por ejemplo, el pueblo que está a esa distancia.')
    ajuste_pct = fields.Float('Subir o bajar todo (%)', tracking=True,
                              help='Sube o baja la tarifa base completa (salida, kilómetros y mínimo). 0 % = la tarifa '
                                   'sin cambios.')
    paso = fields.Selection(PASOS, string='Redondear a', required=True, default='0', tracking=True)
    modo = fields.Selection([('arriba', 'Hacia arriba'), ('cercano', 'Al más cercano')], string='Cómo redondear',
                            required=True, default='arriba', tracking=True)
    max_km = fields.Float('Cotizar aparte desde (km)', tracking=True,
                          help='Más lejos de esto (o sin carretera) el envío se cotiza aparte.')
    cargo_ids = fields.One2many('dcasa.envio.cargo', 'tarifa_id', 'Cargos aparte')
    aprobada = fields.Boolean('Aprobada', readonly=True, tracking=True)
    aprobada_por = fields.Many2one('res.users', 'Aprobada por', readonly=True)
    aprobada_el = fields.Datetime('Aprobada el', readonly=True)
    nota = fields.Text('Nota')
    version_archivo = fields.Integer('Versión del archivo', readonly=True)
    fecha_archivo = fields.Date('Fecha del archivo', readonly=True)
    cargada_por = fields.Many2one('res.users', 'Cargada del archivo por', readonly=True)
    cargada_el = fields.Datetime('Cargada del archivo el', readonly=True)
    configurada = fields.Boolean(compute='_compute_textos')
    regla_html = fields.Html('Cómo se calcula', compute='_compute_textos', sanitize=False)
    formula_txt = fields.Char('Fórmula', compute='_compute_textos')
    efecto_html = fields.Html('Efecto del %', compute='_compute_textos', sanitize=False)
    tramos_html = fields.Html('Tarifa base por tramos', compute='_compute_textos', sanitize=False)

    _una_sola = models.Constraint('UNIQUE(unica)', 'Hay una sola tarifa de envíos: edita la que ya existe.')

    # --- Validaciones ----------------------------------------------------------------------------------------------
    @api.constrains(*CAMPOS_FORMULA)
    def _revisar_formula(self):
        for tarifa in self:
            if min(tarifa.minimo, tarifa.ancla_a_km, tarifa.ancla_a_precio, tarifa.ancla_b_km, tarifa.ancla_b_precio,
                   tarifa.max_km) < 0:
                raise ValidationError(self.env._('Los precios y los kilómetros de la tarifa no pueden ser negativos.'))
            if (tarifa.ancla_a_km or tarifa.ancla_b_km) and tarifa.ancla_b_km <= tarifa.ancla_a_km:
                raise ValidationError(self.env._('El segundo punto tiene que estar más lejos que el primero.'))
            if tarifa.max_km and not 10 <= tarifa.max_km <= MAX_KM:
                raise ValidationError(self.env._('«Cotizar aparte desde» va de 10 a %s km.', MAX_KM))
            if not AJUSTE_MIN <= tarifa.ajuste_pct <= AJUSTE_MAX:
                raise ValidationError(self.env._('El ajuste va de −90 % a +300 %.'))

    # --- Para el motor ---------------------------------------------------------------------------------------------
    def _como_ajustes(self):
        """La tarifa con la forma del HTML (``ajustes``), la que entiende el motor."""
        self.ensure_one()
        return {
            'minimo': self.minimo,
            'anclaA': {'km': self.ancla_a_km, 'precio': self.ancla_a_precio},
            'anclaB': {'km': self.ancla_b_km, 'precio': self.ancla_b_precio, 'nombre': self.ancla_b_nombre or ''},
            'ajustePct': self.ajuste_pct,
            'paso': int(self.paso or 0),
            'modo': self.modo,
            'maxKm': self.max_km,
            'aprobada': self.aprobada,
            'extras': [cargo._como_extra() for cargo in self.cargo_ids.sorted(lambda c: (c.sequence, c.id))],
        }

    def _motor(self):
        self.ensure_one()
        return Tarifa(self._como_ajustes())

    @api.model
    def _vigente(self):
        return self.sudo().search([], limit=1)

    @api.model
    def _vigente_motor(self):
        """La tarifa vigente lista para cotizar, o ``None`` si no hay o le faltan los precios."""
        tarifa = self._vigente()
        if not tarifa:
            return None
        motor = tarifa._motor()
        return motor if motor.configurada else None

    @api.model
    def _estado_publico(self):
        tarifa = self._vigente()
        configurada = bool(tarifa) and tarifa._motor().configurada
        aprobada = configurada and tarifa.aprobada
        return {'configurada': configurada, 'aprobada': aprobada,
                'aviso': '' if aprobada else AVISO_EN_REVISION if configurada else
                'Todavía no hay tarifa de envíos cargada.'}

    @api.model
    def _para_la_pantalla(self):
        """La regla, los tramos y el estado para la calculadora (solo lectura)."""
        estado = self._estado_publico()
        tarifa = self._vigente()
        if not estado['configurada']:
            return dict(estado, regla=[], tramos=[], nota_tramos='', max_km=0)
        motor = tarifa._motor()
        tramos = [{'km_txt': t['km_txt'], 'precio_txt': t['precio_txt']} for t in motor.tramos_para_mostrar()]
        return dict(estado, regla=[{'clase': clase, 'texto': texto} for clase, texto in motor.regla()], tramos=tramos,
                    nota_tramos=motor.nota_tramos(), max_km=motor.max_km,
                    aprobada_por=tarifa.aprobada_por.name or '',
                    aprobada_el=fields.Datetime.to_string(tarifa.aprobada_el) if tarifa.aprobada_el else '')

    # --- La API para cotizar (pantalla, Brian y, mañana, la web) ---------------------------------------------------
    @api.model
    def _cotizacion(self, motor, km, peaje, lugar=None):
        cotizacion = motor.cotizar(km, peaje)
        datos = {
            'con_precio': True, 'km': km, 'km_txt': f'{km_txt(km)} km', 'peaje': bool(peaje),
            'base': cotizacion['base'],
            'extras': [{'nombre': c['nombre'], 'monto': c['v']} for c in cotizacion['extras']],
            'total': cotizacion['total'], 'total_txt': dinero(cotizacion['total']),
            'desglose': motor_tarjeta.desglose(cotizacion),
        }
        if lugar is not None:
            datos['texto_cliente'] = motor_tarjeta.texto_cliente(lugar, cotizacion)
        return datos

    @api.model
    def cotizar_km(self, km, peaje=False):
        """El precio de un envío de ``km`` por carretera desde la tienda (``peaje``: la ruta pasa por peaje).

        Datos puros, iguales para cualquier usuario: ``{'con_precio', 'km', 'base', 'extras': [{'nombre', 'monto'}],
        'total', 'total_txt', 'desglose', 'aviso_lejos', 'tarifa': {aprobada, configurada, aviso}}``. Más lejos que
        «cotizar aparte desde» da el precio de la fórmula y ``aviso_lejos`` (el HTML hacía lo mismo)."""
        self.env['dcasa.envio.lugar']._exigir_lectura()
        estado = self._estado_publico()
        try:
            km = float(km)
        except (TypeError, ValueError):
            km = -1.0
        if not 0 <= km <= MAX_KM:
            return {'con_precio': False, 'motivo': 'km', 'tarifa': estado,
                    'mensaje': f'Escribe los kilómetros (de 0 a {MAX_KM}).'}
        motor = self._vigente_motor()
        if not motor:
            return {'con_precio': False, 'motivo': 'sin_tarifa', 'tarifa': estado, 'mensaje': estado['aviso']}
        datos = self._cotizacion(motor, km, bool(peaje))
        datos['aviso_lejos'] = (f'Pasa de {km_txt(motor.max_km)} km: confirmar con Gerencia.'
                                if km > motor.max_km else '')
        datos['tarifa'] = estado
        return datos

    @api.model
    def cotizar_lugar(self, lugar):
        """El precio del envío a un lugar: un registro o id de ``dcasa.envio.lugar``, o un diccionario con la forma
        del HTML (``nombre``, ``km``, ``peaje``, ``estado``, ``corr``, ``dist``…).

        Datos puros: ``{'con_precio', 'lugar', 'km', 'base', 'extras', 'total', 'total_txt', 'desglose',
        'texto_cliente', 'tarifa'}``; sin precio (lejos, sin carretera, sin medir), ``con_precio`` falso y
        ``motivo``."""
        Lugar = self.env['dcasa.envio.lugar']
        Lugar._exigir_lectura()
        if isinstance(lugar, int):
            lugar = Lugar.sudo().browse(lugar).exists()
        if isinstance(lugar, models.BaseModel):
            if lugar._name != 'dcasa.envio.lugar' or len(lugar) != 1:
                raise UserError(self.env._('Elige un solo lugar de envío.'))
            datos_lugar = lugar.sudo()._como_motor()
        elif isinstance(lugar, dict):
            datos_lugar = lugar
        else:
            raise UserError(self.env._('Elige un lugar de envío.'))
        estado = self._estado_publico()
        motor = self._vigente_motor()
        if not motor:
            return {'con_precio': False, 'motivo': 'sin_tarifa', 'lugar': datos_lugar.get('nombre'), 'tarifa': estado,
                    'mensaje': estado['aviso']}
        if not motor.con_precio(datos_lugar):
            return {'con_precio': False, 'motivo': 'aparte', 'lugar': datos_lugar.get('nombre'), 'tarifa': estado,
                    'km': datos_lugar.get('km'), 'mensaje': 'Este envío se cotiza aparte (lejos, sin carretera o sin '
                                                             'medir): consúltalo con Gerencia.'}
        datos = self._cotizacion(motor, datos_lugar['km'], datos_lugar.get('peaje'), datos_lugar)
        datos.update(lugar=datos_lugar.get('nombre'), tarifa=estado)
        return datos

    # --- Textos de la ficha -------------------------------------------------------------------------------------------
    @api.depends(*CAMPOS_FORMULA, 'cargo_ids.monto', 'cargo_ids.activo', 'cargo_ids.como', 'cargo_ids.desde',
                 'cargo_ids.ajusta', 'cargo_ids.name')
    def _compute_textos(self):
        for tarifa in self:
            motor = tarifa._motor()
            tarifa.configurada = motor.configurada
            if not motor.configurada:
                tarifa.regla_html = tarifa.efecto_html = tarifa.tramos_html = False
                tarifa.formula_txt = ''
                continue
            tarifa.regla_html = Markup('').join(
                Markup('<span class="o_dcasa_envios_ficha">%s</span>') % texto if clase == 'ficha'
                else Markup('<span class="o_dcasa_envios_mas">%s</span>') % texto for clase, texto in motor.regla())
            tarifa.formula_txt = motor.formula_txt()
            tarifa.efecto_html = Markup('').join(Markup('<span class="o_dcasa_envios_efecto">%s</span>') % e['texto']
                                                 for e in motor.efecto())
            filas = Markup('').join(Markup('<div class="o_dcasa_envios_tramo"><span>%s</span><b>%s</b></div>')
                                    % (t['km_txt'], t['precio_txt']) for t in motor.tramos_para_mostrar())
            tarifa.tramos_html = Markup('<p class="text-muted mb-2">%s</p><div class="o_dcasa_envios_tramos">%s</div>'
                                        ) % (motor.nota_tramos(), filas)

    # --- Cambios y aprobación ---------------------------------------------------------------------------------------
    def _firma(self):
        """Todo lo que cambia un precio: la fórmula y los cargos."""
        self.ensure_one()
        return (tuple(self[c] for c in CAMPOS_FORMULA),
                tuple(sorted(tuple(sorted(cargo._como_extra().items())) for cargo in self.cargo_ids)))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            self.env['dcasa.envio.lugar']._exigir_gerencia()
        if len(vals_list) > 1 or self.sudo().search_count([]):
            raise UserError(self.env._('Hay una sola tarifa de envíos: edita la que ya existe.'))
        vals_list = [{k: v for k, v in vals.items() if k not in CAMPOS_DE_LA_APROBACION} for vals in vals_list]
        tarifas = super().create(vals_list)
        self.env['dcasa.envio.lugar']._subir_version()
        return tarifas

    def write(self, vals):
        vals = {k: v for k, v in vals.items() if k not in ('aprobada_por', 'aprobada_el', 'unica')}
        aprobar = vals.pop('aprobada', None)
        if aprobar is not None or set(vals) & set(CAMPOS_FORMULA) or 'cargo_ids' in vals:
            self.env['dcasa.envio.lugar']._exigir_gerencia()
        antes = {tarifa.id: tarifa._firma() for tarifa in self}
        resultado = super().write(vals) if vals else True
        for tarifa in self:
            if tarifa._firma() != antes[tarifa.id]:
                tarifa._volver_a_revision()
        if aprobar:
            self._aprobar()
        elif aprobar is not None:
            self._quitar_aprobacion()
        self.env['dcasa.envio.lugar']._subir_version()
        return resultado

    def unlink(self):
        raise UserError(self.env._('La tarifa de envíos no se borra: se cambia (y queda el historial).'))

    def _volver_a_revision(self, motivo=None):
        for tarifa in self.filtered('aprobada'):
            super(EnvioTarifa, tarifa).write({'aprobada': False, 'aprobada_por': False, 'aprobada_el': False})
            tarifa.message_post(body=motivo or self.env._(
                'La tarifa cambió: vuelve a revisión hasta que Gerencia la apruebe otra vez.'))

    def _aprobar(self):
        for tarifa in self:
            if not tarifa._motor().configurada:
                raise UserError(self.env._('La tarifa todavía no tiene sus precios: carga el archivo o escribe el '
                                           'mínimo y los dos puntos antes de aprobarla.'))
            super(EnvioTarifa, tarifa).write({'aprobada': True, 'aprobada_por': self.env.uid,
                                              'aprobada_el': fields.Datetime.now()})
            tarifa.message_post(body=self.env._(
                'Tarifa aprobada por %s. La calculadora ya no muestra el aviso de revisión.', self.env.user.name))

    def _quitar_aprobacion(self):
        for tarifa in self.filtered('aprobada'):
            super(EnvioTarifa, tarifa).write({'aprobada': False, 'aprobada_por': False, 'aprobada_el': False})
            tarifa.message_post(body=self.env._('%s quitó la aprobación: la tarifa vuelve a revisión.',
                                                self.env.user.name))

    # --- Botones ------------------------------------------------------------------------------------------------------
    def action_aprobar(self):
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        self.check_access('write')
        self._aprobar()
        return True

    def action_quitar_aprobacion(self):
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        self.check_access('write')
        self._quitar_aprobacion()
        return True

    def _mover_ajuste(self, cuanto):
        for tarifa in self:
            nuevo = js_round((tarifa.ajuste_pct + cuanto) * 10) / 10
            tarifa.write({'ajuste_pct': max(AJUSTE_MIN, min(AJUSTE_MAX, nuevo))})
        return True

    def action_subir_5(self):
        return self._mover_ajuste(5)

    def action_bajar_5(self):
        return self._mover_ajuste(-5)

    def action_cargar_archivo(self):
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Cargar lugares y tarifa desde el archivo'),
            'res_model': 'dcasa.envio.importar', 'view_mode': 'form', 'target': 'new',
        }

    @api.model
    def action_abrir(self):
        """Envíos › Tarifa: la ficha de la tarifa vigente (la crea vacía, sin cifras, la primera vez)."""
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        tarifa = self.search([], limit=1) or self.create({})
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Tarifa de envíos'), 'res_model': self._name,
            'res_id': tarifa.id, 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }

    def action_abrir_calculadora(self):
        return self.env['ir.actions.actions']._for_xml_id('dcasa_envios.accion_calculadora')


class EnvioCargo(models.Model):
    _name = 'dcasa.envio.cargo'
    _description = 'Cargo aparte de la tarifa de envíos'
    _order = 'sequence, id'

    tarifa_id = fields.Many2one('dcasa.envio.tarifa', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    codigo = fields.Char('Código', help='Como lo llama el archivo (viatico, honorarios, peaje…).')
    name = fields.Char('Nombre', required=True, default='Otro cargo')
    como = fields.Selection(list(COMO_SE_COBRA.items()), string='Cómo se cobra', required=True, default='viaje')
    monto = fields.Float('Monto $', digits=(10, 2))
    desde = fields.Float('Desde km', help='Solo para «fijo si pasa de cierto km» y «por km después de cierto km».')
    ajusta = fields.Boolean('Sube con el %', help='Este cargo también sube o baja con el ajuste en %.')
    activo = fields.Boolean('Se cobra', help='Nada se cobra hasta que pongas el monto y lo marques.')

    _monto_positivo = models.Constraint('CHECK(monto >= 0 AND desde >= 0)',
                                        'El monto y los km no pueden ser negativos.')

    def _como_extra(self):
        self.ensure_one()
        return {'id': self.codigo or f'c{self.id}', 'nombre': self.name or '', 'como': self.como,
                'monto': self.monto, 'desde': self.desde, 'ajusta': self.ajusta, 'activo': self.activo}

    def _describir(self):
        if not self:
            return self.env._('sin cargos aparte')
        partes = []
        for cargo in self:
            estado = self.env._('se cobra') if cargo.activo and cargo.monto > 0 else self.env._('no se cobra')
            desde = f' desde {km_txt(cargo.desde)} km' if cargo.como in ('desde_km', 'km_desde') else ''
            partes.append(f'{cargo.name}: {COMO_SE_COBRA[cargo.como].lower()}{desde}, {dinero(cargo.monto)} ({estado})')
        return '; '.join(partes)

    def _anotar(self, tarifas, antes):
        for tarifa in tarifas.exists():
            if tarifa._firma() != antes.get(tarifa.id):
                tarifa._volver_a_revision()
                tarifa.message_post(body=Markup('%s<br/>%s') % (
                    self.env._('Cargos aparte cambiados por %s:', self.env.user.name),
                    escape(tarifa.cargo_ids._describir())))
        self.env['dcasa.envio.lugar']._subir_version()

    @api.model_create_multi
    def create(self, vals_list):
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        tarifas = self.env['dcasa.envio.tarifa'].browse({v.get('tarifa_id') for v in vals_list if v.get('tarifa_id')})
        antes = {t.id: t._firma() for t in tarifas.exists()}
        cargos = super().create(vals_list)
        self._anotar(cargos.tarifa_id, antes)
        return cargos

    def write(self, vals):
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        tarifas = self.tarifa_id
        antes = {t.id: t._firma() for t in tarifas}
        resultado = super().write(vals)
        self._anotar(tarifas | self.tarifa_id, antes)
        return resultado

    def unlink(self):
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        tarifas = self.tarifa_id
        antes = {t.id: t._firma() for t in tarifas}
        resultado = super().unlink()
        self._anotar(tarifas, antes)
        return resultado
