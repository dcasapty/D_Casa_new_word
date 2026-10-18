"""Cola de la Conversions API de Meta (``dcasa.meta.evento``).

Cada compra pagada deja UNA fila (``factura-<id>``) desde el enganche del cobro, sin HTTP y sin poder hacerlo fallar
(``account_move.py``). Un cron la manda después, por lotes y cada lote en su propia transacción
(``_dcasa_cron_enviar``), y otro cron diario borra lo que ya no hace falta (``_dcasa_cron_retencion``).

Nada sale hacia Meta si falta una de estas cuatro cosas (docs/META_EVENTOS.md §1): el interruptor encendido, la
sección de Meta publicada en la política de privacidad, el token en el entorno y el consentimiento de la persona (la
fila sin consentimiento queda ``omitido`` y sin datos). Las tres primeras se exigen al encender (Ajustes) y otra vez
en cada corrida del cron. Fuera de producción solo sale lo que lleva el código de prueba.
"""
import calendar
import json
import logging
from datetime import timedelta

from odoo import api, fields, models, modules
from odoo.exceptions import AccessError
from odoo.tools import str2bool

from . import meta_api

_logger = logging.getLogger(__name__)

PARAM = 'dcasa_meta.'
PARAM_TOKEN_RECHAZADO = 'dcasa_meta.token_rechazado'
# Retención (días; valores técnicos, ajustables con el parámetro dcasa_meta.<nombre>).
DIAS_DATOS = 7          # se borra el JSON de lo que ya no está pendiente
DIAS_FILAS = 180        # se borra la fila entera
DIAS_NAVEGADOR = 30     # se limpian los datos del navegador de un pedido que nunca se pagó
DIAS_DESCARTE = 6       # Meta rechaza lo de más de 7 días: a los 6 se descarta
LOTE = 100
MAX_LOTES = 50          # tope de vueltas por corrida del cron
ESPERAS_MIN = (1, 5, 15, 60, 360)   # 5xx, 429 y tiempo agotado: 1, 5 y 15 minutos, 1 hora y 6 horas
INTENTOS_INVALIDO = 2   # otro 4xx: error tras dos intentos
CLAVE_PRECOMMIT = 'dcasa_meta.envio_programado'
PAUSA_ENVIO = timedelta(seconds=30)

GRUPOS_GERENCIA = ('sales_team.group_sale_manager', 'base.group_system')


def leer_config(env):
    """Ajustes de Meta (Ajustes › Meta (Facebook e Instagram)). Todo apagado y vacío de fábrica."""
    param = env['ir.config_parameter'].sudo()

    def encendido(clave):
        return str2bool(param.get_param(PARAM + clave) or 'False', False)

    return {
        'pixel_id': (param.get_param(PARAM + 'pixel_id') or '').strip(),
        'pixel_activo': encendido('pixel_activo'),
        'capi_web': encendido('capi_web'),
        'capi_tienda': encendido('capi_tienda'),
        'test_event_code': (param.get_param(PARAM + 'test_event_code') or '').strip(),
        'graph_version': (param.get_param(PARAM + 'graph_version') or meta_api.VERSION_GRAPH).strip(),
    }


def dias(env, clave, defecto):
    try:
        return max(1, int(env['ir.config_parameter'].sudo().get_param(PARAM + clave) or defecto))
    except (TypeError, ValueError):
        return defecto


def segundos_unix(momento):
    """``event_time`` de Meta: segundos Unix (no milisegundos) de un Datetime de Odoo (UTC sin zona)."""
    return calendar.timegm(momento.utctimetuple())


def es_gerencia(env):
    return env.su or any(env.user.has_group(grupo) for grupo in GRUPOS_GERENCIA)


