"""Lector de códigos de barras: encontrar el producto que se escaneó y contar existencias.

Con un lector que escribe como teclado (Bluetooth, 2.4G, USB, o el Android con lector integrado) el código llega a la
pantalla «Escáner» como si se hubiera tecleado, terminado en Enter. Aquí está lo que esa pantalla le pide al servidor:

* ``buscar``: producto por código de barras, por referencia interna (hoy ninguno tiene código, pero casi todos tienen
  referencia) o por el código de su empaque. Tolera lo que cambia un teclado distinto (guiones, mayúsculas).
* ``buscar_por_nombre`` y ``ficha``: cuando el código no está o la persona prefiere escribir el nombre.
* ``contar``: lo contado reemplaza lo que dice el sistema. Usa el «Inventario físico» de Odoo (``stock.quant`` en modo
  inventario), así que el ajuste queda en el historial de movimientos y ``dcasa_stock`` se actualiza solo.

Permisos (se comprueban aquí, en el servidor, antes de leer o escribir): consultar pide ser usuario de Inventario (la
Vendedora lo es); contar pide ser administrador de Inventario (Gerencia). Nunca se devuelve el costo del producto.
"""
import math
import re

from odoo import api, models, tools
from odoo.addons.dcasa_base.models.codigo_publico import normalizar_codigo_publico
from odoo.exceptions import AccessError, UserError

LARGO_MAXIMO = 64            # un código más largo no es de un lector: se recorta
MAXIMO_CANDIDATOS = 8
MAXIMO_CANTIDAD = 100000     # una cantidad mayor es un error de dedo, no un conteo
UMBRAL_POCAS = 5.0           # igual que Juan, el asistente de clientes (conversaciones/publico.py): ≤ 5 → «pocas»

_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_NO_ALFANUMERICO = re.compile(r'[^0-9A-Za-z]')


def limpiar_codigo(texto):
    """Lo que escribió el lector, sin saltos de línea ni caracteres de control, y de largo razonable."""
    if not isinstance(texto, str):
        return ''
    return _CONTROL.sub('', texto).strip()[:LARGO_MAXIMO]


def clave_tolerante(texto):
    """Solo letras y números, en mayúsculas: «xht022-t-w», «XHT022_T_W» y «XHT022/T/W» son la misma clave.

    Los lectores que escriben como teclado cambian los símbolos si el teclado del equipo está en otro idioma.
    """
    return _NO_ALFANUMERICO.sub('', texto or '').upper()


def etiqueta_existencias(unidades, controla_inventario=True):
    """``disponible`` / ``pocas`` / ``agotado``. Sin control de inventario no hay cifra: se dice «disponible»."""
    if not controla_inventario:
        return 'disponible'
    if unidades <= 0:
        return 'agotado'
    return 'pocas' if unidades <= UMBRAL_POCAS else 'disponible'


def precio_texto(precio):
    """349.99 → «$349.99 + ITBMS» (el precio de D'CASA es sin ITBMS: el 7 % se suma al vender)."""
    return f'${float(precio or 0):,.2f} + ITBMS'


