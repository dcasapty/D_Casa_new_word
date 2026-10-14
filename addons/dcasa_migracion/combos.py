"""Combos de cama + colchón con el tipo «Combo» nativo de Odoo 19 (``combos.csv`` y «armar desde el nombre»).

Cómo queda un combo en Odoo (sin instalar Manufactura):

* El combo es un producto de tipo **Combo** (``product.template.type == 'combo'``) con su precio de venta. Su pestaña
  «Opciones del combo» lleva **grupos** (``product.combo``); cada grupo trae sus opciones (``product.combo.item``), y
  cada opción es un producto REAL del catálogo (la cama, el colchón). Una pieza fija es un grupo de una sola opción; si
  la dueña quiere que la vendedora escoja (el mismo combo con dos colchones posibles), es un grupo con varias opciones.
* Al venderlo, la línea del combo no lleva importe y debajo van las líneas de sus piezas: el precio del combo se reparte
  entre ellas en proporción al precio de lista de cada una (más el recargo de la opción, si lo hay), cada pieza con su
  ITBMS. Las entregas descuentan la cama y el colchón, nunca el combo.
* Odoo no tiene «cantidad» por opción: una pieza que va N veces (3 colchones) son N grupos iguales.

Los combos que ya estaban cargados (productos «COMBO …» de tipo bien, sin publicar) pasan a tipo Combo conservando su
id, su nombre, su precio y su historial. Si el producto tiene existencias, movimientos de inventario o está en una
cotización o venta abierta, NO se toca: queda en el informe como «necesita revisión», con el motivo. Todo es
idempotente.
"""
import difflib
import logging
import re

import psycopg2

from odoo.addons.dcasa_base import itbms_de_venta
from odoo.addons.dcasa_catalogo.catalogo import MODULO as MODULO_CATALOGO
from odoo.addons.dcasa_catalogo.catalogo import categoria_de_nombre, valores_producto_nuevo
from odoo.addons.dcasa_catalogo.inventario_anterior import _variante_por_tamano, leer_inventario_anterior
from odoo.addons.dcasa_catalogo.reglas import clase_de_fila_inventario
from odoo.exceptions import AccessError, UserError, ValidationError

from . import reglas_combos as RC
from .contactos import _motivo

_logger = logging.getLogger(__name__)

PREFIJO_INVENTARIO = 'inventario_anterior_'


def _entorno(env):
    company = env.ref('base.main_company')
    return env(context=dict(env.context, allowed_company_ids=company.ids, lang='es_419'))


# ----------------------------------------------------------------------------------------------
# Buscar piezas y combos
# ----------------------------------------------------------------------------------------------

def clave_de_nombre(nombre):
    """Para comparar nombres sin importar mayúsculas, tildes, espacios sobrantes ni los espacios junto al «+»:
    «COMBO CAMA KING 811KBE+ COLCHÓN» y «combo cama king 811kbe + colchon» son el mismo nombre."""
    return re.sub(r'\s*\+\s*', ' + ', RC.limpio(nombre))


def _numeros_del_nombre(clave):
    """Las fichas del nombre que llevan cifras (los códigos): si dos nombres casi iguales las
    comparten, es el mismo combo."""
    return sorted(f for f in re.findall(r'[a-z0-9]+', clave) if re.search(r'\d', f))


class _Nombres:
    """Los productos por nombre normalizado (una sola lectura por carga)."""

    def __init__(self, env):
        self.vacio = env['product.template']
        self.por_clave = {}
        for plantilla in env['product.template'].with_context(active_test=False).search([]):
            clave = clave_de_nombre(plantilla.name)
            self.por_clave[clave] = self.por_clave.get(clave, self.vacio) | plantilla

    def de(self, nombre):
        return self.por_clave.get(clave_de_nombre(nombre), self.vacio)

    def parecidos(self, nombre):
        """Productos «COMBO …» cuyo nombre se parece mucho al de este combo sin ser igual: la misma cifra en los
        códigos y casi las mismas letras. No son iguales, pero tampoco hay que crear otro al lado."""
        clave = clave_de_nombre(nombre)
        cifras = _numeros_del_nombre(clave)
        parecidos = self.vacio
        for otra, plantillas in self.por_clave.items():
            if otra == clave or not otra.startswith('combo') or _numeros_del_nombre(otra) != cifras:
                continue
            comparador = difflib.SequenceMatcher(None, clave, otra)
            if comparador.quick_ratio() >= 0.9 and comparador.ratio() >= 0.9:
                parecidos |= plantillas
        return parecidos


