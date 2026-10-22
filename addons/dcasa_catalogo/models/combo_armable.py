"""Combos cama + colchón que se arman en la venta (pedido de la dueña, 2026-10-22).

Antes había que crear un producto «COMBO …» por cada cama con cada colchón. Ahora la vendedora arma el combo en la
cotización: escoge la cama y el sistema le muestra los colchones de su medida con existencia. Cada pieza sigue siendo
su producto (el inventario baja bien y los reportes por producto no cambian).

Decisión de la dueña sobre el precio (por escrito, 2026-10-22): cada colchón, en cada medida (variante), tiene un
**precio en combo** que pone Gerencia. Si el colchón va en la misma venta junto con una cama de su misma medida, se
cobra a ese precio; si no tiene precio en combo, va a su precio normal (no se inventa ninguno). La cama va a su precio
normal.

Cómo se cumple en el servidor (no solo en la pantalla):

* **Qué es cama o colchón y su medida**: ``product.template.dcasa_tipo_combo`` (sugerido por el nombre) y
  ``product.product.dcasa_medida`` (del atributo «Tamaño» de la variante o, si no lo tiene, del nombre). Gerencia los
  corrige; nadie más (``_puede_cambiar_precios`` de dcasa_base).
* **El emparejamiento sale de lo que hay en la venta** (``reglas.emparejar_combos``): cada colchón con una cama de su
  medida, sin pasarse de las camas que hay (un camarote lleva 2 o 3 colchones: ``dcasa_colchones_por_cama``). Quitar o
  cambiar la cama, o subir los colchones de más, deja al colchón sin combo y vuelve solo a su precio normal.
* **El precio en combo es un precio que autorizó Gerencia, no una rebaja de la vendedora**: entra por
  ``_get_display_price`` (el mismo camino del precio de lista) y es el «precio autorizado» del tope de descuento
  (``_dcasa_precio_autorizado``): la vendedora puede rebajar sobre él hasta su tope, como sobre una tarifa. Escribirlo
  a mano en un colchón sin su cama choca con el tope como cualquier rebaja.
* **Se vuelve a calcular en cada cambio de líneas**: ``_dcasa_recalcular_combos`` corre justo antes de medir el tope
  del pedido (``_dcasa_validar_tope_del_pedido``, que dcasa_base llama al crear, cambiar o quitar líneas) y al
  reordenarlas. Si un colchón entra o sale del combo, su precio se vuelve a calcular (un precio puesto a mano en ese
  colchón se pierde: cambió de combo). Lo ya facturado y las ventas bloqueadas no se tocan.
* **La tienda en línea no arma combos** (su carrito no está en este pedido de la dueña; queda para que ella decida).
* Los combos de siempre (tipo «Combo» de Odoo) siguen igual: sus piezas no entran en este emparejamiento.
"""
from odoo import api, fields, models
from odoo.addons.dcasa_base.models.product import _puede_cambiar_precios
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

from .. import reglas

MEDIDAS = [(medida, medida) for medida in reglas.TAMANOS]
TIPOS = [('cama', 'Cama'), ('colchon', 'Colchón')]
ATRIBUTOS_DE_MEDIDA = ('tamano', 'medida')
SIN_RECALCULAR = 'dcasa_combo_sin_recalcular'
SIN_PRECIO_COMBO = 'dcasa_combo_sin_precio'
QUITANDO = 'dcasa_combo_quitando'   # ids de las líneas que se están quitando: ya no cuentan para emparejar
# Lo que cambia el emparejamiento y dcasa_base no mide en el tope (el orden de las líneas y la cama preferida).
# (y lo que guarda el propio emparejamiento: si alguien lo escribe a mano, se vuelve a calcular).
CAMPOS_DE_EMPAREJAR = {'sequence', 'dcasa_combo_cama_id', 'dcasa_combo_con_precio', 'dcasa_combo_ahorro_unitario'}
MAX_CANTIDAD = 20
MAX_RESULTADOS = 40
MAX_BUSCAR = 300


def _moneda(moneda, monto):
    return f'{moneda.symbol}{monto:,.2f}' if moneda.position != 'after' else f'{monto:,.2f} {moneda.symbol}'


