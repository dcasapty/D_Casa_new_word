"""La Guía del negocio: «¿Qué necesitas hacer hoy?».

Un catálogo de tareas escrito en palabras sencillas (``data/guia.json``). Cada tarea dice qué quiere hacer la persona
y qué logra al llegar a la pantalla, y lleva un atajo hasta ella. Quien administra un negocio muchas veces no sabe que
existe una pantalla (la declaración de renta, el cierre de mes, una nota de crédito): aquí la ve, la entiende y llega.

* Una tarea solo se muestra si la persona puede abrir su pantalla (los mismos permisos que el menú de la izquierda):
  una vendedora no ve contabilidad, Gerencia sí.
* Nada se inventa: donde hay una fecha límite de impuestos, la nota manda a confirmarla con el contador.
* La misma fuente alimenta la pantalla, la herramienta ``buscar_en_guia`` de Brian y las pruebas (cada atajo debe
  existir; si un módulo cambia un menú, la prueba lo dice).
"""
import json
import os
import unicodedata
from functools import lru_cache

from odoo import api, models

RUTA_CATALOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'guia.json')

# Palabras que no ayudan a buscar.
PALABRAS_VACIAS = frozenset(
    'a al algo con como cual cuales cuando de del donde el ella en es esta este hacer la las le les lo los me mi mis '
    'necesito o para por que quiero se si sin su sus tengo un una uno unos y yo'.split())
MAXIMO_RESULTADOS = 8


def normalizar(texto):
    """Minúsculas y sin tildes, para que «declaración» y «declaracion» sean lo mismo."""
    texto = unicodedata.normalize('NFD', str(texto or '').lower())
    return ''.join(c for c in texto if unicodedata.category(c) != 'Mn')


def palabras_de(consulta):
    return [p for p in normalizar(consulta).replace('?', ' ').replace('¿', ' ').split()
            if len(p) >= 3 and p not in PALABRAS_VACIAS]


@lru_cache(maxsize=1)
def cargar_catalogo(ruta=RUTA_CATALOGO):
    with open(ruta, encoding='utf-8') as archivo:
        return json.load(archivo)


def puntaje(tarea, palabras):
    """Cuánto se parece una tarea a lo que escribió la persona: ``(palabras halladas, puntos)``."""
    campos = (
        (normalizar(tarea['titulo']), 5),
        (' '.join(normalizar(p) for p in tarea.get('palabras', [])), 4),
        (normalizar(tarea.get('grupo')), 2),
        (normalizar(tarea['logras']), 1),
    )
    exactas = {normalizar(p) for p in tarea.get('palabras', [])}
    halladas, puntos = 0, 0
    for palabra in palabras:
        # Una palabra que la tarea declara tal cual («isr» → declaración de renta) vale más que una coincidencia suelta.
        ganado = sum(peso for texto, peso in campos if palabra in texto) + (6 if palabra in exactas else 0)
        if ganado:
            halladas += 1
            puntos += ganado
    return halladas, puntos


