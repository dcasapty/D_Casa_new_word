"""Cada mensaje de una conversación: lo que dijo el cliente, el asistente o una vendedora.

* **Idempotencia**: ``UNIQUE(conversacion_id, id_mensaje)``. El Worker puede repetir la misma
  petición cuantas veces quiera; el mensaje queda una sola vez.
* **Nunca se pierde**: lo que una vendedora escribe en Odoo queda «por enviar» hasta que el Worker
  confirma; si no responde, un cron lo reintenta y, si se agotan los intentos, queda «fallido» a la
  vista con un botón para reintentar. Nada se borra solo.
* **El historial no se edita**: el texto, la hora y el autor de un mensaje no cambian (solo el
  sistema toca el estado del envío).
* Cada mensaje queda también en el chatter de la ficha del cliente.
"""
import base64
import logging
import uuid
from datetime import timedelta

from markupsafe import Markup, escape
from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import AccessError, ConcurrencyError, UserError
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import sql as tools_sql

from . import adjuntos as A
from . import firma as F
from . import horario as H
from . import transaccion
from .ajustes import CANALES

_logger = logging.getLogger(__name__)

DIRECCIONES = [('entrante', 'Entrante'), ('saliente', 'Saliente'), ('interna', 'Interna')]
AUTORES = [('cliente', 'Cliente'), ('bot', 'Asistente'), ('vendedora', 'Vendedora'), ('sistema', 'Sistema')]
# «mensaje» es lo que viaja por el canal. «nota» es interna entre vendedoras (el cliente jamás la ve) y «aviso» lo
# escribe el sistema en el hilo («el asistente pasó la conversación a una vendedora»): ninguno sale por el canal.
TIPOS = [('mensaje', 'Mensaje'), ('nota', 'Nota interna'), ('aviso', 'Aviso del sistema')]
ESTADOS_ENVIO = [
    ('recibido', 'Recibido'),
    ('programado', 'Programado'),
    ('por_enviar', 'Por enviar'),
    ('enviado', 'Enviado'),
    ('fallido', 'No se pudo enviar'),
]
# Lo que el canal dice de un mensaje NUESTRO (las «palomitas» de WhatsApp): enviado ✓, entregado ✓✓, leído ✓✓ azul o
# no llegó ⚠. Los avisos llegan desordenados y repetidos: nunca se baja de estado (leído le gana a entregado, que le
# gana a enviado). «No llegó» queda entre «enviado» y «entregado»: si después llega «entregado», es que sí llegó.
ESTADOS_CANAL = [('enviado', 'Enviado'), ('fallido', 'No llegó'), ('entregado', 'Entregado'), ('leido', 'Leído')]
RANGO_CANAL = {'enviado': 1, 'fallido': 2, 'entregado': 3, 'leido': 4}
REENVIADO = [('una', 'Reenviado'), ('muchas', 'Reenviado muchas veces')]
TIPOS_DE_PARTE = [('texto', 'Texto'), ('imagen', 'Foto'), ('documento', 'Documento'), ('audio', 'Audio'),
                  ('video', 'Video')]
MAX_TEXTO_CITA = 300
MAX_PARTES = 30
# Un «leído» (o «entregado») de una burbuja vale también para las anteriores de la conversación: se suben a lo más
# estas partes por aviso (las que ya subieron no vuelven a contar, así que casi nunca son más de unas pocas).
MAX_PARTES_QUE_SUBEN = 100
# Un id propio de Odoo o del Worker (no del canal): con él no se puede citar ni reconocer un aviso del canal.
PREFIJOS_PROPIOS = ('odoo-', 'bot-', 'vendedora-', 'nota-', 'aviso-')
MAX_INTENTOS = 12                       # con el cron cada 5 min: ~1 hora de reintentos
EDAD_MINIMA_REINTENTO = timedelta(minutes=2)
VENTANA_ADOPCION = timedelta(minutes=15)
CLAVE_SISTEMA = 'dcasa_mensaje_sistema'
# Índices de una sola columna que ya no se declaran: `conversacion_id` y `id_mensaje` los cubren `_hilo_idx` y la
# restricción única; `canal`, `tipo` y `autor` tienen 2 a 5 valores (un índice así no ayuda a buscar);
# `estado_envio` pasó a uno parcial.
INDICES_QUE_SOBRAN = ('conversacion_id', 'id_mensaje', 'canal', 'tipo', 'autor', 'estado_envio')


