"""Piezas PURAS (sin base de datos) de los avisos por Telegram: todos con la misma forma (título con su emoji, quién y
por dónde, qué pasó, qué hacer). Los textos viven en ``conversacion_avisos.py`` y donde nace cada aviso."""

# Lo que se copia de una nota o de lo que anotó Juan en un aviso (el completo está en la conversación).
MAX_EN_EL_AVISO = 300


def armar(*lineas):
    """Las líneas del aviso, una debajo de otra; las vacías no cuentan."""
    return '\n'.join(linea for linea in lineas if linea)


def frase(texto, maximo=MAX_EN_EL_AVISO, punto=True):
    """Un texto suelto (lo que anotó Juan, una nota) como frase: sin saltos ni espacios de más, recortado y (si
    ``punto``) con su punto final."""
    limpio = ' '.join(str(texto or '').split())
    if len(limpio) > maximo:
        limpio = f'{limpio[:maximo - 1].rstrip()}…'
    if punto and limpio and limpio[-1] not in '.!?…':
        limpio = f'{limpio}.'
    return limpio