def _buscar_pieza(env, codigo, nombre, nombres):
    """``(variante, None)`` o ``(None, motivo)``: la pieza (cama, colchón…) del catálogo. Por código y, sin código, por
    nombre exacto normalizado; con el sufijo de tamaño de las variantes (``XHT022-F-W`` → ``XHT022-F-W-FULL``) como en
    el inventario anterior. Nunca inventa ni crea una pieza: si no hay, o hay varias, dice por qué."""
    Variante = env['product.product'].with_context(active_test=False)
    if codigo:
        encontradas = Variante.search([('default_code', '=', codigo)])
        if not encontradas:
            encontradas = _variante_por_tamano(Variante, {'codigo': codigo, 'nombre': nombre})
        if not encontradas:
            return None, 'no hay un producto con ese código'
        if len(encontradas) > 1:
            return None, 'hay varios productos con ese código'
        variante = encontradas
    else:
        plantillas = nombres.de(nombre)
        if not plantillas:
            return None, 'no hay un producto con ese nombre (la pieza no tiene código: se busca por su nombre exacto)'
        if len(plantillas) > 1:
            return None, 'hay varios productos con ese nombre: usa el código'
        variantes = plantillas.with_context(active_test=False).product_variant_ids
        if len(variantes) != 1:
            return None, 'tiene varias medidas: usa el código de la medida'
        variante = variantes
    if not variante.active or not variante.product_tmpl_id.active:
        return None, 'está archivado'
    if variante.type == 'combo':
        return None, 'es otro combo (un combo no lleva combos)'
    return variante, None


PREFIJO_DUPLICADO = 'posible duplicado'


def _buscar_combo(env, combo, nombres):
    """``(plantilla, poner_codigo, error)``: el producto del combo, o una plantilla vacía si hay que crearlo.

    Por código; si ese código no está, por el nombre exacto normalizado de un producto SIN código (los combos viejos no
    tenían): en ese caso ``poner_codigo`` es ``True`` si el código del archivo está libre. Sin código, por nombre exacto
    normalizado. Si hay varios productos con ese nombre, uno con otro código o uno de nombre casi igual (un posible
    duplicado), no se adivina ni se crea otro: ``error`` dice por qué."""
    Plantilla = env['product.template'].with_context(active_test=False)
    Variante = env['product.product'].with_context(active_test=False)
    codigo, nombre = combo['codigo'], combo['nombre']
    if codigo:
        variantes = Variante.search([('default_code', '=', codigo)])
        if len(variantes.product_tmpl_id) > 1:
            return Plantilla.browse(), False, 'hay varios productos con ese código'
        if variantes:
            return variantes.product_tmpl_id, False, None
    con_nombre = nombres.de(nombre) if nombre else Plantilla.browse()
    if not con_nombre and nombre:
        parecidos = nombres.parecidos(nombre)
        if parecidos:
            return Plantilla.browse(), False, (
                f'{PREFIJO_DUPLICADO}: ya hay «{parecidos[0].name}», casi igual: no se creó otro ni se tocó')
    if not codigo:
        if len(con_nombre) > 1:
            return Plantilla.browse(), False, ('hay varios productos con ese nombre (posible duplicado): '
                                               'ponle un código a cada uno')
        return con_nombre, False, None
    sin_codigo = con_nombre.filtered(lambda p: not p.default_code)
    if len(sin_codigo) == 1:
        return sin_codigo, True, None
    if con_nombre:
        return Plantilla.browse(), False, ('ya existe un producto con ese nombre y no se sabe cuál es: el archivo '
                                           f'dice el código {codigo}')
    return Plantilla.browse(), False, None


# ----------------------------------------------------------------------------------------------
# Convertir y armar
# ----------------------------------------------------------------------------------------------

