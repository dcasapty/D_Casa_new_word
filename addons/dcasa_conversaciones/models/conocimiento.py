"""Base de conocimiento del asistente y el ciclo de aprendizaje.

* ``dcasa.conocimiento``: lo que el equipo quiere que el asistente sepa y diga (título, contenido, etiquetas).
  Gerencia lo edita. El asistente lo consulta con la herramienta ``buscar_conocimiento``: las 3 mejores
  coincidencias (búsqueda por palabras; ver ``conocimiento_texto.py``) y solo las entradas activas. Si Gerencia lo
  enciende en Ajustes, lo que falte por llenar se completa buscando por SIGNIFICADO (vectores que calcula el Worker).
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
import json
import logging
import time
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.exceptions import AccessError, ValidationError

from . import conocimiento_texto as C
from .reglas_clientes import redactar
from .tienda import datos_tienda, texto_tienda, url_base

_logger = logging.getLogger(__name__)

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
VENTANA_RESPUESTA = timedelta(days=7)   # cuánto después de la pregunta se busca lo que contestó una vendedora
LOTE_DE_VECTORES = 8            # textos por llamada al Worker (su tope)
VECTORES_POR_CORRIDA = 40       # entradas que se ponen al día por corrida del cron
PAUSA_SIGNIFICADO = 300         # segundos sin volver a intentar la búsqueda por significado después de un fallo
_SIN_SIGNIFICADO_HASTA = {}     # base de datos → instante (time.monotonic) hasta el que no se intenta


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
    vector = fields.Text('Huella de significado', copy=False, readonly=True, prefetch=False, groups=GRUPO_GERENCIA,
                         help='Lo calcula el Worker (JSON de números). Solo sirve para la búsqueda por significado.')
    vector_huella = fields.Char('Texto de la huella', copy=False, readonly=True, groups=GRUPO_GERENCIA,
                                help='Identifica el texto con el que se calculó la huella: si cambia, se recalcula.')

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
        extensión ``unaccent`` de la base y las entradas automáticas se arman al momento. Si quedan lugares sin
        llenar y la búsqueda por significado está encendida, se completan con las que hablan de lo mismo aunque
        no compartan palabras (``puntos`` = coseno × 100); lo que ya salió por palabras va siempre primero.
        """
        limite = max(1, limite)
        entradas = self.sudo().search([('activo', '=', True)])
        puntuadas = []
        for entrada in entradas:
            puntos = C.puntuar(consulta, entrada.titulo, entrada.etiquetas or '', entrada.contenido_vigente or '')
            if puntos:
                puntuadas.append((-puntos, entrada.titulo, entrada.id, entrada, puntos))
        puntuadas.sort(key=lambda t: t[:3])
        resultado = [(t[3], t[4]) for t in puntuadas[:limite]]
        if len(resultado) < limite:
            ya = {entrada.id for entrada, _puntos in resultado}
            resultado += self._buscar_por_significado(
                consulta, entradas.filtered(lambda e: e.id not in ya), limite - len(resultado))
        return resultado

    # ------------------------------------------------------------------
    # Búsqueda por significado (opcional, apagada por defecto)
    # ------------------------------------------------------------------

    def _texto_para_vector(self):
        """Lo que se convierte en huella: título, etiquetas y contenido (el Worker admite hasta 2000 letras)."""
        self.ensure_one()
        partes = (self.titulo, self.etiquetas, self.contenido_vigente)
        return ' . '.join(p.strip() for p in partes if p and p.strip())[:1900]

    @api.model
    def _cron_calcular_vectores(self):
        """Pone al día la huella de significado de las entradas activas cuyo texto cambió (o que no tienen).
        No hace nada si la búsqueda por significado está apagada. Devuelve cuántas calculó."""
        if not self.env['dcasa.juan.ajustes'].obtener().busqueda_semantica:
            return 0
        pendientes = []
        for entrada in self.sudo().search([('activo', '=', True)]):
            texto = entrada._texto_para_vector()
            if entrada.vector_huella != C.huella(texto):
                pendientes.append((entrada, texto))
        pendientes = pendientes[:VECTORES_POR_CORRIDA]
        calculadas = 0
        for i in range(0, len(pendientes), LOTE_DE_VECTORES):
            lote = pendientes[i:i + LOTE_DE_VECTORES]
            respuesta = self.env['dcasa.juan.cliente'].embeber([texto for _entrada, texto in lote])
            vectores = respuesta.get('vectores') if respuesta.get('ok') else None
            if not isinstance(vectores, list) or len(vectores) != len(lote) or not all(map(C.vector_valido, vectores)):
                _logger.warning('Juan: no se pudo calcular la huella de significado (%s).',
                                str(respuesta.get('error') or 'respuesta inválida')[:200])
                break
            for (entrada, texto), vector in zip(lote, vectores, strict=True):
                entrada.write({'vector': json.dumps(vector), 'vector_huella': C.huella(texto)})
            calculadas += len(lote)
        return calculadas

    @api.model
    def _buscar_por_significado(self, consulta, entradas, cuantos):
        """Hasta ``cuantos`` entradas de ``entradas`` cuya huella (al día) se parece a la de la pregunta. Si algo falla
        (Worker caído, sin IA, respuesta rara) devuelve ``[]``: la búsqueda por palabras sigue como siempre."""
        if cuantos < 1 or not self.env['dcasa.juan.ajustes'].obtener().busqueda_semantica:
            return []
        base = self.env.cr.dbname
        if _SIN_SIGNIFICADO_HASTA.get(base, 0) > time.monotonic():
            return []
        candidatas = []
        for entrada in entradas:
            if entrada.vector and entrada.vector_huella == C.huella(entrada._texto_para_vector()):
                try:
                    vector = json.loads(entrada.vector)
                except ValueError:
                    continue
                if C.vector_valido(vector):
                    candidatas.append((entrada, vector))
        if not candidatas:
            return []     # nada que comparar: no vale la pena ni preguntarle al Worker
        respuesta = self.env['dcasa.juan.cliente'].embeber([consulta[:300]], rapido=True)
        vectores = respuesta.get('vectores') if respuesta.get('ok') else None
        if not isinstance(vectores, list) or len(vectores) != 1 or not C.vector_valido(vectores[0]):
            _SIN_SIGNIFICADO_HASTA[base] = time.monotonic() + PAUSA_SIGNIFICADO
            _logger.warning('Juan: la búsqueda por significado no está disponible (%s); se sigue por palabras.',
                            str(respuesta.get('error') or 'respuesta inválida')[:200])
            return []
        _SIN_SIGNIFICADO_HASTA.pop(base, None)
        parecidas = sorted(((C.coseno(vectores[0], vector), entrada.titulo, entrada.id, entrada)
                            for entrada, vector in candidatas), key=lambda t: (-t[0], t[1], t[2]))
        if parecidas:
            _logger.info('Juan: significado, lo más parecido a la pregunta es «%s» (coseno %.2f, umbral %.2f).',
                         parecidas[0][1], parecidas[0][0], C.UMBRAL_SIGNIFICADO)
        return [(entrada, round(coseno * 100)) for coseno, _titulo, _id, entrada in parecidas[:cuantos]
                if coseno >= C.UMBRAL_SIGNIFICADO]


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
    respuesta_vendedora = fields.Text(
        'Lo que contestó una vendedora', readonly=True, copy=False,
        help='Lo que una vendedora le escribió a un cliente después de esta pregunta (sin correos ni números largos). '
             'Es la base de la entrada: revísala; no se activa sola.')
    respuesta_de_id = fields.Many2one('res.users', 'Contestó', readonly=True, ondelete='set null')
    respuesta_en = fields.Datetime('Contestó el', readonly=True)
    respuesta_con_cifras = fields.Boolean(
        'Con cifras', readonly=True, help='La respuesta menciona dinero o números: confírmalos antes de activarla.')

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

    @api.model
    def _cron_buscar_respuestas(self):
        """Cada noche: a cada pregunta «nueva» sin respuesta, busca lo que una vendedora contestó después (hasta 7
        días) en las conversaciones donde se preguntó. Solo propone: la entrada la revisa y la activa Gerencia."""
        encontradas = 0
        for pregunta in self.sudo().search([('estado', '=', 'nueva'), ('respuesta_vendedora', '=', False)],
                                           order='ultima_vez desc', limit=100):
            if pregunta._buscar_respuesta():
                encontradas += 1
        return encontradas

    def _buscar_respuesta(self):
        """Guarda lo que una vendedora contestó sobre el tema, si lo encuentra. Devuelve si lo guardó."""
        self.ensure_one()
        if not self.conversacion_ids or not self.create_date:
            return False
        mensajes = self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', 'in', self.conversacion_ids.ids), ('tipo', '=', 'mensaje'),
            ('autor', '=', 'vendedora'), ('estado_envio', '!=', 'programado'),
            ('ts', '>=', self.create_date), ('ts', '<=', (self.ultima_vez or self.create_date) + VENTANA_RESPUESTA),
        ], order='ts, id', limit=40)
        elegido = C.mejor_respuesta(self.texto, [(m.id, m.texto or '') for m in mensajes])
        if not elegido:
            return False
        mensaje = mensajes.browse(elegido)
        texto = C.limpiar_respuesta(mensaje.texto)
        self.sudo().write({
            'respuesta_vendedora': texto, 'respuesta_de_id': mensaje.usuario_id.id or False,
            'respuesta_en': mensaje.ts,
            # Se mira el texto ya limpio: un celular que se quitó no es una cifra que confirmar.
            'respuesta_con_cifras': C.tiene_cifras(texto)})
        return True

    def action_convertir_en_conocimiento(self):
        """El botón de la dueña: abre el formulario de conocimiento ya con la pregunta. Si una vendedora ya la
        contestó, la entrada nace con esa respuesta como BORRADOR (inactiva) para que la revise y la active."""
        exigir_gerencia(self.env)
        self.ensure_one()
        contexto = {
            'default_titulo': self.texto[:200],
            'default_pregunta_id': self.id,
            'default_nota': self.env._('Nació de una pregunta que se hizo %s.', (
                self.env._('una vez') if self.veces == 1 else self.env._('%s veces', self.veces))),
        }
        if self.respuesta_vendedora:
            quien = self.respuesta_de_id.name or self.env._('una vendedora')
            contexto.update({
                'default_contenido': self.respuesta_vendedora,
                'default_activo': False,
                'default_nota': contexto['default_nota'] + ' ' + self.env._(
                    'Borrador con lo que contestó %(quien)s el %(fecha)s: revísalo%(cifras)s y actívalo.',
                    quien=quien, fecha=fields.Date.to_string(self.respuesta_en) if self.respuesta_en else '—',
                    cifras=self.env._(' (tiene cifras: confírmalas)') if self.respuesta_con_cifras else ''),
            })
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Nueva entrada de conocimiento'),
            'res_model': 'dcasa.conocimiento',
            'view_mode': 'form',
            'target': 'current',
            'context': contexto,
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