class DcasaBarras(models.AbstractModel):
    _name = 'dcasa.barras'
    _description = "Lector de códigos de barras"

    # ------------------------------------------------------------------
    # Permisos
    # ------------------------------------------------------------------
    def _exigir_inventario(self):
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._("Solo quien trabaja con Inventario puede usar el lector."))

    def _exigir_conteo(self):
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(self.env._("Solo Gerencia (administradores de Inventario) puede registrar conteos."))

    # ------------------------------------------------------------------
    # Buscar
    # ------------------------------------------------------------------
    @api.model
    def buscar(self, codigo):
        """Lo que leyó el lector → ``{'resultado': 'ok'|'varios'|'no_encontrado'|'vacio', 'productos': [...]}``."""
        self._exigir_inventario()
        # El QR de un documento (/dcasa/doc/FAC/INV/2026/00001) es largo: se reconoce ANTES de recortar el código.
        documento = self._documento_de_la_lectura(codigo)
        if documento:
            return documento
        codigo = limpiar_codigo(codigo)
        if not codigo:
            return {'resultado': 'vacio', 'codigo': '', 'productos': [], 'forma': False}
        productos, forma = self._productos_por_codigo(codigo)
        resultado = 'no_encontrado' if not productos else ('ok' if len(productos) == 1 else 'varios')
        return {
            'resultado': resultado,
            'codigo': codigo,
            'forma': forma,
            'productos': [self._ficha_de(p) for p in productos[:MAXIMO_CANDIDATOS]],
            # Una etiqueta numerada que se retiró (docs/BARRAS.md): se avisa en vez de decir solo «no existe».
            'retirada': self._etiqueta_retirada(codigo) if not productos else False,
            # El código es de un producto archivado: el mueble puede seguir en bodega con su etiqueta.
            'archivado': self._producto_archivado_con_codigo(codigo) if not productos else False,
        }

    def _documento_de_la_lectura(self, texto):
        """Si lo que leyó el lector es el código QR de un documento (``…/dcasa/doc/<TIPO>/<REFERENCIA>``): la acción
        para abrirlo, si quien escanea puede verlo; si no, un aviso claro y nada del documento. ``None`` si no lo es.

        ``resultado``: ``documento`` (trae ``accion``), ``documento_sin_permiso`` o ``documento_no_existe`` (traen
        ``mensaje``). Los permisos son los de siempre: lo comprueba ``dcasa.documento``, no esta pantalla.
        """
        encontrado = self.env['dcasa.documento']._dcasa_resolver_texto(texto)
        if encontrado is None:
            return None
        resultado = 'documento' if encontrado['estado'] == 'ok' else f"documento_{encontrado['estado']}"
        return {'resultado': resultado, 'codigo': encontrado['referencia'], 'productos': [], 'forma': False,
                'documento': encontrado}

    def _productos_por_codigo(self, codigo):
        """(productos, cómo se encontró): código de barras, código público (DC-K7M4PX), referencia, código de
        empaque o parecido sin símbolos."""
        Producto = self.env['product.product']
        escapado = codigo.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        publico = normalizar_codigo_publico(codigo)   # con o sin guion y en minúsculas, como lo escriba el lector
        intentos = [
            ('codigo_de_barras', [('barcode', '=', codigo)]),
            # Las etiquetas se guardan en mayúsculas; un lector con las mayúsculas invertidas escribe «dc0001».
            ('codigo_de_barras', [('barcode', '=ilike', escapado)]),
        ]
        if publico:
            # El código que ve el cliente es del producto: lo comparten todas sus medidas y colores, por eso pueden
            # salir «varios» para elegir. Nunca se confunde con una etiqueta del rollo (DC0001…): lleva guion, 6
            # símbolos y al menos una letra.
            intentos.append(('codigo_publico', [('dcasa_codigo_publico', '=', publico)]))
        intentos += [
            ('referencia', [('default_code', '=ilike', escapado)]),
            ('empaque', [('product_uom_ids.barcode', '=', codigo)]),
        ]
        for forma, dominio in intentos:
            encontrados = Producto.search(dominio, limit=MAXIMO_CANDIDATOS + 1)
            if encontrados:
                return encontrados, forma
        clave = clave_tolerante(codigo)
        if len(clave) < 4:   # una clave muy corta se parecería a medio catálogo
            return Producto, False
        # El mismo código sin símbolos ni mayúsculas (el lector puede haber escrito «_» donde había «-»).
        self.env.cr.execute("""
            SELECT id FROM product_product
             WHERE active
               AND (regexp_replace(upper(coalesce(default_code, '')), '[^0-9A-Z]', '', 'g') = %(clave)s
                    OR regexp_replace(upper(coalesce(barcode, '')), '[^0-9A-Z]', '', 'g') = %(clave)s)
             LIMIT %(limite)s""", {'clave': clave, 'limite': MAXIMO_CANDIDATOS + 1})
        ids = [fila[0] for fila in self.env.cr.fetchall()]
        # search() aplica las reglas de acceso (compañía) sobre los ids encontrados
        encontrados = Producto.search([('id', 'in', ids)]) if ids else Producto
        return encontrados, 'parecido' if encontrados else False

    @api.model
    def buscar_por_nombre(self, texto):
        """Hasta 8 productos cuyo nombre, referencia o medida lleven las palabras escritas."""
        self._exigir_inventario()
        texto = limpiar_codigo(texto)
        if len(texto) < 2:
            return []
        # search() (no name_search) para que cuente la búsqueda de varias palabras de dcasa_catalogo
        # («cama queen» encuentra la cama en tamaño Queen).
        encontrados = self.env['product.product'].search([('display_name', 'ilike', texto)], limit=MAXIMO_CANDIDATOS)
        return [{'id': p.id, 'nombre': p.display_name, 'referencia': p.default_code or '',
                 'codigo_de_barras': p.barcode or ''} for p in encontrados]

    @api.model
    def ficha(self, producto_id):
        """La misma tarjeta que sale al escanear, para un producto elegido de una lista."""
        self._exigir_inventario()
        producto = self._producto(producto_id)
        return self._ficha_de(producto)

    def _producto(self, producto_id):
        if isinstance(producto_id, bool) or not isinstance(producto_id, int):
            raise UserError(self.env._("Producto no válido."))
        producto = self.env['product.product'].browse(producto_id).exists()
        if not producto:
            raise UserError(self.env._("Ese producto ya no existe."))
        producto.check_access('read')
        return producto

    # ------------------------------------------------------------------
    # La tarjeta del producto
    # ------------------------------------------------------------------
    def _ubicaciones_internas(self):
        return self.env['stock.location'].search([
            ('usage', '=', 'internal'), ('company_id', 'in', [False, self.env.company.id])])

    def _existencias(self, producto):
        """[(ubicación, unidades)] solo de lo que está en bodega o tienda (ubicaciones internas)."""
        grupos = self.env['stock.quant']._read_group(
            [('product_id', '=', producto.id), ('location_id.usage', '=', 'internal'),
             ('company_id', 'in', [False, self.env.company.id])],
            ['location_id'], ['quantity:sum'])
        return [(ubicacion, cantidad) for ubicacion, cantidad in grupos]

    def _ficha_de(self, producto):
        existencias = self._existencias(producto)
        unidades = sum(cantidad for _u, cantidad in existencias)
        controla = bool(producto.is_storable)
        return {
            'id': producto.id,
            'nombre': producto.display_name,
            'referencia': producto.default_code or '',
            'codigo_publico': producto.dcasa_codigo_publico or '',
            'codigo_de_barras': producto.barcode or '',
            'imagen': f'/web/image/product.product/{producto.id}/image_256',
            'precio': producto.lst_price,
            'precio_texto': precio_texto(producto.lst_price) if producto.lst_price else '',
            'controla_inventario': controla,
            'con_lotes': producto.tracking != 'none',
            'unidad': producto.uom_id.name,
            'admite_decimales': tools.float_is_zero(0.5 - producto.uom_id.round(0.5), precision_digits=6),
            'unidades': unidades if controla else None,
            'etiqueta': etiqueta_existencias(unidades, controla),
            'ubicaciones': [{'id': u.id, 'nombre': u.complete_name, 'cantidad': c} for u, c in existencias],
            'puede_contar': controla and producto.tracking == 'none'
                            and self.env.user.has_group('stock.group_stock_manager'),
            'lugares_para_contar': [
                {'id': u.id, 'nombre': u.complete_name} for u in self._ubicaciones_internas()
            ] if controla else [],
            'ubicacion_habitual': self._ubicacion_habitual(producto, existencias),
        }

    def _ubicacion_habitual(self, producto, existencias):
        """Dónde proponer el conteo: donde ya hay existencias; si no hay, la bodega principal."""
        if existencias:
            return max(existencias, key=lambda par: par[1])[0].id
        almacen = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        return almacen.lot_stock_id.id or False

    # ------------------------------------------------------------------
    # Contar
    # ------------------------------------------------------------------
    @api.model
    def contar(self, producto_id, ubicacion_id, cantidad, esperado):
        """Lo contado reemplaza lo que dice el sistema en esa ubicación; el ajuste queda en el historial.

        ``esperado`` es lo que la pantalla le mostró a quien contó. Si mientras tanto el sistema cambió (una venta, una
        entrada), no se guarda: contar sobre un número viejo dejaría el inventario mal.
        """
        self._exigir_conteo()
        producto = self._producto(producto_id)
        cantidad = self._cantidad_valida(cantidad)
        esperado = self._numero(esperado)
        if not producto.is_storable:
            raise UserError(self.env._("«%s» no controla inventario: no tiene existencias que contar.",
                                       producto.display_name))
        if producto.tracking != 'none':
            raise UserError(self.env._(
                "«%s» se controla por lote o por serie: cuéntalo en Inventario › Inventario físico.",
                producto.display_name))
        unidad = producto.uom_id
        if not tools.float_is_zero(cantidad - unidad.round(cantidad), precision_digits=6):
            raise UserError(self.env._(
                "«%(producto)s» se cuenta en %(unidad)s enteras: no admite decimales.",
                producto=producto.display_name, unidad=unidad.name))
        ubicacion = self._ubicacion_valida(ubicacion_id)
        quants = self.env['stock.quant'].search([('product_id', '=', producto.id), ('location_id', '=', ubicacion.id)])
        if len(quants) > 1:
            raise UserError(self.env._(
                "«%s» tiene varias líneas de existencia en esa ubicación (por dueño, paquete o repetidas): "
                "cuéntalo en Inventario › Inventario físico.", producto.display_name))
        antes = sum(quants.mapped('quantity'))
        if unidad.compare(antes, esperado) != 0:
            raise UserError(self.env._(
                "Mientras contabas, el sistema cambió de %(visto)s a %(ahora)s. Escanea el producto otra vez y "
                "cuenta de nuevo.", visto=f'{esperado:g}', ahora=f'{antes:g}'))
        if unidad.compare(cantidad, antes) == 0:
            return {'cambio': False, 'antes': antes, 'despues': antes, 'diferencia': 0.0,
                    'ficha': self._ficha_de(producto)}
        Quant = self.env['stock.quant'].with_context(
            inventory_mode=True,
            inventory_name=self.env._("Conteo con lector (%s)", self.env.user.name))
        Quant.create({'product_id': producto.id, 'location_id': ubicacion.id, 'inventory_quantity': cantidad}) \
            .action_apply_inventory()
        despues = sum(c for u, c in self._existencias(producto) if u == ubicacion)
        return {'cambio': True, 'antes': antes, 'despues': despues, 'diferencia': despues - antes,
                'ficha': self._ficha_de(producto)}

    def _numero(self, valor):
        if isinstance(valor, bool) or not isinstance(valor, int | float) or not math.isfinite(valor):
            raise UserError(self.env._("La cantidad contada debe ser un número."))
        return float(valor)

    def _cantidad_valida(self, cantidad):
        cantidad = self._numero(cantidad)
        if cantidad < 0 or cantidad > MAXIMO_CANTIDAD:
            raise UserError(self.env._("La cantidad contada debe estar entre 0 y %s.", f'{MAXIMO_CANTIDAD:,}'))
        return cantidad

    def _ubicacion_valida(self, ubicacion_id):
        if isinstance(ubicacion_id, bool) or not isinstance(ubicacion_id, int):
            raise UserError(self.env._("Elige la ubicación donde contaste."))
        ubicacion = self._ubicaciones_internas().filtered(lambda u: u.id == ubicacion_id)
        if not ubicacion:
            raise UserError(self.env._("Esa ubicación no es de bodega ni de tienda."))
        return ubicacion