def motivos_para_convertir(env, plantilla):
    """Por qué un producto NO se debe pasar a tipo Combo todavía (lista vacía = se puede).

    * Existencias: un combo no tiene existencias propias. Hay que contarlas y ajustarlas a 0 (el ajuste de inventario
      no impide convertirlo: es solo un conteo).
    * Movimientos de inventario de verdad (entregas, recepciones, traslados) o pendientes: el historial es de un
      producto con existencias y Odoo desaconseja cambiarlo. No se fuerza.
    * Cotizaciones abiertas, o ventas confirmadas con algo por facturar: se quedarían con un combo sin piezas.
    * Varias medidas o colores: un combo no puede tenerlos (una sola línea de «Tamaño» de un valor sí se quita)."""
    variantes = plantilla.with_context(active_test=False).product_variant_ids
    motivos = []
    existencias = sum(env['stock.quant'].sudo().search([
        ('product_id', 'in', variantes.ids), ('location_id.usage', 'in', ('internal', 'transit'))]).mapped('quantity'))
    if existencias:
        motivos.append(f'tiene {existencias:g} unidades en existencia: cuéntalas y ajústalas a 0 en Inventario '
                       '(un combo no tiene existencias propias) y vuelve a cargar')
    movimientos = env['stock.move'].sudo().search([('product_id', 'in', variantes.ids), ('state', '!=', 'cancel')])
    reales = movimientos.filtered(
        lambda m: m.state != 'done' or 'inventory' not in (m.location_id.usage, m.location_dest_id.usage))
    if reales:
        motivos.append(f'tiene {len(reales)} movimientos de inventario (entregas, recepciones o traslados)')
    lineas = env['sale.order.line'].sudo().search([
        ('product_id', 'in', variantes.ids), ('order_id.state', 'in', ('draft', 'sent', 'sale'))])
    abiertas = lineas.filtered(lambda ln: ln.order_id.state != 'sale' or ln.qty_to_invoice > 0).order_id
    if abiertas:
        motivos.append('está en cotizaciones o ventas abiertas (' + ', '.join(abiertas.mapped('name')[:5])
                       + (' …' if len(abiertas) > 5 else '') + '): termínalas o quita el combo de ellas')
    if plantilla.product_variant_count > 1:
        motivos.append('tiene varias medidas o colores: un combo no puede tenerlas')
    return motivos


def _firma(grupos):
    """Lo que identifica una estructura, sin importar el orden: por grupo, sus (producto, recargo)."""
    return sorted(tuple(sorted((producto, round(extra, 2)) for producto, extra in grupo)) for grupo in grupos)


def _firma_de_plantilla(plantilla):
    return _firma([[(item.product_id.id, item.extra_price) for item in grupo.combo_item_ids]
                   for grupo in plantilla.combo_ids])


def _comandos_de_grupos(env, grupos):
    """Crea los grupos de Odoo (``product.combo``) y devuelve el comando para el campo ``combo_ids``."""
    creados = env['product.combo']
    for numero, grupo in enumerate(grupos, start=1):
        creados |= env['product.combo'].create({
            'name': grupo['nombre'], 'sequence': numero * 10,
            'combo_item_ids': [(0, 0, {'product_id': variante.id, 'extra_price': extra})
                               for variante, extra in grupo['opciones']]})
    return [(6, 0, creados.ids)]


def aplicar_estructura(env, plantilla, grupos):
    """Arma el combo ``plantilla`` con ``grupos`` (``[{'nombre', 'opciones': [(variante, recargo)]}]``).

    Devuelve ``(resultado, texto)``: ``convertido`` (pasó a tipo Combo con esas piezas), ``ya_estaba`` (ya era un combo
    con exactamente esas piezas), ``otra_estructura`` (ya era un combo con OTRAS piezas: no se pisa),
    ``necesita_revision`` (no se convirtió; ``texto`` dice por qué) o ``error`` (Odoo lo rechazó; ``texto`` dice por
    qué). No hace commit."""
    if plantilla.type == 'combo':
        if _firma_de_plantilla(plantilla) == _firma([[(v.id, e) for v, e in g['opciones']] for g in grupos]):
            return 'ya_estaba', ''
        return 'otra_estructura', ''
    motivos = motivos_para_convertir(env, plantilla)
    if motivos:
        return 'necesita_revision', '; '.join(motivos)
    try:
        with env.cr.savepoint():
            # La carga del catálogo le puso al combo una línea «Tamaño» de un solo valor (para el filtro de la tienda);
            # un combo no puede tener atributos. Quitarla no cambia el producto: conserva su id y no crea variantes.
            plantilla.attribute_line_ids.unlink()
            plantilla.write({'type': 'combo', 'is_storable': False, 'purchase_ok': False,
                             'combo_ids': _comandos_de_grupos(env, grupos)})
    except (ValidationError, UserError, AccessError, psycopg2.Error) as error:
        return 'error', _motivo(error)
    return 'convertido', ''


