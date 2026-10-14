"""Los ajustes que Gerencia hace desde Ajustes › Programa de vendedores: una capa ENCIMA de ``puntos.json``.

Todo lo de aquí es PURO (igual que ``reglas.py`` y ``reglas_vendedores.py``): entra un diccionario de reglas y salen
números y textos; no toca la base ni lee la hora. Por eso se prueba entero.

Cómo encajan las piezas:

* ``puntos.json`` sigue siendo la fuente de los VALORES DE FÁBRICA. Nunca se edita desde la pantalla.
* Cada vez que Gerencia guarda un cambio nace una versión (``dcasa.vend.reglas``) con fecha-hora de vigencia. Una
  versión guarda solo los AJUSTES (``ruta → valor``) que difieren de la fábrica, acumulados: la última versión vigente
  dice todo lo que está cambiado. Si no hay versión, rige ``puntos.json`` tal cual.
* ``reglas_efectivas(base, versiones, ahora)`` junta fábrica + ajustes. Los cambios solo rigen hacia adelante: lo
  ya acreditado nunca se recalcula (las comisiones guardan lo que pagaron y el libro es inmutable).
* Solo se pueden ajustar las cifras de ``CAMPOS`` y la escalera. Los interruptores legales (canje de externos y en
  efectivo), el diseño antifraude y los supuestos de costo NO están en la lista: aunque una fila de la base trajera
  esas rutas, ``ajustes_validos`` las descarta al leerlas.

Los valores de la pantalla van en palabras sencillas (dólares, porcentajes, días) y aquí se convierten a lo que usa el
programa (centavos, puntos, fracciones) y de vuelta. Los límites duros de cada cifra están en ``CAMPOS`` y en
``problemas_de_las_cifras`` (documentados en ``docs/VENDEDORES.md``, «Ajustar las cifras desde Ajustes»).
"""

import copy
import math
from dataclasses import dataclass
from fractions import Fraction

from . import reglas_vendedores as RV
from .reglas import FaltaConfigurar

MAX_ESCALONES = 5

# Topes de sentido común contra errores de dedo (un cero de más). No son decisiones de negocio: la economía vive en
# ``puntos.json``. Los límites que SÍ son de negocio salen de las propias cifras del programa (el techo por venta, el
# margen supuesto, la comisión base).
MAX_DOLARES_CHICOS = 1000          # venta mínima, canje mínimo
MAX_DOLARES_TOPE = 10000           # tope de puntos que se puede ganar en un mes
MAX_DOLARES_UMBRAL = 1000000       # lo que hay que vender para subir de escalón
MAX_DIRECTOS = 5                   # «3 en la fase 1; sube a 5 en la fase 2, máximo absoluto» (puntos.json)

TIPOS = ('si_no', 'porcentaje', 'fraccion', 'dolares', 'puntos_en_dolares', 'entero', 'veces')


@dataclass(frozen=True)
class Campo:
    """Una cifra que Gerencia puede ajustar: dónde vive en ``puntos.json`` y cómo se ve en la pantalla."""

    clave: str                       # el campo de Odoo es ``dcasa_vend_<clave>``
    ruta: tuple                      # camino dentro de la sección «vendedores»
    tipo: str                        # ver TIPOS
    etiqueta: str
    ayuda: str = ''
    minimo: float = 0                # en las unidades de la pantalla
    maximo: float | None = None
    positivo: bool = False           # tiene que ser mayor que cero
    unidad: str = ''                 # texto después de un entero: ' días', ' meses'…
    cero_es_vacio: bool = False      # 0 en pantalla = ``null`` en puntos.json («sin tope»)
    obligatorio: bool = True         # ``null`` en puntos.json no es «sin tope»: es una cifra que falta
    textos: tuple = ('Sí', 'No')     # cómo se dice un sí/no

    @property
    def ruta_texto(self):
        return '.'.join(self.ruta)

    @property
    def campo_odoo(self):
        return f'dcasa_vend_{self.clave}'


