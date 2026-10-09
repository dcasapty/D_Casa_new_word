"""Las reglas de Socios D'CASA redactadas para un CLIENTE, a partir de ``puntos.json``.

Regla no negociable del programa (CLAUDE.md): **ninguna cifra fuera de ``puntos.json``**. Este módulo
no escribe ni un número: cada cifra que sale en una frase viene de las reglas que se le pasan. Y un
valor ``null`` o ``PENDIENTE`` **no se rellena a ojo**: esa regla no se explica con cifras, se lista en
``pendientes`` y la respuesta dice que la confirma una vendedora.

Función pura: ``redactar(reglas, base_url)`` no toca la base ni lee archivos (el que llama carga
``puntos.json`` con ``dcasa_socios.models.reglas.cargar_reglas``).
"""
from odoo.addons.dcasa_socios.models import reglas as R

PENDIENTE = 'PENDIENTE'


def _falta(valor):
    return valor is None or (isinstance(valor, str) and PENDIENTE in valor.upper())


def _puntos(n):
    return f'{R.como_puntos(n)} {"punto" if n == 1 else "puntos"}'


def _pendientes(reglas):
    """Rutas (``seccion.clave``) con valor ``null`` o ``PENDIENTE``, sin contar los comentarios ``$…``."""
    faltan = []
    for seccion, contenido in reglas.items():
        if seccion.startswith('$') or not isinstance(contenido, dict):
            continue
        for clave, valor in contenido.items():
            if not clave.startswith('$') and _falta(valor):
                faltan.append(f'{seccion}.{clave}')
    return faltan


def _como_se_ganan(reglas):
    lineas, cifras = [], {}
    acum = reglas.get('acumulacion', {})
    por_dolar = acum.get('puntosPorDolar')
    if not _falta(por_dolar):
        sobre = {'total': ', con el ITBMS incluido', 'subtotal': ', sobre el precio antes del ITBMS'}.get(
            acum.get('baseDeCalculo'), '')
        lineas.append(f'Ganas {_puntos(por_dolar)} por cada dólar que pagas{sobre}.')
        cifras['puntos_por_dolar'] = por_dolar
        if acum.get('redondeo') == 'abajo':
            lineas.append('Los puntos se redondean siempre hacia abajo.')
    minima = acum.get('compraMinimaCentavos')
    if not _falta(minima) and minima > 0:
        lineas.append(f'Las compras de menos de {R.como_dolares(minima)} se registran pero no dan puntos.')
        cifras['compra_minima'] = R.como_dolares(minima)
    lineas.append('Los puntos se suman cuando la factura queda pagada, no antes.')
    bienvenida = reglas.get('bienvenida', {}).get('puntos')
    if not _falta(bienvenida):
        lineas.append('Registrarte no da puntos: los puntos vienen de tus compras.' if bienvenida == 0
                      else f'Al registrarte recibes {_puntos(bienvenida)}.')
        cifras['puntos_de_bienvenida'] = bienvenida
    return lineas, cifras


def _como_se_usan(reglas):
    lineas, cifras = ['Los puntos se canjean por premios del catálogo.'], {}
    canje = reglas.get('canje', {})
    minimo = canje.get('saldoMinimoParaCanjear')
    if not _falta(minimo):
        lineas.append(f'Para canjear necesitas al menos {_puntos(minimo)}.')
        cifras['saldo_minimo_para_canjear'] = minimo
    equivale = canje.get('puntosPorDolar')
    if not _falta(equivale):
        lineas.append(f'Como referencia, {_puntos(equivale)} valen $1 al canjear.')
        cifras['puntos_por_dolar_al_canjear'] = equivale
    horas = canje.get('vigenciaDelCodigoHoras')
    if not _falta(horas):
        lineas.append(f'El código de canje dura {horas} horas; si no lo usas, tus puntos vuelven a tu saldo.')
        cifras['vigencia_del_codigo_horas'] = horas
    return lineas, cifras


def _referidos(reglas):
    lineas, cifras = [], {}
    ref = reglas.get('referido', {})
    padrino, ahijado = ref.get('puntosAlPadrino'), ref.get('puntosAlAhijado')
    if not _falta(padrino):
        frase = f'Si invitas a alguien con tu enlace, tú ganas {_puntos(padrino)}'
        if not _falta(ahijado):
            frase += f' y tu invitado {_puntos(ahijado)}'
            cifras['puntos_al_invitado'] = ahijado
        lineas.append(frase + ', cuando haga su primera compra que dé puntos (nunca por registrarse).')
        cifras['puntos_al_padrino'] = padrino
    tope_invitados = ref.get('topeDeAhijadosPorPadrino')
    if not _falta(tope_invitados):
        lineas.append(f'Puedes invitar hasta {tope_invitados} personas.')
        cifras['tope_de_invitados'] = tope_invitados
    tope_mes = ref.get('topeDePuntosPorPadrinoAlMes')
    if not _falta(tope_mes):
        lineas.append(f'Por invitados puedes sumar hasta {_puntos(tope_mes)} al mes.')
        cifras['tope_de_puntos_por_invitados_al_mes'] = tope_mes
    return lineas, cifras


def _vencimiento_y_cumpleanos(reglas):
    lineas, cifras = [], {}
    meses = reglas.get('vencimiento', {}).get('meses')
    if meses is None:
        lineas.append('Por ahora tus puntos no tienen fecha de vencimiento.')
    elif not _falta(meses):
        lineas.append(f'Los puntos vencen a los {meses} meses.')
        cifras['vencen_en_meses'] = meses
    cumple = reglas.get('cumpleanos', {}).get('puntos')
    if not _falta(cumple):
        lineas.append(f'En tu cumpleaños recibes {_puntos(cumple)}, una vez al año, '
                      'si ya tienes una compra que dio puntos.')
        cifras['puntos_de_cumpleanos'] = cumple
    return lineas, cifras


def redactar(reglas, base_url=''):
    """Reglas del programa en lenguaje de cliente: ``{version, resumen, cifras, pendientes, enlaces, aviso}``."""
    base = (base_url or '').rstrip('/')
    resumen, cifras = [], {}
    for seccion in (_como_se_ganan, _como_se_usan, _referidos, _vencimiento_y_cumpleanos):
        lineas, valores = seccion(reglas)
        resumen += lineas
        cifras.update(valores)
    # El vencimiento nulo no es una cifra pendiente: se dijo arriba como «sin fecha de vencimiento».
    pendientes = [p for p in _pendientes(reglas) if p != 'vencimiento.meses']
    return {
        'version': reglas.get('version'),
        'resumen': resumen,
        'cifras': cifras,
        'pendientes': pendientes,
        'enlaces': {'registro': f'{base}/socios', 'premios': f'{base}/socios/premios'},
        'aviso': ('Estas son las cifras vigentes del programa. Lo que no aparezca aquí no se afirma: '
                  'lo confirma una vendedora. Los puntos nunca se prometen por una compra sin facturar.'),
    }
