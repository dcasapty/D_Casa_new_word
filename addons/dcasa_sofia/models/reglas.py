"""Reglas FIJAS de Sofía: funciones PURAS (sin base de datos, sin reloj, sin IA).

Sofía solo propone; una persona aprueba. Todo lo que propone sale de hechos que Odoo ya sabe (la temperatura del CRM,
cuándo escribió el cliente, una cotización que vence, el nombre que trae su ficha) y de estas reglas: así se puede
probar, explicar y apagar. Ver ``docs/SOFIA.md``.
"""
import re
import unicodedata
from datetime import timedelta

from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_socios.models import bien_escrito as B

# Canales de Meta: fuera de las 24 horas desde el último mensaje del cliente no se le puede escribir un texto libre
# (Meta lo rechaza; no hay plantillas aprobadas). WhatsApp por QR y Telegram no tienen esa ventana.
CANALES_CON_VENTANA = frozenset({'whatsapp_cloud', 'messenger', 'instagram'})
# Un poco antes de las 24 horas, para que el mensaje salga con tiempo aunque la vendedora tarde en aprobarlo.
VENTANA = timedelta(hours=23)

ALTA, MEDIA, BAJA = 3, 2, 1
PRIORIDADES = [(str(ALTA), 'Hoy sin falta'), (str(MEDIA), 'Hoy'), (str(BAJA), 'Cuando puedas')]

# Palabras que delatan una frase de perfil o una empresa, no el nombre de una persona. Lista corta y prudente: un
# nombre de verdad nunca debe caer aquí («Jesús», «Luz», «Paz» o «Amparo» son nombres y NO están).
NO_SON_NOMBRE = frozenset({
    'dios', 'bendiga', 'bendice', 'bendecido', 'bendecida', 'bendecidos', 'bendición', 'bendicion', 'amén', 'amen',
    'amor', 'feliz', 'felicidad', 'gracias', 'vida', 'familia', 'mamá', 'papá', 'mami', 'papi', 'hijos', 'princesa',
    'reina', 'rey', 'bebé', 'bebe', 'tienda', 'store', 'shop', 'oficial', 'ventas', 'servicios', 'inversiones',
    'distribuidora', 'importadora', 'grupo', 'corp', 'inc', 'ltd', 's.a', 'sa', 'srl', 'panamá', 'panama', 'whatsapp',
    'business', 'cliente', 'desconocido', 'usuario',
})
MAX_PALABRAS_DE_UN_NOMBRE = 5
SOLO_EL_NOMBRE = 'solo tiene un nombre: falta el apellido'

# Lo que se puede poner en una plantilla. Cualquier otra {clave} no se acepta al guardarla.
CLAVES_DE_PLANTILLA = ('nombre', 'vendedora', 'interes', 'cotizacion', 'vence', 'para_cuando', 'que_falta')
_CLAVE = re.compile(r'\{([a-z_]+)\}')
_CORREO = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
# Un monto o un precio (para que nunca se cuele una cifra en un mensaje desde lo que anotó Juan o dijo el cliente).
_MONTO = re.compile(r'\$|\bb/\.|\busd\b|d[oó]lar|balboa|\d+[.,]\d{2}\b', re.IGNORECASE)


def ventana_abierta(canal, ultimo_mensaje_cliente, ahora):
    """¿Se le puede escribir ahora un mensaje libre por este canal?"""
    if canal not in CANALES_CON_VENTANA:
        return True
    return bool(ultimo_mensaje_cliente) and ahora - ultimo_mensaje_cliente < VENTANA


def _es_emoji_o_simbolo(caracter):
    return unicodedata.category(caracter) in ('So', 'Sk', 'Cs', 'Co') or ord(caracter) >= 0x1F000


def palabras_del_nombre(nombre):
    """Las palabras con letras de un nombre, sin signos alrededor («Ana,» → «Ana»)."""
    palabras = []
    for parte in (nombre or '').split():
        limpia = parte.strip('.,;:!¡?¿"\'()[]«»-_*~')
        if any(c.isalpha() for c in limpia):
            palabras.append(limpia)
    return palabras