class DcasaMetaEvento(models.Model):
    _name = 'dcasa.meta.evento'
    _description = 'Evento enviado a Meta (Conversions API)'
    _order = 'id desc'
    _rec_name = 'event_id'

    event_name = fields.Char('Evento', required=True, readonly=True)
    event_id = fields.Char('ID del evento', required=True, readonly=True, index=True)
    action_source = fields.Selection(
        [('website', 'Sitio web'), ('physical_store', 'Tienda física')], string='Dónde', readonly=True)
    origen = fields.Selection(
        [('web', 'Venta de la web'), ('tienda', 'Venta de la tienda'), ('prueba', 'Prueba')],
        string='Origen', readonly=True, index=True,
        help='Qué interruptor la manda: «Ventas de la web» o «Ventas de la tienda».')
    event_time = fields.Datetime('Momento', required=True, readonly=True)
    datos = fields.Text(
        'Datos listos para enviar', readonly=True, groups='base.group_system',
        help='JSON tal como sale hacia Meta: el correo y el celular ya cifrados con SHA-256, nunca en claro. '
             'Se borra a los pocos días.')
    estado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('enviado', 'Enviado'),
        ('error', 'Error'),
        ('descartado', 'Descartado (muy viejo)'),
        ('omitido', 'No se envía'),
        ('cancelado', 'Cancelado'),
    ], default='pendiente', required=True, readonly=True, index=True)
    motivo = fields.Char(readonly=True)
    valor = fields.Float('Valor sin ITBMS', readonly=True, digits='Product Price')
    moneda = fields.Char(readonly=True)
    intentos = fields.Integer(readonly=True)
    proximo_intento = fields.Datetime('Próximo intento', readonly=True)
    ultimo_error = fields.Char('Último error', readonly=True)
    fbtrace_id = fields.Char('Rastreo de Meta (fbtrace_id)', readonly=True)
    enviado_en = fields.Datetime('Enviado', readonly=True)
    move_id = fields.Many2one('account.move', 'Factura', readonly=True, ondelete='set null', index='btree_not_null')
    order_id = fields.Many2one('sale.order', 'Pedido web', readonly=True, ondelete='set null')
    es_prueba = fields.Boolean('Es una prueba', readonly=True)

    _event_id_unico = models.Constraint('UNIQUE(event_id)', 'Ese evento ya está en la cola de Meta.')

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_config(self):
        return leer_config(self.env)

    # ------------------------------------------------------------------
    # Encolar (desde el cobro: solo inserta, nunca habla con Meta)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_encolar_compra(self, move):
        """Encola el Purchase de una factura pagada (``factura-<id>``). Nunca hace HTTP.

        Ya encolada: no hace nada, salvo que esté ``cancelado`` (volvió a borrador o se canceló y ahora se pagó otra
        vez): entonces se vuelve a armar con lo que tiene hoy la factura y pasa a ``pendiente``.
        """
        move = move.sudo()  # quien cobra puede no ver los pedidos: aquí solo se lee para armar el evento
        config = self._dcasa_config()
        pedido_web = move._dcasa_meta_pedido_web()
        origen = 'web' if pedido_web else 'tienda'
        if not config['capi_web' if origen == 'web' else 'capi_tienda']:
            return self.browse()
        if move.currency_id.compare_amounts(move.amount_untaxed, 0.0) <= 0:
            return self.browse()
        Evento = self.sudo()
        event_id = f'factura-{move.id}'
        existente = Evento.search([('event_id', '=', event_id)], limit=1)
        if existente and existente.estado != 'cancelado':
            return existente
        valores = Evento._dcasa_armar_compra(move, pedido_web, origen)
        if existente:
            existente.write(dict(valores, intentos=0, proximo_intento=False, ultimo_error=False, fbtrace_id=False,
                                 enviado_en=False))
            fila = existente
        else:
            fila = Evento.create(valores)
        if pedido_web:
            pedido_web._dcasa_meta_limpiar_navegador()
        if fila.estado == 'pendiente':
            Evento._dcasa_programar_envio()
        return fila

    @api.model
    def _dcasa_armar_compra(self, move, pedido_web, origen):
        """Valores de la fila del Purchase según los dos consentimientos (docs/META_EVENTOS.md, contrato 2.5).

        * Navegador (A): ``_fbp``, ``_fbc``, IP, navegador y URL, tomados en el checkout solo con consentimiento.
        * Persona (B): la casilla de la ficha o la del checkout de ESE pedido. Habilita el correo y el celular cifrados.
        Sin ninguno: ``omitido`` y sin datos. Con consentimiento pero sin nada con qué emparejar: ``omitido`` también.
        """
        comercial = move.partner_id.commercial_partner_id.sudo()
        ahora = fields.Datetime.now()
        base = {
            'event_name': 'Purchase',
            'event_id': f'factura-{move.id}',
            'event_time': ahora,
            'origen': origen,
            'move_id': move.id,
            'order_id': pedido_web.id if pedido_web else False,
            'valor': move.amount_untaxed,
            'moneda': move.currency_id.name,
            'es_prueba': False,
        }
        custom_data = move._dcasa_meta_custom_data()
        if not custom_data['contents']:
            return dict(base, estado='omitido', datos=False, action_source=False,
                        motivo=self.env._('Sin productos (solo anticipo, servicios o envío)'))
        consentimiento_persona = bool(comercial.dcasa_meta_consentimiento_fecha) or bool(
            pedido_web and pedido_web.dcasa_meta_consentimiento_compra)
        navegador = pedido_web._dcasa_meta_navegador() if pedido_web else {}
        if not (consentimiento_persona or navegador):
            return dict(base, estado='omitido', datos=False, action_source=False,
                        motivo=self.env._('Sin consentimiento de la persona'))

        user_data = {}
        if consentimiento_persona:
            correo = meta_api.hash_correo(move.partner_id.email) or meta_api.hash_correo(comercial.email)
            celular = None
            for numero in (comercial.dcasa_celular, move.partner_id.phone, comercial.phone):
                celular = meta_api.hash_telefono(numero)
                if celular:
                    break
            if correo:
                user_data['em'] = correo
            if celular:
                user_data['ph'] = celular
            if correo or celular:
                user_data['external_id'] = meta_api.hash_id_externo(comercial.id)
                pais = meta_api.hash_pais(comercial.country_id.code)
                if pais:
                    user_data['country'] = pais
        if navegador:
            user_data.update({clave: valor for clave, valor in (
                ('fbp', navegador.get('fbp')), ('fbc', navegador.get('fbc')),
                ('client_ip_address', navegador.get('ip')), ('client_user_agent', navegador.get('ua')),
            ) if valor})
        if not (user_data.get('em') or user_data.get('ph') or navegador):
            return dict(base, estado='omitido', datos=False, action_source=False,
                        motivo=self.env._('Sin datos para emparejar (ni correo ni celular)'))

        # «website» exige el navegador (client_user_agent). Un pedido web sin él (la persona aceptó en la tienda,
        # no en el navegador) se cobra en la tienda: va como venta de tienda física.
        action_source = 'website' if navegador else 'physical_store'
        evento = {
            'event_name': 'Purchase',
            'event_time': segundos_unix(ahora),
            'event_id': base['event_id'],
            'action_source': action_source,
            'user_data': user_data,
            'custom_data': custom_data,
        }
        if action_source == 'website' and navegador.get('url'):
            evento['event_source_url'] = navegador['url']
        return dict(base, estado='pendiente', action_source=action_source, motivo=False,
                    datos=json.dumps(evento, separators=(',', ':')))

    @api.model
    def _dcasa_programar_envio(self):
        """Dispara el cron al confirmar la transacción (una vez por transacción; si el cobro se deshace, también
        el disparo). El intervalo de 10 minutos es la red de seguridad."""
        cr = self.env.cr
        if cr.precommit.data.get(CLAVE_PRECOMMIT):
            return
        cron = self.env.ref('dcasa_meta_eventos.cron_enviar_eventos', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger(fields.Datetime.now() + PAUSA_ENVIO)
            cr.precommit.data[CLAVE_PRECOMMIT] = True

    @api.model
    def _dcasa_cancelar_pendientes(self, moves, motivo):
        """La factura volvió a borrador o se canceló: lo que no salió no sale, tampoco lo que quedó «con error» (si
        no, «Reintentar ahora» reportaría una venta anulada). Lo ya enviado no se retracta (Meta no tiene cómo)."""
        filas = self.sudo().search([('move_id', 'in', moves.ids), ('estado', 'in', ('pendiente', 'error'))])
        if filas:
            filas.write({'estado': 'cancelado', 'motivo': motivo, 'proximo_intento': False})
        return filas

    # ------------------------------------------------------------------
    # Envío (cron)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_puede_enviar(self, config, secreto):
        """Lo que la Conversions API necesita para mandar algo, además del consentimiento de cada fila."""
        return bool(secreto and meta_api.RE_PIXEL.match(config['pixel_id'])
                    and self.env['website']._dcasa_meta_privacidad_lista())

    @api.model
    def _dcasa_cron_enviar(self):
        """Manda lo pendiente por lotes de hasta 100, cada lote en su propia transacción.

        No envía nada sin token, sin ID de píxel, sin la sección de Meta en la política de privacidad o con los
        interruptores apagados. Fuera de producción solo manda con el código de prueba (si no hay, lo pendiente
        queda ``omitido``: «entorno de pruebas»).
        """
        Evento = self.sudo()
        ahora = fields.Datetime.now()
        limite = ahora - timedelta(days=DIAS_DESCARTE)
        viejos = Evento.search([('estado', '=', 'pendiente'), ('event_time', '<', limite)])
        if viejos:
            viejos.write({'estado': 'descartado', 'proximo_intento': False, 'datos': False,
                          'motivo': self.env._('Más de %s días: Meta ya no lo acepta', DIAS_DESCARTE)})
        config = self._dcasa_config()
        origenes = [o for o, clave in (('web', 'capi_web'), ('tienda', 'capi_tienda')) if config[clave]]
        secreto = meta_api.token()
        if not origenes or not self._dcasa_puede_enviar(config, secreto):
            return 0
        codigo = None
        if not meta_api.es_produccion():
            codigo = config['test_event_code'] or None
            if not codigo:
                pendientes = Evento.search([('estado', '=', 'pendiente'), ('origen', 'in', origenes)])
                pendientes.write({'estado': 'omitido', 'datos': False, 'proximo_intento': False,
                                  'motivo': self.env._('Entorno de pruebas: sin código de prueba no se envía')})
                return 0
        en_prueba = modules.module.current_test
        enviados = 0
        for _vuelta in range(MAX_LOTES):
            dominio = [('estado', '=', 'pendiente'), ('origen', 'in', origenes),
                       '|', ('proximo_intento', '=', False), ('proximo_intento', '<=', ahora)]
            lote = Evento.search(dominio, order='id', limit=LOTE)
            if not lote:
                break
            tipo = lote._dcasa_enviar(config, secreto, codigo)
            enviados += len(lote.filtered(lambda f: f.estado == 'enviado'))
            if tipo == meta_api.TOKEN:
                break
            if not en_prueba and self.env['ir.cron']._commit_progress(
                    len(lote), remaining=Evento.search_count(dominio)) <= 0:
                break  # se acabó el tiempo del cron: sigue en la próxima corrida
        return enviados

    def _dcasa_enviar(self, config, secreto, codigo):
        """Manda estas filas en un solo POST y anota el resultado. Devuelve el tipo de resultado (meta_api)."""
        ahora = fields.Datetime.now()
        filas, eventos = self.browse(), []
        for fila in self:
            try:
                eventos.append(json.loads(fila.datos or ''))
                filas |= fila
            except ValueError:
                fila.write({'estado': 'error', 'motivo': self.env._('Datos ilegibles'), 'datos': False})
        if not filas:
            return meta_api.INVALIDO
        resultado = meta_api.enviar(eventos, config['pixel_id'], config['graph_version'], secreto, codigo)
        tipo = resultado['tipo']
        if tipo == meta_api.OK:
            filas._dcasa_anotar_enviado(resultado, ahora)
        elif tipo == meta_api.TOKEN:
            filas._dcasa_anotar_token_rechazado(resultado, ahora)
        elif tipo == meta_api.REINTENTAR:
            filas._dcasa_anotar_reintento(resultado, ahora)
        elif len(filas) > 1:
            # Un 400 del lote entero: uno por uno, para aislar el evento malo.
            _logger.warning('Meta: el lote de %s eventos fue rechazado (HTTP %s); se prueba uno por uno.',
                            len(filas), resultado['status'])
            for fila in filas:
                if fila._dcasa_enviar(config, secreto, codigo) == meta_api.TOKEN:
                    return meta_api.TOKEN
        else:
            filas._dcasa_anotar_rechazo(resultado, ahora)
        return tipo

    def _dcasa_anotar_enviado(self, resultado, ahora):
        for fila in self:
            fila.write({'estado': 'enviado', 'enviado_en': ahora, 'fbtrace_id': resultado['fbtrace_id'] or False,
                        'ultimo_error': False, 'proximo_intento': False, 'motivo': False,
                        'intentos': fila.intentos + 1})
        param = self.env['ir.config_parameter'].sudo()
        if param.get_param(PARAM_TOKEN_RECHAZADO):
            param.set_param(PARAM_TOKEN_RECHAZADO, False)
        _logger.info('Meta: %s evento(s) enviados (HTTP %s).', len(self), resultado['status'])

    def _dcasa_anotar_token_rechazado(self, resultado, ahora):
        """El token no sirve: todo sigue pendiente (sin gastar intentos) y Ajustes lo avisa."""
        self.write({'ultimo_error': resultado['mensaje'] or False})
        self.env['ir.config_parameter'].sudo().set_param(PARAM_TOKEN_RECHAZADO, fields.Datetime.to_string(ahora))
        _logger.warning('Meta: el token de la Conversions API no funciona (HTTP %s): %s',
                        resultado['status'], resultado['mensaje'])

    def _dcasa_anotar_reintento(self, resultado, ahora):
        """5xx, 429 o tiempo agotado: espera progresiva de 1, 5 y 15 minutos, 1 hora y 6 horas."""
        for fila in self:
            intentos = fila.intentos + 1
            espera = ESPERAS_MIN[min(intentos, len(ESPERAS_MIN)) - 1]
            fila.write({'intentos': intentos, 'ultimo_error': resultado['mensaje'] or False,
                        'proximo_intento': ahora + timedelta(minutes=espera)})
        _logger.warning('Meta: no se pudo enviar ahora (HTTP %s); se reintenta: %s',
                        resultado['status'], resultado['mensaje'])

    def _dcasa_anotar_rechazo(self, resultado, ahora):
        """Otro 4xx de un solo evento: se intenta otra vez y, al segundo rechazo, queda con error."""
        self.ensure_one()
        intentos = self.intentos + 1
        valores = {'intentos': intentos, 'ultimo_error': resultado['mensaje'] or False,
                   'proximo_intento': ahora + timedelta(minutes=ESPERAS_MIN[0])}
        if intentos >= INTENTOS_INVALIDO:
            valores.update(estado='error', proximo_intento=False, motivo=self.env._('Meta rechazó el evento'))
        self.write(valores)
        _logger.warning('Meta: rechazó el evento %s (HTTP %s): %s', self.event_id, resultado['status'],
                        resultado['mensaje'])

    # ------------------------------------------------------------------
    # Retención (cron diario)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_cron_retencion(self):
        """Borra el JSON de lo que ya no está pendiente a los 7 días, las filas a los 180 y los datos del navegador de
        los pedidos que nunca se pagaron a los 30 (valores técnicos, ajustables con dcasa_meta.dias_*)."""
        Evento = self.sudo()
        ahora = fields.Datetime.now()
        con_datos = Evento.search([
            ('estado', '!=', 'pendiente'), ('datos', '!=', False),
            ('create_date', '<', ahora - timedelta(days=dias(self.env, 'dias_datos', DIAS_DATOS)))])
        con_datos.write({'datos': False})
        viejas = Evento.search([('create_date', '<', ahora - timedelta(days=dias(self.env, 'dias_filas', DIAS_FILAS)))])
        borradas = len(viejas)
        viejas.unlink()
        pedidos = self.env['sale.order'].sudo()._dcasa_meta_limpiar_navegador_viejo(
            ahora - timedelta(days=dias(self.env, 'dias_navegador', DIAS_NAVEGADOR)))
        return len(con_datos), borradas, len(pedidos)

    # ------------------------------------------------------------------
    # Botón «Reintentar ahora» (lista de eventos)
    # ------------------------------------------------------------------

    def action_dcasa_meta_reintentar(self):
        """Vuelve a poner en la cola lo marcado con error (o pendiente en espera) y dispara el envío. Sin nada
        marcado, todo lo que está con error.

        Exige Gerencia o administrador en el servidor ANTES del sudo. No revive lo descartado (Meta ya no lo
        acepta), lo omitido (sin consentimiento), lo cancelado ni las pruebas.
        """
        if not es_gerencia(self.env):
            raise AccessError(self.env._('Solo Gerencia o un administrador reintenta los eventos de Meta.'))
        filas = self.sudo() if self else self.sudo().search([('estado', '=', 'error')])
        filas = filas.filtered(lambda f: f.estado in ('error', 'pendiente') and not f.es_prueba and f.datos)
        if filas:
            filas.write({'estado': 'pendiente', 'proximo_intento': False, 'intentos': 0, 'motivo': False})
            self._dcasa_programar_envio()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Eventos de Meta'),
                'message': self.env._('%s evento(s) vuelven a la cola; salen en unos minutos.', len(filas))
                if filas else self.env._('No hay nada para reintentar.'),
                'type': 'success' if filas else 'warning',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