CAMPOS = (
    # --- Programa -------------------------------------------------------------------------------------------------
    Campo('programa', ('programaActivo',), 'si_no', 'El programa de vendedores está encendido',
          'Si lo apagas no se acredita nada nuevo y las ventas siguen igual. Lo que los vendedores ya ganaron no se '
          'toca.', textos=('Encendido', 'Apagado')),
    # --- Comisión y escalera --------------------------------------------------------------------------------------
    Campo('comision_base', ('comision', 'puntosPorDolarNeto'), 'porcentaje', 'Comisión base (% de la venta neta)',
          'Lo que gana el vendedor por cada dólar vendido (sin ITBMS y con los descuentos ya aplicados) mientras '
          'todavía no ha subido de escalón.', positivo=True, maximo=100),
    Campo('compra_minima', ('comision', 'compraMinimaCentavos'), 'dolares', 'Venta mínima que da comisión',
          'Una venta de menos que esto se registra, pero no da comisión.', maximo=MAX_DOLARES_CHICOS),
    Campo('recompra', ('comision', 'factorDeRecompra'), 'fraccion',
          'Recompra de su cliente: paga este % de la comisión',
          'Cuando un cliente ligado a un vendedor vuelve a comprar sin decir el código, el vendedor gana esta parte '
          'de la comisión. 100 % es la comisión completa.', maximo=100, obligatorio=False),
    Campo('existente', ('comision', 'factorClienteExistente'), 'fraccion',
          'Cliente que ya compraba: paga este % de la comisión',
          'Cuando alguien que ya había comprado en D’CASA compra con un código, el vendedor gana esta parte de la '
          'comisión. 100 % es la comisión completa.', maximo=100, obligatorio=False),
    Campo('dias_escalon', ('comision', 'diasParaEscalon'), 'entero', 'Días que se miran para el escalón',
          'La escalera mira lo que el vendedor vendió en estos últimos días para decidir en qué escalón está.',
          minimo=1, maximo=365, unidad=' días'),
    Campo('vinculo_meses', ('vinculacion', 'meses'), 'entero', 'Meses que el cliente queda ligado a su vendedor',
          'Sus compras de ese tiempo cuentan para el vendedor aunque no diga el código. 0 = el cliente no se liga. '
          'Un cambio vale para los clientes que se liguen desde que lo guardas; los que ya estaban ligados conservan '
          'el plazo con que se ligaron.', maximo=60, unidad=' meses'),
    # --- Patrocinio -----------------------------------------------------------------------------------------------
    Campo('patrocinio', ('patrocinio', 'puntosPorDolarNetoDelDirecto'), 'porcentaje',
          'Patrocinio (% de la venta del vendedor directo)',
          'Lo que gana quien patrocinó al vendedor, por cada dólar que vende su directo (un solo nivel). No le resta '
          'nada al directo y no puede ser más que la comisión base.', maximo=100),
    Campo('directos', ('patrocinio', 'topeDeDirectos'), 'entero', 'Vendedores que puede patrocinar cada persona',
          'Cuántos vendedores directos puede tener, como máximo, cada patrocinador.', minimo=1,
          maximo=MAX_DIRECTOS, unidad=' vendedores'),
    Campo('ventas_propias', ('patrocinio', 'ventasPropiasMinimasAlMes'), 'entero',
          'Clientes que el patrocinador tiene que atender en el mes',
          'Para cobrar patrocinio en un mes, el patrocinador tiene que haberle vendido él mismo a esta cantidad de '
          'clientes distintos. 0 = no se pide.', maximo=100, obligatorio=False, unidad=' clientes'),
    Campo('patrocinio_multiplo', ('patrocinio', 'topeComoMultiploDeSuComisionDelMes'), 'veces',
          'Tope del patrocinio del mes, en veces su comisión propia',
          'El patrocinio de un mes no puede pasar de esta cantidad de veces lo que el patrocinador ganó ese mes por '
          'sus propias ventas: nadie vive solo de su colmena.', maximo=10, obligatorio=False),
    Campo('patrocinio_tope', ('techos', 'patrocinioPorPatrocinadorAlMesPuntos'), 'puntos_en_dolares',
          'Tope de patrocinio al mes por patrocinador',
          'Lo máximo que un patrocinador puede ganar por patrocinio en un mes. 0 = sin este tope (rige el de arriba).',
          maximo=MAX_DOLARES_TOPE, cero_es_vacio=True, obligatorio=False),
    # --- Retención ------------------------------------------------------------------------------------------------
    Campo('retencion_dias', ('retencion', 'dias'), 'entero', 'Días de espera antes de poder canjear',
          'Los puntos de una venta se ven desde el primer día, pero no se pueden canjear hasta que pasen estos días '
          '(la ventana de devoluciones).', maximo=365, unidad=' días'),
    Campo('primeras_ventas', ('retencion', 'primerasVentas'), 'entero', 'Primeras ventas que esperan más',
          'Las primeras ventas de un vendedor nuevo esperan más días. Aquí dices cuántas son. 0 = ninguna.',
          maximo=100, obligatorio=False, unidad=' ventas'),
    Campo('primeras_dias', ('retencion', 'diasPrimerasVentas'), 'entero', 'Días de espera de esas primeras ventas',
          'No puede ser menos que la espera normal.', maximo=365, obligatorio=False, unidad=' días'),
    # --- Límites --------------------------------------------------------------------------------------------------
    Campo('techo', ('techos', 'totalPorVentaPorcentajeDelNeto'), 'porcentaje',
          'Techo de costo por venta (% de la venta neta)',
          'Por cada factura, lo que cuestan juntos los puntos del cliente, del vendedor y del patrocinador no puede '
          'pasar de este porcentaje de la venta neta. Si se pasa, se recorta primero el patrocinio y luego la '
          'comisión. Ninguna comisión puede ser mayor que este techo.', positivo=True, maximo=100),
    Campo('freno', ('techos', 'frenoGlobalPorcentajeDeLaVentaNeta'), 'porcentaje',
          'Freno de todo el programa (% de lo vendido en la tienda)',
          'Lo que el programa entrega a todos los vendedores en 30 días no puede pasar de este porcentaje de lo '
          'vendido en toda la tienda en esos días. Es el seguro contra una cifra mal puesta; no puede ser mayor '
          'que el techo por venta.', positivo=True, maximo=100),
    Campo('tope_base', ('techos', 'porVendedorAlMesPuntos'), 'puntos_en_dolares', 'Tope del mes en el escalón base',
          'Lo máximo que un vendedor del escalón base puede ganar al mes entre comisión y patrocinio. Es el freno '
          'de la gente nueva; cada escalón de arriba puede tener el suyo.', positivo=True,
          maximo=MAX_DOLARES_TOPE),
    # --- Canjes ---------------------------------------------------------------------------------------------------
    Campo('canje_minimo', ('canje', 'puntosMinimosParaCanjear'), 'puntos_en_dolares', 'Canje mínimo',
          'Lo menos que vale un premio para poder pedirlo.', maximo=MAX_DOLARES_CHICOS, obligatorio=False),
    Campo('vigencia_horas', ('canje', 'vigenciaDelCodigoHoras'), 'entero', 'Horas que dura el código de un premio',
          'Pasado ese tiempo sin recoger el premio, los puntos vuelven al vendedor.', minimo=1, maximo=720,
          unidad=' horas'),
    Campo('canjes_mes', ('canje', 'canjesPorVendedorAlMes'), 'entero', 'Canjes por vendedor al mes',
          'Cuántos premios puede pedir un vendedor en un mes.', minimo=1, maximo=100, unidad=' canjes'),
)

