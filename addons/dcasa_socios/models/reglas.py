"""Las reglas del programa Socios D'CASA, y la aritmética que las aplica.

Traducción a Python de ``compartido/`` del repositorio DCasa-Referidos (Abrinay).
Todo lo de aquí es PURO: entra un número y unas reglas, sale un número. No toca
la base ni lee la hora. Por eso se prueba entero, y por eso la misma función
calcula los puntos en la pantalla de la vendedora y en el asiento que se escribe.

NINGUNA CIFRA ESTÁ ESCRITA AQUÍ. Todas vienen de ``data/puntos.json``, que es la
única fuente y vive en git: cambiar la economía del programa es un commit con
autor y fecha, no un campo que alguien toca en una pantalla.
"""

import json
import re
import secrets
from datetime import timedelta
from pathlib import Path

PUNTOS_JSON = Path(__file__).resolve().parent.parent / 'data' / 'puntos.json'

# Códigos de socio y de canje: sin ninguna pareja que se confunda al dictarlos
# por teléfono o leerlos en una pantalla rayada (sin O/0, sin I/1/L).
ALFABETO_CODIGO = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'
PREFIJO_CODIGO = 'DCA'
LARGO_CODIGO = 6
LARGO_CODIGO_CANJE = 6
LARGO_PIN = 6
VERSION_TERMINOS = 1

# El candado contra fuerza bruta del PIN: a los 5 fallos, 15 minutos; a los 10, 24 horas.
ESCALONES_CANDADO = ((5, 15), (10, 60 * 24))


class FaltaConfigurar(Exception):
    """La economía está a medio definir: se lanza en vez de devolver cero.

    Un cero se suma sin protestar y deja la compra dando nada, que es el fallo
    silencioso que nadie descubre hasta que un cliente reclama.
    """

    def __init__(self, campo, mensaje):
        super().__init__(mensaje)
        self.campo = campo


def cargar_reglas(ruta=PUNTOS_JSON):
    with open(ruta, encoding='utf-8') as archivo:
        return json.load(archivo)


# ---------------------------------------------------------------------------
# Puntos
# ---------------------------------------------------------------------------

def falta_para_acreditar(reglas):
    falta = []
    a = reglas['acumulacion']
    if a.get('puntosPorDolar') is None:
        falta.append('acumulacion.puntosPorDolar: falta definir cuántos puntos da cada dólar.')
    elif not a['puntosPorDolar'] > 0:
        falta.append('acumulacion.puntosPorDolar tiene que ser mayor que cero.')
    if a.get('baseDeCalculo') not in ('total', 'subtotal'):
        falta.append('acumulacion.baseDeCalculo: falta decidir si los puntos salen del total o del subtotal.')
    return falta


def falta_para_referir(reglas):
    if reglas['referido'].get('puntosAlPadrino') is None:
        return ['referido.puntosAlPadrino: falta definir cuánto gana quien trae a alguien.']
    return []


def base_de_compra(monto_centavos, reglas):
    """Sobre cuánto se calculan los puntos, en centavos enteros de principio a fin."""
    if not isinstance(monto_centavos, int) or isinstance(monto_centavos, bool) or monto_centavos <= 0:
        raise ValueError('El monto de una compra va en centavos enteros y mayores que cero.')
    a = reglas['acumulacion']
    if a['baseDeCalculo'] == 'total':
        return monto_centavos
    if a['baseDeCalculo'] == 'subtotal':
        # Redondeo "mitad hacia arriba" como Math.round de JavaScript.
        return (monto_centavos * 100 * 2 + (100 + a['itbmsPorcentaje'])) // (2 * (100 + a['itbmsPorcentaje']))
    raise FaltaConfigurar('acumulacion.baseDeCalculo', 'Falta decidir si los puntos salen del total o del subtotal.')


def puntos_de_compra(monto_centavos, reglas):
    """Cuántos puntos da una compra. Redondea SIEMPRE hacia abajo."""
    falta = falta_para_acreditar(reglas)
    if falta:
        raise FaltaConfigurar('acumulacion', ' '.join(falta))
    a = reglas['acumulacion']
    minimo = a.get('compraMinimaCentavos')
    if minimo is not None and monto_centavos < minimo:
        return 0
    base = base_de_compra(monto_centavos, reglas)
    # Entero × número puede ser fraccionario (p. ej. 1.5 puntos por dólar): floor explícito.
    puntos = int((base * a['puntosPorDolar']) // 100)
    tope = a.get('puntosMaximosPorCompra')
    if tope is not None and puntos > tope:
        return tope
    return puntos


def saldo(asientos):
    """El saldo es la suma del libro mayor, y nada más."""
    return sum(asiento for asiento in asientos)


def faltan_para(saldo_actual, puntos_del_premio):
    return max(0, puntos_del_premio - saldo_actual)


def como_dolares(centavos):
    signo = '-' if centavos < 0 else ''
    enteros, resto = divmod(abs(centavos), 100)
    return f'{signo}${enteros:,}.{resto:02d}'


def como_puntos(puntos):
    return f'{puntos:,}'


def a_centavos(monto):
    """Un importe de Odoo (float con 2 decimales) a centavos enteros sin error de coma flotante."""
    return int(round(round(float(monto), 2) * 100))


# ---------------------------------------------------------------------------
# Códigos
# ---------------------------------------------------------------------------

def nuevo_codigo_socio():
    return PREFIJO_CODIGO + ''.join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))


