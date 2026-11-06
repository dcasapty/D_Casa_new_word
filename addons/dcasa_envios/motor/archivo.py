"""Leer el archivo de envíos de Gerencia (el mismo ``envios-dcasa.html`` o un JSON con su forma), sin Odoo.

El HTML guarda sus datos en tres bloques ``<script type="application/json">``:

* ``lugares`` — la lista de lugares (nombre, tipo, cat, corr, corr_exacto, dist, prov, km, peaje, estado, fuente_km,
  alias, lat, lon, nota);
* ``ajustes`` — la tarifa (minimo, anclaA, anclaB, ajustePct, paso, modo, maxKm, extras…);
* ``agregados-datos`` — los lugares que Gerencia agregó a mano en el HTML.

Un JSON sirve igual si trae ``{"lugares": [...], "ajustes": {...}, "agregados": [...]}`` (o solo la lista de lugares).
Nada de esto se guarda en el repositorio: el archivo lo sube Gerencia en Envíos › Tarifa.
"""
import json
import math
import re

from .buscador import TIPOS, sin_tildes
from .tarifa import COMO_SE_COBRA

ESTADOS = ('ok', 'revisar', 'lancha', 'sin_carretera', 'no_encontrado', 'fuera', 'sin_dato')
PASOS_VALIDOS = (0, 1, 5, 10)
MAX_LUGARES = 60000
LARGOS = {'name': 200, 'cat': 80, 'corr': 120, 'dist': 120, 'prov': 120, 'fuente_km': 80, 'nota': 500}


class ArchivoInvalido(ValueError):
    """El archivo no tiene la forma esperada; el mensaje dice qué falta, en palabras sencillas."""


