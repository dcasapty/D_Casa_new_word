"""«Busca con una foto»: de la foto del visitante a los productos publicados que se le parecen (docs/CATALOGO.md).

El recorrido de una búsqueda (``dcasa.buscar.foto._dcasa_buscar``):

1. **Valida** la foto: base64 válido, de 1 byte a 1,5 MB, y que los bytes sean de verdad JPEG, PNG o WebP (no se le
   cree al tipo que dice el navegador). Si no: ``formato``.
2. **A lo sumo 3 a la vez por proceso** (``_SEMAFORO``, sin espera): la cuarta recibe ``no_ahora`` al instante, en vez
   de dejar a Odoo esperando al Worker con más peticiones abiertas.
3. **Topes, en una transacción corta aparte y ya confirmada antes de llamar al Worker** (``_dcasa_reservar``): bajo
   ``pg_advisory_xact_lock`` y en READ COMMITTED se cuentan las búsquedas (por visitante y por conexión en la última
   hora, y en total en el día, hora de Panamá) y, si hay cupo, se anota la fila. Cinco pedidos a la vez con tope 1
   dejan pasar uno solo, y lo que reviente después (en el Worker o al buscar) igual quedó contado
   (``scripts/revision_rvf_carrera_foto.py`` lo comprueba con transacciones de verdad). La fila no guarda la foto ni a
   la persona: la hora, el resultado y, solo hasta el día siguiente, dos huellas (de la sesión y de la conexión: la
   IPv4 entera o la red /64 de la IPv6, como el borde) con una sal al azar del día que el cron borra. Son huellas que no
   dicen quién eres y se borran al día siguiente.
4. **Lectura** en el Worker de Juan (``POST /odoo/buscar-foto``, con ``JUAN_URL`` y ``JUAN_WORKER_TOKEN`` como el resto
   de las pantallas de Juan; plazo de 15 s). El Worker usa el mismo lector de imágenes de las conversaciones, aplica el
   tope mensual de la foto (``tope_mes_usd``, de Sitio web › Busca con una foto) y no lee nada con el gasto de Juan por
   encima del 80 % de su tope; devuelve SOLO el registro cerrado, que aquí se vuelve a pasar por listas cerradas (con
   sus tipos: nada mal formado revienta). Sin Worker, sin cupo de IA, caído o lento: ``no_ahora``.
5. **Comprobantes y cédulas no se buscan**: tipo ``comprobante``/``identidad`` o cualquier señal de pago o de
   identidad → ``documento``. Lo que no es un mueble → ``otra``.
6. **Búsqueda, solo entre lo publicado** (``website._dcasa_dominio_publicado``, como el «Agregar» de un clic): primero
   por el código leído (el código público ``DC-…`` o la referencia, exacta: las mismas reglas que la búsqueda de Juan);
   si no, por categoría y medida (las mismas palabras y la misma puntuación que ``buscar_productos`` de Juan). Si no hay
   nada: ``nada``.

La foto vive solo en la memoria de esta petición: no se escribe en ningún modelo, adjunto, sesión ni registro (log). La
página nunca muestra texto de la imagen: solo etiquetas de listas cerradas («Cama · Queen»).
"""
import base64
import binascii
import hashlib
import hmac
import logging
import re
import secrets
import threading
from datetime import datetime, timedelta

import pytz

from odoo import SUPERUSER_ID, api, fields, models
from odoo.addons.dcasa_base.red import llave_ip
from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)

# Odoo espera más que el Worker (juan/src/odoo-panel-buscar-foto.ts, PLAZO_BUSCAR_FOTO_MS = 12 s): una prueba del Worker
# lee esta línea y exige el margen (docs/CONTEXTO_AGENTICO.md, regla 10).
TIMEOUT_BUSCAR_FOTO = (3.05, 15)
# El navegador manda la foto achicada (1024 px en JPEG: unos cientos de KB); 1,5 MB deja pasar una sin achicar pequeña.
MAX_BYTES_FOTO = 1536 * 1024
# Lo más que puede pesar la petición entera a /shop/foto (la foto en base64 pesa 4/3 más, más el resto del formulario).
MAX_PETICION = MAX_BYTES_FOTO * 4 // 3 + 64 * 1024
MAX_RESULTADOS = 12
ZONA = 'America/Panama'
# Búsquedas a la vez por proceso de Odoo (cada una espera al Worker hasta 15 s con su petición abierta).
MAX_A_LA_VEZ = 3
_SEMAFORO = threading.BoundedSemaphore(MAX_A_LA_VEZ)
# La llave del cerrojo de los topes (pg_advisory_xact_lock): un número fijo de este módulo.
CERROJO_TOPES = 0x0DCA5F070
CONCEPTO_DEL_GASTO = 'cloudflare:lector-de-fotos'

