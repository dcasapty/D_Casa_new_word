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


# Caracteres invisibles (espacio de ancho cero, cambio de dirección del texto…): nunca van en un nombre.
INVISIBLES = frozenset({'Cf', 'Cc', 'Cn'})


def _es_emoji_o_simbolo(caracter):
    return unicodedata.category(caracter) in ('So', 'Sk', 'Cs', 'Co', *INVISIBLES) or ord(caracter) >= 0x1F000


def palabras_del_nombre(nombre):
    """Las palabras con letras de un nombre, sin signos alrededor («Ana,» → «Ana»)."""
    palabras = []
    visible = ''.join(c if unicodedata.category(c) not in INVISIBLES else ' ' for c in (nombre or ''))
    for parte in visible.split():
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
        local, dominio = encontrado.strip('.').split('@', 1)
        partes = dominio.split('.')
        # «ana@empresa.com.Saludos» → ana@empresa.com (pero «ana@empresa.com.pa» se queda entero)
        while len(partes) > 2 and partes[-1][:1].isupper() and len(partes[-1]) > 3:
            partes.pop()
        correo = f'{local}@{".".join(partes)}'.lower()
        if correo not in vistos:
            vistos.append(correo)
    return vistos


# ---------------------------------------------------------------------------
# Los datos que el cliente contestó (nombre y apellido, correo, cumpleaños)
# ---------------------------------------------------------------------------

MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
    # abreviaturas (no «mar», «ago» ni «set»: son palabras de todos los días, como en «set 2»)
    'ene': 1, 'feb': 2, 'abr': 4, 'jun': 6, 'jul': 7, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dic': 12,
}
MAX_LETRAS_POR_MENSAJE = 2000   # una respuesta con sus datos es corta; un texto enorme no se lee entero
DIAS_DEL_MES = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
# Palabras que van en minúscula dentro de un nombre («María de los Ángeles», «Juan del Carmen»).
PARTICULAS = frozenset({'de', 'del', 'la', 'las', 'los', 'y', 'van', 'von'})
# Lo que contesta la gente y no es un nombre («Hola buenas», «Ok gracias», «Sí claro»).
NO_ES_RESPUESTA_DE_NOMBRE = frozenset({
    'hola', 'buenas', 'buenos', 'buen', 'dia', 'día', 'dias', 'días', 'tardes', 'noches', 'gracias', 'ok', 'okay',
    'si', 'sí', 'no', 'claro', 'listo', 'perfecto', 'vale', 'bueno', 'bien', 'saludos', 'bendiciones', 'favor',
    'correo', 'email', 'mail', 'nombre', 'apellido', 'cumpleaños', 'cumple', 'fecha', 'nacimiento', 'cel', 'celular',
    'whatsapp', 'precio', 'cuanto', 'cuánto', 'quiero', 'tienen', 'hay', 'disponible', 'cotizacion', 'cotización',
    # «soy de La Chorrera», «me interesa», «es para mi casa»: una frase, no un nombre
    'soy', 'me', 'llamo', 'es', 'el', 'yo', 'un', 'una', 'aqui', 'aquí', 'interesa', 'casa',
    # «Mañana paso», «Ahorita voy», «Ya listo», «Te aviso», «Lo pienso», «Muy amable», «Excelente servicio»
    'mañana', 'hoy', 'luego', 'ahorita', 'ahora', 'después', 'despues', 'paso', 'voy', 'ya', 'tarde', 'ayer',
    'te', 'lo', 'le', 'se', 'aviso', 'pienso', 'muy', 'amable', 'excelente', 'servicio', 'atención', 'atencion',
    'caro', 'cara', 'barato', 'barata', 'mandame', 'mándame', 'envíame', 'enviame', 'foto', 'fotos', 'mucho',
    'nadie', 'todo', 'nada', 'igual', 'tambien', 'también', 'exacto', 'entendido', 'dale', 'genial', 'super', 'súper',
    # «Ella se llama Ana Gómez» es otra persona
    'ella', 'él', 'llama', 'esposo', 'esposa', 'hijo', 'hija', 'mamá', 'mama', 'papá', 'papa',
    # una dirección no es un nombre («Calle Principal», «Puerto Caimito»)
    'calle', 'avenida', 'ave', 'vía', 'via', 'puerto', 'barrio', 'barriada', 'urbanización', 'urbanizacion', 'sector',
    'edificio', 'apartamento', 'apto', 'local', 'frente', 'cerca', 'chorrera', 'arraiján', 'arraijan',
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
# Un mensaje que PIDE sus datos: un verbo de pedir junto al dato («¿me regalas tu nombre…?», «compárteme tu correo»,
# «¿cuál es tu correo?», «tu nombre completo, por favor»). «Te envié la cotización a tu correo, ¿la recibiste?» o «la
# factura sale a su nombre, ¿verdad?» no piden nada.
_DATO = r'(?:tu|su)\s+(?:nombre|apellido|correo|e-?mail|cumplea[ñn]os|fecha)'
_PIDE_UN_DATO = re.compile(
    r'(?:reg[aá]l\w*|comp[aá]rt\w*|ind[ií]c\w*|facil[ií]t\w*|confirm[aá](?:me|nos|s)?|d[ií]me|d[aá]me|p[aá]same|'
    r'escr[ií]beme|env[ií]ame|me\s+(?:das|dices|pasas|escribes|env[ií]as))\s+(?:\w+\s+){0,3}?' + _DATO
    + r'|cu[aá]l\s+es\s+' + _DATO + r'|' + _DATO + r'(?:\s+completo)?\s*(?:,\s*)?(?:por\s+favor|\?)',
    re.IGNORECASE)
_NOMBRE_DICHO = re.compile(
    r'(?:(?<!no\s)me\s+llamo|mi\s+nombre(?:\s+completo)?\s+es|nombre(?:\s+completo)?\s*[:=])\s*(?P<nombre>[^\n,.;:0-9@()]+)',
    re.IGNORECASE)
_SOY = re.compile(r'(?:^|[\s,.;])soy\s+(?P<nombre>[^\n,.;:0-9@()]+)', re.IGNORECASE)
# SU cumpleaños: «cumplo el 12 de marzo», «mi cumpleaños es…», «nací el…» (no «fecha» a secas, ni «cumplo con el
# abono», ni el cumpleaños de otra persona: una entrega también tiene fecha).
_HABLA_DE_CUMPLE = re.compile(r'\bmi\s+cumplea[ñn]os|\bmi\s+cumple\b|\bcumplo\s+(?:a[ñn]os\b|el\b|en\b|\d)|\bnac[ií]\b|'
                              r'\bmi\s+fecha\s+de\s+nacimiento', re.IGNORECASE)
# El mensaje habla de otra persona («el cumpleaños de mi mamá», «nacimiento de mi bebé»): esa fecha no es la suya.
_OTRA_PERSONA = re.compile(r'\b(?:mam[aá]|pap[aá]|madre|padre|hij[oa]s?|espos[oa]|beb[eé]|novi[oa]|herman[oa]|'
                           r'abuel[oa]|amig[oa]|t[ií][oa]|prim[oa]|suegr[oa]|sobrin[oa]|niet[oa]|jef[ea]|cuñad[oa])\b',
                           re.IGNORECASE)
# Lo que puede acompañar a la fecha en una línea que es solo su cumpleaños («el 12 de marzo», «mi cumple: 12/03»).
_RELLENO_DE_LA_FECHA = frozenset({'el', 'de', 'del', 'mi', 'cumple', 'cumpleaños', 'es', 'fecha', 'nacimiento', 'día',
                                  'dia', 'y', 'mes', 'año', 'ano'})
_ANO = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')   # el año en que nació («del 1985»): no se guarda, pero no estorba
# Quien le pidió sus datos le pidió también el día y el mes de su cumpleaños (la plantilla «Pedir sus datos» lo hace).
_PIDE_EL_CUMPLE = re.compile(r'd[ií]a\s+y\s+(?:el\s+)?mes|fecha\s+de\s+(?:nacimiento|cumplea)|cu[aá]ndo\s+(?:es\s+)?'
                             r'(?:tu\s+|su\s+)?cumple|cu[aá]ndo\s+naci', re.IGNORECASE)
_FECHA_CON_MES = re.compile(r'\b(?P<dia>\d{1,2})\s*(?:de\s+)?(?P<mes>[a-záéíóú]{3,10})\b', re.IGNORECASE)
_MES_Y_DIA = re.compile(r'\b(?P<mes>[a-záéíóú]{3,10})\s+(?P<dia>\d{1,2})\b', re.IGNORECASE)
_FECHA_NUMERICA = re.compile(r'(?<![\d$])(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})(?:[/-](?:\d{2}|\d{4}))?(?![\d/-])')


def pide_datos(texto):
    """¿Un mensaje del equipo (o de Juan) le pide al cliente su nombre, su correo o su cumpleaños?"""
    return bool(_PIDE_UN_DATO.search(texto or ''))


def pide_el_cumple(texto):
    """¿Ese mensaje le pide también el día y el mes de su cumpleaños? (si no, una fecha en su respuesta puede ser la
    de la entrega)"""
    return bool(_PIDE_EL_CUMPLE.search(texto or ''))


def nombre_con_formato(texto):
    """«maría DE LOS ángeles pérez» → «María de los Ángeles Pérez» (cada palabra con mayúscula inicial; las
    partículas en minúscula, salvo al empezar; los nombres compuestos con guion, cada parte)."""
    palabras = palabras_del_nombre(texto)
    while len(palabras) > 1 and palabras[-1].casefold() in PARTICULAS:   # «Ana Pérez y» → «Ana Pérez»
        palabras.pop()
    salida = []
    for i, palabra in enumerate(palabras):
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
    datos se acepta también «soy …» o una línea que es solo un nombre y apellido («Marisol Pérez»)."""
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
    otro nombre de pila). Si la ficha ya tiene un nombre de pila, el nuevo tiene que llevarlo («Ana» → «Ana Pérez»,
    nunca «Ana» → «Carla Ruiz»)."""
    motivo_actual = falta_el_nombre(actual, provisionales)
    if not nuevo or not motivo_actual:
        return False
    if motivo_actual == SOLO_EL_NOMBRE:
        pila = _sin_tildes(palabras_del_nombre(actual)[0])
        return not falta_el_nombre(nuevo) and pila in {_sin_tildes(p) for p in palabras_del_nombre(nuevo)}
    return not falta_el_nombre(nuevo) or falta_el_nombre(nuevo) == SOLO_EL_NOMBRE


def _sin_tildes(palabra):
    return unicodedata.normalize('NFKD', palabra.casefold()).encode('ascii', 'ignore').decode()


def _mes(palabra):
    return MESES.get(_sin_tildes(palabra)) or MESES.get(palabra.casefold())


def _como_cumple(dia, mes):
    if not (1 <= mes <= 12 and 1 <= dia <= DIAS_DEL_MES[mes - 1]):
        return None
    return f'{mes:02d}-{dia:02d}'


def _fechas_en(linea):
    """``(cumple, lo demás de la línea)`` por cada fecha que existe en la línea, en orden de preferencia."""
    for patron, numerico in ((_FECHA_CON_MES, False), (_MES_Y_DIA, False), (_FECHA_NUMERICA, True)):
        for encontrado in patron.finditer(linea):
            mes = int(encontrado['mes']) if numerico else _mes(encontrado['mes'])
            cumple = mes and _como_cumple(int(encontrado['dia']), mes)
            if cumple:
                yield cumple, f'{linea[:encontrado.start()]} {linea[encontrado.end():]}'


def _solo_la_fecha(resto):
    """¿Lo demás de la línea es relleno («el», «de», «mi cumple»…) o el año en que nació, sin otras palabras ni
    números? Se perdona el «del» mal escrito y pegado al año («7 de marzo deln1990»: así llegó un caso real,
    2026-11-05)."""
    resto = _ANO.sub(' ', resto)
    return not any(c.isdigit() for c in resto) and all(
        palabra.casefold() in _RELLENO_DE_LA_FECHA or (len(palabra) <= 4 and palabra.casefold().startswith('de'))
        for palabra in re.findall(r'[^\W\d_]+', resto))


def cumple_en(texto, despues_de_pedirlo=False):
    """El cumpleaños que el cliente escribió, como lo guarda Socios (``MM-DD``), o ``None``.

    «12 de marzo», «marzo 12», «12/03» o «12-03-1990» (día primero, como en Panamá). Si el mensaje dice que es SU
    cumpleaños («cumplo el…», «mi cumpleaños es…», «nací el…»). Contestando a quien le pidió el día y el mes, también
    una línea que es solo la fecha («12/03»), nunca una fecha en medio de otra frase («entréguenmelo el 15/11»). Nunca
    con un precio ni si habla de otra persona («el cumpleaños de mi mamá»)."""
    texto = (texto or '')[:MAX_LETRAS_POR_MENSAJE]
    if '$' in texto or _OTRA_PERSONA.search(texto):
        return None
    dice_que_es_suyo = bool(_HABLA_DE_CUMPLE.search(texto))
    if not (dice_que_es_suyo or despues_de_pedirlo):
        return None
    for linea in texto.splitlines():
        for cumple, resto in _fechas_en(linea):
            if dice_que_es_suyo or _solo_la_fecha(resto):
                return cumple
    return None


def cumple_para_mostrar(cumple):
    """``03-12`` → ``12/03`` (día y mes, como se lee en Panamá)."""
    if not cumple or len(cumple) != 5:
        return ''
    return f'{cumple[3:]}/{cumple[:2]}'


def datos_en(mensajes, correos_que_no=()):
    """``{nombre, correo, cumple}`` que el cliente escribió en ``mensajes``, del más nuevo al más viejo: de cada dato,
    el más reciente. El correo, escrito como se guarda (minúsculas, bien escrito).

    Cada mensaje es ``(texto, despues_de_pedirlo, despues_de_pedir_el_cumple)``: si contesta a quien le pidió sus datos
    (y su cumpleaños) se lee con más soltura. ``correos_que_no``: los del equipo (se sigue buscando el suyo)."""
    datos = {}
    for escrito_completo, despues, despues_cumple in mensajes:
        texto = (escrito_completo or '')[:MAX_LETRAS_POR_MENSAJE]
        if 'nombre' not in datos:
            nombre = nombre_en(texto, despues)
            if nombre:
                datos['nombre'] = nombre
        if 'correo' not in datos:
            for escrito in correos_en(texto):
                correo = B.correo_limpio(escrito)
                if correo and correo not in correos_que_no:
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
