"""«Marketing»: qué empujar en una campaña, en una sola pantalla (pedido de la dueña, 2026-10-22).

«Créame un botón de Marketing: los productos por categoría con mayor y menor stock, los más vendidos, y poder ver en la
semana, 15 días o el mes los productos con mayor movimiento y los más quietos; allí mismo un apartado para buscar fácil
un producto y subirle sus fotos».

Qué cuenta cada sección (nada se estima ni se inventa: todo sale de la base):

* **Periodo**: Semana, 15 días o Mes son los últimos 7, 15 o 30 días corridos, hoy incluido (hora de Panamá). Corridos y
  no «del lunes» o «del día 1»: así lo quieto no depende de en qué día del mes se mira.
* **Categoría**: el «tipo» del producto, el mismo de «Unidades vendidas por tipo» del Inicio: la categoría de primer
  nivel bajo la raíz (``Muebles / Salas / …`` → «Salas»; una raíz sin padre, como «Colchones», es su propio tipo). Con
  una categoría elegida, TODAS las secciones se filtran a ella.
* **Más y menos stock**: ``dcasa_stock`` (el «A la mano» guardado en el producto, dcasa_catalogo). «Menos stock» deja
  fuera lo agotado (eso no se puede empujar), igual que el favorito «Menor stock primero» de Productos; lo agotado se
  cuenta aparte.
* **Más vendidos**: unidades de las facturas de cliente publicadas del periodo, con la misma base con la que abre el
  Inicio de Gerencia (``BASE_POR_DEFECTO``, «Facturado»): las notas de crédito restan, sin servicios ni anticipos
  (``dcasa.tablero._filas`` y ``_unidades_por_producto``).
* **Movimiento**: lo vendido (lo de arriba) y lo **entregado** (salidas hechas de la bodega a clientes, menos lo que
  devolvieron). Una venta que se factura y se entrega en el mismo periodo es UN movimiento: cuenta lo mayor de las
  dos cifras, no la suma.
* **Más quietos**: con stock y **sin ventas ni entregas** en el periodo. Primero los que nunca se vendieron (en las
  facturas de Odoo) y luego los que llevan más días desde su última venta; a igualdad, el de más stock.
* **Fotos**: los que no tienen foto y los que tienen una sola (la principal sin ninguna extra). No hay una cifra de
  «pocas» inventada: se dice cuántas tiene cada uno.

Gerencia, administradores y el rol «Marketing» (``GRUPOS``): las cifras de toda la tienda, en unidades (sin dinero). El
servidor lo exige.
"""
from collections import defaultdict
from datetime import date, timedelta

from babel.dates import format_date

from odoo import api, fields, models
from odoo.addons.dcasa_interfaz.models.tablero import BASE_POR_DEFECTO
from odoo.exceptions import AccessError, UserError

# Clave → (días corridos, nombre del botón).
PERIODOS = {'semana': (7, 'Semana'), '15_dias': (15, '15 días'), 'mes': (30, 'Mes')}
PERIODO_POR_DEFECTO = 'semana'
FILAS = 8
FILAS_DE_FOTOS = 30
FILTROS_DE_FOTOS = ('faltan', 'sin_foto', 'una_foto', 'todos')
# Gerencia (ventas administrador), administradores y el rol «Marketing» (decisión de la dueña, 2026-10-22: «marketing ve
# todo al igual que Gerencia y administración»; security/marketing_security.xml).
GRUPOS = ('sales_team.group_sale_manager', 'base.group_system', 'dcasa_marketing.group_marketing')
# Los productos que no tienen categoría (Odoo 19 no la exige) también se pueden elegir.
SIN_CATEGORIA = 'sin'


