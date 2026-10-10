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
from odoo.exceptions import AccessError, UserError
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
            valores = {
                'name': adjunto['nombre'], 'datas': base64.b64encode(contenido), 'res_model': self._name,
                'res_id': self.id, 'public': False, 'description': adjunto['tipo'],
                'dcasa_sensible': bool(adjunto.get('sensible') or sensible_de_oficio),
            }
            if adjunto.get('mime'):
                valores['mimetype'] = adjunto['mime']
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
        canal = dict(CANALES).get(self.canal, self.canal)
        if self.tipo == 'nota':
            usuario = self.usuario_id
            quien = self.env._('Nota interna de %s', usuario.name or self.env._('una vendedora'))
            autor_id = usuario.partner_id.id if usuario else self._partner_del_bot().id
        elif self.autor == 'cliente':
            quien, autor_id = 'Cliente', partner.id
        elif self.autor == 'bot':
            quien, autor_id = self.env._('Asistente'), self._partner_del_bot().id
        else:
            usuario = self.usuario_id
            quien = self.env._('Vendedora %s', usuario.name) if usuario else self.env._('Vendedora (desde el teléfono)')
            autor_id = (usuario.partner_id.id if usuario else self._partner_del_bot().id)
        cuerpo = Markup('<p><strong>%s · %s</strong></p><p>%s</p>') % (
            escape(canal), escape(quien), _con_saltos(self.texto) if self.texto else escape(self.env._('(sin texto)')))
        if self.tiene_sensible:
            cuerpo += Markup('<p><em>%s</em></p>') % escape(self.env._(
                'Adjunto sensible (comprobante o documento): lo revisa una vendedora; no se le muestra a la IA.'))
        if self.adjuntos_fallidos:
            cuerpo += Markup('<p><em>%s</em></p>') % escape(self.env._(
                'No se pudo traer %s adjunto(s) del mensaje.', self.adjuntos_fallidos))
        partner.with_context(mail_post_autofollow=False).message_post(
            body=cuerpo, message_type='comment', subtype_xmlid='mail.mt_note', author_id=autor_id,
            attachment_ids=self.adjunto_ids.ids)

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
            resultado = Cliente.enviar(
                conversacion.canal, conversacion.id_externo, texto=mensaje.texto or None,
                adjuntos=mensaje._datos_adjuntos_para_worker() or None, id_envio=mensaje.id_mensaje)
            intentos = mensaje.intentos + 1
            sistema = mensaje.with_context(**{CLAVE_SISTEMA: True})
            if resultado.get('ok'):
                sistema._marcar_enviado(resultado.get('id_mensaje'))
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

    def _marcar_enviado(self, id_externo):
        """El Worker confirmó el envío. Si ya había registrado su propio eco con ese id, se fusionan."""
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
                eco.write({
                    'estado_envio': 'enviado', 'usuario_id': self.usuario_id.id, 'origen': 'odoo',
                    'adjunto_ids': [(4, a.id) for a in self.adjunto_ids],
                    'tiene_sensible': self.tiene_sensible or eco.tiene_sensible})
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
        }

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
    """Un adjunto para la pantalla: enlace de descarga y, si es imagen, miniatura al ancho justo."""
    mime = adjunto.mimetype or ''
    datos = {
        'id': adjunto.id, 'nombre': adjunto.name, 'mime': mime, 'tipo': A.tipo_de_mime(mime),
        'sensible': bool(adjunto.dcasa_sensible), 'tamano': adjunto.file_size or 0,
        'url': f'/web/content/{adjunto.id}?download=true', 'miniatura': None,
    }
    if mime.startswith('image/'):
        datos['miniatura'] = f'/web/image/{adjunto.id}?width=360&height=360'
    return datos
