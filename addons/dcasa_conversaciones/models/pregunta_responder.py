"""«Contestar» una pregunta sin respuesta (decisión de la dueña, 2026-11-09: las vendedoras también las contestan).

Una vendedora (o Gerencia) escribe la respuesta como se la diría al cliente y el asistente la aprende:

* Si ni la respuesta ni el título mencionan dinero, números (también en palabras) ni un tema de política (garantía,
  devoluciones, entregas, crédito, apartados, descuentos; ``conocimiento_texto.necesita_revision``): se crea la entrada
  de conocimiento ACTIVA al instante y la pregunta queda «atendida».
* Si lo mencionan y la escribe una vendedora: NO se activa. Queda en la pregunta como «Lo que contestó una vendedora» y
  Gerencia la convierte en entrada con el botón de siempre (nace como borrador inactivo para que la confirme). Así
  ninguna cifra ni política llega al cliente sin que Gerencia la vea (reglas de la casa: no se inventan cifras ni
  políticas). El título cuenta: la pregunta del cliente puede traer un precio («¿me la dejan en $750?») y un «sí»
  bastaría para confirmarlo (revisión adversarial 2026-11-09).
* Gerencia contesta directo: es quien confirma las cifras.

La vendedora no gana permisos sobre los modelos: no escribe preguntas ni crea entradas por su cuenta (ACL de solo
lectura). Este asistente valida y escribe con sudo solo lo de arriba, con un contexto limpio (nada de lo que mande quien
llama, p. ej. ``tracking_disable``, apaga el historial).
"""
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import conocimiento_texto as C
from .conocimiento import GRUPO_GERENCIA, MAX_CONTENIDO

GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
MAX_TITULO = 200


class DcasaPreguntaResponder(models.TransientModel):
    _name = 'dcasa.pregunta.responder'
    _description = 'Contestar una pregunta sin respuesta'

    pregunta_id = fields.Many2one('dcasa.pregunta_pendiente', 'Pregunta', required=True, readonly=True,
                                  ondelete='cascade')
    pregunta_texto = fields.Text('Lo que preguntaron', related='pregunta_id.texto')
    pregunta_resumen = fields.Text('Contexto', related='pregunta_id.resumen')
    titulo = fields.Char('Tema', compute='_compute_titulo', store=True, readonly=False, required=True, precompute=True,
                         help='Cómo se llama el tema para el asistente. Viene de la pregunta: quítale nombres, '
                              'números o lo que sea solo de ese cliente.')
    respuesta = fields.Text('Tu respuesta', required=True,
                            help='Escríbela como se la dirías al cliente, de tú. El asistente la usará con otros '
                                 'clientes que pregunten lo mismo.')
    es_gerencia = fields.Boolean(compute='_compute_es_gerencia')

    @api.depends('pregunta_id')
    def _compute_titulo(self):
        for asistente in self:
            if not asistente.titulo and asistente.pregunta_id:
                asistente.titulo = C.limpiar_respuesta(' '.join((asistente.pregunta_id.texto or '').split()),
                                                       MAX_TITULO)

    @api.depends_context('uid')
    def _compute_es_gerencia(self):
        gerencia = self.env.user.has_group(GRUPO_GERENCIA)
        for asistente in self:
            asistente.es_gerencia = gerencia

    def action_guardar(self):
        """Guarda la respuesta. Exige el grupo de ventas; la pregunta tiene que seguir «nueva»."""
        self.ensure_one()
        usuario = self.env.user
        if not usuario.has_group(GRUPO_VENDEDORA):
            raise AccessError(self.env._('Solo el equipo de ventas contesta las preguntas sin respuesta.'))
        # Contexto limpio: lo que mande quien llama (tracking_disable, mail_create_nolog…) no apaga el historial.
        limpio = self.with_context({'lang': self.env.lang})
        pregunta = limpio.pregunta_id.sudo()
        if pregunta.estado != 'nueva':
            raise UserError(self.env._('Alguien ya atendió esta pregunta: recarga la lista.'))
        texto = (self.respuesta or '').strip()
        titulo = C.limpiar_respuesta(' '.join((self.titulo or '').split()), MAX_TITULO)
        if not texto:
            raise UserError(self.env._('Escribe la respuesta antes de guardar.'))
        if not titulo:
            raise UserError(self.env._('Ponle un tema (por ejemplo, la pregunta en pocas palabras).'))
        if len(texto) > MAX_CONTENIDO:
            raise UserError(self.env._('La respuesta admite hasta %s caracteres.', MAX_CONTENIDO))
        gerencia = usuario.has_group(GRUPO_GERENCIA)
        revisar = C.necesita_revision(titulo) or C.necesita_revision(texto)
        propuesta = {'respuesta_vendedora': texto, 'respuesta_de_id': usuario.id,
                     'respuesta_en': fields.Datetime.now(), 'respuesta_con_cifras': revisar}
        if revisar and not gerencia:
            # Gerencia la revisa: queda como propuesta en la pregunta (sigue «nueva»). El texto va también al
            # historial: si otra vendedora propone otra cosa después, la primera no se pierde.
            pregunta.write(propuesta)
            pregunta.message_post(body=Markup('{} <blockquote>{}</blockquote>').format(
                self.env._('%s la contestó. Menciona dinero, números o un tema de política: Gerencia la revisa antes '
                           'de que el asistente la use.', usuario.name), escape(texto)))
            return self._aviso(self.env._(
                'Guardada. Como menciona dinero, números o un tema de política (garantía, entregas, crédito…), '
                'Gerencia la revisa antes de que el asistente la use.'))
        entrada = limpio.env['dcasa.conocimiento'].sudo().create({
            'titulo': titulo,
            'contenido': texto,
            'pregunta_id': pregunta.id,   # al crearse, la pregunta queda «atendida» y enlazada
            'activo': True,
            'autor_id': usuario.id,
            'nota': self.env._('La contestó %s desde «Preguntas sin respuesta».', usuario.name),
        })
        pregunta.write(propuesta)
        pregunta.message_post(body=Markup('{} <blockquote>{}</blockquote>').format(
            self.env._('%(quien)s la contestó y el asistente ya la usa (entrada «%(titulo)s»).',
                       quien=usuario.name, titulo=entrada.titulo), escape(texto)))
        return self._aviso(self.env._('Listo: el asistente ya sabe contestar esa pregunta.'))

    def _aviso(self, texto):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': texto, 'type': 'success', 'sticky': False,
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
