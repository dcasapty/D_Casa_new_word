"""Conversación con un cliente por un canal (WhatsApp, Telegram, Messenger, Instagram).

Identidad: ``(canal, id_externo)`` es único. El cliente es una ficha ``res.partner`` con el celular
como llave (ver ``res_partner.py``). Quién contesta lo dice ``estado``:

* ``bot``      — contesta el asistente (Juan);
* ``humano``   — una vendedora la tomó (o el asistente la pasó): el bot calla hasta que se la
                 devuelvan o venza ``pausada_hasta`` (sin fecha = hasta que la devuelvan);
* ``cerrada``  — terminada; si el cliente escribe de nuevo, se reabre con el asistente.

Odoo es la verdad y decide el seguimiento (quién y cuándo): ver ``_programar_seguimiento``.

Seguridad: los métodos que cambian algo con ``sudo()`` son privados (``_``) o exigen el grupo de
ventas; los botones (``action_*``) lo comprueban en el servidor, no solo en la vista.
"""
import logging
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, ConcurrencyError, UserError
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY

from . import celulares, transaccion
from . import horario as H
from .ajustes import CANALES, CANALES_CON_CELULAR
from .mensaje import CLAVE_SISTEMA, VENTANA_ADOPCION

_logger = logging.getLogger(__name__)

GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
ESTADOS = [('bot', 'Con el asistente'), ('humano', 'Con una vendedora'), ('cerrada', 'Cerrada')]
MAX_BURBUJAS = 200
OPORTUNIDAD_RECIENTE = timedelta(days=30)
ESPERA_CONFIRMACION_SEGUIMIENTO = timedelta(hours=24)
MAX_REINTENTOS_SEGUIMIENTO = 6
PAUSA_REINTENTO_SEGUIMIENTO = timedelta(minutes=15)
MAX_NOTA = 1000
MAX_NOTA_PARA_EL_BOT = 500
CANAL_BUS = 'dcasa_conversaciones/evento'
MOTIVOS_DE_BAJA = ('no_contactar', 'no contactar', 'baja', 'opt_out', 'opt-out', 'pidio_no', 'pidió no')