def _crear_combo(env, combo, grupos):
    """Un combo nuevo: no publicado, tipo Combo, con el precio del archivo y el ITBMS que se suma (como el catálogo)."""
    company = env.ref('base.main_company')
    valores = valores_producto_nuevo(env, combo['nombre'], combo['precio'] or 0.0, itbms_de_venta(env, company),
                                     categoria_de_nombre(combo['nombre'].split('+')[0]))
    valores.pop('allow_out_of_stock_order', None)
    valores.update({'type': 'combo', 'is_storable': False, 'purchase_ok': False, 'is_published': False})
    if combo['codigo']:
        valores['default_code'] = combo['codigo']
    with env.cr.savepoint():
        valores['combo_ids'] = _comandos_de_grupos(env, grupos)
        return env['product.template'].create(valores)


def _grupos_con_productos(env, grupos_del_archivo, nombres):
    """Busca cada pieza en el catálogo. ``(grupos, faltan)``: ``faltan`` dice cuáles no se encontraron y por qué."""
    grupos, faltan = [], []
    for grupo in grupos_del_archivo:
        opciones = []
        for opcion in grupo['opciones']:
            variante, motivo = _buscar_pieza(env, opcion['codigo'], opcion['nombre'], nombres)
            if motivo:
                texto = f'{opcion["codigo"] or opcion["nombre"]}: {motivo}'
                if texto not in faltan:
                    faltan.append(texto)
            else:
                opciones.append((variante, opcion['extra']))
        grupos.append({'nombre': grupo['nombre'], 'opciones': opciones})
    return grupos, faltan


CLAVES_DEL_RESUMEN = ('creados', 'convertidos', 'ya_estaban', 'otra_estructura', 'sin_piezas', 'necesitan_revision',
                      'con_error', 'precio_distinto', 'codigo_puesto', 'avisos_de_precio', 'archivados', 'omitidos',
                      'no_coinciden', 'posibles_duplicados', 'corregidos', 'piezas_faltantes', 'precio_puesto')


def cargar_combos(env, combos, actualizar_precios=False, corregir_cama=False):
    """Carga los combos de ``reglas_combos.filas_combos``. Devuelve ``(resumen, tratados)``: ``tratados`` son los
    productos que el archivo nombra y ya existían (para que «armar desde el nombre» no los vuelva a tocar) y
    ``resumen`` las listas por grupo:

    * ``creados`` (producto nuevo), ``convertidos`` (ya existía y pasó a tipo Combo), ``ya_estaban``,
      ``otra_estructura`` (ya eran combos con otras piezas: no se pisan), ``sin_piezas`` (el archivo no les dice qué
      llevan), ``archivados`` (la columna ``activo`` dice 0) y ``omitidos`` (los auxiliares «X COLCHÓN … PARA COMBO»,
      que no se cargan);
    * ``necesitan_revision``, ``con_error`` y ``posibles_duplicados``: ``[(clave, motivo)]`` (con_error incluye los
      combos a los que les falta una pieza en el catálogo; las piezas NUNCA se crean). ``piezas_faltantes`` es
      ``[(pieza, en cuántos combos)]``;
    * ``precio_distinto`` ``[(clave, archivo, aquí)]``, ``precio_puesto`` (el producto no tenía precio y recibió el del
      archivo), ``codigo_puesto`` y ``avisos_de_precio`` ``[(clave, texto)]`` (el precio no cuadra con el de sus
      piezas);
    * ``no_coinciden`` ``[(clave, motivo)]``: lo que el nombre del combo dice y las piezas del archivo contradicen (se
      cargó tal cual, para revisar). Con ``corregir_cama``, la cama que no coincide con el CÓDIGO del nombre se cambia
      por la que lleva ese código (si existe) y se anota en ``corregidos`` ``[(clave, texto)]``.

    No hace commit.
    """
    env = _entorno(env)
    nombres = _Nombres(env)
    carga = _CargaDeCombos(env, nombres, actualizar_precios, corregir_cama)
    tratados = env['product.template'].browse()
    for combo in combos:
        plantilla, poner_codigo, error = _buscar_combo(env, combo, nombres)
        tratados |= plantilla
        carga.uno(combo, plantilla, poner_codigo, error)
    resumen = carga.cerrar()
    _logger.info('Carga de combos: %s nuevos, %s convertidos, %s ya estaban, %s con otra estructura, %s sin piezas, '
                 '%s necesitan revisión, %s con error.', len(resumen['creados']), len(resumen['convertidos']),
                 len(resumen['ya_estaban']), len(resumen['otra_estructura']), len(resumen['sin_piezas']),
                 len(resumen['necesitan_revision']), len(resumen['con_error']))
    return resumen, tratados


