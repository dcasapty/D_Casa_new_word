"""Cliente del Botón de Pago de Yappy y la comprobación del aviso firmado. Sin ORM: cada función se prueba sola.

Todo lo de aquí sale de la documentación oficial de Yappy transcrita en ``docs/YAPPY.md`` (§2). Lo que esa documentación
no dice **no se inventa**: queda marcado «por confirmar con Yappy» en ese documento.

Reglas que no se negocian:

* Las claves (``YAPPY_ID_COMERCIO``, ``YAPPY_CLAVE_SECRETA``; además el dominio ``YAPPY_DOMINIO`` y el entorno
  ``YAPPY_ENTORNO``, que no son secretos) se leen del entorno del contenedor EN EL MOMENTO de usarlas. Nunca van a la
  base, a un campo, a un log, a una respuesta ni a un mensaje de error: todo texto que viene de afuera pasa por
  ``limpiar``.
* El token que da Yappy dura lo que dura una petición: no se guarda en ninguna parte (su vigencia no está documentada).
* Tope de llamadas a Yappy AL MISMO TIEMPO (``cupo``): cada una retiene una conexión de la base y con ``workers = 0`` el
  grupo de conexiones es de TODA la tienda.
* Esta capa NO registra cuerpos de petición ni de respuesta: solo la ruta, el código HTTP y el código de Yappy.
* **Lo único que puede decir «pagado» es un aviso firmado** (``verificar_aviso``): hash HMAC-SHA256 en tiempo constante
  y dominio nuestro. Lo que diga el navegador (``eventSuccess``) jamás decide nada.
"""
import base64
import binascii
import contextlib
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from collections import namedtuple
from urllib.parse import urlsplit

import requests

_logger = logging.getLogger(__name__)

VARIABLE_ID = 'YAPPY_ID_COMERCIO'
VARIABLE_CLAVE = 'YAPPY_CLAVE_SECRETA'
VARIABLE_DOMINIO = 'YAPPY_DOMINIO'
VARIABLE_ENTORNO = 'YAPPY_ENTORNO'
VARIABLE_URL_BASE = 'YAPPY_URL_BASE'    # opcional, NO secreta: dirección pública del aviso (solo fuera de producción)
VARIABLE_SERVIDOR = 'DCASA_ENTORNO'     # lo fija el Worker: «produccion» o «staging» (sin ella: una máquina cualquiera)

PRUEBA = 'prueba'
PRODUCCION = 'produccion'

# El servidor y el componente del navegador cambian por entorno (no solo las claves). El host del componente que vale es
# el de la TABLA de Yappy; el que sale en su ejemplo de frontend (``bt-cdn.yappycloud.com``) no responde
# (docs/YAPPY.md).
HOSTS = {PRODUCCION: 'https://apipagosbg.bgeneral.cloud', PRUEBA: 'https://api-comecom-uat.yappycloud.com'}
CDNS = {
    PRODUCCION: 'https://bt-cdn.yappy.cloud/v1/cdn/web-component-btn-yappy.js',
    PRUEBA: 'https://bt-cdn-uat.yappycloud.com/v1/cdn/web-component-btn-yappy.js',
}
RUTA_AVISO = '/payment/yappy/ipn'     # nuestra ruta del aviso (IPN): la ``ipnUrl`` que se le manda a Yappy
RUTA_VALIDAR = '/payments/validate/merchant'
RUTA_ORDEN = '/payments/payment-wc'

TIEMPO_ESPERA = (5, 10)        # (conectar, leer) en segundos: corto a propósito, la tienda no se cuelga por Yappy
TOPE_DE_LLAMADAS_A_LA_VEZ = 6
MAX_RESPUESTA = 1_000_000      # bytes
LARGO_TEXTO = 200              # lo máximo que de un texto ajeno llega a un log o a una nota
LARGO_MAXIMO_ORDEN = 15