CAMPOS_POR_CLAVE = {campo.clave: campo for campo in CAMPOS}
CAMPOS_POR_RUTA = {campo.ruta_texto: campo for campo in CAMPOS}
RUTA_ESCALONES = 'comision.escalones'

# Las tres cifras de cada escalón de la escalera, con las mismas unidades que las demás.
_DESDE_DE_ESCALON = Campo('esc_desde', ('desdeVentasNetasCentavos',), 'dolares', 'Desde cuánto vendido')
_TASA_DE_ESCALON = Campo('esc_tasa', ('puntosPorDolarNeto',), 'porcentaje', 'Lo que gana')
_TOPE_DE_ESCALON = Campo('esc_tope', ('topeAlMesPuntos',), 'puntos_en_dolares', 'Tope del mes', maximo=MAX_DOLARES_TOPE)


def claves_de_escalon(numero):
    """Los tres campos de la pantalla de un escalón: desde cuánto vendido, cuánto gana y su tope del mes."""
    return f'esc{numero}_desde', f'esc{numero}_tasa', f'esc{numero}_tope'


CLAVES_DE_ESCALONES = tuple(clave for n in range(1, MAX_ESCALONES + 1) for clave in claves_de_escalon(n))
CLAVES_DE_PANTALLA = tuple(campo.clave for campo in CAMPOS) + CLAVES_DE_ESCALONES
# Los campos de Odoo que la pantalla carga al abrirse: las cifras, los dos interruptores legales (solo se ven) y las
# dos marcas de control (cargó bien; qué versión estaba mirando).
CLAVES_DE_PANTALLA_ODOO = tuple(f'dcasa_vend_{clave}' for clave in CLAVES_DE_PANTALLA) + (
    'dcasa_vend_externos', 'dcasa_vend_efectivo', 'dcasa_vend_cargado', 'dcasa_vend_version_vista')


# ---------------------------------------------------------------------------
# Números y textos
# ---------------------------------------------------------------------------

def _fr(valor):
    """Fracción exacta de un número escrito en el JSON o en la pantalla (sin ruido de coma flotante)."""
    return Fraction(str(valor))


def _redondear(fraccion):
    """Al entero más cercano (mitad hacia arriba)."""
    return math.floor(fraccion + Fraction(1, 2))


def _centesimas(valor):
    """Un número de la pantalla en centésimas enteras, redondeando como los campos de Odoo (mitad hacia arriba)."""
    return _redondear(_fr(float(valor)) * 100)


def _numero(fraccion):
    """Entero si lo es (4 y no 4.0), decimal si no: así el JSON queda limpio y 4 == 4.0 sigue valiendo."""
    fraccion = Fraction(fraccion)
    return int(fraccion) if fraccion.denominator == 1 else float(fraccion)


def _g(valor):
    return f'{float(valor):g}'


_SINGULAR = {' días': ' día', ' meses': ' mes', ' horas': ' hora', ' vendedores': ' vendedor', ' clientes': ' cliente',
             ' ventas': ' venta', ' canjes': ' canje'}


def como_porcentaje(valor):
    return f'{_g(valor)} %'


def como_dolares(valor):
    return f'${float(valor):,.2f}'


