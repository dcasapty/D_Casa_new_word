"""El informe que ve quien carga (en la pantalla de Odoo): qué pasó o, en un ensayo, qué pasaría.

Los nombres de las personas se muestran aquí, dentro de Odoo, para que se puedan encontrar; nunca se escriben en el log.
"""
from markupsafe import Markup, escape

LIMITE = 40


def _lista(items, formato, limite=LIMITE):
    """Una lista HTML con los primeros ``limite``; «… y N más» si hay más."""
    items = list(items)
    if not items:
        return Markup('')
    partes = [Markup('<li>%s</li>') % formato(item) for item in items[:limite]]
    if len(items) > limite:
        partes.append(Markup('<li><i>… y %s más</i></li>') % (len(items) - limite))
    return Markup('<ul>%s</ul>') % Markup('').join(partes)


def _linea(texto, cantidad, detalle=''):
    return Markup('<li>%s: <b>%s</b>%s</li>') % (texto, cantidad, detalle)


def _seccion_clientes(resumen):
    errores = resumen['con_error']
    return Markup('<h4>Clientes</h4><ul>%s%s%s</ul>%s') % (
        _linea('Fichas nuevas', len(resumen['creados'])),
        _linea('Ya estaban (no se tocan)', len(resumen['ya_estaban'])),
        _linea('No se pudieron crear', len(errores)),
        _lista(errores, lambda e: Markup('n.º %s — %s: %s') % (e[0], e[1], e[2])),
    )


def _seccion_catalogo(resumen, avisos, con_existencias):
    negativos = resumen['negativos']
    repetidos = resumen['repetidos']
    cuerpo = Markup('').join([
        _linea('Productos nuevos', len(resumen['creados'])),
        _linea('Con cambios (existencias, precio o costo)', len(resumen['actualizados'])),
        _linea('Sin cambios', len(resumen['sin_cambios'])),
        _linea('Combos con colchón (entran sin publicar)', len(resumen['combos'])),
        _linea('Productos nuevos sin foto', len(resumen['sin_foto'])),
        _linea('No se cargan (Descuento, Propinas y similares)', len(resumen['omitidos'])),
        _linea('Códigos repetidos (solo entró el primero)', len(repetidos)),
        _linea('Existencias negativas (entraron en 0: hay que contarlas)', len(negativos)),
    ])
    aviso_codigos = avisos['sin_codigo']
    huerfanos = avisos['huerfanos']
    sin_codigo_inv = avisos['existencias_sin_codigo']
    extra = Markup('').join([
        _linea('Productos archivados (no se cargan)', avisos['archivados']),
        _linea('Productos activos sin código (su existencia no se puede cargar: contarla a mano)', len(aviso_codigos)),
        _linea('Filas del inventario sin código (contarlas a mano)', len(sin_codigo_inv),
               Markup(' — suman %s unidades') % round(sum(sin_codigo_inv), 2) if sin_codigo_inv else Markup('')),
        _linea('Existencias de códigos que no son un producto activo', len(huerfanos)),
        _linea('Existencias con decimales (se redondearon a unidades enteras: contarlas)', len(avisos['decimales'])),
    ])
    nota = Markup('') if con_existencias else Markup(
        '<p><i>No se subió inventario.csv: no se tocó ninguna existencia.</i></p>')
    return Markup('<h4>Productos y existencias</h4><ul>%s</ul>%s<ul>%s</ul>%s%s%s%s%s') % (
        cuerpo, nota, extra,
        _lista(negativos, escape),
        _lista(repetidos, escape),
        _lista(aviso_codigos, escape),
        _lista(huerfanos, lambda h: Markup('%s: %s unidades') % (h[0], h[1])),
        _lista(avisos['decimales'], lambda d: Markup('%s: venía con %s') % (d[0], d[1])),
    )


def informe_html(ensayo, clientes=None, catalogo=None, avisos=None, con_existencias=True, segundos=None):
    """El HTML del informe. ``clientes`` es el resumen de ``cargar_clientes``; ``catalogo`` y ``avisos`` los de
    ``cargar_catalogo``. Lo que no se subió no aparece."""
    if ensayo:
        titulo = Markup('<div class="alert alert-info"><b>ENSAYO: no se cambió nada.</b> '
                        'Así quedaría la carga. Si todo se ve bien, pulsa «Cargar».</div>')
    else:
        titulo = Markup('<div class="alert alert-success"><b>CARGA HECHA.</b> Esto fue lo que pasó. '
                        'Volver a cargar el mismo archivo no repite nada.</div>')
    secciones = [titulo]
    if clientes is not None:
        secciones.append(_seccion_clientes(clientes))
    if catalogo is not None:
        secciones.append(_seccion_catalogo(catalogo, avisos, con_existencias))
    if segundos is not None:
        secciones.append(Markup('<p><i>Tardó %s segundos.</i></p>') % round(segundos))
    return Markup('').join(secciones)
