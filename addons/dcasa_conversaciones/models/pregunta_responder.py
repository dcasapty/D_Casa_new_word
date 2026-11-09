"""«Contestar» una pregunta sin respuesta (decisión de la dueña, 2026-11-09: las vendedoras también las contestan).

Una vendedora (o Gerencia) escribe la respuesta como se la diría al cliente y el asistente la aprende:

* Sin números ni dinero: se crea la entrada de conocimiento ACTIVA al instante y la pregunta queda «atendida».
* Con números o dinero (precios, plazos, horarios, porcentajes) y la escribe una vendedora: NO se activa. Queda en la
  pregunta como «Lo que contestó una vendedora» y Gerencia la convierte en entrada con el botón de siempre (nace como
  borrador inactivo para que confirme las cifras). Así ninguna cifra llega al cliente sin que Gerencia la vea
  (regla de la casa: no se inventan cifras).
* Gerencia contesta directo, con o sin cifras: es quien las confirma.

La vendedora no gana permisos sobre los modelos: no escribe preguntas ni crea entradas por su cuenta (ACL de solo
lectura). Este asistente valida y escribe con sudo solo lo de arriba.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import conocimiento_texto as C
from .conocimiento import GRUPO_GERENCIA, MAX_CONTENIDO

GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'


class DcasaPreguntaResponder(models.TransientModel):
    _name = 'dcasa.pregunta.responder'
    _description = 'Contestar una pregunta sin respuesta'

    pregunta_id = fields.Many2one('dcasa.pregunta_pendiente', 'Pregunta', required=True, readonly=True,
                                  ondelete='cascade')
    pregunta_texto = fields.Text('Lo que preguntaron', related='pregunta_id.texto')
    pregunta_resumen = fields.Text('Contexto', related='pregunta_id.resumen')
    respuesta = fields.Text('Tu respuesta', required=True,
                            help='Escríbela como se la dirías al cliente, de tú. El asistente la usará con otros '
                                 'clientes que pregunten lo mismo.')
    es_gerencia = fields.Boolean(compute='_compute_es_gerencia')

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
        pregunta = self.pregunta_id.sudo()
        if pregunta.estado != 'nueva':
            raise UserError(self.env._('Alguien ya atendió esta pregunta: recarga la lista.'))
        texto = (self.respuesta or '').strip()
        if not texto:
            raise UserError(self.env._('Escribe la respuesta antes de guardar.'))
        if len(texto) > MAX_CONTENIDO:
            raise UserError(self.env._('La respuesta admite hasta %s caracteres.', MAX_CONTENIDO))
        gerencia = usuario.has_group(GRUPO_GERENCIA)
        if C.tiene_cifras(texto) and not gerencia:
            # Las cifras las confirma Gerencia: queda como propuesta en la pregunta (sigue «nueva»).
            pregunta.write({'respuesta_vendedora': texto, 'respuesta_de_id': usuario.id,
                            'respuesta_en': fields.Datetime.now(), 'respuesta_con_cifras': True})
            pregunta.message_post(body=self.env._(
                '%s la contestó. Menciona números o dinero: Gerencia la revisa antes de que el asistente la use.',
                usuario.name))
            return self._aviso(self.env._(
                'Guardada. Como menciona números o dinero, Gerencia la revisa antes de que el asistente la use.'))
        entrada = self.env['dcasa.conocimiento'].sudo().create({
            'titulo': ' '.join(pregunta.texto.split())[:200],
            'contenido': texto,
            'pregunta_id': pregunta.id,   # al crearse, la pregunta queda «atendida» y enlazada
            'activo': True,
            'autor_id': usuario.id,
            'nota': self.env._('La contestó %s desde «Preguntas sin respuesta».', usuario.name),
        })
        pregunta.write({'respuesta_vendedora': texto, 'respuesta_de_id': usuario.id,
                        'respuesta_en': fields.Datetime.now(), 'respuesta_con_cifras': C.tiene_cifras(texto)})
        pregunta.message_post(body=self.env._('%(quien)s la contestó y el asistente ya la usa (entrada «%(titulo)s»).',
                                              quien=usuario.name, titulo=entrada.titulo))
        return self._aviso(self.env._('Listo: el asistente ya sabe contestar esa pregunta.'))

    def _aviso(self, texto):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': texto, 'type': 'success', 'sticky': False,
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
