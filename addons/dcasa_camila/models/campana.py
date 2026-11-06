"""La campaña de correo que arma Camila y una persona aprueba (diseño en docs/CAMILA.md).

* **Estados**: borrador → aprobada (alguien tocó «Enviar»: se está subiendo a Resend) → enviada; o cancelada. Desde la
  etapa 2 (decisión de la dueña, 2026-11-06) puede haber **varias abiertas**, para grupos distintos (``publico``): el
  tope de 15 días es **por cliente** y lo lleva ``dcasa.camila.destinatario``.
* Nadie la escribe por RPC: el ACL es de solo lectura y la crean, editan y envían los métodos de ``dcasa.camila``, que
  exigen el grupo en el servidor antes de tocar nada.
* Cada línea guarda el producto con **el precio de la tienda en línea** del día en que se armó o se aprobó (nunca un
  precio escrito por la IA ni a mano).
* ``dcasa.camila.destinatario``: a qué correo (y ficha) le salió qué campaña y cuándo. Con eso el servidor no le manda a
  nadie más de un correo de campaña cada 15 días, aunque haya varias campañas.
* ``dcasa.camila.llegada``: los chats que llegaron con la marca de la campaña («DCN-0007») en el primer mensaje del
  cliente desde que salió.
* ``dcasa.camila.prueba``: cada «Enviarme una prueba» que salió (para el tope por persona; sin datos de clientes).
"""
from odoo import fields, models

from . import reglas as R

ESTADOS = [
    ('borrador', 'Borrador'),
    ('aprobada', 'Aprobada (enviándose)'),
    ('enviada', 'Enviada'),
    ('cancelada', 'Cancelada'),
]
ABIERTAS = ('borrador', 'aprobada')
FUENTES = [('ia', 'Lo escribió la IA'), ('mixta', 'La IA y el texto fijo'), ('fija', 'Texto fijo'),
           ('persona', 'Lo editó una persona')]


class CamilaCampana(models.Model):
    _name = 'dcasa.camila.campana'
    _description = 'Campaña de correo de Camila'
    _order = 'id desc'

    name = fields.Char('Campaña', readonly=True)
    estado = fields.Selection(ESTADOS, default='borrador', required=True, readonly=True, index=True)
    asunto = fields.Char(readonly=True)
    entrada = fields.Text(readonly=True)
    linea_ids = fields.One2many('dcasa.camila.linea', 'campana_id', 'Productos', readonly=True)
    fuente = fields.Selection(FUENTES, 'Quién escribió el texto', readonly=True)
    nota = fields.Char('Qué pasó al armarla', readonly=True)
    html = fields.Text('Vista previa (HTML)', readonly=True)
    huella = fields.Char(readonly=True,
                         help='Huella del HTML que vio quien aprueba: si cambia, se le vuelve a mostrar.')
    precios_del = fields.Datetime('Precios del', readonly=True)
    automatica = fields.Boolean('La armó Camila sola (cron)', readonly=True)
    armada_por = fields.Many2one('res.users', 'La armó', readonly=True, ondelete='set null')
    editada_por = fields.Many2one('res.users', 'La editó', readonly=True, ondelete='set null')
    aprobada_por = fields.Many2one('res.users', 'La aprobó', readonly=True, ondelete='set null')
    aprobada_en = fields.Datetime('Aprobada el', readonly=True)
    enviando_desde = fields.Datetime(readonly=True)
    enviada_en = fields.Datetime('Enviada el', readonly=True, index='btree_not_null')
    destinatarios = fields.Integer('Clientes a los que se envió', readonly=True)
    resend_broadcast_id = fields.Char('Campaña en Resend', readonly=True, copy=False)
    error = fields.Char('Último error', readonly=True)
    prueba_a = fields.Char('Última prueba a', readonly=True)
    prueba_en = fields.Datetime('Última prueba el', readonly=True)
    cancelada_por = fields.Many2one('res.users', 'La descartó', readonly=True, ondelete='set null')
    # Resultados que da Resend (si los da: GET /broadcasts/{id}/recipients); las aperturas pueden no ser exactas.
    entregados = fields.Integer(readonly=True)
    abiertos = fields.Integer(readonly=True)
    clics = fields.Integer('Tocaron un enlace', readonly=True)
    bajas = fields.Integer('Se dieron de baja', readonly=True)
    resultados_en = fields.Datetime('Resultados de Resend al', readonly=True)
    llegada_ids = fields.One2many('dcasa.camila.llegada', 'campana_id', 'Chats que llegaron', readonly=True)
    destinatario_ids = fields.One2many('dcasa.camila.destinatario', 'campana_id', 'A quién le salió', readonly=True)
    marca = fields.Char(compute='_compute_marca', help='Lo que lleva el mensaje de WhatsApp para saber que vino del '
                                                         'correo.')
    # Etapa 2: a quién va, de dónde salió y la idea que guía a la IA.
    publico = fields.Char('A quién va', readonly=True, default='todos',
                          help='Los grupos elegidos (se suman), siempre cruzados con el permiso, la baja y el tope de '
                               '15 días por cliente.')
    tema = fields.Selection(R.TEMAS, 'De dónde salió', readonly=True, default='mezcla')
    idea = fields.Text('Idea de la campaña', readonly=True,
                       help='Lo que el equipo quiere decir: la IA escribe el asunto y la entrada con esto (no lleva '
                            'datos de clientes).')
    # Los botones y enlaces del correo (decisión de la dueña, 2026-11-06): WhatsApp, la tienda en línea o los dos (al
    # menos uno); los enlaces a la web llevan UTM con la marca de la campaña; las redes del sitio al pie, si se quiere.
    boton_whatsapp = fields.Boolean('Botón «Escríbenos por WhatsApp»', default=True, readonly=True)
    boton_web = fields.Boolean('Botón «Visita nuestra tienda en línea»', default=False, readonly=True)
    enlaces_productos = fields.Boolean('La foto y el nombre llevan a la página del producto', default=True,
                                       readonly=True)
    redes = fields.Boolean('Redes sociales al pie', default=False, readonly=True)

    def _compute_marca(self):
        for campana in self:
            campana.marca = R.marca(campana.id) if campana.id else ''


