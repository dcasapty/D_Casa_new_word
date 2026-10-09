"""Etiquetas de colores, respuestas rápidas y «lo que ya leí» de la bandeja de conversaciones.

* **Etiquetas** (``dcasa.conversacion.etiqueta``): las crea la dueña («Pidió precio», «Comprobante recibido»…).
  Las vendedoras las ponen a mano y el asistente puede ponerlas solo, pero SOLO entre las que ya existen
  (la herramienta ``etiquetar_conversacion``): nunca inventa etiquetas nuevas.
* **Respuestas rápidas** (``dcasa.respuesta.rapida``): atajos con ``/`` (``/horario``, ``/ubicacion``…) que la
  dueña edita. El texto admite ``{nombre}``, ``{horario}``, ``{direccion}`` y ``{whatsapp}``; los datos salen de
  donde ya viven (nunca copias que se queden viejas).
* **Lectura** (``dcasa.conversacion.lectura``): hasta qué mensaje leyó cada persona de cada conversación. No hay
  un contador guardado: «no leídos» se calcula contando los mensajes del cliente posteriores a ese punto.
"""
import re
import unicodedata

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import tienda

MAX_ETIQUETA = 40
MAX_TEXTO_RAPIDO = 1000
PLACEHOLDERS = ('nombre', 'horario', 'direccion', 'whatsapp')
_ATAJO_VALIDO = re.compile(r'^/[a-z0-9_-]{1,30}$')
_LLAVE = re.compile(r'\{([^{}]*)\}')


def normalizar(texto):
    """Minúsculas, sin acentos y con espacios simples: «  Pidió  PRECIO » → «pidio precio»."""
    texto = unicodedata.normalize('NFKD', (texto or '').strip().lower())
    return ' '.join(''.join(c for c in texto if not unicodedata.combining(c)).split())