def puntos_por_dolar(reglas):
    """Cuántos puntos vale un dólar al canjear (``canje.puntosPorDolar``, que es de Socios y no se ajusta aquí).
    Con él se pasan los topes de puntos a dólares y de vuelta. Sin la cifra, nada se convierte."""
    valor = (reglas.get('canje') or {}).get('puntosPorDolar')
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not valor > 0:
        raise FaltaConfigurar('canje.puntosPorDolar', 'Falta definir en puntos.json cuántos puntos vale un dólar.')
    return valor


def a_pantalla(campo, valor, ppd):
    """De lo que dice ``puntos.json`` a lo que se ve en la pantalla (``ppd``: puntos por dólar)."""
    if campo.tipo == 'si_no':
        return bool(valor)
    if campo.tipo == 'fraccion':
        return 100.0 if valor is None else float(_fr(valor) * 100)
    if valor is None:
        return 0 if campo.tipo == 'entero' else 0.0
    if campo.tipo == 'entero':
        return int(valor)
    if campo.tipo == 'dolares':
        return float(Fraction(int(valor), 100))
    if campo.tipo == 'puntos_en_dolares':
        return float(Fraction(int(valor)) / _fr(ppd))
    return float(valor)


def de_pantalla(campo, valor, ppd):
    """De lo que se escribió en la pantalla a lo que guarda ``puntos.json`` (centavos, puntos, fracciones)."""
    if campo.tipo == 'si_no':
        return bool(valor)
    if campo.cero_es_vacio and not valor:
        return None
    if campo.tipo == 'entero':
        return int(valor)
    exacto = Fraction(_centesimas(valor), 100)
    if campo.tipo in {'porcentaje', 'veces'}:
        return _numero(exacto)
    if campo.tipo == 'fraccion':
        return _numero(exacto / 100)
    if campo.tipo == 'dolares':
        return _redondear(exacto * 100)
    return _redondear(exacto * _fr(ppd))          # puntos_en_dolares


def como_texto(campo, valor):
    """Un valor de pantalla dicho en palabras, para los mensajes y el historial."""
    if campo.tipo == 'si_no':
        return campo.textos[0] if valor else campo.textos[1]
    if campo.cero_es_vacio and not valor:
        return 'sin tope'
    if campo.tipo in ('porcentaje', 'fraccion'):
        return como_porcentaje(valor)
    if campo.tipo in ('dolares', 'puntos_en_dolares'):
        return como_dolares(valor)
    if campo.tipo == 'veces':
        return f'{_g(valor)} vez' if float(valor) == 1 else f'{_g(valor)} veces'
    unidad = _SINGULAR.get(campo.unidad, campo.unidad) if int(valor) == 1 else campo.unidad
    return f'{int(valor)}{unidad}'


# ---------------------------------------------------------------------------
# Rutas dentro de la sección «vendedores»
# ---------------------------------------------------------------------------

def leer(seccion, ruta):
    """El valor en ``ruta`` (tupla o ``'a.b'``) de la sección, o ``None`` si no está."""
    actual = seccion
    for clave in (ruta.split('.') if isinstance(ruta, str) else ruta):
        if not isinstance(actual, dict) or clave not in actual:
            return None
        actual = actual[clave]
    return actual


def _escribir(seccion, ruta, valor):
    claves = ruta.split('.')
    for clave in claves[:-1]:
        seccion = seccion.setdefault(clave, {})
    seccion[claves[-1]] = valor


# ---------------------------------------------------------------------------
# Qué ajustes valen (todo lo demás se descarta)
# ---------------------------------------------------------------------------

def _es_entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _valor_valido(campo, valor):
    if valor is None:
        return campo.cero_es_vacio
    if campo.tipo == 'si_no':
        return isinstance(valor, bool)
    if campo.tipo in ('dolares', 'puntos_en_dolares', 'entero'):
        return _es_entero(valor) and valor >= 0
    return _es_numero(valor) and valor >= 0


def _escalones_validos(valor):
    if not isinstance(valor, list) or len(valor) > MAX_ESCALONES:
        return False
    for escalon in valor:
        if not isinstance(escalon, dict):
            return False
        desde, tasa, tope = (escalon.get('desdeVentasNetasCentavos'), escalon.get('puntosPorDolarNeto'),
                             escalon.get('topeAlMesPuntos'))
        if not (_es_entero(desde) and desde > 0) or not (_es_numero(tasa) and tasa > 0):
            return False
        if tope is not None and not (_es_entero(tope) and tope >= 0):
            return False
    return True


def ajustes_validos(ajustes):
    """Lo que se puede creer de una fila de ajustes: solo rutas de ``CAMPOS`` (y la escalera), con el tipo correcto.
    Una ruta desconocida (p. ej. ``canje.externosHabilitado``), de otro tipo o mal formada se descarta."""
    if not isinstance(ajustes, dict):
        return {}
    validos = {}
    for ruta, valor in ajustes.items():
        campo = CAMPOS_POR_RUTA.get(ruta)
        if campo is not None and _valor_valido(campo, valor):
            validos[ruta] = valor
        elif ruta == RUTA_ESCALONES and _escalones_validos(valor):
            validos[ruta] = [{'desdeVentasNetasCentavos': e['desdeVentasNetasCentavos'],
                              'puntosPorDolarNeto': e['puntosPorDolarNeto'],
                              'topeAlMesPuntos': e.get('topeAlMesPuntos')} for e in valor]
    return validos


