"""Comentarios de Instagram y Facebook que atendió Juan (2026-11-12).

Decisiones de la dueña (tal cual): «Solo los que preguntan» (precio, medidas, colores, disponibilidad, envío o interés
de compra; las quejas no se contestan: avisan a Gerencia), «Corto y lo demás por privado» y «Apagado hasta que lo
pruebes» (Ajustes de Juan › Comentarios de Instagram y Facebook).

El Worker decide y contesta (``juan/src/motor/conversacion.ts``); aquí queda el registro:

* Un **aviso en el hilo** de la conversación de esa persona (se crea si no existe, como con un mensaje): «Comentó en una
  publicación de Instagram: "…" · Juan le respondió en público y por privado», con el enlace a la publicación si viene.
  Una pregunta llega dos veces (``POST /dcasa/juan/v1/comentario``): con ``privada = pendiente`` ANTES de contestar
  (así el aviso queda antes de la respuesta en el hilo y la conversación existe para las herramientas) y con el
  resultado al final, que pone al día el mismo aviso. Si la IA u Odoo fallan, en medio puede llegar ``reintento``
  (Juan lo vuelve a intentar en un rato). Idempotente por ``red`` + ``id_comentario``; un resultado final no se pisa.
* Una **queja**: el aviso («Queja en un comentario: … · no se respondió») y Telegram a Gerencia (el mismo mecanismo de
  siempre; si a nadie de Gerencia le llega, a quienes reciben los avisos de Juan).
* El comentario no es un mensaje del cliente: no abre la ventana de 24 h, no cuenta como «el cliente escribió» ni
  dispara seguimientos. La respuesta privada de Juan sí es un mensaje (llega por ``/mensaje``, como cualquier otro).

Es un dato personal (lo que escribió la persona): se borra con la conversación (Ley 81).
"""
import logging

from odoo import api, fields, models

from .mensaje import CLAVE_SISTEMA

_logger = logging.getLogger(__name__)

REDES = [('facebook', 'Facebook'), ('instagram', 'Instagram')]
CLASES = [('pregunta', 'Pregunta'), ('queja', 'Queja'), ('sin_clasificar', 'Sin clasificar (falló la IA)')]
RESPUESTA_PRIVADA = [
    ('pendiente', 'Preparándose'), ('reintento', 'Juan lo vuelve a intentar'), ('respondida', 'Respondida'),
    ('fallo', 'Meta no la dejó salir'), ('no_preparada', 'Juan no pudo prepararla'),
    ('incierta', 'No se sabe si llegó'), ('vendedora', 'No: la atiende una persona'), ('no', 'No se responde'),
]
# Lo que todavía puede cambiar (Juan sigue con ese comentario); lo demás es un resultado final y no se pisa.
PRIVADA_EN_CURSO = ('pendiente', 'reintento')
RESPUESTA_PUBLICA = [
    ('pendiente', 'Preparándose'), ('respondida', 'Respondida'), ('fallo', 'Meta no la dejó salir'),
    ('incierta', 'No se sabe si salió'), ('tope', 'No: tope por hora'), ('no', 'No se responde'),
]
MAX_TEXTO_EN_EL_AVISO = 300


