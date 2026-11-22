"""«Movimiento» (pedido de la dueña, 2026-11-22): lo que más y lo que menos se mueve, **comparando dos periodos**, para
decidir qué anunciar y qué empujar en publicidad y redes.

Lo pidió así: «ver los artículos con mayor y menor movimiento y rotación de forma más precisa por tiempos y comparar
periodos, con la finalidad de poder hacer campañas de publicidad y de redes sociales de forma más práctica y fácil».

Qué cuenta cada cifra (todo sale de la base; nada se estima ni se inventa):

* **Ventas**: las facturas de cliente publicadas, la misma base de Marketing y Rotación (sin servicios ni anticipos;
  las notas de crédito restan unidades y dinero). Un día de venta es la fecha de la factura. Un periodo son días
  corridos, ambos extremos incluidos (hora de Panamá).
* **Dos periodos**: «este» (el que se mira) y «el de comparación», del mismo largo y justo antes (por defecto), el mismo
  tramo del año pasado, o dos rangos de fechas escritos a mano. Si no hubo ventas en el de comparación, la pantalla lo
  dice (sin eso, todo parecería «nuevo»).
* **Pedidos**: en cuántas facturas salió el producto (el flujo de pedidos: un producto que sale en muchas facturas se
  mueve más que otro que salió en una sola con muchas unidades). Un producto con más de un color o medida que sale en la
  misma factura cuenta una vez por cada variante.
* **Estado de cada producto** (uno solo): *subió* (más unidades que en el periodo de comparación), *despertó* (no se
  vendía y ahora sí), *igual*, *bajó* (se vende, pero menos), *se enfrió* (se vendía y ahora no) y *quieto* (con
  existencias y sin ventas en ninguno de los dos periodos). Un producto sin ventas y sin existencias no sale.
* **Alcanza para**: días que alcanza lo que hay al ritmo de este periodo (existencias ÷ unidades vendidas por día).
* **Ancla y días sin vender**: los de «Rotación» (``dcasa.rotacion``), para unir las dos pantallas.

El modelo se llama ``dcasa.movimiento_productos`` porque ``dcasa.movimiento`` ya es el libro de puntos de Socios
(``dcasa_socios``): dos modelos con el mismo nombre se mezclan y rompen la carga.

Quién entra: Gerencia, administradores y el rol Marketing (``dcasa.marketing._exigir``); el servidor lo exige. El
dinero (lo vendido en $ y el capital parado) es solo de Gerencia y administradores (``_ve_utilidad``). El Excel lo arma
el servidor (``controllers/movimiento.py``) con las mismas cifras.
"""
import io
import re
from collections import defaultdict
from datetime import date, timedelta

from babel.dates import format_date

from odoo import api, fields, models
from odoo.exceptions import UserError

# (clave, nombre del botón, días corridos). Los meses son especiales (ver ``_periodo``).
PERIODOS = (
    ('7', 'Últimos 7 días', 7), ('15', 'Últimos 15 días', 15), ('30', 'Últimos 30 días', 30),
    ('60', 'Últimos 60 días', 60), ('90', 'Últimos 90 días', 90),
    ('este_mes', 'Este mes', None), ('mes_pasado', 'Mes pasado', None),
)
CLAVES_DE_PERIODO = tuple(p[0] for p in PERIODOS) + ('fechas',)
# Contra qué se compara: el tramo de justo antes (mismo largo), el mismo tramo del año pasado o fechas a mano.
CONTRAS = (
    ('anterior', 'El periodo de justo antes'), ('anio', 'El mismo periodo del año pasado'),
    ('fechas', 'Elegir fechas'),
)
CLAVES_DE_CONTRA = tuple(c[0] for c in CONTRAS)
DIAS_MAXIMOS = 366
PERIODO_POR_DEFECTO = '30'
FILAS = 100
FILAS_MAXIMAS = 100000
TOPE_DE_IDS = 2000
# Cuántos días caben en el gráfico día por día; pasado eso, se junta por semanas.
DIAS_DEL_GRAFICO_POR_DIA = 31

