"""La promoción de envío (p. ej. «Envío Gratis Todo Noviembre»): la cuenta, SIN Odoo y sin el modelo de IA.

Pedido de la dueña (2026-11-12): Juan dice cuánto cuesta el envío y, si hay promoción, cómo le queda al cliente. Ella
lo escribió así en el Conocimiento: «Promoción solo de este mes, del 01/11/2026 al 30/11/2026: Envío Gratis Todo
Noviembre en compras superiores a $200. Ciudad de Panamá y Panamá Oeste: envío GRATIS. Colón y el Interior: te abonamos
$20 de tu flete. No aplica para envíos con colchón». Y: «los precios de envío no cambian. Lo que cambia es el precio de
cómo les queda con la promoción, pero solo por este mes». Decisiones suyas: los $200 se miden **sin ITBMS** (el
subtotal de los productos) y «Ciudad de Panamá» es **toda la provincia de Panamá**.

Por eso el precio del envío (``tarifa.py``) no cambia: esta función recibe ese precio normal y devuelve el precio con la
promoción, lo que se ahorra, por qué aplica o no y la frase lista para el cliente. Reglas:

* La promoción vale del ``desde`` al ``hasta``, ambos incluidos, en la fecha de Panamá (la pone quien llama).
* «Compras superiores a $X» = **estrictamente mayor** que el mínimo, en centavos. Se mide con o sin ITBMS según diga la
  promoción (``mide``).
* Envío gratis si la provincia del lugar (o su distrito) está en la lista de zonas gratis; en el resto, se abona
  ``abono`` del flete. El abono nunca deja el envío en negativo: si el envío cuesta menos que el abono, queda gratis.
* Si la compra lleva colchón y la promoción lo excluye, no aplica.
* Sin compra conocida (todavía no hay cotización) no se dice que aplica: se dicen las condiciones y cuánto quedaría.
* Un envío sin precio, en $0 o negativo no tiene nada que rebajar: nunca sale «te ahorras $0» ni un monto negativo.

El dinero se cuenta en centavos (``Decimal``), nunca con la suma de punto flotante.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .buscador import sin_tildes
from .texto import dinero

MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre')
MIDE = {'sin_itbms': 'sin ITBMS', 'con_itbms': 'con ITBMS'}
CENTAVO = Decimal('0.01')

# Por qué aplica o no (``motivo``).
SIN_PROMOCION = 'sin_promocion'      # no hay una promoción vigente en esa fecha
SIN_PRECIO = 'sin_precio'            # el envío no tiene precio (se cotiza aparte) o es $0: no hay nada que rebajar
ZONA_SIN_BENEFICIO = 'zona'          # el lugar no está en las zonas gratis y la promoción no abona nada en el resto
SIN_COMPRA = 'sin_compra'            # todavía no hay cotización: se dicen las condiciones
COLCHON = 'colchon'                  # la compra lleva colchón y la promoción no aplica con colchón
MONTO = 'monto'                      # la compra no pasa del mínimo
GRATIS = 'gratis'                    # aplica: envío gratis
ABONO = 'abono'                      # aplica: se abona parte del flete


def centavos(valor):
    """Un monto en ``Decimal`` redondeado al centavo (medio centavo hacia arriba)."""
    return Decimal(str(float(valor or 0))).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _clave(texto):
    return ' '.join(sin_tildes(texto).split())


def fecha_texto(desde, hasta):
    """«del 1 al 30 de noviembre» (mismo mes y año), «del 25 de noviembre al 2 de diciembre» (mismo año) o con los años
    si cambia el año."""
    if desde.year != hasta.year:
        return (f'del {desde.day} de {MESES[desde.month - 1]} de {desde.year} '
                f'al {hasta.day} de {MESES[hasta.month - 1]} de {hasta.year}')
    if desde.month != hasta.month:
        return f'del {desde.day} de {MESES[desde.month - 1]} al {hasta.day} de {MESES[hasta.month - 1]}'
    return f'del {desde.day} al {hasta.day} de {MESES[hasta.month - 1]}'


def vigente(promocion, fecha):
    """¿La promoción vale en esa fecha (de Panamá)? Del ``desde`` al ``hasta``, ambos incluidos."""
    return bool(promocion and promocion.get('desde') and promocion.get('hasta')
                and promocion['desde'] <= fecha <= promocion['hasta'])


def zona_de(promocion, prov, dist):
    """``'gratis'`` si la provincia o el distrito del lugar están en las zonas gratis; si no, ``'abono'`` cuando la
    promoción abona algo en el resto, o ``'ninguna'``."""
    provincias = {_clave(p) for p in promocion.get('provincias_gratis') or [] if _clave(p)}
    distritos = {_clave(d) for d in promocion.get('distritos_gratis') or [] if _clave(d)}
    if (_clave(prov) and _clave(prov) in provincias) or (_clave(dist) and _clave(dist) in distritos):
        return GRATIS
    return ABONO if centavos(promocion.get('abono')) > 0 else 'ninguna'


def _con_promocion(precio, zona, abono):
    """El precio del envío si la promoción aplica (nunca negativo)."""
    if zona == GRATIS:
        return Decimal('0.00')
    return max(Decimal('0.00'), precio - abono)


def _vacio(precio):
    return {
        'hay_promocion': False, 'nombre': '', 'motivo': SIN_PROMOCION, 'aplica': False, 'condicional': False,
        'zona': '', 'precio_normal': float(precio) if precio is not None else None,
        'precio_final': float(precio) if precio is not None else None, 'ahorro': 0.0, 'precio_si_aplica': None,
        'compra_medida': None, 'minimo': None, 'mide': '', 'frase': '', 'menciona_gratis': False,
    }


def _precio(precio_envio):
    """El precio del envío en centavos, o ``None`` si no tiene (se cotiza aparte, $0 o negativo: nada que rebajar)."""
    precio = centavos(precio_envio) if precio_envio is not None else None
    return precio if precio is not None and precio > 0 else None


def aplicar(promocion, precio_envio, prov, dist, fecha, compra=None):
    """La promoción aplicada a un envío.

    * ``promocion``: ``{nombre, desde, hasta (date), minimo, mide ('sin_itbms' | 'con_itbms'), provincias_gratis,
      distritos_gratis, abono, excluye_colchon}`` o ``None``.
    * ``precio_envio``: el precio NORMAL del envío (el de la tarifa), o ``None`` si se cotiza aparte. Con $0 o menos no
      hay nada que rebajar (``SIN_PRECIO``).
    * ``prov``, ``dist``: la provincia y el distrito del lugar. ``fecha``: la fecha de Panamá (la de hoy: la promoción
      se ofrece y se suma con la fecha del día en que se suma; ver ``con_lo_prometido`` para lo ya sumado).
    * ``compra``: ``{subtotal_sin_itbms, subtotal_con_itbms, colchon}`` de la cotización (sin contar el envío), o
      ``None`` si todavía no hay cotización.

    Devuelve ``{hay_promocion, nombre, motivo, aplica, condicional, zona, precio_normal, precio_final, ahorro,
    precio_si_aplica, compra_medida, minimo, mide, frase, menciona_gratis}``. Los montos son números con dos decimales;
    ``precio_final`` es el que paga el cliente por el envío (el normal si no aplica; ``None`` si todavía no se sabe
    porque no hay compra)."""
    precio = _precio(precio_envio)
    if not vigente(promocion, fecha):
        return _vacio(precio)
    return _evaluar(promocion, zona_de(promocion, prov, dist), precio, compra)


def _evaluar(promocion, zona, precio, compra):
    """La cuenta, con la zona ya decidida (``gratis``, ``abono`` o ``ninguna``) y sin mirar la fecha."""
    salida = _vacio(precio)
    minimo = centavos(promocion.get('minimo'))
    mide = promocion.get('mide') if promocion.get('mide') in MIDE else 'sin_itbms'
    salida.update(hay_promocion=True, nombre=(promocion.get('nombre') or '').strip(), zona=zona,
                  minimo=float(minimo), mide=mide)
    if precio is None:
        return dict(salida, motivo=SIN_PRECIO)
    if zona == 'ninguna':
        return dict(salida, motivo=ZONA_SIN_BENEFICIO)
    abono = centavos(promocion.get('abono'))
    si_aplica = _con_promocion(precio, zona, abono)
    salida['precio_si_aplica'] = float(si_aplica)
    if compra is None:
        salida.update(motivo=SIN_COMPRA, condicional=True, precio_final=None)
    else:
        medida = centavos(compra.get('subtotal_con_itbms' if mide == 'con_itbms' else 'subtotal_sin_itbms'))
        salida['compra_medida'] = float(medida) if medida > 0 else 0.0      # nunca una cifra negativa (M-7)
        if promocion.get('excluye_colchon') and compra.get('colchon'):
            salida['motivo'] = COLCHON
        elif not medida > minimo:
            salida['motivo'] = MONTO
        else:
            gratis = si_aplica == 0
            salida.update(motivo=GRATIS if zona == GRATIS or gratis else ABONO, aplica=True,
                          precio_final=float(si_aplica), ahorro=float(precio - si_aplica))
    salida['frase'] = frase(promocion, salida, abono)
    salida['menciona_gratis'] = 'gratis' in sin_tildes(salida['frase'])
    return salida


# --- Lo ya prometido (revisión adversarial, segunda vuelta: I-1 e I-2) ---------------------------------------------
# La promoción se ofrece y se suma con la fecha de HOY. Una vez sumada a una cotización, queda guardado CON QUÉ
# TÉRMINOS se sumó (``terminos``) y el día; mientras la cotización no venza, se respeta lo prometido aunque Gerencia
# cambie o archive la promoción después: solo se vuelve a mirar si la COMPRA sigue cumpliendo esos términos (el
# mínimo, el colchón) y si el envío sigue ahí con su precio.
#
# Hasta cuándo (tercera vuelta, I-B): lo prometido vale hasta el «Vence el» que tenía la cotización al sumarse la
# promoción y nunca más de DIAS_DE_LO_PROMETIDO días después de sumada (si no tenía «Vence el», esos días). Queda
# guardado en los términos (``vale_hasta``): cambiar «Vence el» después no lo alarga ni lo revive.
DIAS_DE_LO_PROMETIDO = 30


def vale_hasta(sumada_el, vence=None):
    """El último día en que vale lo prometido: el «Vence el» de la cotización al sumarse (``vence``), sin pasar de
    ``sumada_el`` + DIAS_DE_LO_PROMETIDO días; sin «Vence el», esos días. Nunca antes del día en que se sumó."""
    tope = sumada_el + timedelta(days=DIAS_DE_LO_PROMETIDO)
    return max(sumada_el, min(vence, tope)) if vence else tope


def prometido_hasta(terminos_guardados):
    """El último día en que valen los términos guardados (``vale_hasta``; si no lo traen, los días de la regla desde que
    se sumó)."""
    if terminos_guardados.get('vale_hasta'):
        return date.fromisoformat(terminos_guardados['vale_hasta'])
    return vale_hasta(date.fromisoformat(terminos_guardados['sumada_el']))


def terminos(promocion, resultado, sumada_el, promocion_id=None, vence=None):
    """Los términos con que se sumó la promoción a una cotización (para guardarlos en su línea): la promoción, sus
    fechas, el mínimo y cómo se mide, si en ese lugar es gratis o un abono (y de cuánto), la regla del colchón, el
    día en que se sumó y hasta cuándo vale lo prometido (``vence``: el «Vence el» de la cotización en ese momento)."""
    return {
        'promocion_id': promocion_id, 'nombre': (promocion.get('nombre') or '').strip(),
        'desde': promocion['desde'].isoformat(), 'hasta': promocion['hasta'].isoformat(),
        'minimo': float(centavos(promocion.get('minimo'))), 'mide': resultado.get('mide') or 'sin_itbms',
        'zona': resultado['zona'], 'abono': float(centavos(promocion.get('abono'))),
        'excluye_colchon': bool(promocion.get('excluye_colchon')), 'sumada_el': sumada_el.isoformat(),
        'vale_hasta': vale_hasta(sumada_el, vence).isoformat(),
    }


def _como_promocion(terminos_guardados):
    """Los términos guardados con la forma de una promoción (para la cuenta y la frase)."""
    return dict(terminos_guardados, desde=date.fromisoformat(terminos_guardados['desde']),
                hasta=date.fromisoformat(terminos_guardados['hasta']))


def con_lo_prometido(terminos_guardados, precio_envio, compra):
    """La promoción ya sumada a una cotización, con los términos con que se sumó (no con la promoción de hoy) y la
    compra de ahora. Mismo resultado que ``aplicar`` (sin mirar la fecha: lo prometido vale hasta ``prometido_hasta``;
    eso lo decide quien llama)."""
    promocion = _como_promocion(terminos_guardados)
    return _evaluar(promocion, terminos_guardados['zona'], _precio(precio_envio), compra)


def recordar(terminos_guardados, resultado):
    """Lo que ya tiene la cotización, dicho sin «hasta cuándo» (la promoción puede haber terminado; lo prometido se
    respeta): «Tu cotización ya tiene la promoción de noviembre, así que D'CASA te regala el envío: te sale gratis (te
    ahorras $45).» Sin beneficio, ``''``."""
    if not resultado.get('aplica'):
        return ''
    promocion = _como_promocion(terminos_guardados)
    return f'Tu cotización ya tiene {nombre_corto(promocion)}, así que {_beneficio(resultado, promocion["abono"])}.'


def _beneficio(resultado, abono):
    precio = Decimal(str(resultado['precio_normal']))
    si_aplica = Decimal(str(resultado['precio_si_aplica'] or 0))
    if resultado['zona'] == GRATIS or si_aplica == 0:
        return f"D'CASA te regala el envío: te sale gratis (te ahorras {dinero(precio - si_aplica)})"
    return f"D'CASA te abona {dinero(abono)} del envío: te queda en {dinero(si_aplica)}"


def nombre_corto(promocion):
    """«la promoción de noviembre» si dura dentro de un mismo mes; si no, «la promoción de envío»."""
    desde, hasta = promocion['desde'], promocion['hasta']
    if (desde.year, desde.month) == (hasta.year, hasta.month):
        return f'la promoción de {MESES[hasta.month - 1]}'
    return 'la promoción de envío'


def hasta_cuando(promocion):
    """«La promoción es hasta el 30 de noviembre; después, el envío vuelve a su precio normal.» (Pedido de la dueña,
    2026-11-12: que quede claro que es por tiempo limitado.)"""
    hasta = promocion['hasta']
    return (f'La promoción es hasta el {hasta.day} de {MESES[hasta.month - 1]}; después, el envío vuelve a su precio '
            'normal.')


def frase(promocion, resultado, abono):
    """La frase de la promoción para el cliente (tuteo, corta, sin cifras que no salgan de aquí).

    Pedido de la dueña (2026-11-12): que se entienda que el envío cuesta normalmente tanto, que D'CASA le resta algo con
    la promoción (lo regala o abona una parte) y que es por tiempo limitado. Por eso, cuando hay beneficio: (2) lo que
    pone D'CASA, como un regalo o un abono que se le resta, y (3) hasta cuándo vale; el precio normal (1) lo antepone
    ``con_el_precio_normal``. Cuando no aplica (colchón, monto) solo se explica por qué el envío va a su precio normal,
    sin prometer nada.

    «gratis» sale SOLO cuando este envío queda o quedaría gratis: así «gratis» nunca respalda un envío que no lo es."""
    motivo = resultado['motivo']
    cual = nombre_corto(promocion)
    Cual = cual[0].upper() + cual[1:]
    mide = MIDE[resultado['mide']]
    minimo = dinero(resultado['minimo'])
    if motivo in (SIN_COMPRA, GRATIS, ABONO):
        beneficio = _beneficio(resultado, abono)
        condicion = f'en compras de más de {minimo} {mide}' if motivo == SIN_COMPRA else \
            f'como tu compra pasa de {minimo} {mide}'
        sin_colchon = ' No aplica si la compra lleva colchón.' \
            if motivo == SIN_COMPRA and promocion.get('excluye_colchon') else ''
        return f'Con {cual}, {condicion}, {beneficio}. {hasta_cuando(promocion)}{sin_colchon}'
    if motivo == COLCHON:
        return f'{Cual} no aplica cuando la compra lleva colchón, así que el envío va a su precio normal.'
    if motivo == MONTO:
        if not resultado['compra_medida']:          # nunca «tu cotización suma $0» ni una cifra negativa
            return f'{Cual} es para compras de más de {minimo} {mide}, así que el envío va a su precio normal.'
        return (f'{Cual} es para compras de más de {minimo} {mide}; tu cotización suma '
                f'{dinero(resultado["compra_medida"])} {mide}, así que el envío va a su precio normal.')
    return ''


def tiene_beneficio(resultado):
    """¿La frase ofrece algo (aplica, o aplicaría con la condición dicha)?"""
    return resultado.get('motivo') in (SIN_COMPRA, GRATIS, ABONO)


def con_el_precio_normal(resultado, lugar, desglose=''):
    """La frase completa cuando hay beneficio: «El envío a <lugar> cuesta normalmente $X.» (con ``desglose`` si hay
    cargos aparte) y después la de la promoción. Sin beneficio, ``''`` (quien llama dice el precio como siempre)."""
    if not tiene_beneficio(resultado):
        return ''
    normal = f'El envío a {lugar} cuesta normalmente {dinero(resultado["precio_normal"])}.'
    return ' '.join(p for p in (normal, desglose, resultado['frase']) if p)


def respaldo(resultado, nombres=(), cargos=(), lleva_itbms=False):
    """Lo que la guardia de salida del Worker deja decir del envío a UN lugar (revisión adversarial del 2026-11-12, I1,
    I2 y I5): cada cifra con su papel, para que una cifra no respalde otra cosa (lo abonado nunca es lo que cuesta).

    ``{nombres, normal, final, ahorro, gratis, condicional, minimo, compra, cargos, lleva_itbms}``:

    * ``nombres``: cómo se le nombra al cliente (el nombre del lugar, su corregimiento, su distrito).
    * ``normal``: el precio normal. ``final``: lo que paga con la promoción (sin compra todavía: lo que quedaría).
    * ``ahorro``: lo que D'CASA regala o abona (solo se dice como ahorro, abono o descuento, nunca como costo).
    * ``gratis``: la frase dice «gratis» (solo cuando este envío queda o quedaría gratis).
    * ``condicional``: todavía no hay compra; el beneficio solo se dice con el mínimo en la misma oración.
    * ``minimo``: el mínimo de la compra, si la frase lo dice. ``compra``: lo que suma la cotización (si la frase lo
      dice: la compra no llega al mínimo).
    * ``cargos``: el desglose que dice la frase (``[{nombre, monto}]``: la tarifa y los cargos aparte).
    * ``lleva_itbms``: si al envío se le suma el ITBMS (lo dice la herramienta, no el modelo)."""
    motivo = resultado.get('motivo')
    normal = resultado.get('precio_normal')
    final = ahorro = None
    if resultado.get('aplica'):
        final, ahorro = resultado.get('precio_final'), resultado.get('ahorro')
    elif resultado.get('condicional') and resultado.get('precio_si_aplica') is not None:
        final = resultado['precio_si_aplica']
        ahorro = float(centavos(normal) - centavos(final))
    return {
        'nombres': [n for n in dict.fromkeys(' '.join(str(n or '').split()) for n in nombres) if n],
        'normal': normal, 'final': final, 'ahorro': ahorro,
        'gratis': bool(resultado.get('menciona_gratis')), 'condicional': bool(resultado.get('condicional')),
        'minimo': resultado.get('minimo') if motivo in (SIN_COMPRA, GRATIS, ABONO, MONTO) else None,
        'compra': resultado.get('compra_medida') if motivo == MONTO and resultado.get('compra_medida') else None,
        'cargos': [{'nombre': str(c['nombre']), 'monto': float(c['monto'])} for c in cargos],
        'lleva_itbms': bool(lleva_itbms),
    }