# Los cuatro finales del aviso. Solo ``E`` es un pago.
EJECUTADO = 'E'
RECHAZADO = 'R'
CANCELADO = 'C'
EXPIRADO = 'X'
ESTADOS = (EJECUTADO, RECHAZADO, CANCELADO, EXPIRADO)

RE_ORDEN = re.compile(r'[A-Za-z0-9]{1,15}', re.ASCII)
RE_HASH = re.compile(r'[0-9a-f]{64}')
RE_CODIGO_DE_YAPPY = re.compile(r'\b(E\d{3}|YAPPY-\d{3})\b')
RE_CELULAR = re.compile(r'[2-9][0-9]{7}')
RE_BASE64 = re.compile(r'[A-Za-z0-9+/_-]+={0,2}')


class Credenciales(namedtuple('Credenciales', 'id_comercio clave dominio')):
    """El ID de comercio, la clave secreta y el dominio declarado. Imprimirla (log, traza, depurador) NO los muestra."""
    __slots__ = ()

    def __repr__(self):
        return 'Credenciales(***)'

    __str__ = __repr__

    def secretos(self):
        return [valor for valor in (self.id_comercio, self.clave) if valor]


class ErrorYappy(Exception):
    """Algo falló al hablar con Yappy. ``tipo``: ``red`` | ``respuesta`` | ``comercio`` | ``rechazo`` | ``ya_estaba``
    | ``ocupado`` (no se intentó: ya hay demasiadas llamadas a la vez). ``codigo``: el código de error de Yappy
    (``E005``…) si lo dijo. El texto ya viene limpio: es seguro mostrarlo en un log."""

    def __init__(self, tipo, detalle='', codigo=None):
        super().__init__(f'{tipo}: {detalle}' if detalle else tipo)
        self.tipo = tipo
        self.detalle = detalle
        self.codigo = codigo


def limpiar(texto, secretos=()):
    """Un texto que viene de afuera, listo para un log o una nota: sin saltos de línea, sin ninguna clave conocida, sin
    nada que parezca un token (cadenas largas de letras y números) y recortado."""
    texto = '' if texto is None else str(texto)
    for secreto in secretos:
        if secreto and len(secreto) >= 4:
            texto = texto.replace(secreto, '***')
    texto = re.sub(r'[A-Za-z0-9_\-+/=.]{32,}', '[…]', texto)
    texto = re.sub(r'[\r\n\t]+', ' ', texto).strip()
    return texto[:LARGO_TEXTO]


# ------------------------------------------------------------------ lo que dice el entorno

def _variable(nombre):
    return (os.environ.get(nombre) or '').strip()


def secreto_valido(clave):
    """¿La clave secreta tiene la forma que dice la documentación (base64 que, decodificado, trae al menos un trozo
    antes del primer punto)? No dice si Yappy la acepta."""
    return bool(_llave_del_hash(clave))


def credenciales():
    """``Credenciales`` del entorno, o ``None`` si falta cualquiera de las tres o la clave no tiene la forma
    esperada."""
    valores = [_variable(VARIABLE_ID), _variable(VARIABLE_CLAVE), _variable(VARIABLE_DOMINIO)]
    if not all(valores) or not secreto_valido(valores[1]):
        return None
    return Credenciales(*valores)


def faltantes():
    """Los nombres de las variables que faltan (o la clave que no tiene la forma esperada). Nunca un valor."""
    falta = [nombre for nombre in (VARIABLE_ID, VARIABLE_CLAVE, VARIABLE_DOMINIO) if not _variable(nombre)]
    if _variable(VARIABLE_CLAVE) and not secreto_valido(_variable(VARIABLE_CLAVE)):
        falta.append(f'{VARIABLE_CLAVE} (no tiene la forma que da Yappy)')
    return falta


def servidor_es_produccion():
    """¿Este servidor es el de producción? Solo ``DCASA_ENTORNO=produccion`` lo dice (la misma regla de Tilopay, de los
    correos y de Meta): una copia en una máquina, o el staging, nunca aceptan dinero real aunque alguien pegue
    «produccion»."""
    return _variable(VARIABLE_SERVIDOR).lower() == 'produccion'


