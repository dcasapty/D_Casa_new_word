"""Las herramientas del asistente de clientes (Juan), registradas en el registro de Brian.

Nombres: dentro de Brian llevan el prefijo ``juan_`` (para no chocar con las de uso interno que tienen
el mismo nombre público: ``buscar_productos``, ``ver_producto``, ``listar_categorias``, ``saldo_puntos``).
La API ``/dcasa/juan/v1/herramientas`` las publica SIN el prefijo, que es como las conoce el Worker.

Quién las ve: solo el usuario técnico ``juan`` (grupo ``dcasa_conversaciones.group_juan``, sin los
grupos internos). Cada ejecución queda en ``brian.accion``.

Reglas que se cumplen aquí (docs/JUAN.md y crm-whatsapp.md §3.1):

* **Vista pública**: solo productos PUBLICADOS en la tienda, con el precio «+ ITBMS», existencias solo
  como etiqueta (``disponible``/``pocas``/``agotado``, nunca el número) y nada de costos.
* **Lo que se vende pero no está publicado** (hoy, los colchones) no se muestra, pero tampoco se niega: la búsqueda
  devuelve ``estado: hay_sin_publicar`` con cuántos y su categoría (sin nombres, precios ni existencias, que no están
  revisados para el público) y Juan lo pasa a una vendedora. «No lo manejamos» solo cuando no hay NADA en el sistema
  (incidente del 2026-11-13: Juan negó los colchones y el cliente se fue).
* **Ninguna escribe puntos, precios, stock, facturas ni pagos**, ni lee datos de otros clientes: el
  cliente SIEMPRE sale de la conversación (``juan_conversacion_id``, puesto por la API), nunca de un argumento.
* **Cifras de Socios** solo desde ``puntos.json`` (``reglas_clientes.redactar``).
* **Saldo con PIN**, con el candado del programa (5 fallos → 15 min; 10 → 24 h).

Los datos se leen con ``sudo()`` porque ``juan`` no tiene permisos internos: la protección está en los
filtros (publicados) y en lo que se devuelve (lista blanca de campos), no en los permisos del usuario.
"""
import logging
import re
from collections import Counter

from odoo import api, fields, models
from odoo.addons.dcasa_base.models.codigo_publico import normalizar_codigo_publico
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.addons.website_dcasa.models.black_weekend import leer_combo
from odoo.fields import Domain
from odoo.tools import html2plaintext

from . import celulares
from . import conocimiento_texto as C
from . import horario as H
from . import publico as P
from .ajustes import CANALES_CON_CELULAR
from .brian_juan import GRUPO_JUAN
from .reglas_clientes import redactar
from .tienda import datos_tienda, url_base, website_publico

_logger = logging.getLogger(__name__)

PREFIJO = 'juan_'
GRUPOS = (GRUPO_JUAN,)
MAX_TEXTO = 1000
MAX_VARIANTES = 10
MAX_CONOCIMIENTO = 2000
MAX_PREGUNTA = 500
MAX_GALERIA = 6
MAX_ETIQUETA = 40
AVISO_PRECIOS = ('Los precios son sin ITBMS: el 7 % se suma en el carrito. La disponibilidad es una '
                 'etiqueta del sistema; una vendedora la confirma antes de cualquier compra.')
PARAM_CONSULTA = {'type': 'string', 'description': 'Lo que busca el cliente, con sus palabras: «colchón queen», '
                                                    '«sofá gris», o el código de la ficha, p. ej. «DC-K7M4PX».'}

# Lo que se vende pero no está publicado en la tienda en línea (incidente del 2026-11-13: Juan negó los colchones).
QUE_HACER_SIN_PUBLICAR = (
    'No digas que no lo manejamos ni des modelos, precios ni disponibilidad. Dile al cliente que sí lo trabajamos y '
    'que una vendedora le confirma los modelos y los precios (p. ej. «Sí, trabajamos [lo que busca]. Los modelos y los '
    'precios te los confirma una vendedora.») y llama a pasar_a_vendedora con motivo_para_la_vendedora como motivo.')
NOTA_HAY_SIN_PUBLICAR = (
    'Esto SÍ lo trabajamos: hay productos así en el sistema de D\'CASA, pero no están publicados en la tienda en línea '
    'y sus modelos, precios y disponibilidad no están revisados para clientes. ' + QUE_HACER_SIN_PUBLICAR)
NOTA_CODIGO_SIN_PUBLICAR = (
    'Ese código SÍ es de un producto que trabajamos, pero no está publicado en la tienda en línea y su modelo, precio '
    'y disponibilidad no están revisados para clientes. ' + QUE_HACER_SIN_PUBLICAR)
NOTA_TAMBIEN_SIN_PUBLICAR = (
    'Además hay productos así en el sistema de D\'CASA que no están publicados en la tienda en línea (sin modelos ni '
    'precios para dar). Ofrece primero los de arriba; si lo que pide el cliente no está entre ellos, no digas que no '
    'lo manejamos: dile que otros modelos se los confirma una vendedora y, si los quiere, llama a pasar_a_vendedora '
    'con motivo_para_la_vendedora como motivo.')
NOTA_NO_LO_MANEJAMOS = (
    'Nada coincide con esa búsqueda en todo el sistema de D\'CASA, ni en la tienda en línea ni fuera de ella: aquí sí '
    'puedes decirle que eso no lo manejamos y ofrecerle lo que sí hay (listar_categorias).')
