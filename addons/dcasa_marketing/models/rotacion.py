"""«Rotación» (pedido de Gerencia, 2026-11-22): qué productos no se mueven, cuánto capital hay parado en ellos y qué
conviene hacer, medido con días y con el flujo de ventas, no solo «lo más movido y lo más quieto».

Lo pidió el jefe: «que indique cuáles productos no han tenido rotación y poder definir en cuánto tiempo (30, 60, 90
días…) a los fines de bajarlos de precio y recuperar capital de trabajo; que se enfoque en los de mejor rotación o
prueba en nuevos SKU que mejoren márgenes, o que sean productos ancla».

Qué cuenta cada cifra (todo sale de la base; nada se estima ni se inventa):

* **Ventas**: las facturas de cliente publicadas, la misma base del Inicio, Marketing y Reponer (``Tablero``: sin
  servicios ni anticipos; las notas de crédito restan unidades). Un día de venta es la fecha de la factura. Una
  «ventana de N días» son los últimos N días corridos, hoy incluido (hora de Panamá).
* **Días sin vender**: de hoy a la fecha de su última factura de cliente. Los grupos son exactos y no se solapan:
  menos de 30 días, 30 a 59, 60 a 89, 90 a 179 y 180 o más (``CORTES``); y «nunca vendido» si no tiene factura.
* **Nuevo**: lo que **llegó de un proveedor** hace menos de 30 días y todavía no tiene ventas: no se le puede exigir
  que haya rotado. Solo cuentan las recepciones de compra: un ajuste de inventario o una carga inicial no es una
  llegada. Sin ninguna recepción registrada, la fecha de llegada se ignora (nunca se inventa).
* **Con pedido abierto**: tiene un pedido confirmado que todavía no se factura entero. Esa mercancía ya tiene dueño:
  no se ofrece como candidata a rebajar aunque lleve meses sin facturarse.
* **Ancla**: los productos que **juntos hacen el 80 % de las unidades vendidas en 90 días** (la regla de Pareto,
  80/20): los que traen a la gente a la tienda. Se calcula sobre toda la tienda, aunque la pantalla esté filtrada a
  una categoría. No se rebajan sin pensarlo: se cuidan.
* **Cobertura**: días que alcanza lo que hay al ritmo de las ventas de los últimos 90 días (existencias ÷ unidades
  vendidas por día); sin ventas en 90 días no se calcula. Cuánto pedir y cuándo lo calcula Reponer.
* **Capital parado** (solo Gerencia y administradores): lo que costó la mercancía que hay, con la valuación de Odoo,
  la misma de «Valor del inventario». **Margen**: (precio de venta sin ITBMS − costo) ÷ precio, como en esa pantalla.
* **Si se rebaja X %** (simulación; no cambia ningún precio): el precio rebajado por las unidades que hay, lo que
  se recuperaría en caja, lo que queda sobre el costo y cuántos productos quedarían por debajo del costo. El
  «precio mínimo para no perder» es el costo.

Quién entra: Gerencia, administradores y el rol Marketing (``dcasa.marketing.GRUPOS``); el servidor lo exige. El
dinero (costos, capital, márgenes, la simulación) es solo de Gerencia y administradores (``_ve_utilidad``); el rol
Marketing ve unidades y días. El Excel lo arma el servidor (``controllers/rotacion.py``) con las mismas cifras.
"""
import io
import re
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

# Días sin vender: los grupos van «menos de 30», «30 a 59», «60 a 89», «90 a 179» y «180 o más».
CORTES = (30, 60, 90, 180)
VENTANAS = (30, 60, 90)
VENTANA_DE_COBERTURA = 90
PARETO = 0.80
DIAS_DE_UN_NUEVO = 30
FILAS = 100
FILAS_MAXIMAS = 100000
ORDENES = ('capital', 'dias', 'rotacion', 'margen', 'cobertura', 'nombre')
REBAJA_MAXIMA = 95
TOPE_DE_IDS = 2000