def _bloque(texto, ident):
    m = re.search(rf'<script\s+id="{ident}"\s+type="application/json">(.*?)</script>', texto, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError as error:
        raise ArchivoInvalido(f'El bloque «{ident}» del archivo está dañado ({error}).') from error


def leer_archivo(datos):
    """``(lugares, ajustes, agregados)`` del archivo (bytes). ``ajustes`` es ``None`` si el archivo no trae tarifa."""
    try:
        texto = datos.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ArchivoInvalido('El archivo no es un texto en UTF-8: sube el envios-dcasa.html o su JSON.') from error
    inicio = texto.lstrip()[:1]
    if inicio in '{[' and inicio:
        try:
            contenido = json.loads(texto)
        except ValueError as error:
            raise ArchivoInvalido(f'El JSON está dañado ({error}).') from error
        if isinstance(contenido, list):
            lugares, ajustes, agregados = contenido, None, []
        elif isinstance(contenido, dict):
            lugares = contenido.get('lugares')
            ajustes = contenido.get('ajustes')
            agregados = contenido.get('agregados', contenido.get('agregados-datos')) or []
        else:
            raise ArchivoInvalido('El JSON no tiene la forma del archivo de envíos.')
    else:
        lugares = _bloque(texto, 'lugares')
        ajustes = _bloque(texto, 'ajustes')
        agregados = _bloque(texto, 'agregados-datos') or []
        if lugares is None:
            raise ArchivoInvalido('No encontré la lista de lugares: ¿es el archivo envios-dcasa.html de la '
                                  'calculadora?')
    if not isinstance(lugares, list) or not isinstance(agregados, list):
        raise ArchivoInvalido('La lista de lugares del archivo no tiene la forma esperada.')
    if ajustes is not None and not isinstance(ajustes, dict):
        raise ArchivoInvalido('La tarifa del archivo no tiene la forma esperada.')
    if len(lugares) + len(agregados) > MAX_LUGARES:
        raise ArchivoInvalido(f'El archivo trae más de {MAX_LUGARES} lugares: revisa que sea el correcto.')
    return lugares, ajustes, agregados


def _texto(valor, campo):
    if not isinstance(valor, str):
        return ''
    return ' '.join(valor.split())[:LARGOS[campo]]


def _numero(valor, minimo=None, maximo=None):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    valor = float(valor)
    if not math.isfinite(valor) or (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
        return None
    return valor


def normalizar_lugar(dato):
    """Un lugar del archivo con los nombres de campo de Odoo, o ``(None, motivo)`` si no se puede cargar."""
    if not isinstance(dato, dict):
        return None, 'no es un lugar'
    nombre = _texto(dato.get('nombre'), 'name')
    if not nombre:
        return None, 'sin nombre'
    tipo = dato.get('tipo')
    if tipo not in TIPOS:
        return None, 'tipo desconocido'
    dist = _texto(dato.get('dist'), 'dist')
    if not dist:
        return None, 'sin distrito'
    km = _numero(dato.get('km'), 0, 5000)
    lat = _numero(dato.get('lat'), -90, 90)
    lon = _numero(dato.get('lon'), -180, 180)
    if lat is None or lon is None:
        lat = lon = None
    alias = [' '.join(a.split())[:LARGOS['name']] for a in (dato.get('alias') or []) if isinstance(a, str)]
    estado = dato.get('estado')
    return {
        'name': nombre,
        'tipo': tipo,
        'cat': _texto(dato.get('cat'), 'cat'),
        'corr': _texto(dato.get('corr'), 'corr'),
        'corr_exacto': bool(dato.get('corr_exacto')),
        'dist': dist,
        'prov': _texto(dato.get('prov'), 'prov'),
        'km': km if km is not None else 0.0,
        'km_medido': km is not None,
        'peaje': bool(dato.get('peaje')),
        'estado': estado if estado in ESTADOS else 'sin_dato',
        'fuente_km': _texto(dato.get('fuente_km'), 'fuente_km'),
        'alias': '\n'.join(a for a in alias if a),
        'lat': lat if lat is not None else 0.0,
        'lon': lon if lon is not None else 0.0,
        'nota': _texto(dato.get('nota'), 'nota'),
    }, ('estado desconocido' if estado not in ESTADOS else None)


def llave(lugar):
    """La llave estable de un lugar del archivo: nombre + tipo + distrito + corregimiento (sin tildes ni
    mayúsculas). Dos lugares distintos con la misma llave se distinguen por sus coordenadas al cargar."""
    partes = (lugar.get('name'), lugar.get('tipo'), lugar.get('dist'), lugar.get('corr'))
    return '|'.join(' '.join(sin_tildes(p or '').split()) for p in partes)


def normalizar_ajustes(ajustes):
    """La tarifa del archivo con los nombres de campo de Odoo: ``(valores, cargos)``. Lanza ArchivoInvalido si un
    número no tiene sentido (los precios no se adivinan)."""
    def numero(valor, que, minimo=0.0, maximo=None):
        resultado = _numero(valor, minimo, maximo)
        if resultado is None:
            raise ArchivoInvalido(f'La tarifa del archivo tiene un número que no sirve en «{que}».')
        return resultado

    ancla_a = ajustes.get('anclaA') or {}
    ancla_b = ajustes.get('anclaB') or {}
    paso = numero(ajustes.get('paso', 0), 'redondear a')
    if paso not in PASOS_VALIDOS:
        raise ArchivoInvalido('La tarifa del archivo redondea a un paso que la calculadora no conoce.')
    valores = {
        'minimo': numero(ajustes.get('minimo'), 'mínimo'),
        'ancla_a_km': numero(ancla_a.get('km'), 'precio a … km'),
        'ancla_a_precio': numero(ancla_a.get('precio'), '… cuesta'),
        'ancla_b_km': numero(ancla_b.get('km'), 'precio a … km (lejos)'),
        'ancla_b_precio': numero(ancla_b.get('precio'), '… cuesta (lejos)'),
        'ancla_b_nombre': _texto(ancla_b.get('nombre'), 'corr'),
        'ajuste_pct': numero(ajustes.get('ajustePct', 0), 'ajuste %', -90, 300),
        'paso': str(int(paso)),
        'modo': 'cercano' if ajustes.get('modo') == 'cercano' else 'arriba',
        'max_km': numero(ajustes.get('maxKm'), 'cotizar aparte desde', 10, 2000),
        'nota': _texto(ajustes.get('nota'), 'nota'),
    }
    if valores['ancla_b_km'] <= valores['ancla_a_km']:
        raise ArchivoInvalido('En la tarifa del archivo, el segundo punto no está más lejos que el primero.')
    cargos = []
    for posicion, extra in enumerate(ajustes.get('extras') or []):
        if not isinstance(extra, dict) or extra.get('como') not in COMO_SE_COBRA:
            raise ArchivoInvalido('Un cargo aparte de la tarifa del archivo no tiene la forma esperada.')
        cargos.append({
            'codigo': _texto(extra.get('id'), 'cat') or f'cargo{posicion + 1}',
            'name': _texto(extra.get('nombre'), 'cat') or 'Cargo',
            'como': extra['como'],
            'monto': numero(extra.get('monto') or 0, 'monto de un cargo'),
            'desde': numero(extra.get('desde') or 0, 'desde km de un cargo'),
            'ajusta': bool(extra.get('ajusta')),
            'activo': bool(extra.get('activo')),
            'sequence': (posicion + 1) * 10,
        })
    version = _numero(ajustes.get('version'), 0)
    fecha = ajustes.get('fecha') if isinstance(ajustes.get('fecha'), str) else ''
    valores['version_archivo'] = int(version) if version is not None else 0
    valores['fecha_archivo'] = fecha if re.fullmatch(r'\d{4}-\d{2}-\d{2}', fecha or '') else False
    return valores, cargos