class DcasaMensaje(models.Model):
    _name = 'dcasa.mensaje'
    _description = 'Mensaje de una conversación'
    _order = 'ts, id'
    _rec_name = 'id_mensaje'

    # Sin `index=True`: lo cubren `_hilo_idx` y la restricción única, que empiezan por `conversacion_id`.
    conversacion_id = fields.Many2one('dcasa.conversacion', required=True, ondelete='cascade', readonly=True)
    partner_id = fields.Many2one(related='conversacion_id.partner_id', store=True, index=True)
    canal = fields.Selection(related='conversacion_id.canal', store=True)
    tipo = fields.Selection(TIPOS, default='mensaje', required=True, readonly=True)
    direccion = fields.Selection(DIRECCIONES, required=True, readonly=True)
    autor = fields.Selection(AUTORES, required=True, readonly=True)
    id_mensaje = fields.Char('Id del mensaje', required=True, readonly=True,
                             help='Lo asigna el canal (o el Worker). Es la llave de la idempotencia.')
    # `trigram`: la búsqueda de la bandeja («lo que se dijo en cualquier mensaje») usa ILIKE '%…%', que sin este
    # índice recorre todos los mensajes.
    texto = fields.Text(readonly=True, index='trigram')
    ts = fields.Datetime('Fecha', required=True, readonly=True, default=fields.Datetime.now, index=True)
    chatter_id = fields.Many2one(
        'mail.message', 'Copia en la ficha del cliente', readonly=True, copy=False, ondelete='set null',
        index='btree_not_null',
        help='La nota que este mensaje dejó en el chatter del cliente. Se borra junto con el mensaje (Ley 81).')
    adjunto_ids = fields.Many2many('ir.attachment', 'dcasa_mensaje_adjunto_rel', 'mensaje_id', 'adjunto_id',
                                   string='Adjuntos', readonly=True)
    adjuntos_fallidos = fields.Integer('Adjuntos que no se pudieron traer', readonly=True)
    mencion_ids = fields.Many2many(
        'res.users', 'dcasa_mensaje_mencion_rel', 'mensaje_id', 'usuario_id', string='Mencionadas', readonly=True,
        help='Compañeras mencionadas con @ en esta nota interna.')
    tiene_sensible = fields.Boolean('Adjunto sensible', readonly=True,
                                    help='Comprobante de pago o documento de identidad: no se le muestra a la IA.')
    origen = fields.Selection([('canal', 'Del canal'), ('odoo', 'Escrito en Odoo')], default='canal', readonly=True,
                              required=True)
    usuario_id = fields.Many2one('res.users', 'Escrito por', readonly=True,
                                 help='La vendedora que lo escribió en Odoo.')
    estado_envio = fields.Selection(ESTADOS_ENVIO, default='recibido', required=True, readonly=True)
    programado_para = fields.Datetime(
        'Se envía el', readonly=True, index='btree_not_null',
        help='Mensaje que una vendedora dejó programado: sale solo a esta hora (la revisión corre cada 5 minutos).')
    intentos = fields.Integer(readonly=True)
    ultimo_intento = fields.Datetime(readonly=True)
    error_envio = fields.Char('Por qué no salió', readonly=True)

    # --- Citas, reenviados, reacciones y palomitas (pedido de la dueña, 2026-11-07). Solo los escribe el sistema. ---
    cita_id = fields.Many2one(
        'dcasa.mensaje', 'Responde a', readonly=True, ondelete='set null', index='btree_not_null',
        help='El mensaje que el cliente citó (o que la vendedora citó al responder).')
    cita_id_canal = fields.Char(
        'Id del mensaje citado', readonly=True, index='btree_not_null',
        help='El id que dio el canal del mensaje citado. Se guarda aunque ese mensaje no esté en el historial.')
    cita_parte_id = fields.Many2one(
        'dcasa.mensaje.parte', 'Burbuja citada', readonly=True, ondelete='set null',
        help='Si el citado es un mensaje nuestro que salió en varias burbujas: justo la que el cliente citó.')
    cita_texto = fields.Char(
        'Lo que decía el mensaje citado (copia del canal)', readonly=True,
        help='Solo cuando lo citado NO está en el historial (Telegram manda el texto citado): las primeras letras. '
             'Si está, lo citado se lee del mensaje original, así borrarlo lo borra también de las respuestas.')
    reenviado = fields.Selection(REENVIADO, readonly=True)
    reaccion = fields.Char('Reacción del cliente', readonly=True, help='El emoji con que el cliente reaccionó.')
    reaccion_en = fields.Datetime('Reaccionó el', readonly=True)
    estado_canal = fields.Selection(
        ESTADOS_CANAL, 'Estado en el canal', readonly=True,
        help='Lo que dice WhatsApp de un mensaje nuestro: enviado, entregado, leído o que no llegó.')
    canal_enviado_en = fields.Datetime('Enviado (según el canal)', readonly=True)
    canal_entregado_en = fields.Datetime('Entregado', readonly=True)
    canal_leido_en = fields.Datetime('Leído', readonly=True)
    parte_ids = fields.One2many('dcasa.mensaje.parte', 'mensaje_id', 'Partes en el canal', readonly=True)

    _id_mensaje_unico = models.Constraint(
        'UNIQUE(conversacion_id, id_mensaje)', 'Ese mensaje ya está registrado en la conversación.')
    _direccion_autor = models.Constraint(
        "CHECK((tipo = 'mensaje' AND ((direccion = 'entrante' AND autor = 'cliente') "
        "OR (direccion = 'saliente' AND autor IN ('bot', 'vendedora')))) "
        "OR (tipo = 'nota' AND direccion = 'interna' AND autor = 'vendedora') "
        "OR (tipo = 'aviso' AND direccion = 'interna' AND autor = 'sistema'))",
        'Un mensaje entrante es del cliente; uno saliente, del asistente o de una vendedora; una nota, de una '
        'vendedora; un aviso, del sistema.')
    def init(self):
        """Odoo NO borra un índice cuando a un campo se le quita ``index=True`` (lo deja: «Keep unexpected index»),
        así que en una base que ya existía seguirían ahí, estorbando al guardar cada mensaje. Se borran aquí."""
        super().init()
        for campo in INDICES_QUE_SOBRAN:
            tools_sql.drop_index(self.env.cr, tools_sql.make_index_name(self._table, campo), self._table)

    # El hilo se pide por tramos hacia atrás (id < X, de 50 en 50): con este índice es una lectura de índice.
    _hilo_idx = models.Index('(conversacion_id, id)')
    # Solo lo que espera salir o falló (unas pocas filas entre muchas): los crones lo encuentran sin recorrer todo.
    _pendientes_idx = models.Index("(estado_envio) WHERE estado_envio IN ('por_enviar', 'programado', 'fallido')")

    def unlink(self):
        """Borrar un mensaje (derecho de borrado, Ley 81) borra también su copia en la ficha del cliente, y lo que de
        él se veía en los mensajes que lo citaban (revisión 2026-11-07): la cita queda «un mensaje que no está en el
        historial», en el hilo y en el chatter."""
        copias = self.sudo().chatter_id
        citantes = self.sudo().search([('cita_id', 'in', self.ids), ('id', 'not in', self.ids)])
        resultado = super().unlink()
        copias.sudo().unlink()
        if citantes:
            citantes.invalidate_recordset(['cita_id', 'cita_parte_id'])
            citantes.with_context(**{CLAVE_SISTEMA: True}).write({'cita_texto': False})
            for citante in citantes.filtered('chatter_id'):
                citante.chatter_id.sudo().write({'body': citante._cuerpo_chatter()})
        return resultado

    # ------------------------------------------------------------------
    # El historial no se edita
    # ------------------------------------------------------------------

    def write(self, vals):
        if not self.env.context.get(CLAVE_SISTEMA) and not self.env.su:
            raise AccessError(self.env._('El historial de la conversación no se edita.'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Crear
    # ------------------------------------------------------------------

    @api.model
    def _crear_si_no_existe(self, valores):
        """Crea el mensaje; si ya existe (mismo ``id_mensaje`` en la conversación) devuelve el que había.

        Devuelve ``(mensaje, creado)``. La carrera con otra petición que inserte el mismo id se
        resuelve con la restricción única: la perdedora ve el mensaje de la ganadora.
        """
        Mensaje = self.sudo().with_context(**{CLAVE_SISTEMA: True})
        dominio = [('conversacion_id', '=', valores['conversacion_id']), ('id_mensaje', '=', valores['id_mensaje'])]
        existente = Mensaje.search(dominio, limit=1)
        if existente:
            return existente, False
        try:
            with self.env.cr.savepoint():
                return Mensaje.create(valores), True
        except IntegrityError:
            existente = Mensaje.search(dominio, limit=1)
            if existente:
                return existente, False
            raise

    @api.model
    def _id_local(self):
        """Id provisional de un mensaje escrito en Odoo mientras el Worker no confirma el suyo."""
        return f'odoo-{uuid.uuid4().hex}'

    def _adjuntar(self, adjuntos, sensible_de_oficio=False):
        """Trae los archivos de ``adjuntos`` (ya validados) y los guarda como ``ir.attachment``.

        Un adjunto que no se pueda traer no tumba el mensaje: se cuenta en ``adjuntos_fallidos`` y la
        burbuja lo dice. ``sensible_de_oficio`` marca todos como sensibles.
        """
        self.ensure_one()
        Adjunto = self.env['ir.attachment'].sudo()
        creados, fallidos = Adjunto, 0
        worker = self.env['dcasa.juan.ajustes'].url_worker()
        origen = worker if worker and self.env['dcasa.juan.cliente']._url_valida(worker) else None
        for adjunto in adjuntos:
            contenido = A.obtener_contenido(adjunto, origen_confiable=origen)
            if not contenido:
                fallidos += 1
                continue
            mime = adjunto.get('mime') or A.tipo_de_medio(contenido, adjunto['tipo'])
            valores = {
                'name': A.nombre_con_extension(adjunto['nombre'], mime), 'datas': base64.b64encode(contenido),
                'res_model': self._name, 'res_id': self.id, 'public': False, 'description': adjunto['tipo'],
                'dcasa_sensible': bool(adjunto.get('sensible') or sensible_de_oficio),
            }
            if mime:
                valores['mimetype'] = mime
            creados |= Adjunto.create(valores)
        sensible = any(creados.mapped('dcasa_sensible'))
        self.with_context(**{CLAVE_SISTEMA: True}).sudo().write({
            'adjunto_ids': [(4, a.id) for a in creados], 'adjuntos_fallidos': fallidos,
            'tiene_sensible': sensible})
        return creados

    @api.model
    def _crear_interno(self, conversacion, tipo, texto, usuario=None, menciones=None):
        """Una nota interna (de una vendedora) o un aviso del sistema dentro del hilo. Nunca sale por el canal.

        ``menciones``: las compañeras mencionadas con @ (``res.users``); solo tiene sentido en una nota.
        """
        if tipo not in ('nota', 'aviso'):
            raise ValueError(tipo)
        valores = {
            'conversacion_id': conversacion.id, 'id_mensaje': f'{tipo}-{uuid.uuid4().hex}', 'tipo': tipo,
            'direccion': 'interna', 'autor': 'vendedora' if tipo == 'nota' else 'sistema',
            'texto': (texto or '').strip()[:2000] or False, 'ts': fields.Datetime.now(), 'origen': 'odoo',
            'usuario_id': usuario.id if usuario else False, 'estado_envio': 'enviado',
        }
        if menciones and tipo == 'nota':
            valores['mencion_ids'] = [(6, 0, menciones.ids)]
        mensaje, _creado = self._crear_si_no_existe(valores)
        return mensaje

    # ------------------------------------------------------------------
    # Chatter del cliente
    # ------------------------------------------------------------------

    def _publicar_en_chatter(self):
        """Deja el mensaje en el chatter de la ficha del cliente (nota interna, no avisa a nadie)."""
        self.ensure_one()
        partner = self.partner_id.sudo()
        if not partner or self.tipo == 'aviso':
            return
        copia = partner.with_context(mail_post_autofollow=False).message_post(
            body=self._cuerpo_chatter(), message_type='comment', subtype_xmlid='mail.mt_note',
            author_id=self._autor_en_chatter(), attachment_ids=self.adjunto_ids.ids)
        self.sudo().chatter_id = copia   # para poder borrarla con el mensaje

    def _autor_en_chatter(self):
        """Quién firma la copia en el chatter: la vendedora (o quien escribió la nota), el cliente o el asistente."""
        self.ensure_one()
        if self.tipo != 'nota' and self.autor == 'cliente':
            return self.partner_id.sudo().id
        usuario = self.usuario_id if self.tipo == 'nota' or self.autor != 'bot' else self.env['res.users']
        return usuario.partner_id.id if usuario else self._partner_del_bot().id

    def _cuerpo_chatter(self):
        """El HTML de la copia en el chatter (se rehace si se borra el mensaje que citaba)."""
        self.ensure_one()
        canal = dict(CANALES).get(self.canal, self.canal)
        if self.tipo == 'nota':
            quien = self.env._('Nota interna de %s', self.usuario_id.name or self.env._('una vendedora'))
        elif self.autor == 'cliente':
            quien = 'Cliente'
        elif self.autor == 'bot':
            quien = self.env._('Asistente')
        else:
            usuario = self.usuario_id
            quien = self.env._('Vendedora %s', usuario.name) if usuario else self.env._('Vendedora (desde el teléfono)')
        cuerpo = Markup('<p><strong>%s · %s</strong></p>') % (escape(canal), escape(quien))
        if self.reenviado:
            cuerpo += Markup('<p><em>%s</em></p>') % escape(dict(REENVIADO)[self.reenviado])
        if self.cita_id or self.cita_id_canal:
            cita = self._cita_como_dict()
            cuerpo += Markup('<blockquote>%s</blockquote>') % escape(
                self.env._('Responde a: «%s»', cita['texto']) if cita['texto']
                else self.env._('Responde a un mensaje que no está en el historial'))
        cuerpo += Markup('<p>%s</p>') % (
            _con_saltos(self.texto) if self.texto else escape(self.env._('(sin texto)')))
        if self.tiene_sensible:
            cuerpo += Markup('<p><em>%s</em></p>') % escape(self.env._(
                'Adjunto sensible (comprobante o documento): lo revisa una vendedora; no se le muestra a la IA.'))
        if self.adjuntos_fallidos:
            cuerpo += Markup('<p><em>%s</em></p>') % escape(self.env._(
                'No se pudo traer %s adjunto(s) del mensaje.', self.adjuntos_fallidos))
        return cuerpo

    @api.model
    def _partner_del_bot(self):
        usuario = self.env.ref('dcasa_conversaciones.user_juan', raise_if_not_found=False)
        return (usuario or self.env.user).sudo().partner_id

    # ------------------------------------------------------------------
    # Enviar lo que una vendedora escribió en Odoo
    # ------------------------------------------------------------------

    def _datos_adjuntos_para_worker(self):
        """Los adjuntos como los espera ``POST /odoo/enviar``: ``{tipo, url, nombre, mime}``.

        La ``url`` es FIRMADA y de VIDA CORTA (15 minutos por defecto, ``dcasa_conversaciones.url_adjunto_minutos``):
        el puente la baja desde internet sin sesión, pero el enlace no sirve después ni si el archivo cambia
        (ver ``firma.py``). Cada reintento de envío genera una nueva.
        """
        self.ensure_one()
        parametros = self.env['ir.config_parameter'].sudo()
        base = (parametros.get_param('web.base.url') or '').rstrip('/')
        secreto = parametros.get_param('database.secret') or ''
        try:
            vida = int(parametros.get_param('dcasa_conversaciones.url_adjunto_minutos') or 15) * 60
        except ValueError:
            vida = F.VIDA_POR_DEFECTO
        return [{
            'tipo': A.tipo_de_mime(adjunto.mimetype), 'nombre': adjunto.name, 'mime': adjunto.mimetype or '',
            'url': base + F.ruta_firmada(secreto, adjunto.id, adjunto.checksum, adjunto.name, vida),
        } for adjunto in self.adjunto_ids.sudo()]

    def _enviar(self):
        """Intenta mandar cada mensaje «por enviar» por el Worker. Devuelve cuántos salieron."""
        salieron = 0
        Cliente = self.env['dcasa.juan.cliente']
        ahora = fields.Datetime.now()
        por_enviar = self.sudo().filtered(lambda m: m.estado_envio == 'por_enviar')
        if por_enviar:
            # El Worker (y el puente, que baja el adjunto por su URL firmada) llaman de vuelta a Odoo mientras Odoo
            # espera: solo ven lo ya confirmado. Además, así el mensaje no se pierde si esta petición se cae a medias.
            transaccion.confirmar(self.env)
        for mensaje in por_enviar:
            conversacion = mensaje.conversacion_id
            # El id del mensaje es la llave de idempotencia: un reintento (sin oír la respuesta) no duplica lo enviado.
            # «Responder» a un mensaje: el canal lo muestra citado si se sabe su id en el canal (si no, sale sin cita).
            resultado = Cliente.enviar(
                conversacion.canal, conversacion.id_externo, texto=mensaje.texto or None,
                adjuntos=mensaje._datos_adjuntos_para_worker() or None, id_envio=mensaje.id_mensaje,
                responde_a=mensaje.cita_id._id_canal_para_citar() if mensaje.cita_id else None)
            intentos = mensaje.intentos + 1
            sistema = mensaje.with_context(**{CLAVE_SISTEMA: True})
            if resultado.get('ok'):
                sistema._marcar_enviado(resultado.get('id_mensaje'), partes=resultado.get('partes'))
                salieron += 1
                continue
            if resultado.get('sin_configurar'):
                # Falta configurar el Worker: no es culpa del mensaje, no gasta intentos.
                sistema.write({'error_envio': resultado['error'][:200]})
                continue
            sistema.write({
                'intentos': intentos, 'ultimo_intento': ahora,
                'error_envio': (resultado.get('error') or 'Sin respuesta del Worker.')[:200],
                'estado_envio': 'fallido' if intentos >= MAX_INTENTOS or resultado.get('estado_http') in (400, 422)
                else 'por_enviar'})
        return salieron

    def _marcar_enviado(self, id_externo, partes=None):
        """El Worker confirmó el envío. Si ya había registrado su propio eco con ese id, se fusionan.

        ``partes``: los ids que el canal dio a cada burbuja o archivo (un Juan nuevo los manda; uno viejo solo manda
        ``id_mensaje``, el del primero). Con ellos se reconocen después las palomitas y las citas del cliente.
        """
        mensaje = self._marcar_enviado_sin_partes(id_externo)
        if isinstance(partes, list) and partes:
            mensaje._crear_partes(partes)
        elif isinstance(id_externo, str) and id_externo and not id_externo.startswith(PREFIJOS_PROPIOS):
            mensaje._crear_partes([{'id_canal': id_externo, 'tipo': mensaje._tipo_de_parte(),
                                    'texto': mensaje._texto_corto()}])
        return mensaje

    def _marcar_enviado_sin_partes(self, id_externo):
        self.ensure_one()
        sistema = self.with_context(**{CLAVE_SISTEMA: True})
        valores = {'estado_envio': 'enviado', 'intentos': self.intentos + 1,
                   'ultimo_intento': fields.Datetime.now(), 'error_envio': False}
        id_externo = (id_externo or '')[:255] if isinstance(id_externo, str) else ''
        if id_externo and id_externo != self.id_mensaje:
            eco = sistema.search([('conversacion_id', '=', self.conversacion_id.id),
                                  ('id_mensaje', '=', id_externo), ('id', '!=', self.id)], limit=1)
            if eco:
                # El Worker ya había registrado este mensaje: el eco se queda con todo lo nuestro.
                valores_eco = {
                    'estado_envio': 'enviado', 'usuario_id': self.usuario_id.id, 'origen': 'odoo',
                    'adjunto_ids': [(4, a.id) for a in self.adjunto_ids],
                    'tiene_sensible': self.tiene_sensible or eco.tiene_sensible}
                if (self.cita_id or self.cita_id_canal) and not (eco.cita_id or eco.cita_id_canal):
                    # El «Responder» de la vendedora: el eco no sabe a qué respondía (revisión 2026-11-07).
                    valores_eco.update({'cita_id': self.cita_id.id, 'cita_id_canal': self.cita_id_canal,
                                        'cita_parte_id': self.cita_parte_id.id, 'cita_texto': self.cita_texto})
                eco.write(valores_eco)
                self.adjunto_ids.sudo().write({'res_id': eco.id})   # que no se borren con este mensaje
                self.write({'adjunto_ids': [(5, 0, 0)]})
                self.sudo().unlink()
                return eco
            valores['id_mensaje'] = id_externo
        self.write(valores)
        return self

    @api.model
    def _cron_enviar_programados(self):
        """Lo programado cuya hora ya llegó pasa a «por enviar» y sale por el canal. Devuelve cuántos."""
        ahora = fields.Datetime.now()
        vencidos = self.sudo().search([
            ('estado_envio', '=', 'programado'), ('programado_para', '<=', ahora),
        ], order='programado_para, id', limit=50)
        nuevos = self.browse()
        for mensaje in vencidos:
            try:
                with self.env.cr.savepoint():
                    nuevos |= mensaje.conversacion_id._despachar_programado(mensaje)
            except Exception:   # noqa: BLE001
                _logger.exception('Juan: no se pudo despachar el mensaje programado %s', mensaje.id)
        if nuevos and self.env['dcasa.juan.cliente'].configurado():
            nuevos._enviar()
        return len(nuevos)

    @api.model
    def _cron_reintentar_envios(self):
        """Reintenta lo «por enviar» (cada 5 minutos). Nada se pierde: al agotarse, queda «fallido» a la vista."""
        ahora = fields.Datetime.now()
        pendientes = self.sudo().search([
            ('estado_envio', '=', 'por_enviar'),
            '|', ('ultimo_intento', '=', False), ('ultimo_intento', '<=', ahora - EDAD_MINIMA_REINTENTO),
        ], order='id', limit=50)
        if not pendientes or not self.env['dcasa.juan.cliente'].configurado():
            return 0
        return pendientes._enviar()

    def action_reintentar(self):
        """Botón «Reintentar envío» de un mensaje que no salió."""
        self.env['dcasa.conversacion']._exigir_vendedora()
        fallidos = self.sudo().filtered(lambda m: m.estado_envio in ('fallido', 'por_enviar') and m.origen == 'odoo')
        fallidos.with_context(**{CLAVE_SISTEMA: True}).write({'estado_envio': 'por_enviar', 'intentos': 0})
        fallidos._enviar()
        return True

    # ------------------------------------------------------------------
    # Para la pantalla del panel (diccionarios sencillos, listos para JSON)
    # ------------------------------------------------------------------

    def _como_dict(self):
        """El mensaje como lo pinta la pantalla: sin registros, con fechas ISO en UTC (``…Z``)."""
        self.ensure_one()
        return {
            'id': self.id, 'tipo': self.tipo, 'autor': self.autor, 'direccion': self.direccion,
            'texto': self.texto or '', 'ts': H.a_iso(self.ts),
            'usuario': {'id': self.usuario_id.id, 'nombre': self.usuario_id.name} if self.usuario_id else None,
            'menciones': [{'id': u.id, 'nombre': u.name} for u in self.mencion_ids.sudo()],
            'estado_envio': self.estado_envio, 'error': self.error_envio or None, 'origen': self.origen,
            'programado_para': H.a_iso(self.programado_para) if self.programado_para else None,
            'adjuntos': [adjunto_como_dict(a) for a in self.adjunto_ids.sudo()],
            'adjuntos_fallidos': self.adjuntos_fallidos,
            'cita': self._cita_como_dict(),
            'reenviado': self.reenviado or None,
            'reaccion': self.reaccion or None,
            # Las palomitas (solo si el canal las dio: WhatsApp oficial; Telegram no las da a los bots).
            'estado_canal': self.estado_canal or None,
            'canal_entregado_en': H.a_iso(self.canal_entregado_en) if self.canal_entregado_en else None,
            'canal_leido_en': H.a_iso(self.canal_leido_en) if self.canal_leido_en else None,
            # «Responder» solo se ofrece si el canal sabrá mostrar la cita (hay un id del canal).
            'se_puede_citar': self.tipo == 'mensaje' and bool(self._id_canal_para_citar()),
        }

    # ------------------------------------------------------------------
    # Citas, reenviados, reacciones y palomitas
    # ------------------------------------------------------------------

    def _tipo_de_parte(self):
        """Qué es este mensaje para el canal: texto o, si no tiene texto, el tipo de su primer archivo."""
        self.ensure_one()
        if self.texto or not self.adjunto_ids:
            return 'texto'
        tipo = A.tipo_de_mime(self.adjunto_ids[:1].sudo().mimetype)
        return tipo if tipo in dict(TIPOS_DE_PARTE) else 'documento'

    def _texto_corto(self):
        """Lo que se muestra de este mensaje cuando alguien lo cita: su texto, o «Foto», «Audio»… si no tiene."""
        self.ensure_one()
        if self.tiene_sensible:
            return self.env._('Archivo sensible')
        texto = ' '.join((self.texto or '').split())
        if texto:
            return texto[:MAX_TEXTO_CITA]
        adjunto = self.adjunto_ids[:1].sudo()
        if not adjunto:
            return ''
        if 'sticker' in (adjunto.name or '').lower():
            return self.env._('Sticker')
        return dict(TIPOS_DE_PARTE).get(A.tipo_de_mime(adjunto.mimetype), self.env._('Documento'))

    def _id_canal_para_citar(self):
        """El id que el canal dio a este mensaje (para responderle citándolo), o ``''`` si no se sabe."""
        self.ensure_one()
        if self.tipo != 'mensaje':
            return ''
        if self.id_mensaje and not self.id_mensaje.startswith(PREFIJOS_PROPIOS):
            return self.id_mensaje
        return self.sudo().parte_ids[:1].id_canal or ''

    def _cita_como_dict(self):
        """La cita para la pantalla: quién dijo lo citado y sus primeras letras; ``en_historial: False`` si no está."""
        self.ensure_one()
        if not (self.cita_id or self.cita_id_canal or self.cita_texto):
            return None
        original = self.cita_id.sudo()
        if not original:
            return {'id': None, 'autor': None, 'usuario': None, 'texto': self.cita_texto or '', 'en_historial': False}
        # Se lee del original, no de una copia: si se borra, se borra también aquí (Ley 81; revisión 2026-11-07).
        parte = self.cita_parte_id.sudo()
        texto = (_texto_de_parte(parte) if parte and parte.mensaje_id == original else '') or original._texto_corto()
        return {
            'id': original.id, 'autor': original.autor,
            'usuario': ({'id': original.usuario_id.id, 'nombre': original.usuario_id.name}
                        if original.usuario_id else None),
            'texto': ' '.join((texto or '').split())[:MAX_TEXTO_CITA], 'en_historial': True,
        }

    @api.model
    def _buscar_por_id_canal(self, conversacion, id_canal):
        """El mensaje (y, si es nuestro, la parte) que el canal conoce con ``id_canal`` en esa conversación."""
        Mensaje = self.sudo()
        if not id_canal:
            return Mensaje, self.env['dcasa.mensaje.parte']
        mensaje = Mensaje.search([('conversacion_id', '=', conversacion.id), ('id_mensaje', '=', id_canal),
                                  ('tipo', '=', 'mensaje')], limit=1)
        parte = self.env['dcasa.mensaje.parte'].sudo().search(
            [('conversacion_id', '=', conversacion.id), ('id_canal', '=', id_canal)], limit=1)
        return (mensaje or parte.mensaje_id), parte

    @api.model
    def _valores_de_cita(self, conversacion, cita):
        """``cita`` (ya validada por la API): ``{id_canal, texto?}``. Devuelve los campos que guarda el mensaje."""
        if not cita:
            return {}
        original, parte = self._buscar_por_id_canal(conversacion, cita.get('id_canal'))
        valores = {'cita_id': original.id or False, 'cita_id_canal': cita.get('id_canal') or False,
                   'cita_parte_id': parte.id or False, 'cita_texto': False}
        if not original:
            # Solo lo que no está en el historial se copia (lo que manda Telegram): no hay otro lado de donde leerlo.
            valores['cita_texto'] = ' '.join((cita.get('texto') or '').split())[:MAX_TEXTO_CITA] or False
        return valores

    def _crear_partes(self, partes):
        """Anota los ids que el canal dio a cada burbuja o archivo de este mensaje nuestro (idempotente)."""
        self.ensure_one()
        Parte = self.env['dcasa.mensaje.parte'].sudo()
        conversacion = self.conversacion_id
        nuevos = []
        for indice, parte in enumerate(partes[:MAX_PARTES]):
            id_canal = parte.get('id_canal') if isinstance(parte, dict) else None
            if not isinstance(id_canal, str) or not id_canal or id_canal.startswith(PREFIJOS_PROPIOS):
                continue
            if Parte.search_count([('conversacion_id', '=', conversacion.id), ('id_canal', '=', id_canal)]):
                continue
            tipo = parte.get('tipo') if parte.get('tipo') in dict(TIPOS_DE_PARTE) else 'texto'
            texto = parte.get('texto') if isinstance(parte.get('texto'), str) else ''
            try:
                with self.env.cr.savepoint():
                    Parte.create({'mensaje_id': self.id, 'conversacion_id': conversacion.id, 'id_canal': id_canal,
                                  'indice': indice, 'tipo': tipo,
                                  'texto': ' '.join(texto.split())[:MAX_TEXTO_CITA] or False})
                    nuevos.append(id_canal)
            except IntegrityError:
                continue   # otra petición la anotó al mismo tiempo
        if nuevos:
            # El cliente citó este mensaje antes de que Odoo supiera sus ids (llega en paralelo): se enlaza ahora.
            citas = self.sudo().search([('conversacion_id', '=', conversacion.id), ('cita_id', '=', False),
                                        ('cita_id_canal', 'in', nuevos)])
            for cita in citas:
                parte = Parte.search([('conversacion_id', '=', conversacion.id),
                                      ('id_canal', '=', cita.cita_id_canal)], limit=1)
                # Ya se sabe cuál es: se lee de ahí y la copia que mandó el canal sobra.
                cita.with_context(**{CLAVE_SISTEMA: True}).write({
                    'cita_id': self.id, 'cita_parte_id': parte.id or False, 'cita_texto': False})
        return nuevos

    def _recalcular_estado_canal(self, ts):
        """El estado del mensaje según sus partes: «no llegó» si alguna no llegó; si no, el de la más atrasada."""
        self.ensure_one()
        estados = [p.estado_canal for p in self.sudo().parte_ids if p.estado_canal]
        if not estados:
            return False
        if 'fallido' in estados:
            agregado = 'fallido'
        else:
            agregado = min(estados, key=RANGO_CANAL.get)
        valores = {}
        if agregado != self.estado_canal:
            valores['estado_canal'] = agregado
        rango = RANGO_CANAL[agregado]
        if agregado != 'fallido':
            # Las horas son la primera vez que el mensaje llegó a cada estado (si «leído» llega antes que «entregado»,
            # entregó a esa misma hora).
            for minimo, campo in ((1, 'canal_enviado_en'), (3, 'canal_entregado_en'), (4, 'canal_leido_en')):
                if rango >= minimo and not self[campo]:
                    valores[campo] = ts
        if agregado == 'fallido':
            error = next((p.error for p in self.sudo().parte_ids if p.estado_canal == 'fallido' and p.error), None)
            valores['error_envio'] = (error or self.env._('WhatsApp avisó que no lo pudo entregar.'))[:200]
        elif self.estado_canal == 'fallido':
            valores['error_envio'] = False
        if valores:
            self.with_context(**{CLAVE_SISTEMA: True}).sudo().write(valores)
            return True
        return False

    def _recalcular_reaccion(self):
        """La reacción que se ve en la burbuja de un mensaje nuestro: la última que el cliente dejó en alguna parte."""
        self.ensure_one()
        con_hora = [p for p in self.sudo().parte_ids if p.reaccion_en]
        ultima = max(con_hora, key=lambda p: p.reaccion_en, default=None)
        visible = next((p.reaccion for p in sorted(con_hora, key=lambda p: p.reaccion_en, reverse=True) if p.reaccion),
                       False)
        self.with_context(**{CLAVE_SISTEMA: True}).sudo().write(
            {'reaccion': visible or False, 'reaccion_en': ultima.reaccion_en if ultima else False})

    @api.model
    def _aplicar_eventos(self, eventos):
        """Palomitas y reacciones que avisa el canal (``POST /dcasa/juan/v1/eventos``), ya validadas por la API.

        Nada de esto es un mensaje del cliente: no crea mensajes ni toca la actividad de la conversación (último mensaje
        del cliente, «sin leer», seguimientos, ventana de 24 h, reparto, Sofía) y no avisa a nadie como mensaje nuevo;
        solo pone al día la burbuja en las pantallas abiertas. Idempotente: repetir un aviso no cambia nada, y uno viejo
        que llega tarde no le gana a uno nuevo. Lo que se refiere a un mensaje que Odoo no conoce se devuelve en
        ``desconocidos`` (el Worker lo reintenta una vez: la respuesta del asistente puede estar registrándose).
        """
        Conversacion = self.env['dcasa.conversacion'].sudo()
        conversaciones = {}
        aplicados, fallidos, desconocidos, cambios = 0, 0, [], []
        for evento in eventos:
            clave = (evento['canal'], evento['id_externo'])
            if clave not in conversaciones:
                conversaciones[clave] = Conversacion.search(
                    [('canal', '=', clave[0]), ('id_externo', '=', clave[1])], limit=1)
            conversacion = conversaciones[clave]
            mensaje, parte = (self._buscar_por_id_canal(conversacion, evento['id_mensaje']) if conversacion
                              else (self.browse(), self.env['dcasa.mensaje.parte']))
            if not mensaje:
                desconocidos.append(evento['id_mensaje'])
                continue
            mensaje = mensaje.sudo()
            try:
                # Un aviso raro no tumba a los demás de la tanda (revisión 2026-11-07).
                with self.env.cr.savepoint():
                    if evento['tipo'] == 'estado':
                        cambiados = self._aplicar_estado(mensaje, parte, evento)
                    else:
                        cambiados = mensaje if self._aplicar_reaccion(mensaje, parte, evento) else self.browse()
            except (ConcurrencyError, *PG_CONCURRENCY_EXCEPTIONS_TO_RETRY):
                raise
            except Exception:   # noqa: BLE001 — una palomita nunca vale más que el resto de la tanda
                _logger.exception('Juan: no se pudo aplicar un aviso del canal (%s) a %s', evento['tipo'],
                                  evento['id_mensaje'])
                fallidos += 1
                continue
            if cambiados:
                aplicados += 1
                cambios.extend(m._recibo_para_pantallas(evento['tipo'] == 'reaccion' and m == mensaje)
                               for m in cambiados)
        if cambios:
            Conversacion._notificar_recibos(cambios)
        resultado = {'aplicados': aplicados, 'desconocidos': desconocidos}
        if fallidos:
            resultado['fallidos'] = fallidos
        return resultado

    def _recibo_para_pantallas(self, reaccion=False):
        """Lo liviano que viaja en vivo por cada palomita o reacción (ni texto ni emoji): ids, estado y sus horas."""
        self.ensure_one()
        return {'conversacion_id': self.conversacion_id.id, 'mensaje_id': self.id,
                'estado_canal': self.estado_canal or None,
                'canal_entregado_en': H.a_iso(self.canal_entregado_en) if self.canal_entregado_en else None,
                'canal_leido_en': H.a_iso(self.canal_leido_en) if self.canal_leido_en else None,
                'reaccion': bool(reaccion)}

    @api.model
    def _aplicar_estado(self, mensaje, parte, evento):
        """Una palomita de una parte. Devuelve los mensajes cuyo estado cambió (este y, si subió, los anteriores)."""
        if mensaje.direccion != 'saliente':
            return self.browse()   # las palomitas solo existen para lo que mandamos nosotros
        if not parte:
            # Un mensaje nuestro anotado con su id del canal pero sin partes (lo mandó un Juan viejo): se le crea una.
            nuevos = mensaje._crear_partes([{'id_canal': evento['id_mensaje'], 'tipo': mensaje._tipo_de_parte(),
                                             'texto': mensaje._texto_corto()}])
            parte = mensaje.parte_ids.filtered(lambda p: p.id_canal in nuevos)[:1]
            if not parte:
                return self.browse()
        estado = evento['estado']
        if RANGO_CANAL[estado] <= RANGO_CANAL.get(parte.estado_canal, 0):
            return self.browse()   # repetido o viejo: nunca se baja de estado
        valores = {'estado_canal': estado, 'estado_en': evento['ts']}
        if estado == 'fallido':
            valores['error'] = (evento.get('error') or '')[:200] or False
        parte.sudo().write(valores)
        cambiados = mensaje if mensaje._recalcular_estado_canal(evento['ts']) else self.browse()
        if estado in ('entregado', 'leido'):
            cambiados |= self._subir_anteriores(parte, estado, evento['ts'])
        return cambiados

    @api.model
    def _subir_anteriores(self, parte, estado, ts):
        """«Leído» (o «entregado») de una burbuja vale también para las anteriores de la conversación (revisión
        2026-11-07): WhatsApp a veces solo avisa del último de varios mensajes, y como el mensaje muestra la burbuja
        más atrasada, las palomitas azules no aparecían nunca en una respuesta de varias burbujas. Al abrir el chat el
        cliente ve todo lo de antes. Nunca baja de estado, nunca toca lo que no llegó («fallido») ni algo avisado
        después."""
        mensaje = parte.mensaje_id
        rango = RANGO_CANAL[estado]
        debajo = [False] + [e for e, r in RANGO_CANAL.items() if r < rango and e != 'fallido']
        Parte = self.env['dcasa.mensaje.parte'].sudo()
        anteriores = Parte.search([
            ('conversacion_id', '=', parte.conversacion_id.id), ('id', '!=', parte.id),
            ('estado_canal', 'in', debajo),
            '|', ('estado_en', '=', False), ('estado_en', '<=', ts),
            '|', ('mensaje_id', '<', mensaje.id), '&', ('mensaje_id', '=', mensaje.id), ('indice', '<', parte.indice),
        ], order='id desc', limit=MAX_PARTES_QUE_SUBEN)
        anteriores = anteriores.filtered(lambda p: p.mensaje_id.direccion == 'saliente')
        if not anteriores:
            return self.browse()
        anteriores.write({'estado_canal': estado, 'estado_en': ts})
        cambiados = self.browse()
        for otro in anteriores.mapped('mensaje_id'):
            if otro._recalcular_estado_canal(ts):
                cambiados |= otro
        return cambiados

    @api.model
    def _aplicar_reaccion(self, mensaje, parte, evento):
        """Una reacción del cliente: la nueva reemplaza a la anterior (una por persona y mensaje); vacía, la quita."""
        destino = parte.sudo() if parte else mensaje
        if destino.reaccion_en and evento['ts'] < destino.reaccion_en:
            return False   # llegó tarde: ya hay una más nueva
        emoji = evento.get('emoji') or False
        if destino.reaccion == emoji and destino.reaccion_en == evento['ts']:
            return False
        if parte:
            parte.sudo().write({'reaccion': emoji, 'reaccion_en': evento['ts']})
            mensaje._recalcular_reaccion()
            return True
        mensaje.with_context(**{CLAVE_SISTEMA: True}).write({'reaccion': emoji, 'reaccion_en': evento['ts']})
        return True

    @api.model
    def marcar_sensible(self, adjunto_ids, valor=True):
        """Una vendedora marca (o desmarca) un adjunto como sensible: comprobante de pago o documento de identidad.

        Un adjunto sensible no se le muestra a la IA. Solo toca la marca; el archivo y el mensaje no cambian.
        """
        self.env['dcasa.conversacion']._exigir_vendedora()
        if not isinstance(adjunto_ids, (list, tuple)) or len(adjunto_ids) > A.MAX_ADJUNTOS * 4 \
                or not all(isinstance(i, int) and not isinstance(i, bool) for i in adjunto_ids):
            raise UserError(self.env._('Pásame la lista de adjuntos a marcar.'))
        # Los mensajes se buscan SIN sudo: solo se marca lo que esa persona puede ver.
        mensajes = self.search([('adjunto_ids', 'in', adjunto_ids)])
        adjuntos = mensajes.sudo().adjunto_ids.filtered(lambda a: a.id in adjunto_ids and a.res_model == self._name)
        adjuntos.write({'dcasa_sensible': bool(valor)})
        for mensaje in mensajes.sudo():
            mensaje.with_context(**{CLAVE_SISTEMA: True}).write(
                {'tiene_sensible': any(mensaje.adjunto_ids.mapped('dcasa_sensible'))})
        return {'marcados': adjuntos.ids, 'sensible': bool(valor)}

    # ------------------------------------------------------------------
    # Verlo como chat
    # ------------------------------------------------------------------

    def _burbuja_html(self, horario):
        """HTML de una burbuja del chat (todo el contenido de terceros va escapado)."""
        self.ensure_one()
        if self.tipo == 'aviso':
            return Markup('<div class="o_dcasa_aviso_sistema">%s</div>') % escape(self.texto or '')
        clase = {'cliente': 'cliente', 'bot': 'bot', 'vendedora': 'vendedora'}[self.autor]
        etiqueta = {
            'cliente': self.partner_id.display_name or self.env._('Cliente'),
            'bot': self.env._('Asistente'),
            'vendedora': self.usuario_id.name or self.env._('Vendedora'),
        }[self.autor]
        if self.tipo == 'nota':
            clase = 'nota'
            etiqueta = self.env._('Nota interna · %s', self.usuario_id.name or self.env._('una vendedora'))
        hora = H.a_local(self.ts, horario).strftime('%d/%m %H:%M')
        partes = [Markup('<div class="o_dcasa_burbuja o_dcasa_burbuja_%s">') % clase,
                  Markup('<div class="o_dcasa_burbuja_meta"><span>%s</span><span>%s</span></div>') % (
                      escape(etiqueta), escape(hora))]
        if self.texto:
            partes.append(Markup('<div class="o_dcasa_burbuja_texto">%s</div>') % _con_saltos(self.texto))
        for adjunto in self.adjunto_ids.sudo():
            partes.append(_adjunto_html(adjunto))
        if self.adjuntos_fallidos:
            partes.append(Markup('<div class="o_dcasa_burbuja_aviso">%s</div>') % escape(
                self.env._('No se pudo traer %s adjunto(s).', self.adjuntos_fallidos)))
        if self.estado_envio == 'programado':
            partes.append(Markup('<div class="o_dcasa_burbuja_estado o_dcasa_por_enviar">%s</div>') % escape(
                self.env._('Programado: sale el %s', hora)))
        elif self.estado_envio == 'por_enviar':
            partes.append(Markup('<div class="o_dcasa_burbuja_estado o_dcasa_por_enviar">%s</div>') % escape(
                self.env._('Por enviar: se reintenta solo')))
        elif self.estado_envio == 'fallido':
            partes.append(Markup('<div class="o_dcasa_burbuja_estado o_dcasa_fallido">%s</div>') % escape(
                self.env._('No se pudo enviar: %s', self.error_envio or '')))
        partes.append(Markup('</div>'))
        return Markup('').join(partes)


def _texto_de_parte(parte):
    """Lo que se ve al citar una burbuja nuestra: su texto; una foto o un documento sin pie, «Foto» o «Documento»."""
    if not parte:
        return ''
    if parte.texto:
        return parte.texto
    return dict(TIPOS_DE_PARTE).get(parte.tipo, '') if parte.tipo != 'texto' else ''


def _con_saltos(texto):
    """Texto escapado con los saltos de línea como <br/>."""
    return Markup('<br/>').join(escape(linea) for linea in (texto or '').split('\n'))


def _adjunto_html(adjunto):
    nombre = escape(adjunto.name or 'adjunto')
    enlace = f'/web/content/{adjunto.id}?download=true'
    etiqueta = ''
    if adjunto.dcasa_sensible:
        etiqueta = Markup('<span class="o_dcasa_sensible">%s</span> ') % escape('Sensible')
    if (adjunto.mimetype or '').startswith('image/'):
        return Markup(
            '<div class="o_dcasa_burbuja_adjunto">%s<a href="%s" target="_blank" rel="noopener">'
            '<img src="/web/image/%s?width=360" alt="%s" loading="lazy"/></a></div>') % (
                etiqueta, enlace, adjunto.id, nombre)
    return Markup(
        '<div class="o_dcasa_burbuja_adjunto">%s<a href="%s" target="_blank" rel="noopener">'
        '<i class="fa fa-paperclip"/> %s</a></div>') % (etiqueta, enlace, nombre)


def adjunto_como_dict(adjunto):
    """Un adjunto para la pantalla: enlace de descarga; si es imagen, miniatura al ancho justo; si es una nota de voz o
    un video, la dirección para escucharlo o verlo ahí mismo (pedido de la dueña, 2026-11-03)."""
    mime = adjunto.mimetype or ''
    tipo = A.tipo_de_mime(mime)
    # Una nota de voz o un video que se guardó sin su tipo (antes del arreglo del 2026-11-03) igual se escucha: el
    # canal dijo qué era («audio», «video») y eso quedó en la descripción.
    if tipo == 'documento' and mime in ('', 'application/octet-stream') and adjunto.description in ('audio', 'video'):
        tipo = adjunto.description
    datos = {
        'id': adjunto.id, 'nombre': adjunto.name, 'mime': mime, 'tipo': tipo,
        'sensible': bool(adjunto.dcasa_sensible), 'tamano': adjunto.file_size or 0,
        'url': f'/web/content/{adjunto.id}?download=true', 'miniatura': None, 'reproducir': None,
    }
    if mime.startswith('image/'):
        datos['miniatura'] = f'/web/image/{adjunto.id}?width=360&height=360'
    elif tipo in ('audio', 'video'):
        datos['reproducir'] = f'/web/content/{adjunto.id}'
    return datos
