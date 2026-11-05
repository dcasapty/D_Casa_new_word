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
        return 'solo tiene un nombre: falta el apellido'
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
    if motivo and motivo != 'solo tiene un nombre: falta el apellido':
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
    return BAJA