class CamilaLinea(models.Model):
    _name = 'dcasa.camila.linea'
    _description = 'Producto de una campaña de Camila'
    _order = 'secuencia, id'

    campana_id = fields.Many2one('dcasa.camila.campana', required=True, ondelete='cascade', index=True,
                                 readonly=True)
    secuencia = fields.Integer(readonly=True)
    producto_id = fields.Many2one('product.template', 'Producto', ondelete='set null', readonly=True, index=True)
    nombre = fields.Char(readonly=True)
    texto = fields.Char('Línea', readonly=True)
    grupo = fields.Selection(R.GRUPOS, readonly=True)
    precio = fields.Float('Precio de la tienda', readonly=True, digits='Product Price')
    precio_texto = fields.Char('Precio como se ve', readonly=True)
    mas_itbms = fields.Boolean('+ ITBMS', readonly=True)
    imagen = fields.Char('Foto (URL pública)', readonly=True)


class CamilaLlegada(models.Model):
    _name = 'dcasa.camila.llegada'
    _description = 'Chat que llegó por una campaña de Camila'
    _order = 'ts desc, id desc'

    campana_id = fields.Many2one('dcasa.camila.campana', required=True, ondelete='cascade', index=True,
                                 readonly=True)
    conversacion_id = fields.Many2one('dcasa.conversacion', ondelete='cascade', readonly=True, index=True)
    partner_id = fields.Many2one('res.partner', 'Cliente', ondelete='set null', readonly=True, index=True)
    mensaje_id = fields.Many2one('dcasa.mensaje', ondelete='set null', readonly=True)
    ts = fields.Datetime('Llegó el', readonly=True)

    _una_por_chat = models.Constraint('UNIQUE(campana_id, conversacion_id)',
                                      'Ese chat ya está contado en esa campaña.')


class CamilaDestinatario(models.Model):
    """A qué correo le salió qué campaña y cuándo: el registro del tope de 15 días POR CLIENTE (decisión de la dueña,
    2026-11-06). Lo escribe el envío antes de mandar (y lo borra si Resend no llegó a mandarlo). Vive solo en Odoo."""
    _name = 'dcasa.camila.destinatario'
    _description = 'A quién le salió una campaña de Camila'
    _order = 'enviada_en desc, id desc'

    campana_id = fields.Many2one('dcasa.camila.campana', required=True, ondelete='cascade', index=True,
                                 readonly=True)
    correo = fields.Char(required=True, index=True, readonly=True)
    partner_id = fields.Many2one('res.partner', 'Cliente', ondelete='set null', readonly=True, index=True)
    enviada_en = fields.Datetime('Le salió el', required=True, index=True, readonly=True)

    _uno_por_campana = models.Constraint('UNIQUE(campana_id, correo)', 'Ese correo ya está en esa campaña.')


class CamilaPrueba(models.Model):
    """Las pruebas que salieron (salen por el mismo cupo que los correos de las facturas): una cada 2 minutos por
    persona y pocas en 24 horas (``envio.py``). Solo las escribe el sistema."""
    _name = 'dcasa.camila.prueba'
    _description = 'Prueba de una campaña de Camila (para el tope)'
    _order = 'enviada_en desc, id desc'

    usuario_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True, readonly=True)
    campana_id = fields.Many2one('dcasa.camila.campana', ondelete='set null', readonly=True)
    enviada_en = fields.Datetime(required=True, default=fields.Datetime.now, index=True, readonly=True)
