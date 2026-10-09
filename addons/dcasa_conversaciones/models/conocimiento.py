"""Base de conocimiento del asistente y el ciclo de aprendizaje.

* ``dcasa.conocimiento``: lo que el equipo quiere que el asistente sepa y diga (título, contenido, etiquetas).
  Gerencia lo edita. El asistente lo consulta con la herramienta ``buscar_conocimiento``: las 3 mejores
  coincidencias (búsqueda por palabras, sin vectores; ver ``conocimiento_texto.py``) y solo las entradas activas.
* ``dcasa.pregunta_pendiente``: lo que un cliente preguntó y el asistente no supo contestar. Las iguales o muy
  parecidas se agrupan y suman un contador. Con UN botón («Convertir en conocimiento») la dueña abre el
  formulario ya con la pregunta, escribe la respuesta y la entrada queda lista: ese es el ciclo de aprendizaje.

Reglas:
* **No se inventan políticas**: las entradas de garantía y de cómo se hace una compra vienen **inactivas** y marcadas
  «pendiente de aprobación de la dueña»; nada de entregas, flete, financiamiento ni apartados (siempre lo
  confirma una vendedora).
* **Ninguna cifra duplicada**: las entradas «automáticas» no guardan texto: lo arman al consultarse con los datos
  vivos de la tienda y con las reglas de Socios de ``puntos.json``. Así no pueden quedarse viejas.
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.exceptions import AccessError, ValidationError

from . import conocimiento_texto as C
from .reglas_clientes import redactar
from .tienda import datos_tienda, texto_tienda, url_base

GRUPO_GERENCIA = 'sales_team.group_sale_manager'
FUENTES = [
    ('manual', 'Escrito a mano'),
    ('tienda', 'Datos de la tienda (automático)'),
    ('socios', 'Reglas de Socios (automático, de puntos.json)'),
]
MAX_CONTENIDO = 5000
MAX_PREGUNTA = 500
REPETICION_MISMA_CONVERSACION = timedelta(hours=1)
PREGUNTAS_A_COMPARAR = 300


def exigir_gerencia(env):
    if not env.su and not env.user.has_group(GRUPO_GERENCIA):
        raise AccessError(env._('Solo Gerencia mantiene el conocimiento del asistente.'))


class DcasaConocimiento(models.Model):
    _name = 'dcasa.conocimiento'
    _description = 'Conocimiento del asistente'
    _inherit = ['mail.thread']
    _order = 'activo desc, titulo'

    titulo = fields.Char('Título', required=True, tracking=True,
                         help='Cómo se llama el tema, p. ej. «Dónde estamos y cómo llegar».')
    fuente = fields.Selection(FUENTES, 'Origen del texto', default='manual', required=True)
    contenido = fields.Text('Contenido', tracking=True,
                            help='Lo que el asistente puede decir sobre el tema, en tus palabras y con tuteo.')
    contenido_vigente = fields.Text('Contenido que usa el asistente', compute='_compute_contenido_vigente')
    etiquetas = fields.Char('Etiquetas', help='Palabras con las que la gente lo pregunta, separadas por comas: '
                                              'horario, dirección, ubicación…')
    activo = fields.Boolean('Activo', default=True, tracking=True, index=True,
                            help='Solo las entradas activas las consulta el asistente.')
    ultima_revision = fields.Date('Última revisión', default=fields.Date.context_today)
    autor_id = fields.Many2one('res.users', 'Autor', default=lambda self: self.env.user, ondelete='set null')
    nota = fields.Text('Nota interna', help='Para el equipo; el asistente no la ve.')
    pregunta_id = fields.Many2one('dcasa.pregunta_pendiente', 'Nació de la pregunta', copy=False, readonly=True,
                                  ondelete='set null', index='btree_not_null')

    # ------------------------------------------------------------------
    # Contenido
    # ------------------------------------------------------------------

    @api.depends('fuente', 'contenido')
    def _compute_contenido_vigente(self):
        for entrada in self:
            if entrada.fuente == 'socios':
                base = url_base(self.env)
                entrada.contenido_vigente = '\n'.join(redactar(R.cargar_reglas(), base)['resumen'])
            elif entrada.fuente == 'tienda':
                entrada.contenido_vigente = texto_tienda(datos_tienda(self.env))
            else:
                entrada.contenido_vigente = entrada.contenido or ''

    @api.constrains('fuente', 'contenido')
    def _check_contenido(self):
        for entrada in self:
            if entrada.fuente == 'manual' and not (entrada.contenido or '').strip():
                raise ValidationError(self.env._('Escribe qué debe decir el asistente sobre «%s».', entrada.titulo))
            if len(entrada.contenido or '') > MAX_CONTENIDO:
                raise ValidationError(self.env._(
                    'El contenido admite hasta %s caracteres: parte el tema en dos entradas.', MAX_CONTENIDO))

    @api.model_create_multi
    def create(self, vals_list):
        entradas = super().create(vals_list)
        for entrada in entradas.filtered('pregunta_id'):
            # Nació de una pregunta sin respuesta: la pregunta queda atendida y enlazada.
            entrada.pregunta_id.sudo().write({'estado': 'atendida', 'conocimiento_id': entrada.id})
        return entradas

    def write(self, vals):
        if {'titulo', 'contenido', 'etiquetas', 'activo', 'fuente'} & set(vals) and 'ultima_revision' not in vals:
            vals = {**vals, 'ultima_revision': fields.Date.context_today(self)}
        return super().write(vals)

    def action_activar(self):
        exigir_gerencia(self.env)
        self.write({'activo': True})
        return True

    def action_desactivar(self):
        exigir_gerencia(self.env)
        self.write({'activo': False})
        return True

    # ------------------------------------------------------------------
    # Búsqueda (la usa la herramienta del asistente)
    # ------------------------------------------------------------------

    @api.model
    def _buscar(self, consulta, limite=3):
        """Las mejores ``limite`` entradas ACTIVAS para la consulta: ``[(entrada, puntos), …]``.

        Se puntúa en Python sobre título + etiquetas + contenido (sin acentos ni plural): no depende de la
        extensión ``unaccent`` de la base y las entradas automáticas se arman al momento.
        """
        puntuadas = []
        for entrada in self.sudo().search([('activo', '=', True)]):
            puntos = C.puntuar(consulta, entrada.titulo, entrada.etiquetas or '', entrada.contenido_vigente or '')
            if puntos:
                puntuadas.append((-puntos, entrada.titulo, entrada.id, entrada, puntos))
        puntuadas.sort(key=lambda t: t[:3])
        return [(t[3], t[4]) for t in puntuadas[:max(1, limite)]]


class DcasaPreguntaPendiente(models.Model):
    _name = 'dcasa.pregunta_pendiente'
    _description = 'Pregunta sin respuesta'
    _inherit = ['mail.thread']
    _order = 'estado, veces desc, ultima_vez desc, id desc'

    name = fields.Char('Pregunta', compute='_compute_name', store=True)
    texto = fields.Text('Cómo la preguntaron', required=True, readonly=True,
                        help='La primera vez que alguien la hizo, con sus palabras.')
    clave = fields.Char(index=True, readonly=True)
    veces = fields.Integer('Veces que se repite', default=1, readonly=True)
    estado = fields.Selection([('nueva', 'Nueva'), ('atendida', 'Atendida'), ('descartada', 'Descartada')],
                              default='nueva', required=True, index=True, tracking=True)
    ultima_vez = fields.Datetime('Última vez', default=fields.Datetime.now, readonly=True)
    resumen = fields.Text('Contexto', readonly=True, help='Lo que el asistente entendió de la conversación.')
    conversacion_id = fields.Many2one('dcasa.conversacion', 'Última conversación', readonly=True, ondelete='set null')
    conversacion_ids = fields.Many2many('dcasa.conversacion', 'dcasa_pregunta_conversacion_rel', 'pregunta_id',
                                        'conversacion_id', string='Conversaciones', readonly=True)
    conocimiento_id = fields.Many2one('dcasa.conocimiento', 'Entrada de conocimiento', readonly=True,
                                      ondelete='set null')

    @api.depends('texto')
    def _compute_name(self):
        for pregunta in self:
            texto = ' '.join((pregunta.texto or '').split())
            pregunta.name = texto if len(texto) <= 90 else texto[:89] + '…'

    @api.model
    def _registrar(self, pregunta, resumen=None, conversacion=None):
        """Anota una pregunta sin respuesta, o suma una vez a la «nueva» que ya se le parece.

        Devuelve ``(registro, es_nueva)``. Dos preguntas se agrupan si tienen las mismas palabras significativas
        o se parecen mucho (ver ``conocimiento_texto.son_parecidas``). La misma conversación repitiendo la
        misma pregunta en menos de una hora no suma: es el modelo reintentando, no otra persona.
        """
        pregunta = ' '.join((pregunta or '').split())[:MAX_PREGUNTA]
        resumen = (resumen or '').strip()[:1000] or False
        ahora = fields.Datetime.now()
        clave = C.clave(pregunta)
        Pregunta = self.sudo()
        candidatas = Pregunta.search([('estado', '=', 'nueva')], order='ultima_vez desc', limit=PREGUNTAS_A_COMPARAR)
        parecida = next((p for p in candidatas if (clave and p.clave == clave) or C.son_parecidas(p.texto, pregunta)),
                        Pregunta.browse())
        if parecida:
            ya_la_hizo = bool(conversacion) and conversacion in parecida.conversacion_ids
            reciente = parecida.ultima_vez and parecida.ultima_vez > ahora - REPETICION_MISMA_CONVERSACION
            valores = {'ultima_vez': ahora}
            if not (ya_la_hizo and reciente):
                valores['veces'] = parecida.veces + 1
            if conversacion:
                valores.update({'conversacion_id': conversacion.id, 'conversacion_ids': [(4, conversacion.id)]})
            if resumen:
                valores['resumen'] = resumen
            parecida.write(valores)
            return parecida, False
        registro = Pregunta.create({
            'texto': pregunta, 'clave': clave, 'resumen': resumen, 'ultima_vez': ahora,
            'conversacion_id': conversacion.id if conversacion else False,
            'conversacion_ids': [(4, conversacion.id)] if conversacion else [],
        })
        return registro, True

    def action_convertir_en_conocimiento(self):
        """El botón de la dueña: abre el formulario de conocimiento ya con la pregunta; ella escribe la respuesta."""
        exigir_gerencia(self.env)
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Nueva entrada de conocimiento'),
            'res_model': 'dcasa.conocimiento',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_titulo': self.texto[:200],
                'default_pregunta_id': self.id,
                'default_nota': self.env._('Nació de una pregunta que se hizo %s.', (
                    self.env._('una vez') if self.veces == 1 else self.env._('%s veces', self.veces))),
            },
        }

    def action_descartar(self):
        exigir_gerencia(self.env)
        self.write({'estado': 'descartada'})
        return True

    def action_reabrir(self):
        exigir_gerencia(self.env)
        self.write({'estado': 'nueva'})
        return True

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(self.env._('Solo Gerencia atiende las preguntas sin respuesta.'))
        return super().write(vals)
