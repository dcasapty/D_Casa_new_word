"""Herramientas del día a día de la tienda (ronda 6): reabastecer, comprar, pendientes,
catálogo incompleto, editar varios productos a la vez (publicar, existencias, precio, categoría) y consumo de
Brian.

Todo corre como el usuario (sin sudo). Las cifras las calcula Odoo y se devuelven ya
formateadas; ninguna se estima con el modelo de IA. La sugerencia de compra es aritmética
visible (ventas del periodo ÷ días × días de cobertura − proyectado), sin «inteligencia» oculta.
"""
import math
from datetime import timedelta

from odoo import api, fields, models

from . import herramientas_comun as c
from .registro import BrianError, herramienta
from .uso import costo_estimado

INTERNO = ('base.group_user',)
INVENTARIO = ('stock.group_stock_user',)
COMPRAS = ('purchase.group_purchase_user',)
GERENTE_VENTAS = ('sales_team.group_sale_manager',)
GERENTE_INVENTARIO = ('stock.group_stock_manager',)
ADMIN = ('base.group_system',)
GERENCIA_O_ADMIN = ('dcasa_base.group_gerencia', 'base.group_system')
DIAS_REPONER = 30
MAX_BLOQUE = 200
MAX_BLOQUE_EXISTENCIAS = 1000
CAMPOS_EN_BLOQUE = ('precio', 'categoria', 'vendible')
PROBLEMAS = {
    'sin_foto': 'sin foto',
    'sin_precio': 'sin precio (o en $0)',
    'sin_categoria': 'sin categoría',
    'sin_medidas': 'sin medidas',
    'sin_codigo': 'sin código',
}
ESTADOS_COMPRA = {'draft': 'solicitud (borrador)', 'sent': 'solicitud enviada', 'to approve': 'por aprobar',
                  'purchase': 'pedido confirmado', 'cancel': 'cancelado'}
RECEPCION = {'pending': 'por recibir', 'partial': 'recibido en parte', 'full': 'recibido'}


