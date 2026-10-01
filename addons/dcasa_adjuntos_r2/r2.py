"""Acceso a R2 (API S3) para los adjuntos, sin nada de Odoo: configuración, cliente y caché.

Variables de entorno del proceso de Odoo (las exporta docker/entrypoint.sh a partir de las
R2_* del contenedor; ver edge/CONTRATO_CONTENEDOR.md §3):

    DCASA_ADJUNTOS_R2_ENDPOINT           https://<cuenta>.r2.cloudflarestorage.com
    DCASA_ADJUNTOS_R2_BUCKET             bucket (el mismo de los respaldos, prefijo adjuntos/)
    DCASA_ADJUNTOS_R2_ACCESS_KEY_ID      token S3 de R2
    DCASA_ADJUNTOS_R2_SECRET_ACCESS_KEY
    DCASA_ADJUNTOS_R2_REGION             «auto» (R2)
    DCASA_ADJUNTOS_R2_VERIFY_TLS         y | n (n solo en CI, S3 local con certificado propio)

Si falta alguna de las cuatro primeras, o boto3 no está instalado, ``configuracion()``
devuelve None y los adjuntos se quedan en la base (CI, desarrollo).
"""
import hashlib
import logging
import os
import threading
from collections import OrderedDict

_logger = logging.getLogger(__name__)

ESQUEMA = 'r2://'
PREFIJO = 'adjuntos/'
VARIABLES = {
    'endpoint': 'DCASA_ADJUNTOS_R2_ENDPOINT',
    'bucket': 'DCASA_ADJUNTOS_R2_BUCKET',
    'access_key_id': 'DCASA_ADJUNTOS_R2_ACCESS_KEY_ID',
    'secret_access_key': 'DCASA_ADJUNTOS_R2_SECRET_ACCESS_KEY',
}
# Errores de S3 que significan «el objeto no está» (permanente), no «R2 no responde».
NO_EXISTE = frozenset({'NoSuchKey', '404', 'NotFound'})


class ErrorR2(Exception):
    """R2 no respondió o respondió con un error: nunca se trata como «archivo vacío»."""


def configuracion(entorno=None):
    """Credenciales de R2 para los adjuntos, o None si no están completas o falta boto3."""
    entorno = os.environ if entorno is None else entorno
    conf = {clave: (entorno.get(variable) or '').strip() for clave, variable in VARIABLES.items()}
    if not all(conf.values()):
        return None
    if not boto3_disponible():
        _logger.error('Adjuntos en R2: hay credenciales pero boto3 no está instalado; se usa la base.')
        return None
    conf['region'] = (entorno.get('DCASA_ADJUNTOS_R2_REGION') or 'auto').strip()
    conf['verify_tls'] = (entorno.get('DCASA_ADJUNTOS_R2_VERIFY_TLS') or 'y').strip().lower() != 'n'
    return conf


def boto3_disponible():
    try:
        import boto3  # noqa: F401
    except ImportError:
        return False
    return True


_clientes = {}
_clientes_candado = threading.Lock()


def cliente(conf):
    """Cliente S3 de boto3 (seguro entre hilos), uno por juego de credenciales."""
    llave = (conf['endpoint'], conf['access_key_id'], conf['secret_access_key'], conf['region'], conf['verify_tls'])
    with _clientes_candado:
        if llave not in _clientes:
            import boto3
            from botocore.config import Config

            opciones = {
                'signature_version': 's3v4',
                'retries': {'max_attempts': 4, 'mode': 'standard'},
                'connect_timeout': 5,
                'read_timeout': 30,
                'max_pool_connections': 16,
                's3': {'addressing_style': 'path'},
            }
            try:
                # botocore ≥ 1.36 manda checksums CRC por defecto; R2 solo exige los obligatorios.
                config = Config(**opciones, request_checksum_calculation='when_required',
                                response_checksum_validation='when_required')
            except TypeError:
                config = Config(**opciones)
            if not conf['verify_tls']:
                # Solo CI (S3 local con certificado propio): sin un aviso por petición en el log.
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            _clientes[llave] = boto3.client(
                's3',
                endpoint_url=conf['endpoint'],
                aws_access_key_id=conf['access_key_id'],
                aws_secret_access_key=conf['secret_access_key'],
                region_name=conf['region'],
                verify=conf['verify_tls'],
                config=config,
            )
        return _clientes[llave]


def codigo_error(error):
    """Código S3 de una excepción de botocore (``NoSuchKey``, ``AccessDenied``…) o ''."""
    respuesta = getattr(error, 'response', None) or {}
    return str((respuesta.get('Error') or {}).get('Code') or '')


def es_r2(fname):
    return bool(fname) and fname.startswith(ESQUEMA)


def fname_de(checksum):
    """``store_fname`` de un contenido: r2://adjuntos/ab/abcdef… (sha1, como el filestore)."""
    return f'{ESQUEMA}{PREFIJO}{checksum[:2]}/{checksum}'


def clave_de(fname):
    """Llave en el bucket a partir del store_fname (sin el esquema)."""
    clave = fname[len(ESQUEMA):]
    if not clave.startswith(PREFIJO) or '..' in clave:
        raise ErrorR2(f'store_fname fuera del prefijo de adjuntos: {fname!r}')
    return clave


def checksum_de(fname):
    return fname.rsplit('/', 1)[-1]


def sha1(datos):
    return hashlib.sha1(datos).hexdigest()


class Cache:
    """LRU en memoria por bytes. El contenido es inmutable (la llave es su sha1): nunca se invalida."""

    def __init__(self, maximo_bytes=64 * 1024 * 1024, maximo_objeto=8 * 1024 * 1024):
        self.maximo_bytes = maximo_bytes
        self.maximo_objeto = maximo_objeto
        self._datos = OrderedDict()
        self._bytes = 0
        self._candado = threading.Lock()

    def obtener(self, clave):
        with self._candado:
            datos = self._datos.get(clave)
            if datos is not None:
                self._datos.move_to_end(clave)
            return datos

    def guardar(self, clave, datos):
        if len(datos) > self.maximo_objeto:
            return
        with self._candado:
            if clave in self._datos:
                self._datos.move_to_end(clave)
                return
            self._datos[clave] = datos
            self._bytes += len(datos)
            while self._bytes > self.maximo_bytes and self._datos:
                _clave, viejo = self._datos.popitem(last=False)
                self._bytes -= len(viejo)

    def limpiar(self):
        with self._candado:
            self._datos.clear()
            self._bytes = 0


cache = Cache()
