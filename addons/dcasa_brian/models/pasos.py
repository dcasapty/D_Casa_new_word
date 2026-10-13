"""Pasos de Brian «en vivo»: cómo se cuenta cada herramienta mientras trabaja.

Funciones puras (sin Odoo) que arman lo que ve la persona en el panel mientras Brian
responde: el título de un paso («Buscando productos «888K»»), el resumen corto del
resultado («3 resultados») y el detalle expandible (JSON compacto y recortado).

Lo que llega aquí ya pasó por la herramienta como el usuario: es SU dato. Nunca se
inventa nada: si el resultado no trae un texto claro, el resumen dice cuántos elementos
devolvió o simplemente «Listo».
"""
import json

MAX_DETALLE = 600
MAX_RESUMEN = 140
MAX_ARGUMENTO = 40

# Verbos cuyo gerundio no sale de la regla general (ar → ando, er/ir → iendo).
GERUNDIOS = {
    'leer': 'leyendo', 'ver': 'viendo', 'ir': 'yendo', 'proponer': 'proponiendo',
    'sugerir': 'sugiriendo', 'conciliar': 'conciliando', 'deshacer': 'deshaciendo',
}

# Herramientas que no empiezan por un verbo: título fijo.
TITULOS = {
    'pantalla_actual': 'Mirando la pantalla actual',
    'ayuda': 'Repasando qué puedo hacer',
    'fecha': 'Viendo la fecha',
    'reporte_del_dia': 'Armando el reporte del día',
    'resumen_ventas': 'Resumiendo las ventas',
    'resumen_contable': 'Resumiendo la contabilidad',
    'reporte_contable': 'Armando el reporte contable',
    'existencias_bajas': 'Revisando existencias bajas',
    'facturas_pendientes': 'Revisando facturas pendientes',
    'clientes_que_deben': 'Revisando quién debe',
    'antiguedad_saldos': 'Revisando la antigüedad de saldos',
    'movimientos_por_conciliar': 'Revisando movimientos por conciliar',
    'estado_factura_electronica': 'Consultando la factura electrónica',
    'guia_cierre_mes': 'Repasando la guía de cierre de mes',
    'saldo_puntos': 'Consultando el saldo de puntos',
    'pendientes_de_hoy': 'Armando los pendientes de hoy',
    'productos_incompletos': 'Buscando productos incompletos',
    'consumo_de_brian': 'Calculando mi consumo de IA',
}

# Argumentos que identifican lo que se está tocando (el primero que aparezca va en el título).
ARGUMENTOS_CLAVE = ('texto', 'codigo', 'nombre', 'celular', 'referencia', 'cliente', 'producto',
                    'proveedor', 'usuario', 'numero', 'pedido', 'factura', 'importacion_id', 'adjunto')


def gerundio(verbo):
    """«buscar» → «buscando», «leer» → «leyendo». ``None`` si no parece un verbo."""
    verbo = (verbo or '').lower()
    if verbo in GERUNDIOS:
        return GERUNDIOS[verbo]
    if len(verbo) < 4:
        return None
    if verbo.endswith('ar'):
        return verbo[:-2] + 'ando'
    if verbo.endswith(('er', 'ir')):
        return verbo[:-2] + 'iendo'
    return None


def _valor_corto(valor):
    if isinstance(valor, bool) or valor in (None, ''):
        return ''
    if isinstance(valor, (list, dict)):
        return ''
    texto = ' '.join(str(valor).split())
    return texto if len(texto) <= MAX_ARGUMENTO else texto[:MAX_ARGUMENTO - 1] + '…'


def titulo_paso(nombre, argumentos=None):
    """Título humano de un paso: «Buscando productos «888K»», «Creando cotización».

    Pensado para que quien mira el panel entienda qué hace Brian sin ver nombres técnicos.
    """
    nombre = nombre or ''
    argumentos = argumentos if isinstance(argumentos, dict) else {}
    if nombre in TITULOS:
        titulo = TITULOS[nombre]
    else:
        partes = nombre.replace('-', '_').split('_')
        accion = gerundio(partes[0]) if partes else None
        resto = ' '.join(partes[1:]).strip()
        if accion:
            titulo = f'{accion.capitalize()} {resto}'.strip()
        else:
            titulo = f'Usando {" ".join(partes).strip() or "una herramienta"}'
    for clave in ARGUMENTOS_CLAVE:
        valor = _valor_corto(argumentos.get(clave))
        if valor:
            return f'{titulo} «{valor}»'
    return titulo


def _primer_texto(datos):
    """El primer texto corto y útil del resultado, si lo trae."""
    if not isinstance(datos, dict):
        return ''
    for clave in ('resumen', 'mensaje', 'titulo', 'nombre', 'creado', 'estado', 'total'):
        valor = datos.get(clave)
        if isinstance(valor, (str, int, float)) and not isinstance(valor, bool) and str(valor).strip():
            return ' '.join(str(valor).split())
    return ''


def resumen_resultado(resultado):
    """Una línea sobre lo que devolvió la herramienta (sin inventar: texto o conteo)."""
    if not isinstance(resultado, dict):
        return ''
    if resultado.get('requiere_confirmacion'):
        return 'Necesita tu permiso'
    if not resultado.get('ok'):
        texto = ' '.join(str(resultado.get('error') or 'No se pudo').split())
        return texto if len(texto) <= MAX_RESUMEN else texto[:MAX_RESUMEN - 1] + '…'
    datos = resultado.get('datos')
    texto = _primer_texto(datos)
    if not texto and isinstance(datos, dict):
        listas = [(k, v) for k, v in datos.items() if isinstance(v, list)]
        if listas:
            clave, lista = listas[0]
            etiqueta = clave.replace('_', ' ')
            texto = f'{len(lista)} {etiqueta}' if len(lista) != 1 else f'1 {etiqueta.rstrip("s") or etiqueta}'
    texto = texto or 'Listo'
    return texto if len(texto) <= MAX_RESUMEN else texto[:MAX_RESUMEN - 1] + '…'


def detalle_resultado(resultado, limite=MAX_DETALLE):
    """El resultado completo en JSON compacto, recortado: lo que se despliega al expandir."""
    if not isinstance(resultado, dict):
        return ''
    cuerpo = resultado.get('datos') if resultado.get('ok') else {
        k: v for k, v in resultado.items() if k in ('error', 'resumen', 'requiere_confirmacion')}
    if cuerpo in (None, {}, []):
        return ''
    texto = json.dumps(cuerpo, ensure_ascii=False, default=str, indent=1)
    return texto if len(texto) <= limite else texto[:limite] + '\n… [recortado]'
