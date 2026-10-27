"""Bitácora de bodega: cada ajuste de existencias con el antes → después, el motivo y quién (etapa 4).

Dónde se anota: en ``stock.quant._apply_inventory``, por donde pasan TODOS los ajustes a mano (Inventario físico,
Escáner › Contar, Brian), más «deshacer un ajuste» (``stock.move.line.action_revert_inventory``) y las mermas
(``merma.py``). Solo se anota lo que cambió la existencia (un conteo que coincide no es un ajuste).

El motivo es obligatorio: el «Aplicar» del Inventario físico abre una ventana que lo pide (vacía, sin el «Inventario
físico» de Odoo de fábrica); el Escáner manda «Conteo con lector (quién)» y Brian manda el que le dice la persona. Sin
motivo, el ajuste no se hace. Lo que corre el sistema sin persona detrás (una carga del catálogo) queda como «Ajuste
del sistema».

La bitácora no se edita ni se borra (ni Gerencia): la escribe el sistema. La lee Gerencia (decisión 5 del 16/10: la
Vendedora no).

Además se cierra el hueco que quedaba del Inventario físico (etapa 1 y decisión 6): ningún movimiento hacia o desde
«Ajuste de inventario» o «Desecho» (ubicaciones de tipo ``inventory``) lo crea quien no es Gerencia, ni por RPC; y
«Deshacer el ajuste» del historial de movimientos también es solo de Gerencia.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

GRUPO_AJUSTA = 'stock.group_stock_manager'
ORIGENES = [
    ('inventario_fisico', 'Inventario físico'),
    ('escaner', 'Escáner › Contar'),
    ('brian', 'Brian'),
    ('deshacer', 'Deshacer un ajuste'),
    ('merma', 'Merma, daño, muestra o regalo'),
    ('sistema', 'El sistema'),
    ('otro', 'Otro'),
]
PREFIJO_ESCANER = 'Conteo con lector'
MOTIVO_SISTEMA = 'Ajuste del sistema'


def _motivo(env):
    """El motivo que trae la llamada (el de la ventana, el del Escáner o el de Brian), o ``''``."""
    return (env.context.get('dcasa_motivo') or env.context.get('inventory_name') or '').strip()


class DcasaBitacoraBodega(models.Model):
    _name = 'dcasa.bitacora.bodega'
    _description = 'Bitácora de bodega (ajustes de existencias)'
    _order = 'fecha desc, id desc'
    _rec_name = 'producto_id'

    fecha = fields.Datetime('Cuándo', required=True, readonly=True, default=fields.Datetime.now, index=True)
    usuario_id = fields.Many2one('res.users', 'Quién', required=True, readonly=True, index=True)
    producto_id = fields.Many2one('product.product', 'Producto', required=True, readonly=True, index=True)
    ubicacion_id = fields.Many2one('stock.location', 'Dónde', readonly=True)
    antes = fields.Float('Antes', readonly=True, digits='Product Unit')
    despues = fields.Float('Después', readonly=True, digits='Product Unit')
    diferencia = fields.Float('Diferencia', readonly=True, digits='Product Unit')
    costo_unitario = fields.Float('Costo unitario', readonly=True, digits='Product Price')
    valor = fields.Monetary('Valor de la diferencia (a costo)', readonly=True, currency_field='currency_id')
    motivo = fields.Char('Motivo', required=True, readonly=True)
    origen = fields.Selection(ORIGENES, 'Desde', required=True, readonly=True, default='otro')
    move_id = fields.Many2one('stock.move', 'Movimiento', readonly=True)
    scrap_id = fields.Many2one('stock.scrap', 'Merma', readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(self.env._('La bitácora de bodega la escribe el sistema.'))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(self.env._('La bitácora de bodega no se edita: queda como pasó.'))

    @api.ondelete(at_uninstall=False)
    def _no_se_borra(self):
        raise UserError(self.env._('La bitácora de bodega no se borra: queda como pasó.'))

    @api.model
    def _anotar(self, filas):
        """Crea las filas (lista de dicts) como el sistema. Nunca hace fallar el ajuste: si algo falla, se registra en
        el log y el ajuste sigue (la existencia ya cambió por su movimiento, que queda en Odoo)."""
        filas = [f for f in filas if f.get('diferencia')]
        if not filas:
            return self.browse()
        for fila in filas:
            fila.setdefault('usuario_id', self.env.uid)
            fila['motivo'] = (fila.get('motivo') or MOTIVO_SISTEMA)[:250]
        return self.sudo().create(filas)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _dcasa_origen(self, motivo):
        origen = self.env.context.get('dcasa_origen')
        if origen in dict(ORIGENES):
            return origen
        if motivo.startswith(PREFIJO_ESCANER):
            return 'escaner'
        return 'otro' if motivo else 'sistema'

    def _dcasa_pedir_motivo(self):
        """La ventana de Odoo «Aplicar», con el motivo vacío y obligatorio."""
        vista = self.env.ref('stock.stock_inventory_adjustment_name_form_view')
        return {
            'name': self.env._('¿Por qué cambias las existencias?'),
            'type': 'ir.actions.act_window', 'res_model': 'stock.inventory.adjustment.name',
            'views': [(vista.id, 'form')], 'target': 'new',
            'context': {**self.env.context, 'default_quant_ids': self.ids},
        }

    def action_apply_inventory(self, date=None):
        if self and not self.env.su and not _motivo(self.env):
            self._dcasa_exigir_gerencia_para_ajustar()
            return self._dcasa_pedir_motivo()
        return super().action_apply_inventory(date)

    def _apply_inventory(self, date=None):
        if not self:
            return super()._apply_inventory(date)
        if not self.env.su:
            self._dcasa_exigir_gerencia_para_ajustar()
        motivo = _motivo(self.env)
        origen = self._dcasa_origen(motivo)
        if not motivo:
            if not self.env.su:
                raise UserError(self.env._(
                    'Escribe el motivo del ajuste (por ejemplo: «conteo de fin de mes», «llegó dañado»). Sin motivo '
                    'no se cambian las existencias.'))
            motivo = MOTIVO_SISTEMA
        antes = {q.id: (q.quantity, q.inventory_quantity, q.product_id, q.location_id, q.company_id) for q in self}
        resultado = super()._apply_inventory(date)
        filas = []
        for _id, (cantidad, contada, producto, ubicacion, company) in antes.items():
            diferencia = contada - cantidad
            costo = producto.sudo().with_company(company or self.env.company).standard_price
            filas.append({
                'producto_id': producto.id, 'ubicacion_id': ubicacion.id, 'antes': cantidad, 'despues': contada,
                'diferencia': diferencia, 'costo_unitario': costo, 'valor': diferencia * costo, 'motivo': motivo,
                'origen': origen, 'company_id': (company or self.env.company).id,
            })
        self.env['dcasa.bitacora.bodega']._anotar(filas)
        return resultado

    def _dcasa_cambio_directo_sin_motivo(self, campos):
        """Escribir «A la mano» directo (sin «Contado» + «Aplicar») ajusta sin pasar por la ventana del motivo."""
        return ('inventory_quantity_auto_apply' in campos and self._is_inventory_mode() and not self.env.su
                and not _motivo(self.env))

    @api.model_create_multi
    def create(self, vals_list):
        if any(self._dcasa_cambio_directo_sin_motivo(set(vals)) for vals in vals_list):
            raise UserError(self.env._(
                'Para cambiar las existencias escribe lo que contaste en «Contado» y pulsa «Aplicar»: te pide el '
                'motivo y queda en la bitácora de bodega.'))
        return super().create(vals_list)

    def write(self, vals):
        if self._dcasa_cambio_directo_sin_motivo(set(vals)):
            raise UserError(self.env._(
                'Para cambiar las existencias escribe lo que contaste en «Contado» y pulsa «Aplicar»: te pide el '
                'motivo y queda en la bitácora de bodega.'))
        return super().write(vals)


class StockInventoryAdjustmentName(models.TransientModel):
    _inherit = 'stock.inventory.adjustment.name'

    # De fábrica Odoo trae «Inventario físico» escrito: así nadie escribía el motivo. Ahora viene vacío y se exige.
    inventory_adjustment_name = fields.Char(default=False, string='Motivo del ajuste')

    def _get_quants_context(self):
        return {**super()._get_quants_context(), 'dcasa_origen': 'inventario_fisico'}

    def action_apply(self):
        if not (self.inventory_adjustment_name or '').strip():
            raise UserError(self.env._('Escribe el motivo del ajuste: queda en la bitácora de bodega.'))
        return super().action_apply()


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(self.env['stock.move']._dcasa_toca_ajuste(vals) for vals in vals_list):
            self.env['stock.move']._dcasa_exigir_ajuste()
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and {'location_id', 'location_dest_id'} & set(vals) \
                and self.env['stock.move']._dcasa_toca_ajuste(vals):
            self.env['stock.move']._dcasa_exigir_ajuste()
        return super().write(vals)

    def action_revert_inventory(self):
        """«Deshacer el ajuste» (historial de movimientos): también cambia existencias a mano, así que es de Gerencia y
        queda en la bitácora."""
        if not self.env.su and not self.env.user.has_group(GRUPO_AJUSTA):
            raise AccessError(self.env._('Solo Gerencia deshace un ajuste de existencias.'))
        ajustes = self.filtered(lambda ml: ml.is_inventory and not ml.product_uom_id.is_zero(ml.quantity))
        resultado = super().action_revert_inventory()
        filas = []
        for linea in ajustes:
            internas = linea.location_id.usage in ('internal', 'transit')
            ubicacion = linea.location_id if internas else linea.location_dest_id
            cantidad = linea.product_uom_id._compute_quantity(linea.quantity, linea.product_id.uom_id)
            diferencia = cantidad if internas else -cantidad   # deshacer devuelve lo que el ajuste movió
            disponible = linea.product_id.with_context(location=ubicacion.id).qty_available
            costo = linea.product_id.sudo().standard_price
            filas.append({
                'producto_id': linea.product_id.id, 'ubicacion_id': ubicacion.id,
                'antes': disponible - diferencia, 'despues': disponible, 'diferencia': diferencia,
                'costo_unitario': costo, 'valor': diferencia * costo, 'origen': 'deshacer',
                'motivo': self.env._('Se deshizo el ajuste %s', linea.reference or ''),
                'company_id': linea.company_id.id or self.env.company.id,
            })
        self.env['dcasa.bitacora.bodega']._anotar(filas)
        return resultado


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _reset_inventory(self):
        """Marcar «Rastrear inventario» en un producto que ya tuvo movimientos (lo creado en una compra sin la casilla):
        Odoo arma las existencias de su historial y las deja en cero con un ajuste, para que la valuación cuadre. Es un
        ajuste del sistema, no de una persona: lleva su motivo y queda en la bitácora. Sin esto, la regla del motivo
        obligatorio no dejaba marcar la casilla (2026-10-27). Sigue siendo de Gerencia, como todo ajuste."""
        motivo = self.env._('Se activó «Rastrear inventario»')
        return super(ProductTemplate, self.with_context(dcasa_motivo=motivo, dcasa_origen='sistema'))._reset_inventory()


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _dcasa_toca_ajuste(self, vals):
        ids = [vals.get('location_id'), vals.get('location_dest_id')]
        ubicaciones = self.env['stock.location'].sudo().browse([i for i in ids if i])
        return vals.get('is_inventory') or any(u.usage == 'inventory' for u in ubicaciones)

    def _dcasa_exigir_ajuste(self):
        if self.env.su or self.env.user.has_group(GRUPO_AJUSTA):
            return
        raise AccessError(self.env._(
            'Solo Gerencia mueve existencias hacia o desde «Ajuste de inventario» o «Desecho» (es un ajuste a mano). '
            'Pídele a Gerencia que lo haga y que deje el motivo.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any(self._dcasa_toca_ajuste(vals) for vals in vals_list):
            self._dcasa_exigir_ajuste()
        return super().create(vals_list)

    def write(self, vals):
        if {'location_id', 'location_dest_id', 'is_inventory'} & set(vals) and self._dcasa_toca_ajuste(vals):
            self._dcasa_exigir_ajuste()
        return super().write(vals)
