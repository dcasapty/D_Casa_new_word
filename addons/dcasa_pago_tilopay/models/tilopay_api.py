"""Cliente de la API de Tilopay y la decisión de «¿este pago es de verdad?». Sin ORM: cada función se prueba sola.

Reglas que no se negocian (docs/TILOPAY.md):

* Las claves (``TILOPAY_API_KEY``, ``TILOPAY_API_USER``, ``TILOPAY_API_PASSWORD``) se leen del entorno del contenedor
  EN EL MOMENTO de usarlas. Nunca van a la base, a un campo, a un log, a una respuesta ni a un mensaje de error: todo
  texto que viene de afuera (o va hacia un log) pasa por ``limpiar``.
* El token de Tilopay vive solo en la memoria del proceso (``_TOKENS``), con su vencimiento.
* Esta capa NO registra cuerpos de petición ni de respuesta: solo la ruta y el código HTTP.
* Un fallo de red, un tiempo agotado o una respuesta rara es ``ErrorTilopay``: quien llama deja la transacción
  pendiente. Nunca se deduce «pagado» de un error.
* Lo único que puede decir «pagado» es ``evaluar_consulta``: una fila **aprobada** de ``consult`` con la orden que
  guardamos, el monto y la moneda exactos del pedido y el entorno que esperamos.
"""
import base64
import binascii
import hashlib
import logging
import math
import os
import re
import threading
import time
from collections import namedtuple
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests

_logger = logging.getLogger(__name__)

VARIABLE_LLAVE = 'TILOPAY_API_KEY'
VARIABLE_USUARIO = 'TILOPAY_API_USER'
VARIABLE_CLAVE = 'TILOPAY_API_PASSWORD'
VARIABLE_ENTORNO = 'TILOPAY_ENTORNO'

HOST = 'https://app.tilopay.com'
RUTA_LOGIN = '/api/v1/login'
RUTA_PAGO = '/api/v1/processPayment'
RUTA_CONSULTA = '/api/v1/consult'

TIEMPO_ESPERA = (5, 10)        # (conectar, leer) en segundos: corto a propósito, la tienda no se cuelga por Tilopay
MAX_RESPUESTA = 1_000_000      # bytes
LARGO_TEXTO = 200              # lo máximo que de un texto ajeno llega a un log o a una nota

PRUEBA = 'prueba'
PRODUCCION = 'produccion'

# Lo que Tilopay llama a cada entorno en ``consult`` (el ejemplo oficial dice «Test»; el otro, «Production», sale de
# ``consultTransactions``). Todo lo demás se trata como desconocido y NO paga (docs/TILOPAY.md §8, punto 5).
ENTORNOS_PRUEBA = frozenset({'test', 'prueba', 'pruebas', 'sandbox'})
ENTORNOS_REAL = frozenset({'production', 'produccion', 'producción', 'prod'})
CAPTURA_VALIDA = frozenset({'capture', 'captura', 'captured', 'capturado'})

# La orden que mandamos y recibimos: letras, números y guion (la hacemos nosotros).
RE_ORDEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{5,63}$')

_CLAVES_DE_ORDEN = ('orderNumber', 'order_number', 'ordernumber', 'orden', 'order')
_ENVOLTURAS = ('data', 'response', 'payload', 'transaction')

# Veredictos de ``evaluar_consulta``.
APROBADO = 'aprobado'
RECHAZADO = 'rechazado'          # hay intentos y ninguno aprobado
SIN_REGISTRO = 'sin_registro'    # Tilopay no tiene (todavía) esa orden
MONTO = 'monto'
MONEDA = 'moneda'
ENTORNO = 'entorno'              # aprobado, pero de prueba en producción (o al revés), o entorno desconocido
CAPTURA = 'captura'              # aprobado pero no capturado
AMBIGUO = 'ambiguo'              # varias aprobadas, o reembolsos/reversos: lo mira una persona
INVALIDO = 'invalido'            # la respuesta no tiene la forma esperada

# Estos veredictos NO cambian el estado de la transacción (se queda como está y se anota).
VEREDICTOS_SIN_CAMBIO = frozenset({SIN_REGISTRO, ENTORNO, CAPTURA, AMBIGUO, INVALIDO})


class Credenciales(namedtuple('Credenciales', 'llave usuario clave')):
    """Las tres claves. Imprimirla (log, traza, depurador) NO las muestra."""
    __slots__ = ()

    def __repr__(self):
        return 'Credenciales(***)'

    __str__ = __repr__

    def secretos(self):
        return [valor for valor in self if valor]


