"""Cuentas sencillas de las pantallas Resumen, Costos y Conexiones: funciones PURAS (sin base de datos).

Aquí no se inventa nada: todo se calcula con lo que dice el Worker o lo que ya está en Odoo. Si falta el dato, el
resultado es ``None`` y la pantalla lo dice («todavía es pronto para proyectar»).
"""
import calendar
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

# Dominios desde los que el puente de WhatsApp descarga las fotos y documentos (MEDIOS_HOSTS_PERMITIDOS del puente).
DOMINIOS_DEL_PUENTE = ('dcasapty.com', 'dcasapty.workers.dev')
# 90 días y 12 meses: para medir en más tiempo (pedido de la dueña, 2026-11-03).
PERIODOS = ('hoy', '7_dias', '30_dias', '90_dias', '12_meses')
NOMBRES_PERIODO = {'hoy': 'Hoy', '7_dias': 'Últimos 7 días', '30_dias': 'Últimos 30 días',
                   '90_dias': 'Últimos 90 días', '12_meses': 'Últimos 12 meses'}
DIAS_DEL_PERIODO = {'hoy': 1, '7_dias': 7, '30_dias': 30, '90_dias': 90, '12_meses': 365}
# Una venta se le atribuye al asistente si habló con el cliente en los 30 días antes de la factura (decisión de la
# dueña, 2026-11-03).
VENTANA_DE_ATRIBUCION_DIAS = 30


def url_descargable_por_el_puente(url):
    """¿El puente puede bajar archivos de esta dirección? Solo https y solo los dominios de D'CASA."""
    try:
        partes = urlsplit(url or '')
        puerto = partes.port
    except ValueError:
        return False
    host = (partes.hostname or '').lower()
    if partes.scheme != 'https' or not host or partes.username or puerto not in (None, 443):
        return False
    return any(host == d or host.endswith('.' + d) for d in DOMINIOS_DEL_PUENTE)


def dias_del_mes(fecha):
    return calendar.monthrange(fecha.year, fecha.month)[1]


def proyeccion_del_mes(gasto, ahora_local, minimo_dias=1.0):
    """Cuánto sería el gasto al terminar el mes si sigue el ritmo de hasta ahora (lineal).

    ``ahora_local``: ``datetime`` en la hora de Panamá. Devuelve ``None`` si aún no pasó ``minimo_dias`` días
    (un día de datos no dice nada del mes), y ``0.0`` si no se ha gastado nada.
    """
    transcurrido = (ahora_local.day - 1) + (ahora_local.hour * 3600 + ahora_local.minute * 60
                                            + ahora_local.second) / 86400
    if transcurrido < minimo_dias:
        return None
    if not gasto or gasto <= 0:
        return 0.0
    return round(gasto / transcurrido * dias_del_mes(ahora_local), 2)


def estado_del_tope(gasto, proyeccion, tope):
    """``sin_tope`` · ``alcanzado`` · ``en_riesgo`` (la proyección lo pasa) · ``bien``."""
    if not tope or tope <= 0:
        return 'sin_tope'
    if gasto >= tope:
        return 'alcanzado'
    if proyeccion is not None and proyeccion > tope:
        return 'en_riesgo'
    return 'bien'


def gasto_por_dia(instantaneas, mes):
    """Gasto de cada día del ``mes`` («AAAA-MM») a partir de fotos del acumulado.

    ``instantaneas``: ``{date: acumulado_usd}``. El gasto de un día es su acumulado menos el del día anterior;
    el día 1 es su propio acumulado (el Worker reinicia la cuenta cada mes). Un día sin foto, o cuyo día anterior
    no tiene foto, queda en ``None``: no se adivina. Devuelve ``[(date, gasto|None)]`` de todos los días con foto.
    """
    resultado = []
    for dia in sorted(d for d in instantaneas if d.strftime('%Y-%m') == mes):
        if dia.day == 1:
            gasto = instantaneas[dia]
        else:
            anterior = instantaneas.get(dia - timedelta(days=1))
            gasto = None if anterior is None else max(round(instantaneas[dia] - anterior, 6), 0.0)
        resultado.append((dia, None if gasto is None else round(gasto, 2)))
    return resultado