def entorno_pedido():
    """Lo que dice ``YAPPY_ENTORNO`` (``'prueba'`` o ``'produccion'``), sin mirar en qué servidor estamos."""
    return PRODUCCION if _variable(VARIABLE_ENTORNO).lower() in ('produccion', 'producción', 'real') else PRUEBA


def entorno_esperado():
    """``'prueba'`` o ``'produccion'``. Sin variable o con un valor raro: ``'prueba'`` (lo seguro). ``'produccion'``
    exige las DOS cosas: que ``YAPPY_ENTORNO`` lo diga y que este servidor sea el de producción."""
    return PRODUCCION if entorno_pedido() == PRODUCCION and servidor_es_produccion() else PRUEBA


def host(entorno=None):
    return HOSTS[entorno or entorno_esperado()]


def cdn(entorno=None):
    return CDNS[entorno or entorno_esperado()]


def anfitrion_del_cdn_permitido(url):
    """Solo los dos anfitriones de Yappy (producción y pruebas), por https: nadie nos hace cargar otro script."""
    try:
        partes = urlsplit(url)
    except (ValueError, AttributeError):
        return False
    return partes.scheme == 'https' and f'https://{partes.hostname}{partes.path}' in CDNS.values()


# ------------------------------------------------------------------ a dónde avisa Yappy

# Una etiqueta de dominio (letras, números y guiones, sin empezar ni acabar en guion) y el anfitrión que las junta con
# puntos.
_RE_ETIQUETA = r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?'
RE_URL_BASE = re.compile(
    rf'https://(?P<anfitrion>{_RE_ETIQUETA}(?:\.{_RE_ETIQUETA})+)(?::(?P<puerto>[1-9][0-9]{{0,4}}))?/?',
    re.IGNORECASE | re.ASCII)


def url_base_del_aviso(base_web):
    """La dirección pública (``https://anfitrion``) con la que se arma la ``ipnUrl``: la de ``YAPPY_URL_BASE`` si está
    y es una dirección https limpia (anfitrión y puerto, sin usuario, ruta, consulta ni espacios), y si no,
    ``base_web`` (el ``web.base.url`` de Odoo). Existe para staging: su dominio propio todavía no apunta al Worker, y
    a Yappy se le puede dar la dirección ``workers.dev`` del Worker de staging. En el servidor de PRODUCCIÓN se ignora
    siempre: allí el aviso va a la dirección canónica del sitio (un valor mal puesto dejaría a Yappy avisando a otro
    lado)."""
    propia = _variable(VARIABLE_URL_BASE)
    if not propia:
        return base_web
    if servidor_es_produccion():
        _logger.warning('Yappy: %s se ignora en el servidor de producción (el aviso va a la dirección canónica).',
                        VARIABLE_URL_BASE)
        return base_web
    partes = RE_URL_BASE.fullmatch(propia)
    if partes is None:
        _logger.warning('Yappy: %s no es una dirección https limpia (solo anfitrión y puerto): se ignora.',
                        VARIABLE_URL_BASE)
        return base_web
    puerto = partes.group('puerto')
    return f"https://{partes.group('anfitrion').lower()}{f':{puerto}' if puerto and puerto != '443' else ''}"


# ------------------------------------------------------------------ el dominio

# Una manera de escribir un dominio que Yappy podría devolver: ``[http://|https://][www.]anfitrion[:puerto][/…]``, sin
# distinguir mayúsculas de minúsculas (solo ASCII: ``re.ASCII`` evita que letras raras como la «K» del signo Kelvin
# pasen por una «k»). Lo que NO cabe aquí no es de ninguno de los dos: espacios, tabuladores, saltos de línea, ``@``
# (usuario antes del anfitrión), ``?``, ``#``, ``%``, un trozo de ruta con letras, ``..`` o un subdominio que no sea
# ``www``.
_RE_ANFITRION = rf'{_RE_ETIQUETA}(?:\.{_RE_ETIQUETA})*'
RE_DOMINIO = re.compile(
    rf'(?P<esquema>https?://)?(?P<www>www\.)?(?P<anfitrion>{_RE_ANFITRION})(?::(?P<puerto>[1-9][0-9]{{0,4}}))?/*',
    re.IGNORECASE | re.ASCII)
