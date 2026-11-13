"""«Busca con una foto»: de la foto del visitante a los productos publicados que se le parecen (docs/CATALOGO.md).

El recorrido de una búsqueda (``dcasa.buscar.foto._dcasa_buscar``):

1. **Valida** la foto: base64 válido, de 1 byte a 4 MB, y que los bytes sean de verdad JPEG, PNG o WebP (no se le cree
   al tipo que dice el navegador). Si no: ``formato``.
2. **Topes**, antes de gastar IA: por visitante y por conexión en la última hora, y en total en el día (hora de Panamá).
   Se cuentan las filas de ``dcasa.buscar.foto.uso``, que no guardan la foto ni a la persona: la hora, el resultado y,
   solo por un día, dos huellas HMAC (sesión y conexión) que no se pueden revertir. Si se pasa: ``no_ahora``.
3. **Lectura** en el Worker de Juan (``POST /odoo/buscar-foto``, con ``JUAN_URL`` y ``JUAN_WORKER_TOKEN`` como el resto
   de las pantallas de Juan). El Worker usa el mismo lector de imágenes de las conversaciones y devuelve SOLO el
   registro cerrado; aquí se vuelve a normalizar contra listas cerradas (nunca se confía en lo que llega). Sin Worker,
   con el tope de IA del mes alcanzado, caído o lento: ``no_ahora``.
4. **Comprobantes y cédulas no se buscan**: tipo ``comprobante``/``identidad`` o cualquier señal de pago o de
   identidad → ``documento``. Lo que no es un mueble → ``otra``.
5. **Búsqueda, solo entre lo publicado** (``website._dcasa_dominio_publicado``, como el «Agregar» de un clic): primero
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
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Odoo espera más que el Worker (juan/src/odoo-panel-buscar-foto.ts, PLAZO_BUSCAR_FOTO_MS = 25 s): una prueba del Worker
# lee esta línea y exige el margen (docs/CONTEXTO_AGENTICO.md, regla 10).
TIMEOUT_BUSCAR_FOTO = (3.05, 30)
MAX_BYTES_FOTO = 4 * 1024 * 1024
# Lo más que puede pesar la petición entera a /shop/foto (la foto en base64 pesa 4/3 más, más el resto del formulario).
MAX_PETICION = MAX_BYTES_FOTO * 4 // 3 + 64 * 1024
MAX_RESULTADOS = 12
ZONA = 'America/Panama'

PARAM_ACTIVO = 'dcasa_buscar_foto.activo'
PARAM_TOPES = {
    'visitante': 'dcasa_buscar_foto.tope_visitante_hora',
    'conexion': 'dcasa_buscar_foto.tope_conexion_hora',
    'dia': 'dcasa_buscar_foto.tope_dia',
}
# Prudentes y cambiables en Sitio web › Busca con una foto. Por conexión es más alto que por visitante: en Panamá muchos
# teléfonos salen a internet por la misma dirección del operador.
TOPES_DE_FABRICA = {'visitante': 10, 'conexion': 30, 'dia': 200}

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
    """``(bytes, mime)`` de la foto en base64, o ``None`` si no sirve (vacía, rota, de más de 4 MB u otro tipo)."""
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


def normalizar_lectura(crudo):
    """El registro cerrado que mandó el Worker, otra vez contra las listas cerradas; ``None`` si no es uno.

    Como en el lector: si faltan las señales de pago o de identidad, se asume lo prudente (que sí las hay)."""
    if not isinstance(crudo, dict) or crudo.get('tipo') not in TIPOS:
        return None
    codigos = []
    for codigo in crudo.get('codigos') if isinstance(crudo.get('codigos'), list) else []:
        if isinstance(codigo, str) and RE_CODIGO.match(codigo.strip()) and codigo.strip().upper() not in codigos:
            codigos.append(codigo.strip().upper())
    categoria, medida = crudo.get('categoria'), crudo.get('medida')
    return {
        'tipo': crudo['tipo'],
        'codigos': codigos[:3],
        'categoria': categoria if categoria in CATEGORIAS else None,
        'medida': medida if medida in MEDIDAS else None,
        'parece_pago': crudo.get('parece_pago') is not False,
        'parece_identidad': crudo.get('parece_identidad') is not False,
    }


def es_documento(lectura):
    return lectura['tipo'] in ('comprobante', 'identidad') or lectura['parece_pago'] or lectura['parece_identidad']


def etiqueta_de(lectura):
    """«Cama · Queen»: SOLO de listas cerradas (nunca texto de la imagen)."""
    partes = []
    if lectura and lectura.get('categoria') in CATEGORIAS:
        partes.append(CATEGORIAS[lectura['categoria']][0])
    if lectura and lectura.get('medida') in MEDIDAS:
        partes.append(MEDIDAS[lectura['medida']])
    return ' · '.join(partes)


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

    # ------------------------------------------------------------------
    # Huellas para los topes (sin guardar la sesión ni la dirección)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_huella(self, tipo, valor):
        """HMAC-SHA256 con el secreto de la base: sirve para contar, no para saber de quién es."""
        if not valor:
            return False
        secreto = self.env['ir.config_parameter'].sudo().get_param('database.secret') or self.env.cr.dbname
        return hmac.new(secreto.encode(), f'{tipo}:{valor}'.encode(), hashlib.sha256).hexdigest()[:32]

    @api.model
    def _dcasa_inicio_del_dia(self, ahora=None):
        """Medianoche de hoy en Panamá, en UTC sin zona (como se guardan los Datetime)."""
        ahora = ahora or fields.Datetime.now()
        zona = pytz.timezone(ZONA)
        local = pytz.utc.localize(ahora).astimezone(zona)
        medianoche = zona.localize(datetime(local.year, local.month, local.day))
        return medianoche.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _dcasa_sin_cupo(self, huella_visitante, huella_conexion):
        """``None`` si hay cupo; si no, cuál tope se pasó (``visitante``, ``conexion`` o ``dia``). 0 = cerrado."""
        topes = self._dcasa_topes()
        Uso = self.env['dcasa.buscar.foto.uso'].sudo()
        ahora = fields.Datetime.now()
        hace_una_hora = ahora - timedelta(hours=1)
        if Uso.search_count([('fecha', '>=', self._dcasa_inicio_del_dia(ahora))]) >= topes['dia']:
            return 'dia'
        if huella_visitante and Uso.search_count([
                ('fecha', '>=', hace_una_hora), ('huella_visitante', '=', huella_visitante)]) >= topes['visitante']:
            return 'visitante'
        if huella_conexion and Uso.search_count([
                ('fecha', '>=', hace_una_hora), ('huella_conexion', '=', huella_conexion)]) >= topes['conexion']:
            return 'conexion'
        return None

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
        huella_visitante = self._dcasa_huella('v', sesion)
        huella_conexion = self._dcasa_huella('c', conexion)
        tope = self._dcasa_sin_cupo(huella_visitante, huella_conexion)
        if tope:
            _logger.info('Busca con una foto: sin cupo (%s).', tope)
            return {**resultado, 'estado': 'no_ahora'}
        # Cuenta para los topes aunque el Worker falle (la IA pudo correr igual); el resultado se anota al final.
        uso = self.env['dcasa.buscar.foto.uso'].sudo().create({
            'huella_visitante': huella_visitante, 'huella_conexion': huella_conexion, 'resultado': 'no_ahora'})

        lectura = self._dcasa_leer(datos, mime)
        del datos, foto   # la foto no sale de esta función
        if lectura is False:
            estado = 'no_ahora'
        elif lectura is None or (lectura['tipo'] not in ('producto', 'publicacion') and not es_documento(lectura)):
            estado = 'otra'
        elif es_documento(lectura):
            estado = 'documento'
            lectura = None   # de un documento no se dice nada: ni categoría ni medida
        else:
            productos, por_codigo = self._dcasa_parecidos(website, lectura)
            estado = 'resultados' if productos else 'nada'
            resultado.update(productos=productos, por_codigo=por_codigo)
        uso.resultado = estado
        resultado.update(estado=estado, lectura=lectura or None, etiqueta=etiqueta_de(lectura))
        return resultado

    @api.model
    def _dcasa_leer(self, datos, mime):
        """El registro cerrado que leyó el Worker; ``None`` si no pudo leerla; ``False`` si no se pudo preguntar (sin
        Worker, tope de IA del mes, caído o lento). Ni la foto ni la respuesta van al registro (log)."""
        respuesta = self.env['dcasa.juan.cliente'].sudo()._pedir(
            'POST', '/odoo/buscar-foto', {'mime': mime, 'base64': base64.b64encode(datos).decode()},
            timeout=TIMEOUT_BUSCAR_FOTO)
        cuerpo = respuesta.get('cuerpo') or {}
        if respuesta.get('error') or not respuesta.get('conectado') or cuerpo.get('ok') is not True:
            causa = cuerpo.get('causa') if cuerpo.get('causa') in ('tope', 'no_disponible', 'tardo') else (
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
        categoria = CATEGORIAS.get(lectura['categoria'])
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
