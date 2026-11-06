"""La fórmula de la tarifa de envíos (puerto fiel del HTML de la propuesta, 2026-11-04).

La tarifa se define con tres precios que Gerencia conoce: el **mínimo** (cerca de la tienda) y dos puntos, «a A km
cuesta $X» y «a B km cuesta $Y». De ahí sale una recta:

    por_km = (Y − X) / (B − A)          salida = X − A × por_km
    base(km) = máx(redondear(mínimo × f), redondear(máx(mínimo, salida + por_km × km) × f))

donde ``f = 1 + ajuste % / 100`` («subir o bajar todo en proporción») y ``redondear`` lleva el precio al múltiplo de
``paso`` (hacia arriba o al más cercano; ``paso = 0`` deja los centavos). Encima van los **cargos aparte** (viático,
honorarios, peaje u otros), cada uno con su forma de cobrarse:

* ``viaje``    — fijo por viaje;
* ``km``       — por cada km;
* ``desde_km`` — fijo si el viaje llega a «desde» km;
* ``km_desde`` — por cada km después de «desde»;
* ``peaje``    — fijo si la ruta pasa por peaje.

Un cargo solo cuenta si está activo y su monto es mayor que cero; con «ajusta» sube o baja con el mismo %. Un lugar a
más de ``maxKm`` (o sin carretera, o sin medir) no tiene precio: se cotiza aparte.

Los números se calculan en el mismo orden y con los mismos redondeos que JavaScript (ver :mod:`.texto`): el precio que
da el servidor es, centavo por centavo, el del HTML.
"""
import math

from .texto import centavos, dinero, js_ceil, js_round, km_txt, numero_js, to_fixed

COMO_SE_COBRA = {
    'viaje': 'Fijo por viaje',
    'km': 'Por cada km',
    'desde_km': 'Fijo si pasa de cierto km',
    'km_desde': 'Por km después de cierto km',
    'peaje': 'Solo si la ruta pasa por peaje',
}
ESTADOS_CON_PRECIO = ('ok', 'revisar', 'lancha')
PASOS = {0: 'sin redondear', 1: 'redondeado a $1', 5: 'redondeado a $5', 10: 'redondeado a $10'}
# Ejemplos fijos del HTML para ver el efecto del % (km por carretera desde la tienda).
EJEMPLOS_DEL_EFECTO = (('Cerca de la tienda', 5.0), ('Ciudad (Santa Ana)', 36.0), ('Santiago', 205.0))


def numero(valor, defecto=0.0):
    """``Number(valor) || defecto`` de JavaScript: lo que no es un número (o es 0) vale ``defecto``."""
    if isinstance(valor, bool):
        valor = float(valor)
    try:
        resultado = float(valor)
    except (TypeError, ValueError):
        return defecto
    if math.isnan(resultado) or resultado == 0:
        return defecto
    return resultado