def _aviso_gerencia(env):
    return AccessError(env._('Solo Gerencia cambia el precio en combo, la medida, si un producto es cama o colchón y '
                             'cuántos colchones lleva una cama.'))


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dcasa_tipo_combo = fields.Selection(
        TIPOS, string='Para armar combos', compute='_compute_dcasa_tipo_combo', store=True, readonly=False,
        index=True,
        help='Cama o colchón: así sale en «Armar combo» de la cotización. Se sugiere por el nombre del producto; '
             'Gerencia lo corrige. Vacío: no entra en los combos.')
    dcasa_colchones_por_cama = fields.Integer(
        string='Colchones que lleva', default=1,
        help='Cuántos colchones lleva esta cama en un combo: 1; en un camarote, 2 o 3. Si en la venta van más '
             'colchones de los que lleva la cama, los de más van a precio normal.')

    @api.depends('name', 'type')
    def _compute_dcasa_tipo_combo(self):
        for plantilla in self:
            if plantilla.type == 'combo':
                plantilla.dcasa_tipo_combo = False
                continue
            # Si el nombre no dice nada, se respeta lo que puso Gerencia.
            plantilla.dcasa_tipo_combo = reglas.tipo_combo_del_nombre(plantilla.name) or plantilla.dcasa_tipo_combo

    @api.constrains('dcasa_colchones_por_cama')
    def _check_dcasa_colchones_por_cama(self):
        for plantilla in self:
            if not 1 <= plantilla.dcasa_colchones_por_cama <= 6:
                raise ValidationError(self.env._('Una cama lleva de 1 a 6 colchones («%s»).', plantilla.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        if not _puede_cambiar_precios(self.env) and any(
                (vals.get('dcasa_colchones_por_cama') or 1) != 1 for vals in vals_list):
            raise _aviso_gerencia(self.env)
        return super().create(vals_list)

    def write(self, vals):
        self._dcasa_exigir_gerencia_combo(vals)
        return super().write(vals)

    def _dcasa_exigir_gerencia_combo(self, vals):
        """Quien no es Gerencia no cambia el tipo ni los colchones por cama. Sí puede guardar el tipo que sugiere el
        nombre (la pantalla lo manda al renombrar un producto, y renombrar sí le toca a la vendedora)."""
        if _puede_cambiar_precios(self.env):
            return
        for plantilla in self:
            if 'dcasa_tipo_combo' in vals:
                nuevo = vals['dcasa_tipo_combo'] or False
                sugerido = reglas.tipo_combo_del_nombre(vals.get('name', plantilla.name)) or False
                if vals.get('type', plantilla.type) == 'combo':
                    sugerido = False
                if nuevo not in ((plantilla.dcasa_tipo_combo or False), sugerido):
                    raise _aviso_gerencia(self.env)
            if 'dcasa_colchones_por_cama' in vals and \
                    (vals['dcasa_colchones_por_cama'] or 1) != plantilla.dcasa_colchones_por_cama:
                raise _aviso_gerencia(self.env)

    def action_dcasa_precios_combo(self):
        """Botón de la ficha: la lista «Camas y colchones para combos» con las medidas de este producto."""
        self.ensure_one()
        accion = self.env['ir.actions.act_window']._for_xml_id('dcasa_catalogo.accion_precios_combo')
        accion['domain'] = [('product_tmpl_id', '=', self.id)]
        accion['context'] = {'search_default_por_medida': 0}
        accion['display_name'] = self.env._('Medidas y precio en combo: %s', self.name)
        return accion


class ProductProduct(models.Model):
    _inherit = 'product.product'

    dcasa_medida = fields.Selection(
        MEDIDAS, string='Medida', compute='_compute_dcasa_medida', store=True, readonly=False, index=True,
        help='Twin, Full, Queen o King. Sale del «Tamaño» de la variante o, si no lo tiene, del nombre (una cama '
             '«Cama king de metal» es King). Con ella el combo junta cada cama con los colchones de su medida. '
             'Vacía: la pone Gerencia.')
    dcasa_precio_combo = fields.Float(
        string='Precio en combo', digits='Product Price', copy=False,
        help='Precio de este colchón (sin ITBMS) cuando va en la misma venta con una cama de su misma medida. Lo pone '
             'Gerencia; tiene que ser menor que el precio normal. Vacío: el colchón va a su precio normal.')
    dcasa_combo_ahorro = fields.Float(
        string='Ahorro', compute='_compute_dcasa_combo_ahorro', digits='Product Price',
        help='Precio normal menos precio en combo (sin ITBMS).')
    dcasa_combo_aviso = fields.Char(string='Revisar', compute='_compute_dcasa_combo_ahorro')

    @api.depends('product_template_attribute_value_ids', 'product_tmpl_id.name', 'product_tmpl_id.dcasa_tipo_combo')
    def _compute_dcasa_medida(self):
        for variante in self:
            variante.dcasa_medida = variante._dcasa_medida_sugerida() or variante.dcasa_medida

    def _dcasa_medida_sugerida(self, nombre=None):
        """La medida del atributo «Tamaño» (o «Medida») de la variante; si no lo tiene, la del nombre."""
        self.ensure_one()
        for valor in self.product_template_attribute_value_ids:
            if reglas.normalizar(valor.attribute_id.name) in ATRIBUTOS_DE_MEDIDA:
                medida = reglas.medida_de_valor(valor.name)
                if medida:
                    return medida
        plantilla = self.product_tmpl_id
        return reglas.medida_del_nombre(nombre or plantilla.name, plantilla.dcasa_tipo_combo)

    @api.depends('dcasa_precio_combo', 'lst_price', 'dcasa_medida', 'dcasa_tipo_combo')
    def _compute_dcasa_combo_ahorro(self):
        for variante in self:
            ahorro, aviso = 0.0, False
            if variante.dcasa_tipo_combo and not variante.dcasa_medida:
                aviso = self.env._('Falta la medida')
            elif variante.dcasa_tipo_combo == 'colchon':
                if not variante.dcasa_precio_combo:
                    aviso = self.env._('Sin precio en combo: va a precio normal')
                elif float_compare(variante.dcasa_precio_combo, variante.lst_price, precision_digits=2) >= 0:
                    aviso = self.env._('El precio en combo ya no es menor que el normal: revísalo')
                else:
                    ahorro = variante.lst_price - variante.dcasa_precio_combo
            variante.dcasa_combo_ahorro = ahorro
            variante.dcasa_combo_aviso = aviso

    @api.constrains('dcasa_precio_combo')
    def _check_dcasa_precio_combo(self):
        for variante in self:
            precio = variante.dcasa_precio_combo
            if not precio:
                continue
            if precio < 0:
                raise ValidationError(self.env._(
                    'El precio en combo tiene que ser mayor que 0 (o vacío: el colchón va a su precio normal).'))
            if variante.dcasa_tipo_combo != 'colchon':
                raise ValidationError(self.env._(
                    '«%s» no está marcado como colchón: solo los colchones llevan precio en combo.',
                    variante.display_name))
            if float_compare(precio, variante.lst_price, precision_digits=2) >= 0:
                raise ValidationError(self.env._(
                    'El precio en combo de «%(producto)s» tiene que ser menor que su precio normal (%(normal)s).',
                    producto=variante.display_name,
                    normal=_moneda(variante.currency_id or self.env.company.currency_id, variante.lst_price)))

    @api.model_create_multi
    def create(self, vals_list):
        if not _puede_cambiar_precios(self.env) and any(vals.get('dcasa_precio_combo') for vals in vals_list):
            raise _aviso_gerencia(self.env)
        return super().create(vals_list)

    def write(self, vals):
        self._dcasa_exigir_gerencia_combo(vals)
        return super().write(vals)

    def _dcasa_exigir_gerencia_combo(self, vals):
        """El precio en combo y la medida los cambia Gerencia. La medida que sugiere el «Tamaño» o el nombre sí se
        puede guardar (la pantalla la manda al renombrar)."""
        if _puede_cambiar_precios(self.env):
            return
        for variante in self:
            if 'dcasa_precio_combo' in vals and float_compare(
                    vals['dcasa_precio_combo'] or 0.0, variante.dcasa_precio_combo, precision_digits=2):
                raise _aviso_gerencia(self.env)
            if 'dcasa_medida' in vals:
                nueva = vals['dcasa_medida'] or False
                if nueva not in ((variante.dcasa_medida or False), variante._dcasa_medida_sugerida() or False):
                    raise _aviso_gerencia(self.env)

    def _dcasa_combo_precio_normal(self, orden=None):
        """Precio normal de la variante para una venta (su tarifa), en la moneda de la venta y sin ITBMS."""
        self.ensure_one()
        if orden and orden.pricelist_id:
            return orden.pricelist_id._get_product_price(
                self, 1.0, currency=orden.currency_id, date=orden.date_order or fields.Datetime.now())
        return self.lst_price

    def _dcasa_combo_colchones(self, todos=False):
        """Los colchones de la medida de esta cama (a la venta); sin ``todos``, solo los que tienen existencia."""
        self.ensure_one()
        if self.dcasa_tipo_combo != 'cama' or not self.dcasa_medida:
            return self.browse()
        colchones = self.search([('dcasa_tipo_combo', '=', 'colchon'), ('dcasa_medida', '=', self.dcasa_medida),
                                 ('sale_ok', '=', True), ('type', '!=', 'combo')])
        if not todos:
            colchones = colchones.filtered(lambda c: not c.is_storable or c.free_qty > 0)
        return colchones


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # Emparejar y recalcular (reglas en el servidor)
    # ------------------------------------------------------------------

    def _dcasa_combos_armables(self):
        """En esta venta se arman combos: no en el carrito de la tienda en línea ni en una venta cancelada."""
        self.ensure_one()
        return not self.website_id and self.state != 'cancel'

    @staticmethod
    def _dcasa_clave_linea(linea):
        return linea._origin.id or linea.id

    def _dcasa_emparejar(self, lineas=None):
        """``{línea del colchón: (línea de la cama, con_precio)}`` de esta venta (``reglas.emparejar_combos``).

        Solo cuentan las líneas de producto con cantidad: ni secciones, ni anticipos, ni los combos de Odoo y sus
        piezas. ``lineas`` permite medir la venta sin las que se van a quitar (o con una que se está creando)."""
        self.ensure_one()
        if not self._dcasa_combos_armables():
            return {}
        lineas = self.order_line if lineas is None else lineas
        candidatas = lineas.filtered(
            lambda ln: not ln.display_type and ln.product_id and not ln.combo_item_id and not ln.is_downpayment
            and ln.product_id.type != 'combo' and ln.product_uom_qty > 0
            and ln.product_id.dcasa_tipo_combo in ('cama', 'colchon') and ln.product_id.dcasa_medida)
        candidatas = candidatas.sorted(lambda ln: (ln.sequence, ln._origin.id or 10 ** 12))
        clave = self._dcasa_clave_linea
        por_clave, camas, colchones = {}, [], []
        for linea in candidatas:
            producto = linea.product_id
            por_clave[clave(linea)] = linea
            if producto.dcasa_tipo_combo == 'cama':
                camas.append({'clave': clave(linea), 'medida': producto.dcasa_medida,
                              'capacidad': linea.product_uom_qty * max(producto.dcasa_colchones_por_cama, 1)})
            else:
                preferida = linea.dcasa_combo_cama_id
                colchones.append({
                    'clave': clave(linea), 'medida': producto.dcasa_medida, 'cantidad': linea.product_uom_qty,
                    'con_precio': producto.dcasa_precio_combo > 0 and linea.product_uom_id == producto.uom_id,
                    'preferida': clave(preferida) if preferida else None})
        pares = reglas.emparejar_combos(camas, colchones)
        return {por_clave[colchon]: (por_clave[cama], con_precio) for colchon, (cama, con_precio) in pares.items()}

    def _dcasa_recalcular_combos(self, sin=None):
        """Deja cada colchón con su cama y su precio al día después de un cambio de líneas.

        Si un colchón entra o sale del precio en combo, su precio se vuelve a calcular (con la tarifa, como al
        escogerlo). Lo ya facturado y las ventas bloqueadas no se tocan. ``sin``: líneas que se van a quitar."""
        if self.env.context.get(SIN_RECALCULAR):
            return
        vacia = self.env['sale.order.line']
        for orden in self.exists():
            lineas = orden.order_line - (sin or vacia)
            pares = orden._dcasa_emparejar(lineas)
            for linea in lineas.filtered(lambda ln: not ln.display_type and ln.product_id):
                if linea.qty_invoiced or orden.locked:
                    continue
                cama, con_precio = pares.get(linea, (vacia, False))
                callada = linea.with_context(**{SIN_RECALCULAR: True, QUITANDO: (sin or vacia).ids})
                vals = {}
                if linea.dcasa_combo_cama_id != cama:
                    vals['dcasa_combo_cama_id'] = cama.id
                if linea.dcasa_combo_con_precio != con_precio:
                    vals['dcasa_combo_con_precio'] = con_precio
                if vals:
                    callada.write(vals)
                if 'dcasa_combo_con_precio' in vals and not linea.is_downpayment:
                    callada._dcasa_reponer_precio()
                ahorro = callada._dcasa_ahorro_unitario_combo() if con_precio else 0.0
                if float_compare(linea.dcasa_combo_ahorro_unitario, ahorro, precision_digits=4):
                    callada.write({'dcasa_combo_ahorro_unitario': ahorro})

    def _dcasa_validar_tope_del_pedido(self, antes=None):
        # dcasa_base mide el tope al crear, cambiar o quitar líneas: antes, cada colchón queda con su precio justo
        # (si se quitó la cama, el colchón ya volvió a su precio normal y no se cuenta como rebaja de la vendedora).
        self._dcasa_recalcular_combos()
        return super()._dcasa_validar_tope_del_pedido(antes)

    def _dcasa_ahorro_combos(self):
        """Lo que el cliente ahorra por los combos de esta venta (sin ITBMS, como los precios del papel)."""
        self.ensure_one()
        return sum(linea.dcasa_combo_ahorro for linea in self.order_line if linea.dcasa_combo_con_precio)

    # ------------------------------------------------------------------
    # Panel «Armar combo» (pantalla de la cotización y Brian)
    # ------------------------------------------------------------------

    def action_dcasa_armar_combo(self):
        """Botón «Armar combo» de la cotización: abre el panel encima de la cotización."""
        self.ensure_one()
        self._dcasa_combo_exigir_editable()
        return {
            'type': 'ir.actions.client', 'tag': 'dcasa_armar_combo', 'target': 'new',
            'name': self.env._('Armar combo cama + colchón'),
            'params': {'order_id': self.id},
            'context': {'dialog_size': 'extra-large', 'footer': False},
        }

    def _dcasa_combo_exigir_editable(self):
        self.ensure_one()
        self.check_access('write')
        if self.website_id:
            raise UserError(self.env._('Este pedido es de la tienda en línea: el combo se arma en una cotización.'))
        if self.state not in ('draft', 'sent') or self.locked:
            raise UserError(self.env._(
                '%s ya no es una cotización: los combos se arman antes de confirmar la venta.', self.name))

    def _dcasa_combo_variante(self, producto_id, tipo):
        variante = self.env['product.product'].browse(int(producto_id or 0)).exists()
        if not variante or variante.dcasa_tipo_combo != tipo or not variante.sale_ok:
            raise UserError(self.env._(
                'Ese producto ya no está a la venta como %s. Vuelve a buscarlo.',
                dict(TIPOS).get(tipo, tipo).lower()))
        return variante

    def _dcasa_combo_linea(self, linea_id, tipo):
        linea = self.order_line.filtered(lambda ln: ln.id == int(linea_id or 0))
        if not linea or linea.product_id.dcasa_tipo_combo != tipo:
            raise UserError(self.env._('Esa línea ya no está en la cotización: vuelve a abrir «Armar combo».'))
        return linea

    @staticmethod
    def _dcasa_combo_cantidad(cantidad):
        try:
            cantidad = 1 if cantidad is None or cantidad is False else int(cantidad)
        except (TypeError, ValueError):
            cantidad = 0
        if not 1 <= cantidad <= MAX_CANTIDAD:
            raise UserError(f'La cantidad de combos va de 1 a {MAX_CANTIDAD}.')
        return cantidad

    def _dcasa_combo_producto(self, variante, gerencia=False):
        """Una cama o un colchón como lo pinta el panel: foto, nombre, medida, precio, disponibles y características."""
        detalle = [texto for texto in (variante.dcasa_medidas, (variante.description_sale or '').strip()) if texto]
        fila = {
            'id': variante.id,
            'nombre': variante.with_context(display_default_code=False).display_name,
            'codigo': variante.default_code or '',
            'medida': variante.dcasa_medida or '',
            'precio': variante._dcasa_combo_precio_normal(self),
            'disponibles': variante.free_qty if variante.is_storable else None,
            'caracteristicas': ' · '.join(detalle)[:220],
            'imagen': f'/web/image/product.product/{variante.id}/image_256' if variante.image_128 else '',
        }
        if variante.dcasa_tipo_combo == 'colchon':
            compania = self.company_id or self.env.company
            precio_combo = compania.currency_id._convert(
                variante.dcasa_precio_combo, self.currency_id or compania.currency_id, compania,
                self.date_order or fields.Datetime.now())
            if precio_combo > 0 and float_compare(precio_combo, fila['precio'], precision_digits=2) < 0:
                fila.update({'precio_combo': precio_combo, 'ahorro': fila['precio'] - precio_combo})
            else:
                fila.update({'precio_combo': None, 'ahorro': 0.0})
        if gerencia and variante.dcasa_combo:
            # Texto del Excel («Combo con colchón $349.99»): solo de referencia para Gerencia, nunca para calcular.
            fila['referencia_excel'] = variante.dcasa_combo
        return fila

    def _dcasa_combo_linea_panel(self, linea):
        fila = self._dcasa_combo_producto(linea.product_id)
        fila.update({
            'linea_id': linea.id,
            'cantidad': linea.product_uom_qty,
            'precio_linea': linea.price_unit,
            'descuento': linea.discount,
            'subtotal': linea.price_subtotal,
            'con_precio': linea.dcasa_combo_con_precio,
            'ahorro_linea': linea.dcasa_combo_ahorro if linea.dcasa_combo_con_precio else 0.0,
        })
        return fila

    def dcasa_combo_panel(self):
        """Lo que muestra el panel: los combos de la cotización, las camas sin colchón y los colchones sueltos."""
        self.ensure_one()
        self.check_access('read')
        pares = self._dcasa_emparejar()
        por_cama = {}
        for colchon, (cama, _con_precio) in pares.items():
            por_cama.setdefault(cama, self.env['sale.order.line'])
            por_cama[cama] |= colchon
        lineas = self.order_line.filtered(
            lambda ln: not ln.display_type and not ln.combo_item_id and ln.product_id.type != 'combo')
        combos, camas_solas, colchones_sueltos = [], [], []
        for linea in lineas.sorted(lambda ln: (ln.sequence, ln.id)):
            tipo = linea.product_id.dcasa_tipo_combo
            if tipo == 'cama' and linea in por_cama:
                colchones = por_cama[linea].sorted(lambda ln: (ln.sequence, ln.id))
                piezas = linea | colchones
                combos.append({
                    'cama': self._dcasa_combo_linea_panel(linea),
                    'colchones': [self._dcasa_combo_linea_panel(c) for c in colchones],
                    'total': sum(piezas.mapped('price_subtotal')),
                    'ahorro': sum(c.dcasa_combo_ahorro for c in colchones if c.dcasa_combo_con_precio),
                })
            elif tipo == 'cama':
                camas_solas.append(self._dcasa_combo_linea_panel(linea))
            elif tipo == 'colchon' and linea not in pares:
                fila = self._dcasa_combo_linea_panel(linea)
                fila['motivo'] = (self.env._('Falta la medida de este colchón: pídele a Gerencia que la ponga.')
                                  if not linea.product_id.dcasa_medida else
                                  self.env._('Va a precio normal: no hay una cama %s libre en esta cotización.',
                                             linea.product_id.dcasa_medida))
                colchones_sueltos.append(fila)
        return {
            'orden': {'id': self.id, 'nombre': self.name, 'cliente': self.partner_id.display_name or '',
                      'moneda_id': self.currency_id.id,
                      'editable': self.state in ('draft', 'sent') and not self.locked and not self.website_id},
            'combos': combos,
            'camas_solas': camas_solas,
            'colchones_sueltos': colchones_sueltos,
            'ahorro_total': self._dcasa_ahorro_combos(),
            'medidas': list(reglas.TAMANOS),
        }

    def dcasa_combo_camas(self, texto='', medida=''):
        """Buscador de camas del panel: por nombre, código o medida («cama king»). Las que tienen existencia
        primero."""
        self.ensure_one()
        self.check_access('read')
        dominio = [('dcasa_tipo_combo', '=', 'cama'), ('sale_ok', '=', True), ('type', '!=', 'combo')]
        if medida in reglas.TAMANOS:
            dominio.append(('dcasa_medida', '=', medida))
        texto = ' '.join(str(texto or '').split())[:80]
        if texto:
            dominio.append(('display_name', 'ilike', texto))
        camas = self.env['product.product'].search(dominio, limit=MAX_BUSCAR)
        gerencia = _puede_cambiar_precios(self.env)
        filas = [self._dcasa_combo_producto(cama, gerencia) for cama in camas]
        filas.sort(key=lambda f: (0 if f['disponibles'] is None or f['disponibles'] > 0 else 1, f['nombre'].lower()))
        return {'camas': filas[:MAX_RESULTADOS], 'hay_mas': len(filas) > MAX_RESULTADOS}

    def dcasa_combo_colchones(self, cama_id, todos=False):
        """Los colchones de la medida de la cama, con existencia (``todos``: también los agotados), con su precio
        normal, su precio en combo y el ahorro. Primero los que tienen precio en combo."""
        self.ensure_one()
        self.check_access('read')
        cama = self._dcasa_combo_variante(cama_id, 'cama')
        gerencia = _puede_cambiar_precios(self.env)
        respuesta = {'cama': self._dcasa_combo_producto(cama, gerencia), 'colchones': [], 'agotados': 0,
                     'falta_medida': not cama.dcasa_medida}
        if not cama.dcasa_medida:
            return respuesta
        con_existencia = cama._dcasa_combo_colchones()
        colchones = cama._dcasa_combo_colchones(todos=True) if todos else con_existencia
        filas = [self._dcasa_combo_producto(colchon) for colchon in colchones]
        filas.sort(key=lambda f: (0 if f['precio_combo'] else 1, f['precio_combo'] or f['precio'],
                                  0 if f['imagen'] else 1, f['nombre'].lower()))
        respuesta.update({'colchones': filas[:MAX_RESULTADOS],
                          'agotados': 0 if todos else len(cama._dcasa_combo_colchones(todos=True) - con_existencia)})
        return respuesta

    def dcasa_combo_agregar(self, cama_id=False, colchon_id=False, cantidad=1, cama_linea_id=False):
        """Agrega el combo: la cama y, debajo, el colchón a precio en combo. Con ``cama_linea_id``, solo el colchón
        para una cama que ya está en la cotización (tantos como lleva esa cama)."""
        self._dcasa_combo_exigir_editable()
        colchon = self._dcasa_combo_variante(colchon_id, 'colchon')
        Linea = self.env['sale.order.line']
        if cama_linea_id:
            cama_linea = self._dcasa_combo_linea(cama_linea_id, 'cama')
            cama = cama_linea.product_id
            cantidad = cama_linea.product_uom_qty
            secuencia = cama_linea.sequence
        else:
            cama = self._dcasa_combo_variante(cama_id, 'cama')
            cantidad = self._dcasa_combo_cantidad(cantidad)
            secuencia = max(self.order_line.mapped('sequence') or [0]) + 1
            cama_linea = Linea
        self._dcasa_combo_misma_medida(cama, colchon)
        if not cama_linea:
            cama_linea = Linea.create({'order_id': self.id, 'product_id': cama.id, 'product_uom_qty': cantidad,
                                       'sequence': secuencia})
        Linea.create({'order_id': self.id, 'product_id': colchon.id, 'sequence': secuencia,
                      'product_uom_qty': cantidad * max(cama.dcasa_colchones_por_cama, 1),
                      'dcasa_combo_cama_id': cama_linea.id})
        return self.dcasa_combo_panel()

    def _dcasa_combo_misma_medida(self, cama, colchon):
        if not cama.dcasa_medida:
            raise UserError(self.env._('Falta la medida de «%s»: pídele a Gerencia que la ponga.', cama.display_name))
        if colchon.dcasa_medida != cama.dcasa_medida:
            raise UserError(self.env._(
                'El colchón «%(colchon)s» es %(medida_colchon)s y la cama es %(medida_cama)s: escoge un colchón de la '
                'misma medida.', colchon=colchon.display_name, medida_colchon=colchon.dcasa_medida or '¿?',
                medida_cama=cama.dcasa_medida))

    def dcasa_combo_cambiar(self, cama_linea_id, cama_id=False, colchon_id=False, colchon_linea_id=False):
        """Cambia la cama y/o el colchón de un combo de la cotización. El precio de cada pieza se vuelve a calcular
        (el colchón vuelve a su precio en combo o normal según su nueva cama)."""
        self._dcasa_combo_exigir_editable()
        cama_linea = self._dcasa_combo_linea(cama_linea_id, 'cama')
        colchon_linea = self._dcasa_combo_linea(colchon_linea_id, 'colchon') if colchon_linea_id \
            else cama_linea.dcasa_combo_colchon_ids.sorted('sequence')[:1]
        cama = self._dcasa_combo_variante(cama_id, 'cama') if cama_id else cama_linea.product_id
        colchon = self._dcasa_combo_variante(colchon_id, 'colchon') if colchon_id else colchon_linea.product_id
        if colchon:
            self._dcasa_combo_misma_medida(cama, colchon)
        if cama != cama_linea.product_id:
            cama_linea.write({'product_id': cama.id})
            cama_linea._dcasa_reponer_precio()
        if colchon_linea and colchon != colchon_linea.product_id:
            colchon_linea.write({'product_id': colchon.id, 'dcasa_combo_cama_id': cama_linea.id})
            colchon_linea._dcasa_reponer_precio()
            self._dcasa_recalcular_combos()
        return self.dcasa_combo_panel()

    def dcasa_combo_quitar(self, cama_linea_id, colchon_linea_id=False):
        """Quita el combo: la cama y su colchón (o solo ese colchón, si se dice cuál)."""
        self._dcasa_combo_exigir_editable()
        if colchon_linea_id and not cama_linea_id:
            self._dcasa_combo_linea(colchon_linea_id, 'colchon').unlink()
            return self.dcasa_combo_panel()
        cama_linea = self._dcasa_combo_linea(cama_linea_id, 'cama')
        colchones = self._dcasa_combo_linea(colchon_linea_id, 'colchon') if colchon_linea_id \
            else cama_linea.dcasa_combo_colchon_ids
        (cama_linea | colchones).unlink()
        return self.dcasa_combo_panel()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_combo_cama_id = fields.Many2one(
        'sale.order.line', string='En combo con', ondelete='set null', copy=False, readonly=True,
        index='btree_not_null', help='La cama de esta misma venta con la que va este colchón (la pone el sistema).')
    dcasa_combo_colchon_ids = fields.One2many('sale.order.line', 'dcasa_combo_cama_id', string='Colchones del combo')
    dcasa_combo_con_precio = fields.Boolean(
        string='Con precio en combo', copy=False, readonly=True,
        help='El colchón va con una cama de su medida y lleva el precio en combo que puso Gerencia.')
    dcasa_combo_ahorro_unitario = fields.Float(
        string='Ahorro por unidad', digits='Product Price', copy=False, readonly=True,
        help='Precio normal menos precio en combo de una unidad (sin ITBMS), al momento de armar el combo.')
    dcasa_combo_ahorro = fields.Monetary(
        string='Ahorro del combo', compute='_compute_dcasa_combo', currency_field='currency_id')
    dcasa_combo_texto = fields.Char(string='Combo', compute='_compute_dcasa_combo')

    @api.depends('dcasa_combo_cama_id', 'dcasa_combo_colchon_ids', 'dcasa_combo_con_precio',
                 'dcasa_combo_ahorro_unitario', 'product_uom_qty', 'currency_id')
    def _compute_dcasa_combo(self):
        for linea in self:
            ahorro = linea.dcasa_combo_ahorro_unitario * linea.product_uom_qty if linea.dcasa_combo_con_precio else 0.0
            linea.dcasa_combo_ahorro = ahorro
            moneda = linea.currency_id or linea.company_id.currency_id or self.env.company.currency_id
            if linea.dcasa_combo_cama_id:
                if not linea.dcasa_combo_con_precio:
                    linea.dcasa_combo_texto = self.env._('Combo · sin precio en combo')
                elif ahorro > 0:
                    linea.dcasa_combo_texto = self.env._('Combo · ahorras %s', _moneda(moneda, ahorro))
                else:
                    linea.dcasa_combo_texto = self.env._('Combo')
            elif linea.dcasa_combo_colchon_ids:
                linea.dcasa_combo_texto = self.env._('Combo')
            else:
                linea.dcasa_combo_texto = False

    # --- Precio -----------------------------------------------------------------------

    def _dcasa_precio_combo(self):
        """El precio en combo que le toca a esta línea (moneda de la venta, sin ITBMS) o ``None``: es un colchón con
        precio en combo y en la venta hay una cama libre de su medida."""
        self.ensure_one()
        producto = self.product_id
        if self.env.context.get(SIN_PRECIO_COMBO) or not self.order_id or not producto \
                or producto.dcasa_tipo_combo != 'colchon' or producto.dcasa_precio_combo <= 0:
            return None
        lineas = self.order_id.order_line.filtered(lambda ln: ln.id not in self.env.context.get(QUITANDO, ()))
        if self not in lineas:
            lineas |= self
        par = self.order_id._dcasa_emparejar(lineas).get(self)
        if not par or not par[1]:
            return None
        compania = self.company_id or self.order_id.company_id or self.env.company
        moneda = self.currency_id or compania.currency_id
        fecha = self.order_id.date_order or fields.Datetime.now()
        return compania.currency_id._convert(producto.dcasa_precio_combo, moneda, compania, fecha, round=False)

    def _get_display_price(self):
        precio = super()._get_display_price()
        combo = self._dcasa_precio_combo()
        # Si la tarifa ya da un precio menor, se queda el de la tarifa: el combo nunca encarece.
        return combo if combo is not None and combo < precio else precio

    def _dcasa_con_impuestos(self, precio):
        linea = self.with_company(self.company_id)
        return linea.product_id._get_tax_included_unit_price_from_price(
            precio,
            product_taxes=linea.product_id.taxes_id._filter_taxes_by_company(linea.company_id),
            fiscal_position=linea.order_id.fiscal_position_id,
        )

    def _dcasa_precio_autorizado(self):
        """El precio en combo lo autorizó Gerencia: no cuenta como rebaja de la vendedora (sí lo que rebaje encima)."""
        autorizado = super()._dcasa_precio_autorizado()
        combo = self._dcasa_precio_combo()
        if combo is None:
            return autorizado
        return min(autorizado, self._dcasa_con_impuestos(combo))

    def _dcasa_reponer_precio(self):
        """El precio de la línea como lo calcula Odoo al escoger el producto (tarifa y precio en combo). Con
        ``sale_write_from_compute``: si no, Odoo descarta el ``technical_price_unit`` y la línea queda como «precio a
        mano» (ya no se recalcularía nunca más)."""
        for linea in self:
            linea.with_context(sale_write_from_compute=True)._reset_price_unit()

    def _dcasa_ahorro_unitario_combo(self):
        """Precio normal menos precio en combo de una unidad, en la misma base que ``price_unit``."""
        self.ensure_one()
        normal = self.with_context(**{SIN_PRECIO_COMBO: True})._get_display_price()
        combo = self._get_display_price()
        return max(self._dcasa_con_impuestos(normal) - self._dcasa_con_impuestos(combo), 0.0)

    # --- Guardar ----------------------------------------------------------------------

    def write(self, vals):
        resultado = super().write(vals)
        # El tope (dcasa_base) ya recalculó los combos si cambió el producto, la cantidad o el precio; el orden de
        # las líneas y la cama preferida no los mide el tope.
        if CAMPOS_DE_EMPAREJAR & set(vals) and not self.env.context.get(SIN_RECALCULAR):
            self.order_id._dcasa_recalcular_combos()
        return resultado

    def unlink(self):
        # Antes de quitar la cama, su colchón vuelve a su precio normal: así el tope del pedido, que se mide al
        # quitar, ya ve el precio justo.
        ordenes = self.order_id
        if not self.env.context.get(SIN_RECALCULAR):
            ordenes._dcasa_recalcular_combos(sin=self)
        return super().unlink()

    def _prepare_invoice_line(self, **optional_values):
        valores = super()._prepare_invoice_line(**optional_values)
        if self.display_type:
            return valores
        if self.dcasa_combo_cama_id:
            valores['dcasa_combo_rol'] = 'colchon'
            valores['dcasa_combo_ahorro_unitario'] = self.dcasa_combo_ahorro_unitario \
                if self.dcasa_combo_con_precio else 0.0
        elif self.dcasa_combo_colchon_ids:
            valores['dcasa_combo_rol'] = 'cama'
        return valores

    def _dcasa_texto_combo(self):
        """«Combo cama + colchón» (y en el colchón, «· ahorras $41.00»): para el papel y la página del cliente."""
        self.ensure_one()
        if not (self.dcasa_combo_cama_id or self.dcasa_combo_colchon_ids):
            return ''
        texto = self.env._('Combo cama + colchón')
        if self.dcasa_combo_ahorro > 0:
            moneda = self.currency_id or self.order_id.currency_id
            texto = self.env._('%(combo)s · ahorras %(ahorro)s', combo=texto,
                               ahorro=_moneda(moneda, self.dcasa_combo_ahorro))
        return texto

    def _dcasa_etiqueta(self):
        return super()._dcasa_etiqueta() or self._dcasa_texto_combo()

    def action_dcasa_armar_combo(self):
        """Botón «Armar combo» junto a «Agregar un producto» (la lista de líneas lo llama con ``order_id``)."""
        orden = self.env['sale.order'].browse(self.env.context.get('order_id')).exists()
        if not orden:
            raise UserError(self.env._('Guarda la cotización (con su cliente) y vuelve a tocar «Armar combo».'))
        return orden.action_dcasa_armar_combo()


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _dcasa_ahorro_combos(self):
        """Lo que el cliente ahorra por combos en esta factura (sin ITBMS). Solo en facturas, no en notas de
        crédito."""
        self.ensure_one()
        if self.move_type != 'out_invoice':
            return 0.0
        return sum(linea.dcasa_combo_ahorro_unitario * linea.quantity for linea in self.invoice_line_ids
                   if linea.dcasa_combo_rol == 'colchon')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    dcasa_combo_rol = fields.Selection(
        [('cama', 'Cama del combo'), ('colchon', 'Colchón del combo')], string='Combo', copy=False, readonly=True)
    dcasa_combo_ahorro_unitario = fields.Float(
        string='Ahorro por unidad (combo)', digits='Product Price', copy=False, readonly=True)

    def _dcasa_etiqueta(self):
        etiqueta = super()._dcasa_etiqueta()
        if etiqueta or not self.dcasa_combo_rol or self.move_id.move_type != 'out_invoice':
            return etiqueta
        texto = self.env._('Combo cama + colchón')
        ahorro = self.dcasa_combo_ahorro_unitario * self.quantity
        if self.dcasa_combo_rol == 'colchon' and ahorro > 0:
            texto = self.env._('%(combo)s · ahorras %(ahorro)s', combo=texto,
                               ahorro=_moneda(self.currency_id or self.move_id.currency_id, ahorro))
        return texto