# El puerto que se puede omitir: el de https (443) o el de http (80); sin esquema, cualquiera de los dos.
PUERTOS_POR_DEFECTO = {'http://': ('80',), 'https://': ('443',), '': ('443', '80')}


def _anfitrion(dominio):
    """``https://www.dcasapty.com/tienda`` → ``dcasapty.com`` (sin esquema, sin ``www``, sin ruta). Lo que se declaró en
    Yappy Comercial, reducido al anfitrión; solo para el dominio DECLARADO por nosotros (el que llega se normaliza con
    ``normalizar_dominio``, que no perdona nada raro)."""
    texto = (dominio or '').strip()
    texto = re.sub(r'^[A-Za-z][A-Za-z0-9+.-]*://', '', texto)
    texto = texto.split('/')[0].split('?')[0].split('#')[0]
    if texto.lower().startswith('www.'):
        texto = texto[4:]
    return texto


def normalizar_dominio(texto):
    """La forma canónica de un dominio (``dcasapty.com``), o ``None`` si lo que llegó no es un dominio escrito de una de
    las maneras conocidas: con o sin ``http://`` o ``https://``, con o sin ``www.``, en mayúsculas o minúsculas, con el
    puerto por defecto (``:443``, o ``:80`` con ``http://``) y con barras al final. Cualquier otra cosa (un usuario
    antes del ``@``, un subdominio, una ruta, un espacio, otra letra) da ``None``: no se adivina."""
    if not isinstance(texto, str) or not texto or len(texto) > 253:
        return None
    partes = RE_DOMINIO.fullmatch(texto)
    if partes is None:
        return None
    esquema = (partes.group('esquema') or '').lower()
    anfitrion = partes.group('anfitrion').lower()
    puerto = partes.group('puerto')
    if puerto is not None and puerto not in PUERTOS_POR_DEFECTO[esquema]:
        return f'{anfitrion}:{puerto}'
    return anfitrion


def dominio_nuestro(declarado, recibido):
    """¿El dominio que llegó en el aviso es el NUESTRO (el declarado en Yappy Comercial)? Sí si es EXACTAMENTE el
    declarado (tal cual) o si, escrito de cualquiera de las maneras que acepta ``normalizar_dominio``, es el mismo
    anfitrión. Un dominio ajeno no entra nunca: la comparación es de igualdad, en tiempo constante. Quien firma el aviso
    es Yappy y su documentación no dice si devuelve el dominio como se declaró o normalizado."""
    if not isinstance(recibido, str):
        return False
    declarado = (declarado or '').strip()
    propio = normalizar_dominio(_anfitrion(declarado))
    if not propio:
        return False
    iguales = hmac.compare_digest(declarado.encode('utf-8'), recibido.encode('utf-8', errors='replace'))
    normalizado = normalizar_dominio(recibido)
    if normalizado is None:
        return iguales
    return hmac.compare_digest(normalizado.encode('ascii'), propio.encode('ascii')) or iguales


# ------------------------------------------------------------------ la orden de Yappy (1 a 15 letras y números)

def orden_valida(texto):
    """La orden si es un texto de 1 a 15 letras y números (ASCII); si no, ``None``."""
    if not isinstance(texto, str):
        return None
    return texto if RE_ORDEN.fullmatch(texto) else None