class ErrorTilopay(Exception):
    """Algo falló al hablar con Tilopay. ``tipo``: ``red`` | ``claves`` | ``respuesta`` | ``rechazo``. El texto ya viene
    limpio: es seguro mostrarlo en un log."""

    def __init__(self, tipo, detalle=''):
        super().__init__(f'{tipo}: {detalle}' if detalle else tipo)
        self.tipo = tipo
        self.detalle = detalle


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


def credenciales():
    """``Credenciales`` del entorno, o ``None`` si falta cualquiera de las tres."""
    valores = [(os.environ.get(nombre) or '').strip()
               for nombre in (VARIABLE_LLAVE, VARIABLE_USUARIO, VARIABLE_CLAVE)]
    return Credenciales(*valores) if all(valores) else None


def entorno_esperado():
    """``'prueba'`` o ``'produccion'``, según ``TILOPAY_ENTORNO``. Sin variable o con un valor raro: ``'prueba'``
    (lo seguro: un pago real no se acepta y uno de prueba nunca paga producción)."""
    valor = (os.environ.get(VARIABLE_ENTORNO) or '').strip().lower()
    return PRODUCCION if valor in ENTORNOS_REAL or valor == 'real' else PRUEBA


def entorno_de(texto):
    """Lo que Tilopay dice (``'Test'``, ``'Production'``) como ``'prueba'`` | ``'produccion'`` | ``None``."""
    valor = (str(texto or '')).strip().lower()
    if valor in ENTORNOS_PRUEBA:
        return PRUEBA
    if valor in ENTORNOS_REAL:
        return PRODUCCION
    return None


# ------------------------------------------------------------------ formas de lo que llega por el navegador

def orden_valida(texto):
    """La orden si tiene la forma de las nuestras; si no, ``None``. Antes de buscar nada en la base."""
    if not isinstance(texto, str):
        return None
    texto = texto.strip()
    return texto if RE_ORDEN.match(texto) else None


def extraer_orden(parametros):
    """La orden que menciona un retorno o un aviso (un diccionario de texto o JSON), o ``None``.

    Solo sirve para saber QUÉ orden revisar; nada de lo que traiga decide un pago. Mira el primer nivel y una envoltura
    (``data``, ``response``…) porque la forma del aviso de compras no es pública (docs/TILOPAY.md §8). Si trae dos
    órdenes distintas no se adivina: ``None``.
    """
    encontradas = set()

    def mirar(diccionario):
        for clave in _CLAVES_DE_ORDEN:
            for llave, valor in diccionario.items():
                if isinstance(llave, str) and llave.lower() == clave.lower():
                    orden = orden_valida(valor) if isinstance(valor, str) else (
                        orden_valida(str(valor)) if isinstance(valor, int) and not isinstance(valor, bool) else None)
                    if orden:
                        encontradas.add(orden)

    if not isinstance(parametros, dict):
        return None
    mirar(parametros)
    for envoltura in _ENVOLTURAS:
        interior = parametros.get(envoltura)
        if isinstance(interior, dict):
            mirar(interior)
    return encontradas.pop() if len(encontradas) == 1 else None


def orden_de_return_data(texto):
    """``returnData`` (lo mandamos en base64) devuelto a texto, o ``None``."""
    if not isinstance(texto, str) or not texto or len(texto) > 200:
        return None
    try:
        crudo = base64.b64decode(texto + '=' * (-len(texto) % 4), validate=False)
        return orden_valida(crudo.decode('ascii'))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None


def codificar_return_data(orden):
    return base64.b64encode(orden.encode('ascii')).decode('ascii')


def url_de_pago_valida(url):
    """La dirección de la página de pago solo se acepta si es ``https`` de un anfitrión de ``tilopay.com``: Odoo manda
    al cliente a donde diga esta respuesta, y no debe poder mandarlo a otro sitio."""
    try:
        partes = urlsplit(url)
    except (ValueError, AttributeError):
        return False
    anfitrion = (partes.hostname or '').lower()
    return (partes.scheme == 'https' and not partes.username and not partes.password
            and (anfitrion == 'tilopay.com' or anfitrion.endswith('.tilopay.com')))


def verificar_hash(order_hash, **datos):
    """HUECO (docs/TILOPAY.md §5.4). El algoritmo de ``OrderHash`` no es público: Tilopay lo entrega por Soporte.
    Hasta entonces la firma NO se puede comprobar y esto lo dice con ``None``; la defensa es ``consult``. Cuando llegue
    el algoritmo se programa aquí con ``hmac.compare_digest`` y se suma como una comprobación MÁS, nunca en lugar de la
    consulta."""
    return None


# ------------------------------------------------------------------ el cliente HTTP

_TOKENS = {}                # huella de las claves → (token, vence en time.monotonic())
_CANDADO = threading.Lock()
VIDA_MAXIMA_TOKEN = 12 * 3600
VIDA_MINIMA_TOKEN = 60