class BrianHerramientasOperacion(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Reabastecimiento y compras
    # ------------------------------------------------------------------

    @api.model
    def _b_vendido_por_variante(self, desde_dias):
        """{product.product: unidades vendidas (ventas confirmadas) en los últimos N días}."""
        if not self.env['sale.order.line'].has_access('read'):
            return {}
        desde = fields.Datetime.now() - timedelta(days=desde_dias)
        grupos = self.env['sale.order.line']._read_group(
            [('order_id.state', '=', 'sale'), ('order_id.date_order', '>=', desde),
             ('display_type', '=', False), ('product_id', '!=', False)],
            ['product_id'], ['product_uom_qty:sum'])
        return {producto.id: cantidad for producto, cantidad in grupos if cantidad}

    @herramienta(
        nombre='sugerir_reabastecimiento',
        descripcion='Qué pedir al proveedor: por producto, lo vendido en los últimos días, lo que hay, lo que viene '
                    'en camino y cuánto pedir para cubrir N días. Cálculo simple y visible.',
        parametros={
            'dias_ventas': {'type': 'integer', 'description': 'Días de ventas a mirar. Por defecto 30.'},
            'dias_cobertura': {'type': 'integer', 'description': 'Para cuántos días alcanzar. Por defecto 30.'},
            'categoria': {'type': 'string', 'description': 'Solo una categoría, p. ej. «Colchones». Opcional.'},
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='catalogo', grupos=INVENTARIO,
        ejemplos=['¿qué tengo que pedir?', 'reabastecimiento de colchones para 45 días → dias_cobertura=45'],
    )
    def _h_sugerir_reabastecimiento(self, dias_ventas=30, dias_cobertura=30, categoria=None, limite=20):
        dias_ventas = max(1, min(int(dias_ventas or 30), 365))
        dias_cobertura = max(1, min(int(dias_cobertura or 30), 365))
        vendidos = self._b_vendido_por_variante(dias_ventas)
        dominio = [('is_storable', '=', True), ('sale_ok', '=', True)]
        if categoria:
            dominio.append(('categ_id', 'child_of', self._b_resolver(
                'product.category', categoria, 'categoría', buscar=[('complete_name', 'ilike', categoria)]).id))
        variantes = self.env['product.product'].search(dominio)
        # El costo del proveedor es costo: solo para Gerencia y administradores (decisión de la dueña, 2026-10-16).
        ve_costo = self.env['dcasa.tablero']._ve_utilidad()
        filas = []
        for variante in variantes:
            vendido = vendidos.get(variante.id, 0.0)
            proyectado = variante.virtual_available
            if not vendido and proyectado >= 0:
                continue
            diario = vendido / dias_ventas
            sugerido = max(math.ceil(round(vendido * dias_cobertura / dias_ventas - proyectado, 6)), 0)
            if not sugerido:
                continue
            fila = {
                'producto': variante.display_name,
                'codigo': variante.default_code or '',
                'vendidas': c.cantidad(vendido),
                'hay': c.cantidad(variante.qty_available),
                'en_camino': c.cantidad(variante.incoming_qty),
                'comprometidas': c.cantidad(variante.outgoing_qty),
                'alcanza_dias': (int(max(proyectado, 0) / diario) if diario else 0),
                'pedir': sugerido,
            }
            proveedor = variante.seller_ids[:1]
            if proveedor:
                fila['proveedor'] = proveedor.partner_id.display_name
                if proveedor.price and ve_costo:
                    fila['costo_proveedor'] = c.moneda(proveedor.price)
            filas.append(fila)
        filas.sort(key=lambda f: (f['alcanza_dias'], -f['pedir']))
        mostradas = filas[:c.limite(limite, 20)]
        lineas = '; '.join(f"{f['codigo'] or f['producto']} x {f['pedir']}" for f in mostradas)
        return {
            'criterio': f'ventas confirmadas de los últimos {dias_ventas} días; cubrir {dias_cobertura} días; '
                        'pedir = vendido por día × días − (hay + en camino − comprometidas)',
            'productos_a_pedir': len(filas),
            'productos': mostradas,
            'lineas_para_compra': lineas,
            'nota': 'Es una sugerencia: revisa temporadas, combos y lo que ya hablaste con el proveedor. '
                    'Para pedirlo usa crear_pedido_compra con «lineas_para_compra».' if filas else
                    'Con estas ventas y existencias no hace falta pedir nada.',
        }

    @herramienta(
        nombre='crear_pedido_compra',
        descripcion='Crea una solicitud de compra en borrador a un proveedor con varios productos '
                    '(«SOF-001 x 4; MES-003 x 2 @ 80»). No la confirma ni la envía.',
        parametros={
            'proveedor': {'type': 'string', 'description': 'Nombre o RUC del proveedor.'},
            'lineas': c.PARAM_LINEAS,
            'referencia': {'type': 'string', 'description': 'Referencia del proveedor (su cotización). Opcional.'},
        },
        requeridos=['proveedor', 'lineas'],
        nivel='construccion', categoria='catalogo', grupos=COMPRAS,
        ejemplos=['pídele a Muebles XYZ 4 SOF-001 y 2 MES-003 → lineas=«SOF-001 x 4; MES-003 x 2»'],
    )
    def _h_crear_pedido_compra(self, proveedor, lineas, referencia=None):
        partner = self._b_contacto(proveedor, 'proveedor')
        items = self._b_lineas_productos(lineas)
        valores = {'partner_id': partner.id, 'order_line': []}
        if referencia:
            valores['partner_ref'] = str(referencia).strip()[:64]
        for variante, cant, precio in items:
            linea = {'product_id': variante.id, 'product_qty': cant}
            if precio is not None:
                if precio < 0:
                    raise BrianError('El costo no puede ser negativo.')
                linea['price_unit'] = precio
            valores['order_line'].append((0, 0, linea))
        orden = self.env['purchase.order'].create(valores)
        sin_costo = orden.order_line.filtered(lambda ln: not ln.price_unit)
        datos = self._b_resumen_compra(orden)
        datos['mensaje'] = f'Solicitud de compra {orden.name} creada en borrador para {partner.display_name}.'
        if sin_costo:
            datos['aviso'] = ('Sin costo (no hay precio del proveedor registrado): '
                              + '; '.join(sin_costo.mapped('product_id.display_name'))
                              + '. Pon el costo antes de confirmarla.')
        datos['abrir'] = {'modelo': 'purchase.order', 'res_id': orden.id, 'titulo': orden.name}
        return datos

    @api.model
    def _b_resumen_compra(self, orden):
        resumen = {
            'numero': orden.name,
            'proveedor': orden.partner_id.display_name,
            'estado': ESTADOS_COMPRA.get(orden.state, orden.state),
            'lineas': [{'producto': ln.product_id.display_name, 'cantidad': c.cantidad(ln.product_qty),
                        'costo': c.moneda(ln.price_unit), 'subtotal': c.moneda(ln.price_subtotal)}
                       for ln in orden.order_line.filtered(lambda ln: not ln.display_type)],
            'total': c.moneda(orden.amount_total),
        }
        if 'receipt_status' in orden._fields and orden.receipt_status:
            resumen['recepcion'] = RECEPCION.get(orden.receipt_status, orden.receipt_status)
        return resumen

    @herramienta(
        nombre='buscar_compras',
        descripcion='Busca pedidos de compra a proveedores: borradores, confirmados y qué falta por recibir.',
        parametros={
            'texto': {'type': 'string', 'description': 'Proveedor o número, p. ej. «P00012». Opcional.'},
            'estado': {'type': 'string', 'enum': ['borrador', 'confirmado', 'por_recibir', 'todos'],
                       'description': 'Por defecto «todos».'},
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='catalogo', grupos=COMPRAS,
        ejemplos=['¿qué compras faltan por llegar? → estado=por_recibir', 'compras a Muebles XYZ'],
    )
    def _h_buscar_compras(self, texto=None, estado='todos', limite=10):
        dominio = []
        if estado == 'borrador':
            dominio.append(('state', 'in', ('draft', 'sent', 'to approve')))
        elif estado == 'confirmado':
            dominio.append(('state', '=', 'purchase'))
        elif estado == 'por_recibir':
            dominio += [('state', '=', 'purchase'), ('receipt_status', 'in', ('pending', 'partial'))]
        elif estado not in (None, 'todos'):
            raise BrianError('Estado desconocido. Usa borrador, confirmado, por_recibir o todos.')
        if texto:
            dominio += ['|', '|', ('name', 'ilike', texto), ('partner_id', 'ilike', texto),
                        ('partner_ref', 'ilike', texto)]
        Compra = self.env['purchase.order']
        ordenes = Compra.search(dominio, limit=c.limite(limite), order='date_order desc, id desc')
        filas = []
        for orden in ordenes:
            fila = {'numero': orden.name, 'proveedor': orden.partner_id.display_name,
                    'fecha': c.fecha(orden.date_order), 'estado': ESTADOS_COMPRA.get(orden.state, orden.state),
                    'total': c.moneda(orden.amount_total)}
            if orden.receipt_status:
                fila['recepcion'] = RECEPCION.get(orden.receipt_status, orden.receipt_status)
            filas.append(fila)
        return {'encontradas': Compra.search_count(dominio), 'compras': filas}

    @herramienta(
        nombre='que_reponer',
        descripcion='Qué reponerle a un proveedor (como Compras › Reponer): por producto, lo vendido en el periodo '
                    '(facturas menos notas de crédito), lo que hay hoy, lo pedido sin llegar y lo que faltaría '
                    '(vendido − existencia − pedido).',
        parametros={
            'proveedor': {'type': 'string', 'description': 'Proveedor principal. Opcional: sin él, todos.'},
            'periodo': c.PARAM_PERIODO, 'desde': c.PARAM_DESDE, 'hasta': c.PARAM_HASTA,
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='catalogo', grupos=(GERENCIA_O_ADMIN,),
        ejemplos=['¿qué le repongo a Muebles XYZ? → proveedor=«Muebles XYZ»',
                  'lo vendido el mes pasado para reponer → periodo=mes_pasado'],
    )
    def _h_que_reponer(self, proveedor=None, periodo=None, desde=None, hasta=None, limite=20):
        if periodo or desde or hasta:
            inicio, fin, etiqueta = self._b_rango(periodo, desde, hasta)
        else:
            fin = self._b_hoy()
            inicio, etiqueta = fin - timedelta(days=DIAS_REPONER - 1), f'los últimos {DIAS_REPONER} días'
        socio = self._b_contacto(proveedor, 'proveedor') if proveedor else None
        filas = self.env['dcasa.reponer']._calcular(inicio, fin, socio)
        productos = [{'producto': f['producto'], 'codigo': f['referencia'], 'proveedor': f['proveedor'] or '—',
                      'vendido': c.cantidad(f['vendido']), 'en_existencia': c.cantidad(f['existencia']),
                      'pedido_sin_llegar': c.cantidad(f['pedido']), 'faltaria': c.cantidad(f['faltaria'])}
                     for f in filas]
        return {
            'periodo': etiqueta,
            'proveedor': socio.display_name if socio else 'todos',
            'criterio': 'vendido = facturas publicadas menos notas de crédito (sin servicios, flete ni anticipos); '
                        'faltaría = vendido − en existencia − pedido sin llegar, solo si da más de 0',
            'productos_vendidos': len(productos),
            'productos': productos[:c.limite(limite, 20)],
            'nota': 'La lista completa, agrupable por proveedor y para exportar, está en Compras › Reponer.'
                    if productos else 'En ese periodo no hay productos vendidos'
                                      + (f' de {socio.display_name}.' if socio else '.'),
        }

    # ------------------------------------------------------------------
    # Pendientes del día
    # ------------------------------------------------------------------

    @herramienta(
        nombre='pendientes_de_hoy',
        descripcion='Lista de pendientes para hoy: entregas por despachar, cotizaciones sin respuesta, compras '
                    'por recibir, facturas vencidas, productos publicados agotados y acciones por confirmar.',
        nivel='lectura', categoria='ventas', grupos=INTERNO,
        ejemplos=['¿qué tengo pendiente hoy?', 'resumen del día para arrancar'],
    )
    def _h_pendientes_de_hoy(self):
        hoy = self._b_hoy()
        _inicio, fin_hoy = self._b_limites(hoy, hoy)
        pendientes = {'fecha': c.fecha(hoy)}

        Picking = self.env['stock.picking']
        if Picking.has_access('read'):
            dominio = [('picking_type_code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'waiting', 'assigned')),
                       ('scheduled_date', '<', fin_hoy)]
            entregas = Picking.search(dominio, order='scheduled_date', limit=5)
            pendientes['entregas_por_despachar'] = {
                'cuantas': Picking.search_count(dominio),
                'primeras': [{'entrega': p.name, 'cliente': p.partner_id.display_name or '',
                              'origen': p.origin or '', 'programada': c.fecha(p.scheduled_date),
                              'lista': p.state == 'assigned'} for p in entregas]}

        Venta = self.env['sale.order']
        if Venta.has_access('read'):
            hace_una_semana = fields.Datetime.now() - timedelta(days=7)
            dominio = [('state', 'in', ('draft', 'sent')), ('write_date', '<', hace_una_semana)]
            viejas = Venta.search(dominio, order='amount_total desc', limit=5)
            pendientes['cotizaciones_sin_respuesta_7_dias'] = {
                'cuantas': Venta.search_count(dominio),
                'mayores': [{'numero': o.name, 'cliente': o.partner_id.display_name, 'total': c.moneda(o.amount_total),
                             'desde': c.fecha(o.date_order)} for o in viejas]}
            if nota := c.alcance(self.env, 'cotizaciones'):
                pendientes['cotizaciones_sin_respuesta_7_dias']['alcance'] = nota

        Compra = self.env['purchase.order']
        if Compra.has_access('read'):
            dominio = [('state', '=', 'purchase'), ('receipt_status', 'in', ('pending', 'partial'))]
            pendientes['compras_por_recibir'] = Compra.search_count(dominio)

        Factura = self.env['account.move']
        if Factura.has_access('read'):
            dominio = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                       ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<', hoy)]
            grupos = Factura._read_group(dominio, [], ['amount_residual:sum', '__count'])
            monto, cuantas = grupos[0] if grupos else (0.0, 0)
            pendientes['facturas_vencidas'] = {'cuantas': cuantas, 'por_cobrar': c.moneda(monto)}
            if nota := c.alcance(self.env):
                pendientes['facturas_vencidas']['alcance'] = nota

        Plantilla = self.env['product.template']
        agotados = Plantilla.search([('is_published', '=', True), ('is_storable', '=', True),
                                     ('qty_available', '<=', 0)])
        pendientes['publicados_agotados'] = {'cuantos': len(agotados),
                                             'ejemplos': agotados[:5].mapped('display_name')}

        por_confirmar = self.env['brian.accion'].search_count([('create_uid', '=', self.env.uid),
                                                               ('estado', '=', 'por_confirmar')])
        if por_confirmar:
            pendientes['acciones_de_brian_por_confirmar'] = por_confirmar
        return pendientes

    # ------------------------------------------------------------------
    # Catálogo incompleto y publicación en bloque
    # ------------------------------------------------------------------

    @api.model
    def _b_dominio_problema(self, problema):
        if problema == 'sin_foto':
            return [('image_1920', '=', False)]
        if problema == 'sin_precio':
            return [('list_price', '<=', 0)]
        if problema == 'sin_categoria':
            todas = self.env.ref('product.product_category_all', raise_if_not_found=False)
            return ['|', ('categ_id', '=', False), ('categ_id', '=', todas.id if todas else False)]
        if problema == 'sin_medidas':
            return [('dcasa_medidas', 'in', (False, ''))]
        if problema == 'sin_codigo':
            return [('default_code', 'in', (False, ''))]
        raise BrianError(f'Problema desconocido. Usa uno de: {", ".join(PROBLEMAS)} o todos.')

    @herramienta(
        nombre='productos_incompletos',
        descripcion='Productos a los que les falta algo para vender bien: foto, precio, categoría, medidas o '
                    'código. Cuenta cada problema y muestra ejemplos.',
        parametros={
            'problema': {'type': 'string', 'enum': list(PROBLEMAS) + ['todos'],
                         'description': 'Qué falta. Por defecto «todos» (solo conteos y pocos ejemplos).'},
            'solo_publicados': {'type': 'boolean', 'description': 'true = solo los que están en la web.'},
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='catalogo', grupos=INTERNO,
        ejemplos=['¿qué productos no tienen foto? → problema=sin_foto', 'revisa el catálogo de la web → '
                  'solo_publicados=true'],
    )
    def _h_productos_incompletos(self, problema='todos', solo_publicados=False, limite=10):
        base = [('sale_ok', '=', True)]
        if solo_publicados:
            base.append(('is_published', '=', True))
        Plantilla = self.env['product.template']
        if problema and problema != 'todos':
            dominio = base + self._b_dominio_problema(problema)
            productos = Plantilla.search(dominio, limit=c.limite(limite), order='name')
            return {'problema': PROBLEMAS[problema], 'encontrados': Plantilla.search_count(dominio),
                    'productos': [{'producto': p.display_name, 'codigo': p.default_code or '',
                                   'publicado': bool(p.is_published)} for p in productos]}
        resumen = []
        for clave, etiqueta in PROBLEMAS.items():
            dominio = base + self._b_dominio_problema(clave)
            cuantos = Plantilla.search_count(dominio)
            if cuantos:
                resumen.append({'problema': etiqueta, 'productos': cuantos,
                                'ejemplos': Plantilla.search(dominio, limit=3, order='name').mapped('display_name')})
        return {'revisados': Plantilla.search_count(base), 'problemas': resumen,
                'mensaje': '' if resumen else 'No encontré productos incompletos.'}

    @api.model
    def _b_productos_bloque(self, productos=None, categoria=None, maximo=MAX_BLOQUE):
        """Plantillas para una acción en bloque: códigos/nombres separados por «;» o «,», o una categoría."""
        if not productos and not categoria:
            raise BrianError('Dime cuáles: «productos» (códigos separados por «;») o una «categoria».')
        Plantilla = self.env['product.template']
        encontradas = Plantilla
        if categoria:
            cat = self._b_resolver('product.category', categoria, 'categoría',
                                   buscar=[('complete_name', 'ilike', categoria)])
            encontradas |= Plantilla.search([('categ_id', 'child_of', cat.id), ('sale_ok', '=', True)])
        if productos:
            errores = []
            for referencia in [p.strip() for p in str(productos).replace(',', ';').split(';') if p.strip()]:
                try:
                    encontradas |= self._b_plantilla(referencia)
                except BrianError as error:
                    errores.append(f'«{referencia}»: {error}')
            if errores:
                raise BrianError('No pude resolver (no hice nada): ' + ' | '.join(errores))
        if len(encontradas) > maximo:
            raise BrianError(f'Son {len(encontradas)} productos; el máximo por vez es {maximo}. Pártelo.')
        if not encontradas:
            raise BrianError('No encontré productos con eso.')
        return encontradas

    @api.model
    def _b_separar_publicables(self, plantillas):
        """(listos, {motivo: plantillas}) para publicar: vendible, con precio y con foto."""
        sin_venta = plantillas.filtered(lambda p: not p.sale_ok)
        sin_precio = (plantillas - sin_venta).filtered(lambda p: p.list_price <= 0)
        sin_foto = (plantillas - sin_venta - sin_precio).filtered(lambda p: not p.image_1920)
        omitidos = {'no vendible': sin_venta, 'sin precio': sin_precio, 'sin foto': sin_foto}
        return plantillas - sin_venta - sin_precio - sin_foto, {k: v for k, v in omitidos.items() if v}

    @herramienta(
        nombre='publicar_productos_en_bloque',
        descripcion='Publica o retira de la web varios productos a la vez (por códigos o por categoría). Al '
                    'publicar se saltan los que no tienen foto o precio.',
        parametros={
            'productos': {'type': 'string', 'description': 'Códigos o nombres separados por «;», p. ej. '
                                                           '«SOF-001; SOF-002». Opcional si das categoría.'},
            'categoria': {'type': 'string', 'description': 'Toda una categoría, p. ej. «Salas». Opcional.'},
            'publicar': {'type': 'boolean', 'description': 'true publica; false retira de la web.'},
        },
        requeridos=['publicar'],
        nivel='sensible', categoria='catalogo', grupos=GERENTE_VENTAS,
        ejemplos=['publica toda la categoría Salas → categoria=Salas, publicar=true',
                  'quita de la web SOF-001 y SOF-002 → productos=«SOF-001; SOF-002», publicar=false'],
    )
    def _h_publicar_productos_en_bloque(self, publicar, productos=None, categoria=None):
        plantillas = self._b_productos_bloque(productos, categoria)
        if publicar:
            listos, omitidos = self._b_separar_publicables(plantillas)
        else:
            listos, omitidos = plantillas, {}
        cambian = listos.filtered(lambda p: bool(p.is_published) != bool(publicar))
        cambian.write({'is_published': bool(publicar)})
        verbo = 'Publiqué' if publicar else 'Retiré de la web'
        return {
            'mensaje': f'{verbo} {c.plural(len(cambian), "producto")}'
                       + (f' ({len(listos) - len(cambian)} ya estaban así).' if len(listos) > len(cambian) else '.'),
            'cambiados': cambian[:c.MAX_FILAS].mapped('display_name'),
            'omitidos': {motivo: v[:c.MAX_FILAS].mapped('display_name') for motivo, v in omitidos.items()},
        }

    # ------------------------------------------------------------------
    # Varios productos a la vez: existencias, precio, categoría, vendible
    # ------------------------------------------------------------------

    @api.model
    def _b_bodega_para_ajustar(self, almacen=None):
        """El almacén donde se ajusta (el único, o el que se nombra)."""
        dominio = [('company_id', 'in', self.env.companies.ids)]
        if almacen:
            return self._b_resolver('stock.warehouse', almacen, 'almacén', exactos=('code',), dominio=dominio)
        bodegas = self.env['stock.warehouse'].search(dominio)
        if len(bodegas) > 1:
            raise BrianError('Hay varios almacenes: ' + '; '.join(bodegas.mapped('name')) + '. Dime en cuál.')
        if not bodegas:
            raise BrianError('No encontré un almacén.')
        return bodegas

    @api.model
    def _b_variantes_para_ajustar(self, cantidad, productos=None, categoria=None, todos=False, almacen=None):
        """``(bodega, variantes que cambian, variantes que ya están así, productos sin inventario)``.

        ``todos`` solo sirve para dejar en cero: toma los productos que hoy tienen existencias en ese almacén."""
        if cantidad is None or cantidad < 0:
            raise BrianError('La cantidad contada no puede ser negativa.')
        bodega = self._b_bodega_para_ajustar(almacen)
        ubicacion = bodega.lot_stock_id
        Producto = self.env['product.product']
        if todos:
            if cantidad:
                raise BrianError('«Todos» solo sirve para dejar en cero. Para otra cantidad dime cuáles productos '
                                 '(códigos o una categoría).')
            if productos or categoria:
                raise BrianError('Dime «todos» o una lista de productos o una categoría, no las dos cosas.')
            quants = self.env['stock.quant'].search([('location_id', 'child_of', ubicacion.id),
                                                     ('quantity', '!=', 0)])
            candidatos = quants.product_id.filtered('is_storable')
            sin_inventario = Producto
        else:
            plantillas = self._b_productos_bloque(productos, categoria, maximo=MAX_BLOQUE_EXISTENCIAS)
            variantes = plantillas.product_variant_ids
            candidatos = variantes.filtered('is_storable')
            sin_inventario = variantes - candidatos
        if len(candidatos) > MAX_BLOQUE_EXISTENCIAS:
            raise BrianError(f'Son {len(candidatos)} productos; el máximo por vez es {MAX_BLOQUE_EXISTENCIAS}. '
                             'Pártelo por categorías.')
        con_ubicacion = candidatos.with_context(location=ubicacion.id)
        cambian = con_ubicacion.filtered(lambda v: round(v.qty_available, 4) != round(cantidad, 4))
        return bodega, cambian, candidatos - cambian, sin_inventario

    @herramienta(
        nombre='ajustar_existencias_en_bloque',
        descripcion='Ajuste de inventario de varios productos a la vez: deja la misma cantidad en todos (lo normal es '
                    'dejarlos en cero). Por códigos, por categoría o «todos» (solo para cero).',
        parametros={
            'cantidad': {'type': 'number', 'description': 'Cantidad que debe quedar en cada uno, p. ej. 0.'},
            'productos': {'type': 'string', 'description': 'Códigos o nombres separados por «;», p. ej. '
                                                           '«SOF-001; SOF-002». Opcional si das categoría o todos.'},
            'categoria': {'type': 'string', 'description': 'Toda una categoría, p. ej. «Salas». Opcional.'},
            'todos': {'type': 'boolean', 'description': 'true = todos los productos que hoy tienen existencias en el '
                                                        'almacén (solo con cantidad 0).'},
            'almacen': {'type': 'string', 'description': 'Nombre del almacén. Opcional si solo hay uno.'},
            'motivo': {'type': 'string', 'description': 'Por qué se ajusta (queda en la bitácora de bodega), p. ej. '
                                                        '«arranque del inventario». Pregúntalo.'},
        },
        requeridos=['cantidad', 'motivo'],
        nivel='sensible', categoria='catalogo', grupos=GERENTE_INVENTARIO,
        ejemplos=['pon todos los productos en cero stock → todos=true, cantidad=0',
                  'deja en cero la categoría Salas → categoria=Salas, cantidad=0',
                  'deja en 3 el SOF-001 y el SOF-002 → productos=«SOF-001; SOF-002», cantidad=3'],
    )
    def _h_ajustar_existencias_en_bloque(self, cantidad, productos=None, categoria=None, todos=False, almacen=None,
                                         motivo=None):
        if not (productos or categoria or todos):
            raise BrianError('Dime cuáles: «productos» (códigos separados por «;»), una «categoria» o «todos».')
        motivo = (motivo or '').strip()
        if not motivo:
            raise BrianError('Dime el motivo del ajuste (p. ej. «arranque del inventario»): queda en la bitácora.')
        bodega, cambian, iguales, sin_inventario = self._b_variantes_para_ajustar(
            cantidad, productos, categoria, todos, almacen)
        ubicacion = bodega.lot_stock_id
        if cambian:
            quants = self.env['stock.quant'].with_context(inventory_mode=True).create([
                {'product_id': v.id, 'location_id': ubicacion.id, 'inventory_quantity': cantidad} for v in cambian])
            quants.with_context(inventory_name=motivo, dcasa_origen='brian').action_apply_inventory()
        return {
            'mensaje': f'Dejé {c.cantidad(cantidad)} en {c.plural(len(cambian), "producto")} ({bodega.name})'
                       + (f'; {len(iguales)} ya estaban así.' if iguales else '.'),
            'cambiados': cambian[:c.MAX_FILAS].mapped('display_name'),
            'omitidos': ({'no llevan inventario': sin_inventario[:c.MAX_FILAS].mapped('display_name')}
                         if sin_inventario else {}),
        }

    @api.model
    def _b_valor_de_precio(self, valor, porcentaje):
        """``(precio fijo o None, porcentaje o None)`` validados."""
        if (valor in (None, '')) == (porcentaje in (None, '')):
            raise BrianError('Para el precio dime UNA cosa: el «valor» nuevo (p. ej. 399.99) o un «porcentaje» '
                             '(p. ej. 10 para subir 10 %, -5 para bajar 5 %).')
        try:
            if valor not in (None, ''):
                fijo = float(str(valor).replace('$', '').replace(',', ''))
                if fijo < 0:
                    raise BrianError('El precio no puede ser negativo.')
                return fijo, None
            pct = float(str(porcentaje).replace('%', '').replace(',', '.'))
        except ValueError as error:
            raise BrianError(f'«{valor if valor not in (None, "") else porcentaje}» no es un número.') from error
        if pct <= -100:
            raise BrianError('El porcentaje no puede dejar el precio en cero o menos.')
        return None, pct

    @api.model
    def _b_cambios_en_bloque(self, plantillas, campo, valor=None, porcentaje=None):
        """Lista de ``(plantilla, valor_nuevo, texto)`` que cambiarían (solo los que de verdad cambian)."""
        if campo not in CAMPOS_EN_BLOQUE:
            raise BrianError(f'En bloque solo puedo cambiar: {", ".join(CAMPOS_EN_BLOQUE)}.')
        cambios = []
        if campo == 'precio':
            fijo, pct = self._b_valor_de_precio(valor, porcentaje)
            for plantilla in plantillas:
                nuevo = fijo if pct is None else round(plantilla.list_price * (1 + pct / 100), 2)
                if round(plantilla.list_price, 2) != round(nuevo, 2):
                    cambios.append((plantilla, nuevo, f'{c.moneda(plantilla.list_price)} → {c.moneda(nuevo)}'))
        elif campo == 'categoria':
            if not valor:
                raise BrianError('Dime la categoría nueva en «valor».')
            categoria = self._b_categoria(str(valor))
            for plantilla in plantillas:
                if plantilla.categ_id != categoria:
                    texto = f'{plantilla.categ_id.display_name} → {categoria.display_name}'
                    cambios.append((plantilla, categoria, texto))
        else:
            vendible = str(valor).strip().lower() in ('1', 'true', 'si', 'sí', 'yes')
            if str(valor).strip().lower() not in ('1', '0', 'true', 'false', 'si', 'sí', 'no', 'yes'):
                raise BrianError('Para «vendible» el valor es sí o no.')
            for plantilla in plantillas:
                if bool(plantilla.sale_ok) != vendible:
                    cambios.append((plantilla, vendible, 'vendible' if vendible else 'ya no vendible'))
        return cambios

    @herramienta(
        nombre='actualizar_productos_en_bloque',
        descripcion='Cambia varios productos a la vez (por códigos o por categoría): el precio (sin ITBMS; un valor '
                    'fijo o un porcentaje), la categoría o si son vendibles.',
        parametros={
            'campo': {'type': 'string', 'enum': list(CAMPOS_EN_BLOQUE), 'description': 'Qué cambiar.'},
            'productos': {'type': 'string', 'description': 'Códigos o nombres separados por «;». Opcional si das '
                                                           'categoría.'},
            'categoria': {'type': 'string', 'description': 'Toda una categoría, p. ej. «Salas». Opcional.'},
            'valor': {'type': 'string', 'description': 'El valor nuevo: precio fijo (399.99), la categoría nueva o '
                                                       'sí/no para vendible.'},
            'porcentaje': {'type': 'number', 'description': 'Solo para el precio: 10 sube 10 %, -5 baja 5 %.'},
        },
        requeridos=['campo'],
        nivel='sensible', categoria='catalogo', grupos=GERENTE_VENTAS,
        ejemplos=['sube 10 % la categoría Salas → campo=precio, categoria=Salas, porcentaje=10',
                  'pon a 99.99 el SOF-001 y el SOF-002 → campo=precio, productos=«SOF-001; SOF-002», valor=99.99',
                  'pasa estos productos a la categoría Colchones → campo=categoria, valor=Colchones'],
    )
    def _h_actualizar_productos_en_bloque(self, campo, productos=None, categoria=None, valor=None, porcentaje=None):
        plantillas = self._b_productos_bloque(productos, categoria)
        cambios = self._b_cambios_en_bloque(plantillas, campo, valor, porcentaje)
        campo_odoo = {'precio': 'list_price', 'categoria': 'categ_id', 'vendible': 'sale_ok'}[campo]
        for plantilla, nuevo, _texto in cambios:
            plantilla[campo_odoo] = nuevo.id if campo == 'categoria' else nuevo
        return {
            'mensaje': f'Cambié {campo} en {c.plural(len(cambios), "producto")}'
                       + (f' ({len(plantillas) - len(cambios)} ya estaban así).' if len(plantillas) > len(cambios)
                          else '.'),
            'cambiados': [f'{p.display_name}: {texto}' for p, _nuevo, texto in cambios[:c.MAX_FILAS]],
        }

    # ------------------------------------------------------------------
    # Consumo de Brian
    # ------------------------------------------------------------------

    @herramienta(
        nombre='consumo_de_brian',
        descripcion='Cuánto ha usado Brian el proveedor de IA en un periodo: llamadas y tokens por modelo y por '
                    'persona, cuánto se leyó de la caché y el costo estimado.',
        parametros={'periodo': c.PARAM_PERIODO, 'desde': c.PARAM_DESDE, 'hasta': c.PARAM_HASTA},
        nivel='lectura', categoria='usuarios', grupos=ADMIN,
        ejemplos=['¿cuánto gastó Brian este mes?', 'consumo de IA de la semana pasada'],
    )
    def _h_consumo_de_brian(self, periodo=None, desde=None, hasta=None):
        inicio, fin, etiqueta = self._b_rango(periodo, desde, hasta)
        d_inicio, d_fin = self._b_limites(inicio, fin)
        dominio = [('create_date', '>=', d_inicio), ('create_date', '<', d_fin)]
        Uso = self.env['brian.uso']
        sumas = ['tokens_entrada:sum', 'tokens_salida:sum', 'tokens_cache_lectura:sum',
                 'tokens_cache_escritura:sum', '__count']
        por_modelo, total_usd, sin_precio = [], 0.0, []
        for modelo, entrada, salida, lectura, escritura, llamadas in Uso._read_group(dominio, ['modelo'], sumas):
            costo = costo_estimado(modelo, entrada, salida, lectura, escritura)
            leidos = entrada + lectura + escritura
            fila = {'modelo': modelo or '—', 'llamadas': llamadas, 'tokens_entrada': entrada + lectura + escritura,
                    'tokens_salida': salida,
                    'leido_de_cache': f'{round(100 * lectura / leidos)} %' if leidos else '0 %'}
            if costo is None:
                fila['costo_estimado'] = 'sin tarifa registrada'
                sin_precio.append(modelo or '—')
            else:
                fila['costo_estimado'] = f'${costo:,.2f}'
                total_usd += costo
            por_modelo.append(fila)
        por_persona = [{'persona': usuario.name or '—', 'llamadas': n}
                       for usuario, n in sorted(Uso._read_group(dominio, ['usuario_id'], ['__count']),
                                                key=lambda g: -g[1])[:10]]
        return {
            'periodo': etiqueta,
            'por_modelo': por_modelo,
            'por_persona': por_persona,
            'costo_estimado_total': f'${total_usd:,.2f}' + (' (más modelos sin tarifa)' if sin_precio else ''),
            'nota': 'Estimado con las tarifas públicas por millón de tokens; la factura del proveedor manda.',
        }


class BrianPoliticaOperacion(models.AbstractModel):
    _inherit = 'brian.politica'

    @api.model
    def _resumir_ajustar_existencias_en_bloque(self, argumentos):
        """La tarjeta dice CUÁNTOS y CUÁLES quedarán en esa cantidad antes del clic."""
        Herramientas = self.env['brian.herramientas']
        try:
            cantidad = float(argumentos.get('cantidad'))
            bodega, cambian, iguales, sin_inventario = Herramientas._b_variantes_para_ajustar(
                cantidad, argumentos.get('productos'), argumentos.get('categoria'),
                bool(argumentos.get('todos')), argumentos.get('almacen'))
        except (BrianError, TypeError, ValueError):
            return ''
        lineas = [f'Dejar en {c.cantidad(cantidad)} las existencias de {c.plural(len(cambian), "producto")} '
                  f'en {bodega.name}:']
        lineas += [f'• {nombre}' for nombre in cambian[:10].mapped('display_name')]
        if len(cambian) > 10:
            lineas.append(f'• … y {len(cambian) - 10} más')
        if iguales:
            lineas.append(f'Ya están así: {len(iguales)}.')
        if sin_inventario:
            lineas.append(f'Se saltan {len(sin_inventario)} (no llevan inventario).')
        if (argumentos.get('motivo') or '').strip():
            lineas.append(f'Motivo (queda en la bitácora de bodega): {argumentos["motivo"].strip()}')
        return '\n'.join(lineas)

    @api.model
    def _resumir_actualizar_productos_en_bloque(self, argumentos):
        """La tarjeta dice qué cambia en cada producto antes del clic."""
        Herramientas = self.env['brian.herramientas']
        try:
            plantillas = Herramientas._b_productos_bloque(argumentos.get('productos'), argumentos.get('categoria'))
            cambios = Herramientas._b_cambios_en_bloque(
                plantillas, argumentos.get('campo'), argumentos.get('valor'), argumentos.get('porcentaje'))
        except BrianError:
            return ''
        lineas = [f'Cambiar {argumentos.get("campo")} en {c.plural(len(cambios), "producto")}:']
        lineas += [f'• {p.display_name}: {texto}' for p, _nuevo, texto in cambios[:10]]
        if len(cambios) > 10:
            lineas.append(f'• … y {len(cambios) - 10} más')
        if len(plantillas) > len(cambios):
            lineas.append(f'Ya estaban así: {len(plantillas) - len(cambios)}.')
        return '\n'.join(lineas)

    @api.model
    def _resumir_publicar_productos_en_bloque(self, argumentos):
        """La tarjeta dice CUÁNTOS y CUÁLES antes del clic (y cuáles se saltarán)."""
        Herramientas = self.env['brian.herramientas']
        try:
            plantillas = Herramientas._b_productos_bloque(argumentos.get('productos'), argumentos.get('categoria'))
        except BrianError:
            return ''
        publicar = bool(argumentos.get('publicar'))
        listos, omitidos = Herramientas._b_separar_publicables(plantillas) if publicar else (plantillas, {})
        verbo = 'Publicar en la web' if publicar else 'Retirar de la web'
        lineas = [f'{verbo} {c.plural(len(listos), "producto")}:']
        lineas += [f'• {nombre}' for nombre in listos[:10].mapped('display_name')]
        if len(listos) > 10:
            lineas.append(f'• … y {len(listos) - 10} más')
        for motivo, registros in omitidos.items():
            lineas.append(f'Se saltan {len(registros)} ({motivo}).')
        return '\n'.join(lineas)