# ---------------------------------------------------------------------------
# Las reglas efectivas: fábrica + ajustes vigentes
# ---------------------------------------------------------------------------

def aplicar_ajustes(base, ajustes):
    """Copia de ``base`` con los ajustes puestos. ``base`` no se toca."""
    reglas = copy.deepcopy(base)
    seccion = reglas.get('vendedores')
    if isinstance(seccion, dict):
        for ruta, valor in ajustes_validos(ajustes).items():
            _escribir(seccion, ruta, copy.deepcopy(valor))
    return reglas


def version_vigente(versiones, ahora):
    """La versión que rige en ``ahora``: la de vigencia más reciente que ya empezó (en un empate, la de mayor
    número). ``None`` si todavía no empezó ninguna."""
    ya = [v for v in versiones if v['vigente_desde'] <= ahora]
    return max(ya, key=lambda v: (v['vigente_desde'], v['numero']), default=None)


def reglas_efectivas(base, versiones, ahora):
    """Las reglas con que se paga en ``ahora``.

    ``versiones``: lista de ``{'numero', 'vigente_desde', 'ajustes', ['id'], ['tipo']}`` (``ajustes`` ya como
    diccionario). Sin versión vigente se devuelve ``base`` tal cual (el mismo objeto): rige ``puntos.json``. Con una,
    se devuelve una copia con sus ajustes y la marca ``ajusteVendedores`` (qué versión rige y desde cuándo)."""
    version = version_vigente(versiones, ahora)
    if version is None:
        return base
    reglas = aplicar_ajustes(base, version.get('ajustes') or {})
    reglas['ajusteVendedores'] = {
        'numero': version['numero'], 'id': version.get('id'), 'tipo': version.get('tipo') or 'ajuste',
        'vigenteDesde': version['vigente_desde'].strftime('%Y-%m-%d %H:%M:%S')}
    return reglas


# ---------------------------------------------------------------------------
# De las reglas a la pantalla y de la pantalla a los ajustes
# ---------------------------------------------------------------------------

def _escalones_ordenados(reglas):
    escalones = (RV.seccion(reglas).get('comision') or {}).get('escalones') or []
    return sorted(escalones, key=lambda e: e['desdeVentasNetasCentavos'])


def valores_de_pantalla(reglas):
    """Todo lo que la pantalla muestra, ``{campo: valor}``, a partir de unas reglas (las efectivas)."""
    ppd = puntos_por_dolar(reglas)
    seccion = RV.seccion(reglas)
    pantalla = {campo.clave: a_pantalla(campo, leer(seccion, campo.ruta), ppd) for campo in CAMPOS}
    escalones = _escalones_ordenados(reglas)
    if len(escalones) > MAX_ESCALONES:
        raise FaltaConfigurar(RUTA_ESCALONES, f'La escalera tiene más de {MAX_ESCALONES} escalones: no caben en la '
                                              'pantalla. Se cambia con el programador.')
    for numero in range(1, MAX_ESCALONES + 1):
        desde, tasa, tope = claves_de_escalon(numero)
        escalon = escalones[numero - 1] if numero <= len(escalones) else None
        pantalla[desde] = float(Fraction(escalon['desdeVentasNetasCentavos'], 100)) if escalon else 0.0
        pantalla[tasa] = float(escalon['puntosPorDolarNeto']) if escalon else 0.0
        pantalla[tope] = a_pantalla(_TOPE_DE_ESCALON, escalon.get('topeAlMesPuntos'), ppd) if escalon else 0.0
    return pantalla


def _escalones_de_pantalla(pantalla, ppd):
    """``(lista de escalones para puntos.json, problemas)`` a partir de las filas de la pantalla. Una fila en cero no
    se usa; una a medias es un problema."""
    escalones, problemas = [], []
    for numero in range(1, MAX_ESCALONES + 1):
        clave_desde, clave_tasa, clave_tope = claves_de_escalon(numero)
        desde, tasa, tope = (pantalla.get(clave_desde) or 0, pantalla.get(clave_tasa) or 0,
                             pantalla.get(clave_tope) or 0)
        if not (desde or tasa or tope):
            continue
        if min(desde, tasa, tope) < 0:
            problemas.append(f'Escalón {numero}: ninguna cifra puede ser negativa.')
            continue
        if not (desde > 0 and tasa > 0):
            problemas.append(f'Escalón {numero}: llena cuánto hay que vender y cuánto gana, o deja todo en 0 para '
                             'no usarlo.')
            continue
        escalones.append({
            'desdeVentasNetasCentavos': de_pantalla(_DESDE_DE_ESCALON, desde, ppd),
            'puntosPorDolarNeto': de_pantalla(_TASA_DE_ESCALON, tasa, ppd),
            'topeAlMesPuntos': de_pantalla(_TOPE_DE_ESCALON, tope, ppd) if tope else None})
    return sorted(escalones, key=lambda e: e['desdeVentasNetasCentavos']), problemas