NO_NIEGUES = ('Por esta búsqueda no le digas al cliente que no lo manejamos: si no das con lo que pide, dile que una '
              'vendedora se lo confirma.')
MAX_CATEGORIAS_SIN_PUBLICAR = 5
# Relleno que no dice qué producto es: no cuenta para saber si alguna palabra de la búsqueda sí existe.
PALABRAS_VACIAS = frozenset({'con', 'sin', 'para', 'por', 'los', 'las', 'del', 'una', 'uno', 'unos', 'unas', 'que',
                             'mas', 'muy', 'algo', 'otro', 'otra', 'the', 'and', 'for', 'with'})


def parece_codigo(consulta):
    """Un código (DC-K7M4PX, o una referencia como «DR-1032»), no palabras: una sola pieza con algún número."""
    texto = P.normalizar(consulta).strip()
    return bool(normalizar_codigo_publico(consulta) or re.fullmatch(r'(?=[^ ]*\d)[a-z0-9][a-z0-9./-]{3,}', texto))


class BrianHerramientasJuan(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @api.model
    def _j_conversacion(self):
        """La conversación en la que se usa la herramienta (la pone la API; nunca viene de un argumento)."""
        conversacion_id = self.env.context.get('juan_conversacion_id')
        conversacion = self.env['dcasa.conversacion'].sudo().browse(conversacion_id).exists() \
            if conversacion_id else self.env['dcasa.conversacion']
        if not conversacion:
            raise BrianError('Esta herramienta solo se usa dentro de una conversación con un cliente.')
        return conversacion

    @api.model
    def _j_website(self):
        return website_publico(self.env)

    @api.model
    def _j_base_url(self):
        return url_base(self.env, self._j_website())

    @api.model
    def _j_dominio_publicado(self):
        website = self._j_website()
        if website:
            return website._dcasa_dominio_publicado()
        return [('sale_ok', '=', True), ('is_published', '=', True)]

    @api.model
    def _j_plantillas_publicadas(self):
        return self.env['product.template'].sudo().search(self._j_dominio_publicado())

    @api.model
    def _j_dominio_sin_publicar(self):
        """Lo que D'CASA vende (``sale_ok``, activo) y NO está publicado en la tienda en línea, solo para saber que
        existe: de esto nunca sale un nombre, un precio ni una existencia. Sin servicios (el flete o el premio de Socios
        no son productos que un cliente busque)."""
        dominio = [('sale_ok', '=', True), ('is_published', '=', False), ('type', '!=', 'service')]
        website = self._j_website()
        if website:
            # Lo mismo que acota la tienda (este sitio y su empresa), sin la regla de «publicado» de los visitantes.
            dominio += [('website_id', 'in', [False, website.id]), ('company_id', 'in', [False, website.company_id.id])]
        return dominio

    @api.model
    def _j_plantillas_sin_publicar(self):
        return self.env['product.template'].sudo().search(self._j_dominio_sin_publicar())

    @api.model
    def _j_plantilla_por_codigo(self, codigo, plantillas):
        """La plantilla de ``plantillas`` con ese código: el público (DC-K7M4PX) o, por si el cliente trae la referencia
        del proveedor (de una foto o de una conversación vieja), esa, exacta: un «%» o un «_» no son comodines."""
        codigo = ' '.join(str(codigo or '').split())
        if not codigo or not plantillas:
            return plantillas.browse()
        publico = normalizar_codigo_publico(codigo)
        plantilla = plantillas.filtered(lambda p: p.dcasa_codigo_publico == publico)[:1] if publico else None
        if plantilla:
            return plantilla
        bajo = codigo.lower()
        variantes = self.env['product.product'].sudo().search([
            ('product_tmpl_id', 'in', plantillas.ids), ('default_code', 'ilike', codigo)])
        exacta = variantes.filtered(lambda v: (v.default_code or '').lower() == bajo)[:1]
        if exacta:
            return exacta.product_tmpl_id
        return plantillas.filtered(lambda p: (p.default_code or '').lower() == bajo)[:1]

    @api.model
    def _j_puntuados(self, consulta, candidatos):
        """Las plantillas de ``candidatos`` que coinciden con ``consulta``, la mejor primero."""
        puntuados = []
        for plantilla, nombre, codigo, extra in candidatos:
            puntos = P.puntuar(consulta, nombre, codigo, extra)
            if puntos:
                puntuados.append((-puntos, nombre, plantilla.id, plantilla))
        puntuados.sort(key=lambda t: t[:3])
        return [t[3] for t in puntuados]

    @api.model
    def _j_palabras_que_aparecen(self, consulta, candidatos):
        """Las palabras de la búsqueda (sin relleno) que sí salen en algún producto, aunque no todas en el mismo."""
        vistas = []
        for palabra in re.findall(r'[a-z0-9]+', P.normalizar(consulta)):
            if len(palabra) < 3 or palabra.isdigit() or palabra in PALABRAS_VACIAS or palabra in vistas:
                continue
            if any(P.puntuar(palabra, nombre, codigo, extra) for _plantilla, nombre, codigo, extra in candidatos):
                vistas.append(palabra)
        return vistas

    @api.model
    def _j_sin_publicar(self, busca, plantillas):
        """Lo único que se dice de lo no publicado: cuántos y su categoría de la tienda (sin nombres, precios ni
        existencias), y el motivo para la vendedora que recibe la conversación."""
        # La categoría más común primero («colchón» → Colchones antes que la de una colchoneta suelta).
        cuantas = Counter(c.name for p in plantillas for c in p.public_categ_ids)
        categorias = sorted(cuantas, key=lambda n: (-cuantas[n], n))[:MAX_CATEGORIAS_SIN_PUBLICAR]
        donde = f' ({", ".join(categorias)})' if categorias else ''
        return {
            'sin_publicar': {'cuantos': len(plantillas), 'categorias': categorias},
            'motivo_para_la_vendedora': f'El cliente busca {busca}. Lo tenemos en el sistema{donde}, pero no está '
                                        'publicado en la tienda en línea: confírmale modelos y precios.',
        }

    @api.model
    def _j_existencias(self, plantilla, variante=None):
        """Etiqueta de existencias (nunca el número): la misma que la ficha de la tienda (dcasa_catalogo)."""
        return plantilla._dcasa_disponibilidad(variante)

    @api.model
    def _j_mas_itbms(self, plantilla):
        website = self._j_website()
        if website:
            return bool(website._dcasa_mas_itbms(plantilla))
        return bool(plantilla.sudo().taxes_id)

    @api.model
    def _j_combo(self, plantilla):
        texto = (plantilla.dcasa_combo or '').strip()
        if not texto:
            return None
        combo = leer_combo(texto)
        if not combo:
            return {'texto': texto}   # tal cual viene del catálogo (ya trae su cifra)
        return {'texto': combo['texto'], 'precio': combo['precio'], 'precio_texto': P.precio_texto(combo['precio'])}

    @api.model
    def _j_foto(self, plantilla, base):
        tiene = self.env['ir.attachment'].sudo().search_count([
            ('res_model', '=', 'product.template'), ('res_id', '=', plantilla.id),
            ('res_field', '=', 'image_1920')], limit=1)
        return f'{base}/web/image/product.template/{plantilla.id}/image_1024' if tiene else None

    @api.model
    def _j_agregable(self, plantilla):
        """¿Se agrega al carrito sin pasar por la ficha? Las reglas del «Agregar» de un clic de la tienda (una sola
        variante, sin atributos que elegir, sin combo ni opcionales y con precio). Para las tarjetas de «Brian de la
        tienda»: si no, la tarjeta lleva a la ficha. La ruta del carrito lo vuelve a comprobar."""
        website = self._j_website()
        precio = plantilla.list_price
        if not website or not plantilla.sale_ok or not precio or precio <= 0:
            return False
        return bool(website._dcasa_compra_directa(plantilla, precio))

    @api.model
    def _j_ficha_corta(self, plantilla, base):
        mas_itbms = self._j_mas_itbms(plantilla)
        foto = self._j_foto(plantilla, base)
        return {
            'nombre': plantilla._dcasa_nombre_cliente(),   # formato título, como lo lee el cliente (F5)
            # El código público (DC-K7M4PX) es el único que ve el cliente: la referencia del proveedor no sale.
            'codigo': plantilla.dcasa_codigo_publico or '',
            'precio': round(plantilla.list_price, 2),
            'precio_texto': P.precio_texto(plantilla.list_price, mas_itbms),
            'mas_itbms': mas_itbms,
            'disponibilidad': self._j_existencias(plantilla),
            'medidas': plantilla.dcasa_medidas or '',
            'combo': self._j_combo(plantilla),
            'categorias': plantilla.public_categ_ids.mapped('name'),
            'url': f'{base}{plantilla.website_url}' if plantilla.website_url else None,
            'foto': foto,
            # Para las tarjetas de «Brian de la tienda» (contrato_cambios §8): la variante que se agrega, la foto y la
            # ficha en rutas relativas (sirven en producción, staging y local) y si se agrega directo.
            'producto_id': plantilla.product_variant_id.id or None,
            'plantilla_id': plantilla.id,
            'imagen': f'/web/image/product.template/{plantilla.id}/image_512' if foto else None,
            'ruta': plantilla.website_url or None,
            'agregable': self._j_agregable(plantilla),
        }

    @api.model
    def _j_candidatos(self, plantillas):
        """[(plantilla, nombre, códigos, extra)] para la búsqueda por palabras (categorías, tamaños y colores)."""
        variantes = self.env['product.product'].sudo().search_read(
            [('product_tmpl_id', 'in', plantillas.ids)], ['product_tmpl_id', 'default_code'])
        codigos = {}
        for v in variantes:
            if v['default_code']:
                codigos.setdefault(v['product_tmpl_id'][0], []).append(v['default_code'])
        valores = {}
        for v in self.env['product.template.attribute.value'].sudo().search_read(
                [('product_tmpl_id', 'in', plantillas.ids)], ['product_tmpl_id', 'name']):
            valores.setdefault(v['product_tmpl_id'][0], []).append(v['name'])
        resultado = []
        for plantilla in plantillas:
            extra = ' '.join(plantilla.public_categ_ids.mapped('display_name') + valores.get(plantilla.id, []))
            # Para encontrarlo: el código público y, por si el cliente trae el del proveedor, los otros.
            propios = [plantilla.dcasa_codigo_publico or '', plantilla.default_code or '']
            codigo = ' '.join(propios + codigos.get(plantilla.id, []))
            resultado.append((plantilla, plantilla.name, codigo, extra))
        return resultado

    @api.model
    def _j_categorias_que_coinciden(self, texto):
        """Categorías públicas (con sus hijas) cuyo nombre coincide con ``texto``; error con la lista si ninguna."""
        Categoria = self.env['product.public.category'].sudo()
        todas = Categoria.search([])
        elegidas = todas.filtered(lambda c: P.puntuar(texto, c.name, '', c.display_name or ''))
        if not elegidas:
            nombres = ', '.join(sorted(set(todas.mapped('name'))))
            raise BrianError(f'No tengo una categoría que se llame «{texto}». Las categorías son: {nombres}. Si no '
                             'es ninguna de esas, vuelve a buscar sin categoría antes de decir que no lo manejamos.')
        return Categoria.search([('id', 'child_of', elegidas.ids)])

    # ------------------------------------------------------------------
    # Catálogo (vista pública)
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'buscar_productos',
        descripcion='Busca productos de la tienda por nombre, código, categoría, tamaño o color: precio (+ ITBMS), '
                    'disponibilidad, medidas, combo, enlace y foto. Sin resultados, sigue el «estado» '
                    '(hay_sin_publicar, busca_de_nuevo o no_lo_manejamos).',
        parametros={
            'consulta': PARAM_CONSULTA,
            'categoria': {'type': 'string', 'description': 'Opcional: una categoría de la tienda, p. ej. «Colchones».'},
            'limite': {'type': 'integer', 'description': f'Cuántos como máximo (1 a {P.LIMITE_MAXIMO}). '
                                                         f'Por defecto {P.LIMITE_POR_DEFECTO}.'},
        },
        requeridos=['consulta'], nivel='lectura', categoria='catalogo', grupos=GRUPOS,
        ejemplos=['«¿tienen camas queen?» → consulta=cama queen',
                  '«colchones» → consulta=colchón, categoria=Colchones'],
    )
    def _juan_buscar_productos(self, consulta, categoria=None, limite=P.LIMITE_POR_DEFECTO):
        consulta = str(consulta or '').strip()[:200]
        if not P.palabras(consulta):
            raise BrianError('Dime qué producto buscas, por ejemplo «cama queen» o el código de la ficha (DC-…).')
        publicadas = self._j_plantillas_publicadas()
        en_la_categoria = publicadas
        if categoria:
            categorias = self._j_categorias_que_coinciden(str(categoria))
            en_la_categoria = publicadas.filtered(lambda p: p.public_categ_ids & categorias)
        candidatos = self._j_candidatos(publicadas)
        todos = self._j_puntuados(consulta, candidatos)
        ids_de_la_categoria = set(en_la_categoria.ids)
        encontrados = [p for p in todos if p.id in ids_de_la_categoria]
        # Lo no publicado se busca igual (las mismas palabras, sin categoría: la pregunta es si D'CASA lo trabaja).
        candidatos_sin_publicar = self._j_candidatos(self._j_plantillas_sin_publicar())
        sin_publicar = self._j_puntuados(consulta, candidatos_sin_publicar)
        if encontrados:
            tope = P.limite_seguro(limite)
            base = self._j_base_url()
            resultado = {
                'encontrados': len(encontrados),
                'mostrados': min(len(encontrados), tope),
                'productos': [self._j_ficha_corta(p, base) for p in encontrados[:tope]],
                'nota': AVISO_PRECIOS,
            }
            if sin_publicar:
                resultado.update(self._j_sin_publicar(f'«{consulta}»', sin_publicar),
                                 nota_sin_publicar=NOTA_TAMBIEN_SIN_PUBLICAR)
            return resultado
        vacio = {'encontrados': 0, 'mostrados': 0, 'productos': []}
        if todos:   # publicados sí hay, pero en otra categoría
            return {**vacio, 'estado': 'busca_de_nuevo',
                    'nota': f'En la categoría «{categoria}» no hay nada así, pero en otras de la tienda sí: vuelve a '
                            f'buscar sin categoría. {NO_NIEGUES}'}
        if sin_publicar:
            return {**vacio, 'estado': 'hay_sin_publicar', **self._j_sin_publicar(f'«{consulta}»', sin_publicar),
                    'nota': NOTA_HAY_SIN_PUBLICAR}
        if parece_codigo(consulta):   # un código mal copiado no es «no lo manejamos»
            return {**vacio, 'estado': 'busca_de_nuevo',
                    'nota': f'No encuentro el código «{consulta}» en el sistema de D\'CASA (puede estar mal escrito): '
                            f'pídele al cliente el nombre o una foto del producto y búscalo así. {NO_NIEGUES}'}
        palabras = self._j_palabras_que_aparecen(consulta, candidatos + candidatos_sin_publicar)
        if palabras:
            return {**vacio, 'estado': 'busca_de_nuevo',
                    'nota': f'Ningún producto tiene todas esas palabras juntas, pero sí hay productos con '
                            f'{", ".join(f"«{p}»" for p in palabras)}: vuelve a buscar con menos palabras (p. ej. '
                            f'solo «{palabras[0]}»). {NO_NIEGUES}'}
        return {**vacio, 'estado': 'no_lo_manejamos', 'nota': NOTA_NO_LO_MANEJAMOS}

    @herramienta(
        nombre=PREFIJO + 'ver_producto',
        descripcion='Ficha completa de un producto publicado por su código: descripción, medidas, variantes '
                    '(tamaños o colores) con su disponibilidad y fotos. Si no está publicado, devuelve estado '
                    'hay_sin_publicar (sin datos del producto).',
        parametros={
            'codigo': {'type': 'string', 'description': 'Código del producto, el que devolvió buscar_productos o el '
                                                        'que dice el cliente: p. ej. «DC-K7M4PX».'},
            'producto_id': {'type': 'integer', 'description': 'En vez del código: el producto_id que devolvió '
                                                              'buscar_productos (o el de la ficha que mira el cliente '
                                                              'en la tienda).'},
        },
        nivel='lectura', categoria='catalogo', grupos=GRUPOS,
        ejemplos=['«¿cuánto mide el DC-K7M4PX?» → codigo=DC-K7M4PX'],
    )
    def _juan_ver_producto(self, codigo=None, producto_id=None):
        codigo = str(codigo or '').strip()[:60]
        if producto_id is not None and not codigo:
            plantilla = self._j_plantilla_por_producto_id(producto_id)
            if not plantilla:
                raise BrianError('Ese producto no está publicado en la tienda en línea. Búscalo por nombre con '
                                 f'buscar_productos y sigue lo que diga. {NO_NIEGUES}')
            return self._j_ficha_completa(plantilla)
        if not codigo:
            raise BrianError('Dime el código del producto (p. ej. «DC-K7M4PX») o su producto_id.')
        plantilla = self._j_plantilla_por_codigo(codigo, self._j_plantillas_publicadas())
        if not plantilla:
            sin_publicar = self._j_plantilla_por_codigo(codigo, self._j_plantillas_sin_publicar())
            if sin_publicar:
                return {'estado': 'hay_sin_publicar', **self._j_sin_publicar(f'el código «{codigo}»', sin_publicar),
                        'nota': NOTA_CODIGO_SIN_PUBLICAR}
            raise BrianError(f'No encuentro el código «{codigo}» en el sistema de D\'CASA (puede estar mal escrito). '
                             f'Búscalo por nombre con buscar_productos y sigue lo que diga. {NO_NIEGUES}')
        return self._j_ficha_completa(plantilla)

    @api.model
    def _j_plantilla_por_producto_id(self, producto_id):
        """La plantilla PUBLICADA de ese ``product.product`` (el ``producto_id`` de las tarjetas); si no, vacía."""
        if isinstance(producto_id, bool) or not isinstance(producto_id, int) or not 0 < producto_id < 2 ** 31:
            return self.env['product.template']
        variante = self.env['product.product'].sudo().browse(producto_id).exists()
        if not variante:
            return self.env['product.template']
        return self.env['product.template'].sudo().search(
            Domain.AND([self._j_dominio_publicado(), [('id', '=', variante.product_tmpl_id.id)]]), limit=1)

    @api.model
    def _j_ficha_completa(self, plantilla):
        base = self._j_base_url()
        ficha = self._j_ficha_corta(plantilla, base)
        descripcion = plantilla.description_sale or html2plaintext(plantilla.description_ecommerce or '')
        ficha['descripcion'] = P.recortar(descripcion)
        mas_itbms = ficha['mas_itbms']
        if plantilla.product_variant_count > 1:
            # Sin código por variante: el código público es del producto y la medida o el color se elige con «opcion».
            ficha['variantes'] = [{
                'nombre': v._dcasa_nombre_cliente(),
                'precio': round(v.lst_price, 2),
                'precio_texto': P.precio_texto(v.lst_price, mas_itbms),
                'disponibilidad': self._j_existencias(plantilla, v),
            } for v in plantilla.sudo().product_variant_ids[:MAX_VARIANTES]]
        ficha['galeria'] = [f'{base}/web/image/product.image/{i.id}/image_1024'
                            for i in plantilla.product_template_image_ids[:MAX_GALERIA]]
        ficha['nota'] = AVISO_PRECIOS
        return ficha

    @herramienta(
        nombre=PREFIJO + 'listar_categorias',
        descripcion='Las categorías de la tienda con cuántos productos publicados tiene cada una y su enlace, y el '
                    'enlace del catálogo completo en la página de D\'CASA (catalogo_completo).',
        nivel='lectura', categoria='catalogo', grupos=GRUPOS,
        ejemplos=['«¿qué venden?» → listar_categorias',
                  '«¿me pasas el catálogo?» o «quiero ver todo lo que tienen» → listar_categorias y das el enlace '
                  'de catalogo_completo'],
    )
    def _juan_listar_categorias(self):
        dominio = self._j_dominio_publicado()
        Plantilla = self.env['product.template'].sudo()
        base = self._j_base_url()
        categorias = []
        for categoria in self.env['product.public.category'].sudo().search([]).sorted('display_name'):
            cuantos = Plantilla.search_count([*dominio, ('public_categ_ids', 'child_of', categoria.id)])
            if cuantos:
                categorias.append({
                    'nombre': categoria.name, 'ruta': categoria.display_name or categoria.name, 'productos': cuantos,
                    'url': f"{base}/shop/category/{self.env['ir.http']._slug(categoria)}"})
        # Pedido de la dueña (2026-11-03): si alguien pide el catálogo completo, que lo vea en la página.
        return {
            'catalogo_completo': f'{base}/shop',
            'categorias': categorias,
            'nota': 'Si el cliente pide el catálogo completo o ver todo lo que hay, dale el enlace de '
                    'catalogo_completo: ahí ve todos los productos publicados con sus fotos. Si busca algo '
                    'concreto, dale también el enlace de esa categoría o búscalo con buscar_productos.',
        }

    # ------------------------------------------------------------------
    # Socios D'CASA
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'reglas_socios',
        descripcion="Las reglas reales del programa Socios D'CASA (puntos, canje, invitados, cumpleaños) ya en "
                    'lenguaje de cliente. Es la ÚNICA fuente de cifras de puntos: no las digas de memoria.',
        nivel='lectura', categoria='clientes', grupos=GRUPOS,
        ejemplos=['«¿cómo funcionan los puntos?» → reglas_socios'],
    )
    def _juan_reglas_socios(self):
        return redactar(R.cargar_reglas(), self._j_base_url())

    @herramienta(
        nombre=PREFIJO + 'saldo_puntos',
        descripcion='Puntos de Socios del cliente de ESTA conversación, solo si da su celular y su PIN de socio. '
                    'Por seguridad solo funciona con el mismo número de WhatsApp desde el que escribe.',
        parametros={
            'celular': {'type': 'string',
                        'description': 'Su celular, p. ej. «6026-1919». Debe ser el de esta conversación.'},
            'pin': {'type': 'string', 'description': 'Su PIN de socio (6 números). Nunca lo repitas ni lo anotes.'},
        },
        requeridos=['celular', 'pin'], nivel='lectura', categoria='clientes', grupos=GRUPOS,
        ejemplos=['«¿cuántos puntos tengo?» → pide el PIN y usa saldo_puntos'],
    )
    def _juan_saldo_puntos(self, celular, pin):
        conversacion = self._j_conversacion()
        if conversacion.canal not in CANALES_CON_CELULAR:
            return self._j_no_verificado(
                'canal_sin_celular', 'Por este canal no puedo comprobar tu número. Escríbenos por WhatsApp '
                                     'o una vendedora te ayuda con tus puntos.')
        ficha = conversacion.partner_id.sudo().commercial_partner_id
        pedido = celulares.interpretar(celular)
        del_canal = celulares.interpretar(conversacion.id_externo)
        de_la_ficha = self.env['res.partner']._dcasa_conv_celular_de_ficha(ficha)
        if not pedido[0] or pedido != del_canal or (de_la_ficha[0] and de_la_ficha != del_canal):
            return self._j_no_verificado(
                'celular_distinto', 'Solo puedo consultar los puntos del mismo número desde el que me escribes.')
        if not ficha.dcasa_reclamada:
            return self._j_no_verificado(
                'sin_registro', f'Todavía no estás en Socios. Entra a {self._j_base_url()}/socios con tu celular '
                                'y elige tu PIN; después te digo tus puntos.')
        ahora = fields.Datetime.now()
        if ficha._dcasa_bloqueada():
            return self._j_no_verificado(
                'bloqueado', 'Tu cuenta de Socios está bloqueada por intentos fallidos. Prueba de nuevo en '
                             f'{R.cuanto_queda(ficha.sudo().dcasa_bloqueado_hasta, ahora)} '
                             'o escríbele a una vendedora.')
        pin = str(pin or '').strip()
        if len(pin) != R.LARGO_PIN or not pin.isdigit():
            return self._j_no_verificado('pin_invalido', f'Tu PIN son {R.LARGO_PIN} números. Vuelve a escribirlo.')
        try:
            correcto = ficha._dcasa_pin_correcto(pin)
        except R.FaltaConfigurar:
            _logger.warning('Juan: no se puede verificar un PIN porque falta DCASA_PIN_PEPPER.')
            return self._j_no_verificado('no_disponible', 'Ahora no puedo comprobar tu PIN. Una vendedora te ayuda.')
        if not correcto:
            # Se devuelve (no se lanza): un error deshace el contador de fallos y el candado no serviría.
            ficha._dcasa_registrar_fallo()
            return self._j_no_verificado('pin_incorrecto', 'Ese PIN no coincide. Revísalo e inténtalo de nuevo.')
        ficha._dcasa_desbloquear()
        if ficha.sudo().dcasa_socio_estado != 'activo':
            return self._j_no_verificado('suspendido', 'Tu cuenta de Socios está en pausa. Una vendedora te ayuda.')
        puntos = ficha.dcasa_saldo
        return {
            'verificado': True,
            'puntos': puntos,
            'puntos_texto': f'{R.como_puntos(puntos)} {"punto" if puntos == 1 else "puntos"}',
            'enlace_para_invitar': f'{self._j_base_url()}/r/{ficha.sudo().dcasa_socio_codigo}',
        }

    @api.model
    def _j_no_verificado(self, motivo, mensaje):
        return {'verificado': False, 'motivo': motivo, 'mensaje': mensaje}

    # ------------------------------------------------------------------
    # La tienda
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'horario_y_tienda',
        descripcion='Dirección real de la tienda, horario de atención, WhatsApp, cómo llegar y la fecha y hora de '
                    'Panamá ahora mismo.',
        nivel='lectura', categoria='general', grupos=GRUPOS,
        ejemplos=['«¿dónde están?» o «¿a qué hora abren?» → horario_y_tienda'],
    )
    def _juan_horario_y_tienda(self):
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        horario = ajustes.horario()
        ahora = fields.Datetime.now()
        return {
            **datos_tienda(self.env),
            'abierto_ahora': H.dentro_de_horario(ahora, horario),
            'fecha_hora_panama': H.texto_fecha_hora(ahora, horario),
        }

    # ------------------------------------------------------------------
    # Conocimiento del equipo y aprendizaje
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'buscar_conocimiento',
        descripcion='Busca en lo que el equipo de D\'CASA escribió para ti (horario, dirección, garantía, Socios, '
                    'cómo comprar…). Devuelve las 3 mejores coincidencias con su texto. Contesta SOLO con eso: '
                    'si no hay nada, no inventes.',
        parametros={'consulta': {'type': 'string', 'description': 'La pregunta del cliente o sus palabras clave, '
                                                                   'p. ej. «horario» o «garantía de colchones».'}},
        requeridos=['consulta'], nivel='lectura', categoria='general', grupos=GRUPOS,
        ejemplos=['«¿a qué hora abren?» → consulta=horario', '«¿tienen garantía?» → consulta=garantía'],
    )
    def _juan_buscar_conocimiento(self, consulta):
        consulta = str(consulta or '').strip()[:300]
        if not C.tokens(consulta):
            raise BrianError('Dime sobre qué tema buscas, por ejemplo «horario» o «garantía».')
        encontrados = self.env['dcasa.conocimiento']._buscar(consulta, 3)
        if not encontrados:
            return {'encontrados': 0, 'resultados': [],
                    'nota': 'El equipo no ha escrito nada sobre eso. No inventes: si el cliente necesita la '
                            'respuesta, usa registrar_pregunta_sin_respuesta y dile que una vendedora se la confirma.'}
        return {
            'encontrados': len(encontrados),
            'resultados': [{
                'titulo': entrada.titulo, 'contenido': (entrada.contenido_vigente or '')[:MAX_CONOCIMIENTO],
                'etiquetas': entrada.etiquetas or '',
                'actualizado': entrada.ultima_revision.isoformat() if entrada.ultima_revision else None,
            } for entrada, _puntos in encontrados],
            # Decisión de la dueña (2026-10-16): Juan explica entregas, financiamiento, apartados y descuentos con lo
            # que escribió el equipo; el caso concreto del cliente y hacer el trámite siguen siendo de una vendedora.
            'nota': 'Contesta solo con lo que dice el equipo, con sus mismas cifras y sin agregar nada. De entregas, '
                    'flete, financiamiento, apartados y descuentos explica solo lo que diga aquí; el caso concreto '
                    'del cliente (costo y fecha de su entrega, si le aprueban el crédito) y hacer el apartado, el '
                    'crédito o el descuento los confirma una vendedora.',
        }

    @herramienta(
        nombre=PREFIJO + 'registrar_pregunta_sin_respuesta',
        descripcion='Anota una pregunta del cliente que no pudiste contestar con las herramientas ni con el '
                    'conocimiento del equipo, para que el equipo la responda y aprendas. Si la misma pregunta se '
                    'repite, solo suma una vez más.',
        parametros={
            'pregunta': {'type': 'string', 'description': 'La pregunta del cliente, completa y con sus palabras.'},
            'resumen': {'type': 'string', 'description': 'Opcional: el contexto en una frase (de qué hablaban).'},
        },
        requeridos=['pregunta'], nivel='construccion', categoria='general', grupos=GRUPOS,
        ejemplos=['no encontraste respuesta sobre «¿instalan los muebles?» → registrar_pregunta_sin_respuesta'],
    )
    def _juan_registrar_pregunta_sin_respuesta(self, pregunta, resumen=None):
        pregunta = ' '.join(str(pregunta or '').split())[:MAX_PREGUNTA]
        if len(pregunta) < 3 or not any(c.isalpha() for c in pregunta):
            raise BrianError('Escribe la pregunta del cliente tal como la hizo.')
        registro, nueva = self.env['dcasa.pregunta_pendiente']._registrar(
            pregunta, resumen, self._j_conversacion())
        return {'registrada': True, 'es_nueva': nueva, 'veces': registro.veces,
                'mensaje': 'Quedó anotada para que el equipo la responda. Dile al cliente que una vendedora se '
                           'lo confirma; no inventes la respuesta.'}

    # ------------------------------------------------------------------
    # Escritura acotada: oportunidad, nota y traspaso
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'crear_oportunidad',
        descripcion='Deja registrado en el CRM lo que el cliente quiere (y su zona y para cuándo, si los dijo) '
                    'para dar seguimiento. No duplica: si ya hay una oportunidad abierta reciente, le agrega una '
                    'nota.',
        parametros={
            'resumen': {'type': 'string',
                        'description': 'Qué pidió el cliente, en 1 a 3 frases con sus datos concretos.'},
            'interes': {'type': 'string',
                        'description': 'El producto o tema en pocas palabras, p. ej. «Cama queen con base».'},
            'presupuesto': {'type': 'number',
                            'description': 'Opcional: solo si el cliente dijo cuánto quiere gastar (USD).'},
            'zona': {'type': 'string',
                     'description': 'Opcional: solo si el cliente dijo dónde vive, en distrito o corregimiento '
                                    '(nunca la dirección exacta).'},
            'cuando': {'type': 'string',
                       'description': 'Opcional: solo si el cliente dijo para cuándo lo quiere, con sus palabras.'},
        },
        requeridos=['resumen', 'interes'], nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['el cliente quiere una cama queen para esta semana → crear_oportunidad(resumen, interes, '
                  'cuando="esta semana")'],
    )
    def _juan_crear_oportunidad(self, resumen, interes, presupuesto=None, zona=None, cuando=None):
        resumen = str(resumen or '').strip()[:MAX_TEXTO]
        interes = str(interes or '').strip()[:120]
        if not resumen or not interes:
            raise BrianError('Necesito un resumen y el interés del cliente para crear la oportunidad.')
        if presupuesto is not None and (isinstance(presupuesto, bool) or not isinstance(presupuesto, (int, float))
                                        or presupuesto < 0):
            raise BrianError('El presupuesto es un número en dólares, mayor o igual que cero.')
        for nombre, valor in (('zona', zona), ('cuando', cuando)):
            if valor is not None and not isinstance(valor, str):
                raise BrianError(f'«{nombre}» es texto: lo que dijo el cliente, con sus palabras.')
        lead, nueva = self._j_conversacion()._oportunidad(
            resumen, interes=interes, presupuesto=presupuesto, zona=zona, cuando=cuando)
        return {'oportunidad_id': lead.id, 'nombre': lead.name, 'nueva': nueva,
                'mensaje': 'Oportunidad creada.' if nueva else 'Ya tenía una oportunidad abierta: le agregué una nota.'}

    @herramienta(
        nombre=PREFIJO + 'anotar_conversacion',
        descripcion='Deja una nota interna en la ficha del cliente (la ven las vendedoras): un dato útil, una '
                    'preferencia, un comprobante recibido. El cliente no la ve.',
        parametros={'nota': {'type': 'string', 'description': 'La nota, corta y concreta.'}},
        requeridos=['nota'], nivel='construccion', categoria='clientes', grupos=GRUPOS,
        ejemplos=['el cliente mandó un comprobante de pago → anotar_conversacion'],
    )
    def _juan_anotar_conversacion(self, nota):
        nota = str(nota or '').strip()[:MAX_TEXTO]
        if not nota:
            raise BrianError('La nota está vacía.')
        conversacion = self._j_conversacion()
        conversacion._nota_en_ficha(nota)
        return {'anotado': True}

    @herramienta(
        nombre=PREFIJO + 'etiquetar_conversacion',
        descripcion='Pone una etiqueta a la conversación para que las vendedoras la encuentren («Pidió precio», '
                    '«Comprobante recibido»…). Solo sirven las etiquetas que ya existen; no se inventan nuevas. '
                    'Si la que escribes no existe, te digo cuáles hay.',
        parametros={'etiqueta': {'type': 'string', 'description': 'El nombre de la etiqueta, tal como existe.'}},
        requeridos=['etiqueta'], nivel='construccion', categoria='clientes', grupos=GRUPOS,
        ejemplos=['el cliente preguntó el precio de un sofá → etiquetar_conversacion(etiqueta="Pidió precio")'],
    )
    def _juan_etiquetar_conversacion(self, etiqueta):
        nombre = ' '.join(str(etiqueta or '').split())[:MAX_ETIQUETA]
        Etiqueta = self.env['dcasa.conversacion.etiqueta'].sudo()
        existente = Etiqueta._buscar_por_nombre(nombre)
        if not existente:
            activas = Etiqueta.search([('activa', '=', True)]).mapped('name')
            if not activas:
                raise BrianError('Todavía no hay etiquetas creadas; no pongas ninguna.')
            raise BrianError(f'No existe la etiqueta «{nombre}». Las etiquetas que existen son: '
                             f'{", ".join(activas)}. Usa una de esas o ninguna.')
        conversacion = self._j_conversacion()
        ya_la_tenia = existente in conversacion.etiqueta_ids
        if not ya_la_tenia:
            conversacion.write({'etiqueta_ids': [(4, existente.id)]})
            conversacion._notificar_panel('etiquetas')
        return {'etiquetada': True, 'etiqueta': existente.name, 'ya_la_tenia': ya_la_tenia}

    @herramienta(
        nombre=PREFIJO + 'pasar_a_vendedora',
        descripcion='Pasa la conversación a una vendedora: el asistente deja de contestar, se crea la tarea y se '
                    'avisa al equipo. Devuelve el texto exacto que debes decirle al cliente según el horario.',
        parametros={
            'motivo': {'type': 'string', 'description': 'Por qué se pasa y qué necesita el cliente.'},
            'urgencia': {'type': 'string', 'enum': ['normal', 'alta'],
                         'description': '«alta» si el cliente está molesto o quiere comprar ya. Por defecto «normal».'},
        },
        requeridos=['motivo'], nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«quiero hablar con una persona» → pasar_a_vendedora'],
    )
    def _juan_pasar_a_vendedora(self, motivo, urgencia='normal'):
        motivo = str(motivo or '').strip()[:MAX_TEXTO]
        if not motivo:
            raise BrianError('Cuéntale a la vendedora por qué se la pasas.')
        return self._j_conversacion()._pasar_a_vendedora(
            motivo, 'alta' if urgencia == 'alta' else 'normal')

