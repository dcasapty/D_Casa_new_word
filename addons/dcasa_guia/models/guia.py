"""La Guía del negocio: «¿Qué necesitas hacer hoy?».

Un catálogo de tareas escrito en palabras sencillas (``data/guia.json``). Cada tarea dice qué quiere hacer la persona
y qué logra al llegar a la pantalla, y lleva un atajo hasta ella. Quien administra un negocio muchas veces no sabe que
existe una pantalla (la declaración de renta, el cierre de mes, una nota de crédito): aquí la ve, la entiende y llega.

* Una tarea solo se muestra si la persona puede abrir su pantalla (los mismos permisos que el menú de la izquierda):
  una vendedora no ve contabilidad, Gerencia sí. Si la tarea trae ``grupos``, además hace falta tener alguno.
* Nada se inventa: donde hay una fecha límite de impuestos, la nota manda a confirmarla con el contador.
* La misma fuente alimenta la pantalla, la herramienta ``buscar_en_guia`` de Brian y las pruebas (cada atajo debe
  existir; si un módulo cambia un menú, la prueba lo dice).
* «Llévame ahí» lleva a la pantalla justa en un clic y, sin que la persona lo note, anota que lo usó
  (``registrar_uso``, modelo ``dcasa.guia.uso``): de ahí sale «Lo que tú más usas». Además, la lista curada por
  puesto (``data/guia_roles.json``) sale como «En tu puesto lo que más se usa».
"""
import json
import logging
import os
import unicodedata
from functools import lru_cache

from odoo import api, models

_logger = logging.getLogger(__name__)

CARPETA_DATOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
RUTA_CATALOGO = os.path.join(CARPETA_DATOS, 'guia.json')
RUTA_ROLES = os.path.join(CARPETA_DATOS, 'guia_roles.json')

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


@lru_cache(maxsize=1)
def cargar_roles(ruta=RUTA_ROLES):
    """Lo curado por puesto (``data/guia_roles.json``) y cuándo hay datos suficientes de «Lo que tú más usas»."""
    with open(ruta, encoding='utf-8') as archivo:
        return json.load(archivo)


def buscar_tarea(tarea_id):
    """La tarea del catálogo con ese id, o ``None`` (sin importar qué le llegue: nunca falla)."""
    if not isinstance(tarea_id, str):
        return None
    return next((t for t in cargar_catalogo()['tareas'] if t['id'] == tarea_id), None)


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
    def _tiene_algun_grupo(self, grupos):
        """``grupos`` (opcional en una tarea): la tarea sale solo a quien tiene alguno. Sirve cuando la pantalla la
        abren todos pero lo que la tarea explica no (el bloque «Comparar» del Inicio es solo de Gerencia)."""
        usuario = self.env.user
        for grupo in grupos or ():
            try:
                if usuario.has_group(grupo):
                    return True
            except (ValueError, KeyError):      # el grupo no existe en esta instalación: no cuenta
                continue
        return not grupos

    @api.model
    def _tarea_para_mostrar(self, tarea, visibles):
        """La tarea lista para la pantalla, o ``None`` si la persona no puede abrir su destino (o no tiene ninguno de
        sus ``grupos``)."""
        if not self._tiene_algun_grupo(tarea.get('grupos')):
            return None
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
        """Todo lo que la pantalla necesita: categorías con sus tareas (las que quien mira puede abrir), las que
        conviene mostrar primero, lo que más se usa en su puesto y lo que ella o él más usa. Las categorías sin tareas
        para esta persona no salen."""
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
        rol = self._rol_de_quien_mira()
        return {
            'categorias': categorias,
            'empezar': [por_id[i] for i in catalogo.get('empezar', []) if i in por_id],
            'rol': {'clave': rol['clave'], 'titulo': rol.get('titulo') or ''},
            # Lo curado para su puesto: solo lo que puede abrir, en el orden del archivo.
            'puesto': [por_id[i] for i in rol['tareas'] if i in por_id],
            # Lo que ella o él más usa (vacío mientras no haya datos suficientes).
            'mas_usadas': self._mas_usadas(por_id),
            'total': len(tareas),
        }

    # ------------------------------------------------------------------
    # Lo más usado: según el puesto (curado) y según cada persona (real)
    # ------------------------------------------------------------------

    @api.model
    def _rol_de_quien_mira(self):
        """El puesto de quien mira: el primero de ``guia_roles.json`` al que pertenece alguno de sus grupos
        (Gerencia va antes que Contabilidad y que Vendedora); si no es de ninguno, la lista por defecto."""
        roles = cargar_roles()
        usuario = self.env.user
        for rol in roles['roles']:
            for grupo in rol['grupos']:
                try:
                    if usuario.has_group(grupo):
                        return rol
                except (ValueError, KeyError):  # el grupo no existe en esta instalación: no cuenta
                    continue
        return roles['porDefecto']

    @api.model
    def _mas_usadas(self, por_id):
        """«Lo que tú más usas»: las tareas con más «Llévame ahí» de esta persona, solo si hay datos suficientes (por
        ejemplo, 3 tareas con 2 usos o más). Cuenta solo lo que todavía puede abrir. Si algo falla, no hay lista:
        nunca estorba a la pantalla."""
        reglas = cargar_roles()['masUsadas']
        Uso = self.env['dcasa.guia.uso']
        try:
            if not Uso.has_access('read'):
                return []
            filas = Uso.search_read([('veces', '>=', reglas['minimoVeces'])], ['tarea', 'veces'],
                                    order='veces desc, ultima_vez desc, id')
        except Exception:
            _logger.warning('Guía: no se pudo leer lo que más usa la persona', exc_info=True)
            return []
        usadas = [{**por_id[fila['tarea']], 'veces': fila['veces']} for fila in filas if fila['tarea'] in por_id]
        if len(usadas) < reglas['minimoTareas']:
            return []
        return usadas[:reglas['maximo']]

    @api.model
    def registrar_uso(self, tarea_id):
        """Anota que quien llama usó «Llévame ahí» en esa tarea (+1 y la hora). La pantalla lo llama sin esperar
        respuesta: **nunca falla** (un id raro, una tarea que no existe, una que la persona no puede abrir o un error
        de la base devuelven ``False`` y quedan en el log) para no estorbar al «Llévame ahí».

        Cada quien anota solo lo suyo (``user_id`` siempre es quien llama; además lo exige una regla de registro) y
        solo de tareas que existen y que puede abrir. No lleva nada de clientes ni de documentos.
        """
        try:
            tarea = buscar_tarea(tarea_id)
            if not tarea or not self._tarea_para_mostrar(tarea, self._menus_visibles()):
                return False
            # Un savepoint: si la base protesta (p. ej. dos pestañas a la vez), solo se pierde este +1.
            with self.env.cr.savepoint():
                self.env['dcasa.guia.uso']._sumar(tarea['id'])
            return True
        except Exception:
            _logger.warning('Guía: no se pudo anotar el uso de %r', tarea_id, exc_info=True)
            return False

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