def _normal(escalones):
    return [(e['desdeVentasNetasCentavos'], _fr(e['puntosPorDolarNeto']), e.get('topeAlMesPuntos'))
            for e in (escalones or [])]


def _texto_de_escalon(escalon, ppd):
    if escalon is None:
        return 'sin usar'
    tope = escalon.get('topeAlMesPuntos')
    return (f"desde {como_dolares(Fraction(escalon['desdeVentasNetasCentavos'], 100))} vendidos · gana "
            f"{como_porcentaje(escalon['puntosPorDolarNeto'])} · tope del mes "
            f"{como_dolares(Fraction(tope) / _fr(ppd)) if tope is not None else 'el del escalón base'}")


def _iguales_en_pantalla(campo, actual, en_pantalla, ppd):
    """¿Lo que quedó en la pantalla es lo mismo que ya rige? Se compara como lo ve la persona (a 2 decimales): una
    cifra que el JSON deja en ``null`` y la pantalla muestra en 0, o con más decimales de los que caben, no cuenta
    como un cambio mientras no la toquen."""
    if campo.tipo == 'si_no':
        return bool(actual) == bool(en_pantalla)
    return _centesimas(a_pantalla(campo, actual, ppd)) == _centesimas(en_pantalla or 0)


def _iguales_en_json(a, b):
    if isinstance(a, list) or isinstance(b, list):
        return _normal(a) == _normal(b)
    if a is None or b is None:
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return _fr(a) == _fr(b)


def calcular_cambio(base, actuales, ajustes_actuales, pantalla):
    """Qué cambia lo que quedó en la pantalla, frente a lo que ya rige.

    ``base``: ``puntos.json``. ``actuales``: las reglas efectivas de ahora. ``ajustes_actuales``: los ajustes de la
    versión vigente (``{}`` si no hay). ``pantalla``: ``{campo: valor}``; un campo ausente no se toca.

    Devuelve ``{'ajustes': nuevos ajustes acumulados, 'cambios': [{campo, antes, despues}], 'candidato': las reglas
    con el cambio puesto, 'problemas': lo que impide guardar, 'problemas_de_pantalla': los que vienen de cómo se
    llenó la pantalla (p. ej. un escalón a medias)}``. Un ajuste que queda igual a la fábrica se quita: esa cifra
    vuelve a seguir a ``puntos.json``."""
    ppd = puntos_por_dolar(base)
    seccion_actual, seccion_base = RV.seccion(actuales), RV.seccion(base)
    ajustes = ajustes_validos(ajustes_actuales)
    cambios = []
    for campo in CAMPOS:
        if campo.clave not in pantalla:
            continue
        actual = leer(seccion_actual, campo.ruta)
        if _iguales_en_pantalla(campo, actual, pantalla[campo.clave], ppd):
            continue
        nuevo = de_pantalla(campo, pantalla[campo.clave], ppd)
        ajustes[campo.ruta_texto] = nuevo
        cambios.append({'campo': campo.etiqueta, 'ruta': campo.ruta_texto,
                        'antes': como_texto(campo, a_pantalla(campo, actual, ppd)),
                        'despues': como_texto(campo, a_pantalla(campo, nuevo, ppd))})
    problemas = []
    if any(clave in pantalla for clave in CLAVES_DE_ESCALONES):
        nuevos, problemas = _escalones_de_pantalla(pantalla, ppd)
        antes = _escalones_ordenados(actuales)
        if _normal(nuevos) != _normal(antes):
            ajustes[RUTA_ESCALONES] = nuevos
            for numero in range(max(len(antes), len(nuevos))):
                dicho_antes = _texto_de_escalon(antes[numero] if numero < len(antes) else None, ppd)
                dicho_despues = _texto_de_escalon(nuevos[numero] if numero < len(nuevos) else None, ppd)
                if dicho_antes != dicho_despues:
                    cambios.append({'campo': f'Escalón {numero + 1}', 'ruta': RUTA_ESCALONES,
                                    'antes': dicho_antes, 'despues': dicho_despues})
    for ruta in list(ajustes):
        if _iguales_en_json(ajustes[ruta], leer(seccion_base, ruta)):
            del ajustes[ruta]
    # Un valor que ``ajustes_validos`` descartaría (p. ej. un número negativo) nunca se guarda en silencio.
    for ruta in ajustes.keys() - ajustes_validos(ajustes).keys():
        campo = CAMPOS_POR_RUTA.get(ruta)
        problemas.append(f'{campo.etiqueta}: no puede ser negativo.' if campo
                         else 'La escalera está mal armada: revisa cada escalón (cuánto hay que vender y cuánto gana).')
    candidato = aplicar_ajustes(base, ajustes)
    return {'ajustes': ajustes, 'cambios': cambios, 'candidato': candidato, 'problemas_de_pantalla': problemas,
            'problemas': problemas + problemas_de_las_cifras(candidato)}