class DcasaMarketing(models.AbstractModel):
    _name = 'dcasa.marketing'
    _description = "Marketing de D'CASA: lo que se mueve, lo quieto y las fotos que faltan"

    # ------------------------------------------------------------------
    # Permisos y filtros
    # ------------------------------------------------------------------

    @api.model
    def _es_de_marketing(self):
        return any(self.env.user.has_group(grupo) for grupo in GRUPOS)

    @api.model
    def _exigir(self):
        if not self._es_de_marketing():
            raise AccessError(self.env._('Marketing es de Gerencia, de los administradores y del rol Marketing.'))

    @api.model
    def _rango(self, periodo):
        """Los días del periodo (ambos incluidos) y cómo se dicen."""
        if periodo in (None, False, ''):
            periodo = PERIODO_POR_DEFECTO
        if periodo not in PERIODOS:
            raise UserError(self.env._('Elige Semana, 15 días o Mes.'))
        dias, nombre = PERIODOS[periodo]
        hoy = fields.Date.context_today(self)
        desde = hoy - timedelta(days=dias - 1)
        return {
            'clave': periodo, 'nombre': nombre, 'dias': dias, 'desde': desde, 'hasta': hoy,
            'etiqueta': self.env._('Últimos %(dias)s días: del %(desde)s al %(hasta)s', dias=dias,
                                   desde=format_date(desde, 'd MMM', locale='es'),
                                   hasta=format_date(hoy, 'd MMM', locale='es')),
        }

    @api.model
    def _tipos(self):
        """``{tipo: [ids de categorías que caen en ese tipo]}`` y el nombre de cada tipo (ver el docstring)."""
        categorias = self.env['product.category'].sudo().search_fetch([], ['name', 'parent_path'])
        del_tipo = defaultdict(list)
        for categoria in categorias:
            camino = [int(i) for i in (categoria.parent_path or '').split('/') if i]
            tipo = camino[1] if len(camino) > 1 else (camino[0] if camino else categoria.id)
            del_tipo[tipo].append(categoria.id)
        nombres = {categoria.id: categoria.name for categoria in categorias}
        return del_tipo, nombres

    @api.model
    def _dominio_base(self):
        """Lo que se vende y se puede empujar: productos activos a la venta que no son servicios (flete)."""
        return [('sale_ok', '=', True), ('active', '=', True), ('type', '!=', 'service')]

    @api.model
    def _categoria_pedida(self, categoria):
        """``(tipo, dominio)`` del tipo elegido (``SIN_CATEGORIA``: los productos sin categoría), o ``(None, [])``
        para todas."""
        if categoria in (None, False, '', 0):
            return None, []
        if categoria == SIN_CATEGORIA:
            return SIN_CATEGORIA, [('categ_id', '=', False)]
        if isinstance(categoria, bool) or not (isinstance(categoria, int) or str(categoria).isdigit()):
            raise UserError(self.env._('Elige una categoría de la lista.'))
        del_tipo, _nombres = self._tipos()
        tipo = int(categoria)
        if tipo not in del_tipo:
            raise UserError(self.env._('Esa categoría ya no existe.'))
        return tipo, [('categ_id', 'in', del_tipo[tipo])]

    # ------------------------------------------------------------------
    # Lo que pide la pantalla
    # ------------------------------------------------------------------

    @api.model
    def datos(self, periodo=None, categoria=None):
        """Todas las secciones de Marketing para un periodo y (opcional) una categoría (el «tipo»)."""
        self._exigir()
        return self._datos(periodo, categoria)

    @api.model
    def buscar_fotos(self, texto='', filtro='faltan', categoria=None):
        """La sección «Fotos»: productos por nombre, código, código de barras o código público, con cuántas fotos
        tiene cada uno."""
        self._exigir()
        return self._buscar_fotos(texto, filtro, categoria)

    @api.model
    def _datos(self, periodo=None, categoria=None):
        rango = self._rango(periodo)
        tipo, filtro = self._categoria_pedida(categoria)
        movimiento = self._movimiento(rango, filtro)
        return {
            'periodo': {k: (fields.Date.to_string(v) if isinstance(v, date) else v) for k, v in rango.items()},
            'periodos': [{'clave': clave, 'nombre': nombre} for clave, (_dias, nombre) in PERIODOS.items()],
            'categorias': self._lista_de_categorias(),
            'categoria': tipo,
            'stock': self._stock(filtro),
            'mas_vendidos': movimiento['mas_vendidos'],
            'mas_movimiento': movimiento['mas_movimiento'],
            'quietos': movimiento['quietos'],
            'quietos_total': movimiento['quietos_total'],
            'quietos_ids': movimiento['quietos_ids'],
            'fotos': self._conteo_de_fotos(filtro),
            'acciones': {
                'campanas': 'sale.product_template_action',
            },
        }

    @api.model
    def _lista_de_categorias(self):
        """Los tipos que tienen productos a la venta, con cuántos, de más a menos."""
        del_tipo, nombres = self._tipos()
        tipo_de = {categoria: tipo for tipo, categorias in del_tipo.items() for categoria in categorias}
        cuenta = defaultdict(int)
        for categoria, cuantos in self.env['product.template']._read_group(
                self._dominio_base(), ['categ_id'], ['__count']):
            cuenta[tipo_de.get(categoria.id, categoria.id) if categoria else SIN_CATEGORIA] += cuantos
        nombres[SIN_CATEGORIA] = self.env._('Sin categoría')
        return sorted(({'id': tipo, 'nombre': nombres.get(tipo, ''), 'productos': cuantos}
                       for tipo, cuantos in cuenta.items() if cuantos),
                      key=lambda fila: (-fila['productos'], fila['nombre'].lower()))

    # ------------------------------------------------------------------
    # Filas de productos
    # ------------------------------------------------------------------

    @api.model
    def _fila(self, plantilla, **extra):
        version = fields.Datetime.to_string(plantilla.write_date or fields.Datetime.now()).replace(' ', '')
        return {
            'id': plantilla.id,
            'nombre': plantilla.name,
            'codigo': plantilla.default_code or '',
            'categoria': plantilla.categ_id.name or '',
            'stock': plantilla.dcasa_stock if plantilla.is_storable else None,
            'imagen': f'/web/image/product.template/{plantilla.id}/image_256?unique={version}',
            'con_foto': bool(plantilla.with_context(bin_size=True).image_1920),
            **extra,
        }

    @api.model
    def _stock(self, filtro):
        Plantilla = self.env['product.template']
        base = self._dominio_base() + filtro + [('is_storable', '=', True)]
        con_stock = base + [('dcasa_stock', '>', 0)]
        cuantos = Plantilla.search_count(con_stock)
        # Con pocos productos las dos listas se partirían el mismo grupo: cada producto sale en una sola (la mitad de
        # arriba en «Más stock», la de abajo en «Menos stock»).
        arriba = min(FILAS, (cuantos + 1) // 2)
        abajo = min(FILAS, cuantos - arriba)
        return {
            'mas': [self._fila(p) for p in Plantilla.search(
                con_stock, order='dcasa_stock desc, name, id', limit=arriba)] if arriba else [],
            'menos': [self._fila(p) for p in Plantilla.search(
                con_stock, order='dcasa_stock asc, name desc, id desc', limit=abajo)] if abajo else [],
            'con_stock': cuantos,
            'agotados': Plantilla.search_count(base + [('dcasa_stock', '<=', 0)]),
        }

    @api.model
    def _vendidas(self, d0, d1):
        """``{id de plantilla: unidades}`` de las facturas publicadas del periodo (la base del Inicio de Gerencia)."""
        Tablero = self.env['dcasa.tablero']
        por_plantilla = defaultdict(float)
        for producto, (unidades, _sin_itbms) in Tablero._unidades_por_producto(
                Tablero._filas(d0, d1, BASE_POR_DEFECTO)).items():
            por_plantilla[producto.product_tmpl_id.id] += unidades
        return por_plantilla

    @api.model
    def _entregadas(self, d0, d1):
        """``{id de plantilla: unidades}`` que salieron de la bodega a clientes en el periodo (entregas hechas), menos
        lo que los clientes devolvieron, en la unidad del producto."""
        Tablero = self.env['dcasa.tablero']
        inicio, _fin = Tablero._limites_del_dia(d0)
        _inicio, fin = Tablero._limites_del_dia(d1)
        movimientos = self.env['stock.move'].sudo().search_fetch([
            ('state', '=', 'done'), ('date', '>=', inicio), ('date', '<', fin),
            ('company_id', 'in', self.env.companies.ids),
            '|', '&', ('location_id.usage', '=', 'internal'), ('location_dest_id.usage', '=', 'customer'),
                 '&', ('location_id.usage', '=', 'customer'), ('location_dest_id.usage', '=', 'internal'),
        ], ['product_id', 'product_uom', 'quantity', 'location_dest_id'])
        por_plantilla = defaultdict(float)
        for movimiento in movimientos:
            producto = movimiento.product_id
            unidades = movimiento.product_uom._compute_quantity(movimiento.quantity, producto.uom_id)
            signo = 1 if movimiento.location_dest_id.usage == 'customer' else -1
            por_plantilla[producto.product_tmpl_id.id] += signo * unidades
        return por_plantilla

    @api.model
    def _ultima_venta(self, plantillas):
        """``{id de plantilla: día de su última factura de cliente publicada}`` (las que nunca se vendieron no
        salen)."""
        if not plantillas:
            return {}
        grupos = self.env['account.move.line'].sudo()._read_group(
            [('move_id.move_type', '=', 'out_invoice'), ('parent_state', '=', 'posted'),
             ('display_type', '=', 'product'), ('product_id.product_tmpl_id', 'in', plantillas.ids),
             ('company_id', 'in', self.env.companies.ids)],
            ['product_id'], ['date:max'])
        ultima = {}
        for producto, dia in grupos:
            plantilla = producto.product_tmpl_id.id
            if dia and (plantilla not in ultima or dia > ultima[plantilla]):
                ultima[plantilla] = dia
        return ultima

    @api.model
    def _movimiento(self, rango, filtro, limite=FILAS):
        """Más vendidos, mayor movimiento y más quietos del periodo (ver el docstring del módulo)."""
        d0, d1 = rango['desde'], rango['hasta']
        vendidas = self._vendidas(d0, d1)
        entregadas = self._entregadas(d0, d1)
        Plantilla = self.env['product.template']
        # Solo lo que se puede empujar (activo, a la venta, no servicio) y, si se eligió, de esa categoría.
        validas = set(Plantilla.search(self._dominio_base() + filtro).ids)
        mas_vendidos = sorted(((pid, u) for pid, u in vendidas.items() if u > 0 and pid in validas),
                              key=lambda par: -par[1])
        movimiento = []
        for pid in (set(vendidas) | set(entregadas)) & validas:
            vendido, entregado = vendidas.get(pid, 0.0), entregadas.get(pid, 0.0)
            if max(vendido, entregado) > 0:
                movimiento.append((pid, max(vendido, entregado), vendido, entregado))
        nombres = {p.id: (p.name or '').lower() for p in Plantilla.browse(
            [pid for pid, _u in mas_vendidos] + [fila[0] for fila in movimiento])}
        mas_vendidos.sort(key=lambda par: (-par[1], nombres.get(par[0], ''), par[0]))
        movimiento.sort(key=lambda fila: (-fila[1], nombres.get(fila[0], ''), fila[0]))

        con_movimiento = [pid for pid in set(vendidas) | set(entregadas)
                          if round(vendidas.get(pid, 0.0), 4) or round(entregadas.get(pid, 0.0), 4)]
        quietos = Plantilla.search(self._dominio_base() + filtro + [
            ('is_storable', '=', True), ('dcasa_stock', '>', 0), ('id', 'not in', con_movimiento)])
        ultima = self._ultima_venta(quietos)
        hoy = rango['hasta']
        ordenados = sorted(quietos, key=lambda p: (ultima.get(p.id) or date.min, -p.dcasa_stock, p.name or '', p.id))
        return {
            'mas_vendidos': [self._fila(Plantilla.browse(pid), unidades=round(u, 2))
                             for pid, u in mas_vendidos[:limite]],
            'mas_movimiento': [self._fila(Plantilla.browse(pid), movimiento=round(total, 2), vendidas=round(v, 2),
                                          entregadas=round(e, 2))
                               for pid, total, v, e in movimiento[:limite]],
            'quietos': [self._fila(
                p, ultima_venta=fields.Date.to_string(ultima[p.id]) if p.id in ultima else None,
                ultima_venta_texto=format_date(ultima[p.id], 'd MMM yyyy', locale='es') if p.id in ultima else None,
                dias_sin_vender=(hoy - ultima[p.id]).days if p.id in ultima else None)
                for p in ordenados[:limite]],
            'quietos_total': len(quietos),
            'quietos_ids': quietos.ids,
        }

    # ------------------------------------------------------------------
    # Fotos
    # ------------------------------------------------------------------

    @api.model
    def _dominio_de_fotos(self, filtro):
        if filtro == 'sin_foto':
            return [('image_1920', '=', False)]
        if filtro == 'una_foto':
            return [('image_1920', '!=', False), ('product_template_image_ids', '=', False)]
        if filtro == 'faltan':
            return ['|', ('image_1920', '=', False), ('product_template_image_ids', '=', False)]
        return []

    @api.model
    def _conteo_de_fotos(self, filtro):
        Plantilla = self.env['product.template']
        base = self._dominio_base() + filtro
        return {
            'sin_foto': Plantilla.search_count(base + self._dominio_de_fotos('sin_foto')),
            'una_foto': Plantilla.search_count(base + self._dominio_de_fotos('una_foto')),
            'productos': Plantilla.search_count(base),
        }

    @api.model
    def _cuantas_fotos(self, plantillas):
        """``{id: cuántas fotos}``: la principal más las extra con imagen (sin videos)."""
        extras = defaultdict(int)
        for plantilla, cuantas in self.env['product.image']._read_group(
                [('product_tmpl_id', 'in', plantillas.ids), ('image_1920', '!=', False), ('video_url', '=', False)],
                ['product_tmpl_id'], ['__count']):
            extras[plantilla.id] = cuantas
        return {p.id: (1 if p.with_context(bin_size=True).image_1920 else 0) + extras[p.id] for p in plantillas}

    @api.model
    def _dominio_de_texto(self, texto):
        """Cada palabra escrita tiene que estar en el nombre, el código, el código de barras o el código público."""
        dominio = []
        for palabra in (texto or '').split()[:6]:
            dominio += ['|', '|', '|', ('name', 'ilike', palabra), ('default_code', 'ilike', palabra),
                        ('product_variant_ids.barcode', 'ilike', palabra), ('dcasa_codigo_publico', 'ilike', palabra)]
        return dominio

    @api.model
    def _buscar_fotos(self, texto='', filtro='faltan', categoria=None, limite=FILAS_DE_FOTOS):
        if filtro not in FILTROS_DE_FOTOS:
            raise UserError(self.env._('Elige qué productos ver: les faltan fotos, sin foto, una sola o todos.'))
        if texto is not None and not isinstance(texto, str):
            raise UserError(self.env._('Escribe el nombre o el código del producto.'))
        _tipo, categoria_filtro = self._categoria_pedida(categoria)
        texto = (texto or '').strip()[:100]
        Plantilla = self.env['product.template']
        dominio = self._dominio_base() + categoria_filtro + self._dominio_de_texto(texto) + \
            self._dominio_de_fotos(filtro)
        encontrados = Plantilla.search(dominio, order='name, id', limit=limite)
        fotos = self._cuantas_fotos(encontrados)
        filas = [self._fila(p, fotos=fotos[p.id]) for p in encontrados]
        if filtro == 'faltan' and not texto:
            filas.sort(key=lambda fila: (fila['fotos'], fila['nombre'].lower(), fila['id']))
        return {
            'texto': texto,
            'filtro': filtro,
            'total': Plantilla.search_count(dominio),
            'mostrando': len(filas),
            'productos': filas,
            'conteo': self._conteo_de_fotos(categoria_filtro),
        }

    @api.model
    def accion_productos(self, ids=None, nombre=None):
        """La lista de Productos (la de las campañas: foto, precio y stock ordenables) con esos productos."""
        self._exigir()
        if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool)
                                                                       for i in ids)):
            raise UserError(self.env._('No entendí qué productos abrir.'))
        accion = self.env['ir.actions.act_window']._for_xml_id('sale.product_template_action')
        if ids is not None:
            accion['domain'] = [('id', 'in', ids[:2000])]
            accion['context'] = {}
        accion['name'] = nombre if isinstance(nombre, str) and nombre.strip() else self.env._('Productos')
        return accion
