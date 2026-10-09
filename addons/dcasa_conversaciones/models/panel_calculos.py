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
PERIODOS = ('hoy', '7_dias', '30_dias')
NOMBRES_PERIODO = {'hoy': 'Hoy', '7_dias': 'Últimos 7 días', '30_dias': 'Últimos 30 días'}
DIAS_DEL_PERIODO = {'hoy': 1, '7_dias': 7, '30_dias': 30}


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