def falta_el_nombre(nombre, provisionales=()):
    """Por qué el nombre de la ficha NO sirve como nombre y apellido de una persona (texto corto), o ``None``.

    Sirve para encontrar a quien llegó por WhatsApp o redes con lo que tenga en su perfil: un emoji, una frase, una
    empresa o solo un nombre de pila. No juzga a una persona: solo dice si falta pedirle sus datos.
    """
    texto = ' '.join((nombre or '').split())
    if not texto or texto in provisionales:
        return 'no tiene nombre'
    if not any(c.isalpha() for c in texto):
        return 'su nombre es un emoji o un símbolo'
    if any(_es_emoji_o_simbolo(c) for c in texto):
        return 'su nombre tiene emojis'
    if any(c.isdigit() for c in texto):
        return 'su nombre tiene números'
    palabras = palabras_del_nombre(texto)
    if len(palabras) > MAX_PALABRAS_DE_UN_NOMBRE:
        return 'su nombre parece una frase'
    if any(p.casefold() in NO_SON_NOMBRE for p in palabras):
        return 'su nombre parece una frase o una empresa'
    if len(palabras) == 1:
        return SOLO_EL_NOMBRE
    return None


def falta_el_correo(correo):
    """¿Falta un correo bien escrito?"""
    if not correo:
        return True
    codigo, _sugerencia = B.problema_del_correo(correo)
    return bool(codigo)


def primer_nombre(nombre, provisionales=()):
    """El nombre de pila para saludar, solo si la ficha trae uno de verdad (nunca «Hola 🙏» ni «Hola Dios»)."""
    motivo = falta_el_nombre(nombre, provisionales)
    if motivo and motivo != SOLO_EL_NOMBRE:
        return ''
    palabras = palabras_del_nombre(nombre)
    return palabras[0].capitalize() if palabras else ''


def que_falta(sin_nombre, sin_correo):
    """«tu nombre y apellido y tu correo», «tu nombre y apellido» o «tu correo» (vacío si no falta nada)."""
    partes = []
    if sin_nombre:
        partes.append('tu nombre y apellido')
    if sin_correo:
        partes.append('tu correo')
    return ' y '.join(partes)


def claves_desconocidas(texto):
    """Las ``{claves}`` de una plantilla que Sofía no sabe llenar."""
    return sorted({c for c in _CLAVE.findall(texto or '') if c not in CLAVES_DE_PLANTILLA})


def rellenar(plantilla, valores):
    """La plantilla con sus datos. Lo que falta queda vacío y se arreglan los espacios («¡Hola !» → «¡Hola!»)."""
    texto = _CLAVE.sub(lambda m: str(valores.get(m.group(1)) or ''), plantilla or '')
    texto = re.sub(r'[ \t]+', ' ', texto)
    texto = re.sub(r' +([!?.,;:])', r'\1', texto)
    texto = re.sub(r'([¡¿]) +', r'\1', texto)
    return '\n'.join(linea.strip() for linea in texto.splitlines()).strip()


def sin_canal(texto, canales):
    """Lo que le interesó, sin el canal delante: «WhatsApp (QR): colchón queen» → «colchón queen» (Juan nombra así las
    oportunidades; si el canal del chat cambió o alguien la renombró, el prefijo puede ser de otro canal)."""
    texto = (texto or '').strip()
    for canal in canales:
        if texto.casefold().startswith(f'{canal}:'.casefold()):
            return texto[len(canal) + 1:].strip()
    return texto


def sin_montos(texto):
    """El texto tal cual, o vacío si trae un monto o un precio («sofá $899», «unos 450.00»)."""
    texto = ' '.join(str(texto or '').split())
    return '' if _MONTO.search(texto) else texto


def correos_en(texto):
    """Los correos que aparecen en un mensaje, en el orden en que aparecen y sin repetir."""
    vistos = []
    for encontrado in _CORREO.findall(texto or ''):
        correo = encontrado.strip('.').lower()
        if correo not in vistos:
            vistos.append(correo)
    return vistos


# ---------------------------------------------------------------------------
# Los datos que el cliente contestó (nombre y apellido, correo, cumpleaños)
# ---------------------------------------------------------------------------

MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'jun': 6, 'jul': 7, 'ago': 8, 'sep': 9, 'sept': 9, 'set': 9, 'oct': 10,
    'nov': 11, 'dic': 12,
}
DIAS_DEL_MES = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
# Palabras que van en minúscula dentro de un nombre («María de los Ángeles», «Juan del Carmen»).
PARTICULAS = frozenset({'de', 'del', 'la', 'las', 'los', 'y', 'e', 'da', 'das', 'do', 'dos', 'van', 'von', 'di'})
# Lo que contesta la gente y no es un nombre («Hola buenas», «Ok gracias», «Sí claro»).
NO_ES_RESPUESTA_DE_NOMBRE = frozenset({
    'hola', 'buenas', 'buenos', 'buen', 'dia', 'día', 'dias', 'días', 'tardes', 'noches', 'gracias', 'ok', 'okay',
    'si', 'sí', 'no', 'claro', 'listo', 'perfecto', 'vale', 'bueno', 'bien', 'saludos', 'bendiciones', 'favor',
    'correo', 'email', 'mail', 'nombre', 'apellido', 'cumpleaños', 'cumple', 'fecha', 'nacimiento', 'cel', 'celular',
    'whatsapp', 'precio', 'cuanto', 'cuánto', 'quiero', 'tienen', 'hay', 'disponible', 'cotizacion', 'cotización',
    # «soy de La Chorrera», «me interesa», «es para mi casa»: una frase, no un nombre
    'soy', 'me', 'llamo', 'es', 'el', 'yo', 'un', 'una', 'aqui', 'aquí', 'interesa', 'casa',
    # «Mañana paso», «Ahorita voy», «Ya listo»
    'mañana', 'hoy', 'luego', 'ahorita', 'ahora', 'después', 'despues', 'paso', 'voy', 'ya', 'tarde',
    # muebles, medidas y colores: «cama queen gris» no es un nombre
    'cama', 'camas', 'sofa', 'sofá', 'sofás', 'mueble', 'muebles', 'colchon', 'colchón', 'mesa', 'silla', 'sillas',
    'comedor', 'juego', 'sala', 'closet', 'clóset', 'ropero', 'escritorio', 'gavetero', 'base', 'cabecera',
    'queen', 'king', 'full', 'twin', 'matrimonial', 'sencilla', 'doble', 'gris', 'negro', 'negra', 'blanco', 'blanca',
    'beige', 'azul', 'cafe', 'café', 'marron', 'marrón', 'madera', 'tela', 'cuero', 'entrega', 'envio', 'envío',
})
# Al leer un nombre, aquí empieza otra cosa («me llamo Ana Pérez y mi correo es…»).
CORTE_DEL_NOMBRE = frozenset({'mi', 'correo', 'email', 'mail', 'cumplo', 'cumpleaños', 'naci', 'nací', 'tel', 'cel',
                              'celular', 'gracias', 'para', 'por', 'con', 'que', 'pero', 'me', 'es', 'soy', 'estoy',
                              'quiero', 'tengo', 'busco', 'necesito', 'vivo', 'desde', 'en', 'a', 'al'})
# Un mensaje que PIDE sus datos: nombra el dato («tu nombre», «nombre y apellido», «tu correo»…) y lo pide (una
# pregunta o «regálame», «compárteme», «indícame»…). «Te envié la cotización a tu correo» no pide nada.
_DATO_PEDIDO = re.compile(r'(?:tu|su)\s+(?:nombre|apellido|correo|e-?mail|cumplea)|nombre\s+y\s+apellido|'
                          r'nombre\s+completo|d[ií]a\s+y\s+(?:el\s+)?mes', re.IGNORECASE)
_VERBO_DE_PEDIR = re.compile(r'\?|regal|compart|indic|facilit|d[ií]me|d[aá]me|p[aá]same|escr[ií]beme|env[ií]ame|'
                             r'confirm', re.IGNORECASE)
_NOMBRE_DICHO = re.compile(
    r'(?:me\s+llamo|mi\s+nombre(?:\s+completo)?\s+es|nombre(?:\s+completo)?\s*[:=])\s*(?P<nombre>[^\n,.;:0-9@()]+)',
    re.IGNORECASE)
_SOY = re.compile(r'(?:^|[\s,.;])soy\s+(?P<nombre>[^\n,.;:0-9@()]+)', re.IGNORECASE)
# «cumplo el 12 de marzo», «mi cumpleaños es…», «nací el…» (no «fecha» a secas ni «nacional»: una entrega también
# tiene fecha).
_HABLA_DE_CUMPLE = re.compile(r'\bcumplea[ñn]os|\bcumplo\b|\bmi\s+cumple\b|\bnac[ií](?:\b|da\b|do\b|miento\b)',
                              re.IGNORECASE)
