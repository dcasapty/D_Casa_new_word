"""Las reglas del programa de VENDEDORES de D'CASA, y la aritmética que las aplica.

Igual que ``reglas.py`` (Socios): todo lo de aquí es PURO. Entra un número y las reglas, sale un número; no toca la
base ni lee la hora. Por eso se prueba entero.

NINGUNA CIFRA ESTÁ ESCRITA AQUÍ. Todas vienen de la sección ``vendedores`` de ``data/puntos.json`` (la única fuente,
versionada en git). Una cifra en ``null`` no se rellena a ojo: el programa se niega a acreditar hasta que alguien la
decida con un commit.

Unidad: 1 punto = 1 centavo nominal (la misma escala de Socios: ``canje.puntosPorDolar``). Por eso, con la venta NETA
en centavos, el porcentaje nominal que se lleva un vendedor es igual a sus puntos por dólar.
"""

import secrets
from datetime import timedelta
from fractions import Fraction

from .reglas import ALFABETO_CODIGO, LARGO_CODIGO, FaltaConfigurar, codigo_normal

PREFIJO_CODIGO_VENDEDOR = 'VEN'
FORMAS_DE_PAGO = ('cada-compra', 'primera-compra')


def seccion(reglas):
    """La sección «vendedores» de las reglas (vacía si el archivo todavía no la trae)."""
    return reglas.get('vendedores') or {}


# ---------------------------------------------------------------------------
# ¿Está lista la economía?
# ---------------------------------------------------------------------------

def falta_para_comisionar(reglas):
    """Lo que falta decidir para que el programa acredite. Vacío = listo.

    ``programaActivo`` es el interruptor de la dueña: apagado, el programa no acredita nada y las ventas siguen
    igual. Encendido, ninguna cifra clave puede estar en ``null``.
    """
    v = seccion(reglas)
    if not v.get('programaActivo'):
        return ['vendedores.programaActivo: el programa de vendedores está apagado.']
    falta = []
    comision = v.get('comision') or {}
    ppd = comision.get('puntosPorDolarNeto')
    if ppd is None:
        falta.append('vendedores.comision.puntosPorDolarNeto: falta definir cuántos puntos gana el vendedor por dólar.')
    elif not ppd > 0:
        falta.append('vendedores.comision.puntosPorDolarNeto tiene que ser mayor que cero.')
    if comision.get('pagaEn') not in FORMAS_DE_PAGO:
        falta.append('vendedores.comision.pagaEn: falta decidir si paga en cada compra o solo en la primera.')
    if (v.get('retencion') or {}).get('dias') is None:
        falta.append('vendedores.retencion.dias: falta definir cuántos días esperan los puntos antes de canjearse.')
    if (v.get('techos') or {}).get('totalPorVentaPorcentajeDelNeto') is None:
        falta.append('vendedores.techos.totalPorVentaPorcentajeDelNeto: falta definir el techo de costo por venta.')
    return falta


def falta_para_patrocinar(reglas):
    """El patrocinio (un nivel) necesita su propia cifra; sin ella, el vendedor directo gana y el patrocinador no."""
    p = seccion(reglas).get('patrocinio') or {}
    if p.get('puntosPorDolarNetoDelDirecto') is None:
        return ['vendedores.patrocinio.puntosPorDolarNetoDelDirecto: falta definir lo que gana quien patrocina.']
    return []


# ---------------------------------------------------------------------------
# Puntos
# ---------------------------------------------------------------------------

def _validar_neto(neto_centavos):
    if not isinstance(neto_centavos, int) or isinstance(neto_centavos, bool) or neto_centavos < 0:
        raise ValueError('La venta neta va en centavos enteros, sin negativos.')


