"""El buscador de lugares para cotizar un envío (puerto fiel del HTML de la propuesta, 2026-11-04).

Se escribe como lo dice el cliente: sin tildes, con abreviaturas («urb.», «res.», «bda.»), con una frase («cuánto
cuesta mandar a Villa Lucre»), con errores de dedo, con el nombre todo junto («sanmiguelito») o con un lugar conocido
(«cerca del hospital de Chorrera»).

Cómo puntúa cada lugar (igual que el HTML):

* Cada palabra buscada se compara con las palabras conocidas (``calidades``): igual (1), empieza igual (0.8), con una
  o dos letras de diferencia (Damerau-Levenshtein: 0.7, 0.5 o 0.4 según el largo) o casi igual en palabras largas
  (0.5).
* Pesa más si calza con el **nombre** o sus otros nombres (× 3), luego con el **tipo de lugar** y sus sinónimos
  («mall», «hospital», «super»: × 2.2) y al final con la **zona** (corregimiento, distrito, provincia: × 1.2).
* Las palabras genéricas («urbanización», «residencial», «PH», «torre») suman si están, pero no hacen falta.
* Con 3 palabras o más se perdona una que no calce; con menos, tienen que calzar todas. Solo la zona no basta, salvo
  que se busque un distrito o una provincia («chorrera», «colón»): entonces salen primero sus corregimientos.
* Extras: la frase entera igual al nombre (+8), al principio (+4) o adentro (+2); el tipo (corregimiento +1, barrio
  +0.6, edificio +0.2); un lugar agregado a mano (+0.5); y un poco menos para los nombres largos.
* Empates: primero el más cercano a la tienda.

Cuando no encuentra nada, ``sugerir`` propone hasta 6 nombres parecidos por trigramas («¿Quisiste decir…?»).

El índice se arma una vez y se reusa: buscar no recorre los 11 000 lugares, solo los que comparten alguna palabra (y,
para los nombres escritos juntos, compara el texto pegado). El resultado es el mismo que recorrerlos todos.
"""
import bisect
import re
import unicodedata

RE_NO_ALFANUMERICO = re.compile(r'[^a-z0-9ñ]+')

ABREV = {
    'urb': 'urbanizacion', 'urbanizac': 'urbanizacion', 'res': 'residencial', 'resid': 'residencial',
    'bda': 'barriada', 'barr': 'barriada', 'cond': 'condominio', 'sta': 'santa', 'sto': 'santo', 'sn': 'san',
    'pto': 'puerto', 'gral': 'general', 'dr': 'doctor', 'av': 'avenida', 'ave': 'avenida', 'avda': 'avenida',
    'pque': 'parque', 'esc': 'escuela', 'col': 'colegio', 'hosp': 'hospital', 'univ': 'universidad',
    'edif': 'edificio', 'ed': 'edificio', 'nvo': 'nuevo', 'nva': 'nueva', 'stgo': 'santiago', 'igl': 'iglesia',
    'super': 'supermercado', 'mini': 'minisuper', 'poli': 'policlinica', 'cc': 'centro comercial',
    'u': 'universidad', 'sanmiguelito': 'san miguelito', 'sanmi': 'san miguelito', 'pma': 'panama',
    'pty': 'panama', 'chorr': 'chorrera', 'vla': 'villa',
}

# Palabras que el cliente usa alrededor del lugar y que no ayudan a encontrarlo.
VACIAS = frozenset((
    'a al la el los las lo de del en para por y o con mi mis su sus me que cual cuanto cuantos cuesta cuestan costo '
    'costaria precio precios sale saldria cobran cobra cobrarian envio envios enviar envian mandar mandan llevar '
    'llevan entrega entregar entregan delivery flete transporte traslado hasta desde vivo vive viven queda quedo '
    'ubicado ubicada ubicacion direccion casa sector area zona cerca cercano cercana frente lado detras atras '
    'diagonal entrada despues antes pasando favor porfa hola buenas buenos dias tardes noches quiero necesito seria '
    'es son esta estan hay tienen hacen un una unos unas por favor gracias alla aqui ahi donde mas menos').split(' '))