def cambios_contra_fabrica(base, actuales):
    """Lo que cambiaría «Volver a los valores de fábrica»: ``[{campo, antes, despues}]`` (vacío = ya está igual)."""
    try:
        ppd = puntos_por_dolar(base)
    except FaltaConfigurar:
        return []
    pantalla_actual, pantalla_base = valores_de_pantalla(actuales), valores_de_pantalla(base)
    cambios = []
    seccion_actual, seccion_base = RV.seccion(actuales), RV.seccion(base)
    for campo in CAMPOS:
        if not _iguales_en_json(leer(seccion_actual, campo.ruta), leer(seccion_base, campo.ruta)):
            cambios.append({'campo': campo.etiqueta, 'ruta': campo.ruta_texto,
                            'antes': como_texto(campo, pantalla_actual[campo.clave]),
                            'despues': como_texto(campo, pantalla_base[campo.clave])})
    antes, despues = _escalones_ordenados(actuales), _escalones_ordenados(base)
    if _normal(antes) != _normal(despues):
        for numero in range(max(len(antes), len(despues))):
            dicho_antes = _texto_de_escalon(antes[numero] if numero < len(antes) else None, ppd)
            dicho_despues = _texto_de_escalon(despues[numero] if numero < len(despues) else None, ppd)
            if dicho_antes != dicho_despues:
                cambios.append({'campo': f'Escalón {numero + 1}', 'ruta': RUTA_ESCALONES,
                                'antes': dicho_antes, 'despues': dicho_despues})
    return cambios


# ---------------------------------------------------------------------------
# ¿Cuánto cuesta?
# ---------------------------------------------------------------------------

def _puntos_del_cliente(reglas):
    """Lo que cuestan los puntos de Socios del cliente, en % de la venta neta (``None`` si falta una cifra).

    El cliente gana ``acumulacion.puntosPorDolar`` por dólar pagado; con la base «total» eso incluye el ITBMS."""
    acumulacion, canje = reglas.get('acumulacion') or {}, reglas.get('canje') or {}
    por_dolar, al_canjear = acumulacion.get('puntosPorDolar'), canje.get('puntosPorDolar')
    if not por_dolar or not al_canjear:
        return None
    con_itbms = acumulacion.get('baseDeCalculo') == 'total'
    pagado = 1 + _fr(acumulacion.get('itbmsPorcentaje') or 0) / 100 if con_itbms else 1
    return _fr(por_dolar) * pagado / _fr(al_canjear) * 100


def costo_del_programa(reglas):
    """Lo que le cuesta a D'CASA cada venta, en % de la venta neta, con las cifras que se le pasan.

    Cada escalón: (comisión + patrocinio) × lo que de verdad cuesta un punto de vendedor (``pesoDelPuntoDeVendedor``)
    + los puntos del cliente. ``peor`` es el escalón más caro, con patrocinio: la venta que más cuesta. El punto de
    equilibrio es ``peor ÷ margen``: qué parte de lo vendido con código tiene que ser de clientes que no habrían
    comprado para que el programa se pague (sin margen supuesto en ``puntos.json``, no se calcula). ``None`` si
    falta alguna cifra. No inventa supuestos: todo sale de ``puntos.json`` y de los ajustes."""
    seccion = RV.seccion(reglas)
    comision, patrocinio, techos = (seccion.get('comision') or {}), (seccion.get('patrocinio') or {}), \
        (seccion.get('techos') or {})
    escalones = comision.get('escalones') or []
    tasas = [comision.get('puntosPorDolarNeto'), *(e.get('puntosPorDolarNeto') for e in escalones)]
    tasas = [_fr(t) for t in tasas if t is not None]
    cliente = _puntos_del_cliente(reglas)
    if not tasas or cliente is None:
        return None
    peso = RV.peso_del_punto_de_vendedor(reglas)
    extra = _fr(patrocinio.get('puntosPorDolarNetoDelDirecto') or 0)
    por_escalon = [(t + extra) * peso + cliente for t in sorted(tasas)]
    peor = max(por_escalon)
    margen, techo = techos.get('margenBrutoSupuestoPorcentaje'), techos.get('totalPorVentaPorcentajeDelNeto')
    return {
        'por_escalon': [float(costo) for costo in por_escalon], 'peor': float(peor), 'cliente': float(cliente),
        'margen': float(margen) if margen else None,
        'equilibrio': float(peor / _fr(margen) * 100) if margen else None,
        'techo': float(techo) if techo is not None else None,
        'supera_el_techo': techo is not None and peor > _fr(techo),
    }


# ---------------------------------------------------------------------------
# Límites duros: lo que NO se deja guardar
# ---------------------------------------------------------------------------