class _CargaDeCombos:
    """Lo que se hace con cada combo del archivo y lo que se anota en el resumen."""

    def __init__(self, env, nombres, actualizar_precios, corregir_cama):
        self.env = env
        self.nombres = nombres
        self.actualizar_precios = actualizar_precios
        self.corregir_cama = corregir_cama
        self.resumen = {k: [] for k in CLAVES_DEL_RESUMEN}
        self.faltantes = {}
        self._indices = None   # (camas, por id, nombres, códigos): se arma la primera vez que hace falta

    def cerrar(self):
        self.resumen['piezas_faltantes'] = sorted(self.faltantes.items(), key=lambda par: (-par[1], par[0]))
        return self.resumen

    def indices(self):
        self._indices = self._indices or _indices_para_contraste(self.env)
        return self._indices

    def uno(self, combo, plantilla, poner_codigo, error):
        clave, resumen = combo['clave'], self.resumen
        if combo['archivado']:
            resumen['archivados'].append(clave)
        elif clase_de_fila_inventario(combo['nombre'] or clave) == 'omitir':
            resumen['omitidos'].append(clave)
        elif combo['sin_piezas']:
            resumen['sin_piezas'].append(clave)
        elif error:
            clave_de_lista = 'posibles_duplicados' if error.startswith(PREFIJO_DUPLICADO) else 'con_error'
            resumen[clave_de_lista].append((clave, error))
        elif plantilla and plantilla.type != 'combo' and 'combo' not in RC.limpio(plantilla.name):
            resumen['con_error'].append((clave, f'el código es del producto «{plantilla.name}», que no parece un '
                                                'combo: no se convierte'))
        else:
            grupos, faltan = _grupos_con_productos(self.env, combo['grupos'], self.nombres)
            if faltan:
                resumen['con_error'].append((clave, 'no se cargó, falta en el catálogo: ' + '; '.join(faltan)))
                for texto in faltan:
                    self.faltantes[texto] = self.faltantes.get(texto, 0) + 1
                self._contrastar_lo_que_hay(combo, grupos)
                return
            if self.corregir_cama:
                self._corregir_la_cama(combo, grupos)
            if plantilla:
                self._existente(combo, plantilla, poner_codigo, grupos)
            else:
                self._nuevo(combo, grupos)

    def _contrastar_lo_que_hay(self, combo, grupos):
        """A un combo al que le falta una pieza aún se le mira el colchón que sí está contra su nombre."""
        problemas = _contraste(combo['nombre'] or combo['clave'],
                               [[v for v, _e in g['opciones']] for g in grupos if g['opciones']],
                               self.indices(), completo=False)
        if problemas:
            self.resumen['no_coinciden'].append((combo['clave'], '; '.join(problemas)
                                                 + ' (el combo no se cargó: le falta una pieza)'))

    def _corregir_la_cama(self, combo, grupos):
        """Con la casilla encendida: la cama que no es la del CÓDIGO del nombre se cambia por la que lo lleva."""
        camas, por_id, _nombres, _codigos = self.indices()
        buena = RC.cama_por_el_codigo_del_nombre(combo['nombre'], camas)
        if not buena:
            return
        for grupo in grupos:
            propias = [por_id.get(v.id) for v, _e in grupo['opciones']]
            if len(propias) == 1 and propias[0] and not RC.es_colchon(propias[0]) and propias[0]['id'] != buena['id']:
                antes = propias[0]
                grupo['opciones'] = [(self.env['product.product'].browse(buena['id']), grupo['opciones'][0][1])]
                self.resumen['corregidos'].append((combo['clave'], f'cama {RC.texto_de(antes)} → {RC.texto_de(buena)}'))
                return

    def _nuevo(self, combo, grupos):
        clave, env = combo['clave'], self.env
        if not combo['nombre']:
            self.resumen['con_error'].append((clave, 'es un combo nuevo y el archivo no trae su nombre'))
            return
        try:
            plantilla = _crear_combo(env, combo, grupos)
        except (ValidationError, UserError, AccessError, psycopg2.Error) as error:
            self.resumen['con_error'].append((clave, _motivo(error)))
            return
        self.resumen['creados'].append(clave)
        self._revisar(clave, plantilla, grupos, combo['precio'])

    def _existente(self, combo, plantilla, poner_codigo, grupos):
        clave = combo['clave']
        resultado, texto = aplicar_estructura(self.env, plantilla, grupos)
        if resultado == 'necesita_revision':
            self.resumen['necesitan_revision'].append((clave, texto))
        elif resultado == 'error':
            self.resumen['con_error'].append((clave, texto))
        else:
            self.resumen[{'convertido': 'convertidos', 'ya_estaba': 'ya_estaban',
                          'otra_estructura': 'otra_estructura'}[resultado]].append(clave)
            if resultado != 'otra_estructura':
                _ajustar_ficha(self.env, plantilla, combo, poner_codigo, self.actualizar_precios, self.resumen)
                self._revisar(clave, plantilla, grupos, plantilla.list_price)

    def _revisar(self, clave, plantilla, grupos, precio):
        """Avisos de un combo ya cargado: su precio frente al de sus piezas y su nombre frente a sus piezas."""
        self.resumen['avisos_de_precio'].extend((clave, aviso) for aviso in RC.aviso_de_precio(
            precio, [min(v.lst_price for v, _extra in g['opciones']) for g in grupos]))
        problemas = _contraste(plantilla.name, [[v for v, _e in g['opciones']] for g in grupos], self.indices())
        if not problemas:
            return
        camas = self.indices()[0]
        if not self.corregir_cama and RC.cama_por_el_codigo_del_nombre(plantilla.name, camas):
            problemas.append('existe la cama con el código del nombre: la casilla «Corregir la cama por el código del '
                             'nombre» la pone')
        self.resumen['no_coinciden'].append((clave, '; '.join(problemas)))


