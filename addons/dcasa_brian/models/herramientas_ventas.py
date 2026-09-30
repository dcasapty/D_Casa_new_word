"""Herramientas de ventas: reporte del día, resúmenes, cotizaciones y ventas."""
from odoo import api, models

from . import herramientas_comun as c
from .registro import BrianError, herramienta

VENDEDOR = ('sales_team.group_sale_salesman',)
PARAM_VENTA = {'type': 'string', 'description': 'Número de la cotización o venta («S00012») o nombre del cliente.'}
PARAM_PRODUCTO = {'type': 'string', 'description': 'Nombre o código del producto, p. ej. «SOF-001» o «colchón queen».'}
PARAM_CANTIDAD = {'type': 'number', 'description': 'Cantidad. Por defecto 1.'}
PARAM_PRECIO = {'type': 'number',
                'description': 'Precio unitario con ITBMS incluido. Si no lo das, se usa el precio de lista.'}
ESTADOS = {'cotizacion': ['draft', 'sent'], 'confirmada': ['sale'], 'cancelada': ['cancel']}


class BrianHerramientasVentas(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @api.model
    def _b_fila_venta(self, orden):
        return {
            'numero': orden.name,
            'cliente': orden.partner_id.display_name,
            'fecha': c.fecha(orden.date_order),
            'estado': self._b_estado_venta(orden),
            'total': c.moneda(orden.amount_total),
        }

    @api.model
    def _b_cotizacion_editable(self, texto):
        orden = self._b_venta(texto)
        if orden.state not in ('draft', 'sent'):
            raise BrianError(f'{orden.name} es una {self._b_estado_venta(orden)}: solo se cambian cotizaciones '
                             'que no se han confirmado.')
        return orden

    @api.model
    def _b_linea_venta(self, orden, producto, cantidad, precio):
        if cantidad is not None and cantidad <= 0:
            raise BrianError('La cantidad tiene que ser mayor que cero.')
        if precio is not None and precio < 0:
            raise BrianError('El precio no puede ser negativo.')
        valores = {'order_id': orden.id, 'product_id': producto.id, 'product_uom_qty': cantidad or 1}
        linea = self.env['sale.order.line'].create(valores)
        if precio is not None:
            linea.price_unit = precio
        return linea

    @api.model
    def _b_resumen_orden(self, orden):
        return {
            'numero': orden.name,
            'cliente': orden.partner_id.display_name,
            'estado': self._b_estado_venta(orden),
            'lineas': [{
                'producto': linea.product_id.display_name,
                'cantidad': c.cantidad(linea.product_uom_qty),
                'precio': c.moneda(linea.price_unit),
                'subtotal': c.moneda(linea.price_total),
            } for linea in orden.order_line.filtered(lambda ln: not ln.display_type)],
            'total': c.moneda(orden.amount_total),
            'itbms': c.moneda(orden.amount_tax),
        }

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @herramienta(
        nombre='reporte_del_dia',
        descripcion='Cómo va el día: vendido y cobrado hoy (por forma de pago), cotizaciones abiertas, '
                    'pedidos web, por cobrar, entregas y lo más vendido del mes. Las mismas cifras del tablero Inicio.',
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['¿cómo vamos hoy?', 'reporte del día', '¿cuánto se ha vendido hoy?'],
    )
    def _h_reporte_del_dia(self):
        datos = self.env['dcasa.tablero'].obtener_datos()
        cifras = []
        for cifra in datos['cifras']:
            valor = c.moneda(cifra['valor']) if cifra['formato'] == 'moneda' else cifra['valor']
            fila = {'titulo': cifra['titulo'], 'valor': valor}
            if cifra.get('detalle_moneda') is not None:
                fila['detalle'] = f'por {c.moneda(cifra["detalle_moneda"])}'
            elif cifra.get('detalle'):
                fila['detalle'] = cifra['detalle']
            cifras.append(fila)
        return {
            'fecha': c.fecha(self._b_hoy()),
            'cifras': cifras,
            'cobros_por_forma_de_pago': [{'forma': x['forma'], 'monto': c.moneda(x['monto'])} for x in datos['cobros']],
            'mas_vendidos_30_dias': [{'producto': t['nombre'], 'unidades': t['cantidad']} for t in datos['top']],
        }

    @herramienta(
        nombre='resumen_ventas',
        descripcion='Total vendido en un periodo (ventas confirmadas): cantidad, ticket promedio, por vendedor y '
                    'productos más vendidos.',
        parametros={'periodo': c.PARAM_PERIODO, 'desde': c.PARAM_DESDE, 'hasta': c.PARAM_HASTA},
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['ventas de este mes → periodo=este_mes', 'ventas del 01/09/2026 al 15/09/2026'],
    )
    def _h_resumen_ventas(self, periodo=None, desde=None, hasta=None):
        inicio, fin, etiqueta = self._b_rango(periodo, desde, hasta)
        d_inicio, d_fin = self._b_limites(inicio, fin)
        dominio = [('state', '=', 'sale'), ('date_order', '>=', d_inicio), ('date_order', '<', d_fin)]
        Order = self.env['sale.order']
        ventas = Order.search(dominio)
        total = sum(ventas.mapped('amount_total'))
        por_vendedor = {}
        for venta in ventas:
            nombre = venta.user_id.name or 'Sin vendedor'
            por_vendedor[nombre] = por_vendedor.get(nombre, 0.0) + venta.amount_total
        grupos = self.env['sale.order.line']._read_group(
            [('order_id', 'in', ventas.ids), ('display_type', '=', False), ('is_downpayment', '=', False)],
            ['product_id'], ['product_uom_qty:sum', 'price_total:sum'])
        top = sorted(grupos, key=lambda g: -g[1])[:5]
        return {
            'periodo': etiqueta,
            'desde': c.fecha(inicio), 'hasta': c.fecha(fin),
            'ventas': len(ventas),
            'total': c.moneda(total),
            'ticket_promedio': c.moneda(total / len(ventas)) if ventas else c.moneda(0),
            'por_vendedor': [{'vendedor': n, 'total': c.moneda(m)}
                             for n, m in sorted(por_vendedor.items(), key=lambda nm: -nm[1])[:10]],
            'productos_mas_vendidos': [{'producto': p.display_name, 'unidades': c.cantidad(q), 'total': c.moneda(t)}
                                       for p, q, t in top if p],
        }

    @herramienta(
        nombre='buscar_ventas',
        descripcion='Busca ventas y cotizaciones por cliente o número, estado y periodo.',
        parametros={
            'texto': {'type': 'string', 'description': 'Cliente o número, p. ej. «Juan Pérez» o «S00012». Opcional.'},
            'estado': {'type': 'string', 'enum': ['cotizacion', 'confirmada', 'cancelada', 'todas'],
                       'description': 'Filtrar por estado. Por defecto «todas».'},
            'periodo': c.PARAM_PERIODO,
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['cotizaciones abiertas → estado=cotizacion', 'ventas de María este mes'],
    )
    def _h_buscar_ventas(self, texto=None, estado='todas', periodo=None, limite=10):
        dominio = []
        if estado and estado != 'todas':
            if estado not in ESTADOS:
                raise BrianError('Estado desconocido. Usa cotizacion, confirmada, cancelada o todas.')
            dominio.append(('state', 'in', ESTADOS[estado]))
        if texto:
            dominio += ['|', ('name', 'ilike', texto), ('partner_id', 'ilike', texto)]
        if periodo:
            inicio, fin, _etiqueta = self._b_rango(periodo)
            d_inicio, d_fin = self._b_limites(inicio, fin)
            dominio += [('date_order', '>=', d_inicio), ('date_order', '<', d_fin)]
        Order = self.env['sale.order']
        total = Order.search_count(dominio)
        ordenes = Order.search(dominio, limit=c.limite(limite), order='date_order desc, id desc')
        return {'encontradas': total, 'mostradas': len(ordenes), 'ventas': [self._b_fila_venta(o) for o in ordenes]}

    @herramienta(
        nombre='ver_venta',
        descripcion='Detalle de una venta o cotización: cliente, productos, total, facturación y entrega.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['ver S00012', '¿qué lleva la cotización de Juan?'],
    )
    def _h_ver_venta(self, venta):
        orden = self._b_venta(venta)
        facturacion = {'no': 'nada que facturar', 'to invoice': 'por facturar', 'invoiced': 'facturada',
                       'upselling': 'facturada (con extra)'}
        resumen = self._b_resumen_orden(orden)
        resumen.update({
            'fecha': c.fecha(orden.date_order),
            'vendedor': orden.user_id.name or '',
            'facturacion': facturacion.get(orden.invoice_status, orden.invoice_status or ''),
            'facturas': [f'{self._b_numero_factura(f)} ({self._b_estado_factura(f)})' for f in orden.invoice_ids],
        })
        if orden.state == 'sale' and 'delivery_status' in orden._fields:
            resumen['entrega'] = {'pending': 'por entregar', 'started': 'entregada en parte', 'partial':
                                  'entregada en parte', 'full': 'entregada'}.get(orden.delivery_status, 'sin entregas')
        return resumen

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    @herramienta(
        nombre='crear_cotizacion',
        descripcion='Crea una cotización en borrador para un cliente con un primer producto. '
                    'Para más productos usa agregar_linea_cotizacion.',
        parametros={
            'cliente': {'type': 'string', 'description': 'Nombre, celular o RUC del cliente, p. ej. «6123-4567».'},
            'producto': PARAM_PRODUCTO, 'cantidad': PARAM_CANTIDAD, 'precio': PARAM_PRECIO,
        },
        requeridos=['cliente', 'producto'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['cotiza 2 sillas SIL-010 para Ana Gómez'],
    )
    def _h_crear_cotizacion(self, cliente, producto, cantidad=1, precio=None):
        partner = self._b_contacto(cliente)
        variante = self._b_producto(producto)
        orden = self.env['sale.order'].create({'partner_id': partner.id})
        self._b_linea_venta(orden, variante, cantidad, precio)
        return {'mensaje': f'Cotización {orden.name} creada en borrador.', **self._b_resumen_orden(orden)}

    @herramienta(
        nombre='agregar_linea_cotizacion',
        descripcion='Agrega un producto a una cotización que no se ha confirmado.',
        parametros={'venta': PARAM_VENTA, 'producto': PARAM_PRODUCTO, 'cantidad': PARAM_CANTIDAD,
                    'precio': PARAM_PRECIO},
        requeridos=['venta', 'producto'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['agrega una mesa de noche a S00012'],
    )
    def _h_agregar_linea_cotizacion(self, venta, producto, cantidad=1, precio=None):
        orden = self._b_cotizacion_editable(venta)
        self._b_linea_venta(orden, self._b_producto(producto), cantidad, precio)
        return {'mensaje': f'Agregado a {orden.name}.', **self._b_resumen_orden(orden)}

    @herramienta(
        nombre='quitar_linea_cotizacion',
        descripcion='Quita un producto de una cotización que no se ha confirmado.',
        parametros={'venta': PARAM_VENTA, 'producto': PARAM_PRODUCTO},
        requeridos=['venta', 'producto'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['quita el sofá de la cotización S00012'],
    )
    def _h_quitar_linea_cotizacion(self, venta, producto):
        orden = self._b_cotizacion_editable(venta)
        lineas = orden.order_line.filtered(lambda ln: not ln.display_type)
        texto = c.normalizar_texto(producto)
        coinciden = lineas.filtered(lambda ln: texto in c.normalizar_texto(ln.product_id.display_name)
                                    or texto == c.normalizar_texto(ln.product_id.default_code or ''))
        if not coinciden:
            raise BrianError(f'{orden.name} no tiene «{producto}». Lleva: '
                             + '; '.join(lineas.mapped('product_id.display_name')) + '.')
        if len(coinciden) > 1:
            raise BrianError(f'En {orden.name} hay varias líneas con «{producto}»: '
                             + '; '.join(coinciden.mapped('product_id.display_name')) + '. Dime cuál.')
        nombre = coinciden.product_id.display_name
        coinciden.unlink()
        return {'mensaje': f'Quité {nombre} de {orden.name}.', **self._b_resumen_orden(orden)}

    @herramienta(
        nombre='enviar_cotizacion_whatsapp',
        descripcion='Prepara el mensaje de WhatsApp con la cotización (total y enlace) para el celular del cliente '
                    'y devuelve el enlace para abrirlo. La marca como enviada.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['mándale la cotización S00012 por WhatsApp'],
    )
    def _h_enviar_cotizacion_whatsapp(self, venta):
        orden = self._b_venta(venta)
        if orden.state == 'cancel':
            raise BrianError(f'{orden.name} está cancelada: no se envía.')
        accion = orden.action_dcasa_whatsapp()
        return {'mensaje': f'Listo el mensaje de {orden.name} para {orden.partner_id.display_name}. '
                           'Abre el enlace para enviarlo por WhatsApp.',
                'enlace': accion['url'], 'abrir': {'url': accion['url'], 'titulo': 'Enviar por WhatsApp'}}

    # ------------------------------------------------------------------
    # Sensibles
    # ------------------------------------------------------------------

    @herramienta(
        nombre='confirmar_venta',
        descripcion='Confirma una cotización y la convierte en venta (reserva y crea la entrega).',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='sensible', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['confirma la cotización S00012'],
    )
    def _h_confirmar_venta(self, venta):
        orden = self._b_cotizacion_editable(venta)
        if not orden.order_line.filtered(lambda ln: not ln.display_type):
            raise BrianError(f'{orden.name} no tiene productos: agrega al menos uno antes de confirmar.')
        orden.action_confirm()
        return {'mensaje': f'{orden.name} confirmada.', **self._b_resumen_orden(orden)}

    @herramienta(
        nombre='cancelar_cotizacion',
        descripcion='Cancela una cotización que no se ha confirmado. Las ventas confirmadas las cancela una persona.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='sensible', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['cancela la cotización S00012'],
    )
    def _h_cancelar_cotizacion(self, venta):
        orden = self._b_venta(venta)
        if orden.state not in ('draft', 'sent'):
            raise BrianError(f'{orden.name} es una {self._b_estado_venta(orden)}: cancelar una venta confirmada '
                             '(con entregas o facturas) lo hace una persona desde Ventas.')
        orden.action_cancel()
        return {'mensaje': f'Cotización {orden.name} cancelada.', 'numero': orden.name,
                'estado': self._b_estado_venta(orden)}