def orden_nueva(referencia_del_pedido, azar=secrets):
    """Una orden que Yappy acepta: el **número del pedido** de Odoo DELANTE (es lo que ve quien mira el reporte de Yappy
    Comercial, y puede ir directo al pedido) y letras y números al azar detrás, que son lo que la hace única: un
    reintento nunca choca con el intento anterior. Todo en mayúsculas y sin guiones (que es lo que cabe en
    «alfanumérico»). Si el pedido es largo, lo que se recorta es el pedido, nunca el azar."""
    base = re.sub(r'[^A-Za-z0-9]', '', referencia_del_pedido or '').upper()
    sufijo = ''.join(azar.choice('0123456789ABCDEFGHJKLMNPQRSTUVWXYZ') for _i in range(5))
    return f'{base[:LARGO_MAXIMO_ORDEN - len(sufijo)]}{sufijo}'


# ------------------------------------------------------------------ el celular de Yappy de la clienta

def celular_de_yappy(texto):
    """El celular de Panamá sin prefijo (8 números), o ``None``. Acepta espacios, guiones, paréntesis y el prefijo +507,
    507 o 00507. Lo mínimo que se exige es la forma (8 números que no empiezan en 0 ni en 1): si no está registrado en
    Yappy, es Yappy quien lo dice (E005) y se le explica a la persona."""
    if not isinstance(texto, str) or len(texto) > 40:
        return None
    digitos = re.sub(r'[\s\-().]', '', texto)
    for prefijo in ('+507', '00507', '507'):
        if digitos.startswith(prefijo) and len(digitos) == len(prefijo) + 8:
            digitos = digitos[len(prefijo):]
            break
    return digitos if RE_CELULAR.fullmatch(digitos) else None


def importe(monto):
    """Un importe como lo pide Yappy: cadena con dos decimales («64.19»)."""
    return f'{monto:.2f}'


# ------------------------------------------------------------------ el hash del aviso

def _llave_del_hash(clave_secreta):
    """La llave del HMAC: la clave secreta viene en base64; se decodifica a texto, se parte por el punto y se usa SOLO
    el primer trozo. ``b''`` si la clave no se puede leer (no es base64, o no deja ningún trozo antes del primer
    punto). Se acepta el alfabeto de siempre y el de las direcciones web (``-`` y ``_``), con o sin el relleno
    ``=``."""
    if not isinstance(clave_secreta, str):
        return b''
    crudo = clave_secreta.strip()
    if not RE_BASE64.fullmatch(crudo):
        return b''
    sin_relleno = crudo.rstrip('=').replace('-', '+').replace('_', '/')
    try:
        decodificada = base64.b64decode(sin_relleno + '=' * (-len(sin_relleno) % 4))
    except (binascii.Error, ValueError):
        return b''
    # Como el ejemplo oficial de Node: ``Buffer.from(clave, 'base64').toString('utf-8')``.
    texto = decodificada.decode('utf-8', errors='replace')
    return texto.split('.')[0].encode('utf-8')


def firma_del_aviso(clave_secreta, orden, estado, dominio):
    """La firma que Yappy manda en el aviso: HMAC-SHA256, en hexadecimal minúsculas, de ``orden + estado + dominio``
    pegados sin separadores y en ese orden, con la llave que sale de ``_llave_del_hash``."""
    llave = _llave_del_hash(clave_secreta)
    mensaje = f'{orden}{estado}{dominio}'.encode()
    return hmac.new(llave, mensaje, hashlib.sha256).hexdigest()


# Lo que sale de un aviso bien firmado. Solo se crea en ``verificar_aviso``.
Aviso = namedtuple('Aviso', 'orden estado confirmacion')

# Por qué ``verificar_aviso`` dice que no. Solo para los registros y las pruebas: a quien llama no se le dice.
RECHAZO_FORMA = 'forma'
RECHAZO_ESTADO = 'estado'
RECHAZO_DOMINIO = 'dominio'
RECHAZO_FIRMA = 'firma'
RECHAZO_SIN_CLAVES = 'sin_claves'
# Los que dejan rastro en la transacción de esa orden (si existe): puede ser un aviso REAL que no se pudo aceptar (el
# dominio escrito de otra forma, la clave mal pegada, las claves que faltan) y a quien opera le tiene que constar.
RECHAZOS_CON_RASTRO = (RECHAZO_DOMINIO, RECHAZO_FIRMA, RECHAZO_SIN_CLAVES)