def _indices_para_contraste(env):
    camas, colchones = indices_de_piezas(env)
    nombres, codigos = _origenes(_entorno(env))
    return camas, {p['id']: p for p in camas + colchones}, nombres, codigos


def _anotar_contraste(resumen, clave, plantilla, grupos, contraste):
    problemas = _contraste(plantilla.name, grupos, contraste)
    if problemas:
        resumen['no_coinciden'].append((clave, '; '.join(problemas)))


def _ajustar_ficha(env, plantilla, combo, poner_codigo, actualizar_precios, resumen):
    """El precio del archivo y el código que le faltaba al combo. Lo demás no se toca.

    El precio del archivo solo se aplica si el producto no tenía precio (o si se pidió con la casilla «También cambiar
    precio y costo»); si difiere, se anota."""
    precio = combo['precio']
    if precio and abs(plantilla.list_price - precio) >= 0.005:
        if actualizar_precios or not plantilla.list_price:
            plantilla.list_price = precio
            if not actualizar_precios:
                resumen['precio_puesto'].append(combo['clave'])
        else:
            resumen['precio_distinto'].append((combo['clave'], precio, plantilla.list_price))
    if poner_codigo and not plantilla.default_code and not env['product.product'].with_context(
            active_test=False).search_count([('default_code', '=', combo['codigo'])], limit=1):
        plantilla.default_code = combo['codigo']
        resumen['codigo_puesto'].append(combo['clave'])


# ----------------------------------------------------------------------------------------------
# Armar los combos desde su nombre
# ----------------------------------------------------------------------------------------------

