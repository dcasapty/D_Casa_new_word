"""«Movimientos» (Inventario › Movimientos): todo lo que entró y salió de un producto, en palabras (pedido de la dueña,
2026-10-22: «en inventario hay un historial de movimientos pero también es muy poco intuitivo»).

Cada movimiento terminado (``stock.move`` en ``done``) es una línea de la línea de tiempo, de lo más nuevo a lo más
viejo: «Entró por la compra P00012 de PROVEEDOR», «Salió por la venta S00123 a CLIENTE», «Ajuste de inventario (+2)»,
«Devolución del cliente…», «Traslado de Bodega a Tienda». Al lado, la cantidad con su signo (lo que entró o salió de
la tienda: las ubicaciones de los almacenes de la empresa, las mismas con que Odoo calcula «Disponible»), quién y
cuándo, y el documento que lo originó (la venta, la compra o la operación).

**Qué tipo es cada movimiento** (``_tipo``; el mismo orden en el dominio de los filtros, ``_dominio_tipo``):

1. ``ajuste``: ajuste de inventario (contar, «Ajustar»), una baja (merma) o cualquier movimiento contra la ubicación de
   pérdidas de inventario.
2. ``devolucion``: una devolución de Odoo (``origin_returned_move_id``), o mercancía que vuelve de un cliente o que
   se le regresa a un proveedor.
3. ``compra``: entra desde un proveedor.
4. ``venta``: sale hacia un cliente.
5. ``traslado``: de una ubicación de la tienda a otra (no cambia lo que hay en total).
6. ``otro``: lo demás (por ejemplo, un envío directo del proveedor al cliente).

**Lo que quedó después de cada movimiento** (solo en la vista de un producto): se parte de lo que hay hoy y se recorre
hacia atrás restando cada movimiento. Solo se muestra si la historia cuadra: la suma de todos los movimientos de ese
producto da exactamente lo que hay hoy. Si no cuadra (existencias cargadas sin movimiento), no se muestra y la pantalla
lo dice: nunca se inventa una existencia.

Solo Gerencia (que es administradora de Inventario) y los administradores: el servidor lo exige en cada llamada.
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import float_is_zero

GRUPOS_MOVIMIENTOS = ('stock.group_stock_manager', 'base.group_system')
ZONA_PANAMA = 'America/Panama'
POR_PAGINA = 50
MAXIMO_POR_PAGINA = 200
MAXIMO_RESULTADOS = 8
TIPOS = ('compra', 'venta', 'devolucion', 'ajuste', 'traslado', 'otro')
NOMBRES_DE_TIPO = {
    'compra': 'Compras', 'venta': 'Ventas', 'devolucion': 'Devoluciones', 'ajuste': 'Ajustes',
    'traslado': 'Traslados', 'otro': 'Otros',
}
# Ubicaciones que guardan mercancía (para el tipo): internas y en tránsito entre almacenes.
DENTRO = ('internal', 'transit')
MESES_CORTOS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')


def _cuando(momento):
    """«22 oct 2026, 3:45 p. m.» (hora de Panamá)."""
    local = pytz.utc.localize(momento).astimezone(pytz.timezone(ZONA_PANAMA))
    hora = local.hour % 12 or 12
    return (f'{local.day} {MESES_CORTOS[local.month - 1]} {local.year}, '
            f'{hora}:{local.minute:02d} {"a. m." if local.hour < 12 else "p. m."}')


def _cantidad(valor):
    """2.0 → «2»; 1.5 → «1.5»."""
    valor = round(float(valor or 0.0), 2)
    return str(int(valor)) if valor.is_integer() else f'{valor:g}'


class DcasaMovimientos(models.AbstractModel):
    _name = 'dcasa.movimientos'
    _description = 'Movimientos de inventario en palabras'

    # ------------------------------------------------------------------
    # Permisos y validación
    # ------------------------------------------------------------------

    @api.model
    def _exigir_permiso(self):
        if not any(self.env.user.has_group(grupo) for grupo in GRUPOS_MOVIMIENTOS):
            raise AccessError(self.env._('«Movimientos» es solo de Gerencia y los administradores.'))

    @api.model
    def _dia(self, valor, cual):
        if valor in (None, False, ''):
            return None
        try:
            dia = fields.Date.to_date(valor)
        except (TypeError, ValueError, OverflowError):
            dia = None
        if not dia:
            raise UserError(self.env._('Escribe la fecha «%(cual)s» completa, por ejemplo 2026-10-01.', cual=cual))
        return dia

    @api.model
    def _limites(self, desde, hasta):
        """Los días de Panamá «desde»–«hasta» (ambos incluidos, cualquiera puede faltar) en UTC sin zona."""
        d0, d1 = self._dia(desde, 'desde'), self._dia(hasta, 'hasta')
        if d0 and d1 and d0 > d1:
            raise UserError(self.env._('Escribe un rango válido: «desde» no puede ser después de «hasta».'))
        zona = pytz.timezone(ZONA_PANAMA)

        def en_utc(dia):
            return zona.localize(datetime.combine(dia, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

        return (en_utc(d0) if d0 else None), (en_utc(d1 + timedelta(days=1)) if d1 else None)

    @api.model
    def _producto(self, producto_id):
        if producto_id in (None, False, ''):
            return None
        if isinstance(producto_id, bool) or not isinstance(producto_id, int):
            raise UserError(self.env._('Elige un producto de la lista.'))
        producto = self.env['product.product'].sudo().with_context(active_test=False).browse(producto_id).exists()
        if not producto or (producto.company_id and producto.company_id not in self.env.companies):
            raise UserError(self.env._('Ese producto no existe.'))
        return producto

    # ------------------------------------------------------------------
    # Buscar un producto
    # ------------------------------------------------------------------

    @api.model
    def buscar_productos(self, texto, limite=MAXIMO_RESULTADOS):
        """Productos de mercancía cuyo nombre, código o código de barras contienen ``texto`` (los que coinciden exacto
        con el código o el código de barras, primero). Exige Gerencia o administrador."""
        self._exigir_permiso()
        texto = str(texto or '').strip()
        if len(texto) < 2:
            return []
        try:
            limite = min(max(int(limite), 1), 20)
        except (TypeError, ValueError):
            limite = MAXIMO_RESULTADOS
        Producto = self.env['product.product'].sudo()
        empresas = [('company_id', 'in', [False] + self.env.companies.ids), ('type', '=', 'consu')]
        exactos = Producto.search(empresas + ['|', ('default_code', '=ilike', texto), ('barcode', '=', texto)],
                                  limit=limite)
        palabras = [p for p in texto.split() if p]
        por_palabra = Domain.AND(
            Domain.OR([Domain('name', 'ilike', p), Domain('default_code', 'ilike', p), Domain('barcode', 'ilike', p)])
            for p in palabras)
        otros = Producto
        if len(exactos) < limite:
            candidatos = Producto.search(Domain.AND([empresas, por_palabra, [('id', 'not in', exactos.ids)]]),
                                         limit=200, order='name, id')
            # Primero los que traen el texto entero (en el nombre o el código), y entre ellos, el nombre más corto.
            frase = texto.lower()
            otros = candidatos.sorted(lambda p: (
                frase not in f'{p.name or ""} {p.default_code or ""}'.lower(), len(p.name or ''), p.id,
            ))[:limite - len(exactos)]
        return [self._ficha(producto) for producto in exactos | otros]

    @api.model
    def _ficha(self, producto):
        return {
            'id': producto.id, 'nombre': producto.display_name, 'codigo': producto.default_code or '',
            'barras': producto.barcode or '', 'unidad': producto.uom_id.name or '',
            'existencia': producto.with_context(allowed_company_ids=self.env.companies.ids).qty_available
            if producto.is_storable else None,
            'lleva_inventario': producto.is_storable,
            'imagen': f'/web/image/product.product/{producto.id}/image_128',
        }

    # ------------------------------------------------------------------
    # Qué es cada movimiento
    # ------------------------------------------------------------------

    @staticmethod
    def _tipo(movimiento):
        """``compra``, ``venta``, ``devolucion``, ``ajuste``, ``traslado`` u ``otro`` (orden del docstring)."""
        origen, destino = movimiento.location_id.usage, movimiento.location_dest_id.usage
        if movimiento.is_inventory or movimiento.scrap_id or 'inventory' in (origen, destino):
            return 'ajuste'
        if movimiento.origin_returned_move_id or (origen == 'customer' and destino in DENTRO) \
                or (origen in DENTRO and destino == 'supplier'):
            return 'devolucion'
        if origen == 'supplier' and destino in DENTRO:
            return 'compra'
        if destino == 'customer' and origen in DENTRO:
            return 'venta'
        if origen in DENTRO and destino in DENTRO:
            return 'traslado'
        return 'otro'

    @staticmethod
    def _dominio_tipo(tipo):
        """El dominio de ``stock.move`` de un tipo, en el orden de ``_tipo`` (cada uno excluye los anteriores)."""
        ajuste = Domain.OR([Domain('is_inventory', '=', True), Domain('scrap_id', '!=', False),
                            Domain('location_id.usage', '=', 'inventory'),
                            Domain('location_dest_id.usage', '=', 'inventory')])
        devolucion = Domain.OR([
            Domain('origin_returned_move_id', '!=', False),
            Domain('location_id.usage', '=', 'customer') & Domain('location_dest_id.usage', 'in', DENTRO),
            Domain('location_id.usage', 'in', DENTRO) & Domain('location_dest_id.usage', '=', 'supplier')])
        compra = Domain('location_id.usage', '=', 'supplier') & Domain('location_dest_id.usage', 'in', DENTRO)
        venta = Domain('location_dest_id.usage', '=', 'customer') & Domain('location_id.usage', 'in', DENTRO)
        traslado = Domain('location_id.usage', 'in', DENTRO) & Domain('location_dest_id.usage', 'in', DENTRO)
        orden = [('ajuste', ajuste), ('devolucion', devolucion), ('compra', compra), ('venta', venta),
                 ('traslado', traslado)]
        anteriores = Domain.TRUE
        for clave, dominio in orden:
            if clave == tipo:
                return anteriores & dominio
            anteriores &= ~dominio
        return anteriores           # «otro»: ninguno de los anteriores

    @api.model
    def _ubicaciones_de_la_tienda(self):
        """Las ubicaciones de los almacenes de las empresas de quien mira: las mismas con que Odoo calcula «Disponible»
        (``qty_available``)."""
        almacenes = self.env['stock.warehouse'].sudo().search([('company_id', 'in', self.env.companies.ids)])
        if not almacenes:
            return self.env['stock.location']
        return self.env['stock.location'].sudo().search([('id', 'child_of', almacenes.view_location_id.ids)])

    @staticmethod
    def _lugar(ubicacion):
        """«Tienda» (la ubicación principal de un almacén se llama como el almacén) o el nombre de la ubicación."""
        almacen = ubicacion.warehouse_id
        if almacen and ubicacion == almacen.lot_stock_id:
            return almacen.name
        return ubicacion.name or ubicacion.display_name

    @api.model
    def _delta(self, movimiento, tienda):
        """Lo que el movimiento sumó (o restó) a la tienda, en la unidad del producto (de sus líneas)."""
        delta = 0.0
        for linea in movimiento.move_line_ids:
            cantidad = linea.quantity_product_uom
            if linea.location_dest_id in tienda and linea.location_id not in tienda:
                delta += cantidad
            elif linea.location_id in tienda and linea.location_dest_id not in tienda:
                delta -= cantidad
        return delta

    @api.model
    def _documento(self, movimiento):
        """El documento que originó el movimiento: la venta, la compra, la operación o la baja."""
        venta = movimiento.sale_line_id.order_id if 'sale_line_id' in movimiento._fields else None
        compra = movimiento.purchase_line_id.order_id if 'purchase_line_id' in movimiento._fields else None
        if venta:
            return {'modelo': 'sale.order', 'id': venta.id, 'nombre': venta.name}
        if compra:
            return {'modelo': 'purchase.order', 'id': compra.id, 'nombre': compra.name}
        if movimiento.picking_id:
            return {'modelo': 'stock.picking', 'id': movimiento.picking_id.id, 'nombre': movimiento.picking_id.name}
        if movimiento.scrap_id:
            return {'modelo': 'stock.scrap', 'id': movimiento.scrap_id.id, 'nombre': movimiento.scrap_id.name}
        return None

    @api.model
    def _texto(self, movimiento, tipo, delta):
        """La frase del movimiento, en palabras sencillas."""
        venta = movimiento.sale_line_id.order_id if 'sale_line_id' in movimiento._fields else None
        compra = movimiento.purchase_line_id.order_id if 'purchase_line_id' in movimiento._fields else None
        operacion = movimiento.picking_id
        socio = (movimiento.picking_id.partner_id or movimiento.partner_id or (venta and venta.partner_id)
                 or (compra and compra.partner_id))
        quien = socio.commercial_partner_id.display_name if socio else ''
        signo = '+' if delta > 0 else ('−' if delta < 0 else '')
        if tipo == 'ajuste':
            if movimiento.scrap_id:
                return self.env._('Se dio de baja (merma) %(baja)s', baja=movimiento.scrap_id.name)
            texto = self.env._('Ajuste de inventario (%(cambio)s)', cambio=f'{signo}{_cantidad(abs(delta))}')
            # El nombre que le puso quien contó (p. ej. «Conteo con lector (Ana)», del Escáner).
            return f'{texto}: {movimiento.inventory_name}' if movimiento.inventory_name else texto
        if tipo == 'devolucion':
            original = movimiento.origin_returned_move_id
            de_venta = original.sale_line_id.order_id if original and 'sale_line_id' in original._fields else None
            de_compra = original.purchase_line_id.order_id if original and 'purchase_line_id' in original._fields \
                else None
            if delta >= 0 or movimiento.location_id.usage == 'customer':
                texto = self.env._('Devolución del cliente %(cliente)s', cliente=quien) if quien else \
                    self.env._('Devolución de un cliente')
                referencia = de_venta or venta
            else:
                texto = self.env._('Devolución al proveedor %(proveedor)s', proveedor=quien) if quien else \
                    self.env._('Devolución a un proveedor')
                referencia = de_compra or compra
            if referencia:
                texto += self.env._(' (de %(documento)s)', documento=referencia.name)
            return texto
        if tipo == 'compra':
            if compra:
                return self.env._('Entró por la compra %(compra)s de %(proveedor)s', compra=compra.name,
                                  proveedor=quien or self.env._('un proveedor'))
            return self.env._('Entró por la recepción %(recepcion)s de %(proveedor)s',
                              recepcion=operacion.name or movimiento.reference or '',
                              proveedor=quien or self.env._('un proveedor'))
        if tipo == 'venta':
            if venta:
                return self.env._('Salió por la venta %(venta)s a %(cliente)s', venta=venta.name,
                                  cliente=quien or self.env._('un cliente'))
            return self.env._('Salió por la entrega %(entrega)s a %(cliente)s',
                              entrega=operacion.name or movimiento.reference or '',
                              cliente=quien or self.env._('un cliente'))
        if tipo == 'traslado':
            linea = movimiento.move_line_ids[:1]
            origen = linea.location_id if linea else movimiento.location_id
            destino = linea.location_dest_id if linea else movimiento.location_dest_id
            return self.env._('Traslado de %(origen)s a %(destino)s', origen=self._lugar(origen),
                              destino=self._lugar(destino))
        return self.env._('Movimiento %(referencia)s: de %(origen)s a %(destino)s',
                          referencia=movimiento.reference or operacion.name or '',
                          origen=movimiento.location_id.display_name, destino=movimiento.location_dest_id.display_name)

    @api.model
    def _fila(self, movimiento, tienda, delta=None, queda=None, con_producto=False):
        tipo = self._tipo(movimiento)
        if delta is None:
            delta = self._delta(movimiento, tienda)
        usuario = movimiento.move_line_ids[:1].write_uid or movimiento.write_uid
        quien = self.env._('El sistema') if not usuario or usuario.id == SUPERUSER_ID else usuario.name
        documento = self._documento(movimiento)
        operacion = movimiento.picking_id.name or ''
        fila = {
            'id': movimiento.id,
            'fecha': fields.Datetime.to_string(movimiento.date),
            'cuando': _cuando(movimiento.date),
            'tipo': tipo, 'tipo_nombre': NOMBRES_DE_TIPO[tipo],
            'texto': self._texto(movimiento, tipo, delta),
            'cantidad': round(delta, 4),
            'sentido': 'entra' if delta > 0 else ('sale' if delta < 0 else 'mueve'),
            'cantidad_texto': (('+' if delta > 0 else '−') + _cantidad(abs(delta))) if delta else
            _cantidad(sum(movimiento.move_line_ids.mapped('quantity_product_uom')) or movimiento.product_qty),
            'queda': queda,
            'quien': quien,
            # La operación de inventario (WH/OUT/00012) cuando el documento es la venta o la compra.
            'operacion': operacion if documento and documento['nombre'] != operacion else '',
            'documento': documento,
        }
        if con_producto:
            fila['producto'] = {'id': movimiento.product_id.id, 'nombre': movimiento.product_id.display_name,
                                'codigo': movimiento.product_id.default_code or ''}
        return fila

    # ------------------------------------------------------------------
    # La línea de tiempo
    # ------------------------------------------------------------------

    @api.model
    def movimientos(self, producto_id=False, desde=False, hasta=False, tipo=False, pagina=0, por_pagina=POR_PAGINA):
        """La línea de tiempo de un producto (con lo que quedó después de cada movimiento, si la historia cuadra) o los
        últimos movimientos de todos los productos. Filtros: días de Panamá ``desde``–``hasta`` y ``tipo``. Exige
        Gerencia o administrador y valida todo antes de leer (con ``sudo``, siempre filtrado a las empresas de quien
        mira)."""
        self._exigir_permiso()
        producto = self._producto(producto_id)
        inicio, fin = self._limites(desde, hasta)
        if tipo in (None, False, ''):
            tipo = None
        elif tipo not in TIPOS:
            raise UserError(self.env._('Elige uno de los tipos de movimiento.'))
        try:
            pagina = max(int(pagina), 0)
            por_pagina = min(max(int(por_pagina), 1), MAXIMO_POR_PAGINA)
        except (TypeError, ValueError):
            raise UserError(self.env._('La página tiene que ser un número.')) from None
        tienda = self._ubicaciones_de_la_tienda()
        if producto:
            return self._de_un_producto(producto, tienda, inicio, fin, tipo, pagina, por_pagina)
        return self._de_todos(tienda, inicio, fin, tipo, pagina, por_pagina)

    @api.model
    def _base(self):
        return [('state', '=', 'done'), ('company_id', 'in', self.env.companies.ids)]

    @api.model
    def _de_un_producto(self, producto, tienda, inicio, fin, tipo, pagina, por_pagina):
        Move = self.env['stock.move'].sudo()
        todos = Move.search(self._base() + [('product_id', '=', producto.id)], order='date desc, id desc')
        hoy = self.env['stock.quant'].sudo()._read_group(
            [('product_id', '=', producto.id), ('location_id', 'in', tienda.ids)], [], ['quantity:sum'])
        existencia = (hoy[0][0] if hoy else 0.0) or 0.0
        deltas = {movimiento.id: self._delta(movimiento, tienda) for movimiento in todos}
        redondeo = producto.uom_id.rounding
        diferencia = existencia - sum(deltas.values())
        cuadra = float_is_zero(diferencia, precision_rounding=redondeo)
        quedas = {}
        if cuadra:
            despues = existencia
            for movimiento in todos:                     # de lo más nuevo a lo más viejo
                quedas[movimiento.id] = round(despues, 4)
                despues -= deltas[movimiento.id]
        elegidos = todos
        if inicio:
            elegidos = elegidos.filtered(lambda m: m.date >= inicio)
        if fin:
            elegidos = elegidos.filtered(lambda m: m.date < fin)
        if tipo:
            elegidos = elegidos.filtered(lambda m: self._tipo(m) == tipo)
        pagina_de = elegidos[pagina * por_pagina:(pagina + 1) * por_pagina]
        return {
            'producto': self._ficha(producto),
            'existencia': round(existencia, 4),
            'cuadra': cuadra,
            'diferencia': round(diferencia, 4),
            'filas': [self._fila(m, tienda, deltas[m.id], quedas.get(m.id)) for m in pagina_de],
            'total': len(elegidos),
            'hay_mas': len(elegidos) > (pagina + 1) * por_pagina,
            'pagina': pagina,
        }

    @api.model
    def _de_todos(self, tienda, inicio, fin, tipo, pagina, por_pagina):
        dominio = Domain(self._base())
        if inicio:
            dominio &= Domain('date', '>=', inicio)
        if fin:
            dominio &= Domain('date', '<', fin)
        if tipo:
            dominio &= self._dominio_tipo(tipo)
        Move = self.env['stock.move'].sudo()
        movimientos = Move.search(dominio, order='date desc, id desc', offset=pagina * por_pagina,
                                  limit=por_pagina + 1)
        return {
            'producto': None,
            'existencia': None,
            'cuadra': None,
            'diferencia': None,
            'filas': [self._fila(m, tienda, con_producto=True) for m in movimientos[:por_pagina]],
            'total': None,
            'hay_mas': len(movimientos) > por_pagina,
            'pagina': pagina,
        }

    @api.model
    def opciones(self):
        """Los tipos para los filtros. Exige Gerencia o administrador."""
        self._exigir_permiso()
        return {'tipos': [{'clave': clave, 'nombre': NOMBRES_DE_TIPO[clave]} for clave in TIPOS]}