def verificar_aviso(creds, parametros):
    """``(Aviso, None)`` si el aviso es de verdad; ``(None, motivo)`` si no. ES LO ÚNICO QUE PUEDE DAR UN PAGO.

    Orden de las comprobaciones (ninguna se salta):

    1. La forma: ``orderId`` (1 a 15 letras y números), ``status``, ``domain`` y ``hash`` son texto.
    2. El estado es uno de E, R, C, X (se acepta en minúscula y con espacios).
    3. El dominio es EL NUESTRO (``dominio_nuestro``: el declarado tal cual, o el mismo anfitrión escrito con o sin
       ``http://``/``https://``, con o sin ``www.``, en mayúsculas o minúsculas, con el puerto por defecto y con
       barras al final), y va ANTES del hash: el hash se calcula sobre el dominio que venga en la dirección, así que
       sin esto bastaría firmar un aviso para otro dominio y la firma cuadraría consigo misma. Lo que se firma después
       es el dominio como llegó, ya comprobado. 4. La firma, en TIEMPO CONSTANTE (``hmac.compare_digest``): un ``==``
       filtra, por lo que tarda, cuánto del hash acertó quien lo intenta. El hash se acepta en mayúsculas y con
       espacios alrededor.

    ``confirmationNumber`` no es un parámetro documentado y **no está firmado**: se devuelve limpio y solo sirve para
    mirarlo, nunca para decidir.
    """
    if creds is None:
        return None, RECHAZO_SIN_CLAVES
    if not isinstance(parametros, dict):
        return None, RECHAZO_FORMA
    orden, estado, dominio, hash_recibido = (
        parametros.get(nombre) for nombre in ('orderId', 'status', 'domain', 'hash'))
    if not all(isinstance(valor, str) for valor in (orden, estado, dominio, hash_recibido)):
        return None, RECHAZO_FORMA
    if len(dominio) > 253 or len(hash_recibido) > 200 or len(estado) > 10 or not orden_valida(orden):
        return None, RECHAZO_FORMA
    estado = estado.strip().upper()
    if estado not in ESTADOS:
        return None, RECHAZO_ESTADO
    if not dominio_nuestro(creds.dominio, dominio):
        return None, RECHAZO_DOMINIO
    # Se firma el dominio TAL COMO LLEGÓ (así lo hacen los cuatro ejemplos oficiales): ya se comprobó que es el
    # nuestro y que tiene una forma acotada (solo letras, números, puntos, guiones, el esquema, el puerto por defecto
    # y barras).
    esperada = firma_del_aviso(creds.clave, orden, estado, dominio)
    recibida = hash_recibido.strip().lower()
    if not RE_HASH.fullmatch(recibida) or not hmac.compare_digest(recibida.encode('ascii'), esperada.encode('ascii')):
        return None, RECHAZO_FIRMA
    confirmacion = parametros.get('confirmationNumber')
    return Aviso(orden, estado, limpiar(confirmacion) if isinstance(confirmacion, (str, int)) else ''), None


def _dominio_para_el_registro(valor, secretos=()):
    """Un dominio (que llegó o que se declaró) listo para un registro: se ve COMPLETO (``limpiar`` taparía uno largo
    como si fuera un token y es justo lo que hace falta ver), sin caracteres de control ni claves conocidas y
    recortado."""
    texto = '' if valor is None else str(valor)
    for secreto in secretos:
        if secreto and len(secreto) >= 4:
            texto = texto.replace(secreto, '***')
    texto = ''.join(letra if letra.isprintable() else '?' for letra in texto)
    return texto[:100]


