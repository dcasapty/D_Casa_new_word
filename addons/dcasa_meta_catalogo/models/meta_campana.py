import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .reglas_meta import LARGO_ETIQUETA, etiqueta_ascii

CODIGO = re.compile(rf'[a-z0-9_]{{1,{LARGO_ETIQUETA}}}')


class DcasaMetaCampana(models.Model):
    """Una campaña de anuncios (p. ej. «Navidad»): la dueña la pone en los productos y en Meta arma con ella un
    conjunto de productos («Etiqueta personalizada 1 es igual a navidad»)."""
    _name = 'dcasa.meta.campana'
    _description = 'Campaña de anuncios en Meta'
    _order = 'active desc, name'

    name = fields.Char('Campaña', required=True, help='Como la llamas tú, p. ej. «Navidad» o «Regreso a clases».')
    codigo = fields.Char(
        'Código para Meta', readonly=True, copy=False, index=True,
        help='Lo que escribes en Meta al armar el conjunto de productos: «Etiqueta personalizada 1» es igual a este '
             'código. Sale del nombre al crear la campaña (minúsculas, sin tildes ni espacios) y no cambia aunque '
             'después le cambies el nombre, para que el conjunto de Meta no se rompa.')
    active = fields.Boolean(
        'Activa', default=True,
        help='Una campaña archivada deja de salir en el catálogo de Meta (sus productos quedan sin esa etiqueta), '
             'pero no se les quita a los productos.')
    producto_count = fields.Integer('Productos', compute='_compute_producto_count')

    _codigo_unico = models.Constraint('UNIQUE(codigo)', 'Ya hay una campaña con ese código para Meta.')

    @api.model_create_multi
    def create(self, vals_list):
        # El código sale del nombre UNA vez, al crear (minúsculas, sin tildes ni espacios). No cambia aunque después le
        # cambien el nombre: si cambiara, el conjunto de productos de Meta dejaría de encontrar los productos.
        for vals in vals_list:
            vals['codigo'] = etiqueta_ascii(vals.get('codigo') or vals.get('name'))
        return super().create(vals_list)

    @api.constrains('codigo')
    def _check_codigo(self):
        for campana in self:
            if not campana.codigo or not CODIGO.fullmatch(campana.codigo):
                raise ValidationError(self.env._(
                    'El nombre de la campaña necesita letras o números: de ahí sale el código que escribes en Meta.'))

    def _compute_producto_count(self):
        # Con sudo: el campo de la campaña en el producto es de Gerencia; un conteo no muestra nada más.
        conteo = dict(self.env['product.template'].sudo()._read_group(
            [('dcasa_meta_campana_id', 'in', self.ids)], ['dcasa_meta_campana_id'], ['__count']))
        for campana in self:
            campana.producto_count = conteo.get(campana, 0)