def unir_gasto_por_dia(de_fotos, del_worker, mes):
    """Junta el gasto por día armado con fotos (``gasto_por_dia``) con el que el Worker lleva día a día.

    El del Worker manda donde existe (es exacto y no depende de que alguien abra la pantalla); las fotos llenan los
    días anteriores a que el Worker empezara a llevarlo. Devuelve ``[{'fecha': 'AAAA-MM-DD', 'usd': gasto|None}]``,
    en orden de fecha.
    """
    por_fecha = {dia.isoformat(): gasto for dia, gasto in de_fotos}
    for x in del_worker or []:
        fecha = x.get('fecha') if isinstance(x, dict) else None
        usd = x.get('usd') if isinstance(x, dict) else None
        if (isinstance(fecha, str) and fecha.startswith(f'{mes}-') and re.fullmatch(r'\d{4}-\d{2}-\d{2}', fecha)
                and isinstance(usd, (int, float)) and not isinstance(usd, bool) and usd >= 0):
            por_fecha[fecha] = round(float(usd), 2)
    return [{'fecha': fecha, 'usd': por_fecha[fecha]} for fecha in sorted(por_fecha)]


# ----------------------------------------------------------------------------------------------------------------
# «Consumido desde el último pago» (Costos de IA, pedido de la dueña, 2026-11-12)
# ----------------------------------------------------------------------------------------------------------------
#
# La IA se paga en Meta y lo que cobra Meta coincide casi exacto con lo que calcula el sistema; la dueña quiere ir a
# la par: «cuánto se consumió desde el último pago». NADA se borra ni se reinicia: un pago solo marca un CORTE en la
# línea del gasto. Con lo que ya hay:
#
# * el Worker sabe solo el acumulado del MES en curso (mes de Panamá; vuelve a cero el día 1, a las 00:00);
# * Odoo guarda una foto diaria de ese acumulado (``dcasa.juan.costo.dia``: el cron de las 23:50 y cada visita).
#
# Un corte es ``(mes, acumulado de ese mes en ese instante)``. Al registrar un pago «ahora», el corte lo da el Worker
# (exacto). Si el Worker no responde, o el pago es de otro momento, el corte es el último punto conocido ANTES del
# pago: la última foto de ese mismo mes, o el inicio del mes (el Worker empieza en cero: ese punto siempre se conoce).
# Lo consumido entre ese punto y el pago cae «después del pago»: la cifra puede quedar un poco por encima, y la
# pantalla dice que es aproximada (``corte_del_pago``).
#
# Lo consumido entre dos cortes (``consumo_entre``):
# * los dos en el mismo mes: la resta de los acumulados;
# * pago en un mes y consulta en otro: lo que faltaba del mes del pago (su cierre − el corte) + los meses completos
#   de en medio (su cierre) + el acumulado del mes de llegada (empezó en cero). El cierre de un mes es su ÚLTIMA foto:
#   si no es del último día (esa noche el cron no corrió) el mes queda «incompleto», y si no tiene ninguna foto
#   (antes de que existiera el cron, u Odoo apagado todo el mes) queda «sin datos» y suma cero. En los dos casos la
#   cifra es un mínimo («al menos») y se nombran los meses; nunca se adivina;
# * un corte posterior al siguiente (p. ej. un pago anotado con el Worker caído toma una foto anterior a otro pago ya
#   anotado) o un acumulado que bajó (el Worker perdió su cuenta) dan cero, nunca un negativo.
#
# Con varios pagos (``periodos_de_pagos``): «desde el último pago» mira solo el más reciente por la FECHA del pago (no
# por cuándo se anotó); cada pago de la lista muestra lo consumido entre el pago anterior y él (el primero no tiene
# con qué compararse) y la diferencia con lo que cobró Meta, solo si las dos cifras son completas. Los pagos anulados
# no cuentan para nada (siguen en la lista, con su motivo).


def meses_entre(desde, hasta):
    """«2026-09», «2026-11» → ``['2026-09', '2026-10', '2026-11']`` (los dos incluidos); ``[]`` si ``hasta`` es antes."""
    anio, mes = (int(x) for x in desde.split('-'))
    fin = tuple(int(x) for x in hasta.split('-'))
    meses = []
    while (anio, mes) <= fin:
        meses.append(f'{anio:04d}-{mes:02d}')
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return meses