def describir_rechazo(creds, parametros, motivo):
    """Una frase corta y LIMPIA (sin claves, sin la firma recibida) de por qué se rechazó un aviso, para el registro del
    servidor y para la transacción de esa orden. Si fue por el dominio, dice cuál llegó y cuál está declarado, para que
    quien opera vea la diferencia (por ejemplo ``http://`` o una letra) sin adivinar."""
    secretos = creds.secretos() if creds is not None else ()
    if motivo == RECHAZO_DOMINIO:
        llego = _dominio_para_el_registro(parametros.get('domain') if isinstance(parametros, dict) else '', secretos)
        declarado = _dominio_para_el_registro(creds.dominio if creds is not None else '', secretos)
        return f'dominio: llegó «{llego}» y el declarado en YAPPY_DOMINIO es «{declarado}»'
    if motivo == RECHAZO_FIRMA:
        return 'firma: no coincide (revisa que YAPPY_CLAVE_SECRETA sea la de este botón)'
    if motivo == RECHAZO_SIN_CLAVES:
        return 'faltan las claves de Yappy en el servidor'
    return motivo


# ------------------------------------------------------------------ el tope de llamadas a la vez

_CUPO = {'en_vuelo': 0}
_CANDADO_CUPO = threading.Lock()


def llamadas_en_vuelo():
    return _CUPO['en_vuelo']


def hay_cupo():
    with _CANDADO_CUPO:
        return _CUPO['en_vuelo'] < TOPE_DE_LLAMADAS_A_LA_VEZ


@contextlib.contextmanager
def cupo():
    """Reserva un lugar para UNA llamada a Yappy mientras dura el ``with``; si el tope está lleno NO espera: lanza
    ``ErrorYappy('ocupado')`` y la llamada ni se intenta. Se suelta siempre, pase lo que pase."""
    with _CANDADO_CUPO:
        if _CUPO['en_vuelo'] >= TOPE_DE_LLAMADAS_A_LA_VEZ:
            raise ErrorYappy('ocupado', 'demasiadas llamadas a Yappy a la vez')
        _CUPO['en_vuelo'] += 1
    try:
        yield
    finally:
        with _CANDADO_CUPO:
            _CUPO['en_vuelo'] -= 1


# ------------------------------------------------------------------ el cliente HTTP

def _texto(valor):
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return str(valor)
    return None


def _codigo_de_error(cuerpo):
    """El código de error de Yappy (``E005``…) si algún texto de su respuesta lo trae. En qué campo llega no está
    documentado: se mira ``status.code`` y ``status.description`` (y lo de nivel superior) buscando la forma del
    código."""
    if not isinstance(cuerpo, dict):
        return None
    estado = cuerpo.get('status') if isinstance(cuerpo.get('status'), dict) else {}
    for candidato in (estado.get('code'), estado.get('description'), cuerpo.get('code'), cuerpo.get('message')):
        encontrado = RE_CODIGO_DE_YAPPY.search(str(candidato)) if candidato is not None else None
        if encontrado:
            return encontrado.group(1)
    return None