def nuevo_codigo_canje():
    return ''.join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO_CANJE))


def codigo_normal(valor):
    return re.sub(r'[\s-]', '', valor or '').upper()


def es_codigo_valido(codigo):
    return (
        len(codigo) == len(PREFIJO_CODIGO) + LARGO_CODIGO
        and codigo.startswith(PREFIJO_CODIGO)
        and all(c in ALFABETO_CODIGO for c in codigo[len(PREFIJO_CODIGO):])
    )


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

def solo_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def celular_normal(valor):
    """Los ocho dígitos nacionales: '+507 6026-1919' y '60261919' son la misma persona."""
    digitos = solo_digitos(valor)
    return digitos[-8:] if len(digitos) > 8 else digitos


def celular_fmt(normal):
    """'61234567' → '6123-4567', como se escribe en Panamá."""
    return f'{normal[:4]}-{normal[4:]}' if normal and len(normal) == 8 else (normal or '')


def celular_valido(normal):
    return bool(re.fullmatch(r'[234567]\d{7}', normal or ''))


EXPLICACION_PIN = {
    'largo': f'Tu PIN son {LARGO_PIN} números.',
    'no-son-digitos': 'El PIN son solo números, sin letras ni espacios.',
    'repetidos': 'Ese PIN es muy fácil de adivinar. Usa números distintos.',
    'secuencia': 'Ese PIN es muy fácil de adivinar. Evita los números seguidos.',
    'es-el-telefono': 'No uses parte de tu número de celular: es lo primero que alguien probaría.',
}


def problema_del_pin(pin, celular=''):
    valor = (pin or '').strip()
    if len(valor) != LARGO_PIN:
        return 'largo'
    if not valor.isdigit():
        return 'no-son-digitos'
    if len(set(valor)) == 1:
        return 'repetidos'
    digitos = [int(d) for d in valor]
    if all(i == 0 or d == digitos[i - 1] + 1 for i, d in enumerate(digitos)) or \
       all(i == 0 or d == digitos[i - 1] - 1 for i, d in enumerate(digitos)):
        return 'secuencia'
    for i in range(len(celular) - LARGO_PIN + 1):
        if celular[i:i + LARGO_PIN] == valor:
            return 'es-el-telefono'
    return None


def cumple_valido(valor):
    """'MM-DD' u opcional (vacío). Sin año: no hace falta para felicitar a nadie."""
    v = (valor or '').strip()
    if not v:
        return True
    partes = re.fullmatch(r'(\d{2})-(\d{2})', v)
    if not partes:
        return False
    mes, dia = int(partes[1]), int(partes[2])
    if not 1 <= mes <= 12 or dia < 1:
        return False
    return dia <= (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[mes - 1]


def nombre_publico(nombre, apellido=''):
    """De un tercero solo salen el nombre y la inicial del apellido."""
    nombre = (nombre or '').strip()
    apellido = (apellido or '').strip()
    return f'{nombre} {apellido[0].upper()}.' if apellido else nombre


# ---------------------------------------------------------------------------
# Facturas
# ---------------------------------------------------------------------------

def factura_normal(valor):
    """'F-001234', 'f 001234' y 'F1234' son la misma factura: una factura, una carga."""
    limpia = re.sub(r'[\s\-_./]', '', (valor or '').upper())
    return re.sub(r'^([A-Z]*)0+(?=\d)', r'\1', limpia)


# ---------------------------------------------------------------------------
# Candado del PIN
# ---------------------------------------------------------------------------

def bloqueo_tras(fallos, ahora):
    minutos = 0
    for umbral, duracion in ESCALONES_CANDADO:
        if fallos >= umbral:
            minutos = duracion
    return ahora + timedelta(minutes=minutos) if minutos else None


def sigue_bloqueada(bloqueado_hasta, ahora):
    return bool(bloqueado_hasta) and bloqueado_hasta > ahora


def cuanto_queda(bloqueado_hasta, ahora):
    minutos = -(-int((bloqueado_hasta - ahora).total_seconds()) // 60)
    if minutos <= 1:
        return 'un minuto'
    if minutos < 60:
        return f'{minutos} minutos'
    horas = -(-minutos // 60)
    return 'una hora' if horas == 1 else f'{horas} horas'