PARAM_ACTIVO = 'dcasa_buscar_foto.activo'
PARAM_TOPES = {
    'visitante': 'dcasa_buscar_foto.tope_visitante_hora',
    'conexion': 'dcasa_buscar_foto.tope_conexion_hora',
    'dia': 'dcasa_buscar_foto.tope_dia',
}
PARAM_TOPE_MES = 'dcasa_buscar_foto.tope_mes_usd'
# Prudentes y cambiables en Sitio web › Busca con una foto. Por conexión es más alto que por visitante: en Panamá muchos
# teléfonos salen a internet por la misma red del operador.
TOPES_DE_FABRICA = {'visitante': 10, 'conexion': 30, 'dia': 200}
TOPE_MES_DE_FABRICA = 5.0
MAX_TOPE_MES = 1000.0

MIMES = ('image/jpeg', 'image/png', 'image/webp')
# Las mismas listas cerradas del lector (juan/src/motor/vision.ts).
TIPOS = ('producto', 'publicacion', 'comprobante', 'identidad', 'otra', 'ilegible')
MEDIDAS = {'twin': 'Twin', 'full': 'Full', 'queen': 'Queen', 'king': 'King'}
# categoría del lector → (cómo se dice en la página, palabras con que se busca en el catálogo, en orden).
CATEGORIAS = {
    'cama': ('Cama', ('cama',)),
    'colchon': ('Colchón', ('colchon',)),
    'sofa': ('Sofá', ('sofa', 'sala')),
    'comedor': ('Comedor', ('comedor',)),
    'escritorio': ('Escritorio', ('escritorio',)),
    'silla': ('Silla', ('silla',)),
    'closet': ('Clóset', ('closet', 'ropero', 'armario')),
    'mesa': ('Mesa', ('mesa',)),
}
RE_CODIGO = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{1,23}$')
RE_BASE64 = re.compile(r'^[A-Za-z0-9+/]+={0,2}$')

ESTADOS = ('resultados', 'nada', 'documento', 'otra', 'no_ahora', 'formato')


