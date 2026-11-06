"""Lo que se muestra de un lugar (la «tarjeta» del HTML) como datos puros: la pantalla solo los pinta.

Así la pantalla interna, Brian y, mañana, la web dicen lo mismo: el precio, el desglose, la ruta en Google Maps y el
texto que se le copia al cliente salen de aquí.
"""
from .tarifa import Tarifa
from .texto import dinero, encode_uri_component, km_txt, numero_js

# La tienda (el pin de Google Maps de D'CASA en La Chorrera): de aquí salen todas las distancias.
TIENDA = '8.8765881,-79.7867962'
ETIQUETA_TIPO = {'barrio': 'barrio o urbanización', 'edificio': 'edificio o PH', 'referencia': 'lugar conocido',
                 'corregimiento': 'corregimiento'}
ATRIBUCION = 'Datos de mapas © colaboradores de OpenStreetMap (ODbL) y GeoNames (CC BY 4.0)'


def url_ruta(destino):
    return ('https://www.google.com/maps/dir/?api=1&origin=' + TIENDA + '&destination='
            + encode_uri_component(destino) + '&travelmode=driving')


def mapa_ruta(lugar):
    """La ruta en carro desde la tienda hasta el lugar (por coordenadas si las tiene; si no, por nombre)."""
    if lugar.get('lat') is not None:
        destino = f"{numero_js(lugar['lat'])},{numero_js(lugar.get('lon'))}"
    else:
        destino = f"{lugar.get('nombre') or ''}, {lugar.get('dist') or ''}, Panamá"
    return url_ruta(destino)


def desglose(cotizacion):
    """«Tarifa base $20», «+ Peaje $3»…: ``[{'texto', 'monto'}]``."""
    filas = [{'texto': 'Tarifa base', 'monto': dinero(cotizacion['base'])}]
    filas += [{'texto': f"+ {cargo['nombre']}", 'monto': dinero(cargo['v'])} for cargo in cotizacion['extras']]
    return filas


def texto_cliente(lugar, cotizacion):
    """El texto de «Copiar el precio»: «Envío a <lugar> (<corregimiento>, <distrito>): $X.», y el desglose si hay
    cargos aparte («Tarifa $Y + peaje $Z.»)."""
    corr = lugar.get('corr') or ''
    zona = ', '.join(p for p in (corr if corr and corr != lugar.get('nombre') else '', lugar.get('dist') or '') if p)
    partes = [f"Envío a {lugar.get('nombre') or ''}{' (' + zona + ')' if zona else ''}: {dinero(cotizacion['total'])}"]
    if cotizacion['extras']:
        partes.append(f"Tarifa {dinero(cotizacion['base'])} + "
                      + ' + '.join(f"{cargo['nombre'].lower()} {dinero(cargo['v'])}" for cargo in cotizacion['extras']))
    return '. '.join(partes) + '.'


def cotizar_lugar(tarifa, lugar):
    """La cotización del lugar con esa tarifa, o ``None`` si se cotiza aparte."""
    if not isinstance(tarifa, Tarifa):
        tarifa = Tarifa(tarifa)
    if not tarifa.configurada or not tarifa.con_precio(lugar):
        return None
    return tarifa.cotizar(lugar['km'], lugar.get('peaje'))


def chips(lugar, cotizacion, tarifa):
    """Las etiquetas de la tarjeta: ``[{'texto', 'clase'}]`` (clase: tipo, revisar, aparte o mano)."""
    tipo = lugar.get('tipo')
    salida = [{'texto': lugar.get('cat') if tipo == 'referencia' else ETIQUETA_TIPO.get(tipo, ''), 'clase': 'tipo'}]
    estado = lugar.get('estado')
    if estado == 'revisar':
        salida.append({'texto': 'revisar', 'clase': 'revisar'})
    if estado == 'lancha':
        salida.append({'texto': '+ lancha', 'clase': 'tipo'})
    if lugar.get('peaje'):
        salida.append({'texto': 'pasa por peaje', 'clase': 'tipo'})
    if lugar.get('agregado'):
        salida.append({'texto': 'agregado a mano', 'clase': 'mano'})
    if not cotizacion:
        km = lugar.get('km')
        if not tarifa.configurada:          # (el HTML siempre traía su tarifa; Odoo puede no tenerla todavía)
            aparte = 'sin tarifa'
        elif estado == 'sin_carretera':
            aparte = 'sin carretera'
        elif estado == 'no_encontrado':
            aparte = 'no encontrado'
        elif km is not None and km > tarifa.max_km:
            aparte = f'más de {numero_js(tarifa.max_km)} km'
        else:
            aparte = 'sin medida'
        salida.append({'texto': aparte, 'clase': 'aparte'})
    return salida


def zona(lugar):
    dist, prov = lugar.get('dist') or '', lugar.get('prov') or ''
    if lugar.get('tipo') == 'corregimiento':
        return f'Corregimiento · {dist} · {prov}'
    corr = lugar.get('corr')
    previa = f"Zona: {corr}{'' if lugar.get('corr_exacto') else ' (aprox.)'} · " if corr else ''
    return f'{previa}{dist} · {prov}'


def tarjeta(lugar, tarifa):
    """Todo lo que la pantalla muestra de un lugar (sin HTML: textos y números)."""
    if not isinstance(tarifa, Tarifa):
        tarifa = Tarifa(tarifa)
    cotizacion = cotizar_lugar(tarifa, lugar)
    alias = list(lugar.get('alias') or [])
    km = lugar.get('km')
    datos = {
        'nombre': lugar.get('nombre') or '',
        'tipo': lugar.get('tipo'),
        'chips': chips(lugar, cotizacion, tarifa),
        'zona': zona(lugar),
        'tambien': f"También: {' · '.join(alias[:4])}" if alias else '',
        'nota': lugar.get('nota') or '',
        'km': km,
        'km_txt': f'{km_txt(km)} km' if km is not None else '',
        'google': lugar.get('fuente_km') == 'Google Maps',
        'peaje': bool(lugar.get('peaje')),
        'url_mapa': mapa_ruta(lugar),
        'con_precio': bool(cotizacion),
    }
    if cotizacion:
        datos.update({
            'base': cotizacion['base'],
            'extras': [{'nombre': c['nombre'], 'monto': c['v']} for c in cotizacion['extras']],
            'total': cotizacion['total'],
            'total_txt': dinero(cotizacion['total']),
            'desglose': desglose(cotizacion),
            'texto_cliente': texto_cliente(lugar, cotizacion),
        })
    return datos
