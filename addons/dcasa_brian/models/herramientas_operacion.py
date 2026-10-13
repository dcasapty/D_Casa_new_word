"""Herramientas del día a día de la tienda (ronda 6): reabastecer, comprar, pendientes,
catálogo incompleto, publicar en bloque y consumo de Brian.

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
ADMIN = ('base.group_system',)
MAX_BLOQUE = 200
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
                if proveedor.price:
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
    def _b_productos_bloque(self, productos=None, categoria=None):
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
        if len(encontradas) > MAX_BLOQUE:
            raise BrianError(f'Son {len(encontradas)} productos; el máximo por vez es {MAX_BLOQUE}. Pártelo.')
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