# Qué palabras traen cada tipo de lugar conocido («mall» trae los centros comerciales).
CAT_SIN = {
    'centro comercial': 'mall centro comercial plaza', 'supermercado': 'supermercado super',
    'minisúper': 'minisuper abarroteria tienda chino', 'ferretería': 'ferreteria materiales',
    'mueblería': 'muebleria muebles', 'tienda por departamentos': 'tienda almacen',
    'hospital': 'hospital policlinica css seguro social salud urgencias',
    'clínica o centro de salud': 'clinica centro salud minsa policentro consultorio', 'universidad': 'universidad',
    'instituto': 'instituto', 'escuela o colegio': 'escuela colegio instituto liceo kinder school',
    'mercado': 'mercado', 'terminal de buses': 'terminal piquera buses bus', 'muelle': 'muelle',
    'policía': 'policia subestacion', 'bomberos': 'bomberos',
    'junta comunal o municipio': 'junta comunal municipio alcaldia representante',
    'iglesia': 'iglesia parroquia capilla templo catedral', 'casa comunal': 'casa comunal',
    'aeropuerto': 'aeropuerto', 'estación de metro o tren': 'metro estacion tren', 'estadio': 'estadio',
    'parque': 'parque', 'cancha o centro deportivo': 'cancha deportivo gimnasio', 'hotel': 'hotel', 'museo': 'museo',
    'banco': 'banco', 'farmacia': 'farmacia', 'gasolinera': 'gasolinera bomba gasolina combustible',
    'restaurante': 'restaurante fonda', 'comida rápida': 'comida rapida',
    'edificio o PH': 'edificio ph torre apartamento apartamentos condominio',
    'barrio o urbanización': 'barrio urbanizacion residencial barriada', 'corregimiento': 'corregimiento',
}
DIST_SIN = {'Panamá': 'ciudad capital', 'San Miguelito': 'san miguelito sanmiguelito', 'La Chorrera': 'chorrera',
            'Arraiján': 'arraijan'}
PROV_SIN = {'Panamá Oeste': 'oeste'}

# Palabras que dicen qué clase de lugar es, no cuál: suman si están en el nombre, pero no hacen falta.
GENERICAS = frozenset(['residencial', 'urbanizacion', 'barriada', 'barrio', 'condominio', 'ph', 'edificio', 'torre',
                       'torres', 'sector', 'comunidad', 'conjunto', 'proyecto', 'calle', 'avenida', 'via'])
PRIORIDAD = {'corregimiento': 1, 'barrio': 0.6, 'edificio': 0.2, 'referencia': 0}
TIPOS = ('corregimiento', 'barrio', 'edificio', 'referencia')
MAX_SUGERENCIAS = 6


def sin_tildes(texto):
    """Minúsculas y sin tildes (la «ñ» también queda como «n», igual que en el HTML)."""
    texto = unicodedata.normalize('NFD', str(texto or ''))
    return ''.join(c for c in texto if not '̀' <= c <= 'ͯ').lower()


def tokens(texto):
    """Las palabras que sirven para buscar: sin tildes, abreviaturas expandidas y sin las palabras vacías."""
    salida = []
    for escrita in RE_NO_ALFANUMERICO.sub(' ', sin_tildes(texto)).split(' '):
        if not escrita:
            continue
        palabra = ABREV.get(escrita) or escrita
        if (len(palabra) == 1 and 'a' <= palabra <= 'z') or palabra in ('nro', 'num', 'numero'):
            continue          # «Nº 2», «No. 2», «Torre A»
        salida.extend(p for p in palabra.split(' ') if p and p not in VACIAS)
    return salida


def largo_js(texto):
    """``texto.length`` de JavaScript (cuenta en UTF-16: un emoji vale 2)."""
    return len(texto.encode('utf-16-le')) // 2


def distancia(a, b, tope):
    """Damerau-Levenshtein (alineación óptima) con corte temprano: ``tope + 1`` si ya pasó el tope."""
    if abs(len(a) - len(b)) > tope:
        return tope + 1
    m, n = len(a), len(b)
    anterior2 = None
    anterior = list(range(n + 1))
    for i in range(1, m + 1):
        actual = [i]
        minimo = i
        ai = a[i - 1]
        for j in range(1, n + 1):
            costo = 0 if ai == b[j - 1] else 1
            v = min(anterior[j] + 1, actual[j - 1] + 1, anterior[j - 1] + costo)
            if anterior2 is not None and i > 1 and j > 1 and ai == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, anterior2[j - 2] + 1)
            actual.append(v)
            minimo = min(minimo, v)
        if minimo > tope:
            return tope + 1
        anterior2, anterior = anterior, actual
    return anterior[n]