def corte_del_pago(momento_local, fotos, es_ahora=False, acumulado_worker=None):
    """El corte de un pago hecho en ``momento_local`` (``datetime`` en la hora de Panamá).

    ``es_ahora``: el pago es de este momento; ``acumulado_worker``: lo que acaba de decir el Worker (``None`` si no
    respondió). ``fotos``: ``{date: acumulado}``. Devuelve ``{'mes', 'acumulado', 'origen', 'foto'}`` con ``origen``:

    * ``worker``: el acumulado del Worker en el momento de anotarlo (exacto; solo si ``es_ahora``);
    * ``foto``: la última foto del mismo mes tomada antes del pago. «Ahora» vale la de hoy (se tomó antes); para un
      pago de otro momento, solo las de días anteriores (la del mismo día pudo tomarse después del pago);
    * ``inicio_de_mes``: sin fotos antes del pago en ese mes, el 1 del mes a las 00:00, cuando el Worker empezó en 0.
    """
    mes = momento_local.strftime('%Y-%m')
    if es_ahora and acumulado_worker is not None:
        return {'mes': mes, 'acumulado': round(max(float(acumulado_worker), 0.0), 6), 'origen': 'worker', 'foto': None}
    dia = momento_local.date()
    antes = [d for d in fotos if d.strftime('%Y-%m') == mes and (d <= dia if es_ahora else d < dia)]
    if antes:
        foto = max(antes)
        return {'mes': mes, 'acumulado': round(max(float(fotos[foto] or 0.0), 0.0), 6), 'origen': 'foto', 'foto': foto}
    return {'mes': mes, 'acumulado': 0.0, 'origen': 'inicio_de_mes', 'foto': None}


def cierres_de_mes(fotos):
    """El cierre de cada mes con las fotos diarias ``{date: acumulado}``: ``{'AAAA-MM': (acumulado, completo)}``.

    El acumulado es el de la última foto del mes; ``completo`` dice si esa foto es del último día del mes."""
    ultimas = {}
    for dia in fotos:
        mes = dia.strftime('%Y-%m')
        if mes not in ultimas or dia > ultimas[mes]:
            ultimas[mes] = dia
    return {mes: (float(fotos[dia] or 0.0), dia.day == dias_del_mes(dia)) for mes, dia in ultimas.items()}


def consumo_entre(desde, hasta, cierres):
    """Lo consumido entre dos cortes ``(mes «AAAA-MM», acumulado de ese mes)`` (ver el comentario de arriba).

    ``cierres``: lo de ``cierres_de_mes``. Devuelve ``{'usd', 'completo', 'meses_sin_datos', 'meses_incompletos'}``;
    si ``completo`` es falso, ``usd`` es un mínimo (a algún mes de en medio le falta su cierre).
    """
    (mes_a, a), (mes_b, b) = desde, hasta
    a, b = float(a or 0.0), float(b or 0.0)
    resultado = {'usd': 0.0, 'completo': True, 'meses_sin_datos': [], 'meses_incompletos': []}
    if mes_b < mes_a:
        return resultado
    if mes_a == mes_b:
        resultado['usd'] = round(max(b - a, 0.0), 2)
        return resultado
    total = 0.0
    for mes in meses_entre(mes_a, mes_b)[:-1]:
        cierre = cierres.get(mes)
        if cierre is None:
            resultado['meses_sin_datos'].append(mes)
            continue
        usd, completo = cierre
        if not completo:
            resultado['meses_incompletos'].append(mes)
        total += max(usd - (a if mes == mes_a else 0.0), 0.0)
    total += max(b, 0.0)
    resultado['usd'] = round(total, 2)
    resultado['completo'] = not (resultado['meses_sin_datos'] or resultado['meses_incompletos'])
    return resultado