class DcasaGuia(models.AbstractModel):
    _name = 'dcasa.guia'
    _description = 'La Guía del negocio'

    # ------------------------------------------------------------------
    # Qué puede abrir quien mira
    # ------------------------------------------------------------------

    @api.model
    def _menus_visibles(self):
        """Los menús que quien mira ve en la barra de la izquierda (grupos y acceso al modelo incluidos)."""
        return set(self.env['ir.ui.menu']._visible_menu_ids())

    @api.model
    def _menu_se_ve(self, menu, visibles):
        """Un menú se ve si él y todos sus padres se ven: Odoo marca visible a un menú sin grupos aunque su app no lo
        sea (la barra de la izquierda lo esconde porque su app está escondida), y la Guía no debe ofrecerlo."""
        actual = menu.sudo()
        while actual:
            if actual.id not in visibles:
                return False
            actual = actual.parent_id
        return True

    @api.model
    def _resolver_destino(self, destino, visibles):
        """Convierte un destino del catálogo en algo que el navegador sabe abrir; ``None`` si no se puede.

        Devuelve ``{'tipo', 'ruta', ...}`` donde ``ruta`` es dónde queda en el menú («Facturación › Reportes
        contables › Estado de resultados»), para que la próxima vez la persona llegue sola.
        """
        if not destino:
            return None
        contexto = destino.get('contexto') or {}
        if destino.get('menu'):
            menu = self.env.ref(destino['menu'], raise_if_not_found=False)
            if not menu or menu._name != 'ir.ui.menu' or not self._menu_se_ve(menu, visibles):
                return None
            return {'tipo': 'menu', 'menu_id': menu.id, 'contexto': contexto,
                    'ruta': ' › '.join(menu.sudo().complete_name.split('/'))}
        modelo = destino.get('nuevo')
        if modelo:
            if modelo not in self.env or not self.env[modelo].has_access('create'):
                return None
            nombre = self.env['ir.model'].sudo()._get(modelo).name
            return {'tipo': 'nuevo', 'modelo': modelo, 'contexto': contexto, 'ruta': f'Crear › {nombre}'}
        return None

    @api.model
    def _tarea_para_mostrar(self, tarea, visibles):
        """La tarea lista para la pantalla, o ``None`` si la persona no puede abrir su destino."""
        destino = self._resolver_destino(tarea.get('destino'), visibles)
        if tarea.get('destino') and not destino:
            return None
        pasos = [{'texto': paso['texto'], 'destino': self._resolver_destino(paso.get('destino'), visibles)}
                 for paso in tarea.get('pasos', [])]
        return {
            'id': tarea['id'], 'categoria': tarea['categoria'], 'tambien': tarea.get('tambien', []),
            'grupo': tarea.get('grupo') or '', 'titulo': tarea['titulo'], 'logras': tarea['logras'],
            'nota': tarea.get('nota') or '', 'brian': tarea.get('brian') or '', 'palabras': tarea.get('palabras', []),
            'destino': destino, 'pasos': pasos,
        }

    @api.model
    def _tareas_visibles(self):
        catalogo = cargar_catalogo()
        visibles = self._menus_visibles()
        tareas = (self._tarea_para_mostrar(t, visibles) for t in catalogo['tareas'])
        return [t for t in tareas if t]

    # ------------------------------------------------------------------
    # API para la pantalla y para Brian
    # ------------------------------------------------------------------

    @api.model
    def obtener(self):
        """Todo lo que la pantalla necesita: categorías con sus tareas (las que quien mira puede abrir) y las que
        conviene mostrar primero. Las categorías sin tareas para esta persona no salen."""
        catalogo = cargar_catalogo()
        tareas = self._tareas_visibles()
        categorias = []
        for categoria in catalogo['categorias']:
            clave = categoria['clave']
            # Primero las tareas que son de este tema; después las que viven en otro y también aplican aquí.
            propias = [t for t in tareas if t['categoria'] == clave] + [t for t in tareas if clave in t['tambien']]
            if propias:
                categorias.append({**categoria, 'tareas': propias})
        por_id = {t['id']: t for t in tareas}
        return {
            'categorias': categorias,
            'empezar': [por_id[i] for i in catalogo.get('empezar', []) if i in por_id],
            'total': len(tareas),
        }

    @api.model
    def buscar(self, consulta, limite=MAXIMO_RESULTADOS):
        """Las tareas que más se parecen a lo que escribió la persona, de las que puede abrir.

        Sin tildes ni mayúsculas, y por trozos de palabra («factur» halla «facturas» y «facturación»). Solo salen las
        que coinciden con más palabras de lo escrito; entre ellas, el título pesa más que la explicación."""
        palabras = palabras_de(consulta)
        if not palabras:
            return []
        puntuadas = []
        for tarea in self._tareas_visibles():
            halladas, puntos = puntaje(tarea, palabras)
            if halladas:
                puntuadas.append((halladas, puntos, tarea))
        if not puntuadas:
            return []
        # Si alguna tarea coincide con todas (o con más) de las palabras, las que coinciden con menos son ruido:
        # «declaración de renta» no debe traer «rentabilidad».
        mejor = max(halladas for halladas, _, _ in puntuadas)
        puntuadas = [p for p in puntuadas if p[0] == mejor]
        puntuadas.sort(key=lambda p: (-p[1], p[2]['titulo']))
        return [tarea for _, _, tarea in puntuadas[:max(1, int(limite))]]
