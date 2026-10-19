"""«Reponer» (Compras › Reponer): qué se vendió en un periodo y cuánto faltaría pedirle al proveedor.

Una fila por producto vendido en las **facturas publicadas** del periodo (las notas de crédito restan), con las mismas
unidades que «Lo más vendido» del Inicio de Gerencia (``dcasa.tablero._unidades_por_producto`` sobre la base
«Facturado»): sin servicios, flete, anticipos ni líneas sin producto. Al lado, lo que hay hoy en las ubicaciones
internas y lo pedido en compras confirmadas que todavía no llega. «Faltaría» es una cuenta a la vista:
vendido − existencia − pedido sin llegar, solo si da más de 0. No hay ninguna otra cifra.

Solo Gerencia y los administradores (ir.model.access, el menú y ``_exigir_gerencia`` en el servidor). La herramienta
``que_reponer`` de Brian lee lo mismo (``_calcular``).
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .tablero import BASE_FACTURADO

GRUPOS_REPONER = ('dcasa_base.group_gerencia', 'base.group_system')
DIAS_POR_DEFECTO = 30


class DcasaReponer(models.TransientModel):
    _name = 'dcasa.reponer'
    _description = 'Reponer: qué pedirle al proveedor'

    fecha_desde = fields.Date(
        'Desde', required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=DIAS_POR_DEFECTO - 1))
    fecha_hasta = fields.Date('Hasta', required=True, default=fields.Date.context_today)
    proveedor_id = fields.Many2one(
        'res.partner', 'Proveedor', help='Opcional: solo los productos cuyo proveedor principal es este.')
    linea_ids = fields.One2many('dcasa.reponer.linea', 'reponer_id')

    @api.model
    def _exigir_gerencia(self):
        if not any(self.env.user.has_group(grupo) for grupo in GRUPOS_REPONER):
            raise AccessError(self.env._('«Reponer» es solo de Gerencia y los administradores.'))

    @api.model
    def _calcular(self, desde, hasta, proveedor=None):
        """Las filas de «Reponer», de más vendido a menos: ``[{'producto_id', 'producto', 'referencia',
        'proveedor_id', 'proveedor', 'vendido', 'existencia', 'pedido', 'faltaria'}]``.

        Lecturas agrupadas (una por tipo de dato, nunca una por producto), con ``sudo`` tras comprobar el grupo y
        siempre filtradas a las empresas de quien mira."""
        self._exigir_gerencia()
        if not desde or not hasta or desde > hasta:
            raise UserError(self.env._('Revisa las fechas: «Desde» va antes que «Hasta».'))
        tablero = self.env['dcasa.tablero']
        unidades = tablero._unidades_por_producto(tablero._filas(desde, hasta, BASE_FACTURADO))
        vendidos = {producto.id: cantidad for producto, (cantidad, _monto) in unidades.items()
                    if round(cantidad, 2) > 0}
        if not vendidos:
            return []
        empresas = self.env.companies.ids
        productos = self.env['product.product'].sudo().with_context(active_test=False).browse(list(vendidos))

        # Proveedor principal: el primero de sus precios de proveedor (el orden de Odoo), el de esa variante o el de
        # todo el producto.
        principal = {}
        variantes = {}
        for producto in productos:
            variantes.setdefault(producto.product_tmpl_id.id, []).append(producto)
        precios = self.env['product.supplierinfo'].sudo().search_fetch(
            [('product_tmpl_id', 'in', list(variantes)), ('company_id', 'in', [False] + empresas)],
            ['partner_id', 'product_tmpl_id', 'product_id'])
        for precio in precios:
            for producto in variantes[precio.product_tmpl_id.id]:
                if producto.id not in principal and (not precio.product_id or precio.product_id == producto):
                    principal[producto.id] = precio.partner_id
        if proveedor:
            vendidos = {pid: cantidad for pid, cantidad in vendidos.items()
                        if principal.get(pid) and principal[pid].id == proveedor.id}
            productos = productos.filtered(lambda p: p.id in vendidos)
            if not vendidos:
                return []

        existencia = {producto.id: cantidad for producto, cantidad in self.env['stock.quant'].sudo()._read_group(
            [('product_id', 'in', productos.ids), ('location_id.usage', '=', 'internal'),
             ('company_id', 'in', empresas)], ['product_id'], ['quantity:sum'])}

        pedido = dict.fromkeys(productos.ids, 0.0)
        for linea in self.env['purchase.order.line'].sudo().search_fetch(
                [('product_id', 'in', productos.ids), ('order_id.state', '=', 'purchase'),
                 ('company_id', 'in', empresas)], ['product_id', 'product_qty', 'qty_received', 'product_uom_id']):
            falta = max(linea.product_qty - linea.qty_received, 0.0)
            unidad = linea.product_id.uom_id
            if falta and linea.product_uom_id and unidad and linea.product_uom_id != unidad:
                falta = linea.product_uom_id._compute_quantity(falta, unidad)
            pedido[linea.product_id.id] += falta

        filas = []
        for producto in productos:
            vendido = round(vendidos[producto.id], 2)
            hay = round(existencia.get(producto.id, 0.0), 2)
            en_camino = round(pedido[producto.id], 2)
            socio = principal.get(producto.id)
            filas.append({
                'producto_id': producto.id, 'producto': producto.display_name,
                'referencia': producto.default_code or '',
                'proveedor_id': socio.id if socio else False, 'proveedor': socio.display_name if socio else '',
                'vendido': vendido, 'existencia': hay, 'pedido': en_camino,
                'faltaria': round(max(vendido - hay - en_camino, 0.0), 2),
            })
        filas.sort(key=lambda fila: (-fila['vendido'], fila['producto'].lower()))
        return filas

    def action_ver(self):
        """Botón «Ver»: llena las filas de este pedido de filtros y abre la lista (agrupable y exportable)."""
        self.ensure_one()
        filas = self._calcular(self.fecha_desde, self.fecha_hasta, self.proveedor_id)
        self.linea_ids.unlink()
        self.env['dcasa.reponer.linea'].create([
            {'reponer_id': self.id, 'secuencia': orden, 'product_id': fila['producto_id'],
             'referencia': fila['referencia'], 'proveedor_id': fila['proveedor_id'], 'vendido': fila['vendido'],
             'existencia': fila['existencia'], 'pedido': fila['pedido'], 'faltaria': fila['faltaria']}
            for orden, fila in enumerate(filas)])
        titulo = self.env._('Reponer: %(desde)s a %(hasta)s', desde=self.fecha_desde.strftime('%d/%m/%Y'),
                            hasta=self.fecha_hasta.strftime('%d/%m/%Y'))
        if self.proveedor_id:
            titulo = f'{titulo} · {self.proveedor_id.display_name}'
        return {
            'type': 'ir.actions.act_window',
            'name': titulo,
            'res_model': 'dcasa.reponer.linea',
            'view_mode': 'list',
            'views': [(self.env.ref('dcasa_interfaz.dcasa_reponer_linea_view_list').id, 'list')],
            'search_view_id': self.env.ref('dcasa_interfaz.dcasa_reponer_linea_view_search').id,
            'domain': [('reponer_id', '=', self.id)],
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }


class DcasaReponerLinea(models.TransientModel):
    _name = 'dcasa.reponer.linea'
    _description = 'Reponer: una fila por producto'
    _order = 'secuencia, id'

    reponer_id = fields.Many2one('dcasa.reponer', required=True, ondelete='cascade', index=True)
    secuencia = fields.Integer(default=0)
    product_id = fields.Many2one('product.product', 'Producto', readonly=True)
    referencia = fields.Char('Referencia', readonly=True)
    proveedor_id = fields.Many2one('res.partner', 'Proveedor principal', readonly=True,
                                   help='El primero de los precios de proveedor del producto.')
    vendido = fields.Float('Vendido', digits='Product Unit', readonly=True,
                           help='Unidades de las facturas publicadas del periodo menos las notas de crédito.')
    existencia = fields.Float('En existencia hoy', digits='Product Unit', readonly=True,
                              help='Lo que hay hoy en las ubicaciones internas.')
    pedido = fields.Float('Pedido sin llegar', digits='Product Unit', readonly=True,
                          help='Compras confirmadas que todavía no se reciben.')
    faltaria = fields.Float('Faltaría (vendido − existencia − pedido)', digits='Product Unit', readonly=True,
                            help='Vendido − En existencia hoy − Pedido sin llegar, solo si da más de 0.')
