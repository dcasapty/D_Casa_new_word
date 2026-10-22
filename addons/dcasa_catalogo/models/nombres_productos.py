"""Nombres de productos en MAYÚSCULAS (decisión F5 de la gerencia).

* **Lo nuevo:** el nombre de un producto se guarda en mayúsculas al crearlo o cambiarlo, venga de donde venga (la
  ficha, la importación del Excel del proveedor con Brian, el catálogo, la creación rápida de una línea). Solo cambian
  las letras (con sus tildes: «Sofá» → «SOFÁ») y se juntan los espacios repetidos; nada más.
* **Lo que ya estaba:** no se toca solo. Gerencia lo revisa en **Ventas › Productos › Nombres en MAYÚSCULAS**: la
  pantalla muestra «así quedarán estos N nombres» (antes → después) y un botón los cambia. Cada nombre se cambia en
  todos los idiomas que tenga guardados, y solo si sigue igual a como se vio en la vista previa.
* El sitio, Juan, Brian y los buscadores no distinguen mayúsculas al buscar, así que nada deja de encontrarse.
"""
from odoo import Command, api, fields, models
from odoo.exceptions import AccessError

GRUPOS_CATALOGO = ('product.group_product_manager', 'base.group_system')


def nombre_en_mayusculas(texto):
    """«Sofá  seccional milán» → «SOFÁ SECCIONAL MILÁN». Lo que no es texto vuelve igual."""
    if not isinstance(texto, str):
        return texto
    return ' '.join(texto.split()).upper()


def _mayusculas(valor):
    """El nombre tal como llega a create/write: texto, o un diccionario por idioma."""
    if isinstance(valor, dict):
        return {idioma: nombre_en_mayusculas(texto) for idioma, texto in valor.items()}
    return nombre_en_mayusculas(valor)


def exigir_catalogo(env):
    if not (env.su or any(env.user.has_group(grupo) for grupo in GRUPOS_CATALOGO)):
        raise AccessError(env._('Ordenar los nombres y unir productos repetidos lo hace Gerencia.'))


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'name' in vals:
                vals['name'] = _mayusculas(vals['name'])
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals:
            vals = dict(vals, name=_mayusculas(vals['name']))
        return super().write(vals)

    @api.model
    def _dcasa_nombres_por_cambiar(self):
        """``[(plantilla, nombre que se ve, nombre nuevo)]`` de los productos (activos y archivados) cuyo nombre en
        algún idioma no está en MAYÚSCULAS. El nombre que se ve es el del idioma de quien mira."""
        self.env['product.template'].flush_model(['name'])
        self.env.cr.execute('SELECT id, name FROM product_template WHERE name IS NOT NULL ORDER BY id')
        idioma = self.env.lang or 'en_US'
        resultado = []
        for plantilla_id, guardados in self.env.cr.fetchall():
            textos = guardados or {}
            if not any(texto and texto != nombre_en_mayusculas(texto) for texto in textos.values()):
                continue
            visto = textos.get(idioma) or textos.get('en_US') or next(iter(textos.values()), '') or ''
            resultado.append((self.browse(plantilla_id), visto, nombre_en_mayusculas(visto)))
        return resultado

    def _dcasa_nombres_guardados(self):
        """``{idioma: nombre}`` tal como está guardado (cada traducción)."""
        self.ensure_one()
        self.flush_recordset(['name'])
        self.env.cr.execute('SELECT name FROM product_template WHERE id = %s', [self.id])
        fila = self.env.cr.fetchone()
        return dict(fila[0] or {}) if fila else {}

    def _dcasa_pasar_a_mayusculas(self):
        """Escribe el nombre en MAYÚSCULAS en cada idioma guardado (por el ORM: el sitio y Meta se enteran)."""
        for plantilla in self:
            for idioma, texto in plantilla._dcasa_nombres_guardados().items():
                if texto and texto != nombre_en_mayusculas(texto):
                    plantilla.with_context(lang=idioma).write({'name': texto})


class DcasaProductoMayusculas(models.TransientModel):
    """Ventas › Productos › Nombres en MAYÚSCULAS: vista previa y botón."""
    _name = 'dcasa.producto.mayusculas'
    _description = 'Nombres de productos en MAYÚSCULAS'

    linea_ids = fields.One2many('dcasa.producto.mayusculas.linea', 'asistente_id', string='Nombres')
    cantidad = fields.Integer('Nombres por cambiar', compute='_compute_cantidad')

    @api.model
    def default_get(self, fields_list):
        exigir_catalogo(self.env)
        resultado = super().default_get(fields_list)
        if 'linea_ids' in fields_list:
            resultado['linea_ids'] = [
                Command.create({'product_tmpl_id': plantilla.id, 'antes': antes, 'despues': despues})
                for plantilla, antes, despues in self.env['product.template']._dcasa_nombres_por_cambiar()]
        return resultado

    @api.depends('linea_ids')
    def _compute_cantidad(self):
        for asistente in self:
            asistente.cantidad = len(asistente.linea_ids)

    def action_aplicar(self):
        """Cambia SOLO los nombres de la vista previa que siguen como se vieron."""
        self.ensure_one()
        exigir_catalogo(self.env)
        cambiados = 0
        for linea in self.linea_ids:
            plantilla = linea.product_tmpl_id.with_context(active_test=False)
            if not plantilla.exists() or (plantilla.name or '') != linea.antes:
                continue
            plantilla._dcasa_pasar_a_mayusculas()
            cambiados += 1
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'title': self.env._('Nombres en MAYÚSCULAS'),
            'message': self.env._('Listo: %s nombres quedaron en mayúsculas.', cambiados),
            'next': {'type': 'ir.actions.act_window_close'}}}


class DcasaProductoMayusculasLinea(models.TransientModel):
    _name = 'dcasa.producto.mayusculas.linea'
    _description = 'Nombre de producto por pasar a MAYÚSCULAS'

    asistente_id = fields.Many2one('dcasa.producto.mayusculas', required=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one('product.template', string='Producto', readonly=True)
    antes = fields.Char('Hoy se llama', readonly=True)
    despues = fields.Char('Quedará así', readonly=True)