def _problemas_de_rango(seccion, ppd):
    """Cada cifra de ``CAMPOS`` presente, bien escrita y dentro de su rango (en las unidades de la pantalla)."""
    problemas = []
    for campo in CAMPOS:
        valor = leer(seccion, campo.ruta)
        if valor is None:
            if campo.obligatorio:
                problemas.append(f'Falta una cifra: {campo.etiqueta.lower()}.')
            continue
        if not _valor_valido(campo, valor):
            problemas.append(f'{campo.etiqueta}: el valor no es un número válido.')
            continue
        dicho = a_pantalla(campo, valor, ppd)
        if campo.positivo and not dicho > 0:
            problemas.append(f'{campo.etiqueta}: tiene que ser mayor que cero.')
        elif dicho < campo.minimo:
            problemas.append(f'{campo.etiqueta}: no puede ser menos de {como_texto(campo, campo.minimo)}.')
        if campo.maximo is not None and dicho > campo.maximo:
            problemas.append(f'{campo.etiqueta}: no puede pasar de {como_texto(campo, campo.maximo)}.')
    return problemas


def _problemas_de_techos(reglas, seccion, escalones):
    """Ninguna comisión sobre el techo por venta; el techo no sobre la ganancia supuesta; el freno no sobre el techo;
    y que una sola venta no pueda costar más que el techo."""
    comision, techos = seccion.get('comision') or {}, seccion.get('techos') or {}
    techo, base = techos.get('totalPorVentaPorcentajeDelNeto'), comision.get('puntosPorDolarNeto')
    if not (_es_numero(techo) and techo > 0):
        return []
    problemas = []
    if _es_numero(base) and base > techo:
        problemas.append(f'La comisión base ({como_porcentaje(base)}) no puede ser mayor que el techo de costo por '
                         f'venta ({como_porcentaje(techo)}): baja la comisión o sube el techo.')
    for numero, escalon in enumerate(escalones, 1):
        if escalon['puntosPorDolarNeto'] > techo:
            problemas.append(f"Escalón {numero}: paga {como_porcentaje(escalon['puntosPorDolarNeto'])} y el techo de "
                             f'costo por venta es {como_porcentaje(techo)}: baja el escalón o sube el techo.')
    margen = techos.get('margenBrutoSupuestoPorcentaje')
    if _es_numero(margen) and techo > margen:
        problemas.append(f'El techo por venta ({como_porcentaje(techo)}) no puede ser mayor que la ganancia que se '
                         f'supone en cada venta ({como_porcentaje(margen)}).')
    freno = techos.get('frenoGlobalPorcentajeDeLaVentaNeta')
    if _es_numero(freno) and freno > techo:
        problemas.append(f'El freno de todo el programa ({como_porcentaje(freno)}) no puede ser mayor que el techo '
                         f'por venta ({como_porcentaje(techo)}).')
    costo = costo_del_programa(reglas)
    if costo and costo['supera_el_techo']:
        peor = como_porcentaje(round(costo['peor'], 2))
        problemas.append(f'Con estas cifras una sola venta podría costar hasta {peor} de la venta neta y el techo '
                         f'por venta es {como_porcentaje(techo)}: baja las comisiones o sube el techo.')
    return problemas


def problemas_de_las_cifras(reglas):
    """Todo lo que está mal o es incoherente en estas reglas, dicho en palabras sencillas (vacío = se puede guardar).

    Cubre: cifras que faltan; cada cifra dentro de su rango; ninguna comisión (ni de escalón) por encima del techo por
    venta; el patrocinio no mayor que la comisión base; que una sola venta no pueda costar más que el techo; el techo
    no mayor que la ganancia supuesta; el freno de todo el programa no mayor que el techo; las primeras ventas no
    esperan menos que las demás; y la coherencia de la escalera (umbrales que suben, tasas que suben, topes que no
    bajan)."""
    seccion = RV.seccion(reglas)
    if not seccion:
        return ['Faltan las cifras del programa de vendedores en puntos.json.']
    try:
        ppd = puntos_por_dolar(reglas)
    except FaltaConfigurar as error:
        return [str(error)]
    problemas = _problemas_de_rango(seccion, ppd)
    comision = seccion.get('comision') or {}
    escalones = _escalones_ordenados(reglas) if _escalones_validos(comision.get('escalones') or []) else []
    if comision.get('escalones') and not escalones:
        problemas.append('La escalera está mal armada: revisa cada escalón (cuánto hay que vender y cuánto gana).')
    problemas += _problemas_de_techos(reglas, seccion, escalones)
    patrocinio, base = (seccion.get('patrocinio') or {}).get('puntosPorDolarNetoDelDirecto'), \
        comision.get('puntosPorDolarNeto')
    if _es_numero(patrocinio) and _es_numero(base) and patrocinio > base:
        problemas.append(f'El patrocinio ({como_porcentaje(patrocinio)}) no puede ser mayor que la comisión base '
                         f'({como_porcentaje(base)}): quien patrocina no gana más que quien vende.')
    retencion = seccion.get('retencion') or {}
    if retencion.get('primerasVentas') and (retencion.get('diasPrimerasVentas') or 0) < (retencion.get('dias') or 0):
        problemas.append('Las primeras ventas de un vendedor nuevo no pueden esperar menos días que las demás.')
    if escalones:
        problemas.extend(RV.problemas_de_la_escalera(reglas))
    return problemas
