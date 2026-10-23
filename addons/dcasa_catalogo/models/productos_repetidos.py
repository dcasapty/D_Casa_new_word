"""Productos que parecen repetidos y cómo unirlos sin perder nada (decisión F5 de la gerencia).

**Ventas › Productos › Productos repetidos** (Gerencia) lista, sin cambiar nada, los productos (de fichas distintas)
que comparten:

* el **mismo código** (la referencia, sin importar mayúsculas, guiones ni espacios);
* el **mismo código de barras** (o el código de barras de uno es la referencia del otro);
* el **mismo nombre** (sin importar mayúsculas, tildes, espacios ni signos).

Cada fila tiene «Ver los productos» y «Unir…», que abre el asistente ``dcasa.producto.unir``: tú eliges qué ficha
queda y cuál se archiva; la pantalla dice antes qué va a pasar y no deja seguir si hay algo pendiente.
"""
from odoo import fields, models, tools
from odoo.exceptions import UserError

from .nombres_productos import exigir_catalogo

ACENTOS = ('ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun')


def _normal(columna):
    """SQL: solo letras y números, sin tildes y en mayúsculas (igual en cualquier configuración de la base)."""
    return (f"regexp_replace(upper(translate(coalesce({columna}, ''), '{ACENTOS[0]}', '{ACENTOS[1]}')), "
            f"'[^0-9A-Z]', '', 'g')")


class DcasaProductoRepetido(models.Model):
    _name = 'dcasa.producto.repetido'
    _description = 'Productos que parecen repetidos'
    _auto = False
    _order = 'tipo, cantidad desc, valor'
    _rec_name = 'valor'

    tipo = fields.Selection([('codigo', 'Mismo código'), ('barras', 'Mismo código de barras'),
                             ('nombre', 'Mismo nombre')], string='Por qué', readonly=True)
    valor = fields.Char('Lo que comparten', readonly=True)
    cantidad = fields.Integer('Productos', readonly=True)
    nombres = fields.Char('Cuáles son', readonly=True)
    ids_productos = fields.Char('Ids de los productos', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        nombre = "coalesce(pt.name->>'es_419', pt.name->>'en_US')"
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH p AS (
                    SELECT pp.id, pp.product_tmpl_id AS tmpl,
                           {nombre} || coalesce(' [' || pp.default_code || ']', '') AS etiqueta,
                           {_normal('pp.default_code')} AS cod,
                           {_normal('pp.barcode')} AS bar,
                           {_normal(nombre)} AS nom
                      FROM product_product pp
                      JOIN product_template pt ON pt.id = pp.product_tmpl_id
                     WHERE pp.active AND pt.active AND pt.type IN ('consu', 'combo')
                ), claves AS (
                    SELECT 'codigo' AS tipo, cod AS valor, id, tmpl, etiqueta FROM p WHERE length(cod) >= 3
                    UNION
                    SELECT 'barras', bar, id, tmpl, etiqueta FROM p WHERE length(bar) >= 4
                    UNION
                    SELECT 'barras', p.cod, p.id, p.tmpl, p.etiqueta FROM p
                     WHERE length(p.cod) >= 4 AND EXISTS (SELECT 1 FROM p q WHERE q.bar = p.cod AND q.tmpl <> p.tmpl)
                    UNION
                    SELECT 'nombre', nom, id, tmpl, etiqueta FROM p WHERE length(nom) >= 4
                )
                SELECT ('x' || substr(md5(tipo || '|' || valor), 1, 13))::bit(52)::bigint AS id, tipo, valor,
                       count(DISTINCT tmpl) AS cantidad,
                       string_agg(DISTINCT etiqueta, ' · ') AS nombres,
                       string_agg(id::text, ',' ORDER BY id) AS ids_productos
                  FROM claves
                 GROUP BY tipo, valor
                HAVING count(DISTINCT tmpl) > 1
            )""")

    def _productos(self):
        self.ensure_one()
        exigir_catalogo(self.env)
        self.env['product.product'].flush_model()
        self.env['product.template'].flush_model()
        if not self.exists():
            raise UserError(self.env._('Ya no se repiten: actualiza la lista.'))
        ids = [int(i) for i in (self.ids_productos or '').split(',') if i]
        return self.env['product.product'].browse(ids).exists()

    def action_ver(self):
        self.ensure_one()
        productos = self._productos()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'product.template', 'view_mode': 'list,form',
            'name': self.env._('Productos que parecen repetidos'),
            'domain': [('id', 'in', productos.product_tmpl_id.ids)],
        }

    def action_unir(self):
        self.ensure_one()
        productos = self._productos()
        if len(productos.product_tmpl_id) < 2:
            raise UserError(self.env._('Ya no se repiten: actualiza la lista.'))
        return self.env['dcasa.producto.unir']._dcasa_abrir(productos)
