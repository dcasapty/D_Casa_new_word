"""Herramientas del catálogo: productos, precios, medidas, web y existencias."""
from odoo import api, models

from . import herramientas_comun as c
from .registro import BrianError, herramienta

INTERNO = ('base.group_user',)
GERENTE_VENTAS = ('sales_team.group_sale_manager',)
GERENTE_INVENTARIO = ('stock.group_stock_manager',)
PARAM_PRODUCTO = {'type': 'string', 'description': 'Nombre o código del producto, p. ej. «SOF-001» o «colchón queen».'}
PARAM_CATEGORIA = {'type': 'string', 'description': 'Categoría, p. ej. «Colchones» o «Salas».'}
CAMPOS_EDITABLES = {'precio': 'list_price', 'nombre': 'name', 'descripcion': 'description_sale',
                    'medidas': 'dcasa_medidas', 'codigo': 'default_code'}


class BrianHerramientasCatalogo(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @api.model
    def _b_categoria(self, texto):
        return self._b_resolver('product.category', texto, 'categoría',
                                buscar=[('complete_name', 'ilike', texto)])

    @api.model
    def _b_itbms_incluido(self):
        """El mismo ITBMS «incluido» que usa el catálogo de D'CASA (sin crear impuestos nuevos)."""
        base = self.env.company.account_sale_tax_id
        if not base or base.price_include:
            return base
        return self.env['account.tax'].search([
            ('company_id', '=', self.env.company.id), ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', base.amount_type), ('amount', '=', base.amount),
            ('price_include_override', '=', 'tax_included'),
        ], limit=1) or base

    @api.model
    def _b_precios(self, plantilla, precio=None):
        """Precio con y sin ITBMS según los impuestos del producto (en D'CASA, ITBMS incluido)."""
        precio = plantilla.list_price if precio is None else precio
        impuestos = plantilla.taxes_id.filtered(lambda t: t.company_id in self.env.companies or not t.company_id)
        if not impuestos:
            return {'precio': c.moneda(precio)}
        calculo = impuestos.compute_all(precio, currency=self.env.company.currency_id, quantity=1.0,
                                        product=plantilla.product_variant_id)
        return {'precio_con_itbms': c.moneda(calculo['total_included']),
                'precio_sin_itbms': c.moneda(calculo['total_excluded'])}

    @api.model
    def _b_fila_producto(self, plantilla):
        fila = {'producto': plantilla.display_name, 'codigo': plantilla.default_code or '',
                'categoria': plantilla.categ_id.name or '', 'precio': c.moneda(plantilla.list_price)}
        if plantilla.is_storable:
            fila['existencias'] = c.cantidad(plantilla.qty_available)
        return fila

    @api.model
    def _b_ficha_producto(self, plantilla):
        ficha = {
            'producto': plantilla.display_name,
            'codigo': plantilla.default_code or '',
            'categoria': plantilla.categ_id.complete_name or '',
            **self._b_precios(plantilla),
            'medidas': plantilla.dcasa_medidas or '',
            'publicado_en_web': bool(plantilla.is_published),
        }
        if plantilla.dcasa_combo:
            ficha['combo'] = plantilla.dcasa_combo
        if plantilla.description_sale:
            ficha['descripcion'] = plantilla.description_sale[:500]
        if plantilla.product_variant_count > 1:
            ficha['variantes'] = [{
                'variante': v.display_name, 'codigo': v.default_code or '',
                'precio': c.moneda(v.lst_price),
                'existencias': c.cantidad(v.qty_available) if plantilla.is_storable else None,
            } for v in plantilla.product_variant_ids[:c.MAX_FILAS]]
        if plantilla.is_storable:
            ficha['existencias_total'] = c.cantidad(plantilla.qty_available)
            if self.env['stock.quant'].has_access('read'):
                grupos = self.env['stock.quant']._read_group(
                    [('product_id', 'in', plantilla.product_variant_ids.ids), ('location_id.usage', '=', 'internal')],
                    ['warehouse_id'], ['quantity:sum'])
                ficha['existencias_por_almacen'] = [
                    {'almacen': almacen.name if almacen else 'Sin almacén', 'cantidad': c.cantidad(qty)}
                    for almacen, qty in grupos]
        return ficha

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @herramienta(
        nombre='buscar_productos',
        descripcion='Busca productos por nombre o código, categoría, rango de precio y disponibilidad.',
        parametros={
            'texto': {'type': 'string',
                      'description': 'Palabras del nombre o el código, p. ej. «sofá gris». Opcional.'},
            'categoria': PARAM_CATEGORIA,
            'precio_min': {'type': 'number', 'description': 'Precio mínimo (con ITBMS), p. ej. 100.'},
            'precio_max': {'type': 'number', 'description': 'Precio máximo (con ITBMS), p. ej. 500.'},
            'disponibilidad': {'type': 'string', 'enum': ['todos', 'disponibles', 'agotados'],
                               'description': 'Solo con existencias o solo agotados. Por defecto «todos».'},
        },
        nivel='lectura', categoria='catalogo', grupos=INTERNO,
        ejemplos=['colchones de menos de $300 → categoria=Colchones, precio_max=300', '¿qué sofás están agotados?'],
    )
    def _h_buscar_productos(self, texto=None, categoria=None, precio_min=None, precio_max=None,
                            disponibilidad='todos'):
        dominio = [('sale_ok', '=', True)]
        if texto:
            variantes = self.env['product.product'].search([('display_name', 'ilike', texto)])
            dominio.append(('id', 'in', variantes.product_tmpl_id.ids))
        if categoria:
            dominio.append(('categ_id', 'child_of', self._b_categoria(categoria).id))
        if precio_min is not None:
            dominio.append(('list_price', '>=', precio_min))
        if precio_max is not None:
            dominio.append(('list_price', '<=', precio_max))
        if disponibilidad == 'disponibles':
            dominio += ['|', ('is_storable', '=', False), ('qty_available', '>', 0)]
        elif disponibilidad == 'agotados':
            dominio += [('is_storable', '=', True), ('qty_available', '<=', 0)]
        Template = self.env['product.template']
        total = Template.search_count(dominio)
        productos = Template.search(dominio, limit=c.MAX_FILAS, order='name')
        return {'encontrados': total, 'mostrados': len(productos),
                'productos': [self._b_fila_producto(p) for p in productos]}

    @herramienta(
        nombre='ver_producto',
        descripcion='Ficha de un producto: precio con y sin ITBMS, medidas, variantes, si está en la web y '
                    'existencias por almacén.',
        parametros={'producto': PARAM_PRODUCTO}, requeridos=['producto'],
        nivel='lectura', categoria='catalogo', grupos=INTERNO,
        ejemplos=['¿cuánto mide el sofá SOF-001?', '¿cuántos colchones queen hay?'],
    )
    def _h_ver_producto(self, producto):
        return self._b_ficha_producto(self._b_plantilla(producto))

    @herramienta(
        nombre='existencias_bajas',
        descripcion='Productos inventariables con pocas unidades (o agotados), para reponer.',
        parametros={'umbral': {'type': 'integer',
                               'description': 'Mostrar los que tienen esta cantidad o menos. Por defecto 2.'},
                    'limite': c.PARAM_LIMITE},
        nivel='lectura', categoria='catalogo', grupos=INTERNO,
        ejemplos=['¿qué hay que reponer?', 'productos con 5 o menos → umbral=5'],
    )
    def _h_existencias_bajas(self, umbral=2, limite=20):
        umbral = 2 if umbral is None else umbral
        dominio = [('is_storable', '=', True), ('sale_ok', '=', True), ('qty_available', '<=', umbral)]
        Product = self.env['product.product']
        # qty_available no se guarda: se ordena en Python (primero los agotados).
        todas = Product.search(dominio).sorted(lambda v: (v.qty_available, v.display_name))
        variantes = todas[:c.limite(limite, 20)]
        return {'umbral': umbral, 'encontrados': len(todas), 'productos': [
            {'producto': v.display_name, 'codigo': v.default_code or '', 'existencias': c.cantidad(v.qty_available)}
            for v in variantes]}

    @herramienta(
        nombre='listar_categorias',
        descripcion='Las categorías de productos con cuántos productos tiene cada una.',
        nivel='lectura', categoria='catalogo', grupos=INTERNO,
        ejemplos=['¿qué categorías hay?'],
    )
    def _h_listar_categorias(self):
        conteo = dict(self.env['product.template']._read_group(
            [('sale_ok', '=', True)], ['categ_id'], ['__count']))
        categorias = self.env['product.category'].search([], order='complete_name')
        return {'categorias': [{'categoria': cat.complete_name, 'productos': conteo.get(cat, 0)}
                               for cat in categorias[:50]]}

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    @herramienta(
        nombre='crear_producto',
        descripcion='Crea un producto inventariable con precio final (ITBMS incluido). Queda sin publicar en la '
                    'web; para publicarlo usa publicar_producto_web.',
        parametros={
            'nombre': {'type': 'string',
                       'description': 'Nombre que distingue el mueble, p. ej. «Sofá 3 puestos gris».'},
            'precio': {'type': 'number', 'description': 'Precio de venta con ITBMS incluido, p. ej. 499.99.'},
            'categoria': PARAM_CATEGORIA,
            'codigo': {'type': 'string', 'description': 'Código interno o del proveedor, p. ej. «SOF-120». Opcional.'},
            'medidas': {'type': 'string', 'description': 'Medidas, p. ej. «Ancho × Fondo × Alto: 200 × 90 × 85 cm».'},
        },
        requeridos=['nombre', 'precio'],
        nivel='construccion', categoria='catalogo', grupos=GERENTE_VENTAS,
        ejemplos=['crea el producto «Mesa de centro roble» a $149.99 en Salas'],
    )
    def _h_crear_producto(self, nombre, precio, categoria=None, codigo=None, medidas=None):
        nombre = (nombre or '').strip()
        if not nombre:
            raise BrianError('El producto necesita un nombre.')
        if precio is None or precio < 0:
            raise BrianError('El precio tiene que ser un número mayor o igual que cero.')
        if codigo and self.env['product.product'].search_count([('default_code', '=ilike', codigo.strip())]):
            raise BrianError(f'Ya existe un producto con el código «{codigo}». Usa ese o elige otro código.')
        if self.env['product.template'].search_count([('name', '=ilike', nombre)]):
            raise BrianError(f'Ya existe un producto llamado «{nombre}». Revísalo con ver_producto o usa otro nombre.')
        valores = {'name': nombre, 'type': 'consu', 'is_storable': True, 'list_price': precio,
                   'is_published': False}
        impuesto = self._b_itbms_incluido()
        if impuesto:
            valores['taxes_id'] = [(6, 0, impuesto.ids)]
        if categoria:
            valores['categ_id'] = self._b_categoria(categoria).id
        if codigo:
            valores['default_code'] = codigo.strip()
        if medidas:
            valores['dcasa_medidas'] = medidas.strip()
        plantilla = self.env['product.template'].create(valores)
        return {'mensaje': f'Producto «{plantilla.name}» creado (sin publicar en la web).',
                **self._b_ficha_producto(plantilla)}

    @herramienta(
        nombre='actualizar_producto',
        descripcion='Cambia el precio (con ITBMS), el nombre, la descripción, las medidas o el código de un producto.',
        parametros={
            'producto': PARAM_PRODUCTO,
            'campo': {'type': 'string', 'enum': list(CAMPOS_EDITABLES), 'description': 'Qué cambiar.'},
            'valor': {'type': 'string', 'description': 'El valor nuevo, p. ej. «399.99» para el precio.'},
        },
        requeridos=['producto', 'campo', 'valor'],
        nivel='construccion', categoria='catalogo', grupos=GERENTE_VENTAS,
        ejemplos=['sube el SOF-001 a $529.99 → campo=precio, valor=529.99'],
    )
    def _h_actualizar_producto(self, producto, campo, valor):
        if campo not in CAMPOS_EDITABLES:
            raise BrianError(f'Solo puedo cambiar: {", ".join(CAMPOS_EDITABLES)}.')
        plantilla = self._b_plantilla(producto)
        valor = str(valor if valor is not None else '').strip()
        if campo == 'precio':
            try:
                nuevo = float(valor.replace('$', '').replace(',', ''))
            except ValueError as error:
                raise BrianError(f'«{valor}» no es un precio. Escríbelo como 399.99.') from error
            if nuevo < 0:
                raise BrianError('El precio no puede ser negativo.')
            anterior = c.moneda(plantilla.list_price)
            plantilla.list_price = nuevo
            return {'mensaje': f'Precio de «{plantilla.display_name}»: {anterior} → {c.moneda(nuevo)}.',
                    **self._b_precios(plantilla)}
        if campo in ('nombre', 'codigo') and not valor:
            raise BrianError(f'El {campo} no puede quedar vacío.')
        if campo == 'codigo' and plantilla.product_variant_count > 1:
            raise BrianError('Este producto tiene variantes (tamaños): cada una lleva su propio código.')
        if campo == 'codigo' and self.env['product.product'].search_count(
                [('default_code', '=ilike', valor), ('product_tmpl_id', '!=', plantilla.id)]):
            raise BrianError(f'El código «{valor}» ya es de otro producto.')
        plantilla[CAMPOS_EDITABLES[campo]] = valor or False
        return {'mensaje': f'Actualicé {campo} de «{plantilla.display_name}».', **self._b_ficha_producto(plantilla)}

    # ------------------------------------------------------------------
    # Sensibles
    # ------------------------------------------------------------------

    @herramienta(
        nombre='publicar_producto_web',
        descripcion='Publica o despublica un producto en la tienda web de D\'CASA.',
        parametros={'producto': PARAM_PRODUCTO,
                    'publicar': {'type': 'boolean',
                                 'description': 'true para publicar, false para retirarlo de la web.'}},
        requeridos=['producto', 'publicar'],
        nivel='sensible', categoria='catalogo', grupos=GERENTE_VENTAS,
        ejemplos=['publica el SOF-120 en la web → publicar=true', 'quita de la web la mesa roble → publicar=false'],
    )
    def _h_publicar_producto_web(self, producto, publicar):
        plantilla = self._b_plantilla(producto)
        if publicar and not plantilla.sale_ok:
            raise BrianError(f'«{plantilla.display_name}» no está marcado como vendible: no se publica.')
        plantilla.is_published = bool(publicar)
        estado = 'publicado en la web' if publicar else 'retirado de la web'
        aviso = {} if not publicar or plantilla.image_1920 else {
            'aviso': 'No tiene foto: en la tienda se verá sin imagen. Súbele una foto desde el producto.'}
        return {'mensaje': f'«{plantilla.display_name}» {estado}.', **aviso}

    @herramienta(
        nombre='ajustar_existencias',
        descripcion='Ajuste de inventario: deja la cantidad contada de un producto en un almacén.',
        parametros={
            'producto': {'type': 'string', 'description': 'Nombre o código de la variante exacta, '
                                                          'p. ej. «colchón ortopédico (Queen)».'},
            'cantidad': {'type': 'number', 'description': 'Cantidad contada que debe quedar, p. ej. 4.'},
            'almacen': {'type': 'string', 'description': 'Nombre del almacén. Opcional si solo hay uno.'},
        },
        requeridos=['producto', 'cantidad'],
        nivel='sensible', categoria='catalogo', grupos=GERENTE_INVENTARIO,
        ejemplos=['conté 4 SOF-001 en la tienda → cantidad=4'],
    )
    def _h_ajustar_existencias(self, producto, cantidad, almacen=None):
        if cantidad is None or cantidad < 0:
            raise BrianError('La cantidad contada no puede ser negativa.')
        variante = self._b_producto(producto)
        if not variante.is_storable:
            raise BrianError(f'«{variante.display_name}» no lleva inventario.')
        dominio = [('company_id', 'in', self.env.companies.ids)]
        if almacen:
            bodega = self._b_resolver('stock.warehouse', almacen, 'almacén', exactos=('code',), dominio=dominio)
        else:
            bodegas = self.env['stock.warehouse'].search(dominio)
            if len(bodegas) > 1:
                raise BrianError('Hay varios almacenes: ' + '; '.join(bodegas.mapped('name')) + '. Dime en cuál.')
            bodega = bodegas
        ubicacion = bodega.lot_stock_id
        antes = variante.with_context(location=ubicacion.id).qty_available
        quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': variante.id, 'location_id': ubicacion.id, 'inventory_quantity': cantidad})
        quant.action_apply_inventory()
        despues = variante.with_context(location=ubicacion.id).qty_available
        return {'mensaje': f'Existencias de «{variante.display_name}» en {bodega.name}: '
                           f'{c.cantidad(antes)} → {c.cantidad(despues)}.'}
