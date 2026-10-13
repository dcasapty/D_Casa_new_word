"""Horario laboral y fechas de seguimiento: funciones PURAS (sin base de datos, sin reloj).

Odoo guarda las fechas como ``datetime`` ingenuos en UTC. Todas las funciones de aquí reciben y
devuelven ese mismo formato (UTC ingenuo) y convierten por dentro a la hora de Panamá, de modo
que nadie más tenga que pensar en zonas horarias:

    siguiente_horario_laboral(utc, horario)        → UTC ingenuo
    fecha_de_seguimiento(base, ...)                → UTC ingenuo

Convención de los días: ``0 = domingo … 6 = sábado`` (la de ``Date.getDay()`` de JavaScript, que
es lo que lee el Worker ``juan``). Python usa ``weekday()`` con lunes = 0: ``dia_js`` hace el cambio.

Panamá no tiene horario de verano (UTC−5 todo el año). Aun así se usa ``zoneinfo`` y, solo si el
sistema no trae la base de zonas horarias, un desfase fijo de −5 h para ``America/Panama``.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ZONA_PANAMA = 'America/Panama'
DIAS = (0, 1, 2, 3, 4, 5, 6)
NOMBRES_DIA = ('domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado')
DIAS_MAX_BUSQUEDA = 8   # con al menos un día activo, el próximo horario laboral cae en ≤ 7 días


def cargar_zona(nombre=ZONA_PANAMA):
    try:
        return ZoneInfo(nombre or ZONA_PANAMA)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        if (nombre or ZONA_PANAMA) == ZONA_PANAMA:
            return timezone(timedelta(hours=-5), ZONA_PANAMA)
        raise


@dataclass(frozen=True)
class Horario:
    inicio: time = time(8, 0)
    fin: time = time(17, 0)
    dias: frozenset = frozenset(DIAS)
    zona: str = ZONA_PANAMA

    def __post_init__(self):
        if not self.inicio < self.fin:
            raise ValueError('La hora de inicio tiene que ser anterior a la de fin.')
        if not set(self.dias) <= set(DIAS):
            raise ValueError('Los días van de 0 (domingo) a 6 (sábado).')

    def como_json(self):
        return {'inicio': texto_hora(self.inicio), 'fin': texto_hora(self.fin),
                'dias': sorted(self.dias), 'zona': self.zona}


@dataclass(frozen=True)
class ReglaSeguimiento:
    """Seguimiento a quien preguntó y no volvió a escribir (decisión de la dueña)."""
    primero_horas: float = 5
    segundo_dias: float = 5
    solo_horario_laboral: bool = True
    maximo: int = 2


# ---------------------------------------------------------------------------
# Conversión
# ---------------------------------------------------------------------------

def a_local(utc, horario):
    """UTC ingenuo → fecha y hora local (con zona) de ``horario.zona``."""
    return utc.replace(tzinfo=UTC).astimezone(cargar_zona(horario.zona))


def a_utc(local):
    """Fecha y hora local (con zona) → UTC ingenuo."""
    return local.astimezone(UTC).replace(tzinfo=None)


def dia_js(local):
    """Día de la semana con 0 = domingo (lunes = 1 … sábado = 6)."""
    return (local.weekday() + 1) % 7


def float_a_hora(valor):
    """8.0 → 08:00 · 17.5 → 17:30 (formato ``float_time`` de Odoo)."""
    if valor is None or not 0 <= valor < 24:
        raise ValueError('La hora tiene que estar entre 0:00 y 23:59.')
    minutos = round(valor * 60)
    return time(minutos // 60, minutos % 60)


def hora_a_float(hora):
    return hora.hour + hora.minute / 60


def texto_hora(hora):
    return f'{hora.hour:02d}:{hora.minute:02d}'


MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre')


def texto_fecha_hora(utc, horario):
    """«viernes 9 de octubre de 2026, 9:03 a. m.» en la hora de Panamá, sin depender del idioma."""
    local = a_local(utc, horario)
    return (f'{NOMBRES_DIA[dia_js(local)]} {local.day} de {MESES[local.month - 1]} de {local.year}, '
            f'{texto_hora_amable(local.time())}')


def texto_hora_amable(hora):
    """08:00 → «8:00 a. m.» · 17:00 → «5:00 p. m.»"""
    sufijo = 'a. m.' if hora.hour < 12 else 'p. m.'
    h12 = hora.hour % 12 or 12
    return f'{h12}:{hora.minute:02d} {sufijo}'


def a_iso(utc):
    """UTC ingenuo → «2026-10-09T14:03:00Z» (el formato del contrato). ``None`` → ``None``."""
    return utc.replace(microsecond=0).isoformat() + 'Z' if utc else None


def de_iso(texto):
    """«2026-10-09T14:03:00Z» (o con desfase, p. ej. «-05:00») → UTC ingenuo. ``ValueError`` si no es una fecha.

    Una fecha sin zona se toma como UTC, que es lo que el contrato pide mandar.
    """
    if not isinstance(texto, str) or not 10 <= len(texto) <= 40:
        raise ValueError('Fecha inválida.')
    fecha = datetime.fromisoformat(texto.strip().replace('Z', '+00:00').replace('z', '+00:00'))
    if fecha.tzinfo is None:
        return fecha
    return fecha.astimezone(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Horario laboral
# ---------------------------------------------------------------------------

def dentro_de_horario(utc, horario):
    """¿Esta hora (UTC ingenuo) cae dentro del horario laboral? El fin no cuenta (17:00 ya es fuera)."""
    local = a_local(utc, horario)
    return dia_js(local) in horario.dias and horario.inicio <= local.time() < horario.fin


def siguiente_horario_laboral(utc, horario):
    """Primer instante ≥ ``utc`` que cae dentro del horario laboral (el mismo, si ya está dentro).

    ``None`` si no hay ningún día activo (nunca habría horario laboral).
    """
    if not horario.dias:
        return None
    if dentro_de_horario(utc, horario):
        return utc
    zona = cargar_zona(horario.zona)
    local = a_local(utc, horario)
    for desplazamiento in range(DIAS_MAX_BUSQUEDA + 1):
        fecha = local.date() + timedelta(days=desplazamiento)
        candidato = datetime.combine(fecha, horario.inicio, tzinfo=zona)
        if dia_js(candidato) in horario.dias and candidato >= local:
            return a_utc(candidato)
    return None   # inalcanzable con ``dias`` no vacío; por seguridad


def fecha_de_seguimiento(base, delta, horario, solo_horario_laboral=True):
    """``base + delta`` (UTC ingenuo); si debe caer en horario laboral y no cae, espera al siguiente."""
    objetivo = base + delta
    if not solo_horario_laboral:
        return objetivo
    return siguiente_horario_laboral(objetivo, horario)


def proximo_seguimiento(enviados, ultimo_mensaje, ultimo_seguimiento, regla, horario):
    """Cuándo toca el siguiente seguimiento, o ``None`` si ya no toca ninguno.

    * ``enviados == 0``: ``primero_horas`` después del último mensaje.
    * ``enviados == 1``: ``segundo_dias`` después del primer seguimiento.
    * ``enviados >= maximo``: ninguno.
    """
    if enviados >= regla.maximo or enviados < 0:
        return None
    if enviados == 0:
        if not ultimo_mensaje:
            return None
        return fecha_de_seguimiento(ultimo_mensaje, timedelta(hours=regla.primero_horas), horario,
                                    regla.solo_horario_laboral)
    base = ultimo_seguimiento or ultimo_mensaje
    if not base:
        return None
    return fecha_de_seguimiento(base, timedelta(days=regla.segundo_dias), horario, regla.solo_horario_laboral)


def cuando_atienden(utc, horario):
    """Frase para el cliente cuando pide una vendedora: dentro de horario, «ahora»; fuera, cuándo vuelven.

    Nunca promete una hora exacta: dice desde cuándo atienden.
    """
    if dentro_de_horario(utc, horario):
        return 'ahora'
    siguiente = siguiente_horario_laboral(utc, horario)
    if siguiente is None:
        return 'en cuanto el equipo vuelva a atender'
    local_actual = a_local(utc, horario)
    local_siguiente = a_local(siguiente, horario)
    desde = texto_hora_amable(horario.inicio)
    diferencia = (local_siguiente.date() - local_actual.date()).days
    if diferencia == 0:
        return f'hoy desde las {desde}'
    if diferencia == 1:
        return f'mañana a primera hora, desde las {desde}'
    return f'el {NOMBRES_DIA[dia_js(local_siguiente)]} desde las {desde}'


# ---------------------------------------------------------------------------
# Texto del cliente: ¿pidió que no lo contacten?
# ---------------------------------------------------------------------------

_PIDE_NO_CONTACTAR = re.compile(
    r'\b('
    r'no\s+(?:me\s+)?(?:vuelvas?|vuelvan)\s+a\s+(?:escribir|contactar|llamar|molestar)'
    r'|no\s+me\s+(?:escribas|escriban|contactes|contacten|llames|llamen|molestes|molesten|envies|envien|mandes|manden)'
    r'|(?:deja|dejan|deje|dejen|para|paran|pare|paren)\s+de\s+(?:escribir|contactar|molestar|enviar|mandar|llamar)(?:me)?'
    r'|dej(?:a|e|en)me(?:n)?\s+en\s+paz'
    r'|ya\s+no\s+(?:me\s+)?(?:escribas|escriban|contactes|contacten|molestes|molesten)'
    r'|no\s+quiero\s+(?:que\s+me\s+(?:escriban|escribas|contacten|contactes|llamen|llames)|mas\s+mensajes)'
    r'|no\s+(?:me\s+)?interesa\s+(?:que\s+me\s+)?(?:escriban|escribas|contacten|contactes)'
    r'|borra(?:n)?\s+mi\s+numero'
    r')\b')


def _sin_acentos(texto):
    texto = unicodedata.normalize('NFKD', (texto or '').lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


# «STOP» solo, como mensaje completo: la señal de baja que usa todo el mundo en WhatsApp y SMS.
_SOLO_STOP = re.compile(r'[\s¡!.¿?]*(?:stop|baja)[\s¡!.¿?]*')


def pide_no_contactar(texto):
    """True si el mensaje del cliente pide, sin rodeos, que no le escriban más.

    Es una red de seguridad determinista (la IA puede fallar): ante un falso positivo solo se
    deja de hacerle seguimiento, que es el lado seguro. La vendedora puede quitar la marca.
    """
    limpio = _sin_acentos(texto)
    return bool(_PIDE_NO_CONTACTAR.search(limpio) or _SOLO_STOP.fullmatch(limpio))