class DcasaConversacion(models.Model):
    _name = 'dcasa.conversacion'
    _description = 'Conversación con un cliente'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'ultima_actividad desc nulls last, id desc'

    name = fields.Char('Conversación', compute='_compute_name', store=True)
    canal = fields.Selection(CANALES, required=True, readonly=True, index=True)
    id_externo = fields.Char('Id en el canal', required=True, readonly=True, index=True,
                             help='Celular (WhatsApp, sin +), chat_id (Telegram) o PSID/IGSID (Meta).')
    partner_id = fields.Many2one('res.partner', 'Cliente', index=True, ondelete='restrict', tracking=True)
    celular = fields.Char('Celular', compute='_compute_celular')
    estado = fields.Selection(ESTADOS, default='bot', required=True, index=True, tracking=True)
    pausada_hasta = fields.Datetime(
        'El asistente calla hasta', tracking=True,
        help='Vacío con la conversación en manos de una vendedora = hasta que se la devuelvan al asistente.')
    asignada_a = fields.Many2one('res.users', 'Atiende', domain=[('share', '=', False)], tracking=True,
                                 index='btree_not_null')
    bot_atiende = fields.Boolean('Contesta el asistente', compute='_compute_bot_atiende')
    ultima_actividad = fields.Datetime('Última actividad', index=True)
    ultimo_mensaje_cliente = fields.Datetime('Último mensaje del cliente')
    ultimo_mensaje_texto = fields.Char('Último mensaje', readonly=True)
    ultimo_mensaje_autor = fields.Selection([('cliente', 'Cliente'), ('bot', 'Asistente'), ('vendedora', 'Vendedora')],
                                            readonly=True)
    inicio = fields.Datetime('Empezó', readonly=True, default=fields.Datetime.now)
    oportunidad_id = fields.Many2one('crm.lead', 'Oportunidad', copy=False, index='btree_not_null',
                                     ondelete='set null')
    mensaje_ids = fields.One2many('dcasa.mensaje', 'conversacion_id', string='Mensajes')
    mensajes_count = fields.Integer('Cantidad de mensajes', compute='_compute_contadores')
    por_enviar_count = fields.Integer('Por enviar', compute='_compute_contadores')
    chat_html = fields.Html('Chat', compute='_compute_chat_html', sanitize=False)
    etiqueta_ids = fields.Many2many('dcasa.conversacion.etiqueta', 'dcasa_conversacion_etiqueta_rel',
                                    'conversacion_id', 'etiqueta_id', string='Etiquetas')
    nota_para_el_bot = fields.Text(
        'Nota para el asistente', readonly=True,
        help='Lo que una vendedora le dejó dicho al devolverle la conversación (p. ej. «ya quedó la cita»). '
             'El asistente la lee en cada respuesta hasta que otra persona tome la conversación.')
    ultimo_cliente_msg_id = fields.Integer(
        'Último mensaje del cliente (id)', readonly=True, copy=False,
        help='Id del último mensaje del cliente: con él se sabe, sin contar nada, si hay algo sin leer.')
    borrador = fields.Text('Tu respuesta')
    borrador_adjunto_ids = fields.Many2many('ir.attachment', 'dcasa_conversacion_borrador_rel', 'conversacion_id',
                                            'adjunto_id', string='Adjuntar')

    # --- Seguimiento (Odoo decide quién y cuándo; el Worker redacta y envía) -------------------------
    seguimientos_enviados = fields.Integer('Seguimientos enviados', readonly=True)
    ultimo_seguimiento_en = fields.Datetime('Último seguimiento', readonly=True)
    seguimiento_proximo = fields.Datetime('Próximo seguimiento', readonly=True, index='btree_not_null')
    seguimiento_pedido_en = fields.Datetime('Seguimiento pedido', readonly=True,
                                            help='Cuándo se le pidió al Worker; se limpia al confirmar.')
    seguimiento_numero_pedido = fields.Integer(readonly=True)
    seguimiento_reintentos = fields.Integer(readonly=True)
    estado_pendiente_de_avisar = fields.Boolean(
        readonly=True, help='El cambio de estado aún no se le avisó al Worker (se reintenta solo).')

    _conversacion_unica = models.Constraint(
        'UNIQUE(canal, id_externo)', 'Ya existe una conversación con esa persona por ese canal.')
    # La lista de la bandeja es «las más recientes primero, de 30 en 30»: con estos índices es una lectura de
    # índice y no ordenar toda la tabla (probado con 5.000 conversaciones).
    _lista_idx = models.Index('(ultima_actividad DESC NULLS LAST, id DESC)')
    _estado_lista_idx = models.Index('(estado, ultima_actividad DESC NULLS LAST)')

    # ------------------------------------------------------------------
    # Cómputos
    # ------------------------------------------------------------------

    @api.depends('partner_id.name', 'id_externo', 'canal')
    def _compute_name(self):
        etiquetas = dict(CANALES)
        for conv in self:
            quien = conv.partner_id.name or conv.id_externo or ''
            conv.name = f'{quien} · {etiquetas.get(conv.canal, conv.canal or "")}'

    @api.depends('partner_id', 'id_externo', 'canal')
    def _compute_celular(self):
        for conv in self:
            tipo, valor = self.env['res.partner']._dcasa_conv_celular_de_ficha(conv.partner_id) \
                if conv.partner_id else (None, '')
            if not tipo and conv.canal in CANALES_CON_CELULAR:
                tipo, valor = celulares.interpretar(conv.id_externo)
            conv.celular = celulares.para_mostrar(tipo, valor) if tipo else False

    @api.depends('estado', 'pausada_hasta')
    def _compute_bot_atiende(self):
        ahora = fields.Datetime.now()
        for conv in self:
            conv.bot_atiende = conv._controla_bot(ahora)

    @api.depends('mensaje_ids', 'mensaje_ids.estado_envio')
    def _compute_contadores(self):
        datos = {}
        for conv, estado, n in self.env['dcasa.mensaje']._read_group(
                [('conversacion_id', 'in', self.ids), ('tipo', '=', 'mensaje')],
                ['conversacion_id', 'estado_envio'], ['__count']):
            datos.setdefault(conv.id, {})[estado] = n
        for conv in self:
            cuenta = datos.get(conv.id, {})
            conv.mensajes_count = sum(cuenta.values())
            conv.por_enviar_count = cuenta.get('por_enviar', 0) + cuenta.get('fallido', 0)

    @api.depends('mensaje_ids.texto', 'mensaje_ids.estado_envio', 'mensaje_ids.adjunto_ids', 'partner_id.name')
    def _compute_chat_html(self):
        horario = self.env['dcasa.juan.ajustes'].obtener().horario()
        for conv in self:
            mensajes = conv.mensaje_ids.sorted(lambda m: (m.ts, m.id))[-MAX_BURBUJAS:]
            if not mensajes:
                conv.chat_html = Markup('<div class="o_dcasa_chat o_dcasa_chat_vacio">%s</div>') % escape(
                    self.env._('Todavía no hay mensajes.'))
                continue
            burbujas = Markup('').join(m._burbuja_html(horario) for m in mensajes)
            conv.chat_html = Markup('<div class="o_dcasa_chat">%s</div>') % burbujas

    # ------------------------------------------------------------------
    # Quién contesta
    # ------------------------------------------------------------------

    def _controla_bot(self, ahora=None):
        """¿Contesta el asistente ahora? Con la pausa vencida, también (el bot no se queda mudo para siempre)."""
        self.ensure_one()
        ahora = ahora or fields.Datetime.now()
        if self.estado == 'bot':
            return True
        return self.estado == 'humano' and bool(self.pausada_hasta) and self.pausada_hasta <= ahora

    def _normalizar_pausa(self):
        """Si venció la pausa, la conversación vuelve al asistente (y su seguimiento se programa desde ahora)."""
        ahora = fields.Datetime.now()
        for conv in self.sudo().filtered(lambda c: c.estado == 'humano' and c.pausada_hasta
                                         and c.pausada_hasta <= ahora):
            conv.write({'estado': 'bot', 'pausada_hasta': False})
            conv._programar_seguimiento(desde=ahora)

    def _bot_activo(self, ajustes=None):
        """El asistente puede contestar: está encendido (global y canal) y la conversación es suya."""
        self.ensure_one()
        ajustes = ajustes or self.env['dcasa.juan.ajustes'].obtener()
        return bool(ajustes.canal_activo(self.canal) and self.estado != 'cerrada' and self._controla_bot())

    def _estado_para_worker(self, ajustes=None):
        self.ensure_one()
        ajustes = ajustes or self.env['dcasa.juan.ajustes'].obtener()
        ahora = fields.Datetime.now()
        return {
            'bot_activo': self._bot_activo(ajustes),
            'estado': 'bot' if self.estado == 'humano' and self._controla_bot(ahora) else self.estado,
            'pausada_hasta': H.a_iso(self.pausada_hasta) if self.estado == 'humano' else None,
            'dentro_de_horario': H.dentro_de_horario(ahora, ajustes.horario()),
            'nota_para_el_bot': (self.nota_para_el_bot or None) if self._bot_activo(ajustes) else None,
        }

    @api.model
    def _estado_sin_conversacion(self, canal, ajustes=None):
        ajustes = ajustes or self.env['dcasa.juan.ajustes'].obtener()
        ahora = fields.Datetime.now()
        return {'bot_activo': bool(ajustes.canal_activo(canal)), 'estado': 'bot', 'pausada_hasta': None,
                'dentro_de_horario': H.dentro_de_horario(ahora, ajustes.horario()), 'nota_para_el_bot': None}

    # ------------------------------------------------------------------
    # Permisos
    # ------------------------------------------------------------------

    @api.model
    def _exigir_vendedora(self):
        """Los botones se comprueban en el servidor: por RPC cualquiera podría llamarlos."""
        if not self.env.su and not self.env.user.has_group(GRUPO_VENDEDORA):
            raise AccessError(self.env._('Solo el equipo de ventas puede atender conversaciones.'))

    def write(self, vals):
        if not self.env.su and {'canal', 'id_externo'} & set(vals):
            raise AccessError(self.env._('El canal y la persona de una conversación no se cambian.'))
        resultado = super().write(vals)
        if 'oportunidad_id' in vals:
            # La intención de compra es lo que habilita el seguimiento: al ligar o soltar la oportunidad se vuelve a calcular.
            self._programar_seguimiento()
        return resultado

    def unlink(self):
        """Borrar una conversación (derecho de borrado, Ley 81) borra sus mensajes y adjuntos por el ORM."""
        self.check_access('unlink')   # primero el permiso; los mensajes se borran con sudo
        self.sudo().mensaje_ids.unlink()
        return super().unlink()

    # ------------------------------------------------------------------
    # Entrada de mensajes (la usa la API; privado: escribe con sudo)
    # ------------------------------------------------------------------

    @api.model
    def _bloquear(self, canal, id_externo):
        """Serializa lo concurrente de UNA misma conversación (dos mensajes a la vez no la duplican)."""
        self.env.cr.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',
                            [f'dcasa_conversacion:{canal}:{id_externo}'])

    @api.model
    def _obtener_o_crear(self, canal, id_externo, nombre=None, celular=None, ts=None):
        """La conversación (creándola con su ficha de cliente si hace falta). Devuelve ``(conv, creada)``."""
        conv = self.sudo().search([('canal', '=', canal), ('id_externo', '=', id_externo)], limit=1)
        if conv:
            conv._actualizar_ficha(nombre, celular)
            return conv, False
        ficha = self.env['res.partner']._dcasa_conv_ficha(canal, id_externo, nombre, celular)
        conv = self.sudo().with_context(mail_create_nolog=True, mail_create_nosubscribe=True).create({
            'canal': canal, 'id_externo': id_externo, 'partner_id': ficha.id,
            'estado': 'bot', 'inicio': ts or fields.Datetime.now(),
        })
        return conv, True

    def _actualizar_ficha(self, nombre=None, celular=None):
        """Con datos nuevos del canal: el nombre real reemplaza al provisional; un celular nuevo se enlaza."""
        self.ensure_one()
        partner = self.partner_id.sudo()
        if not partner:
            return
        Partner = self.env['res.partner']
        provisional = Partner._dcasa_conv_nombre_provisional(self.canal, self.id_externo)
        if nombre and partner.name in (provisional, Partner._dcasa_conv_nombre_provisional(
                self.canal, self.id_externo, celular)):
            partner.write({'name': nombre.strip()[:200]})
        tipo, valor = celulares.interpretar(celular or '')
        if tipo and not partner.phone and self.canal not in CANALES_CON_CELULAR:
            otra = Partner._dcasa_conv_buscar(celular)
            if otra and otra != partner:
                self.write({'partner_id': otra.id})
            elif not otra:
                partner.write({'phone': celulares.para_mostrar(tipo, valor)})

    @api.model
    def _registrar_mensaje(self, datos):
        """Registra un mensaje (idempotente por ``id_mensaje``). Devuelve ``(conversacion, mensaje, creado)``.

        ``datos``: ``canal, id_externo, id_mensaje, direccion, autor, ts`` y, opcionales, ``nombre,
        celular, texto, adjuntos`` (ya validados por la API).
        """
        canal, id_externo = datos['canal'], datos['id_externo']
        self._bloquear(canal, id_externo)
        conv, _creada = self.sudo()._obtener_o_crear(canal, id_externo, datos.get('nombre'), datos.get('celular'),
                                              datos.get('ts'))
        conv._normalizar_pausa()
        Mensaje = self.env['dcasa.mensaje'].sudo()
        propio = conv._adoptar_mensaje_de_odoo(datos)
        if propio:
            return conv, propio, False
        mensaje, creado = Mensaje._crear_si_no_existe({
            'conversacion_id': conv.id, 'id_mensaje': datos['id_mensaje'], 'direccion': datos['direccion'],
            'autor': datos['autor'], 'texto': datos.get('texto') or False, 'ts': datos['ts'],
            'estado_envio': 'recibido' if datos['direccion'] == 'entrante' else 'enviado',
        })
        if not creado:
            # Repetición: si antes fallaron adjuntos y ahora vienen otra vez, se vuelven a intentar.
            if datos.get('adjuntos') and mensaje.adjuntos_fallidos:
                mensaje.adjunto_ids.sudo().unlink()
                mensaje._adjuntar(datos['adjuntos'])
            return conv, mensaje, False
        if datos.get('adjuntos'):
            mensaje._adjuntar(datos['adjuntos'])
        conv._despues_de_mensaje(mensaje)
        mensaje._publicar_en_chatter()
        conv._notificar_panel('mensaje', mensaje)
        return conv, mensaje, True

    def _adoptar_mensaje_de_odoo(self, datos):
        """Lo que una vendedora escribió en Odoo y el Worker devuelve como eco se queda como UN mensaje."""
        self.ensure_one()
        if datos['direccion'] != 'saliente' or datos['autor'] != 'vendedora' or not datos.get('texto'):
            return self.env['dcasa.mensaje']
        Mensaje = self.env['dcasa.mensaje'].with_context(**{CLAVE_SISTEMA: True})
        if Mensaje.search_count([('conversacion_id', '=', self.id), ('id_mensaje', '=', datos['id_mensaje'])]):
            return self.env['dcasa.mensaje']   # ya está por su id: el camino normal lo trata como repetición
        propio = Mensaje.search([
            ('conversacion_id', '=', self.id), ('origen', '=', 'odoo'), ('id_mensaje', '=like', 'odoo-%'),
            ('texto', '=', datos['texto']),
            ('create_date', '>=', fields.Datetime.now() - VENTANA_ADOPCION),
        ], order='id desc', limit=1)
        if propio:
            propio.write({'id_mensaje': datos['id_mensaje'], 'estado_envio': 'enviado', 'error_envio': False})
        return propio

    def _despues_de_mensaje(self, mensaje):
        """Lo que un mensaje nuevo cambia en la conversación: actividad, quién contesta y seguimiento."""
        self.ensure_one()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        ahora = fields.Datetime.now()
        valores = {
            'ultima_actividad': max(self.ultima_actividad or mensaje.ts, mensaje.ts),
            'ultimo_mensaje_texto': (mensaje.texto or self.env._('(adjunto)'))[:140],
            'ultimo_mensaje_autor': mensaje.autor,
        }
        if mensaje.autor == 'cliente':
            valores.update({
                'ultimo_mensaje_cliente': mensaje.ts,
                'seguimientos_enviados': 0, 'ultimo_seguimiento_en': False, 'seguimiento_proximo': False,
                'seguimiento_pedido_en': False, 'seguimiento_numero_pedido': 0, 'seguimiento_reintentos': 0,
            })
            valores['ultimo_cliente_msg_id'] = max(self.ultimo_cliente_msg_id, mensaje.id)
            if self.estado == 'cerrada':
                valores['estado'] = 'bot'
                self._aviso(self.env._('La conversación estaba cerrada y se reabrió porque el cliente escribió.'))
            if H.pide_no_contactar(mensaje.texto):
                self._marcar_no_contactar(self.env._('El cliente pidió que no lo contactemos.'))
        elif mensaje.autor == 'vendedora':
            valores['seguimiento_proximo'] = False
            valores.update(self._valores_de_pausa(ajustes, ahora, cambia_a_humano=self.estado != 'humano'))
        self.write(valores)
        if mensaje.autor == 'bot':
            self._programar_seguimiento()

    def _valores_de_pausa(self, ajustes, ahora, cambia_a_humano):
        """Estado y pausa cuando una vendedora escribe: toma la conversación o renueva la pausa."""
        minutos = ajustes.pausa_por_defecto_minutos
        if cambia_a_humano:
            return {'estado': 'humano', 'pausada_hasta': ahora + timedelta(minutes=minutos) if minutos else False}
        if not self.pausada_hasta:
            return {}   # «hasta que la devuelvan»: se queda así
        return {'pausada_hasta': max(self.pausada_hasta, ahora + timedelta(minutes=minutos)) if minutos else False}

    def _marcar_no_contactar(self, motivo):
        self.ensure_one()
        partner = self.partner_id.sudo()
        if partner and not partner.dcasa_no_contactar:
            partner.write({'dcasa_no_contactar': True})
            self.sudo().message_post(body=escape(motivo), subtype_xmlid='mail.mt_note')
        self.sudo().write({'seguimiento_proximo': False})

    # ------------------------------------------------------------------
    # Seguimiento: Odoo decide quién y cuándo
    # ------------------------------------------------------------------

    def _ya_compro(self):
        """¿Ya es cliente? Tiene alguna factura pagada, de antes o de después de empezar la conversación."""
        self.ensure_one()
        return bool(self.partner_id) and self.partner_id._dcasa_conv_ya_compro()

    def _con_intencion_de_compra(self):
        """¿Mostró intención de compra? Hay una oportunidad de CRM viva (ni ganada ni perdida) ligada a la conversación.

        El asistente la crea cuando el cliente muestra interés concreto (un mueble puntual, un presupuesto, quiere ir a
        la tienda) y una vendedora puede crearla con un botón. Sin oportunidad, el seguimiento no corre.
        """
        self.ensure_one()
        oportunidad = self.oportunidad_id.sudo()
        return bool(oportunidad and oportunidad.active and oportunidad.won_status == 'pending')

    def _motivo_sin_seguimiento(self, ahora=None, ajustes=None):
        """Por qué NO toca seguimiento ahora (texto corto), o ``None`` si toca. Es la regla 10 del contrato."""
        self.ensure_one()
        ahora = ahora or fields.Datetime.now()
        ajustes = ajustes or self.env['dcasa.juan.ajustes'].obtener()
        if not ajustes.canal_activo(self.canal):
            return 'el asistente está apagado'
        if ajustes.seguimiento_maximo <= 0:
            return 'el seguimiento está apagado'
        if self.estado == 'cerrada':
            return 'la conversación está cerrada'
        if not self._controla_bot(ahora):
            return 'la atiende una persona'
        if self.partner_id.dcasa_no_contactar:
            return 'pidió que no lo contacten'
        if not self.ultimo_mensaje_cliente:
            return 'la persona nunca escribió'
        if self.ultimo_mensaje_autor != 'bot':
            return 'el último mensaje no es del asistente'
        if self.seguimientos_enviados >= ajustes.seguimiento_maximo:
            return 'ya recibió todos los seguimientos'
        if self._ya_compro():
            return 'ya es cliente: ya compró'
        if not self._con_intencion_de_compra():
            return 'no mostró intención de compra'
        return None

    def _programar_seguimiento(self, desde=None):
        """Calcula y guarda ``seguimiento_proximo`` según las reglas de la dueña (ver ``horario.py``)."""
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        horario, regla = ajustes.horario(), ajustes.regla_seguimiento()
        ahora = fields.Datetime.now()
        for conv in self.sudo():
            proximo = False
            if conv.seguimiento_pedido_en:
                proximo = False   # ya hay uno en camino: el aviso del Worker lo cierra
            elif conv._motivo_sin_seguimiento(ahora, ajustes) is None:
                base = max(conv.ultima_actividad, desde) if desde and conv.ultima_actividad else (
                    conv.ultima_actividad or desde)
                proximo = H.proximo_seguimiento(
                    conv.seguimientos_enviados, base, conv.ultimo_seguimiento_en, regla, horario) or False
            conv.write({'seguimiento_proximo': proximo})

    @api.model
    def _cron_seguimientos(self):
        """Cada 15 minutos: a quien le toca seguimiento, se lo pide al Worker (que redacta y envía)."""
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        if not self.env['dcasa.juan.cliente'].configurado() or not ajustes.bot_activo_global:
            return 0
        ahora = fields.Datetime.now()
        pendientes = self.sudo().search([
            ('seguimiento_proximo', '!=', False), ('seguimiento_proximo', '<=', ahora),
            ('estado', '!=', 'cerrada')], order='seguimiento_proximo', limit=50)
        pedidos = 0
        for conv in pendientes:
            try:
                # Sin savepoint: cada seguimiento se CONFIRMA en la base antes de llamar al Worker (ver abajo).
                pedidos += 1 if conv._intentar_seguimiento(ahora, ajustes) else 0
            except Exception:   # noqa: BLE001 — un fallo no frena a los demás
                transaccion.deshacer(self.env)
                _logger.exception('Juan: falló el seguimiento de la conversación %s', conv.id)
        return pedidos

    def _intentar_seguimiento(self, ahora, ajustes):
        """Revisa TODO otra vez (el estado pudo cambiar desde que se programó) y, si toca, lo pide."""
        self.ensure_one()
        motivo = self._motivo_sin_seguimiento(ahora, ajustes)
        if motivo:
            self.write({'seguimiento_proximo': False})
            return False
        horario = ajustes.horario()
        if ajustes.seguimiento_solo_horario_laboral and not H.dentro_de_horario(ahora, horario):
            self.write({'seguimiento_proximo': H.siguiente_horario_laboral(ahora, horario) or False})
            return False
        numero = self.seguimientos_enviados + 1
        interes, ultimo_mensaje = self._interes(), H.a_iso(self.ultima_actividad)
        # El Worker contesta DESPUÉS de haber llamado a ``/seguimiento/hecho`` (y a ``/mensaje`` con el texto que
        # envió), que escriben esta misma fila. Si esta transacción llegara a escribir después con su «foto» vieja,
        # Postgres la rechazaría («could not serialize access») o, peor, pisaría lo que el Worker ya confirmó. Por eso
        # el pedido se anota y se CONFIRMA (commit) antes de llamar, y al volver se lee todo de nuevo.
        self.write({'seguimiento_pedido_en': ahora, 'seguimiento_numero_pedido': numero, 'seguimiento_proximo': False})
        transaccion.confirmar(self.env)
        respuesta = self.env['dcasa.juan.cliente'].pedir_seguimiento(
            self.id, self.canal, self.id_externo, numero, interes=interes, ultimo_mensaje_ts=ultimo_mensaje)
        # Mientras esperaba, esta transacción volvió a abrirse (al leer la dirección del Worker) con una «foto» ANTERIOR
        # a lo que el Worker confirmó: se cierra y se lee todo de nuevo, o se vería (y se pisaría) el estado viejo.
        transaccion.confirmar(self.env)
        self.env.invalidate_all()
        if self.seguimientos_enviados >= numero:
            return True   # el Worker ya lo confirmó (enviado o descartado) mientras contestaba
        if respuesta.get('ok') and respuesta.get('resultado') == 'pospuesto':
            # El Worker no lo envió ahora (fuera de horario, asistente apagado): sin ``hecho``; se reintenta luego.
            siguiente = H.siguiente_horario_laboral(ahora, ajustes.horario()) \
                if ajustes.seguimiento_solo_horario_laboral else None
            self.write({'seguimiento_pedido_en': False, 'seguimiento_numero_pedido': 0,
                        'seguimiento_proximo': max(siguiente or ahora, ahora + PAUSA_REINTENTO_SEGUIMIENTO)})
            return False
        if respuesta.get('ok'):
            self.write({'seguimiento_reintentos': 0})   # sigue «pedido»: el aviso del Worker lo cierra
            return True
        # El Worker no lo aceptó: ya no hay nada pedido.
        self.write({'seguimiento_pedido_en': False, 'seguimiento_numero_pedido': 0})
        reintentos = self.seguimiento_reintentos + 1
        if reintentos >= MAX_REINTENTOS_SEGUIMIENTO or respuesta.get('estado_http') in (400, 404, 422):
            self.write({'seguimiento_proximo': False, 'seguimiento_reintentos': reintentos})
            self.sudo().message_post(body=escape(self.env._(
                'No pude pedirle el seguimiento n.º %(n)s al Worker: %(e)s', n=numero,
                e=respuesta.get('error') or '')), subtype_xmlid='mail.mt_note')
        else:
            self.write({'seguimiento_reintentos': reintentos,
                        'seguimiento_proximo': ahora + PAUSA_REINTENTO_SEGUIMIENTO * reintentos})
        return False

    def _interes(self):
        self.ensure_one()
        if self.oportunidad_id:
            nombre = self.oportunidad_id.name or ''
            prefijo = f'{dict(CANALES).get(self.canal, self.canal)}: '   # «WhatsApp (QR): cama queen» → «cama queen»
            return (nombre[len(prefijo):] if nombre.startswith(prefijo) else nombre)[:200]
        ultimo = self.env['dcasa.mensaje'].search([('conversacion_id', '=', self.id), ('autor', '=', 'cliente')],
                                                  order='ts desc, id desc', limit=1)
        return (ultimo.texto or '')[:200]

    def _seguimiento_hecho(self, numero, resultado, motivo=None):
        """El Worker confirmó que envió (o descartó) el seguimiento ``numero``. Idempotente."""
        self.ensure_one()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        ahora = fields.Datetime.now()
        motivo = (motivo or '').strip()[:200]
        if resultado == 'enviado':
            if numero <= self.seguimientos_enviados:
                return {'repetido': True}
            self.write({'seguimientos_enviados': numero, 'ultimo_seguimiento_en': ahora,
                        'seguimiento_pedido_en': False, 'seguimiento_numero_pedido': 0,
                        'seguimiento_reintentos': 0})
            texto = self.env._('Seguimiento n.º %s enviado.', numero)
            self._aviso(texto)
        else:
            # Descartado: el Worker decidió no enviarlo. Se cierra el ciclo (nunca más insistencia).
            if self.seguimientos_enviados >= ajustes.seguimiento_maximo and not self.seguimiento_pedido_en:
                return {'repetido': True}
            self.write({'seguimientos_enviados': max(ajustes.seguimiento_maximo, numero), 'seguimiento_proximo': False,
                        'seguimiento_pedido_en': False, 'seguimiento_numero_pedido': 0})
            texto = self.env._('Seguimiento n.º %s descartado por el Worker.', numero)
            if any(clave in motivo.lower() for clave in MOTIVOS_DE_BAJA):
                self._marcar_no_contactar(
                    self.env._('El Worker descartó el seguimiento: la persona pidió no ser contactada.'))
        if motivo:
            texto = f'{texto} ({motivo})'
        self.sudo().message_post(body=escape(texto), subtype_xmlid='mail.mt_note')
        self._programar_seguimiento()
        return {'repetido': False}

    @api.model
    def _cron_mantenimiento(self):
        """Cada 5 minutos: reintenta envíos y avisos, devuelve las pausas vencidas y cierra seguimientos sin aviso."""
        self.env['dcasa.mensaje']._cron_reintentar_envios()
        vencidas = self.sudo().search([('estado', '=', 'humano'), ('pausada_hasta', '!=', False),
                                       ('pausada_hasta', '<=', fields.Datetime.now())])
        for conv in vencidas:
            conv._normalizar_pausa()
            conv.estado_pendiente_de_avisar = True
        self._reintentar_avisos_de_estado()
        self._cerrar_seguimientos_sin_aviso()

    @api.model
    def _reintentar_avisos_de_estado(self):
        if not self.env['dcasa.juan.cliente'].configurado():
            return
        for conv in self.sudo().search([('estado_pendiente_de_avisar', '=', True)], limit=50):
            conv._avisar_estado_al_worker()

    @api.model
    def _cerrar_seguimientos_sin_aviso(self):
        """Un seguimiento pedido hace > 24 h sin aviso del Worker: si salió un mensaje del asistente
        después de pedirlo se da por enviado; si no, se cierra el ciclo (nunca se insiste a ciegas)."""
        limite = fields.Datetime.now() - ESPERA_CONFIRMACION_SEGUIMIENTO
        for conv in self.sudo().search([
                ('seguimiento_pedido_en', '!=', False), ('seguimiento_pedido_en', '<=', limite)]):
            salio = self.env['dcasa.mensaje'].search_count([
                ('conversacion_id', '=', conv.id), ('autor', '=', 'bot'), ('ts', '>=', conv.seguimiento_pedido_en)])
            conv._seguimiento_hecho(conv.seguimiento_numero_pedido or 1, 'enviado' if salio else 'descartado',
                                    None if salio else 'sin confirmación del Worker')

    # ------------------------------------------------------------------
    # Avisar al Worker del cambio de estado (tomar / devolver)
    # ------------------------------------------------------------------

    def _avisar_estado_al_worker(self):
        """``POST /odoo/estado``. Si falla queda pendiente y se reintenta; el estado de Odoo manda de todos modos
        porque el Worker pregunta ``GET /estado`` justo antes de enviar."""
        for conv in self.sudo():
            if not self.env['dcasa.juan.cliente'].configurado():
                conv.estado_pendiente_de_avisar = False
                continue
            humano = conv.estado == 'humano' and not conv._controla_bot()
            respuesta = self.env['dcasa.juan.cliente'].cambiar_estado(
                conv.canal, conv.id_externo, 'humano' if humano else 'bot',
                pausada_hasta=H.a_iso(conv.pausada_hasta) if humano else None,
                nota=None if humano else conv.nota_para_el_bot)
            conv.estado_pendiente_de_avisar = not respuesta.get('ok')

    # ------------------------------------------------------------------
    # Botones de la bandeja
    # ------------------------------------------------------------------

    def _poner_en_humano(self, usuario=None, minutos=None):
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        minutos = ajustes.pausa_por_defecto_minutos if minutos is None else minutos
        ahora = fields.Datetime.now()
        for conv in self.sudo():
            valores = {'estado': 'humano', 'pausada_hasta': ahora + timedelta(minutes=minutos) if minutos else False,
                       'seguimiento_proximo': False, 'nota_para_el_bot': False}
            if usuario:
                valores['asignada_a'] = usuario.id
            conv.write(valores)

    def action_atender(self):
        """«Atender»: el asistente calla, la conversación pasa a la vendedora y el Worker se entera."""
        self._exigir_vendedora()
        self.check_access('write')
        self._tomar(self.env.user)
        return True

    def action_devolver_al_bot(self):
        """«Devolver al asistente»: vuelve a contestar el bot; su seguimiento cuenta desde ahora."""
        self._exigir_vendedora()
        self.check_access('write')
        self._devolver(self.env.user)
        return True

    def action_cerrar(self):
        self._exigir_vendedora()
        self.check_access('write')
        self._cerrar(self.env.user)
        return True

    # ------------------------------------------------------------------
    # Tomar, devolver, cerrar: UNA sola ruta para los botones y para la API de la pantalla
    # ------------------------------------------------------------------

    def _tomar(self, usuario, minutos=None):
        """Una persona toma la conversación: el asistente calla (por ``minutos`` o lo que digan los ajustes)."""
        horario = self.env['dcasa.juan.ajustes'].obtener().horario()
        self._poner_en_humano(usuario=usuario, minutos=minutos)
        for conv in self.sudo():
            if conv.pausada_hasta:
                texto = self.env._('%(quien)s tomó la conversación. El asistente calla hasta %(hasta)s.',
                                   quien=usuario.name, hasta=H.texto_fecha_hora(conv.pausada_hasta, horario))
            else:
                texto = self.env._('%s tomó la conversación. El asistente calla hasta que se la devuelvan.',
                                   usuario.name)
            conv._aviso(texto)
            conv._notificar_panel('estado')
        self._avisar_estado_al_worker()

    def _devolver(self, usuario, nota=None):
        """Vuelve a contestar el asistente; la nota (opcional) se la lee en cada respuesta."""
        nota = ' '.join(str(nota or '').split())[:MAX_NOTA_PARA_EL_BOT] or False
        ahora = fields.Datetime.now()
        for conv in self.sudo():
            conv.write({'estado': 'bot', 'pausada_hasta': False, 'nota_para_el_bot': nota})
            conv._programar_seguimiento(desde=ahora)
            texto = self.env._('%s devolvió la conversación al asistente.', usuario.name)
            if nota:
                texto = f'{texto} ' + self.env._('Nota para el asistente: %s', nota)
            conv._aviso(texto)
            conv._notificar_panel('estado')
        self._avisar_estado_al_worker()

    def _cerrar(self, usuario):
        for conv in self.sudo():
            conv.write({'estado': 'cerrada', 'pausada_hasta': False, 'seguimiento_proximo': False,
                        'nota_para_el_bot': False})
            conv._aviso(self.env._('%s cerró la conversación.', usuario.name))
            conv._notificar_panel('estado')

    # ------------------------------------------------------------------
    # Avisos en el hilo y en las pantallas abiertas
    # ------------------------------------------------------------------

    def _aviso(self, texto):
        """Una línea del sistema dentro del hilo («Ana tomó la conversación»). No sale por el canal."""
        self.ensure_one()
        return self.env['dcasa.mensaje']._crear_interno(self.sudo(), 'aviso', texto)

    def _usuarios_del_panel(self):
        grupo = self.env.ref(GRUPO_VENDEDORA)
        # all_group_ids: la gerencia también es de ventas por herencia de grupos, aunque no lo tenga marcado.
        return self.env['res.users'].sudo().search([('all_group_ids', 'in', grupo.ids), ('share', '=', False)])

    def _notificar_panel(self, evento, mensaje=None):
        """Avisa por el bus de Odoo a las pantallas abiertas que algo cambió (mensaje nuevo, estado, etiquetas…).

        Viaja SOLO ids y estado, nunca el texto: el bus guarda lo que se envía y una pantalla pide el detalle
        con sus permisos. Un fallo aquí jamás tumba lo que se estaba haciendo.
        """
        for conv in self.sudo():
            try:
                with self.env.cr.savepoint():
                    carga = {
                        'evento': evento, 'conversacion_id': conv.id, 'estado': conv.estado,
                        'asignada_a': conv.asignada_a.id or None, 'ultima_actividad': H.a_iso(conv.ultima_actividad),
                        'mensaje_id': mensaje.id if mensaje else None,
                        'autor': mensaje.autor if mensaje else None,
                    }
                    for usuario in conv._usuarios_del_panel():
                        usuario._bus_send(CANAL_BUS, carga)
            except (ConcurrencyError, *PG_CONCURRENCY_EXCEPTIONS_TO_RETRY):
                # No es del aviso: al entrar al savepoint se escriben las escrituras pendientes de la petición, y si
                # chocaron con otra transacción hay que repetir TODA la petición (Odoo lo hace si el error sube).
                raise
            except Exception:   # noqa: BLE001 — avisar a las pantallas es un extra
                _logger.exception('Juan: no se pudo avisar a las pantallas (conversación %s)', conv.id)

    def _nombre_de_pila(self):
        """El primer nombre del cliente, o vacío si solo tenemos el provisional («WhatsApp 6123-4567»)."""
        self.ensure_one()
        partner = self.partner_id.sudo()
        nombre = (partner.name or '').strip()
        Partner = self.env['res.partner']
        if not nombre or nombre in (
                Partner._dcasa_conv_nombre_provisional(self.canal, self.id_externo),
                Partner._dcasa_conv_nombre_provisional(self.canal, self.id_externo, partner.phone)):
            return ''
        return nombre.split()[0]

    def action_enviar(self):
        """Escribir desde Odoo: el mensaje sale por el Worker; si no responde, queda «por enviar» y se reintenta."""
        self._exigir_vendedora()
        self.check_access('write')
        self.ensure_one()
        texto = (self.borrador or '').strip()
        adjuntos = self.borrador_adjunto_ids
        if not texto and not adjuntos:
            raise UserError(self.env._('Escribe algo o adjunta un archivo antes de enviar.'))
        mensaje = self._crear_mensaje_de_odoo(texto, adjuntos)
        self.sudo().write({'borrador': False, 'borrador_adjunto_ids': [(5, 0, 0)]})
        mensaje._enviar()
        if mensaje.exists() and mensaje.estado_envio != 'enviado':
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'title': self.env._('Quedó por enviar'),
                'message': self.env._('El Worker no respondió. Tu mensaje no se pierde: se reintenta solo.'),
                'type': 'warning', 'sticky': False}}
        return True

    def _crear_mensaje_de_odoo(self, texto, adjuntos=None, usuario=None):
        """Registra lo que una vendedora escribe en Odoo («por enviar») y toma la conversación."""
        self.ensure_one()
        usuario = usuario or self.env.user
        conv = self.sudo()
        ahora = fields.Datetime.now()
        mensaje, _creado = self.env['dcasa.mensaje']._crear_si_no_existe({
            'conversacion_id': conv.id, 'id_mensaje': self.env['dcasa.mensaje']._id_local(), 'direccion': 'saliente',
            'autor': 'vendedora', 'texto': texto or False, 'ts': ahora, 'origen': 'odoo', 'usuario_id': usuario.id,
            'estado_envio': 'por_enviar'})
        if adjuntos:
            mensaje.with_context(**{CLAVE_SISTEMA: True}).write({'adjunto_ids': [(4, a.id) for a in adjuntos]})
            adjuntos.sudo().write({'res_model': 'dcasa.mensaje', 'res_id': mensaje.id})
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        la_tomo = conv.estado != 'humano'
        conv.write({
            'ultima_actividad': ahora, 'ultimo_mensaje_texto': (texto or self.env._('(adjunto)'))[:140],
            'ultimo_mensaje_autor': 'vendedora', 'seguimiento_proximo': False, 'asignada_a': usuario.id,
            'nota_para_el_bot': False,
            **conv._valores_de_pausa(ajustes, ahora, cambia_a_humano=la_tomo)})
        mensaje._publicar_en_chatter()
        if la_tomo:
            conv._aviso(self.env._('%s tomó la conversación al escribir. El asistente calla.', usuario.name))
        conv._notificar_panel('mensaje', mensaje)
        return mensaje

    def action_reintentar_envios(self):
        self._exigir_vendedora()
        self.mensaje_ids.filtered(lambda m: m.estado_envio in ('por_enviar', 'fallido') and m.origen == 'odoo') \
            .action_reintentar()
        return True

    def action_crear_oportunidad(self):
        self._exigir_vendedora()
        self.check_access('write')
        self.ensure_one()
        lead, nueva = self._oportunidad(resumen=self.env._('Creada por %s desde la bandeja.', self.env.user.name),
                                        interes=None, usuario=self.env.user)
        return {'type': 'ir.actions.act_window', 'res_model': 'crm.lead', 'res_id': lead.id, 'view_mode': 'form',
                'name': lead.name, 'target': 'current'}

    def action_ver_oportunidad(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'crm.lead', 'res_id': self.oportunidad_id.id,
                'view_mode': 'form', 'name': self.oportunidad_id.name}

    # ------------------------------------------------------------------
    # Oportunidad y notas (las usan los botones y las herramientas del asistente)
    # ------------------------------------------------------------------

    def _oportunidad(self, resumen, interes=None, presupuesto=None, usuario=None):
        """La oportunidad de CRM de esta conversación: la abierta si ya hay una reciente; si no, una nueva.

        Devuelve ``(lead, nueva)``. No duplica: una oportunidad abierta de los últimos 30 días del
        mismo cliente se reutiliza (el resumen nuevo queda como nota en ella).
        """
        self.ensure_one()
        Lead = self.env['crm.lead'].sudo()
        ahora = fields.Datetime.now()
        abierta = self.oportunidad_id.sudo() if (
            self.oportunidad_id and self.oportunidad_id.active and self.oportunidad_id.won_status == 'pending') \
            else Lead
        if not abierta and self.partner_id:
            abierta = Lead.search([
                ('partner_id', '=', self.partner_id.id), ('type', '=', 'opportunity'), ('won_status', '=', 'pending'),
                ('create_date', '>=', ahora - OPORTUNIDAD_RECIENTE)], order='id desc', limit=1)
        etiqueta = dict(CANALES).get(self.canal, self.canal)
        nota = Markup('<p><strong>%s</strong></p><p>%s</p>') % (
            escape(self.env._('Desde la conversación de %s', etiqueta)), escape(resumen or ''))
        if abierta:
            abierta.message_post(body=nota, subtype_xmlid='mail.mt_note')
            if presupuesto and not abierta.expected_revenue:
                abierta.write({'expected_revenue': presupuesto})
            if not self.oportunidad_id:
                self.sudo().write({'oportunidad_id': abierta.id})
            return abierta, False
        partner = self.partner_id.sudo()
        titulo = (interes or resumen or self.env._('Consulta')).strip().replace('\n', ' ')
        valores = {
            'name': f'{etiqueta}: {titulo}'[:120],
            'type': 'opportunity',
            'partner_id': partner.id,
            'phone': partner.phone or False,
            'email_from': partner.email or False,
            'description': nota,
            'user_id': (usuario or self.asignada_a).id if (usuario or self.asignada_a) else False,
        }
        if presupuesto and presupuesto > 0:
            valores['expected_revenue'] = presupuesto
        lead = Lead.with_context(mail_create_nosubscribe=True).create(valores)
        self.sudo().write({'oportunidad_id': lead.id})
        self._aviso(self.env._('Se creó la oportunidad «%s».', lead.name))
        self._notificar_panel('estado')
        return lead, True

    def _nota_en_ficha(self, nota, titulo=None):
        """Nota interna en el chatter de la ficha del cliente."""
        self.ensure_one()
        partner = self.partner_id.sudo()
        cuerpo = Markup('<p><strong>%s</strong></p><p>%s</p>') % (
            escape(titulo or self.env._('Nota del asistente')), escape((nota or '')[:MAX_NOTA]))
        partner.message_post(body=cuerpo, message_type='comment', subtype_xmlid='mail.mt_note',
                             author_id=self.env['dcasa.mensaje']._partner_del_bot().id)

    # ------------------------------------------------------------------
    # Pasar a una vendedora (herramienta del asistente)
    # ------------------------------------------------------------------

    def _pasar_a_vendedora(self, motivo, urgencia='normal'):
        """Pausa al asistente, deja una actividad y avisa. Devuelve lo que el asistente le dice al cliente."""
        self.ensure_one()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        ahora = fields.Datetime.now()
        horario = ajustes.horario()
        dentro = H.dentro_de_horario(ahora, horario)
        self._poner_en_humano()
        responsable = self.asignada_a or ajustes.responsable_id or self.env.ref('base.user_admin', False)
        urgente = urgencia == 'alta'
        cliente = self.partner_id.display_name or self.id_externo
        resumen = self.env._('%(u)sAtender a %(c)s (%(canal)s)', u='URGENTE: ' if urgente else '', c=cliente,
                             canal=dict(CANALES).get(self.canal, self.canal))
        if responsable:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo', summary=resumen[:200],
                note=escape((motivo or '')[:MAX_NOTA]) or False, user_id=responsable.id)
        self._avisar_por_telegram(self.env._(
            '%(r)s\nMotivo: %(m)s\n%(h)s', r=resumen, m=motivo or '—',
            h=self.env._('Dentro del horario.') if dentro else self.env._('Fuera del horario laboral.')))
        self._aviso(self.env._('El asistente pasó la conversación a una vendedora. Motivo: %s',
                               (motivo or '—')[:300]))
        self._notificar_panel('estado')
        cuando = H.cuando_atienden(ahora, horario)
        if dentro:
            texto = self.env._(
                'Listo, ya avisé a una vendedora para que te atienda por aquí. Ella te escribe en cuanto pueda.')
        else:
            texto = self.env._('Ya dejé tu consulta anotada para una vendedora. Te escribe %s.', cuando.rstrip('.'))
        return {'texto_para_el_cliente': texto, 'dentro_de_horario': dentro, 'urgente': urgente}

    def _avisar_por_telegram(self, texto):
        """Aviso a las vendedoras por Telegram (el bot de Brian). Nunca falla: es un extra de la actividad."""
        Enlace = self.env['brian.telegram.enlace'].sudo()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        dominio = [('activo', '=', True)]
        if ajustes.usuarios_aviso_ids:
            dominio.append(('user_id', 'in', ajustes.usuarios_aviso_ids.ids))
        else:
            dominio.append(('user_id.all_group_ids', 'in', self.env.ref(GRUPO_VENDEDORA).ids))
        enviados = 0
        for enlace in Enlace.search(dominio, limit=10):
            try:
                with self.env.cr.savepoint():
                    Enlace._enviar(enlace.chat_id, texto)
                    enviados += 1
            except Exception:   # noqa: BLE001
                _logger.exception('Juan: no se pudo avisar por Telegram')
        return enviados