def periodos_de_pagos(pagos, cierres, ahora=None):
    """Las cuentas de la lista de pagos y de la cifra «Consumido desde el último pago».

    ``pagos``: ``[{'id', 'fecha', 'corte': (mes, acumulado), 'exacto': bool, 'monto': float|None, 'anulado': bool}]``
    en cualquier orden (``exacto``: el corte lo dio el Worker). ``ahora``: el corte de este momento (mes y acumulado
    que dice el Worker) o ``None`` si no respondió.

    Devuelve ``(por_pago, desde_el_ultimo)``:

    * ``por_pago[id] = {'calculado': consumo_entre|None, 'aproximado': bool, 'diferencia': float|None}``.
      ``calculado`` es ``None`` en el primer pago vigente (no hay corte anterior) y en los anulados. ``diferencia`` =
      lo que cobró Meta − lo calculado, solo si Meta lo anotó y lo calculado es completo.
    * ``desde_el_ultimo``: ``consumo_entre`` desde el último pago vigente hasta ``ahora``, más ``pago_id`` y
      ``aproximado``; ``None`` sin pagos vigentes o sin ``ahora``.
    """
    vigentes = sorted((p for p in pagos if not p['anulado']), key=lambda p: (p['fecha'], p['id']))
    por_pago = {p['id']: {'calculado': None, 'aproximado': False, 'diferencia': None} for p in pagos}
    for anterior, pago in zip(vigentes, vigentes[1:]):
        calculado = consumo_entre(anterior['corte'], pago['corte'], cierres)
        diferencia = None
        if pago['monto'] is not None and calculado['completo']:
            diferencia = round(pago['monto'] - calculado['usd'], 2)
        por_pago[pago['id']] = {'calculado': calculado, 'aproximado': not (anterior['exacto'] and pago['exacto']),
                                'diferencia': diferencia}
    desde_el_ultimo = None
    if vigentes and ahora is not None:
        ultimo = vigentes[-1]
        desde_el_ultimo = {**consumo_entre(ultimo['corte'], ahora, cierres), 'pago_id': ultimo['id'],
                           'aproximado': not ultimo['exacto']}
    return por_pago, desde_el_ultimo


def mediana(valores):
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    medio = len(valores) // 2
    return valores[medio] if len(valores) % 2 else (valores[medio - 1] + valores[medio]) / 2


def duracion_corta(segundos):
    """90 → «1 min 30 s» · 4000 → «1 h 7 min» · ``None`` → «—». Es un texto para personas."""
    if segundos is None:
        return '—'
    segundos = int(round(segundos))
    if segundos < 60:
        return f'{segundos} s'
    minutos, resto = divmod(segundos, 60)
    if minutos < 60:
        return f'{minutos} min {resto} s' if resto and minutos < 10 else f'{minutos} min'
    horas, minutos = divmod(minutos, 60)
    if horas < 48:
        return f'{horas} h {minutos} min' if minutos else f'{horas} h'
    return f'{horas // 24} d {horas % 24} h' if horas % 24 else f'{horas // 24} d'


def tasa(ventas, conversaciones):
    """Ventas cerradas por cada 100 conversaciones (porcentaje, dos decimales), o ``None`` si no hubo conversaciones."""
    if not conversaciones:
        return None
    return round(100.0 * ventas / conversaciones, 2)


def tasas_de_cierre(conversaciones, ventas):
    """La tasa de cierre del periodo (pedido de la dueña, 2026-11-05): ventas cerradas ÷ conversaciones × 100, con las
    ventas atribuidas partidas como en «Ventas atribuidas»: el asistente y una persona, solo el asistente y el total de
    las dos (donde participó el asistente). ``ventas`` es lo que devuelve ``_ventas_atribuidas``."""
    con_persona = ventas['juan_y_vendedora']['facturas']
    solo = ventas['solo_juan']['facturas']
    return {
        'conversaciones': conversaciones,
        'juan_y_vendedora': {'ventas': con_persona, 'tasa': tasa(con_persona, conversaciones)},
        'solo_juan': {'ventas': solo, 'tasa': tasa(solo, conversaciones)},
        'total': {'ventas': con_persona + solo, 'tasa': tasa(con_persona + solo, conversaciones)},
    }


def limites_del_periodo(periodo, ahora_local):
    """``(inicio_local, fin_local)`` del periodo, a la medianoche de Panamá. El fin es exclusivo (mañana 00:00)."""
    if periodo not in PERIODOS:
        raise ValueError(periodo)
    hoy = ahora_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return hoy - timedelta(days=DIAS_DEL_PERIODO[periodo] - 1), hoy + timedelta(days=1)


def fecha_de_iso(texto):
    """«2026-10-09» → ``date``; ``None`` si no es una fecha."""
    if not isinstance(texto, str) or not re.fullmatch(r'\d{4}-\d\d-\d\d', texto):
        return None
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return None


def mes_de(fecha):
    return fecha.strftime('%Y-%m') if isinstance(fecha, (date, datetime)) else None
