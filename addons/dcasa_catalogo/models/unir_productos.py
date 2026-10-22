"""Unir dos productos repetidos sin perder historia (decisión F5 de la gerencia).

Tú eliges **qué ficha queda** y **cuál se archiva**. Antes de unir, la pantalla dice exactamente qué va a pasar; si
hay algo a medias con la ficha que se archiva (una entrega o recepción sin terminar, una cotización o una compra
abierta) no deja seguir y dice cuál es.

Al unir (como quien lo pide, que debe ser Gerencia):

* **Existencias:** lo que hay de la ficha que se archiva pasa a la que queda, en la misma ubicación, con un ajuste de
  inventario por cada lado («Unión de productos: A → B»): queda en el historial de movimientos de las dos.
* **Precios de proveedor**, **piezas de combo**, **reglas de tarifa** y **premios de Socios** que usaban la ficha que se
  archiva pasan a la que queda.
* **Fotos:** si la que queda no tiene foto, toma la de la otra; si ya tiene, la de la otra y su galería se suman a la
  galería (sin repetir la misma foto).
* **Código de barras y referencia:** si la que queda no los tiene, pasan a ella (la etiqueta deja su historial en
  dcasa_barras); si ya tiene los suyos, se quedan los suyos y la nota lo dice.
* **Ventas, facturas, compras y movimientos viejos no se reescriben:** siguen en la ficha archivada, que se puede
  abrir siempre (la que queda la lista en «Fichas unidas a esta»). Así nada de la contabilidad ni del inventario
  pasado cambia.
* La ficha que se va **se archiva** (no se borra) y las dos quedan con una nota de quién unió qué y cuándo.

No se unen: dos fichas que tienen varios tamaños o colores cada una (se une una ficha de un solo producto a una medida
de otra), productos con lote o serie, con unidades distintas, ni el producto del sistema para los descuentos.
"""
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError

from .nombres_productos import exigir_catalogo


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dcasa_unido_a_id = fields.Many2one(
        'product.template', string='Se unió a', readonly=True, copy=False, index='btree_not_null',
        help='Esta ficha estaba repetida y se unió a esa (sus ventas y movimientos viejos siguen aquí).')
    dcasa_unidas_ids = fields.One2many(
        'product.template', 'dcasa_unido_a_id', string='Fichas unidas a esta', readonly=True,
        context={'active_test': False}, domain=[('active', 'in', (True, False))])