# Quien le pidió sus datos le pidió también el día y el mes de su cumpleaños (la plantilla «Pedir sus datos» lo hace).
_PIDE_EL_CUMPLE = re.compile(r'd[ií]a\s+y\s+(?:el\s+)?mes|fecha\s+de\s+(?:nacimiento|cumplea)|cu[aá]ndo\s+(?:es\s+)?'
                             r'(?:tu\s+|su\s+)?cumple|cu[aá]ndo\s+naci', re.IGNORECASE)
_FECHA_CON_MES = re.compile(r'\b(?P<dia>\d{1,2})\s*(?:de\s+)?(?P<mes>[a-záéíóú]{3,10})\b', re.IGNORECASE)
_MES_Y_DIA = re.compile(r'\b(?P<mes>[a-záéíóú]{3,10})\s+(?P<dia>\d{1,2})\b', re.IGNORECASE)
_FECHA_NUMERICA = re.compile(r'(?<![\d$])(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})(?:[/-](?:\d{2}|\d{4}))?(?![\d/-])')


def pide_datos(texto):
    """¿Un mensaje del equipo (o de Juan) le pide al cliente su nombre, su correo o su cumpleaños?"""
    texto = texto or ''
    return bool(_DATO_PEDIDO.search(texto) and _VERBO_DE_PEDIR.search(texto))


def pide_el_cumple(texto):
    """¿Ese mensaje le pide también el día y el mes de su cumpleaños? (si no, una fecha en su respuesta puede ser la
    de la entrega)"""
    return bool(_PIDE_EL_CUMPLE.search(texto or ''))


def nombre_con_formato(texto):
    """«maría DE LOS ángeles pérez» → «María de los Ángeles Pérez» (cada palabra con mayúscula inicial; las
    partículas en minúscula, salvo al empezar; los nombres compuestos con guion, cada parte)."""
    salida = []
    for i, palabra in enumerate(palabras_del_nombre(texto)):
        if i and palabra.casefold() in PARTICULAS:
            salida.append(palabra.casefold())
            continue
        salida.append('-'.join("'".join(trozo[:1].upper() + trozo[1:].lower() for trozo in parte.split("'"))
                               for parte in palabra.split('-')))
    return ' '.join(salida)


def _nombre_valido(candidato, permitir_uno=False):
    """El candidato, recortado donde empieza otra cosa y con formato, si de verdad parece un nombre y apellido (o, con
    ``permitir_uno``, al menos un nombre de pila dicho a propósito: «me llamo Ana»)."""
    palabras = []
    for palabra in palabras_del_nombre(candidato):
        if palabra.casefold() in CORTE_DEL_NOMBRE:
            break
        palabras.append(palabra)
    while palabras and palabras[-1].casefold() in PARTICULAS:   # «Ana Pérez y» → «Ana Pérez»
        palabras.pop()
    if not palabras or palabras[0].casefold() in PARTICULAS \
            or any(p.casefold() in NO_ES_RESPUESTA_DE_NOMBRE for p in palabras):
        return None   # un nombre no empieza con «de» ni «la» («soy de La Chorrera»)
    nombre = ' '.join(palabras)
    motivo = falta_el_nombre(nombre)
    if motivo and not (permitir_uno and motivo == SOLO_EL_NOMBRE):
        return None
    return nombre_con_formato(nombre)


def nombre_en(texto, despues_de_pedirlo=False):
    """El nombre y apellido que el cliente escribió, ya con formato, o ``None``.

    Siempre se lee «me llamo …», «mi nombre es …» o «nombre: …». Solo cuando el mensaje contesta a quien le pidió sus
    datos se acepta también «soy …» o una línea que es solo un nombre y apellido («Ingrid Pérez»)."""
    texto = texto or ''
    for encontrado in _NOMBRE_DICHO.finditer(texto):
        nombre = _nombre_valido(encontrado['nombre'], permitir_uno=True)
        if nombre:
            return nombre
    if not despues_de_pedirlo:
        return None
    for encontrado in _SOY.finditer(texto):
        nombre = _nombre_valido(encontrado['nombre'])
        if nombre:
            return nombre
    for renglon in texto.splitlines():
        linea = _CORREO.sub(' ', renglon).strip()
        if not linea or any(c.isdigit() for c in linea):
            continue
        nombre = _nombre_valido(linea)
        if nombre and len(palabras_del_nombre(linea)) == len(nombre.split()):
            return nombre
    return None