# De «se mueve» a «lo más parado»: el orden de las tarjetas. (clave, nombre corto, frase)
GRUPOS = (
    ('v30', 'Menos de 30 días', 'Se vendió hace menos de 30 días'),
    ('v60', '30 a 59 días', 'Sin vender de 30 a 59 días'),
    ('v90', '60 a 89 días', 'Sin vender de 60 a 89 días'),
    ('v180', '90 a 179 días', 'Sin vender de 90 a 179 días'),
    ('mas180', '180 días o más', 'Sin vender 180 días o más'),
    ('nunca', 'Nunca vendido', 'Nunca se ha vendido (no tiene ni una factura)'),
    ('nuevo', 'Llegó hace poco', 'Llegó hace menos de 30 días y todavía no se vende'),
    ('abierto', 'Pedido abierto', 'Tiene un pedido confirmado que falta facturar'),
)
# Lo que se puede elegir ver: un grupo exacto, «o más» (suma de grupos: 30 o más = todo lo que lleva 30 días o más sin
# venderse, sin los nuevos ni los de pedido abierto) o los ancla.
ACUMULADOS = {
    'mas_de_30': ('v60', 'v90', 'v180', 'mas180', 'nunca'),
    'mas_de_60': ('v90', 'v180', 'mas180', 'nunca'),
    'mas_de_90': ('v180', 'mas180', 'nunca'),
    'mas_de_180': ('mas180', 'nunca'),
}
NOMBRES_ACUMULADOS = {
    'mas_de_30': '30 días o más sin vender', 'mas_de_60': '60 días o más sin vender',
    'mas_de_90': '90 días o más sin vender', 'mas_de_180': '180 días o más sin vender',
}
CLAVES_DE_GRUPO = tuple(g[0] for g in GRUPOS)
VISTAS = ('todos', 'ancla') + CLAVES_DE_GRUPO + tuple(ACUMULADOS)


def _grupo_por_dias(dias):
    """``v30``, ``v60``, ``v90``, ``v180`` o ``mas180`` según los días que lleva sin venderse."""
    if dias < CORTES[0]:
        return 'v30'
    if dias < CORTES[1]:
        return 'v60'
    if dias < CORTES[2]:
        return 'v90'
    if dias < CORTES[3]:
        return 'v180'
    return 'mas180'