def tipo_por_firma(datos):
    """El tipo que dicen los BYTES (no el navegador), o ``None`` si no es JPEG, PNG ni WebP."""
    if datos[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if datos[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if len(datos) > 12 and datos[:4] == b'RIFF' and datos[8:12] == b'WEBP':
        return 'image/webp'
    return None


def decodificar_foto(texto):
    """``(bytes, mime)`` de la foto en base64, o ``None`` si no sirve (vacía, rota, de más de 1,5 MB u otro tipo)."""
    if not isinstance(texto, str):
        return None
    texto = texto.strip()
    if texto.startswith('data:'):   # un «data URL» completo también vale
        texto = texto.partition(',')[2]
    if not texto or len(texto) > MAX_BYTES_FOTO * 4 // 3 + 4 or len(texto) % 4 or not RE_BASE64.match(texto):
        return None
    try:
        datos = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not datos or len(datos) > MAX_BYTES_FOTO:
        return None
    mime = tipo_por_firma(datos)
    return (datos, mime) if mime else None


def _de_la_lista(valor, permitidos):
    """El valor si es un texto de la lista; si no (otro tipo, una lista, un diccionario…), ``None``."""
    return valor if isinstance(valor, str) and valor in permitidos else None


def normalizar_lectura(crudo):
    """El registro cerrado que mandó el Worker, otra vez contra las listas cerradas; ``None`` si no es uno.

    Se revisa el TIPO de cada campo (un ``['cama']`` o un ``{'queen': 1}`` no revientan: se descartan). Como en el
    lector: si faltan las señales de pago o de identidad (o no son ``false``), se asume lo prudente (que sí las hay)."""
    if not isinstance(crudo, dict):
        return None
    tipo = _de_la_lista(crudo.get('tipo'), TIPOS)
    if not tipo:
        return None
    codigos = []
    for codigo in crudo.get('codigos') if isinstance(crudo.get('codigos'), list) else []:
        if isinstance(codigo, str) and RE_CODIGO.match(codigo.strip()) and codigo.strip().upper() not in codigos:
            codigos.append(codigo.strip().upper())
    return {
        'tipo': tipo,
        'codigos': codigos[:3],
        'categoria': _de_la_lista(crudo.get('categoria'), CATEGORIAS),
        'medida': _de_la_lista(crudo.get('medida'), MEDIDAS),
        'parece_pago': crudo.get('parece_pago') is not False,
        'parece_identidad': crudo.get('parece_identidad') is not False,
    }


def es_documento(lectura):
    return lectura['tipo'] in ('comprobante', 'identidad') or lectura['parece_pago'] or lectura['parece_identidad']


def etiqueta_de(lectura):
    """«Cama · Queen»: SOLO de listas cerradas (nunca texto de la imagen)."""
    partes = []
    if lectura and _de_la_lista(lectura.get('categoria'), CATEGORIAS):
        partes.append(CATEGORIAS[lectura['categoria']][0])
    if lectura and _de_la_lista(lectura.get('medida'), MEDIDAS):
        partes.append(MEDIDAS[lectura['medida']])
    return ' · '.join(partes)


def huella(sal, tipo, valor):
    """HMAC-SHA256 con la sal del día: sirve para contar, no dice de quién es; ``False`` sin valor."""
    if not valor or not sal:
        return False
    return hmac.new(sal.encode(), f'{tipo}:{valor}'.encode(), hashlib.sha256).hexdigest()[:32]


class DcasaBuscarFoto(models.AbstractModel):
    _name = 'dcasa.buscar.foto'
    _description = 'Busca con una foto (la lógica de la tienda)'

    # ------------------------------------------------------------------
    # Interruptor y topes (ir.config_parameter; se cambian en Sitio web › Busca con una foto)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_activa(self):
        """Encendida de fábrica (data/parametros.xml). Apagada = la cámara no se dibuja y /shop/foto no existe."""
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_ACTIVO, 'False')
        return str(valor).strip().lower() in ('1', 'true', 'yes', 'si', 'sí')

    @api.model
    def _dcasa_topes(self):
        """Los topes vigentes: lo que puso Gerencia o, si no hay o no es un número, los de fábrica (nunca sin tope)."""
        Parametro = self.env['ir.config_parameter'].sudo()
        topes = {}
        for clave, parametro in PARAM_TOPES.items():
            try:
                valor = int(Parametro.get_param(parametro) or TOPES_DE_FABRICA[clave])
            except (TypeError, ValueError):
                valor = TOPES_DE_FABRICA[clave]
            topes[clave] = max(valor, 0)
        return topes

    @api.model
    def _dcasa_tope_mes(self):
        """Lo más que la foto puede gastar de IA en el mes (USD): lo de Gerencia o 5 de fábrica (nunca sin tope)."""
        try:
            valor = float(self.env['ir.config_parameter'].sudo().get_param(PARAM_TOPE_MES) or TOPE_MES_DE_FABRICA)
        except (TypeError, ValueError):
            valor = TOPE_MES_DE_FABRICA
        return min(max(valor, 0.0), MAX_TOPE_MES)

    # ------------------------------------------------------------------
    # Fechas y sales del día
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_ahora_local(self, ahora=None):
        return pytz.utc.localize(ahora or fields.Datetime.now()).astimezone(pytz.timezone(ZONA))

    @api.model
    def _dcasa_inicio_del_dia(self, ahora=None):
        """Medianoche de hoy en Panamá, en UTC sin zona (como se guardan los Datetime)."""
        local = self._dcasa_ahora_local(ahora)
        medianoche = pytz.timezone(ZONA).localize(datetime(local.year, local.month, local.day))
        return medianoche.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _dcasa_sales(self, ahora=None):
        """``(sal de hoy, sal de ayer)``, días de Panamá. La de hoy nace al azar con la primera búsqueda del día; el
        cron borra las de antes de ayer. Con la de ayer se reconocen las búsquedas de antes de la medianoche (topes por
        hora). Se llama con el cerrojo de los topes tomado (dos búsquedas a la vez no crean dos sales)."""
        Sal = self.env['dcasa.buscar.foto.sal'].sudo()
        hoy = self._dcasa_ahora_local(ahora).date()
        sales = {s.fecha: s.valor for s in Sal.search([('fecha', 'in', [hoy, hoy - timedelta(days=1)])])}
        if hoy not in sales:
            sales[hoy] = Sal.create({'fecha': hoy, 'valor': secrets.token_hex(32)}).valor
        return sales[hoy], sales.get(hoy - timedelta(days=1))

    # ------------------------------------------------------------------
    # La reserva del cupo (transacción corta aparte)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_reservar(self, sesion, conexion):
        """Cuenta y, si hay cupo, anota la búsqueda en una transacción PROPIA que se confirma al salir (antes de llamar
        al Worker). Devuelve ``(id de la fila, None)`` o ``(None, el tope que se pasó)``.

        En READ COMMITTED y bajo ``pg_advisory_xact_lock``: cada conteo ve lo que confirmaron las anteriores (en
        REPEATABLE READ, la foto de la base se tomaría ANTES de esperar el cerrojo y no las vería). En las pruebas la
        transacción es la de la prueba (``TestCursor``): ahí no se cambia el aislamiento."""
        with self.env.registry.cursor() as cr:
            if isinstance(cr, Cursor):
                cr.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            cr.execute('SELECT pg_advisory_xact_lock(%s)', [CERROJO_TOPES])
            env = api.Environment(cr, SUPERUSER_ID, {})
            Foto = env['dcasa.buscar.foto']
            Uso = env['dcasa.buscar.foto.uso']
            topes = Foto._dcasa_topes()
            ahora = fields.Datetime.now()
            hace_una_hora = ahora - timedelta(hours=1)
            sal_hoy, sal_ayer = Foto._dcasa_sales(ahora)
            red = llave_ip(conexion) if conexion else None
            visitante = [h for h in (huella(sal_hoy, 'v', sesion), huella(sal_ayer, 'v', sesion)) if h]
            de_la_red = [h for h in (huella(sal_hoy, 'c', red), huella(sal_ayer, 'c', red)) if h]
            if Uso.search_count([('fecha', '>=', Foto._dcasa_inicio_del_dia(ahora))]) >= topes['dia']:
                return None, 'dia'
            if visitante and Uso.search_count([('fecha', '>=', hace_una_hora),
                                               ('huella_visitante', 'in', visitante)]) >= topes['visitante']:
                return None, 'visitante'
            if de_la_red and Uso.search_count([('fecha', '>=', hace_una_hora),
                                               ('huella_conexion', 'in', de_la_red)]) >= topes['conexion']:
                return None, 'conexion'
            # Cuenta desde ya, aunque el Worker falle o algo reviente después (la IA pudo correr igual).
            uso = Uso.create({'huella_visitante': visitante[0] if visitante else False,
                              'huella_conexion': de_la_red[0] if de_la_red else False, 'resultado': 'no_ahora'})
            return uso.id, None

    @api.model
    def _dcasa_anotar(self, uso_id, estado):
        """El resultado de la búsqueda, en otra transacción corta (la de la petición no ve la fila de la reserva)."""
        try:
            with self.env.registry.cursor() as cr:
                cr.execute('UPDATE dcasa_buscar_foto_uso SET resultado = %s WHERE id = %s', [estado, uso_id])
        except Exception:  # noqa: BLE001 — el resultado es para las cifras: nunca le cambia la página al cliente
            _logger.warning('Busca con una foto: no se pudo anotar el resultado de una búsqueda.', exc_info=True)

    # ------------------------------------------------------------------
    # La búsqueda
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_buscar(self, foto_base64, website, sesion=None, conexion=None):
        """``{estado, productos, lectura, etiqueta, por_codigo}``. ``productos``: ``product.template`` del visitante.

        ``sesion`` y ``conexion`` (el id de la sesión y la dirección de quien pide) solo se usan para los topes, como
        huellas. Nunca lanza por culpa del Worker."""
        vacio = self.env['product.template'].browse()
        resultado = {'estado': 'formato', 'productos': vacio, 'lectura': None, 'etiqueta': '', 'por_codigo': False}
        foto = decodificar_foto(foto_base64)
        if not foto:
            return resultado
        datos, mime = foto
        del foto
        if not _SEMAFORO.acquire(blocking=False):
            _logger.info('Busca con una foto: ya hay %s búsquedas a la vez en este proceso.', MAX_A_LA_VEZ)
            return {**resultado, 'estado': 'no_ahora'}
        try:
            uso_id, tope = self._dcasa_reservar(sesion, conexion)
            if tope:
                _logger.info('Busca con una foto: sin cupo (%s).', tope)
                return {**resultado, 'estado': 'no_ahora'}
            estado = 'no_ahora'
            try:
                lectura = self._dcasa_leer(datos, mime)
                del datos   # la foto no sale de aquí
                mueble = bool(lectura) and lectura['tipo'] in ('producto', 'publicacion')
                if lectura is False:
                    estado = 'no_ahora'
                elif lectura is None or (not mueble and not es_documento(lectura)):
                    estado = 'otra'
                elif es_documento(lectura):
                    estado = 'documento'
                    lectura = None   # de un documento no se dice nada: ni categoría ni medida
                else:
                    productos, por_codigo = self._dcasa_parecidos(website, lectura)
                    estado = 'resultados' if productos else 'nada'
                    resultado.update(productos=productos, por_codigo=por_codigo)
                resultado.update(estado=estado, lectura=lectura or None, etiqueta=etiqueta_de(lectura))
            finally:
                self._dcasa_anotar(uso_id, estado)
        finally:
            _SEMAFORO.release()
        return resultado

    @api.model
    def _dcasa_leer(self, datos, mime):
        """El registro cerrado que leyó el Worker; ``None`` si no pudo leerla; ``False`` si no se pudo preguntar (sin
        Worker, sin cupo de IA, caído o lento). Ni la foto ni la respuesta van al registro (log)."""
        respuesta = self.env['dcasa.juan.cliente'].sudo()._pedir(
            'POST', '/odoo/buscar-foto',
            {'mime': mime, 'base64': base64.b64encode(datos).decode(), 'tope_mes_usd': self._dcasa_tope_mes()},
            timeout=TIMEOUT_BUSCAR_FOTO)
        cuerpo = respuesta.get('cuerpo') if isinstance(respuesta.get('cuerpo'), dict) else {}
        if respuesta.get('error') or not respuesta.get('conectado') or cuerpo.get('ok') is not True:
            causa = _de_la_lista(cuerpo.get('causa'), ('tope', 'tope_foto', 'reserva', 'no_disponible', 'tardo')) or (
                respuesta.get('causa') or ('sin_configurar' if respuesta.get('sin_configurar') else 'error'))
            _logger.info('Busca con una foto: el Worker no la leyó (%s).', causa)
            return False
        return normalizar_lectura(cuerpo.get('lectura'))

    @api.model
    def _dcasa_parecidos(self, website, lectura):
        """``(productos, por_codigo)``: los publicados que se parecen, el mejor primero (como máximo 12)."""
        Plantilla = self.env['product.template']
        publicadas = Plantilla.search(website._dcasa_dominio_publicado())   # como el visitante: solo lo publicado
        if not publicadas:
            return Plantilla.browse(), False
        Juan = self.env['brian.herramientas']
        # Por código: el público (DC-…) o la referencia exacta, con la misma regla que la búsqueda de Juan.
        por_codigo = Plantilla.browse()
        for codigo in lectura['codigos']:
            por_codigo |= Juan._j_plantilla_por_codigo(codigo, publicadas.sudo())
        if por_codigo:
            return Plantilla.browse(por_codigo.ids[:MAX_RESULTADOS]), True
        categoria = CATEGORIAS.get(lectura['categoria']) if lectura['categoria'] else None
        if not categoria:
            return Plantilla.browse(), False
        candidatos = Juan._j_candidatos(publicadas.sudo())
        medida = lectura['medida']
        encontrados = []
        # Primero con la medida («cama queen»); si con la medida no hay nada, la categoría sola («cama»).
        for consultas in ([f'{p} {medida}' for p in categoria[1]] if medida else [], list(categoria[1])):
            for consulta in consultas:
                for plantilla in Juan._j_puntuados(consulta, candidatos):
                    if plantilla.id not in encontrados:
                        encontrados.append(plantilla.id)
            if encontrados:
                break
        return Plantilla.browse(encontrados[:MAX_RESULTADOS]), False