def mejora_el_nombre(actual, nuevo, provisionales=()):
    """¿Vale la pena cambiar el nombre de la ficha por ``nuevo``? Solo si el de ahora no sirve y el nuevo es mejor: un
    nombre y apellido siempre; un nombre solo, únicamente en lugar de un emoji, una frase o nada (nunca en lugar de
    otro nombre de pila)."""
    motivo_actual = falta_el_nombre(actual, provisionales)
    if not nuevo or not motivo_actual:
        return False
    if not falta_el_nombre(nuevo):
        return True
    return motivo_actual != SOLO_EL_NOMBRE


def _mes(palabra):
    return MESES.get(unicodedata.normalize('NFKD', palabra.casefold()).encode('ascii', 'ignore').decode()) \
        or MESES.get(palabra.casefold())


def _como_cumple(dia, mes):
    if not (1 <= mes <= 12 and 1 <= dia <= DIAS_DEL_MES[mes - 1]):
        return None
    return f'{mes:02d}-{dia:02d}'


def cumple_en(texto, despues_de_pedirlo=False):
    """El cumpleaños que el cliente escribió, como lo guarda Socios (``MM-DD``), o ``None``.

    «12 de marzo», «marzo 12», «12/03» o «12-03-1990» (día primero, como en Panamá). Solo si el mensaje habla de su
    cumpleaños o de cuándo nació, o contesta a quien le pidió sus datos. Nunca con un precio en el mensaje."""
    texto = texto or ''
    if '$' in texto or not (despues_de_pedirlo or _HABLA_DE_CUMPLE.search(texto)):
        return None
    for patron in (_FECHA_CON_MES, _MES_Y_DIA):
        for encontrado in patron.finditer(texto):
            mes = _mes(encontrado['mes'])
            if mes:
                cumple = _como_cumple(int(encontrado['dia']), mes)
                if cumple:
                    return cumple
    for encontrado in _FECHA_NUMERICA.finditer(texto):
        cumple = _como_cumple(int(encontrado['dia']), int(encontrado['mes']))
        if cumple:
            return cumple
    return None


def cumple_para_mostrar(cumple):
    """``03-12`` → ``12/03`` (día y mes, como se lee en Panamá)."""
    if not cumple or len(cumple) != 5:
        return ''
    return f'{cumple[3:]}/{cumple[:2]}'


def datos_en(mensajes):
    """``{nombre, correo, cumple}`` que el cliente escribió en ``mensajes``, del más nuevo al más viejo: de cada dato,
    el más reciente. El correo, escrito como se guarda (minúsculas, bien escrito).

    Cada mensaje es ``(texto, despues_de_pedirlo, despues_de_pedir_el_cumple)``: si contesta a quien le pidió sus datos
    (y su cumpleaños) se lee con más soltura."""
    datos = {}
    for texto, despues, despues_cumple in mensajes:
        if 'nombre' not in datos:
            nombre = nombre_en(texto, despues)
            if nombre:
                datos['nombre'] = nombre
        if 'correo' not in datos:
            for escrito in correos_en(texto):
                correo = B.correo_limpio(escrito)
                if correo:
                    datos['correo'] = correo
                    break
        if 'cumple' not in datos:
            cumple = cumple_en(texto, despues_cumple)
            if cumple:
                datos['cumple'] = cumple
    return datos


def prioridad(tipo, temperatura=None, vence_hoy=False):
    """Qué tan urgente es una propuesta: 3 «Hoy sin falta», 2 «Hoy», 1 «Cuando puedas»."""
    caliente = temperatura == CRM.CALIENTE
    if tipo == 'contestar':
        return ALTA
    if tipo == 'vence':
        return ALTA if vence_hoy else MEDIA
    if tipo in ('escribir', 'asignar'):
        return ALTA if caliente else MEDIA if temperatura == CRM.TIBIO else BAJA
    if tipo in ('llamar', 'pedir_datos'):
        return MEDIA if caliente else BAJA
    if tipo == 'guardar_datos':
        return MEDIA if temperatura in (CRM.TIBIO, CRM.CALIENTE) else BAJA
    return BAJA