def trigramas(texto):
    return {texto[i:i + 3] for i in range(len(texto) - 2)}


def calidad(q, t, tope):
    """Qué tan bien calza la palabra buscada ``q`` con la palabra conocida ``t``: 1 igual, 0.8 empieza igual, 0.7 /
    0.5 / 0.4 con una o dos letras de diferencia, 0.5 casi igual en palabras largas, 0 nada."""
    largo = len(q)
    v = 0
    if t == q:
        v = 1
    elif largo >= 3 and t.startswith(q):
        v = 0.8
    elif tope and len(t) >= 3:
        d = distancia(q, t, tope)
        if d <= tope:
            v = (0.7 if largo >= 5 else 0.4) if d == 1 else 0.5
    if not v and largo >= 5 and len(t) >= 5 and (t.startswith(q[:-1]) or q.startswith(t)):
        v = 0.5
    return v


class _Entrada:
    __slots__ = ('lugar', 'n', 'c', 'z', 'llanos', 'juntos', 'tri', 'clave_sugerencia', 'largo_nombre')


class Indice:
    """El índice de búsqueda de una lista de lugares (diccionarios con la forma del HTML: ``nombre``, ``tipo``,
    ``cat``, ``corr``, ``dist``, ``prov``, ``alias``, ``km``…; ``agregado`` = agregado a mano).

    El orden de la lista importa: a igual puntaje y distancia, sale primero el que va antes (como en el HTML)."""

    def __init__(self, lugares):
        self.lugares = list(lugares)
        self._vocab = {}
        self._entradas = []
        self._por_palabra = {}       # id de palabra → posiciones de los lugares que la tienen (nombre, tipo o zona)
        self._por_trigrama = {}      # trigrama del nombre → posiciones (para «¿Quisiste decir…?»)
        self._cache_calidades = {}
        self._ids_por_texto = {}
        for posicion, lugar in enumerate(self.lugares):
            self._entradas.append(self._indexar(posicion, lugar))
        self._palabras = list(self._vocab)                     # id → palabra
        self._ordenadas = sorted(self._vocab)                  # para buscar por prefijo
        self._por_largo = {}
        for palabra, ident in self._vocab.items():
            self._por_largo.setdefault(len(palabra), []).append((palabra, ident))

    def __len__(self):
        return len(self.lugares)

    def _id(self, palabra):
        ident = self._vocab.get(palabra)
        if ident is None:
            ident = self._vocab[palabra] = len(self._vocab)
        return ident

    def _ids_de(self, texto):
        """Los ids de las palabras de un texto que se repite mucho (el tipo de lugar, la zona), una vez cada texto."""
        guardado = self._ids_por_texto.get(texto)
        if guardado is None:
            guardado = self._ids_por_texto[texto] = tuple(dict.fromkeys(self._id(p) for p in tokens(texto)))
        return guardado

    def _indexar(self, posicion, lugar):
        e = _Entrada()
        e.lugar = lugar
        nombres = [lugar.get('nombre') or ''] + list(lugar.get('alias') or [])
        palabras_de_nombres = [tokens(nombre) for nombre in nombres]
        n = {}
        for palabras in palabras_de_nombres:
            for palabra in palabras:
                n[self._id(palabra)] = True
        cat = lugar.get('cat') or ''
        dist, prov = lugar.get('dist') or '', lugar.get('prov') or ''
        zona = f"{lugar.get('corr') or ''} {dist} {prov} {DIST_SIN.get(dist) or ''} {PROV_SIN.get(prov) or ''}"
        e.n = tuple(n)
        e.c = self._ids_de((CAT_SIN.get(cat) or '') + ' ' + cat)
        e.z = self._ids_de(zona)
        e.llanos = tuple(' '.join(palabras) for palabras in palabras_de_nombres)
        e.juntos = tuple(llano.replace(' ', '') for llano in e.llanos)
        for ident in {*e.n, *e.c, *e.z}:
            self._por_palabra.setdefault(ident, []).append(posicion)
        pegado = RE_NO_ALFANUMERICO.sub('', sin_tildes(lugar.get('nombre') or ''))
        e.tri = frozenset(trigramas(pegado))
        for tri in e.tri:
            self._por_trigrama.setdefault(tri, []).append(posicion)
        e.clave_sugerencia = sin_tildes(lugar.get('nombre') or '')
        e.largo_nombre = largo_js(lugar.get('nombre') or '')
        return e

    # --- Palabras parecidas ------------------------------------------------------------------------------------------
    def _con_prefijo(self, prefijo):
        inicio = bisect.bisect_left(self._ordenadas, prefijo)
        for palabra in self._ordenadas[inicio:]:
            if not palabra.startswith(prefijo):
                break
            yield palabra

    def _candidatas(self, q, tope):
        """Las palabras conocidas que PUEDEN calzar con ``q`` (las demás darían 0): igual, con su prefijo, de largo
        parecido (hasta ``tope`` letras de diferencia) o, en palabras largas, casi iguales."""
        largo = len(q)
        candidatas = {q} if q in self._vocab else set()
        if largo >= 3:
            candidatas.update(self._con_prefijo(q))
        if tope:
            for medida in range(max(3, largo - tope), largo + tope + 1):
                candidatas.update(p for p, _ in self._por_largo.get(medida, ()))
        if largo >= 5:
            candidatas.update(p for p in self._con_prefijo(q[:-1]) if len(p) >= 5)
            candidatas.update(q[:k] for k in range(5, largo + 1) if q[:k] in self._vocab)
        return candidatas

    def calidades(self, q):
        """Qué tan bien calza la palabra buscada con cada palabra conocida: ``{id: calidad}`` (como el HTML, que las
        recorría todas; aquí solo se miran las que pueden calzar)."""
        guardado = self._cache_calidades.get(q)
        if guardado is not None:
            return guardado
        tope = 2 if len(q) >= 8 else 1 if len(q) >= 4 else 0
        salida = {}
        for t in self._candidatas(q, tope):
            v = calidad(q, t, tope)
            if v:
                salida[self._vocab[t]] = v
        if len(self._cache_calidades) > 4000:
            self._cache_calidades.clear()
        self._cache_calidades[q] = salida
        return salida

    # --- Buscar ------------------------------------------------------------------------------------------------------
    def buscar(self, texto, tipo=None, distrito=None):
        """Las posiciones de los lugares que calzan, del más parecido al menos parecido.

        ``tipo``: solo corregimientos, barrios, edificios o lugares conocidos. ``distrito``: un distrito o una
        provincia."""
        consulta = self._preparar(texto)
        if consulta is None:
            return []
        resultados = []
        for posicion in sorted(self._candidatos(consulta)):
            e = self._entradas[posicion]
            lugar = e.lugar
            if tipo and lugar.get('tipo') != tipo:
                continue
            if distrito and lugar.get('dist') != distrito and lugar.get('prov') != distrito:
                continue
            puntaje = self._puntuar(e, consulta)
            if puntaje is not None:
                km = lugar.get('km')
                resultados.append((-puntaje, 999 if km is None else km, posicion))
        resultados.sort(key=lambda r: (r[0], r[1]))      # estable: a igual puntaje y km, el orden de la lista
        return [r[2] for r in resultados]

    def _preparar(self, texto):
        """Las palabras buscadas (sin repetir), separadas en las que dicen cuál lugar y las genéricas, con sus
        calidades; ``None`` si no queda ninguna."""
        todas = list(dict.fromkeys(tokens(texto)))
        if not todas:
            return None
        qs = [t for t in todas if t not in GENERICAS]
        gen = [t for t in todas if t in GENERICAS]
        if not qs:
            qs, gen = gen, []
        return {'cal': [self.calidades(t) for t in qs], 'cal_gen': [self.calidades(t) for t in gen],
                'frase': ' '.join(qs), 'junto': ''.join(qs), 'cuantas': len(qs),
                'perdon': 1 if len(qs) >= 3 else 0}

    def _candidatos(self, consulta):
        """Los lugares que comparten alguna palabra buscada, más los que tienen el texto pegado en su nombre. Los demás
        no pueden calzar: recorrerlos todos (como el HTML) daría lo mismo."""
        candidatos = set()
        for calidades in consulta['cal']:
            for ident in calidades:
                candidatos.update(self._por_palabra.get(ident, ()))
        junto = consulta['junto']
        if len(junto) >= 5:
            candidatos.update(i for i, e in enumerate(self._entradas) if any(junto in x for x in e.juntos))
        return candidatos

    @staticmethod
    def _mejor_calce(e, calidades):
        """Dónde calza mejor una palabra buscada en el lugar: ``(puntos, 'n' nombre | 'c' tipo | 'z' zona | '')``."""
        mejor, donde = 0, ''
        for ids, peso, lugar_del_calce in ((e.n, 3, 'n'), (e.c, 2.2, 'c'), (e.z, 1.2, 'z')):
            for i in ids:
                v = calidades.get(i)
                if v and v * peso > mejor:
                    mejor, donde = v * peso, lugar_del_calce
        return mejor, donde

    def _puntuar(self, e, consulta):
        """El puntaje del lugar para esta búsqueda (igual que el HTML), o ``None`` si no calza."""
        puntos, faltan, en_nombre, en_cat, solo_zona = 0, 0, 0, 0, 0
        for calidades in consulta['cal']:
            mejor, donde = self._mejor_calce(e, calidades)
            if not mejor:
                faltan += 1
                continue
            puntos += mejor
            if donde == 'n':
                en_nombre += 1
            elif donde == 'c':
                en_cat += 1
            elif any((calidades.get(i) or 0) >= 0.7 for i in e.z):
                solo_zona += 1
        # «urb.», «ph», «torre»: si el nombre o el tipo de lugar lo dicen, suma un poco
        for calidades in consulta['cal_gen']:
            puntos += max([0] + [calidades.get(i) or 0 for i in e.n] + [calidades.get(i) or 0 for i in e.c])
        # un nombre escrito todo junto o separado distinto («sanmiguelito», «villa lucre») también vale
        junto = consulta['junto']
        if len(junto) >= 5 and any(junto in x for x in e.juntos):
            faltan = 0
            en_nombre = max(en_nombre, 1)
            puntos = max(puntos, consulta['cuantas'] * 2.5)
        if faltan > consulta['perdon']:
            return None
        # buscar un distrito o una provincia («chorrera», «colón») trae primero sus corregimientos
        de_la_zona = e.lugar.get('tipo') == 'corregimiento' and solo_zona == consulta['cuantas']
        # fuera de eso, tiene que calzar algo del nombre o del tipo de lugar: solo la zona no basta
        if not en_nombre and not en_cat and not de_la_zona:
            return None
        return puntos - faltan * 2 + self._extra(e, consulta['frase'], de_la_zona) - (
            0 if de_la_zona else e.largo_nombre * 0.01)

    @staticmethod
    def _extra(e, frase, de_la_zona):
        """La frase entera en el nombre, el tipo de lugar, la zona buscada y lo agregado a mano."""
        extra = PRIORIDAD.get(e.lugar.get('tipo')) or 0
        if any(x == frase for x in e.llanos):
            extra += 8
        elif any(x.startswith(frase) for x in e.llanos):
            extra += 4
        elif any(frase in x for x in e.llanos):
            extra += 2
        if de_la_zona:
            extra += 5
        if e.lugar.get('agregado'):
            extra += 0.5
        return extra

    def sugerir(self, texto):
        """«¿Quisiste decir…?»: hasta 6 posiciones de nombres parecidos por trigramas (sin repetir el nombre)."""
        q = RE_NO_ALFANUMERICO.sub('', sin_tildes(texto))
        if len(q) < 3:
            return []
        tq = trigramas(q)
        comunes = {}
        for tri in tq:
            for posicion in self._por_trigrama.get(tri, ()):
                comunes[posicion] = comunes.get(posicion, 0) + 1
        puntajes = []
        for posicion in sorted(comunes):
            comun = comunes[posicion]
            parecido = comun / max(1, len(tq) + len(self._entradas[posicion].tri) - comun)
            if parecido > 0.2:
                puntajes.append((-parecido, posicion))
        puntajes.sort(key=lambda p: p[0])
        vistos, salida = set(), []
        for _, posicion in puntajes:
            clave = self._entradas[posicion].clave_sugerencia
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append(posicion)
            if len(salida) == MAX_SUGERENCIAS:
                break
        return salida
