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


def _seccion_contactos(titulo, resumen):
    errores = resumen['con_error']
    ampliadas = Markup('') if not resumen['ampliados'] else _linea(
        'Ya estaban con el otro papel (ahora tienen también este)', len(resumen['ampliados']))
    return Markup('<h4>%s</h4><ul>%s%s%s%s</ul>%s') % (
        titulo,
        _linea('Fichas nuevas', len(resumen['creados'])),
        _linea('Ya estaban (no se tocan)', len(resumen['ya_estaban'])),
        ampliadas,
        _linea('No se pudieron crear', len(errores)),
        _lista(errores, lambda e: Markup('n.º %s — %s: %s') % (e[0], e[1], e[2])),
    )


def _seccion_precios(resumen):
    errores = resumen['con_error']
    return Markup('<h4>Precios de proveedor</h4><ul>%s%s%s%s</ul>%s') % (
        _linea('Precios nuevos', len(resumen['creados'])),
        _linea('Ya estaban (no se tocan)', len(resumen['ya_estaban'])),
        _linea('Con precio 0 (no se registró: no se cargan)', len(resumen['omitidos'])),
        _linea('No se pudieron cargar', len(errores)),
        _lista(errores, lambda e: Markup('proveedor n.º %s, producto %s: %s') % (e[0], e[1], e[2])),
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


def _seccion_documentos(titulo, resumen, creados, sin_pendiente, extras=()):
    """Una sección de documentos abiertos (facturas en borrador u órdenes de compra). ``extras`` son pares
    ``(clave del aviso, título, formato de cada elemento)`` que se muestran como listas «para revisar»."""
    errores = resumen['con_error']
    cuerpo = Markup('<h4>%s</h4><ul>%s%s%s%s</ul>%s') % (
        titulo,
        _linea(creados, len(resumen['creados'])),
        _linea('Ya estaban (no se tocan)', len(resumen['ya_estaban'])),
        _linea(sin_pendiente, len(resumen['sin_pendiente'])),
        _linea('No se pudieron crear', len(errores)),
        _lista(errores, lambda e: Markup('orden %s: %s') % (e[0], e[1])),
    )
    for clave, texto, formato in extras:
        if resumen[clave]:
            cuerpo += Markup('<p><b>%s</b> (%s)</p>%s') % (texto, len(resumen[clave]), _lista(resumen[clave], formato))
    return cuerpo


def _formato_sin_producto(item):
    return Markup('orden %s: %s') % (item[0], item[1])


def _formato_total(item):
    return Markup('orden %s: el archivo dice %s y aquí salió %s') % (item[0], f'{item[1]:.2f}', f'{item[2]:.2f}')


def _seccion_ventas(resumen):
    return _seccion_documentos(
        'Ventas por facturar (quedan como factura en borrador)', resumen, 'Facturas en borrador nuevas',
        'Órdenes sin nada por facturar', extras=(
            ('sin_producto', 'Líneas cuyo producto no está en el catálogo (van con el nombre del archivo)',
             _formato_sin_producto),
            ('total_distinto', 'Total distinto al de la orden vieja: revisar antes de publicar', _formato_total)))


def _seccion_entregas(entregas):
    return Markup('<h4>Ventas con mercancía por entregar (no se cargan)</h4>'
                  '<p>Entrégalas o vuelve a hacer la orden a mano: la mercancía ya cuenta en las existencias.</p>'
                  '%s') % _lista(entregas, lambda e: Markup('orden %s — %s: %s') % (
                      e[0], e[1], ', '.join(f'{cantidad:g} × {producto}' for producto, cantidad in e[2])))


def _seccion_compras_por_recibir(resumen):
    return _seccion_documentos(
        'Compras por recibir (quedan como orden de compra confirmada)', resumen, 'Órdenes de compra nuevas',
        'Órdenes sin nada por recibir', extras=(
            ('ya_facturadas', 'Ya tenían factura del proveedor: al recibirlas, NO las factures otra vez',
             escape),))


def _seccion_compras_por_facturar(resumen):
    return _seccion_documentos(
        'Compras por facturar (quedan como factura de proveedor en borrador)', resumen,
        'Facturas de proveedor en borrador nuevas', 'Órdenes sin nada por facturar', extras=(
            ('sin_referencia', 'Sin el número de factura del proveedor: ponérselo antes de publicar', escape),
            ('sin_producto', 'Líneas cuyo producto no está en el catálogo (van con el nombre del archivo)',
             _formato_sin_producto),
            ('total_distinto', 'Total distinto al de la orden vieja: revisar antes de publicar', _formato_total)))


def _dinero(valor):
    return f'{valor:,.2f}'


def _seccion_historia(titulo, resumen, extras=()):
    """Facturas o pagos del año. ``resumen`` es el de ``historial.cargar_facturas`` o ``cargar_pagos``; ``extras``
    son ``(clave, título, formato)`` de listas para revisar."""
    errores = resumen['con_error']
    cuerpo = Markup('<ul>%s%s%s%s</ul>%s') % (
        _linea('Nuevas', len(resumen['creados'])),
        _linea('Ya estaban (no se tocan)', len(resumen['ya_estaban'])),
        _linea('Faltan por cargar (otra tanda)', resumen['faltan']) if resumen['faltan'] else Markup(''),
        _linea('No se pudieron cargar', len(errores)),
        _lista(errores, lambda e: Markup('%s: %s') % (e[0], e[1])),
    )
    cuerpo = Markup('<h4>%s</h4>%s') % (titulo, cuerpo)
    for clave, texto, formato in extras:
        if resumen.get(clave):
            cuerpo += Markup('<p><b>%s</b> (%s)</p>%s') % (texto, len(resumen[clave]), _lista(resumen[clave], formato))
    return cuerpo


def _seccion_previa(previa):
    """Lo que se ve de todo el archivo antes de cargar (aunque el ensayo solo cubra la primera tanda)."""
    avisos = Markup('').join([
        Markup('<p><b>Contactos que no están cargados</b> (sus documentos no entran)</p>%s') % _lista(
            previa['contactos'], lambda c: Markup('%s n.º %s: %s documentos') % (c[0], c[1], c[2]))
        if previa['contactos'] else Markup(''),
        Markup('<p><b>Impuestos que no existen aquí</b> (créalos con ese nombre o cámbialos en el archivo)</p>%s')
        % _lista(previa['impuestos'], lambda i: Markup('«%s»: %s líneas') % (i[0], i[2]))
        if previa['impuestos'] else Markup(''),
        Markup('<p><b>Diarios de banco o efectivo que no existen</b> (créalos en Contabilidad con ese nombre)</p>%s')
        % _lista(previa['diarios'], lambda d: Markup('«%s»: %s pagos') % (d[0], d[1]))
        if previa['diarios'] else Markup(''),
        Markup('<p><b>Productos que no están en el catálogo</b> (sus líneas entran sin producto, con el nombre del '
               'archivo)</p>%s') % _lista(previa['productos'], lambda p: Markup('%s: %s líneas') % (p[0], p[1]))
        if previa['productos'] else Markup(''),
        Markup('<p><b>Facturas que citan los pagos y no están en los archivos</b> (el pago entra sin aplicarse a '
               'ellas)</p>%s') % _lista(previa['facturas'], escape) if previa['facturas'] else Markup(''),
    ])
    if not avisos:
        avisos = Markup('<p>Todo el archivo se ve bien: contactos, impuestos y diarios existen.</p>')
    return Markup('<h4>Antes de cargar (se revisó todo el archivo)</h4>%s') % avisos


def _seccion_cuadre(cuadre):
    """Archivo contra lo que quedó en el libro (solo cuando ya no falta nada por cargar)."""
    partes = []
    for rol, titulo in (('cliente', 'Facturas de clientes'), ('proveedor', 'Facturas de proveedores')):
        if rol not in cuadre:
            continue
        datos = cuadre[rol]
        filas = Markup('').join(
            Markup('<li>%s: archivo <b>%s</b> · aquí <b>%s</b></li>') % (nombre, _dinero(datos['archivo'][clave]),
                                                                           _dinero(datos['aqui'][clave]))
            for nombre, clave in (('Base', 'base'), ('Impuesto', 'impuesto'), ('Total', 'total'),
                                  ('Saldo por ' + ('cobrar' if rol == 'cliente' else 'pagar'), 'saldo')))
        libro = Markup('<li>El libro mayor dice que %s <b>%s</b>%s</li>') % (
            'te deben' if rol == 'cliente' else 'debes', _dinero(datos['libro']),
            Markup('') if abs(datos['libro'] - datos['archivo']['saldo']) <= 0.02 else Markup(
                ' — <b>no coincide con la suma de saldos del archivo</b>: la diferencia son pagos sin aplicar a '
                'ninguna factura o notas de crédito aplicadas distinto; que el contador la revise'))
        partes.append(Markup('<p><b>%s</b> (%s cargadas)</p><ul>%s%s</ul>%s') % (
            titulo, datos['cargadas'], filas, libro,
            Markup('<p>Facturas que quedaron con un saldo distinto al del archivo (%s):</p>%s') % (
                len(datos['saldos']), _lista(datos['saldos'], lambda x: Markup('%s: el archivo dice %s y aquí %s') % (
                    x[0], _dinero(x[1]), _dinero(x[2])))) if datos['saldos'] else Markup('')))
    return Markup('<h4>Cuadre contra el archivo</h4>%s') % Markup('').join(partes) if partes else Markup('')


def _seccion_historial(historial, ensayo):
    faltan = historial['faltan']
    if faltan and ensayo:
        aviso = Markup('<div class="alert alert-warning">El ensayo cubre solo la primera tanda; en total faltarían '
                       '<b>%s</b> documentos. La revisión de arriba sí abarca todo el archivo.</div>') % faltan
    elif faltan:
        aviso = Markup('<div class="alert alert-warning"><b>Faltan %s documentos por cargar.</b> Pulsa '
                       '«Cargar» otra vez: sigue donde se quedó y no repite nada.</div>') % faltan
    else:
        aviso = Markup('')
    secciones = [aviso, _seccion_previa(historial['previa'])]
    extras_facturas = (('para_revisar', 'Entraron, pero conviene mirarlas',
                        lambda x: Markup('%s: %s') % (x[0], x[1])),)
    if 'facturas_clientes' in historial:
        secciones.append(_seccion_historia(
            'Facturas de clientes del año (quedan publicadas)', historial['facturas_clientes'], extras_facturas))
    if 'facturas_proveedores' in historial:
        secciones.append(_seccion_historia(
            'Facturas de proveedores del año (quedan publicadas)', historial['facturas_proveedores'], extras_facturas))
    if 'pagos' in historial:
        pagos = historial['pagos']
        secciones.append(_seccion_historia('Cobros y pagos del año', pagos, (
            ('facturas_no_cargadas', 'Citan facturas que no están cargadas (el pago entró sin aplicarse a ellas)',
             lambda x: Markup('%s: %s') % (x[0], ', '.join(x[1]))),)))
        if pagos['sin_facturas']:
            secciones.append(Markup('<p>%s pagos no dicen qué factura pagan: quedaron como saldo a favor de su '
                                    'ficha.</p>') % pagos['sin_facturas'])
    if 'cuadre' in historial:
        secciones.append(_seccion_cuadre(historial['cuadre']))
    return Markup('').join(secciones)


def informe_html(ensayo, clientes=None, catalogo=None, avisos=None, con_existencias=True, segundos=None,
                 proveedores=None, precios=None, ventas=None, entregas=None, compras_por_recibir=None,
                 compras_por_facturar=None, historial=None):
    """El HTML del informe. ``clientes`` y ``proveedores`` son los resúmenes de ``cargar_contactos``; ``catalogo``
    y ``avisos`` los de ``cargar_catalogo``; ``precios`` el de ``cargar_precios_proveedor``; ``ventas``,
    ``compras_por_recibir`` y ``compras_por_facturar`` los de ``documentos`` y ``entregas`` la lista de
    ``documentos.entregas_pendientes``; ``historial`` el de ``historial.cargar_historial``. Lo que no se subió no
    aparece."""
    if ensayo:
        titulo = Markup('<div class="alert alert-info"><b>ENSAYO: no se cambió nada.</b> '
                        'Así quedaría la carga. Si todo se ve bien, pulsa «Cargar».</div>')
    else:
        titulo = Markup('<div class="alert alert-success"><b>CARGA HECHA.</b> Esto fue lo que pasó. '
                        'Volver a cargar el mismo archivo no repite nada.</div>')
    secciones = [titulo]
    if clientes is not None:
        secciones.append(_seccion_contactos('Clientes', clientes))
    if proveedores is not None:
        secciones.append(_seccion_contactos('Proveedores', proveedores))
    if catalogo is not None:
        secciones.append(_seccion_catalogo(catalogo, avisos, con_existencias))
    if precios is not None:
        secciones.append(_seccion_precios(precios))
    if ventas is not None:
        secciones.append(_seccion_ventas(ventas))
    if entregas:
        secciones.append(_seccion_entregas(entregas))
    if compras_por_recibir is not None:
        secciones.append(_seccion_compras_por_recibir(compras_por_recibir))
    if compras_por_facturar is not None:
        secciones.append(_seccion_compras_por_facturar(compras_por_facturar))
    if historial is not None:
        secciones.append(_seccion_historial(historial, ensayo))
    if segundos is not None:
        secciones.append(Markup('<p><i>Tardó %s segundos.</i></p>') % round(segundos))
    return Markup('').join(secciones)