class Tarifa:
    """La tarifa con la forma del HTML (``ajustes``): ``minimo``, ``anclaA`` {km, precio}, ``anclaB`` {km, precio,
    nombre}, ``ajustePct``, ``paso``, ``modo`` (arriba o cercano), ``maxKm`` y ``extras`` (los cargos aparte)."""

    def __init__(self, ajustes):
        a = ajustes or {}
        ancla_a = a.get('anclaA') or {}
        ancla_b = a.get('anclaB') or {}
        self.minimo = numero(a.get('minimo'))
        self.a_km = numero(ancla_a.get('km'))
        self.a_precio = numero(ancla_a.get('precio'))
        self.b_km = numero(ancla_b.get('km'))
        self.b_precio = numero(ancla_b.get('precio'))
        self.b_nombre = ancla_b.get('nombre') or ''
        self.ajuste_pct = numero(a.get('ajustePct'))
        self.paso = numero(a.get('paso'))
        self.modo = 'cercano' if a.get('modo') == 'cercano' else 'arriba'
        self.max_km = numero(a.get('maxKm'))
        self.aprobada = bool(a.get('aprobada'))
        self.extras = [dict(e) for e in (a.get('extras') or []) if isinstance(e, dict)]

    # --- La forma del HTML -----------------------------------------------------------------------------------------
    def como_ajustes(self):
        """De vuelta a la forma del HTML (para guardarla o mandarla a otra pantalla)."""
        return {
            'minimo': self.minimo, 'anclaA': {'km': self.a_km, 'precio': self.a_precio},
            'anclaB': {'km': self.b_km, 'precio': self.b_precio, 'nombre': self.b_nombre},
            'ajustePct': self.ajuste_pct, 'paso': self.paso, 'modo': self.modo, 'maxKm': self.max_km,
            'aprobada': self.aprobada, 'extras': [dict(e) for e in self.extras],
        }

    @property
    def configurada(self):
        """Tiene los dos puntos de la recta (el segundo más lejos que el primero) y una distancia máxima."""
        return self.b_km > self.a_km and self.max_km > 0

    # --- La fórmula (mismas operaciones, en el mismo orden, que el HTML) ---------------------------------------------
    def por_km(self):
        return (self.b_precio - self.a_precio) / (self.b_km - self.a_km)

    def salida(self):
        return self.a_precio - self.a_km * self.por_km()

    def factor(self):
        return 1 + self.ajuste_pct / 100

    def redondear(self, valor):
        paso = self.paso
        if not paso:
            return js_round(valor * 100) / 100
        if self.modo == 'cercano':
            return js_round(valor / paso) * paso
        return js_ceil(valor / paso - 1e-6) * paso

    def bruto_base(self, km):
        return max(self.minimo, self.salida() + self.por_km() * km) * self.factor()

    def base(self, km):
        return max(self.redondear(self.minimo * self.factor()), self.redondear(self.bruto_base(km)))

    def cargos_activos(self):
        return [e for e in self.extras if e.get('activo') and numero(e.get('monto')) > 0]

    def cargos(self, km, peaje):
        """Los cargos aparte que tocan en este viaje: ``[{'nombre', 'v'}]`` (solo los mayores que cero)."""
        salida = []
        for cargo in self.extras:
            monto = numero(cargo.get('monto'))
            if not cargo.get('activo') or monto <= 0:
                continue
            desde = numero(cargo.get('desde'))
            como = cargo.get('como')
            valor = 0.0
            if como == 'viaje':
                valor = monto
            elif como == 'km':
                valor = monto * km
            elif como == 'desde_km':
                valor = monto if km >= desde else 0.0
            elif como == 'km_desde':
                valor = max(0.0, km - desde) * monto
            elif como == 'peaje':
                valor = monto if peaje else 0.0
            if cargo.get('ajusta'):
                valor *= self.factor()
            valor = centavos(valor)
            if valor > 0:
                salida.append({'nombre': cargo.get('nombre') or 'Cargo', 'v': valor})
        return salida

    def cotizar(self, km, peaje=False):
        """``{'base', 'extras': [{'nombre', 'v'}], 'total'}`` para un viaje de ``km`` por carretera."""
        km = float(km)
        base = self.base(km)
        extras = self.cargos(km, peaje)
        suma = 0.0
        for cargo in extras:          # suma de izquierda a derecha, como reduce() (no sum(), que compensa)
            suma = suma + cargo['v']
        return {'base': base, 'extras': extras, 'total': centavos(base + suma)}

    def con_precio(self, lugar):
        """¿Ese lugar tiene precio? Medido, a lo sumo ``maxKm`` y con carretera (``ok``, ``revisar`` o ``lancha``)."""
        km = lugar.get('km')
        return km is not None and km <= self.max_km and lugar.get('estado') in ESTADOS_CON_PRECIO

    # --- Tramos -----------------------------------------------------------------------------------------------------
    def tramos(self):
        """Dónde cambia la tarifa base, de 0 a ``maxKm`` en décimas de km: ``[{'desde', 'hasta', 'p'}]``."""
        salida = []
        desde, ultimo = 0.0, None
        km = 0.0
        while km <= self.max_km + 0.05:
            precio = self.base(km)
            if precio != ultimo:
                if ultimo is not None:
                    salida.append({'desde': desde, 'hasta': km - 0.1, 'p': ultimo})
                desde, ultimo = km, precio
            km = js_round((km + 0.1) * 10) / 10
        salida.append({'desde': desde, 'hasta': self.max_km, 'p': ultimo})
        return salida

    def tramos_para_mostrar(self):
        """Los tramos de la tabla de la pantalla. Sin redondeo cada décima cambia el precio: se agrupan de a $1."""
        if self.paso:
            filas = self.tramos()
        else:
            filas, desde = [], 0.0
            precio = js_ceil(self.base(0))
            tope = self.base(self.max_km) + 1
            while precio <= tope:
                hasta = (precio / self.factor() - self.salida()) / self.por_km()
                hasta = min(max(hasta, desde), self.max_km)
                if hasta > desde:
                    filas.append({'desde': desde, 'hasta': hasta, 'p': precio})
                    desde = hasta
                precio += 1
        return [{**fila, 'km_txt': (('hasta' if fila['desde'] == 0 else km_txt(fila['desde']) + ' –')
                                    + f" {km_txt(fila['hasta'])} km"),
                 'precio_txt': dinero(fila['p'])} for fila in filas]

    def nota_tramos(self):
        if self.paso:
            return 'Solo la tarifa base; los cargos aparte se suman encima.'
        return 'Sin redondeo, cada décima de km cambia el precio; aquí se ven en tramos de $1.'

    # --- Textos de la regla ------------------------------------------------------------------------------------------
    def regla(self):
        """Las fichas de la cabecera, como el HTML: «$X de salida» + «$Y por km» · «mínimo $Z» · el redondeo · el
        ajuste · los cargos que se cobran. Lista de ``(clase, texto)``: ``ficha`` o ``mas`` (el signo entre fichas)."""
        factor = self.factor()
        fichas = [('ficha', f'${to_fixed(self.salida() * factor, 2)} de salida'), ('mas', '+'),
                  ('ficha', f'${to_fixed(self.por_km() * factor, 3)} por km'), ('mas', '·'),
                  ('ficha', f'mínimo {dinero(self.redondear(self.minimo * factor))}'), ('mas', '·')]
        paso = PASOS.get(self.paso, '')
        if self.paso:
            paso += ' (al más cercano)' if self.modo == 'cercano' else ' hacia arriba'
        fichas.append(('ficha', paso))
        if self.ajuste_pct:
            signo = '+' if self.ajuste_pct > 0 else ''
            fichas += [('mas', '·'), ('ficha', f'ajuste {signo}{numero_js(self.ajuste_pct)} %')]
        activos = [e.get('nombre') for e in self.cargos_activos()]
        if activos:
            fichas += [('mas', '+'), ('ficha', ', '.join(str(n or '') for n in activos))]
        return fichas

    def formula_txt(self):
        """«Con estos precios: $X de salida + $Y por km, mínimo $Z.» (la recta sin el %, y luego el %)."""
        pct = ''
        if self.ajuste_pct:
            pct = f", y luego {'+' if self.ajuste_pct > 0 else ''}{numero_js(self.ajuste_pct)} %"
        return (f'Con estos precios: ${to_fixed(self.salida(), 2)} de salida + ${to_fixed(self.por_km(), 3)} por km, '
                f'mínimo ${numero_js(self.minimo)}{pct}.')

    def efecto(self):
        """Lo que cuesta un viaje de ejemplo sin ajuste y con el % puesto: ``[{nombre, antes, ahora}]``."""
        sin_ajuste = Tarifa({**self.como_ajustes(), 'ajustePct': 0})
        ejemplos = [EJEMPLOS_DEL_EFECTO[0], (f'{km_txt(self.a_km)} km', self.a_km), EJEMPLOS_DEL_EFECTO[1],
                    (self.b_nombre or f'{km_txt(self.b_km)} km', self.b_km), EJEMPLOS_DEL_EFECTO[2]]
        salida = []
        for nombre, km in ejemplos:
            antes, ahora = sin_ajuste.base(km), self.base(km)
            texto = f'{nombre}: {dinero(antes)}'
            if self.ajuste_pct:
                texto += f' → {dinero(ahora)}'
            salida.append({'nombre': nombre, 'km': km, 'antes': antes, 'ahora': ahora, 'texto': texto})
        return salida
