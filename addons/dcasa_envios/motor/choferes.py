"""Lo que ve un chofer con el enlace de la calculadora (``/envios/choferes/<enlace>``), como datos puros y sin Odoo.

Pedido de la dueña (2026-11-09): «que no vean la tabla de kilometraje, solamente busquen el lugar y confirmen si ese es
el precio, o vean el precio y la dirección en Google Maps … que la persona desde donde está dé clic y se ponga su
ubicación y a partir de ahí se calcule».

* De cada lugar el chofer ve **solo** el nombre, la zona, el precio y la ruta en Google Maps desde la tienda
  (:func:`para_chofer` arma una lista blanca de claves, ``CLAVES``). Nunca los km, la tabla por tramos, el desglose ni
  la fórmula.
* Mientras Gerencia no apruebe la tarifa no sale ningún precio: «Tarifa en revisión: confirma el precio con la tienda».
* Lo que se cotiza aparte (lejos, sin carretera o sin medir) sale sin precio: «Se cotiza aparte: confirma con la
  tienda».
* «Usar mi ubicación» busca el lugar de la tabla más cercano por sus coordenadas (:func:`cercanos`): gratis, sin API de
  mapas. Hasta 3 lugares a no más de 3 km. La distancia se dice en metros («a 300 m»): en la pantalla del chofer no
  aparece la palabra «km».
"""
import math

from .texto import entero_pa, js_round

RADIO_TIERRA_M = 6371008.8          # radio medio de la Tierra (metros)
RADIO_CERCA_M = 3000                # «cerca de ti»: a lo sumo 3 km
MAX_CERCA = 3
MAX_BUSQUEDA = 8
MAX_SUGERENCIAS = 6
MIN_TEXTO = 2
# Panamá con margen (su mar y sus islas incluidos): una ubicación fuera de aquí no es la de un chofer de D'CASA.
LATITUD = (6.0, 10.5)
LONGITUD = (-83.8, -76.5)
EN_REVISION = 'Tarifa en revisión: confirma el precio con la tienda'
APARTE = 'Se cotiza aparte: confirma con la tienda'
NADA_CERCA = 'No hay un lugar de la tabla cerca de ti: búscalo por nombre o confirma con la tienda'
# Lo único que sale de un lugar hacia el chofer (y, con «Usar mi ubicación», la distancia).
CLAVES = ('nombre', 'zona', 'precio', 'aviso', 'mapa')
CLAVES_CERCA = CLAVES + ('distancia',)


def coordenada(valor):
    """Un número finito (un texto, un booleano o un ``NaN`` no son coordenadas)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    valor = float(valor)
    return valor if math.isfinite(valor) else None


def ubicacion_valida(lat, lon):
    """``(lat, lon)`` como números si caen en Panamá (con margen); si no, ``None``."""
    lat, lon = coordenada(lat), coordenada(lon)
    if lat is None or lon is None:
        return None
    if not (LATITUD[0] <= lat <= LATITUD[1] and LONGITUD[0] <= lon <= LONGITUD[1]):
        return None
    return lat, lon


def distancia_m(lat1, lon1, lat2, lon2):
    """Metros en línea recta entre dos puntos (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(min(1.0, math.sqrt(a)))


def cercanos(lugares, lat, lon, radio_m=RADIO_CERCA_M, maximo=MAX_CERCA):
    """Los lugares con coordenadas a lo sumo a ``radio_m`` metros, del más cercano al más lejano:
    ``[(posición, metros)]`` (a lo sumo ``maximo``). Los que no tienen coordenadas no cuentan.

    Primero descarta por un recuadro (más grande que el círculo) y solo mide de verdad a los de adentro: así no
    calcula 11 000 distancias en cada toque."""
    margen_lat = radio_m / 110_000                          # un grado de latitud mide unos 111 km: sobra
    margen_lon = margen_lat / max(math.cos(math.radians(lat)), 0.01)
    encontrados = []
    for posicion, lugar in enumerate(lugares):
        la, lo = lugar.get('lat'), lugar.get('lon')
        if la is None or lo is None or abs(la - lat) > margen_lat or abs(lo - lon) > margen_lon:
            continue
        metros = distancia_m(lat, lon, la, lo)
        if metros <= radio_m:
            encontrados.append((metros, posicion))
    encontrados.sort()
    return [(posicion, metros) for metros, posicion in encontrados[:maximo]]


def distancia_txt(metros):
    """«a 300 m»: siempre en metros, redondeado a 10 m (a 50 m desde 1 000 m)."""
    paso = 10 if metros < 1000 else 50
    return f'a {entero_pa(max(paso, js_round(metros / paso) * paso))} m'


def zona(tarjeta):
    """«Corregimiento · Distrito» (sin repetir el nombre del lugar cuando es el mismo corregimiento)."""
    nombre, corr = tarjeta.get('nombre') or '', tarjeta.get('corr') or ''
    partes = (corr if corr and corr != nombre else '', tarjeta.get('dist') or '')
    return ' · '.join(p for p in partes if p)


def para_chofer(tarjeta, aprobada, metros=None):
    """Lo único que ve el chofer de un lugar: su tarjeta del motor (más ``corr`` y ``dist``) reducida a ``CLAVES``.

    ``aprobada``: la tarifa está aprobada por Gerencia (si no, ningún precio). ``metros``: con «Usar mi ubicación», a
    cuánto está de quien pregunta."""
    if not aprobada:
        precio, aviso = '', EN_REVISION
    elif not tarjeta.get('con_precio'):
        precio, aviso = '', APARTE
    else:
        precio, aviso = tarjeta.get('total_txt') or '', ''
        if any(chip.get('texto') == '+ lancha' for chip in tarjeta.get('chips') or ()):
            precio += ' + lancha'
    datos = {'nombre': tarjeta.get('nombre') or '', 'zona': zona(tarjeta), 'precio': precio, 'aviso': aviso,
             'mapa': tarjeta.get('url_mapa') or ''}
    if metros is not None:
        datos['distancia'] = distancia_txt(metros)
    return datos