class DcasaComentario(models.Model):
    _name = 'dcasa.comentario'
    _description = 'Comentario de Instagram o Facebook que atendió Juan'
    _order = 'ts desc, id desc'
    _rec_name = 'id_comentario'

    conversacion_id = fields.Many2one('dcasa.conversacion', 'Conversación', required=True, readonly=True,
                                      ondelete='cascade', index=True)
    red = fields.Selection(REDES, required=True, readonly=True)
    id_comentario = fields.Char('Id del comentario en Meta', required=True, readonly=True)
    texto = fields.Text('Lo que comentó', readonly=True)
    enlace = fields.Char('Publicación', readonly=True)
    ts = fields.Datetime('Comentó el', required=True, readonly=True)
    clase = fields.Selection(CLASES, required=True, readonly=True)
    privada = fields.Selection(RESPUESTA_PRIVADA, 'Respuesta privada', required=True, readonly=True)
    publica = fields.Selection(RESPUESTA_PUBLICA, 'Respuesta pública', required=True, readonly=True)
    motivo = fields.Char('Por qué no salió', readonly=True)
    aviso_id = fields.Many2one('dcasa.mensaje', 'Aviso en el hilo', readonly=True, ondelete='set null')

    # Nadie lo edita a mano: el equipo de ventas solo lo lee (ir.model.access.csv) y lo escribe el sistema (con sudo).
    _comentario_unico = models.Constraint('UNIQUE(red, id_comentario)', 'Ese comentario ya está registrado.')

    # ------------------------------------------------------------------
    # Registrar (lo usa la API; privado: escribe con sudo)
    # ------------------------------------------------------------------

    @api.model
    def _registrar(self, datos):
        """Registra un comentario (o pone al día su resultado). Devuelve ``(comentario, que)`` con ``que`` en
        ``creado``, ``actualizado`` o ``repetido``.

        ``datos`` (ya validados por la API): ``canal, id_externo, nombre, red, id_comentario, texto, enlace, ts, clase,
        privada, publica, motivo``.
        """
        Conversacion = self.env['dcasa.conversacion'].sudo()
        Conversacion._bloquear(datos['canal'], datos['id_externo'])
        Comentario = self.sudo().with_context(**{CLAVE_SISTEMA: True})
        existente = Comentario.search([('red', '=', datos['red']), ('id_comentario', '=', datos['id_comentario'])],
                                      limit=1)
        if existente:
            if existente.privada in PRIVADA_EN_CURSO and datos['privada'] != 'pendiente' and (
                    datos['privada'] != existente.privada or (datos.get('motivo') or False) != existente.motivo):
                existente._poner_resultado(datos)
                return existente, 'actualizado'
            return existente, 'repetido'
        conv, _creada = Conversacion._obtener_o_crear(datos['canal'], datos['id_externo'], datos.get('nombre'), None,
                                                      datos['ts'])
        comentario = Comentario.create({
            'conversacion_id': conv.id, 'red': datos['red'], 'id_comentario': datos['id_comentario'],
            'texto': datos.get('texto') or False, 'enlace': datos.get('enlace') or False, 'ts': datos['ts'],
            'clase': datos['clase'], 'privada': datos['privada'], 'publica': datos['publica'],
            'motivo': datos.get('motivo') or False,
        })
        aviso = self.env['dcasa.mensaje']._crear_interno(conv, 'aviso', comentario._texto_del_aviso(),
                                                         enlace=comentario.enlace or None)
        comentario.write({'aviso_id': aviso.id})
        ahora = fields.Datetime.now()
        valores = {'ultima_actividad': max(conv.ultima_actividad or ahora, ahora)}
        if not conv.ultimo_mensaje_texto:
            valores['ultimo_mensaje_texto'] = (aviso.texto or '')[:140]
        conv.write(valores)
        if comentario.clase == 'queja':
            comentario._avisar_queja_a_gerencia()
        conv._notificar_panel('mensaje', aviso)
        return comentario, 'creado'

    def _poner_resultado(self, datos):
        """El resultado final de una pregunta: en el registro y en el MISMO aviso del hilo (que ya estaba antes de la
        respuesta de Juan)."""
        self.ensure_one()
        cambios = {'privada': datos['privada'], 'publica': datos['publica'], 'motivo': datos.get('motivo') or False}
        if datos.get('enlace') and not self.enlace:
            cambios['enlace'] = datos['enlace']
        self.sudo().with_context(**{CLAVE_SISTEMA: True}).write(cambios)
        if self.aviso_id:
            self.aviso_id.sudo().with_context(**{CLAVE_SISTEMA: True}).write(
                {'texto': self._texto_del_aviso(), 'enlace': self.enlace or False})
            self.conversacion_id._notificar_panel('mensaje', self.aviso_id)

    # ------------------------------------------------------------------
    # El aviso en el hilo y el de Gerencia
    # ------------------------------------------------------------------

    def _lo_que_dijo(self):
        self.ensure_one()
        texto = ' '.join((self.texto or '').split())
        return texto if len(texto) <= MAX_TEXTO_EN_EL_AVISO else f'{texto[:MAX_TEXTO_EN_EL_AVISO - 1]}…'

    def _texto_del_aviso(self):
        """La línea del hilo, en palabras sencillas (decisión de la dueña): qué comentó y qué hizo Juan."""
        self.ensure_one()
        red, dicho = dict(REDES)[self.red], self._lo_que_dijo()
        if self.clase == 'queja':
            return self.env._('Queja en un comentario de %(red)s: "%(dicho)s" · no se respondió. Se avisó a Gerencia.',
                              red=red, dicho=dicho)
        inicio = self.env._('Comentó en una publicación de %(red)s: "%(dicho)s"', red=red, dicho=dicho)
        return f'{inicio} · {self._que_hizo_juan()}'

    def _que_hizo_juan(self):
        self.ensure_one()
        motivo = f' ({self.motivo})' if self.motivo else ''
        if self.clase == 'sin_clasificar':
            return self.env._('Juan no pudo saber si era una pregunta (falló la IA%s) y no le respondió. Si hace '
                              'falta, contéstale tú.', f': {self.motivo}' if self.motivo else '')
        privada, publica = self.privada, self.publica
        if privada == 'pendiente':
            return self.env._('Juan le está respondiendo.')
        if privada == 'reintento':
            return self.env._('Juan todavía no pudo prepararle la respuesta%s y lo vuelve a intentar en un rato. Si es '
                              'urgente, contéstale tú desde Meta Business Suite.', motivo)
        if privada == 'respondida':
            return {
                'respondida': self.env._('Juan le respondió en público y por privado.'),
                'tope': self.env._('Juan le respondió por privado; en público no, porque ya iban las respuestas '
                                   'públicas de esta hora (el tope de Ajustes de Juan).'),
                'fallo': self.env._('Juan le respondió por privado; en público no salió%s.', motivo),
                'incierta': self.env._('Juan le respondió por privado; no se sabe si salió la respuesta pública.'),
                'no': self.env._('Juan le respondió por privado; en público no%s.', motivo),
            }.get(publica, self.env._('Juan le respondió por privado.'))
        if privada == 'fallo':
            return self.env._('Meta no dejó responderle por privado%s y en público tampoco se le respondió. '
                              'Contéstale tú desde Meta Business Suite.', motivo)
        if privada == 'no_preparada':
            return self.env._('Juan no pudo prepararle la respuesta%s, ni en los reintentos; en público tampoco se le '
                              'respondió. Contéstale tú desde Meta Business Suite.', motivo)
        if privada == 'incierta':
            return self.env._('Juan empezó a responderle por privado, pero no se sabe si le llegó; en público no se le '
                              'respondió. Revísalo en Meta Business Suite.')
        if privada == 'vendedora':
            return self.env._('No se le respondió porque una persona del equipo atiende esta conversación: '
                              'contéstale tú.')
        return self.env._('No se le respondió%s.', motivo)

    def _avisar_queja_a_gerencia(self):
        """Telegram a Gerencia (el mismo mecanismo de los avisos de siempre); si a nadie de Gerencia le llega, a quienes
        reciben los avisos de Juan. Sin el botón «Atender»: por mensaje no se le puede escribir a quien solo comentó.
        Nunca rompe el registro."""
        self.ensure_one()
        conv = self.conversacion_id.sudo()
        try:
            with self.env.cr.savepoint():
                quien = conv.partner_id.display_name or conv.id_externo
                texto = self.env._(
                    'Para Gerencia: queja en un comentario de %(red)s de %(quien)s: "%(dicho)s". Juan no la respondió. '
                    'Está en Conversaciones.', red=dict(REDES)[self.red], quien=quien, dicho=self._lo_que_dijo())
                if self.enlace:
                    texto = f'{texto}\n{self.enlace}'
                gerencia = self.env['dcasa.reparto']._gerencia_que_recibe_avisos()
                enviados = conv._avisar_por_telegram(texto, usuarios=gerencia) if gerencia else 0
                if not enviados:
                    conv._avisar_por_telegram(texto)
        except Exception:   # noqa: BLE001 — un aviso nunca tumba el registro
            _logger.exception('Juan: no se pudo avisar a Gerencia de la queja en un comentario (%s)', self.id)