def _origenes(env):
    """{id de plantilla: 'inventario' | 'catalogo'} según de dónde salió el producto, y los códigos del inventario
    anterior (el CSV del módulo ``dcasa_catalogo``)."""
    nombres = {d['res_id']: d['name'] for d in env['ir.model.data'].sudo().search_read(
        [('module', '=', MODULO_CATALOGO), ('model', '=', 'product.template')], ['name', 'res_id'])}
    codigos = {fila['codigo'] for fila in leer_inventario_anterior() if fila['codigo']}
    return nombres, codigos


def _describir(variante, nombres, codigos, existencias=None):
    """Una variante como la ven las reglas puras: ``id, codigo, nombre, tamano, precio, existencias, origen``."""
    nombre = variante.with_context(display_default_code=False).display_name
    codigo = variante.default_code or ''
    xmlid = nombres.get(variante.product_tmpl_id.id, '')
    base = codigo.rsplit('-', 1)[0] if codigo.rsplit('-', 1)[-1].lower() in RC.TAMANOS else codigo
    es_colchon = bool(re.search(r'\bcolch', RC.limpio(nombre)))
    return {
        'id': variante.id, 'codigo': codigo, 'nombre': nombre, 'precio': variante.lst_price,
        'existencias': variante.qty_available if existencias is None else existencias.get(variante.id, 0.0),
        'origen': 'inventario' if xmlid.startswith(PREFIJO_INVENTARIO) or codigo in codigos or base in codigos
        else 'catalogo',
        'tamano': RC.tamano_de_colchon(nombre) if es_colchon
        else RC.tamano_de_cama(nombre) or RC.tamano_de_cama(codigo.replace('-', ' ')),
    }


def indices_de_piezas(env):
    """``(camas, colchones)`` para ``reglas_combos.resolver_combo``: los productos que se pueden vender, sin combos ni
    colchonetas. Cada uno: ``id, codigo, nombre, tamano, precio, existencias, origen``. ``origen`` es ``inventario``
    si viene del inventario del sistema anterior (lo creó esa carga o su código está en él)."""
    env = _entorno(env)
    nombres, codigos = _origenes(env)
    variantes = env['product.product'].search([('type', '=', 'consu'), ('sale_ok', '=', True)])
    existencias = {v.id: v.qty_available for v in variantes}
    camas, colchones = [], []
    for variante in variantes:
        pieza = _describir(variante, nombres, codigos, existencias)
        claro = RC.limpio(pieza['nombre'])
        if claro.startswith('combo') or 'colchoneta' in claro or clase_de_fila_inventario(pieza['nombre']) == 'omitir':
            continue
        (colchones if re.search(r'\bcolch', claro) else camas).append(pieza)
    return camas, colchones


def _contraste(nombre, grupos, contraste, completo=True):
    """Lo que no coincide entre el nombre del combo y las piezas de ``grupos`` (listas de variantes por grupo)."""
    camas, por_id, nombres, codigos = contraste
    descritos = [[por_id.get(v.id) or _describir(v, nombres, codigos) for v in grupo] for grupo in grupos]
    return RC.contrastar_con_el_nombre(nombre, descritos, camas, completo)


def _texto_pieza(pieza):
    codigo = f'[{pieza["codigo"]}] ' if pieza.get('codigo') else ''
    precio, existencias = pieza.get('precio') or 0, pieza.get('existencias') or 0
    return f'{codigo}{pieza["nombre"]} — ${precio:,.2f} — {existencias:g} en existencia'


def combos_por_nombre(env):
    """Los productos «COMBO … + COLCHÓN» que todavía no son tipo Combo, y los que ya lo son."""
    env = _entorno(env)
    plantillas = env['product.template'].with_context(active_test=False).search([('name', 'ilike', 'combo')])
    de_nombre = plantillas.filtered(lambda p: clase_de_fila_inventario(p.name) == 'combo' and p.active)
    return de_nombre.filtered(lambda p: p.type != 'combo'), de_nombre.filtered(lambda p: p.type == 'combo')


