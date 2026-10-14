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
    enlazados = resumen['enlazados']
    return Markup('<h4>%s</h4><ul>%s%s%s%s%s</ul>%s%s') % (
        titulo,
        _linea('Fichas nuevas', len(resumen['creados'])),
        _linea('Ya estaban (no se tocan)', len(resumen['ya_estaban'])),
        ampliadas,
        _linea('Repetidos enlazados a una ficha con el mismo RUC o cédula (no se crea otra)', len(enlazados))
        if enlazados else Markup(''),
        _linea('No se pudieron crear', len(errores)),
        _lista(enlazados, _enlazado),
        _lista(errores, lambda e: Markup('n.º %s — %s: %s') % (e[0], e[1], e[2])),
    )


def _enlazado(item):
    """«n.º 4034 usa la ficha del n.º 4033»; si esa ficha ya existía por otro lado, se dice su nombre."""
    id_viejo, otro_numero, nombre = item
    if otro_numero:
        return Markup('n.º %s usa la ficha del n.º %s (mismo RUC o cédula)') % (id_viejo, otro_numero)
    return Markup('n.º %s usa la ficha que ya existía de «%s» (mismo RUC o cédula)') % (id_viejo, nombre)


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


LIMITE_COMBOS = 120


def _combo_con_motivo(item):
    return Markup('%s — %s') % (item[0], item[1])


def _seccion_combos(resumen):
    """Los combos de combos.csv (tipo Combo de Odoo)."""
    cabecera = Markup('').join([
        _linea('Combos nuevos', len(resumen['creados'])),
        _linea('Ya existían y pasaron a tipo Combo (conservan su nombre, precio e historial)',
               len(resumen['convertidos'])),
        _linea('Ya estaban con esas mismas piezas (no se tocan)', len(resumen['ya_estaban'])),
        _linea('Ya eran combos con OTRAS piezas (no se pisan)', len(resumen['otra_estructura'])),
        _linea('Sin piezas en el archivo (no se cargan)', len(resumen['sin_piezas'])),
        _linea('Archivados en el sistema anterior (no se cargan)', len(resumen['archivados'])),
        _linea('Auxiliares «X COLCHÓN … PARA COMBO» (no se cargan, a propósito)', len(resumen['omitidos'])),
        _linea('Necesitan revisión (no se tocaron)', len(resumen['necesitan_revision'])),
        _linea('No se pudieron cargar', len(resumen['con_error'])),
        _linea('No coinciden con su nombre (se cargaron como dice el archivo: revisar)',
               len(resumen['no_coinciden'])),
    ])
    listas = Markup('').join([
        _titulo_lista('No coincide con el nombre: el combo dice una cosa y sus piezas son otras (se cargó tal cual '
                      'viene en el archivo)', resumen['no_coinciden'], _combo_con_motivo),
        _titulo_lista('Necesitan revisión: no se convirtieron', resumen['necesitan_revision'], _combo_con_motivo),
        _titulo_lista('No se pudieron cargar (lo que falta en el catálogo no se inventa)', resumen['con_error'],
                      _combo_con_motivo),
        _titulo_lista('Ya eran combos con otras piezas (el archivo dice otra cosa: se respetó lo que hay)',
                      resumen['otra_estructura'], escape),
        _titulo_lista('El archivo no dice qué piezas lleva', resumen['sin_piezas'], escape),
        _titulo_lista('Archivados en el sistema anterior', resumen['archivados'], escape),
        _titulo_lista('Auxiliares que no se cargan', resumen['omitidos'], escape),
        _titulo_lista('Precio del archivo distinto al de aquí (no se cambió; la casilla «También cambiar precio» '
                      'lo cambia)', resumen['precio_distinto'],
                      lambda e: Markup('%s — archivo $%s, aquí $%s') % (e[0], f'{e[1]:,.2f}', f'{e[2]:,.2f}')),
        _titulo_lista('Se les puso el código del archivo (no tenían)', resumen['codigo_puesto'], escape),
        _titulo_lista('Revisar el precio', resumen['avisos_de_precio'], _combo_con_motivo),
    ])
    return Markup('<h4>Combos de cama y colchón (combos.csv)</h4><ul>%s</ul>%s') % (cabecera, listas)


def _titulo_lista(titulo, items, formato):
    if not items:
        return Markup('')
    return Markup('<p><b>%s</b> (%s)</p>%s') % (titulo, len(items), _lista(items, formato, LIMITE_COMBOS))


def _opciones(item):
    return Markup('<br/>').join(Markup('<i>%s:</i> %s') % (rol, texto) for rol, texto in item[2])


def _combo_con_opciones(item):
    return Markup('<b>%s</b> — %s%s') % (item[0], item[1], Markup('<br/>%s') % _opciones(item) if item[2] else '')


