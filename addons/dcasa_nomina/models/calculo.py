"""Cálculos de la planilla, sin base de datos (se prueban solos en tests/test_calculo.py).

Aquí NO hay ninguna tasa, tramo ni fecha de la ley: todo llega como argumento desde
``dcasa.nomina.parametros`` (las tasas con vigencia que valida el contador). Estas funciones solo hacen la
aritmética y el redondeo a centavos (mitad hacia arriba), igual en todas las pantallas y reportes.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

PERIODOS_POR_ANIO = 24  # planilla quincenal
MESES_DE_LA_PARTIDA = 4  # el décimo tercer mes se paga en 3 partidas de 4 meses
DIVISOR_DECIMO = 12  # cada partida = lo devengado en sus 4 meses / 12


def r2(valor):
    """Centavos, mitad hacia arriba (0.125 → 0.13), sin los errores de coma flotante."""
    return float(Decimal(str(valor or 0.0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def porcentaje(base, tasa):
    """``tasa`` está en por ciento (9.75 = 9,75 %)."""
    return r2((base or 0.0) * (tasa or 0.0) / 100.0)


def impuesto_anual(renta_anual, tramos):
    """ISR de una renta anual con tramos marginales ``[(desde, hasta|None, tasa %)]``.

    Cada tramo grava solo la parte de la renta que cae dentro de él: ``hasta`` vacío es «sin tope».
    """
    renta = max(renta_anual or 0.0, 0.0)
    total = 0.0
    for desde, hasta, tasa in tramos:
        if renta <= desde:
            continue
        tope = renta if not hasta else min(renta, hasta)
        total += (tope - desde) * (tasa or 0.0) / 100.0
    return r2(total)


def dias_pagados(desde, hasta, ingreso=None, salida=None):
    """Días del periodo [desde, hasta] (ambos incluidos) en que la persona estuvo contratada."""
    inicio = max(desde, ingreso) if ingreso else desde
    fin = min(hasta, salida) if salida else hasta
    return max((fin - inicio).days + 1, 0)


def dias_del_periodo(desde, hasta):
    return (hasta - desde).days + 1


def salario_del_periodo(salario_mensual, dias_pagados_, dias_periodo):
    """Una quincena es medio salario mensual; si entró o salió a mitad se paga la parte de los días."""
    if not dias_periodo:
        return 0.0
    return r2((salario_mensual or 0.0) / 2.0 * dias_pagados_ / dias_periodo)


def isr_del_periodo(salario_quincena_completa, fraccion, extras, tramos, descuento_css_se_pct=0.0,
                    deducciones_anuales=0.0):
    """Retención de ISR de una quincena por «proyección anual» (a validar por el contador).

    * La parte regular (el salario de una quincena completa) se proyecta a todo el año (24 quincenas):
      impuesto anual / 24, y se paga en proporción a los días que se trabajaron (``fraccion`` entre 0 y 1).
    * Lo extra de esa quincena (horas extras, bonos) NO se proyecta: paga el impuesto adicional que causa
      sobre la renta anual del salario.
    * ``descuento_css_se_pct`` (suma de seguro social + educativo del trabajador, en %) se resta de la renta si
      los parámetros dicen que el ISR se calcula después de esos aportes (cero = no se resta).
    * ``deducciones_anuales``: lo que el contador autoriza deducir a esa persona en el año.
    """
    factor = 1.0 - (descuento_css_se_pct or 0.0) / 100.0
    regular = max((salario_quincena_completa or 0.0) * PERIODOS_POR_ANIO * factor - (deducciones_anuales or 0.0), 0.0)
    base = impuesto_anual(regular, tramos)
    adicional = 0.0
    if extras:
        adicional = impuesto_anual(regular + extras * factor, tramos) - base
    return r2(base / PERIODOS_POR_ANIO * fraccion + adicional)


def meses_trabajados(desde, hasta, ingreso=None, salida=None):
    """Meses (con fracción) trabajados en [desde, hasta]: cada mes cuenta por la parte de sus días trabajados."""
    inicio = max(desde, ingreso) if ingreso else desde
    fin = min(hasta, salida) if salida else hasta
    total = 0.0
    dia = date(inicio.year, inicio.month, 1)
    while dia <= fin:
        siguiente = date(dia.year + (dia.month == 12), dia.month % 12 + 1, 1)
        ultimo = siguiente - timedelta(days=1)
        a, b = max(inicio, dia), min(fin, ultimo)
        if b >= a:
            total += ((b - a).days + 1) / ((ultimo - dia).days + 1)
        dia = siguiente
    return round(total, 4)


def vacaciones_ganadas(dias_de_servicio, dias_de_trabajo_por_dia_de_descanso):
    """Un día de descanso por cada ``n`` días de trabajo (Código de Trabajo: 11) = 30 días por 11 meses."""
    if not dias_de_trabajo_por_dia_de_descanso:
        return 0.0
    return round(max(dias_de_servicio, 0) / dias_de_trabajo_por_dia_de_descanso, 2)


def valor_de_los_dias(salario_mensual, dias):
    """Valor de ``dias`` de descanso: un día = salario mensual / 30."""
    return r2((salario_mensual or 0.0) / 30.0 * dias)


def anios_de_servicio(ingreso, hasta):
    """Años de servicio con fracción (días / 365)."""
    if not ingreso or hasta < ingreso:
        return 0.0
    return round(((hasta - ingreso).days + 1) / 365.0, 4)


def prima_de_antiguedad(salario_mensual, anios, semanas_por_anio, semanas_por_mes):
    """``semanas_por_anio`` semanas de salario por año de servicio (semana = salario mensual / semanas por mes)."""
    if not semanas_por_mes:
        return 0.0
    return r2((salario_mensual or 0.0) / semanas_por_mes * semanas_por_anio * anios)


def decimo(devengado_de_la_partida):
    """Una partida del décimo tercer mes = lo devengado en sus 4 meses / 12."""
    return r2((devengado_de_la_partida or 0.0) / DIVISOR_DECIMO)


# Las tres partidas del décimo tercer mes: (mes de pago, día de pago, (mes, día) de inicio, (mes, día) de cierre,
# y si el periodo empieza el año anterior). Fechas de fuentes públicas (15 de abril, agosto y diciembre).
PARTIDAS = {
    '1': {'pago': (4, 15), 'inicio': (12, 1), 'fin': (3, 31), 'inicia_el_anio_anterior': True},
    '2': {'pago': (8, 15), 'inicio': (4, 1), 'fin': (7, 31), 'inicia_el_anio_anterior': False},
    '3': {'pago': (12, 15), 'inicio': (8, 1), 'fin': (11, 30), 'inicia_el_anio_anterior': False},
}


def fechas_de_la_partida(partida, anio):
    """``(desde, hasta, fecha_de_pago)`` de una partida del décimo tercer mes del año ``anio``."""
    datos = PARTIDAS[partida]
    anio_inicio = anio - 1 if datos['inicia_el_anio_anterior'] else anio
    return (date(anio_inicio, *datos['inicio']), date(anio, *datos['fin']), date(anio, *datos['pago']))


def partida_de(fecha):
    """``(partida, desde, hasta, fecha_de_pago)`` de la partida del décimo que contiene ``fecha``."""
    for clave in PARTIDAS:
        for anio in (fecha.year, fecha.year + 1):
            desde, hasta, pago = fechas_de_la_partida(clave, anio)
            if desde <= fecha <= hasta:
                return clave, desde, hasta, pago
    raise ValueError(fecha)  # las tres partidas cubren todo el año