def armar_desde_nombre(env, tratados=()):
    """Lee el nombre de cada combo sin estructura, resuelve su cama y su colchón y, de los **claros**, arma el combo.

    ``tratados`` son los combos (productos) que ya armó ``combos.csv`` en esta misma carga: no se vuelven a mirar.
    Devuelve un diccionario de listas:

    * ``cargados``: ``(nombre, texto de la cama, texto del colchón)`` de los que pasaron a tipo Combo;
    * ``dudosos`` y ``sin_resolver``: ``(nombre, motivo, [(rol, texto de una opción)])``: no se tocan;
    * ``necesitan_revision`` y ``con_error``: ``(nombre, motivo)``;
    * ``ya_estaban``: nombres de los que ya son tipo Combo (no se tocan);
    * ``no_coinciden``: ``(nombre, motivo)`` de los que ya son tipo Combo y cuyas piezas contradicen lo que dice su
      nombre (el contraste: solo para revisar);
    * ``con_alternativa``: ``(pieza elegida, por qué, [otras piezas parecidas], en cuántos combos)`` de las piezas donde
      había otro producto igual en el catálogo;
    * ``avisos_de_precio``: ``(nombre, texto)`` de los claros cuyo precio no cuadra con el de sus piezas.

    Solo los claros se cargan. No hace commit."""
    env = _entorno(env)
    resumen = {k: [] for k in ('cargados', 'dudosos', 'sin_resolver', 'necesitan_revision', 'con_error', 'ya_estaban',
                               'avisos_de_precio', 'con_alternativa', 'no_coinciden')}
    pendientes, ya_combos = combos_por_nombre(env)
    resumen['ya_estaban'] = [p.name for p in ya_combos if p not in tratados]
    contraste = _indices_para_contraste(env)
    camas, colchones = indices_de_piezas(env)
    for plantilla in ya_combos - tratados:
        _anotar_contraste(resumen, plantilla.name, plantilla,
                          [grupo.combo_item_ids.product_id for grupo in plantilla.combo_ids.sorted('sequence')],
                          contraste)
    Variante = env['product.product']
    alternativas = {}
    for plantilla in pendientes - tratados:
        resolucion = RC.resolver_combo(plantilla.name, camas, colchones, plantilla.list_price)
        if resolucion['estado'] != RC.CLARO:
            clave = 'dudosos' if resolucion['estado'] == RC.DUDOSO else 'sin_resolver'
            resumen[clave].append((plantilla.name, resolucion['motivo'], _opciones_de(resolucion)))
            continue
        cama, colchon, n = resolucion['cama'], resolucion['colchon'], resolucion['cantidad_colchones']
        grupos = [{'nombre': RC.nombre_de_grupo(cama['elegida']['nombre']),
                   'opciones': [(Variante.browse(cama['elegida']['id']), 0.0)]}]
        grupos += [{'nombre': RC.nombre_de_grupo(colchon['elegida']['nombre'], i, n),
                    'opciones': [(Variante.browse(colchon['elegida']['id']), 0.0)]} for i in range(1, n + 1)]
        resultado, texto = aplicar_estructura(env, plantilla, grupos)
        if resultado == 'necesita_revision':
            resumen['necesitan_revision'].append((plantilla.name, texto))
            continue
        if resultado == 'error':
            resumen['con_error'].append((plantilla.name, texto))
            continue
        resumen['cargados'].append((plantilla.name, _texto_pieza(cama['elegida']),
                                    (f'{n} × ' if n > 1 else '') + _texto_pieza(colchon['elegida'])))
        for pieza in (cama, colchon):
            if pieza['nota']:
                alternativas.setdefault(pieza['elegida']['id'], [pieza, 0])[1] += 1
        resumen['avisos_de_precio'].extend((plantilla.name, aviso) for aviso in resolucion['avisos_de_precio'])
    resumen['con_alternativa'] = [
        (_texto_pieza(pieza['elegida']), pieza['nota'], [_texto_pieza(otra) for otra in pieza['otras']], veces)
        for pieza, veces in alternativas.values()]
    _logger.info('Combos desde su nombre: %s armados, %s dudosos, %s sin resolver, %s necesitan revisión.',
                 len(resumen['cargados']), len(resumen['dudosos']), len(resumen['sin_resolver']),
                 len(resumen['necesitan_revision']))
    return resumen


def _opciones_de(resolucion):
    """Las opciones que se muestran en el informe de un combo dudoso o sin resolver: ``[('Cama', texto)]``."""
    opciones = []
    for rol, clave in (('Cama', 'cama'), ('Colchón', 'colchon')):
        pieza = resolucion[clave]
        if not pieza or pieza['estado'] == RC.CLARO:
            continue
        opciones.extend((rol, _texto_pieza(o)) for o in pieza['opciones'])
    return opciones
