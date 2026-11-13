"""La búsqueda del sitio y lo que Google no debe mostrar (lote 1 de la web, aprobado por la dueña el 2026-11-13).

* **Páginas para entrar** (``/web/login``, ``/web/signup``, ``/web/reset_password``): Google mostraba «Login -
  D'CASA Panamá» con el texto de la web vieja. Llevan ``noindex`` en la cabecera ``X-Robots-Tag`` y en
  ``<meta name="robots">``.
* **Resultados de búsqueda** (``/shop?search=…``, ``/website/search``): ``noindex, follow``; Google no los guarda,
  pero sí sigue sus enlaces a las fichas.
* **Una tilde no es otra búsqueda.** Odoo buscaba «sofa», no hallaba esa palabra exacta, buscaba la más parecida
  («sofá») y avisaba «Su búsqueda "sofa" no coincidió con nada. Se muestran los resultados para "sofá"». Si la única
  diferencia son tildes o mayúsculas, se muestran los resultados sin ese aviso (en el catálogo, en la lista
  desplegable mientras se escribe y en la búsqueda general).

La regla de las páginas sin índice es una función pura (``robots_de``): la usan la cabecera HTTP y la plantilla.
"""
import re
import unicodedata

from odoo import models
from odoo.http import request

SIN_INDICE = 'noindex'
BUSQUEDA = 'noindex, follow'

# Idioma delante de la dirección (``/es/web/login``, ``/en_US/shop``): Odoo lo acepta en las rutas del sitio.
_IDIOMA = r'(?:/[a-z]{2}(?:_[A-Za-z0-9]{2,4})?)?'
_ENTRAR = re.compile(rf'^{_IDIOMA}/web/(?:login|signup|reset_password)(?:/.*)?$')
_BUSQUEDA_GENERAL = re.compile(rf'^{_IDIOMA}/website/search(?:/.*)?$')
# La lista del catálogo (no la ficha, ni el carrito): /shop, /shop/page/2, /shop/category/salas-3[/page/2].
_LISTA_TIENDA = re.compile(rf'^{_IDIOMA}/shop(?:/category/[^/]+)?(?:/page/\d+)?/?$')


def robots_de(ruta, parametros):
    """``noindex`` para entrar, ``noindex, follow`` para resultados de búsqueda, ``None`` para lo demás."""
    ruta = ruta or ''
    if _ENTRAR.match(ruta):
        return SIN_INDICE
    if _BUSQUEDA_GENERAL.match(ruta):
        return BUSQUEDA
    if _LISTA_TIENDA.match(ruta) and (parametros.get('search') or '').strip():
        return BUSQUEDA
    return None


def sin_tildes(texto):
    """Minúsculas y sin tildes ni diéresis: «Sofá» → «sofa»."""
    texto = unicodedata.normalize('NFKD', str(texto or '').lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


def solo_cambia_una_tilde(buscado, sugerido):
    """¿El término «parecido» que eligió Odoo es el mismo que escribió la persona, salvo tildes o mayúsculas?"""
    return bool(buscado and sugerido) and sin_tildes(buscado).strip() == sin_tildes(sugerido).strip()


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        robots = robots_de(request.httprequest.path, request.httprequest.args)
        if robots and response is not None and 'X-Robots-Tag' not in response.headers:
            response.headers['X-Robots-Tag'] = robots


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_robots(self):
        """Para ``<meta name="robots">`` de la página que se está dibujando (``None``: lo de Odoo)."""
        if not request:
            return None
        return robots_de(request.httprequest.path, request.httprequest.args)

    def _dcasa_categorias_para_buscar(self):
        """Las categorías de «Compra por espacio» que tienen algo publicado: lo que se ofrece cuando una búsqueda no
        encuentra nada (las vacías abrirían WhatsApp: para eso ya está el botón)."""
        return [tarjeta for tarjeta in self._dcasa_categorias() if not tarjeta['whatsapp']]

    def _dcasa_whatsapp_buscar(self, termino):
        """WhatsApp con lo que la persona buscó ya escrito: la vendedora sabe qué responder."""
        termino = ' '.join(str(termino or '').split())[:100]
        return self._dcasa_whatsapp_url(f"Hola D'CASA, busco: {termino}" if termino else None)

    def _search_with_fuzzy(self, search_type, search, limit, order, options):
        count, results, parecido = super()._search_with_fuzzy(search_type, search, limit, order, options)
        if parecido and solo_cambia_una_tilde(search, parecido):
            # Los resultados ya son los de la palabra con tilde: solo se quita el aviso de «se muestran los de…».
            parecido = False
        return count, results, parecido