def _huella(creds):
    return hashlib.sha256('\0'.join((creds.usuario, creds.clave)).encode()).hexdigest()


def olvidar_tokens():
    """Vacía la memoria de tokens (pruebas, y si se cambian las claves)."""
    with _CANDADO:
        _TOKENS.clear()


class Cliente:
    """Habla con ``app.tilopay.com``. Un fallo es ``ErrorTilopay``; nunca se registran cuerpos."""

    def __init__(self, creds):
        self._creds = creds

    # -- bajo nivel

    def _post(self, ruta, cuerpo, con_token=True, reintentar=True):
        cabeceras = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if con_token:
            cabeceras['Authorization'] = 'bearer ' + self._token()
        inicio = time.monotonic()
        try:
            respuesta = requests.post(HOST + ruta, json=cuerpo, headers=cabeceras, timeout=TIEMPO_ESPERA)
        except requests.exceptions.Timeout:
            _logger.warning('Tilopay %s: tiempo agotado (%.1f s).', ruta, time.monotonic() - inicio)
            raise ErrorTilopay('red', 'tiempo agotado') from None
        except requests.exceptions.RequestException as error:
            _logger.warning('Tilopay %s: sin conexión (%s).', ruta, type(error).__name__)
            raise ErrorTilopay('red', 'sin conexión') from None
        _logger.info('Tilopay %s: HTTP %s en %.1f s.', ruta, respuesta.status_code, time.monotonic() - inicio)
        if respuesta.status_code == 401 and con_token and reintentar:
            self._olvidar_token()
            return self._post(ruta, cuerpo, con_token=True, reintentar=False)
        if len(respuesta.content or b'') > MAX_RESPUESTA:
            raise ErrorTilopay('respuesta', 'demasiado grande')
        try:
            datos = respuesta.json()
        except ValueError:
            raise ErrorTilopay('respuesta', f'no es JSON (HTTP {respuesta.status_code})') from None
        return respuesta.status_code, datos

    # -- token

    def _olvidar_token(self):
        with _CANDADO:
            _TOKENS.pop(_huella(self._creds), None)

    def _token(self):
        huella = _huella(self._creds)
        with _CANDADO:
            guardado = _TOKENS.get(huella)
            if guardado and guardado[1] > time.monotonic():
                return guardado[0]
        token, vida = self._login()
        with _CANDADO:
            _TOKENS[huella] = (token, time.monotonic() + vida)
        return token

    def _login(self):
        estado, datos = self._post(RUTA_LOGIN, {'apiuser': self._creds.usuario, 'password': self._creds.clave},
                                   con_token=False)
        if estado in (400, 401, 403) or not isinstance(datos, dict) or datos.get('error'):
            raise ErrorTilopay('claves', 'Tilopay no aceptó el usuario y la contraseña')
        token = datos.get('access_token')
        if not isinstance(token, str) or not token.strip() or len(token) > 8192:
            raise ErrorTilopay('respuesta', 'el inicio de sesión no trajo un token')
        vigencia = datos.get('expires_in')
        vida = VIDA_MAXIMA_TOKEN
        if isinstance(vigencia, (int, float)) and not isinstance(vigencia, bool) and math.isfinite(vigencia):
            vida = min(max(vigencia * 0.8, VIDA_MINIMA_TOKEN), VIDA_MAXIMA_TOKEN)
        return token.strip(), vida

    # -- lo que usa Odoo

    def probar(self):
        """``True`` si Tilopay aceptó el usuario y la contraseña. No devuelve ni guarda datos."""
        self._olvidar_token()
        self._token()
        return True

    def crear_pago(self, datos):
        """Pide la página de pago. ``datos`` ya trae todo salvo la llave. Devuelve la dirección (https de
        tilopay.com)."""
        estado, cuerpo = self._post(RUTA_PAGO, {**datos, 'key': self._creds.llave})
        if not isinstance(cuerpo, dict):
            raise ErrorTilopay('respuesta', 'respuesta inesperada al crear el pago')
        if str(cuerpo.get('type', '')).strip() != '100':
            raise ErrorTilopay('rechazo', limpiar(f"{cuerpo.get('type')}: {cuerpo.get('message')}",
                                                  self._creds.secretos()))
        url = cuerpo.get('url')
        if not isinstance(url, str) or not url_de_pago_valida(url):
            raise ErrorTilopay('respuesta', 'la dirección de pago no es de Tilopay')
        return url

    def consultar(self, orden):
        """El cuerpo de ``consult`` para esa orden (nuestra, guardada; nunca la del navegador)."""
        estado, cuerpo = self._post(RUTA_CONSULTA, {'key': self._creds.llave, 'orderNumber': orden})
        if estado == 401:
            raise ErrorTilopay('claves', 'Tilopay no aceptó el token')
        return cuerpo