# Los estados (uno por producto) y cómo se dicen.
ESTADOS = (
    ('subio', 'Subió'), ('desperto', 'Despertó'), ('igual', 'Igual'), ('bajo', 'Bajó'),
    ('enfrio', 'Se enfrió'), ('quieto', 'Quieto'),
)
NOMBRES_DE_ESTADO = dict(ESTADOS)
# Lo que se puede elegir ver (cada una es un conjunto de estados).
VISTAS = (
    ('venden', 'Los que más venden', ('subio', 'desperto', 'igual', 'bajo')),
    ('subieron', 'Los que más subieron', ('subio', 'desperto')),
    ('bajaron', 'Los que bajaron', ('bajo',)),
    ('enfriaron', 'Se enfriaron', ('enfrio',)),
    ('quietos', 'Quietos con existencias', ('quieto',)),
    ('todos', 'Todos', tuple(clave for clave, _nombre in ESTADOS)),
)
CLAVES_DE_VISTA = tuple(v[0] for v in VISTAS)
ESTADOS_DE_VISTA = {clave: estados for clave, _nombre, estados in VISTAS}
# Cómo se ordena cada vista si la persona no elige otra cosa.
ORDEN_POR_VISTA = {'venden': 'ventas', 'subieron': 'cambio', 'bajaron': 'baja', 'enfriaron': 'antes',
                   'quietos': 'dias', 'todos': 'ventas'}
ORDENES = ('ventas', 'cambio', 'baja', 'antes', 'dias', 'cobertura', 'capital', 'nombre')