class DcasaConversacionEtiqueta(models.Model):
    _name = 'dcasa.conversacion.etiqueta'
    _description = 'Etiqueta de conversación'
    _order = 'sequence, name, id'

    name = fields.Char('Etiqueta', required=True, translate=False)
    color = fields.Integer('Color', default=1, help='Número de color de Odoo (0 a 11).')
    activa = fields.Boolean(
        'Activa', default=True,
        help='Una etiqueta inactiva no se puede poner, pero se queda en las conversaciones que ya la tienen.')
    sequence = fields.Integer('Orden', default=10)
    conversacion_count = fields.Integer('Conversaciones', compute='_compute_conversacion_count')

    _nombre_unico = models.Constraint('UNIQUE(name)', 'Ya existe una etiqueta con ese nombre.')
    _color_valido = models.Constraint('CHECK(color >= 0 AND color <= 11)', 'El color va de 0 a 11.')

    def _compute_conversacion_count(self):
        datos = {}
        if self.ids:
            self.env.cr.execute(
                'SELECT etiqueta_id, COUNT(*) FROM dcasa_conversacion_etiqueta_rel WHERE etiqueta_id IN %s '
                'GROUP BY etiqueta_id', [tuple(self.ids)])
            datos = dict(self.env.cr.fetchall())
        for etiqueta in self:
            etiqueta.conversacion_count = datos.get(etiqueta.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for valores in vals_list:
            if 'name' in valores:
                valores['name'] = ' '.join((valores['name'] or '').split())
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals:
            vals = {**vals, 'name': ' '.join((vals['name'] or '').split())}
        return super().write(vals)

    @api.constrains('name')
    def _check_nombre(self):
        for etiqueta in self:
            if not etiqueta.name or len(etiqueta.name) > MAX_ETIQUETA:
                raise ValidationError(self.env._('El nombre de la etiqueta va de 1 a %s letras.', MAX_ETIQUETA))
        # Sin repetir «Pidió precio» y «pidio  PRECIO»: el asistente las busca sin mayúsculas ni acentos.
        todas = self.search([])
        vistos = {}
        for otra in todas:
            vistos.setdefault(normalizar(otra.name), []).append(otra.id)
        for etiqueta in self:
            if len(vistos.get(normalizar(etiqueta.name), [])) > 1:
                raise ValidationError(self.env._('Ya existe una etiqueta parecida a «%s».', etiqueta.name))

    @api.model
    def _buscar_por_nombre(self, nombre):
        """La etiqueta ACTIVA con ese nombre (sin importar mayúsculas ni acentos), o vacío."""
        buscado = normalizar(nombre)
        if not buscado:
            return self.browse()
        return self.sudo().search([('activa', '=', True)]).filtered(lambda e: normalizar(e.name) == buscado)[:1]

    @api.model
    def lista(self):
        """Las etiquetas activas para la pantalla: ``[{id, nombre, color}]``."""
        self.env['dcasa.conversacion']._exigir_vendedora()
        return [{'id': e.id, 'nombre': e.name, 'color': e.color} for e in self.search([('activa', '=', True)])]


class DcasaRespuestaRapida(models.Model):
    _name = 'dcasa.respuesta.rapida'
    _description = 'Respuesta rápida'
    _order = 'sequence, atajo, id'
    _rec_name = 'atajo'

    atajo = fields.Char('Atajo', required=True, help='Lo que se escribe para usarla, p. ej. /horario.')
    texto = fields.Text(
        'Texto', required=True,
        help='Puedes usar {nombre} (el cliente), {horario}, {direccion} y {whatsapp} (los datos de la tienda).')
    descripcion = fields.Char('Para qué sirve')
    activa = fields.Boolean('Activa', default=True)
    sequence = fields.Integer('Orden', default=10)

    _atajo_unico = models.Constraint('UNIQUE(atajo)', 'Ya existe una respuesta rápida con ese atajo.')

    @api.model
    def _limpiar_atajo(self, atajo):
        atajo = (atajo or '').strip().lower().replace(' ', '-')
        return atajo if not atajo or atajo.startswith('/') else '/' + atajo

    @api.model_create_multi
    def create(self, vals_list):
        for valores in vals_list:
            if 'atajo' in valores:
                valores['atajo'] = self._limpiar_atajo(valores['atajo'])
        return super().create(vals_list)

    def write(self, vals):
        if 'atajo' in vals:
            vals = {**vals, 'atajo': self._limpiar_atajo(vals['atajo'])}
        return super().write(vals)

    @api.constrains('atajo', 'texto')
    def _check_respuesta(self):
        for respuesta in self:
            if not _ATAJO_VALIDO.match(respuesta.atajo or ''):
                raise ValidationError(self.env._(
                    'El atajo empieza con «/» y lleva solo letras minúsculas, números, «-» o «_» (hasta 30), '
                    'por ejemplo /horario.'))
            texto = (respuesta.texto or '').strip()
            if not texto or len(texto) > MAX_TEXTO_RAPIDO:
                raise ValidationError(self.env._(
                    'El texto de la respuesta va de 1 a %s letras.', MAX_TEXTO_RAPIDO))
            desconocidos = sorted({k for k in _LLAVE.findall(texto) if k not in PLACEHOLDERS})
            if desconocidos:
                raise ValidationError(self.env._(
                    'En el texto solo se pueden usar {nombre}, {horario}, {direccion} y {whatsapp}. '
                    'No reconozco: %s', ', '.join(f'{{{k}}}' for k in desconocidos)))

    def _armar(self, conversacion):
        """El texto con los datos de ESTE cliente y de la tienda."""
        self.ensure_one()
        datos = None
        valores = {}
        if '{nombre}' in self.texto:
            valores['nombre'] = conversacion._nombre_de_pila() if conversacion else ''
        if any(f'{{{k}}}' in self.texto for k in ('horario', 'direccion', 'whatsapp')):
            datos = tienda.datos_tienda(self.env)
            horario = datos['horario']['texto']
            valores.update({
                'horario': horario[:1].lower() + horario[1:], 'direccion': datos['direccion'],
                'whatsapp': datos['whatsapp'],
            })
        texto = self.texto
        if not valores.get('nombre'):
            # Sin nombre real no queda un «Hola ,»: se quita la palabra y el espacio o la coma que la rodean.
            texto = re.sub(r'\s*\{nombre\}', '', texto)
            texto = re.sub(r'^\s*[,;:]\s*', '', texto)
            valores.pop('nombre', None)
        return _LLAVE.sub(lambda m: str(valores.get(m.group(1), m.group(0))), texto).strip()

    @api.model
    def lista(self):
        """Las respuestas activas para el menú de ``/``: ``[{id, atajo, texto, descripcion}]`` (sin armar)."""
        self.env['dcasa.conversacion']._exigir_vendedora()
        return [{'id': r.id, 'atajo': r.atajo, 'texto': r.texto, 'descripcion': r.descripcion or ''}
                for r in self.search([('activa', '=', True)])]

    @api.model
    def texto_para(self, conversacion_id, atajo):
        """El texto de ``atajo`` ya armado para esa conversación (nombre del cliente, horario…)."""
        conversacion = self.env['dcasa.conversacion']._para_panel(conversacion_id)
        respuesta = self.search([('atajo', '=', self._limpiar_atajo(str(atajo or ''))), ('activa', '=', True)],
                                limit=1)
        if not respuesta:
            raise UserError(self.env._('No existe la respuesta rápida «%s».', atajo))
        return {'atajo': respuesta.atajo, 'texto': respuesta.sudo()._armar(conversacion.sudo())}


class DcasaConversacionLectura(models.Model):
    _name = 'dcasa.conversacion.lectura'
    _description = 'Hasta dónde leyó una persona una conversación'

    conversacion_id = fields.Many2one('dcasa.conversacion', required=True, ondelete='cascade', index=True)
    usuario_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    ultimo_leido_id = fields.Integer('Último mensaje leído', help='Id del último mensaje que la persona ya vio.')

    _lectura_unica = models.Constraint(
        'UNIQUE(conversacion_id, usuario_id)', 'Ya hay una marca de lectura de esa persona en la conversación.')