class DcasaRotacion(models.AbstractModel):
    _name = 'dcasa.rotacion'
    _description = "Rotación del inventario de D'CASA: qué se mueve, qué no y cuánto capital hay parado"

    # ------------------------------------------------------------------
    # Permisos y entradas
    # ------------------------------------------------------------------

    @api.model
    def _exigir(self):
        self.env['dcasa.marketing']._exigir()

    @api.model
    def _con_dinero(self):
        """Costos, capital, márgenes y la simulación de rebaja: solo Gerencia y administradores."""
        return self.env['dcasa.tablero']._ve_utilidad()

    @api.model
    def datos(self, vista=None, categoria=None, texto='', orden=None, rebaja=None):
        """La pantalla: las tarjetas por grupo, el resumen, la lista filtrada y, si se pide, la simulación de rebaja."""
        self._exigir()
        return self._datos(vista, categoria, texto, orden, rebaja)

    @api.model
    def _validar(self, vista, categoria, texto, orden, rebaja):
        vista = vista or 'todos'
        if vista not in VISTAS:
            raise UserError(self.env._('Elige qué productos ver de la lista.'))
        if texto is not None and not isinstance(texto, str):
            raise UserError(self.env._('Escribe el nombre o el código del producto.'))
        con_dinero = self._con_dinero()
        orden = orden or ('capital' if con_dinero else 'dias')
        if orden not in ORDENES:
            raise UserError(self.env._('Elige cómo ordenar la lista.'))
        if not con_dinero and orden in ('capital', 'margen'):
            orden = 'dias'
        if rebaja in (None, False, ''):
            rebaja = None
        else:
            if isinstance(rebaja, bool) or not isinstance(rebaja, (int, float, str)):
                raise UserError(self.env._('El descuento es un número entre 1 y %s.', REBAJA_MAXIMA))
            try:
                rebaja = float(rebaja)
            except ValueError as error:
                raise UserError(self.env._('El descuento es un número entre 1 y %s.', REBAJA_MAXIMA)) from error
            if not 0 < rebaja <= REBAJA_MAXIMA:
                raise UserError(self.env._('El descuento es un número entre 1 y %s.', REBAJA_MAXIMA))
            if not con_dinero:
                rebaja = None
        return vista, (texto or '').strip()[:100], orden, rebaja

    # ------------------------------------------------------------------
    # El cálculo: una fila por producto
    # ------------------------------------------------------------------

    @api.model
    def _ventas_por_plantilla(self, hoy):
        """``{plantilla: {'ultima', 'u30', 'u60', 'u90', 'v90'}}`` de las facturas de cliente publicadas: la última
        fecha de venta, las unidades netas (las notas de crédito restan) de cada ventana y en cuántas facturas salió en
        90 días."""
        Linea = self.env['account.move.line'].sudo()
        base = [('parent_state', '=', 'posted'), ('display_type', '=', 'product'), ('product_id', '!=', False),
                ('product_id.type', '!=', 'service'), ('is_downpayment', '=', False),
                ('company_id', 'in', self.env.companies.ids), ('date', '<=', hoy)]
        ventas = defaultdict(lambda: {'ultima': None, 'u30': 0.0, 'u60': 0.0, 'u90': 0.0, 'v90': 0})
        for producto, dia in Linea._read_group(base + [('move_id.move_type', '=', 'out_invoice')],
                                               ['product_id'], ['date:max']):
            plantilla = producto.product_tmpl_id.id
            if dia and (ventas[plantilla]['ultima'] is None or dia > ventas[plantilla]['ultima']):
                ventas[plantilla]['ultima'] = dia
        for dias in VENTANAS:
            desde = hoy - timedelta(days=dias - 1)
            for tipo, signo in (('out_invoice', 1), ('out_refund', -1)):
                for producto, unidades, facturas in Linea._read_group(
                        base + [('move_id.move_type', '=', tipo), ('date', '>=', desde)],
                        ['product_id'], ['quantity:sum', 'move_id:count_distinct']):
                    fila = ventas[producto.product_tmpl_id.id]
                    fila[f'u{dias}'] += signo * unidades
                    if dias == VENTANA_DE_COBERTURA and signo > 0:
                        fila['v90'] += facturas
        return ventas

    @api.model
    def _llegadas(self, plantillas, hoy):
        """``{plantilla: día de su primera recepción de un proveedor}`` (solo compras; sin recepciones, no sale)."""
        if not plantillas:
            return {}
        movimientos = self.env['stock.move'].sudo()._read_group(
            [('state', '=', 'done'), ('product_id.product_tmpl_id', 'in', plantillas.ids),
             ('location_id.usage', '=', 'supplier'), ('location_dest_id.usage', '=', 'internal'),
             ('company_id', 'in', self.env.companies.ids)],
            ['product_id'], ['date:min'])
        primera = {}
        for producto, momento in movimientos:
            if not momento:
                continue
            dia = fields.Datetime.context_timestamp(self, momento).date()
            plantilla = producto.product_tmpl_id.id
            if plantilla not in primera or dia < primera[plantilla]:
                primera[plantilla] = dia
        return primera

    @api.model
    def _pedidos_abiertos(self, plantillas):
        """``{plantilla: unidades}`` de pedidos confirmados que todavía no se facturan enteros."""
        if not plantillas:
            return {}
        lineas = self.env['sale.order.line'].sudo().search_fetch(
            [('order_id.state', '=', 'sale'), ('order_id.invoice_status', '!=', 'invoiced'),
             ('display_type', '=', False), ('is_downpayment', '=', False),
             ('product_id.product_tmpl_id', 'in', plantillas.ids), ('company_id', 'in', self.env.companies.ids)],
            ['product_id', 'product_uom_qty', 'qty_invoiced'])
        abiertos = defaultdict(float)
        for linea in lineas:
            pendiente = linea.product_uom_qty - linea.qty_invoiced
            if pendiente > 0:
                abiertos[linea.product_id.product_tmpl_id.id] += pendiente
        return abiertos

    @api.model
    def _valoradas(self):
        """``{plantilla: {'unidades', 'costo', 'venta'}}``: la mercancía de cada producto al costo (la valuación de
        Odoo) y a precio de venta sin ITBMS, las mismas cifras de «Valor del inventario». Lo negativo no suma."""
        Tablero = self.env['dcasa.tablero']
        por_plantilla = defaultdict(lambda: {'unidades': 0.0, 'costo': 0.0, 'venta': 0.0})
        for producto, unidades, costo in Tablero._existencias_valoradas():
            if unidades < 0:
                continue
            fila = por_plantilla[producto.product_tmpl_id.id]
            fila['unidades'] += unidades
            fila['costo'] += costo
            fila['venta'] += Tablero._venta_sin_itbms(producto, unidades)
        return por_plantilla

    @api.model
    def _calcular(self):
        """Una fila por producto (toda la tienda, sin filtros): ver el docstring del módulo."""
        hoy = fields.Date.context_today(self)
        con_dinero = self._con_dinero()
        Plantilla = self.env['product.template']
        plantillas = Plantilla.search(self.env['dcasa.marketing']._dominio_base() + [('is_storable', '=', True)])
        ventas = self._ventas_por_plantilla(hoy)
        llegadas = self._llegadas(plantillas, hoy)
        abiertos = self._pedidos_abiertos(plantillas)
        valoradas = self._valoradas() if con_dinero else {}

        filas = {}
        for plantilla in plantillas:
            venta = ventas.get(plantilla.id, {})
            u90 = venta.get('u90', 0.0)
            filas_de = {
                'plantilla': plantilla, 'stock': plantilla.dcasa_stock,
                'ultima': venta.get('ultima'), 'u30': venta.get('u30', 0.0), 'u60': venta.get('u60', 0.0),
                'u90': u90, 'v90': venta.get('v90', 0), 'abierto': abiertos.get(plantilla.id, 0.0),
                'llegada': llegadas.get(plantilla.id), 'ancla': False,
            }
            filas_de['dias'] = max((hoy - filas_de['ultima']).days, 0) if filas_de['ultima'] else None
            filas_de['cobertura'] = (round(plantilla.dcasa_stock / (u90 / VENTANA_DE_COBERTURA))
                                     if u90 > 0 and plantilla.dcasa_stock > 0 else None)
            if con_dinero:
                dinero = valoradas.get(plantilla.id, {'unidades': 0.0, 'costo': 0.0, 'venta': 0.0})
                filas_de.update(costo=dinero['costo'], venta_total=dinero['venta'],
                                unidades_valoradas=dinero['unidades'])
            filas_de['grupo'] = self._grupo(filas_de, hoy)
            filas[plantilla.id] = filas_de

        # Ancla: los productos que juntos hacen el 80 % de las unidades de 90 días (toda la tienda).
        total = sum(fila['u90'] for fila in filas.values() if fila['u90'] > 0)
        acumulado = 0.0
        for fila in sorted((f for f in filas.values() if f['u90'] > 0),
                           key=lambda f: (-f['u90'], f['plantilla'].name or '', f['plantilla'].id)):
            if acumulado >= PARETO * total:
                break
            fila['ancla'] = True
            acumulado += fila['u90']
        return hoy, con_dinero, filas

    @api.model
    def _grupo(self, fila, hoy):
        """El grupo de un producto con existencias (los agotados no tienen: ya no hay capital parado)."""
        if fila['stock'] <= 0:
            return None
        if fila['dias'] is not None and fila['dias'] < CORTES[0]:
            return 'v30'
        if fila['abierto'] > 0:
            return 'abierto'
        if fila['dias'] is None:
            nuevo = fila['llegada'] is not None and (hoy - fila['llegada']).days < DIAS_DE_UN_NUEVO
            return 'nuevo' if nuevo else 'nunca'
        return _grupo_por_dias(fila['dias'])

    # ------------------------------------------------------------------
    # Lo que ve la pantalla
    # ------------------------------------------------------------------

    @api.model
    def _de_la_vista(self, fila, vista):
        if vista == 'todos':
            return fila['grupo'] is not None
        if vista == 'ancla':
            return fila['ancla']
        if vista in ACUMULADOS:
            return fila['grupo'] in ACUMULADOS[vista]
        return fila['grupo'] == vista

    @api.model
    def _ordenar(self, filas, orden, con_dinero):
        nombre = self._clave_de_nombre
        if orden == 'dias':
            # Primero los que nunca se vendieron y luego los de última venta más vieja; a igualdad, el de más stock.
            return sorted(filas, key=lambda f: (f['dias'] is not None, -(f['dias'] or 0), -f['stock'], nombre(f)))
        if orden == 'rotacion':
            return sorted(filas, key=lambda f: (-f['u90'], -f['u30'], nombre(f)))
        if orden == 'cobertura':
            return sorted(filas, key=lambda f: (f['cobertura'] is None, f['cobertura'] or 0, nombre(f)))
        if orden == 'margen' and con_dinero:
            return sorted(filas, key=lambda f: (self._margen(f) is None, -(self._margen(f) or 0), nombre(f)))
        if orden == 'capital' and con_dinero:
            return sorted(filas, key=lambda f: (-f['costo'], -f['stock'], nombre(f)))
        return sorted(filas, key=nombre)

    @staticmethod
    def _clave_de_nombre(fila):
        return (fila['plantilla'].name or '').lower(), fila['plantilla'].id

    @staticmethod
    def _margen(fila):
        """Margen sobre el precio (%), o ``None`` sin precio o sin costo."""
        if fila.get('venta_total', 0) > 0 and fila.get('costo', 0) > 0:
            return round((fila['venta_total'] - fila['costo']) / fila['venta_total'] * 100, 1)
        return None

    @api.model
    def _fila_para_la_pantalla(self, fila, con_dinero, rebaja, hoy):
        plantilla = fila['plantilla']
        datos = self.env['dcasa.marketing']._fila(
            plantilla, grupo=fila['grupo'], ancla=fila['ancla'],
            ultima_venta=fields.Date.to_string(fila['ultima']) if fila['ultima'] else None,
            dias_sin_vender=fila['dias'], vendidas_30=round(fila['u30'], 2), vendidas_60=round(fila['u60'], 2),
            vendidas_90=round(fila['u90'], 2), ventas_90=fila['v90'], pedido_abierto=round(fila['abierto'], 2),
            cobertura_dias=fila['cobertura'],
            llegada=fields.Date.to_string(fila['llegada']) if fila['llegada'] else None)
        if con_dinero:
            redondear = self.env.company.currency_id.round
            unidades = fila['unidades_valoradas']
            datos.update(
                capital=redondear(fila['costo']), venta_total=redondear(fila['venta_total']),
                costo_unitario=redondear(fila['costo'] / unidades) if unidades and fila['costo'] > 0 else None,
                precio_unitario=redondear(fila['venta_total'] / unidades) if unidades and fila['venta_total'] > 0
                else None,
                margen=self._margen(fila), sin_costo=fila['stock'] > 0 and fila['costo'] <= 0)
            if rebaja and datos['precio_unitario']:
                con_rebaja = redondear(datos['precio_unitario'] * (1 - rebaja / 100))
                datos['precio_rebaja'] = con_rebaja
                if datos['costo_unitario']:
                    datos['margen_rebaja'] = round((con_rebaja - datos['costo_unitario']) / con_rebaja * 100, 1) \
                        if con_rebaja > 0 else None
                    datos['bajo_costo'] = con_rebaja < datos['costo_unitario']
        return datos

    @api.model
    def _tarjetas(self, filas, con_dinero, total_capital):
        """Una tarjeta por grupo: productos, unidades y, con dinero, el capital al costo y su parte del total."""
        redondear = self.env.company.currency_id.round
        tarjetas = []
        for clave, nombre, frase in GRUPOS:
            del_grupo = [f for f in filas if f['grupo'] == clave]
            tarjeta = {'clave': clave, 'nombre': nombre, 'frase': frase, 'productos': len(del_grupo),
                       'unidades': round(sum(f['stock'] for f in del_grupo), 2)}
            if con_dinero:
                capital = sum(f['costo'] for f in del_grupo)
                tarjeta['capital'] = redondear(capital)
                tarjeta['parte'] = round(capital / total_capital * 100, 1) if total_capital > 0 else None
            tarjetas.append(tarjeta)
        return tarjetas

    @api.model
    def _resumen(self, filas, con_dinero, total_capital):
        con_stock = [f for f in filas if f['grupo'] is not None]
        parados = [f for f in con_stock if f['grupo'] in ACUMULADOS['mas_de_90']]
        resumen = {
            'productos': len(con_stock), 'unidades': round(sum(f['stock'] for f in con_stock), 2),
            'parados_90': len(parados), 'ancla': sum(1 for f in filas if f['ancla']),
        }
        if con_dinero:
            redondear = self.env.company.currency_id.round
            capital_parado = sum(f['costo'] for f in parados)
            resumen.update(
                capital=redondear(total_capital), capital_parado_90=redondear(capital_parado),
                parte_parada_90=round(capital_parado / total_capital * 100, 1) if total_capital > 0 else None,
                sin_costo=sum(1 for f in con_stock if f['costo'] <= 0))
        return resumen

    @api.model
    def _simular(self, filas, rebaja):
        """Si todas esas filas se vendieran con ``rebaja`` % de descuento: cuánto entra, qué queda sobre el costo y
        cuántos productos quedarían por debajo del costo. No cambia ningún precio."""
        redondear = self.env.company.currency_id.round
        capital = ingreso = 0.0
        bajo_costo = unidades_bajo = 0
        sin_precio = 0
        for fila in filas:
            if fila['venta_total'] <= 0:
                sin_precio += 1
                continue
            rebajada = fila['venta_total'] * (1 - rebaja / 100)
            capital += fila['costo']
            ingreso += rebajada
            if rebajada < fila['costo']:
                bajo_costo += 1
                unidades_bajo += fila['stock']
        return {
            'rebaja': rebaja, 'productos': len(filas), 'sin_precio': sin_precio,
            'capital': redondear(capital), 'ingreso': redondear(ingreso), 'ganancia': redondear(ingreso - capital),
            'margen': round((ingreso - capital) / ingreso * 100, 1) if ingreso > 0 else None,
            'bajo_costo': bajo_costo, 'unidades_bajo_costo': round(unidades_bajo, 2),
        }

    @api.model
    def _seleccion(self, vista, categoria, texto, orden):
        """``(hoy, con_dinero, de_la_categoria, elegidas)``: las filas de la categoría (de ellas salen las tarjetas y
        el resumen) y las de la vista, filtradas por el texto y ordenadas."""
        hoy, con_dinero, filas = self._calcular()
        marketing = self.env['dcasa.marketing']
        Plantilla = self.env['product.template']
        base = marketing._dominio_base() + [('is_storable', '=', True)]
        _tipo, filtro = marketing._categoria_pedida(categoria)
        if filtro:
            de_la_categoria = [f for pid, f in filas.items() if pid in set(Plantilla.search(base + filtro).ids)]
        else:
            de_la_categoria = list(filas.values())
        candidatas = de_la_categoria
        if texto:
            con_el_texto = set(Plantilla.search(base + marketing._dominio_de_texto(texto)).ids)
            candidatas = [f for f in de_la_categoria if f['plantilla'].id in con_el_texto]
        elegidas = self._ordenar([f for f in candidatas if self._de_la_vista(f, vista)], orden, con_dinero)
        return hoy, con_dinero, de_la_categoria, elegidas

    @api.model
    def _datos(self, vista=None, categoria=None, texto='', orden=None, rebaja=None):
        vista, texto, orden, rebaja = self._validar(vista, categoria, texto, orden, rebaja)
        hoy, con_dinero, todas, elegidas = self._seleccion(vista, categoria, texto, orden)
        moneda = self.env.company.currency_id
        total_capital = sum(f['costo'] for f in todas if f['grupo'] is not None) if con_dinero else 0.0
        marketing = self.env['dcasa.marketing']
        tipo, _filtro = marketing._categoria_pedida(categoria)
        datos = {
            'hoy': fields.Date.to_string(hoy), 'con_dinero': con_dinero,
            'moneda': {'simbolo': moneda.symbol, 'antes': moneda.position == 'before'},
            'categorias': marketing._lista_de_categorias(), 'categoria': tipo,
            'vista': vista, 'texto': texto, 'orden': orden, 'rebaja': rebaja,
            'vistas': self._vistas(todas),
            'resumen': self._resumen(todas, con_dinero, total_capital),
            'tarjetas': self._tarjetas(todas, con_dinero, total_capital),
            'total': len(elegidas), 'mostrando': min(len(elegidas), FILAS),
            'productos': [self._fila_para_la_pantalla(f, con_dinero, rebaja, hoy) for f in elegidas[:FILAS]],
            'ids': [f['plantilla'].id for f in elegidas[:TOPE_DE_IDS]],
            'como_se_cuenta': self._como_se_cuenta(),
        }
        if con_dinero and rebaja:
            datos['simulacion'] = self._simular(elegidas, rebaja)
        return datos

    @api.model
    def _vistas(self, filas=None):
        """Los botones de «Ver»: de lo que más importa (sin vender hace 30, 60, 90 o 180 días) a lo demás. Con
        ``filas``, cada uno trae cuántos productos tiene."""
        vistas = ([{'clave': 'todos', 'nombre': 'Todos los que tienen existencias'}]
                  + [{'clave': clave, 'nombre': nombre} for clave, nombre in NOMBRES_ACUMULADOS.items()]
                  + [{'clave': 'nunca', 'nombre': 'Nunca vendidos'}, {'clave': 'nuevo', 'nombre': 'Llegaron hace poco'},
                     {'clave': 'abierto', 'nombre': 'Con pedido abierto'},
                     {'clave': 'ancla', 'nombre': 'Ancla (los que más venden)'}])
        if filas is not None:
            for vista in vistas:
                vista['productos'] = sum(1 for fila in filas if self._de_la_vista(fila, vista['clave']))
        return vistas

    @api.model
    def _como_se_cuenta(self):
        return {
            'ventas': self.env._('Facturas de cliente publicadas (las notas de crédito restan), igual que el Inicio.'),
            'dias': self.env._('Días desde la última factura del producto. Menos de 30, 30 a 59, 60 a 89, 90 a 179 y '
                               '180 o más.'),
            'nuevo': self.env._('Llegó de un proveedor hace menos de 30 días y todavía no se vende: no se le exige '
                                'rotación.'),
            'abierto': self.env._('Tiene un pedido confirmado que falta facturar: esa mercancía ya tiene dueño.'),
            'ancla': self.env._('Los productos que juntos hacen el 80 % de las unidades vendidas en 90 días.'),
            'cobertura': self.env._('Días que alcanza lo que hay al ritmo de los últimos 90 días.'),
        }

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    @api.model
    def _excel(self, vista=None, categoria=None, texto='', orden=None, rebaja=None):
        """``(nombre, contenido)``: la hoja «Rotación» (todos los productos de la vista, sin el tope de la pantalla) y
        «Resumen» (las tarjetas por grupo). Los nombres no pueden salir como fórmulas (``strings_to_formulas``)."""
        import xlsxwriter  # noqa: PLC0415 (como el exportar de Odoo: solo se carga al usarlo)

        self._exigir()
        vista, texto, orden, rebaja = self._validar(vista, categoria, texto, orden, rebaja)
        hoy, con_dinero, todas, elegidas = self._seleccion(vista, categoria, texto, orden)
        total_capital = sum(f['costo'] for f in todas if f['grupo'] is not None) if con_dinero else 0.0
        if len(elegidas) > FILAS_MAXIMAS:
            raise UserError(self.env._('Son demasiados productos para un solo Excel. Filtra por categoría.'))
        salida = io.BytesIO()
        libro = xlsxwriter.Workbook(salida, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
        formatos = {
            'titulo': libro.add_format({'bold': True, 'font_size': 14, 'font_color': '#1340B1'}),
            'nota': libro.add_format({'italic': True, 'font_color': '#44506A'}),
            'cabeza': libro.add_format({'bold': True, 'bg_color': '#1340B1', 'font_color': '#FFFFFF',
                                        'text_wrap': True, 'valign': 'vcenter', 'border': 1}),
            'entero': libro.add_format({'num_format': '#,##0'}),
            'decimal': libro.add_format({'num_format': '#,##0.0#'}),
            'dinero': libro.add_format({'num_format': '#,##0.00'}),
            'peligro': libro.add_format({'bold': True, 'font_color': '#B42318'}),
            'total': libro.add_format({'bold': True, 'num_format': '#,##0.00', 'top': 1}),
        }
        nombre_de_vista = next((v['nombre'] for v in self._vistas() if v['clave'] == vista), vista)
        encabezado = [
            (self.env._('Rotación del inventario · %(vista)s', vista=nombre_de_vista), formatos['titulo']),
            (self.env._('Al %(dia)s · ventas = facturas de cliente publicadas (las notas de crédito restan) · '
                        'días sin vender = desde la última factura.', dia=hoy.strftime('%d/%m/%Y')), formatos['nota']),
            (self.env._('Ancla = los productos que juntos hacen el 80 % de las unidades de 90 días. Cobertura = días '
                        'que alcanza lo que hay al ritmo de los últimos 90 días.'), formatos['nota']),
        ]
        self._hoja_rotacion(libro.add_worksheet(self.env._('Rotación')), formatos, encabezado, elegidas, con_dinero,
                            rebaja, hoy)
        self._hoja_resumen(libro.add_worksheet(self.env._('Resumen')), formatos, self._tarjetas(todas, con_dinero,
                                                                                               total_capital),
                           con_dinero)
        libro.close()
        sufijo = re.sub(r'[^a-z0-9_]+', '-', vista.lower()).strip('-')
        return f'rotacion_{sufijo}_{hoy.isoformat()}.xlsx', salida.getvalue()

    def _hoja_rotacion(self, hoja, formatos, encabezado, filas, con_dinero, rebaja, hoy):
        for numero, (texto, formato) in enumerate(encabezado):
            hoja.write(numero, 0, texto, formato)
        columnas = [(self.env._('Producto'), 40), (self.env._('Referencia'), 14), (self.env._('Categoría'), 22),
                    (self.env._('Grupo'), 18), (self.env._('Ancla'), 7), (self.env._('Existencias'), 11),
                    (self.env._('Última venta'), 12), (self.env._('Días sin vender'), 11),
                    (self.env._('Vendidas 30 días'), 10), (self.env._('Vendidas 60 días'), 10),
                    (self.env._('Vendidas 90 días'), 10), (self.env._('Facturas en 90 días'), 10),
                    (self.env._('Alcanza para (días)'), 11), (self.env._('Pedido abierto'), 10)]
        if con_dinero:
            columnas += [(self.env._('Costo unitario'), 11), (self.env._('Capital parado'), 12),
                         (self.env._('Precio sin ITBMS'), 12), (self.env._('Margen %'), 9)]
            if rebaja:
                columnas += [(self.env._('Precio con %(r)s %% de descuento', r=f'{rebaja:g}'), 14),
                             (self.env._('Margen con descuento %'), 12)]
        cabecera = len(encabezado) + 1
        for columna, (nombre, ancho) in enumerate(columnas):
            hoja.write(cabecera, columna, nombre, formatos['cabeza'])
            hoja.set_column(columna, columna, ancho)
        hoja.set_row(cabecera, 44)
        for numero, fila in enumerate(filas, start=cabecera + 1):
            self._escribir_fila(hoja, numero, fila, formatos, con_dinero, rebaja)
        if filas:
            hoja.autofilter(cabecera, 0, cabecera + len(filas), len(columnas) - 1)
        else:
            hoja.write(cabecera + 1, 0, self.env._('No hay productos con eso.'), formatos['nota'])
        hoja.freeze_panes(cabecera + 1, 1)

    def _escribir_fila(self, hoja, numero, fila, formatos, con_dinero, rebaja):
        plantilla = fila['plantilla']
        nombres = {clave: nombre for clave, nombre, _frase in GRUPOS}
        hoja.write(numero, 0, plantilla.name or '')
        hoja.write(numero, 1, plantilla.default_code or '')
        hoja.write(numero, 2, plantilla.categ_id.name or '')
        hoja.write(numero, 3, nombres.get(fila['grupo'], self.env._('Agotado')))
        hoja.write(numero, 4, self.env._('Sí') if fila['ancla'] else '')
        hoja.write_number(numero, 5, fila['stock'], formatos['entero'])
        hoja.write(numero, 6, fila['ultima'].strftime('%d/%m/%Y') if fila['ultima'] else self.env._('Nunca'))
        self._numero_o_raya(hoja, numero, 7, fila['dias'], formatos['entero'])
        for columna, clave in enumerate(('u30', 'u60', 'u90'), start=8):
            hoja.write_number(numero, columna, fila[clave], formatos['decimal'])
        hoja.write_number(numero, 11, fila['v90'], formatos['entero'])
        self._numero_o_raya(hoja, numero, 12, fila['cobertura'], formatos['entero'])
        hoja.write_number(numero, 13, fila['abierto'], formatos['decimal'])
        if con_dinero:
            self._dinero_en_la_fila(hoja, numero, fila, formatos, rebaja)

    @staticmethod
    def _numero_o_raya(hoja, fila, columna, valor, formato):
        if valor is None:
            hoja.write(fila, columna, '—')
        else:
            hoja.write_number(fila, columna, valor, formato)

    def _dinero_en_la_fila(self, hoja, numero, fila, formatos, rebaja):
        unidades = fila['unidades_valoradas']
        costo_unitario = fila['costo'] / unidades if unidades and fila['costo'] > 0 else None
        precio = fila['venta_total'] / unidades if unidades and fila['venta_total'] > 0 else None
        for columna, valor, formato in ((14, costo_unitario, 'dinero'), (15, fila['costo'], 'dinero'),
                                        (16, precio, 'dinero'), (17, self._margen(fila), 'decimal')):
            self._numero_o_raya(hoja, numero, columna, valor, formatos[formato])
        if rebaja:
            if precio is None:
                hoja.write(numero, 18, '—')
                hoja.write(numero, 19, '—')
                return
            con_rebaja = precio * (1 - rebaja / 100)
            hoja.write_number(numero, 18, con_rebaja, formatos['dinero'])
            if costo_unitario and con_rebaja > 0:
                margen = (con_rebaja - costo_unitario) / con_rebaja * 100
                hoja.write_number(numero, 19, margen, formatos['peligro'] if con_rebaja < costo_unitario
                                  else formatos['decimal'])
            else:
                hoja.write(numero, 19, '—')

    def _hoja_resumen(self, hoja, formatos, tarjetas, con_dinero):
        from xlsxwriter.utility import xl_col_to_name  # noqa: PLC0415

        columnas = [(self.env._('Grupo'), 34), (self.env._('Productos'), 11), (self.env._('Unidades'), 11)]
        if con_dinero:
            columnas += [(self.env._('Capital al costo'), 15), (self.env._('% del capital'), 12)]
        for columna, (nombre, ancho) in enumerate(columnas):
            hoja.write(0, columna, nombre, formatos['cabeza'])
            hoja.set_column(columna, columna, ancho)
        hoja.set_row(0, 32)
        for numero, tarjeta in enumerate(tarjetas, start=1):
            hoja.write(numero, 0, tarjeta['frase'])
            hoja.write_number(numero, 1, tarjeta['productos'], formatos['entero'])
            hoja.write_number(numero, 2, tarjeta['unidades'], formatos['decimal'])
            if con_dinero:
                hoja.write_number(numero, 3, tarjeta['capital'], formatos['dinero'])
                if tarjeta['parte'] is None:
                    hoja.write(numero, 4, '—')
                else:
                    hoja.write_number(numero, 4, tarjeta['parte'], formatos['decimal'])
        ultima = len(tarjetas) + 1
        hoja.write(ultima, 0, self.env._('Total'), formatos['total'])
        for indice, columna in enumerate(range(1, len(columnas) if not con_dinero else 4)):
            letra = xl_col_to_name(columna)
            total = sum(t[('productos', 'unidades', 'capital')[indice]] for t in tarjetas)
            hoja.write_formula(ultima, columna, f'=SUM({letra}2:{letra}{ultima})', formatos['total'], round(total, 2))
        hoja.freeze_panes(1, 1)