class DcasaMovimiento(models.AbstractModel):
    _name = 'dcasa.movimiento_productos'
    _description = "Movimiento de productos de D'CASA: lo que más y lo que menos se mueve, comparando dos periodos"

    # ------------------------------------------------------------------
    # Permisos y entradas
    # ------------------------------------------------------------------

    @api.model
    def _exigir(self):
        self.env['dcasa.marketing']._exigir()

    @api.model
    def _con_dinero(self):
        """Lo vendido en $ y el capital parado: solo Gerencia y administradores."""
        return self.env['dcasa.tablero']._ve_utilidad()

    @api.model
    def datos(self, periodo=None, contra=None, desde=None, hasta=None, contra_desde=None, contra_hasta=None,
              vista=None, categoria=None, texto='', orden=None):
        """La pantalla: los dos periodos, el resumen, el gráfico, los botones de qué ver y la lista."""
        self._exigir()
        return self._datos(periodo, contra, desde, hasta, contra_desde, contra_hasta, vista, categoria, texto, orden)

    @api.model
    def _fecha(self, valor, que):
        if isinstance(valor, date):
            return valor
        if not isinstance(valor, str) or not valor.strip():
            raise UserError(self.env._('Escribe la fecha %s.', que))
        try:
            return fields.Date.to_date(valor.strip())
        except (ValueError, TypeError) as error:
            raise UserError(self.env._('La fecha %s no es válida. Elígela del calendario.', que)) from error

    @api.model
    def _validar(self, periodo, contra, vista, orden, texto):
        periodo = periodo or PERIODO_POR_DEFECTO
        if periodo not in CLAVES_DE_PERIODO:
            raise UserError(self.env._('Elige uno de los periodos de la lista.'))
        contra = contra or 'anterior'
        if contra not in CLAVES_DE_CONTRA:
            raise UserError(self.env._('Elige contra qué comparar: el periodo de antes, el año pasado o fechas.'))
        vista = vista or 'venden'
        if vista not in CLAVES_DE_VISTA:
            raise UserError(self.env._('Elige qué productos ver de la lista.'))
        if orden in (None, False, ''):
            orden = None
        elif orden not in ORDENES:
            raise UserError(self.env._('Elige cómo ordenar la lista.'))
        if texto is not None and not isinstance(texto, str):
            raise UserError(self.env._('Escribe el nombre o el código del producto.'))
        if not self._con_dinero() and orden == 'capital':
            orden = None
        return periodo, contra, vista, orden, (texto or '').strip()[:100]

    # ------------------------------------------------------------------
    # Los dos periodos
    # ------------------------------------------------------------------

    @staticmethod
    def _mes(hoy, atras=0):
        """``(primer día, último día)`` del mes de ``hoy`` o de ``atras`` meses antes."""
        indice = hoy.year * 12 + hoy.month - 1 - atras
        primero = date(indice // 12, indice % 12 + 1, 1)
        siguiente = date((indice + 1) // 12, (indice + 1) % 12 + 1, 1)
        return primero, siguiente - timedelta(days=1)

    @staticmethod
    def _hace_un_anio(dia):
        try:
            return dia.replace(year=dia.year - 1)
        except ValueError:      # 29 de febrero
            return dia.replace(year=dia.year - 1, day=28)

    @api.model
    def _dia_texto(self, dia, hoy, siempre_anio=False):
        formato = 'd MMM yyyy' if (siempre_anio or dia.year != hoy.year) else 'd MMM'
        return format_date(dia, formato, locale='es')

    @api.model
    def _tramo(self, desde, hasta, hoy, siempre_anio=False):
        dias = (hasta - desde).days + 1
        return {
            'desde': desde, 'hasta': hasta, 'dias': dias,
            'etiqueta': self.env._('del %(desde)s al %(hasta)s', desde=self._dia_texto(desde, hoy, siempre_anio),
                                   hasta=self._dia_texto(hasta, hoy, siempre_anio)),
        }

    @api.model
    def _periodos(self, periodo, contra, desde, hasta, contra_desde, contra_hasta, hoy):
        """``(este, el de comparación)``: dos tramos de días ``{'desde', 'hasta', 'dias', 'etiqueta'}``."""
        if periodo == 'fechas':
            d0, d1 = self._fecha(desde, self.env._('«desde»')), self._fecha(hasta, self.env._('«hasta»'))
        elif periodo == 'este_mes':
            d0, d1 = self._mes(hoy)[0], hoy
        elif periodo == 'mes_pasado':
            d0, d1 = self._mes(hoy, 1)
        else:
            dias = next(p[2] for p in PERIODOS if p[0] == periodo)
            d0, d1 = hoy - timedelta(days=dias - 1), hoy
        self._revisar_tramo(d0, d1, hoy, self.env._('El periodo'))
        largo = (d1 - d0).days + 1
        if contra == 'fechas':
            c0 = self._fecha(contra_desde, self.env._('«desde» de la comparación'))
            c1 = self._fecha(contra_hasta, self.env._('«hasta» de la comparación'))
            self._revisar_tramo(c0, c1, hoy, self.env._('El periodo de comparación'))
            if c0 <= d1 and d0 <= c1:
                raise UserError(self.env._('Los dos periodos no pueden cruzarse: elige fechas distintas.'))
        elif contra == 'anio':
            c0, c1 = self._hace_un_anio(d0), self._hace_un_anio(d1)
        elif periodo == 'este_mes':
            # El mismo tramo del mes pasado (si el mes pasado fue más corto, hasta su último día).
            primero, ultimo = self._mes(hoy, 1)
            c0, c1 = primero, min(primero + timedelta(days=largo - 1), ultimo)
        elif periodo == 'mes_pasado':
            c0, c1 = self._mes(hoy, 2)
        else:
            c0, c1 = d0 - timedelta(days=largo), d0 - timedelta(days=1)
        siempre_anio = contra == 'anio'
        return self._tramo(d0, d1, hoy, siempre_anio), self._tramo(c0, c1, hoy, siempre_anio)

    @api.model
    def _revisar_tramo(self, d0, d1, hoy, nombre):
        if d0 > d1:
            raise UserError(self.env._('%s empieza después de terminar: cambia las fechas.', nombre))
        if d1 > hoy:
            raise UserError(self.env._('%s no puede pasar de hoy.', nombre))
        if (d1 - d0).days + 1 > DIAS_MAXIMOS:
            raise UserError(self.env._('%(nombre)s no puede pasar de %(dias)s días.', nombre=nombre,
                                       dias=DIAS_MAXIMOS))

    # ------------------------------------------------------------------
    # Las ventas de cada tramo
    # ------------------------------------------------------------------

    @api.model
    def _dominio_de_lineas(self, desde, hasta):
        return [('parent_state', '=', 'posted'), ('display_type', '=', 'product'), ('product_id', '!=', False),
                ('product_id.type', '!=', 'service'), ('is_downpayment', '=', False),
                ('company_id', 'in', self.env.companies.ids), ('date', '>=', desde), ('date', '<=', hasta)]

    @api.model
    def _ventas(self, desde, hasta):
        """``{plantilla: {'u': unidades netas, 'pedidos': facturas, 'monto': ventas sin ITBMS}}`` del tramo (las notas
        de crédito restan unidades y dinero)."""
        Linea = self.env['account.move.line'].sudo()
        ventas = defaultdict(lambda: {'u': 0.0, 'pedidos': 0, 'monto': 0.0})
        base = self._dominio_de_lineas(desde, hasta)
        for tipo, signo in (('out_invoice', 1), ('out_refund', -1)):
            for producto, unidades, facturas, balance in Linea._read_group(
                    base + [('move_id.move_type', '=', tipo)], ['product_id'],
                    ['quantity:sum', 'move_id:count_distinct', 'balance:sum']):
                fila = ventas[producto.product_tmpl_id.id]
                fila['u'] += signo * unidades
                fila['monto'] -= balance        # la factura guarda las ventas en negativo (crédito) y la nota al revés
                if signo > 0:
                    fila['pedidos'] += facturas
        return ventas

    @api.model
    def _facturas_del_tramo(self, desde, hasta, filtro_de_lineas):
        """Cuántas facturas distintas hubo en el tramo (con productos de la categoría, si se eligió una)."""
        resultado = self.env['account.move.line'].sudo()._read_group(
            self._dominio_de_lineas(desde, hasta) + filtro_de_lineas + [('move_id.move_type', '=', 'out_invoice')],
            [], ['move_id:count_distinct'])
        return resultado[0][0] if resultado else 0

    @staticmethod
    def _filtro_de_lineas(filtro):
        """El filtro de categoría de ``product.template`` dicho para las líneas de factura."""
        return [('product_id.' + campo, operador, valor) for campo, operador, valor in filtro]

    @api.model
    def _serie(self, tramo, filtro_de_lineas, por_semana):
        """Unidades netas del tramo, día por día o semana por semana: una lista del largo del tramo."""
        Linea = self.env['account.move.line'].sudo()
        base = self._dominio_de_lineas(tramo['desde'], tramo['hasta']) + filtro_de_lineas
        pasos = -(-tramo['dias'] // 7) if por_semana else tramo['dias']
        serie = [0.0] * pasos
        for tipo, signo in (('out_invoice', 1), ('out_refund', -1)):
            for dia, unidades in Linea._read_group(base + [('move_id.move_type', '=', tipo)], ['date:day'],
                                                   ['quantity:sum']):
                if not dia:
                    continue
                indice = (dia - tramo['desde']).days
                serie[indice // 7 if por_semana else indice] += signo * unidades
        return [round(valor, 2) for valor in serie]

    @api.model
    def _grafico(self, este, otro, filtro_de_lineas):
        por_semana = max(este['dias'], otro['dias']) > DIAS_DEL_GRAFICO_POR_DIA
        a = self._serie(este, filtro_de_lineas, por_semana)
        b = self._serie(otro, filtro_de_lineas, por_semana)
        largo = max(len(a), len(b))
        a += [None] * (largo - len(a))      # el más corto no tiene esos días: no se dibuja
        b += [None] * (largo - len(b))
        paso = timedelta(days=7 if por_semana else 1)
        etiquetas = [fields.Date.to_string(este['desde'] + paso * i) for i in range(largo)]
        etiquetas_b = [fields.Date.to_string(otro['desde'] + paso * i) for i in range(largo)]
        return {'por': 'semana' if por_semana else 'dia', 'este': a, 'otro': b,
                'fechas_este': etiquetas, 'fechas_otro': etiquetas_b}

    # ------------------------------------------------------------------
    # Una fila por producto
    # ------------------------------------------------------------------

    @staticmethod
    def _estado(ua, ub, stock):
        """Uno solo por producto (ver el docstring del módulo); ``None`` si no se vendió y no hay existencias."""
        ua, ub = max(ua, 0.0), max(ub, 0.0)
        if ua > 0:
            if ub <= 0:
                return 'desperto'
            return 'subio' if ua > ub else ('bajo' if ua < ub else 'igual')
        if ub > 0:
            return 'enfrio'
        return 'quieto' if (stock or 0) > 0 else None

    @api.model
    def _calcular(self, este, otro, plantillas):
        """Una fila por producto de ``plantillas`` con lo vendido en cada tramo, su estado y lo de «Rotación»."""
        _hoy, _con_dinero_de_rotacion, rotacion = self.env['dcasa.rotacion']._calcular()
        con_dinero = self._con_dinero()      # el dinero lo decide esta pantalla, no la de Rotación
        ventas_a, ventas_b = self._ventas(este['desde'], este['hasta']), self._ventas(otro['desde'], otro['hasta'])
        vacio = {'u': 0.0, 'pedidos': 0, 'monto': 0.0}
        filas = []
        for plantilla in plantillas:
            a, b = ventas_a.get(plantilla.id, vacio), ventas_b.get(plantilla.id, vacio)
            rot = rotacion.get(plantilla.id) or {}
            stock = plantilla.dcasa_stock if plantilla.is_storable else None
            ua, ub = a['u'], b['u']
            estado = self._estado(ua, ub, stock)
            if estado is None:
                continue
            fila = {
                'plantilla': plantilla, 'stock': stock, 'estado': estado,
                'ua': ua, 'ub': ub, 'pa': a['pedidos'], 'pb': b['pedidos'],
                'delta': ua - ub, 'pct': round((ua - ub) / ub * 100, 1) if ub > 0 else None,
                'cobertura': round(stock / (ua / este['dias'])) if ua > 0 and stock and stock > 0 else None,
                'ultima': rot.get('ultima'), 'dias': rot.get('dias'), 'grupo': rot.get('grupo'),
                'ancla': bool(rot.get('ancla')),
            }
            if con_dinero:
                fila.update(va=a['monto'], vb=b['monto'], costo=rot.get('costo', 0.0))
            filas.append(fila)
        return con_dinero, filas

    # ------------------------------------------------------------------
    # Lo que ve la pantalla
    # ------------------------------------------------------------------

    @api.model
    def _ordenar(self, filas, orden, con_dinero):
        def nombre(fila):
            return (fila['plantilla'].name or '').lower(), fila['plantilla'].id
        if orden == 'cambio':
            return sorted(filas, key=lambda f: (-f['delta'], nombre(f)))
        if orden == 'baja':
            return sorted(filas, key=lambda f: (f['delta'], nombre(f)))
        if orden == 'antes':
            return sorted(filas, key=lambda f: (-f['ub'], nombre(f)))
        if orden == 'dias':
            # Primero los que nunca se vendieron y luego los de última venta más vieja; a igualdad, el de más stock.
            return sorted(filas, key=lambda f: (f['dias'] is not None, -(f['dias'] or 0), -(f['stock'] or 0),
                                                nombre(f)))
        if orden == 'cobertura':
            return sorted(filas, key=lambda f: (f['cobertura'] is None, f['cobertura'] or 0, nombre(f)))
        if orden == 'capital' and con_dinero:
            return sorted(filas, key=lambda f: (-f['costo'], -(f['stock'] or 0), nombre(f)))
        if orden == 'nombre':
            return sorted(filas, key=nombre)
        return sorted(filas, key=lambda f: (-f['ua'], -f['delta'], nombre(f)))

    @api.model
    def _de_la_vista(self, fila, vista):
        return fila['estado'] in ESTADOS_DE_VISTA[vista]

    @api.model
    def _vistas(self, filas):
        return [{'clave': clave, 'nombre': nombre, 'productos': sum(1 for f in filas if f['estado'] in estados)}
                for clave, nombre, estados in VISTAS]

    @api.model
    def _comparacion(self, a, b):
        """``{'a', 'b', 'cambio', 'pct'}``: el cambio es a − b; el porcentaje, sobre b (sin b, ``None``)."""
        return {'a': round(a, 2), 'b': round(b, 2), 'cambio': round(a - b, 2),
                'pct': round((a - b) / b * 100, 1) if b > 0 else None}

    @api.model
    def _resumen(self, filas, este, otro, con_dinero, filtro_de_lineas):
        resumen = {
            'unidades': self._comparacion(sum(f['ua'] for f in filas), sum(f['ub'] for f in filas)),
            'pedidos': self._comparacion(self._facturas_del_tramo(este['desde'], este['hasta'], filtro_de_lineas),
                                         self._facturas_del_tramo(otro['desde'], otro['hasta'], filtro_de_lineas)),
            'productos': self._comparacion(sum(1 for f in filas if f['ua'] > 0), sum(1 for f in filas if f['ub'] > 0)),
            'sin_ventas_de_comparacion': not any(f['ub'] > 0 for f in filas),
        }
        if con_dinero:
            redondear = self.env.company.currency_id.round
            monto = self._comparacion(sum(f['va'] for f in filas), sum(f['vb'] for f in filas))
            resumen['monto'] = {k: (redondear(v) if v is not None and k != 'pct' else v) for k, v in monto.items()}
        return resumen

    @api.model
    def _fila_para_la_pantalla(self, fila, con_dinero):
        plantilla = fila['plantilla']
        datos = self.env['dcasa.marketing']._fila(
            plantilla, estado=fila['estado'], nombre_estado=NOMBRES_DE_ESTADO[fila['estado']],
            vendidas_este=round(fila['ua'], 2), vendidas_otro=round(fila['ub'], 2), cambio=round(fila['delta'], 2),
            cambio_pct=fila['pct'], pedidos_este=fila['pa'], pedidos_otro=fila['pb'],
            cobertura_dias=fila['cobertura'], ancla=fila['ancla'], grupo=fila['grupo'],
            ultima_venta=fields.Date.to_string(fila['ultima']) if fila['ultima'] else None,
            dias_sin_vender=fila['dias'])
        if con_dinero:
            redondear = self.env.company.currency_id.round
            datos.update(vendido_este=redondear(fila['va']), vendido_otro=redondear(fila['vb']),
                         capital=redondear(fila['costo']))
        return datos

    @api.model
    def _seleccion(self, periodo, contra, desde, hasta, contra_desde, contra_hasta, vista, categoria, texto, orden):
        """``(hoy, este, otro, con_dinero, de_la_categoria, elegidas, filtro_de_lineas, orden)``: las filas de la
        categoría (de ellas salen el resumen y los botones) y las de la vista, filtradas por el texto y ordenadas."""
        hoy = fields.Date.context_today(self)
        este, otro = self._periodos(periodo, contra, desde, hasta, contra_desde, contra_hasta, hoy)
        marketing = self.env['dcasa.marketing']
        _tipo, filtro = marketing._categoria_pedida(categoria)
        Plantilla = self.env['product.template']
        plantillas = Plantilla.search(marketing._dominio_base() + filtro)
        con_dinero, de_la_categoria = self._calcular(este, otro, plantillas)
        candidatas = de_la_categoria
        if texto:
            con_el_texto = set(Plantilla.search(marketing._dominio_base() + filtro
                                                + marketing._dominio_de_texto(texto)).ids)
            candidatas = [f for f in de_la_categoria if f['plantilla'].id in con_el_texto]
        orden = orden or ORDEN_POR_VISTA[vista]
        if orden == 'capital' and not con_dinero:
            orden = ORDEN_POR_VISTA[vista]
        elegidas = self._ordenar([f for f in candidatas if self._de_la_vista(f, vista)], orden, con_dinero)
        return hoy, este, otro, con_dinero, de_la_categoria, elegidas, self._filtro_de_lineas(filtro), orden

    @api.model
    def _datos(self, periodo=None, contra=None, desde=None, hasta=None, contra_desde=None, contra_hasta=None,
               vista=None, categoria=None, texto='', orden=None):
        periodo, contra, vista, orden, texto = self._validar(periodo, contra, vista, orden, texto)
        hoy, este, otro, con_dinero, todas, elegidas, filtro_de_lineas, orden = self._seleccion(
            periodo, contra, desde, hasta, contra_desde, contra_hasta, vista, categoria, texto, orden)
        moneda = self.env.company.currency_id
        marketing = self.env['dcasa.marketing']
        tipo, _filtro = marketing._categoria_pedida(categoria)

        def texto_de(tramo):
            return {'desde': fields.Date.to_string(tramo['desde']), 'hasta': fields.Date.to_string(tramo['hasta']),
                    'dias': tramo['dias'], 'etiqueta': tramo['etiqueta']}
        return {
            'hoy': fields.Date.to_string(hoy), 'con_dinero': con_dinero,
            'moneda': {'simbolo': moneda.symbol, 'antes': moneda.position == 'before'},
            'periodo': periodo, 'periodos': [{'clave': clave, 'nombre': nombre} for clave, nombre, _d in PERIODOS]
            + [{'clave': 'fechas', 'nombre': self.env._('Elegir fechas')}],
            'contra': contra, 'contras': [{'clave': clave, 'nombre': nombre} for clave, nombre in CONTRAS],
            'este': texto_de(este), 'otro': texto_de(otro),
            'categorias': marketing._lista_de_categorias(), 'categoria': tipo,
            'vista': vista, 'texto': texto, 'orden': orden,
            'vistas': self._vistas(todas),
            'resumen': self._resumen(todas, este, otro, con_dinero, filtro_de_lineas),
            'grafico': self._grafico(este, otro, filtro_de_lineas),
            'total': len(elegidas), 'mostrando': min(len(elegidas), FILAS),
            'productos': [self._fila_para_la_pantalla(f, con_dinero) for f in elegidas[:FILAS]],
            'ids': [f['plantilla'].id for f in elegidas[:TOPE_DE_IDS]],
            'como_se_cuenta': self._como_se_cuenta(),
        }

    @api.model
    def _como_se_cuenta(self):
        return {
            'ventas': self.env._('Facturas de cliente publicadas (las notas de crédito restan), como Marketing y '
                                 'Rotación. Solo productos activos y a la venta, sin servicios.'),
            'periodos': self.env._('Cada periodo son días corridos, con el primero y el último incluidos. El de '
                                   'comparación tiene el mismo largo y va justo antes (o el mismo tramo del año '
                                   'pasado, o las fechas que elijas).'),
            'pedidos': self.env._('En cuántas facturas salió el producto: muestra si se mueve seguido o si fue una '
                                  'sola venta grande.'),
            'estado': self.env._('Subió: más unidades que antes. Despertó: antes no se vendía. Bajó: se vende, pero '
                                 'menos. Se enfrió: antes se vendía y ahora no. Quieto: con existencias y sin ventas '
                                 'en ninguno de los dos periodos.'),
            'alcanza': self.env._('Días que alcanza lo que hay al ritmo de este periodo. Antes de anunciar un producto '
                                  'mira que no se agote en la campaña.'),
        }

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    @api.model
    def _excel(self, periodo=None, contra=None, desde=None, hasta=None, contra_desde=None, contra_hasta=None,
               vista=None, categoria=None, texto='', orden=None):
        """``(nombre, contenido)``: la hoja «Comparación» (todos los productos de la vista, sin el tope de la pantalla)
        y «Resumen». Los nombres no pueden salir como fórmulas (``strings_to_formulas``)."""
        import xlsxwriter  # noqa: PLC0415 (como el exportar de Odoo: solo se carga al usarlo)

        self._exigir()
        periodo, contra, vista, orden, texto = self._validar(periodo, contra, vista, orden, texto)
        hoy, este, otro, con_dinero, todas, elegidas, filtro_de_lineas, orden = self._seleccion(
            periodo, contra, desde, hasta, contra_desde, contra_hasta, vista, categoria, texto, orden)
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
            'cambio': libro.add_format({'num_format': '+#,##0.0#;-#,##0.0#;0'}),
            'dinero': libro.add_format({'num_format': '#,##0.00'}),
            'total': libro.add_format({'bold': True, 'num_format': '#,##0.00', 'top': 1}),
        }
        nombre_de_vista = next(v[1] for v in VISTAS if v[0] == vista)
        encabezado = [
            (self.env._('Movimiento de productos · %(vista)s', vista=nombre_de_vista), formatos['titulo']),
            (self.env._('Este periodo: %(este)s (%(n)s días) · Comparado con: %(otro)s (%(m)s días)',
                        este=este['etiqueta'], n=este['dias'], otro=otro['etiqueta'], m=otro['dias']),
             formatos['nota']),
            (self.env._('Ventas = facturas de cliente publicadas (las notas de crédito restan). Pedidos = en cuántas '
                        'facturas salió el producto. Al %(dia)s.', dia=hoy.strftime('%d/%m/%Y')), formatos['nota']),
        ]
        self._hoja_comparacion(libro.add_worksheet(self.env._('Comparación')), formatos, encabezado, elegidas,
                               con_dinero, este['dias'])
        self._hoja_resumen(libro.add_worksheet(self.env._('Resumen')), formatos,
                           self._resumen(todas, este, otro, con_dinero, filtro_de_lineas), este, otro, con_dinero)
        libro.close()
        sufijo = re.sub(r'[^a-z0-9_]+', '-', vista.lower()).strip('-')
        return f'movimiento_{sufijo}_{este["desde"].isoformat()}_{este["hasta"].isoformat()}.xlsx', salida.getvalue()

    def _hoja_comparacion(self, hoja, formatos, encabezado, filas, con_dinero, dias_este):
        for numero, (texto, formato) in enumerate(encabezado):
            hoja.write(numero, 0, texto, formato)
        columnas = [(self.env._('Producto'), 40), (self.env._('Referencia'), 14), (self.env._('Categoría'), 22),
                    (self.env._('Estado'), 12), (self.env._('Existencias'), 11),
                    (self.env._('Vendidas este periodo'), 11), (self.env._('Vendidas en la comparación'), 12),
                    (self.env._('Cambio'), 10), (self.env._('Cambio %'), 10),
                    (self.env._('Pedidos este periodo'), 10), (self.env._('Pedidos en la comparación'), 11),
                    (self.env._('Alcanza para (días)'), 11), (self.env._('Última venta'), 12),
                    (self.env._('Días sin vender'), 11), (self.env._('Ancla'), 7)]
        if con_dinero:
            columnas += [(self.env._('Vendido este periodo'), 13), (self.env._('Vendido en la comparación'), 13),
                         (self.env._('Capital parado'), 12)]
        cabecera = len(encabezado) + 1
        for columna, (nombre, ancho) in enumerate(columnas):
            hoja.write(cabecera, columna, nombre, formatos['cabeza'])
            hoja.set_column(columna, columna, ancho)
        hoja.set_row(cabecera, 44)
        for numero, fila in enumerate(filas, start=cabecera + 1):
            self._escribir_fila(hoja, numero, fila, formatos, con_dinero)
        if filas:
            hoja.autofilter(cabecera, 0, cabecera + len(filas), len(columnas) - 1)
        else:
            hoja.write(cabecera + 1, 0, self.env._('No hay productos con eso.'), formatos['nota'])
        hoja.freeze_panes(cabecera + 1, 1)

    def _escribir_fila(self, hoja, numero, fila, formatos, con_dinero):
        plantilla = fila['plantilla']
        hoja.write(numero, 0, plantilla.name or '')
        hoja.write(numero, 1, plantilla.default_code or '')
        hoja.write(numero, 2, plantilla.categ_id.name or '')
        hoja.write(numero, 3, NOMBRES_DE_ESTADO[fila['estado']])
        self._numero_o_raya(hoja, numero, 4, fila['stock'], formatos['entero'])
        hoja.write_number(numero, 5, fila['ua'], formatos['decimal'])
        hoja.write_number(numero, 6, fila['ub'], formatos['decimal'])
        hoja.write_number(numero, 7, fila['delta'], formatos['cambio'])
        self._numero_o_raya(hoja, numero, 8, fila['pct'], formatos['cambio'])
        hoja.write_number(numero, 9, fila['pa'], formatos['entero'])
        hoja.write_number(numero, 10, fila['pb'], formatos['entero'])
        self._numero_o_raya(hoja, numero, 11, fila['cobertura'], formatos['entero'])
        hoja.write(numero, 12, fila['ultima'].strftime('%d/%m/%Y') if fila['ultima'] else self.env._('Nunca'))
        self._numero_o_raya(hoja, numero, 13, fila['dias'], formatos['entero'])
        hoja.write(numero, 14, self.env._('Sí') if fila['ancla'] else '')
        if con_dinero:
            hoja.write_number(numero, 15, fila['va'], formatos['dinero'])
            hoja.write_number(numero, 16, fila['vb'], formatos['dinero'])
            hoja.write_number(numero, 17, fila['costo'], formatos['dinero'])

    @staticmethod
    def _numero_o_raya(hoja, fila, columna, valor, formato):
        if valor is None:
            hoja.write(fila, columna, '—')
        else:
            hoja.write_number(fila, columna, valor, formato)

    def _hoja_resumen(self, hoja, formatos, resumen, este, otro, con_dinero):
        columnas = [(self.env._('Qué se cuenta'), 34), (self.env._('Este periodo'), 16),
                    (self.env._('Comparación'), 16), (self.env._('Cambio'), 12), (self.env._('Cambio %'), 12)]
        for columna, (nombre, ancho) in enumerate(columnas):
            hoja.write(0, columna, nombre, formatos['cabeza'])
            hoja.set_column(columna, columna, ancho)
        hoja.set_row(0, 32)
        lineas = [(self.env._('Unidades vendidas'), resumen['unidades'], 'decimal'),
                  (self.env._('Pedidos (facturas)'), resumen['pedidos'], 'entero'),
                  (self.env._('Productos que se vendieron'), resumen['productos'], 'entero')]
        if con_dinero:
            lineas.append((self.env._('Vendido sin ITBMS'), resumen['monto'], 'dinero'))
        for numero, (nombre, valores, formato) in enumerate(lineas, start=1):
            hoja.write(numero, 0, nombre)
            hoja.write_number(numero, 1, valores['a'], formatos[formato])
            hoja.write_number(numero, 2, valores['b'], formatos[formato])
            hoja.write_number(numero, 3, valores['cambio'], formatos[formato])
            self._numero_o_raya(hoja, numero, 4, valores['pct'], formatos['cambio'])
        final = len(lineas) + 2
        hoja.write(final, 0, self.env._('Este periodo'), formatos['nota'])
        hoja.write(final, 1, f"{este['etiqueta']} ({este['dias']} días)")
        hoja.write(final + 1, 0, self.env._('Comparación'), formatos['nota'])
        hoja.write(final + 1, 1, f"{otro['etiqueta']} ({otro['dias']} días)")
        hoja.freeze_panes(1, 1)