class Cliente:
    """Habla con el servidor de Yappy del entorno. Un fallo es ``ErrorYappy``; nunca se registran cuerpos."""

    def __init__(self, creds, entorno=None):
        self._creds = creds
        self._entorno = entorno or entorno_esperado()

    def _post(self, ruta, cuerpo, token=None):
        cabeceras = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            # el token solo, sin «Bearer» (como el ejemplo; por confirmar con Yappy)
            cabeceras['Authorization'] = token
        inicio = time.monotonic()
        try:
            with cupo():
                respuesta = requests.post(host(self._entorno) + ruta, json=cuerpo, headers=cabeceras,
                                          timeout=TIEMPO_ESPERA)
        except requests.exceptions.Timeout:
            _logger.warning('Yappy %s: tiempo agotado (%.1f s).', ruta, time.monotonic() - inicio)
            raise ErrorYappy('red', 'tiempo agotado') from None
        except requests.exceptions.RequestException as error:
            _logger.warning('Yappy %s: sin conexión (%s).', ruta, type(error).__name__)
            raise ErrorYappy('red', 'sin conexión') from None
        _logger.info('Yappy %s: HTTP %s en %.1f s.', ruta, respuesta.status_code, time.monotonic() - inicio)
        if len(respuesta.content or b'') > MAX_RESPUESTA:
            raise ErrorYappy('respuesta', 'demasiado grande')
        try:
            datos = respuesta.json()
        except ValueError:
            raise ErrorYappy('respuesta', f'no es JSON (HTTP {respuesta.status_code})') from None
        if not isinstance(datos, dict):
            raise ErrorYappy('respuesta', 'la respuesta no es un objeto')
        return respuesta.status_code, datos

    def _cuerpo(self, datos):
        cuerpo = datos.get('body')
        return cuerpo if isinstance(cuerpo, dict) else {}

    def _describir(self, estado_http, datos):
        """Una frase corta (limpia, sin claves) de lo que dijo Yappy, para el registro."""
        estado = datos.get('status') if isinstance(datos.get('status'), dict) else {}
        return limpiar(f"HTTP {estado_http} {estado.get('code', '')} {estado.get('description', '')}",
                       self._creds.secretos())

    def validar_comercio(self):
        """Paso 1: ``POST /payments/validate/merchant`` → el token de sesión. Falla con ``comercio`` si Yappy no valida
        el ID de comercio y el dominio (lo más común: el dominio no es letra por letra el de Yappy Comercial)."""
        estado, datos = self._post(RUTA_VALIDAR, {'merchantId': self._creds.id_comercio,
                                                  'urlDomain': self._creds.dominio})
        token = _texto(self._cuerpo(datos).get('token'))
        if estado >= 400 or token is None or len(token) > 8192:
            raise ErrorYappy('comercio', self._describir(estado, datos), codigo=_codigo_de_error(datos))
        return token

    def crear_orden(self, orden, celular, total, url_del_aviso):
        """Pasos 1 y 2: valida el comercio y crea la orden. Devuelve ``{'transactionId', 'token', 'documentName'}`` (los
        tres que se le pasan al botón; ninguno es secreto: la clave secreta no sale de aquí).

        ``E007`` («el pedido ya ha sido registrado») es ``ya_estaba``, no un fallo: la orden existe en Yappy aunque no
        tengamos con qué abrirle el botón a la clienta."""
        if not orden_valida(orden):
            raise ErrorYappy('rechazo', 'la orden no es de 1 a 15 letras y números', codigo='E009')
        if not celular_de_yappy(celular):
            raise ErrorYappy('rechazo', 'el celular no es de Panamá', codigo='E005')
        if not (isinstance(total, str) and re.fullmatch(r'[0-9]+\.[0-9]{2}', total) and float(total) >= 0.01):
            raise ErrorYappy('rechazo', 'el total no es un importe válido (mínimo 0.01)', codigo='E010')
        token = self.validar_comercio()
        # El orden de los campos es el de la documentación; los importes, cadenas con dos decimales.
        cuerpo = {
            'merchantId': self._creds.id_comercio,
            'orderId': orden,
            'domain': self._creds.dominio,
            # segundos desde 1970 (si son segundos o milisegundos: por confirmar)
            'paymentDate': int(time.time()),
            'aliasYappy': celular,
            'ipnUrl': url_del_aviso,
            'discount': '0.00',
            'taxes': '0.00',
            'subtotal': total,       # el envío, el descuento y el ITBMS ya están dentro del total del pedido
            'total': total,
        }
        estado, datos = self._post(RUTA_ORDEN, cuerpo, token=token)
        cuerpo_respuesta = self._cuerpo(datos)
        resultado = {
            nombre: _texto(cuerpo_respuesta.get(nombre)) for nombre in ('transactionId', 'token', 'documentName')}
        if estado < 400 and all(resultado.values()):
            return resultado
        codigo = _codigo_de_error(datos)
        if codigo == 'E007':
            raise ErrorYappy('ya_estaba', 'Yappy ya tenía esa orden', codigo=codigo)
        raise ErrorYappy('rechazo', self._describir(estado, datos), codigo=codigo)