def _seccion_combos_nombre(resumen):
    """«Armar los combos desde su nombre»: claros (se cargan), dudosos y sin resolver (solo se listan)."""
    cabecera = Markup('').join([
        _linea('Claros: armados (un solo producto posible para su cama y su colchón)', len(resumen['cargados'])),
        _linea('Dudosos: varios productos posibles o una suposición (NO se cargan: decide la dueña)',
               len(resumen['dudosos'])),
        _linea('Sin resolver: no se encontró su cama o su colchón (NO se cargan)', len(resumen['sin_resolver'])),
        _linea('Necesitan revisión (no se tocaron)', len(resumen['necesitan_revision'])),
        _linea('No se pudieron armar', len(resumen['con_error'])),
        _linea('Ya eran tipo Combo (no se tocan)', len(resumen['ya_estaban'])),
        _linea('Ya eran combos pero sus piezas no coinciden con su nombre (revisar)', len(resumen['no_coinciden'])),
    ])
    listas = Markup('').join([
        _titulo_lista('No coincide con el nombre: ya eran combos y sus piezas contradicen su nombre',
                      resumen['no_coinciden'], _combo_con_motivo),
        _titulo_lista('Dudosos: escoge cuál es y dímelo, o arma el combo a mano', resumen['dudosos'],
                      _combo_con_opciones),
        _titulo_lista('Sin resolver', resumen['sin_resolver'], _combo_con_opciones),
        _titulo_lista('Necesitan revisión: no se convirtieron', resumen['necesitan_revision'], _combo_con_motivo),
        _titulo_lista('No se pudieron armar', resumen['con_error'], _combo_con_motivo),
        _titulo_lista('Revisar el precio', resumen['avisos_de_precio'], _combo_con_motivo),
        _titulo_lista(
            'Armados con un producto que tiene otro igual en el catálogo (revisa que sea el correcto)',
            resumen['con_alternativa'],
            lambda a: Markup('%s — %s (en %s combos).<br/>%s') % (
                a[0], a[1], a[3], Markup('<br/>').join(Markup('Otro igual: %s') % otra for otra in a[2]))),
        _titulo_lista('Armados', resumen['cargados'],
                      lambda c: Markup('<b>%s</b><br/>Cama: %s<br/>Colchón: %s') % (c[0], c[1], c[2])),
    ])
    return Markup('<h4>Combos armados desde su nombre</h4><ul>%s</ul>%s') % (cabecera, listas)


def informe_html(ensayo, clientes=None, catalogo=None, avisos=None, con_existencias=True, segundos=None,
                 proveedores=None, precios=None, ventas=None, entregas=None, compras_por_recibir=None,
                 compras_por_facturar=None, historial=None, combos=None, combos_nombre=None):
    """El HTML del informe. ``clientes`` y ``proveedores`` son los resúmenes de ``cargar_contactos``; ``catalogo``
    y ``avisos`` los de ``cargar_catalogo``; ``precios`` el de ``cargar_precios_proveedor``; ``combos`` el de
    ``combos.cargar_combos`` y ``combos_nombre`` el de ``combos.armar_desde_nombre``; ``ventas``,
    ``compras_por_recibir`` y ``compras_por_facturar`` los de ``documentos`` y ``entregas`` la lista de
    ``documentos.entregas_pendientes``; ``historial`` el de ``historial.cargar_historial``. Lo que no se subió no
    aparece."""
    if ensayo:
        titulo = Markup('<div class="alert alert-info"><b>ENSAYO: no se cambió nada.</b> '
                        'Así quedaría la carga. Si todo se ve bien, pulsa «Cargar».</div>')
    else:
        titulo = Markup('<div class="alert alert-success"><b>CARGA HECHA.</b> Esto fue lo que pasó. '
                        'Volver a cargar el mismo archivo no repite nada.</div>')
    secciones = [titulo] + [armar() for hay, armar in (
        (clientes is not None, lambda: _seccion_contactos('Clientes', clientes)),
        (proveedores is not None, lambda: _seccion_contactos('Proveedores', proveedores)),
        (catalogo is not None, lambda: _seccion_catalogo(catalogo, avisos, con_existencias)),
        (precios is not None, lambda: _seccion_precios(precios)),
        (combos is not None, lambda: _seccion_combos(combos)),
        (combos_nombre is not None, lambda: _seccion_combos_nombre(combos_nombre)),
        (ventas is not None, lambda: _seccion_ventas(ventas)),
        (bool(entregas), lambda: _seccion_entregas(entregas)),
        (compras_por_recibir is not None, lambda: _seccion_compras_por_recibir(compras_por_recibir)),
        (compras_por_facturar is not None, lambda: _seccion_compras_por_facturar(compras_por_facturar)),
        (historial is not None, lambda: _seccion_historial(historial, ensayo)),
        (segundos is not None, lambda: Markup('<p><i>Tardó %s segundos.</i></p>') % round(segundos)),
    ) if hay]
    return Markup('').join(secciones)