class DcasaProductoUnir(models.TransientModel):
    _name = 'dcasa.producto.unir'
    _description = 'Unir productos repetidos'

    candidato_ids = fields.Many2many('product.product', string='Productos del grupo', readonly=True)
    queda_id = fields.Many2one('product.product', string='Queda esta', required=True,
                               domain="[('id', 'in', candidato_ids)]")
    sale_id = fields.Many2one('product.product', string='Se archiva esta', required=True,
                              domain="[('id', 'in', candidato_ids), ('id', '!=', queda_id)]")
    resumen = fields.Html('Qué va a pasar', compute='_compute_resumen', sanitize=False)
    bloqueos = fields.Text('Antes hay que', compute='_compute_resumen')

    # ------------------------------------------------------------------
    # Abrir
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_abrir(self, productos):
        exigir_catalogo(self.env)
        queda, sale = self._dcasa_por_defecto(productos)
        asistente = self.create({'candidato_ids': [(6, 0, productos.ids)], 'queda_id': queda.id,
                                 'sale_id': sale.id})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': asistente.id,
                'view_mode': 'form', 'target': 'new', 'name': self.env._('Unir productos repetidos')}

    @api.model
    def _dcasa_por_defecto(self, productos):
        """Queda la ficha con más ventas (a igual, la más vieja); se archiva otra de un solo producto."""
        Linea = self.env['sale.order.line'].sudo()
        ventas = dict(Linea._read_group([('product_id', 'in', productos.ids)], ['product_id'], ['__count']))
        ordenados = productos.sorted(lambda p: (-ventas.get(p, 0), p.product_tmpl_id.id, p.id))
        queda = ordenados[:1]
        sale = (ordenados - queda).filtered(lambda p: p.product_tmpl_id != queda.product_tmpl_id
                                            and p.product_tmpl_id.product_variant_count == 1)[:1]
        return queda, sale or (ordenados - queda)[:1]

    # ------------------------------------------------------------------
    # Vista previa
    # ------------------------------------------------------------------

    def _dcasa_bloqueos(self):
        """Lo que impide unir, en palabras de la tienda (lista vacía = se puede)."""
        self.ensure_one()
        queda, sale = self.queda_id, self.sale_id
        if not queda or not sale:
            return [self.env._('Elige qué ficha queda y cuál se archiva.')]
        if queda == sale or queda.product_tmpl_id == sale.product_tmpl_id:
            return [self.env._('Elige dos fichas distintas.')]
        bloqueos = []
        if sale.product_tmpl_id.with_context(active_test=False).product_variant_count > 1:
            bloqueos.append(self.env._(
                '«%s» tiene varios tamaños o colores: solo se archiva una ficha de un solo producto. Elige al revés '
                'o únelas a mano.', sale.product_tmpl_id.display_name))
        if queda.company_id != sale.company_id:
            bloqueos.append(self.env._('Las dos fichas son de empresas distintas.'))
        if queda.uom_id != sale.uom_id:
            bloqueos.append(self.env._('Se venden en unidades distintas (%(a)s y %(b)s).',
                                       a=queda.uom_id.name, b=sale.uom_id.name))
        if 'tracking' in sale._fields and (sale.tracking != 'none' or queda.tracking != 'none'):
            bloqueos.append(self.env._('Una de las dos se controla por lote o por serie: se une a mano.'))
        sistema = (sale.company_id or self.env.company).sudo().sale_discount_product_id
        if sistema and sistema in (queda | sale):
            bloqueos.append(self.env._('Una de las dos es un producto del sistema (el del descuento).'))
        movimientos = self.env['stock.move'].sudo().search(
            [('product_id', '=', sale.id), ('state', 'not in', ('done', 'cancel'))], limit=10)
        if movimientos:
            documentos = ', '.join(sorted(set(movimientos.mapped(lambda m: m.picking_id.name or m.reference or ''))))
            bloqueos.append(self.env._('Termina o cancela lo que está en camino de «%(p)s»: %(d)s.',
                                       p=sale.display_name, d=documentos))
        cotizaciones = self.env['sale.order.line'].sudo().search(
            [('product_id', '=', sale.id), ('order_id.state', 'in', ('draft', 'sent'))], limit=10).order_id
        if cotizaciones:
            bloqueos.append(self.env._('Cambia el producto en estas cotizaciones (o confírmalas): %s.',
                                       ', '.join(cotizaciones.mapped('name'))))
        compras = self.env['purchase.order.line'].sudo().search(
            [('product_id', '=', sale.id), ('order_id.state', 'in', ('draft', 'sent', 'to approve'))],
            limit=10).order_id
        if compras:
            bloqueos.append(self.env._('Termina o cancela estas compras abiertas: %s.',
                                       ', '.join(compras.mapped('name'))))
        quants = self._dcasa_existencias(sale)
        if any(q.lot_id or q.package_id or q.owner_id for q in quants):
            bloqueos.append(self.env._('Parte de las existencias de «%s» está en paquetes, lotes o de otro dueño: '
                                       'muévelas a mano.', sale.display_name))
        return bloqueos

    @api.model
    def _dcasa_existencias(self, producto):
        return self.env['stock.quant'].sudo().search([
            ('product_id', '=', producto.id), ('location_id.usage', '=', 'internal'), ('quantity', '!=', 0)])

    def _dcasa_que_pasa(self):
        """La lista de lo que hará «Unir» (lo mismo que hace, sin hacerlo)."""
        self.ensure_one()
        queda, sale = self.queda_id, self.sale_id
        plantilla_sale, plantilla_queda = sale.product_tmpl_id, queda.product_tmpl_id
        filas = []
        for quant in self._dcasa_existencias(sale):
            filas.append(self.env._('Pasan %(n)s unidades en %(ubicacion)s.', n=f'{quant.quantity:g}',
                                    ubicacion=quant.location_id.display_name))
        precios = self._dcasa_precios_proveedor(sale)
        if precios:
            filas.append(self.env._('Pasan %s precios de proveedor.', len(precios)))
        combos = self.env['product.combo.item'].sudo().search_count([('product_id', '=', sale.id)])
        if combos:
            filas.append(self.env._('Pasa a %s combos.', combos))
        if plantilla_sale.image_1920 and not plantilla_queda.image_1920:
            filas.append(self.env._('Su foto pasa a ser la foto de la que queda.'))
        elif plantilla_sale.image_1920 and plantilla_sale.image_1920 != plantilla_queda.image_1920:
            filas.append(self.env._('Su foto se suma a la galería.'))
        if 'product_template_image_ids' in plantilla_sale._fields and plantilla_sale.product_template_image_ids:
            filas.append(self.env._('Su galería (%s fotos) se suma a la de la que queda.',
                                    len(plantilla_sale.product_template_image_ids)))
        if sale.barcode:
            filas.append(self.env._('El código de barras %s pasa a la que queda.', sale.barcode) if not queda.barcode
                         else self.env._('La que queda conserva su código de barras (%(a)s); el %(b)s se queda en la '
                                         'ficha archivada.', a=queda.barcode, b=sale.barcode))
        if sale.default_code and not queda.default_code:
            filas.append(self.env._('La referencia %s pasa a la que queda.', sale.default_code))
        filas.append(self.env._('Sus ventas, facturas y movimientos viejos no cambian: siguen en la ficha archivada.'))
        filas.append(self.env._('«%s» se archiva (no se borra).', plantilla_sale.display_name))
        return filas

    @api.depends('queda_id', 'sale_id')
    def _compute_resumen(self):
        for asistente in self:
            bloqueos = asistente._dcasa_bloqueos()
            asistente.bloqueos = '\n'.join(f'• {b}' for b in bloqueos) or False
            if bloqueos:
                asistente.resumen = False
                continue
            filas = ''.join(f'<li>{escape(f)}</li>' for f in asistente._dcasa_que_pasa())
            asistente.resumen = Markup(f'<ul class="mb-0">{filas}</ul>')

    def action_cambiar(self):
        """Intercambia cuál queda y cuál se archiva."""
        self.ensure_one()
        self.write({'queda_id': self.sale_id.id, 'sale_id': self.queda_id.id})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'target': 'new', 'name': self.env._('Unir productos repetidos')}

    # ------------------------------------------------------------------
    # Unir
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_precios_proveedor(self, producto):
        return self.env['product.supplierinfo'].sudo().with_context(active_test=False).search([
            ('product_tmpl_id', '=', producto.product_tmpl_id.id),
            '|', ('product_id', '=', False), ('product_id', '=', producto.id)])

    def action_unir(self):
        self.ensure_one()
        exigir_catalogo(self.env)
        bloqueos = self._dcasa_bloqueos()
        if bloqueos:
            raise UserError('\n'.join(bloqueos))
        queda, sale = self.queda_id, self.sale_id
        plantilla_queda, plantilla_sale = queda.product_tmpl_id, sale.product_tmpl_id
        hecho = self._dcasa_que_pasa()
        self._dcasa_pasar_existencias(sale, queda)
        varias = plantilla_queda.product_variant_count > 1
        self._dcasa_precios_proveedor(sale).write({
            'product_tmpl_id': plantilla_queda.id, 'product_id': queda.id if varias else False})
        self.env['product.combo.item'].sudo().search([('product_id', '=', sale.id)]).write({'product_id': queda.id})
        Regla = self.env['product.pricelist.item'].sudo().with_context(active_test=False)
        Regla.search([('product_id', '=', sale.id)]).write(
            {'product_id': queda.id, 'product_tmpl_id': plantilla_queda.id})
        Regla.search([('product_tmpl_id', '=', plantilla_sale.id), ('product_id', '=', False)]).write(
            {'product_tmpl_id': plantilla_queda.id})
        if 'dcasa.premio' in self.env:
            self.env['dcasa.premio'].sudo().with_context(active_test=False).search(
                [('product_id', '=', sale.id)]).write({'product_id': queda.id})
        self._dcasa_pasar_fotos(plantilla_sale, plantilla_queda)
        self._dcasa_pasar_codigos(sale, queda)
        plantilla_sale.write({'active': False, 'dcasa_unido_a_id': plantilla_queda.id})
        quien = self.env.user.name
        lista = Markup(''.join(f'<li>{escape(f)}</li>' for f in hecho))
        plantilla_queda.message_post(body=Markup('<p>%s</p><ul>%s</ul>') % (
            self.env._('Se le unió «%(otra)s» (repetida), por %(quien)s:', otra=plantilla_sale.display_name,
                       quien=quien), lista), subtype_xmlid='mail.mt_note')
        plantilla_sale.message_post(body=Markup('<p>%s</p><ul>%s</ul>') % (
            self.env._('Se unió a «%(queda)s» y se archivó, por %(quien)s:', queda=plantilla_queda.display_name,
                       quien=quien), lista), subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window', 'res_model': 'product.template', 'res_id': plantilla_queda.id,
                'view_mode': 'form', 'target': 'current'}

    def _dcasa_pasar_existencias(self, sale, queda):
        """Un ajuste de inventario por cada lado, en la misma ubicación (lo hace Gerencia: dcasa_base lo exige)."""
        motivo = self.env._('Unión de productos: %(a)s → %(b)s', a=sale.display_name, b=queda.display_name)
        Quant = self.env['stock.quant'].with_context(inventory_mode=True, inventory_name=motivo)
        for quant in self._dcasa_existencias(sale):
            cantidad, ubicacion = quant.quantity, quant.location_id
            origen = quant.with_env(Quant.env)
            origen.write({'inventory_quantity': 0.0})
            self._dcasa_aplicar(origen)
            destino = Quant.search([('product_id', '=', queda.id), ('location_id', '=', ubicacion.id),
                                    ('lot_id', '=', False), ('package_id', '=', False), ('owner_id', '=', False)],
                                   limit=1)
            if destino:
                destino.write({'inventory_quantity': destino.quantity + cantidad})
            else:
                destino = Quant.create({'product_id': queda.id, 'location_id': ubicacion.id,
                                        'inventory_quantity': cantidad})
            self._dcasa_aplicar(destino)

    def _dcasa_aplicar(self, quant):
        """Aplica el ajuste; si Odoo pide resolver un conflicto (el conteo quedó viejo), no sigue."""
        resultado = quant.action_apply_inventory()
        if isinstance(resultado, dict):
            raise UserError(self.env._(
                'Las existencias de «%s» cambiaron mientras se unía: vuelve a intentarlo.',
                quant.product_id.display_name))

    def _dcasa_pasar_fotos(self, origen, destino):
        if not origen.image_1920:
            return
        Imagen = self.env['product.image'] if 'product.image' in self.env else None
        actuales = {destino.image_1920} | set(destino.product_template_image_ids.mapped('image_1920')) \
            if Imagen is not None else {destino.image_1920}
        if not destino.image_1920:
            destino.image_1920 = origen.image_1920
        elif Imagen is not None and origen.image_1920 not in actuales:
            Imagen.create({'name': origen.name, 'image_1920': origen.image_1920, 'product_tmpl_id': destino.id})
        if Imagen is None:
            return
        actuales = {destino.image_1920} | set(destino.product_template_image_ids.mapped('image_1920'))
        for imagen in origen.product_template_image_ids:
            if imagen.image_1920 and imagen.image_1920 not in actuales:
                Imagen.create({'name': imagen.name or origen.name, 'image_1920': imagen.image_1920,
                               'product_tmpl_id': destino.id})
                actuales.add(imagen.image_1920)

    def _dcasa_pasar_codigos(self, sale, queda):
        motivo = self.env._('Pasó a «%s» al unir productos repetidos', queda.display_name)
        if sale.barcode and not queda.barcode:
            codigo = sale.barcode
            sale.with_context(dcasa_etiqueta_retiro=motivo).write({'barcode': False})
            queda.with_context(dcasa_etiqueta_alta=self.env._('Unión de productos repetidos')).write(
                {'barcode': codigo})
        if sale.default_code and not queda.default_code:
            queda.write({'default_code': sale.default_code})
