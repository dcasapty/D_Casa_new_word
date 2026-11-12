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


def aplicar(promocion, precio_envio, prov, dist, fecha, compra=None):
    """La promoción aplicada a un envío.

    * ``promocion``: ``{nombre, desde, hasta (date), minimo, mide ('sin_itbms' | 'con_itbms'), provincias_gratis,
      distritos_gratis, abono, excluye_colchon}`` o ``None``.
    * ``precio_envio``: el precio NORMAL del envío (el de la tarifa), o ``None`` si se cotiza aparte. Con $0 o menos no
      hay nada que rebajar (``SIN_PRECIO``).
    * ``prov``, ``dist``: la provincia y el distrito del lugar. ``fecha``: la fecha de Panamá.
    * ``compra``: ``{subtotal_sin_itbms, subtotal_con_itbms, colchon}`` de la cotización (sin contar el envío), o
      ``None`` si todavía no hay cotización.

    Devuelve ``{hay_promocion, nombre, motivo, aplica, condicional, zona, precio_normal, precio_final, ahorro,
    precio_si_aplica, compra_medida, minimo, mide, frase, menciona_gratis}``. Los montos son números con dos decimales;
    ``precio_final`` es el que paga el cliente por el envío (el normal si no aplica; ``None`` si todavía no se sabe
    porque no hay compra)."""
    precio = centavos(precio_envio) if precio_envio is not None else None
    if precio is not None and precio <= 0:
        precio = None                    # $0 o negativo: como sin precio (nada que rebajar ni que decir)
    salida = {
        'hay_promocion': False, 'nombre': '', 'motivo': SIN_PROMOCION, 'aplica': False, 'condicional': False,
        'zona': '', 'precio_normal': float(precio) if precio is not None else None,
        'precio_final': float(precio) if precio is not None else None, 'ahorro': 0.0, 'precio_si_aplica': None,
        'compra_medida': None, 'minimo': None, 'mide': '', 'frase': '', 'menciona_gratis': False,
    }
    if not vigente(promocion, fecha):
        return salida
    minimo = centavos(promocion.get('minimo'))
    mide = promocion.get('mide') if promocion.get('mide') in MIDE else 'sin_itbms'
    zona = zona_de(promocion, prov, dist)
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
        salida['compra_medida'] = float(medida)
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
        precio = Decimal(str(resultado['precio_normal']))
        si_aplica = Decimal(str(resultado['precio_si_aplica'] or 0))
        if resultado['zona'] == GRATIS or si_aplica == 0:
            beneficio = f"D'CASA te regala el envío: te sale gratis (te ahorras {dinero(precio - si_aplica)})"
        else:
            beneficio = f"D'CASA te abona {dinero(abono)} del envío: te queda en {dinero(si_aplica)}"
        condicion = f'en compras de más de {minimo} {mide}' if motivo == SIN_COMPRA else \
            f'como tu compra pasa de {minimo} {mide}'
        sin_colchon = ' No aplica si la compra lleva colchón.' \
            if motivo == SIN_COMPRA and promocion.get('excluye_colchon') else ''
        return f'Con {cual}, {condicion}, {beneficio}. {hasta_cuando(promocion)}{sin_colchon}'
    if motivo == COLCHON:
        return f'{Cual} no aplica cuando la compra lleva colchón, así que el envío va a su precio normal.'
    if motivo == MONTO:
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


def respaldo(resultado):
    """Lo que la guardia de salida del Worker deja decir sobre el costo del envío en ese turno: las cifras de este
    envío que la frase le da al cliente (el precio normal; con la promoción aplicada, el precio final y lo que se
    ahorra o se abona; sin compra todavía, lo que quedaría y lo que se abonaría) y si la frase dice «gratis»."""
    montos = {resultado.get('precio_normal')}
    if resultado.get('aplica'):
        montos |= {resultado.get('precio_final'), resultado.get('ahorro')}
    elif resultado.get('condicional') and resultado.get('precio_si_aplica') is not None:
        # Sin compra todavía: lo que quedaría y lo que D'CASA abona o regala (la frase dice las dos cifras).
        montos.add(resultado['precio_si_aplica'])
        montos.add(float(centavos(resultado['precio_normal']) - centavos(resultado['precio_si_aplica'])))
    return {'montos': sorted(m for m in montos if m is not None), 'gratis': bool(resultado.get('menciona_gratis'))}