def _puntos(neto_centavos, puntos_por_dolar):
    """Puntos de una venta neta. Redondea SIEMPRE hacia abajo (como Socios): nunca se regala una fracción."""
    _validar_neto(neto_centavos)
    # Fracción exacta: 0.4 × 14500 es 5800 y no 5799.999…; un decimal escrito en el JSON se toma tal cual.
    return int(Fraction(neto_centavos) * Fraction(str(puntos_por_dolar)) // 100)


def puntos_por_dolar_de_escalon(ventas_netas_centavos, comision):
    """Puntos por dólar que corresponden según lo vendido en los últimos días (escalones opcionales).

    ``escalones`` es una lista ``[{"desdeVentasNetasCentavos": 0, "puntosPorDolarNeto": 3}, ...]``. Sin escalones,
    vale la cifra base. Toma el escalón más alto que se alcanzó.
    """
    base = comision['puntosPorDolarNeto']
    escalones = sorted(comision.get('escalones') or [], key=lambda e: e['desdeVentasNetasCentavos'])
    valor = base
    for escalon in escalones:
        if ventas_netas_centavos >= escalon['desdeVentasNetasCentavos']:
            valor = escalon['puntosPorDolarNeto']
    return valor


def comision_directa(neto_centavos, reglas, ventas_netas_recientes_centavos=0):
    """Puntos del vendedor que trajo la venta. Venta mínima y escalones de ``puntos.json``."""
    _validar_neto(neto_centavos)
    falta = falta_para_comisionar(reglas)
    if falta:
        raise FaltaConfigurar('vendedores', ' '.join(falta))
    comision = seccion(reglas)['comision']
    minimo = comision.get('compraMinimaCentavos')
    if minimo is not None and neto_centavos < minimo:
        return 0
    return _puntos(neto_centavos, puntos_por_dolar_de_escalon(ventas_netas_recientes_centavos, comision))


def comision_patrocinio(neto_centavos, reglas):
    """Puntos del patrocinador por la venta de su vendedor DIRECTO (un solo nivel). No resta nada al directo."""
    _validar_neto(neto_centavos)
    falta = falta_para_comisionar(reglas) + falta_para_patrocinar(reglas)
    if falta:
        raise FaltaConfigurar('vendedores', ' '.join(falta))
    minimo = (seccion(reglas).get('comision') or {}).get('compraMinimaCentavos')
    if minimo is not None and neto_centavos < minimo:
        return 0
    return _puntos(neto_centavos, seccion(reglas)['patrocinio']['puntosPorDolarNetoDelDirecto'])


def aplicar_factor_de_recompra(puntos, reglas):
    """La compra de un cliente ligado que llega SIN código paga una fracción de la comisión (``factorDeRecompra``).
    Sin cifra, paga entera."""
    factor = (seccion(reglas).get('comision') or {}).get('factorDeRecompra')
    if factor is None:
        return puntos
    return int(Fraction(puntos) * Fraction(str(factor)))


def aplicar_factor_de_cliente_existente(puntos, reglas):
    """La venta con código a un cliente que YA había comprado en D'CASA (no lo trajo el vendedor) paga una fracción
    (``factorClienteExistente``). Sin cifra, paga entera."""
    factor = (seccion(reglas).get('comision') or {}).get('factorClienteExistente')
    if factor is None:
        return puntos
    return int(Fraction(puntos) * Fraction(str(factor)))


def patrocinio_solo_clientes_nuevos(reglas):
    """¿El patrocinio solo nace de la primera compra de un cliente nuevo? Así el patrocinador no cobra sobre ventas que
    la tienda ya tenía. Por defecto no (paga en toda venta que pagó al directo)."""
    return bool((seccion(reglas).get('patrocinio') or {}).get('soloClientesNuevos', False))


def patrocinio_paga_en_recompras(reglas):
    """¿Las recompras de un cliente ligado (sin código) también dan patrocinio? Por defecto no."""
    return bool((seccion(reglas).get('vinculacion') or {}).get('pagaPatrocinio', False))


def ventas_propias_minimas_para_patrocinar(reglas):
    """Cuántas ventas propias pagadas tiene que haber hecho el patrocinador en el mes para cobrar patrocinio."""
    return (seccion(reglas).get('patrocinio') or {}).get('ventasPropiasMinimasAlMes') or 0


def topar_patrocinio(puntos, patrocinio_ya_ganado_en_el_mes, comision_propia_del_mes, reglas):
    """El patrocinio de un mes no puede pasar de ``topeComoMultiploDeSuComisionDelMes`` veces la comisión propia que
    el patrocinador ganó ese mes: así el patrocinio nunca es la mayor parte de su ingreso. Lo que sobra se pierde."""
    multiplo = (seccion(reglas).get('patrocinio') or {}).get('topeComoMultiploDeSuComisionDelMes')
    if multiplo is None:
        return puntos
    tope = int(Fraction(comision_propia_del_mes) * Fraction(str(multiplo)))
    return max(0, min(puntos, tope - patrocinio_ya_ganado_en_el_mes))


def repartir_bajo_el_freno_global(directa, patrocinio, emitido_en_30_dias, venta_neta_30_dias_centavos, reglas):
    """Freno final del programa: lo emitido a vendedores en los últimos 30 días no pasa de un porcentaje de la venta
    neta de esos mismos 30 días (de TODA la tienda, no solo de lo vendido con código).

    Devuelve ``(directa, patrocinio, recortado)``; se recorta primero el patrocinio. Es el seguro contra una cifra mal
    puesta o una racha de ventas con código: la venta nunca falla, solo se recorta lo que se emite. Se mide en una
    ventana móvil (no en el mes del calendario) para que los primeros días del mes no queden sin base."""
    pct = (seccion(reglas).get('techos') or {}).get('frenoGlobalPorcentajeDeLaVentaNeta')
    if pct is None:
        return directa, patrocinio, False
    cabe = max(0, int(Fraction(max(venta_neta_30_dias_centavos, 0)) * Fraction(str(pct)) // 100) - emitido_en_30_dias)
    if directa + patrocinio <= cabe:
        return directa, patrocinio, False
    nueva_directa = min(directa, cabe)
    return nueva_directa, min(patrocinio, cabe - nueva_directa), True


def techo_total_por_venta(neto_centavos, reglas):
    """Lo máximo que una venta puede costar entre cliente, vendedor y patrocinador (en puntos de costo real)."""
    pct = seccion(reglas)['techos']['totalPorVentaPorcentajeDelNeto']
    return int(Fraction(neto_centavos) * Fraction(str(pct)) // 100)


def peso_del_punto_de_vendedor(reglas):
    """Cuánto le cuesta de verdad a D'CASA un punto de vendedor, frente a uno de cliente (que vale 1): los puntos de
    vendedor solo se canjean por mercancía que cuesta una fracción de su precio. Sin cifra, vale 1 (lo más estricto)."""
    peso = (seccion(reglas).get('techos') or {}).get('pesoDelPuntoDeVendedor')
    return Fraction(str(peso)) if peso else Fraction(1)


def puntos_minimos_de_premio(costo, puntos_por_dolar, reglas):
    """Lo menos que puede pedir un premio de vendedores: su costo en puntos, dividido entre el peso del punto de
    vendedor. Así el costo real del punto nunca pasa del peso que el techo da por supuesto."""
    exacto = Fraction(str(costo)) * Fraction(str(puntos_por_dolar)) / peso_del_punto_de_vendedor(reglas)
    return -((-exacto.numerator) // exacto.denominator)          # hacia arriba


def repartir_bajo_el_techo(directa, patrocinio, puntos_del_cliente, neto_centavos, reglas):
    """Aplica el techo por venta. Devuelve ``(directa, patrocinio, recortado)``.

    El cliente ya recibió sus puntos (Socios, y el referido que su compra disparó): lo que sobra del techo, medido en
    costo real, es lo que pueden repartirse el vendedor y su patrocinador, y se recorta primero al patrocinador (quien
    trajo la venta no pierde antes que el patrocinio).
    """
    peso = peso_del_punto_de_vendedor(reglas)
    cabe_real = max(0, techo_total_por_venta(neto_centavos, reglas) - max(0, puntos_del_cliente))
    cabe = int(Fraction(cabe_real) / peso)
    if directa + patrocinio <= cabe:
        return directa, patrocinio, False
    nueva_directa = min(directa, cabe)
    nuevo_patrocinio = min(patrocinio, cabe - nueva_directa)
    return nueva_directa, nuevo_patrocinio, True


def topar_al_mes(puntos, ya_ganados_en_el_mes, tope):
    """Recorta ``puntos`` para no pasar el tope mensual. ``tope`` ``None`` = sin tope."""
    if tope is None:
        return puntos
    return max(0, min(puntos, tope - ya_ganados_en_el_mes))


def disponible_desde(cuando, reglas, ventas_previas=None):
    """Desde cuándo se pueden gastar unos puntos acreditados ``cuando`` (ventana de devoluciones).

    A quien apenas empieza (menos de ``retencion.primerasVentas`` ventas con puntos) se le exige más espera
    (``retencion.diasPrimerasVentas``): «vender, canjear y que el cliente devuelva» es el truco de quien recién llega.
    ``ventas_previas`` ``None`` = no se sabe, vale la ventana normal."""
    retencion = seccion(reglas).get('retencion') or {}
    dias = retencion.get('dias') or 0
    primeras, dias_nuevo = retencion.get('primerasVentas'), retencion.get('diasPrimerasVentas')
    if ventas_previas is not None and primeras and dias_nuevo and ventas_previas < primeras:
        dias = max(dias, dias_nuevo)
    return cuando + timedelta(days=dias)


def tope_de_directos(reglas):
    return (seccion(reglas).get('patrocinio') or {}).get('topeDeDirectos')


def meses_de_vinculacion(reglas):
    """Cuántos meses queda ligado un cliente al vendedor que lo trajo. 0 o ``None``: solo la compra con el código."""
    return (seccion(reglas).get('vinculacion') or {}).get('meses') or 0


# ---------------------------------------------------------------------------
# Códigos
# ---------------------------------------------------------------------------

def nuevo_codigo_vendedor():
    return PREFIJO_CODIGO_VENDEDOR + ''.join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))


def es_codigo_vendedor_valido(codigo):
    return (
        len(codigo) == len(PREFIJO_CODIGO_VENDEDOR) + LARGO_CODIGO
        and codigo.startswith(PREFIJO_CODIGO_VENDEDOR)
        and all(c in ALFABETO_CODIGO for c in codigo[len(PREFIJO_CODIGO_VENDEDOR):])
    )


def codigo_vendedor_normal(valor):
    return codigo_normal(valor)
