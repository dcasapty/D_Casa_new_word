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
from odoo.exceptions import AccessError

from . import adjuntos as A
from . import horario as H
from .ajustes import CANALES

_logger = logging.getLogger(__name__)

DIRECCIONES = [('entrante', 'Entrante'), ('saliente', 'Saliente')]
AUTORES = [('cliente', 'Cliente'), ('bot', 'Asistente'), ('vendedora', 'Vendedora')]
ESTADOS_ENVIO = [
    ('recibido', 'Recibido'),
    ('por_enviar', 'Por enviar'),
    ('enviado', 'Enviado'),
    ('fallido', 'No se pudo enviar'),
]
MAX_INTENTOS = 12                       # con el cron cada 5 min: ~1 hora de reintentos
EDAD_MINIMA_REINTENTO = timedelta(minutes=2)
VENTANA_ADOPCION = timedelta(minutes=15)
CLAVE_SISTEMA = 'dcasa_mensaje_sistema'


class DcasaMensaje(models.Model):
    _name = 'dcasa.mensaje'
    _description = 'Mensaje de una conversación'
    _order = 'ts, id'
    _rec_name = 'id_mensaje'

    conversacion_id = fields.Many2one('dcasa.conversacion', required=True, ondelete='cascade', index=True,
                                      readonly=True)
    partner_id = fields.Many2one(related='conversacion_id.partner_id', store=True, index=True)
    canal = fields.Selection(related='conversacion_id.canal', store=True, index=True)
    direccion = fields.Selection(DIRECCIONES, required=True, readonly=True)
    autor = fields.Selection(AUTORES, required=True, readonly=True, index=True)
    id_mensaje = fields.Char('Id del mensaje', required=True, readonly=True, index=True,
                             help='Lo asigna el canal (o el Worker). Es la llave de la idempotencia.')
    texto = fields.Text(readonly=True)
    ts = fields.Datetime('Fecha', required=True, readonly=True, default=fields.Datetime.now, index=True)
    adjunto_ids = fields.Many2many('ir.attachment', 'dcasa_mensaje_adjunto_rel', 'mensaje_id', 'adjunto_id',
                                   string='Adjuntos', readonly=True)
    adjuntos_fallidos = fields.Integer('Adjuntos que no se pudieron traer', readonly=True)
    tiene_sensible = fields.Boolean('Adjunto sensible', readonly=True,
                                    help='Comprobante de pago o documento de identidad: no se le muestra a la IA.')
    origen = fields.Selection([('canal', 'Del canal'), ('odoo', 'Escrito en Odoo')], default='canal', readonly=True,
                              required=True)
    usuario_id = fields.Many2one('res.users', 'Escrito por', readonly=True,
                                 help='La vendedora que lo escribió en Odoo.')
    estado_envio = fields.Selection(ESTADOS_ENVIO, default='recibido', required=True, readonly=True, index=True)
    intentos = fields.Integer(readonly=True)
    ultimo_intento = fields.Datetime(readonly=True)
    error_envio = fields.Char('Por qué no salió', readonly=True)

    _id_mensaje_unico = models.Constraint(
        'UNIQUE(conversacion_id, id_mensaje)', 'Ese mensaje ya está registrado en la conversación.')
    _direccion_autor = models.Constraint(
        "CHECK((direccion = 'entrante' AND autor = 'cliente') "
        "OR (direccion = 'saliente' AND autor IN ('bot', 'vendedora')))",
        'Un mensaje entrante es del cliente; uno saliente, del asistente o de una vendedora.')

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
        creados, fallidos, sensible = Adjunto, 0, False
        for adjunto in adjuntos:
            contenido = A.obtener_contenido(adjunto)
            if not contenido:
                fallidos += 1
                continue
            es_sensible = bool(adjunto.get('sensible') or sensible_de_oficio)
            valores = {
                'name': adjunto['nombre'], 'datas': base64.b64encode(contenido), 'res_model': self._name,
                'res_id': self.id, 'public': False, 'description': adjunto['tipo'],
            }
            if adjunto.get('mime'):
                valores['mimetype'] = adjunto['mime']
            creados |= Adjunto.create(valores)
            if es_sensible:
                creados[-1].dcasa_sensible = True
                sensible = True
        self.with_context(**{CLAVE_SISTEMA: True}).sudo().write({
            'adjunto_ids': [(4, a.id) for a in creados], 'adjuntos_fallidos': fallidos,
            'tiene_sensible': sensible})
        return creados

    # ------------------------------------------------------------------
    # Chatter del cliente
    # ------------------------------------------------------------------

    def _publicar_en_chatter(self):
        """Deja el mensaje en el chatter de la ficha del cliente (nota interna, no avisa a nadie)."""
        self.ensure_one()
        partner = self.partner_id.sudo()
        if not partner:
            return
        canal = dict(CANALES).get(self.canal, self.canal)
        if self.autor == 'cliente':
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
        """Los adjuntos como los espera ``POST /odoo/enviar``: ``{tipo, url, nombre, mime}``."""
        self.ensure_one()
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        resultado = []
        for adjunto in self.adjunto_ids.sudo():
            token = adjunto.generate_access_token()[0]
            resultado.append({
                'tipo': A.tipo_de_mime(adjunto.mimetype), 'nombre': adjunto.name, 'mime': adjunto.mimetype or '',
                'url': f'{base}/web/content/{adjunto.id}?access_token={token}&download=true',
            })
        return resultado

    def _enviar(self):
        """Intenta mandar cada mensaje «por enviar» por el Worker. Devuelve cuántos salieron."""
        salieron = 0
        Cliente = self.env['dcasa.juan.cliente']
        ahora = fields.Datetime.now()
        for mensaje in self.sudo().filtered(lambda m: m.estado_envio == 'por_enviar'):
            conversacion = mensaje.conversacion_id
            resultado = Cliente.enviar(
                conversacion.canal, conversacion.id_externo, texto=mensaje.texto or None,
                adjuntos=mensaje._datos_adjuntos_para_worker() or None)
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
    # Verlo como chat
    # ------------------------------------------------------------------

    def _burbuja_html(self, horario):
        """HTML de una burbuja del chat (todo el contenido de terceros va escapado)."""
        self.ensure_one()
        clase = {'cliente': 'cliente', 'bot': 'bot', 'vendedora': 'vendedora'}[self.autor]
        etiqueta = {
            'cliente': self.partner_id.display_name or self.env._('Cliente'),
            'bot': self.env._('Asistente'),
            'vendedora': self.usuario_id.name or self.env._('Vendedora'),
        }[self.autor]
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
        if self.estado_envio == 'por_enviar':
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