# ------------------------------------------------------------------ la decisión

class DatosVerificados(dict):
    """Lo que Odoo le entrega a ``_process``: el resultado de UNA consulta a Tilopay ya evaluada. Solo se crea en
    ``evaluar_consulta``; lo que llega por el navegador o por un aviso son textos, nunca esta clase, así que
    ``_apply_updates`` puede exigirla y un descuido de programación no acepta datos ajenos como si fueran de Tilopay."""

    __slots__ = ()


def _decimal(valor):
    """``Decimal`` de un monto que Tilopay manda como texto (o número), o ``None`` si no es un monto."""
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        numero = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def evaluar_consulta(cuerpo, orden, monto, moneda, entorno):
    """Decide qué dijo Tilopay de ESTA orden. Devuelve ``DatosVerificados`` con ``veredicto`` y lo necesario.

    ``monto`` (``Decimal``), ``moneda`` y ``orden`` salen de la transacción de Odoo; ``entorno`` es ``'prueba'`` o
    ``'produccion'`` (lo que declara el Worker). Solo ``APROBADO`` autoriza a marcar pagado, y solo si una (y solo una)
    fila de pago de esa orden trae ``code = 1``, el monto y la moneda **exactos**, el entorno esperado y está capturada.
    """
    def dato(veredicto, **extra):
        return DatosVerificados(veredicto=veredicto, orden=orden, **extra)

    if not isinstance(cuerpo, dict):
        return dato(INVALIDO, detalle='la respuesta no es un objeto')
    if str(cuerpo.get('type', '')).strip() != '200':
        # Tilopay también contesta así a una orden que todavía no conoce: se queda pendiente, no es un error de pago.
        motivo = cuerpo.get('message') or cuerpo.get('error') or ''
        return dato(SIN_REGISTRO, detalle=limpiar(f"{cuerpo.get('type', '')}: {motivo}"))
    filas = cuerpo.get('response')
    if not isinstance(filas, list):
        return dato(INVALIDO, detalle='la consulta no trajo una lista')
    propias = [f for f in filas if isinstance(f, dict) and str(f.get('orderNumber', '')).strip() == orden]
    if not propias:
        return dato(SIN_REGISTRO, detalle='Tilopay no tiene esa orden todavía')

    pagos = [f for f in propias if str(f.get('type', '')).strip().lower() == 'payment']
    otras = [f for f in propias if f not in pagos]
    if otras:
        tipos = limpiar(', '.join(sorted({str(f.get('type', '')) for f in otras})))
        return dato(AMBIGUO, detalle=f'la orden trae movimientos que no son un pago ({tipos})')
    aprobadas = [f for f in pagos if str(f.get('code', '')).strip() == '1']
    if not aprobadas:
        motivo = limpiar(pagos[-1].get('response') or pagos[-1].get('description') or '') if pagos else ''
        return dato(RECHAZADO, detalle=motivo or 'Tilopay no aprobó el pago')
    if len(aprobadas) > 1:
        return dato(AMBIGUO, detalle='la orden trae más de un pago aprobado')

    fila = aprobadas[0]
    entorno_visto = entorno_de(fila.get('environment'))
    visto_texto = limpiar(fila.get('environment'))
    if entorno_visto is None:
        return dato(ENTORNO, detalle=f'el entorno «{visto_texto}» no se reconoce', entorno_visto=visto_texto)
    if entorno_visto != entorno:
        return dato(ENTORNO, detalle=f'Tilopay respondió «{entorno_visto}» y se esperaba «{entorno}»',
                    entorno_visto=entorno_visto)
    moneda_vista = str(fila.get('currency') or '').strip().upper()
    if moneda_vista != str(moneda).strip().upper():
        return dato(MONEDA, detalle=f'moneda distinta (Tilopay: {limpiar(moneda_vista)})', entorno_visto=entorno_visto)
    monto_visto = _decimal(fila.get('amount'))
    if monto_visto is None or monto_visto != monto:
        return dato(MONTO, detalle=f'monto distinto (Tilopay: {limpiar(fila.get("amount"))}; pedido: {monto})',
                    entorno_visto=entorno_visto)
    captura = str(fila.get('capture') or '').strip().lower()
    if captura and captura not in CAPTURA_VALIDA:
        return dato(CAPTURA, detalle=f'el pago no está capturado ({limpiar(captura)})', entorno_visto=entorno_visto)
    return dato(APROBADO, detalle='aprobado', entorno_visto=entorno_visto, monto=monto_visto, moneda=moneda_vista,
                id_tilopay=limpiar(fila.get('id_tilopay')), autorizacion=limpiar(fila.get('auth')))
