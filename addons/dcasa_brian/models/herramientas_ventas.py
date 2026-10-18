"""Herramientas de ventas: reporte del día, resúmenes, la comparación del Inicio, cotizaciones y ventas."""
import re
from datetime import date

from odoo import api, models
from odoo.addons.dcasa_interfaz.models.comparar import COMPARACIONES, MESES
from odoo.addons.dcasa_interfaz.models.tablero import (
    BASE_CON_ABONOS,
    BASE_FACTURADO,
    BASE_VENDIDO,
    BASES_DE_GERENCIA,
    SIN_VENDEDORA,
)
from odoo.exceptions import UserError

from . import herramientas_comun as c
from .registro import BrianError, herramienta

VENDEDOR = ('sales_team.group_sale_salesman',)
GERENCIA = ('sales_team.group_sale_manager',)
# Las mismas palabras del interruptor del Inicio de Gerencia: cuenta sobre las facturas (decisión del jefe, 2026-10-17).
PARAM_BASE = {
    'type': 'string', 'enum': list(BASES_DE_GERENCIA),
    'description': 'Solo Gerencia: qué facturas contar. «facturado» (por defecto, como abre el Inicio): todas las '
                   'facturas publicadas, por su fecha, igual que Contabilidad (las notas de crédito restan). '
                   '«con_abonos»: con al menos un abono, por su valor total, el día de la factura (trae lo que falta '
                   'por cobrar). «completadas»: pagadas al 100 %, el día del último pago.',
}
PARAM_VENDEDORA = {
    'type': 'string',
    'description': 'Solo Gerencia: el nombre de una vendedora, o «sin vendedora» (ventas de la web o de Juan que '
                   'nadie tomó, facturas sin vendedor). Vacío: todo el equipo. Una factura es de la vendedora de su '
                   'pedido o, sin pedido, de su «Vendedor». Su cobrado es lo que se cobró de SUS facturas.',
}
SIN_VENDEDORA_TEXTOS = ('sin vendedora', 'sin vendedor', 'sin', 'nadie', 'ninguna', 'ninguno')
PARAM_VENTA = {'type': 'string', 'description': 'Número de la cotización o venta («S00012») o nombre del cliente.'}
PARAM_PRODUCTO = {'type': 'string', 'description': 'Nombre o código del producto, p. ej. «SOF-001» o «colchón queen».'}
PARAM_CANTIDAD = {'type': 'number', 'description': 'Cantidad. Por defecto 1.'}
PARAM_PRECIO = {'type': 'number',
                'description': 'Precio unitario sin ITBMS (se suma el 7 %). Si no lo das, se usa el precio de lista.'}
ESTADOS = {'cotizacion': ['draft', 'sent'], 'confirmada': ['sale'], 'cancelada': ['cancel']}


class BrianHerramientasVentas(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @api.model
    def _b_fila_venta(self, orden):
        return {
            'numero': orden.name,
            'cliente': orden.partner_id.display_name,
            'fecha': c.fecha(orden.date_order),
            'estado': self._b_estado_venta(orden),
            'total': c.moneda(orden.amount_total),
        }

    @api.model
    def _b_cotizacion_editable(self, texto):
        orden = self._b_venta(texto)
        if orden.state not in ('draft', 'sent'):
            raise BrianError(f'{orden.name} es una {self._b_estado_venta(orden)}: solo se cambian cotizaciones '
                             'que no se han confirmado.')
        return orden

    @api.model
    def _b_linea_venta(self, orden, producto, cantidad, precio):
        if cantidad is not None and cantidad <= 0:
            raise BrianError('La cantidad tiene que ser mayor que cero.')
        if precio is not None and precio < 0:
            raise BrianError('El precio no puede ser negativo.')
        if producto.type == 'combo':
            # Un combo lleva una línea por cada pieza (la cama, el colchón…) y su precio no se cambia a mano.
            if precio is not None:
                raise BrianError(f'«{producto.display_name}» es un combo: su precio no se cambia a mano. '
                                 'Si hay rebaja, se da como descuento en Ventas.')
            try:
                return orden._dcasa_agregar_producto(producto, cantidad or 1)
            except UserError as error:
                raise BrianError(f'{error} Agrégalo desde Ventas, donde se escogen las piezas.') from error
        valores = {'order_id': orden.id, 'product_id': producto.id, 'product_uom_qty': cantidad or 1}
        linea = self.env['sale.order.line'].create(valores)
        if precio is not None:
            linea.price_unit = precio
        return linea

    @api.model
    def _b_resumen_orden(self, orden):
        return {
            'numero': orden.name,
            'cliente': orden.partner_id.display_name,
            'estado': self._b_estado_venta(orden),
            'lineas': [{
                'producto': linea.product_id.display_name,
                'cantidad': c.cantidad(linea.product_uom_qty),
                'precio': c.moneda(linea.price_unit),
                'subtotal': c.moneda(linea.price_total),
            } for linea in orden.order_line.filtered(lambda ln: not ln.display_type)],
            'total': c.moneda(orden.amount_total),
            'itbms': c.moneda(orden.amount_tax),
        }

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @herramienta(
        nombre='reporte_del_dia',
        descripcion='Cómo va el día, como el tablero Inicio: vendido hoy (Gerencia: lo facturado, como '
                    'Contabilidad; sin ITBMS, con el ITBMS y el total aparte; la ganancia solo a Gerencia), cobrado '
                    'por forma de pago, cotizaciones, por cobrar, entregas y lo más vendido.',
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['¿cómo vamos hoy?', 'reporte del día', '¿cuánto se ha vendido hoy?'],
    )
    def _h_reporte_del_dia(self):
        datos = self.env['dcasa.tablero'].obtener_datos()
        cifras = []
        panel = datos['ventas'] if datos['permisos']['completo'] else None
        for cifra in datos['cifras']:
            if panel and cifra['clave'] == 'ventas_hoy':
                continue      # el Inicio de Gerencia no la muestra: cuenta con el interruptor (abajo, «ventas_de_hoy»)
            valor = c.moneda(cifra['valor']) if cifra['formato'] == 'moneda' else cifra['valor']
            fila = {'titulo': cifra['titulo'], 'valor': valor}
            if cifra.get('nota'):
                fila['nota'] = cifra['nota']
            if cifra.get('itbms') is not None:
                fila['itbms'] = c.moneda(cifra['itbms'])
                fila['total_con_itbms'] = c.moneda(cifra['total_con_itbms'])
            if cifra.get('detalle_moneda') is not None:
                fila['detalle'] = f'por {c.moneda(cifra["detalle_moneda"])} con ITBMS'
            elif cifra.get('detalle'):
                fila['detalle'] = cifra['detalle']
            cifras.append(fila)
        respuesta = {
            'fecha': c.fecha(self._b_hoy()),
            'cifras': cifras,
            'cobros_por_forma_de_pago': [{'forma': x['forma'], 'monto': c.moneda(x['monto'])} for x in datos['cobros']],
            'mas_vendidos_30_dias': [{'producto': t['nombre'], 'unidades': t['cantidad']} for t in datos['top']],
        }
        if datos['cobros']:
            respuesta['total_cobrado_con_itbms'] = c.moneda(datos['total_cobrado'])
        if panel:
            actual = panel['actual']
            respuesta['ventas_de_hoy'] = {
                'cuenta': self._b_base(panel['base']),
                'ventas': actual['cuantas'],
                'ventas_sin_itbms': c.moneda(actual['sin_itbms']),
                'itbms': c.moneda(actual['itbms']),
                'total_con_itbms': c.moneda(actual['total']),
            }
            if panel['base'] == BASE_FACTURADO:
                respuesta['ventas_de_hoy']['de_un_pedido'] = self._b_de_un_pedido(actual)
            if actual.get('notas'):
                respuesta['ventas_de_hoy']['notas_de_credito'] = actual['notas']
        ganancia = datos['ventas'] and datos['ve_utilidad'] and datos['ventas']['actual'].get('ganancia')
        if ganancia:
            respuesta['ganancia_de_hoy_sin_itbms'] = self._b_ganancia(ganancia)
        return respuesta

    @api.model
    def _b_ganancia(self, ganancia):
        """La ganancia tal como la calcula el Inicio (venta neta menos costo, sin ITBMS); lo que no tiene costo cargado
        se avisa, no se inventa."""
        fila = {'ganancia': c.moneda(ganancia['valor']),
                'porcentaje': f'{ganancia["porcentaje"]} %' if ganancia['porcentaje'] is not None else None,
                'ventas_con_costo': ganancia['ventas_con_costo']}
        if ganancia['ventas_sin_costo']:
            fila['aviso'] = (f'{ganancia["ventas_sin_costo"]} factura(s) o venta(s) con productos sin costo cargado no '
                             'cuentan en la ganancia; cargar el costo en el producto.')
        return fila

    @staticmethod
    def _b_de_un_pedido(actual):
        """«3 de 5 salieron de un pedido de una vendedora» (la línea corta de «Facturado» en el Inicio)."""
        n, m = actual['de_pedido'], actual['cuantas']
        return f'{n} de {m} ' + ('salió' if m == 1 else 'salieron') + ' de un pedido de una vendedora'

    @api.model
    def _b_base(self, base):
        """«Facturado: todas las facturas, igual que Contabilidad» (las palabras del interruptor)."""
        for opcion in self.env['dcasa.tablero']._bases_de_ventas():
            if opcion['clave'] == base:
                detalle = opcion['detalle']
                return f'{opcion["nombre"]}: {detalle[:1].lower()}{detalle[1:]}'
        return 'Pedidos facturados por completo, el día de la factura'

    @api.model
    def _b_vendedora(self, texto):
        """``None`` (todo el equipo), ``'sin'`` o el id del usuario que dice ``texto``."""
        texto = str(texto or '').strip()
        if not texto or c.normalizar_texto(texto) in ('todo el equipo', 'todas', 'todos', 'equipo'):
            return None
        if c.normalizar_texto(texto) in SIN_VENDEDORA_TEXTOS:
            return SIN_VENDEDORA
        return self._b_usuario(texto).id

    @api.model
    def _b_mes_completo(self, texto):
        """«septiembre», «septiembre 2025», «09/2026», «2026-09» → «2026-09». Sin año: el último que ya terminó."""
        texto = c.normalizar_texto(texto)
        hoy = self._b_hoy()
        if re.fullmatch(r'\d{4}-\d{1,2}', texto):
            anio, mes = (int(x) for x in texto.split('-'))
        elif re.fullmatch(r'\d{1,2}/\d{4}', texto):
            mes, anio = (int(x) for x in texto.split('/'))
        else:
            nombres = [c.normalizar_texto(m) for m in MESES]
            partes = texto.replace(' de ', ' ').split()
            numero = next((nombres.index(p) + 1 for p in partes if p in nombres), None)
            numero = numero or next((i + 1 for i, n in enumerate(nombres) for p in partes if len(p) >= 3
                                     and n.startswith(p)), None)
            if not numero:
                raise BrianError(f'No entendí el mes «{texto}». Dilo como «septiembre» o «09/2026».')
            anio = next((int(p) for p in partes if p.isdigit() and len(p) == 4), None)
            mes = numero
            if anio is None:
                anio = hoy.year if mes < hoy.month else hoy.year - 1
        if not 1 <= mes <= 12:
            raise BrianError(f'No entendí el mes «{texto}». Dilo como «septiembre» o «09/2026».')
        return date(anio, mes, 1).strftime('%Y-%m')

    @herramienta(
        nombre='resumen_ventas',
        descripcion='Ventas de un periodo: n.º, sin ITBMS (ITBMS y total aparte), ticket promedio, '
                    'unidades por tipo, por vendedora, más vendidos y (Gerencia) ganancia. Gerencia cuenta facturas '
                    '(facturado, con_abonos o completadas) y elige vendedora; quien vende, solo lo suyo.',
        parametros={'periodo': c.PARAM_PERIODO, 'desde': c.PARAM_DESDE, 'hasta': c.PARAM_HASTA,
                    'base': PARAM_BASE, 'vendedora': PARAM_VENDEDORA},
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['ventas de este mes → periodo=este_mes', 'ventas del 01/09/2026 al 15/09/2026',
                  '¿cuánto ganamos este mes? → periodo=este_mes (la ganancia solo la ve Gerencia)',
                  '¿cuánto vendió Ana este mes con abonos? → periodo=este_mes, vendedora=Ana, base=con_abonos'],
    )
    def _h_resumen_ventas(self, periodo=None, desde=None, hasta=None, base=None, vendedora=None):
        inicio, fin, etiqueta = self._b_rango(periodo, desde, hasta)
        # Las mismas cifras del Inicio (dcasa_interfaz, de la que depende este módulo) y el mismo criterio de panel:
        # quien vende sin controlar la tienda (la Vendedora) ve solo lo que ella vendió, facturado por completo, el día
        # de su última factura; Gerencia cuenta las facturas según el interruptor del Inicio («facturado» por defecto)
        # y puede pedir una vendedora (el servidor del Inicio rechaza una vendedora ajena a quien no es Gerencia).
        # Criterio contable (2026-10-16): las ventas van sin ITBMS; el ITBMS y el total se dan aparte.
        Tablero = self.env['dcasa.tablero']
        propio = Tablero._solo_lo_propio()
        filtro = Tablero._vendedor_pedido(self._b_vendedora(vendedora))
        if propio:
            base, filtro = BASE_VENDIDO, self.env.uid
        else:
            base = Tablero._base_pedida(base)
        con_ganancia = not propio and Tablero._ve_utilidad()
        totales = Tablero._medir(inicio, fin, base, filtro, con_ganancia=con_ganancia)
        por_vendedor = {}
        for clave, (_cuantas, monto) in Tablero._por_vendedora(totales).items():
            nombre = Tablero._nombre_de_vendedora(clave) if clave else 'Sin vendedora'
            por_vendedor[nombre] = por_vendedor.get(nombre, 0.0) + monto
        top = Tablero._productos_mas_vendidos(totales, 5)
        respuesta = {
            'periodo': etiqueta,
            'desde': c.fecha(inicio), 'hasta': c.fecha(fin),
            'ventas': totales['cuantas'],
            'ventas_sin_itbms': c.moneda(totales['sin_itbms']),
            'itbms': c.moneda(totales['itbms']),
            'total_con_itbms': c.moneda(totales['total']),
            # El mismo ticket del Inicio y de Comparar (``_ticket_promedio``); sin ventas, «—».
            'ticket_promedio_sin_itbms': '—' if totales['ticket'] is None else c.moneda(totales['ticket']),
            'por_vendedor_sin_itbms': [{'vendedor': n, 'total': c.moneda(m)}
                                       for n, m in sorted(por_vendedor.items(), key=lambda nm: -nm[1])[:10]],
            'productos_mas_vendidos': [
                {'producto': p.display_name, 'unidades': c.cantidad(q), 'total_sin_itbms': c.moneda(t)}
                for p, q, t in top if p],
        }
        if not propio:
            respuesta['cuenta'] = self._b_base(base)
            if base == BASE_FACTURADO:
                respuesta['de_un_pedido'] = self._b_de_un_pedido(totales)
            if totales['notas']:
                respuesta['notas_de_credito'] = totales['notas']
            # Las unidades por tipo del Inicio de Gerencia (K1): de las mismas facturas, «Otros» pasados 8 tipos.
            unidades = Tablero._unidades_por_tipo(totales['filas'])
            respuesta['unidades_por_tipo'] = [{'tipo': fila['tipo'], 'unidades': c.cantidad(fila['unidades'])}
                                              for fila in unidades['tipos']]
            respuesta['unidades_total'] = c.cantidad(unidades['total'])
            if filtro:
                respuesta['vendedora'] = ('Sin vendedora' if filtro == SIN_VENDEDORA
                                          else self.env['res.users'].sudo().browse(filtro).name)
        if base == BASE_CON_ABONOS:
            respuesta['falta_por_cobrar_con_itbms'] = c.moneda(totales['falta_por_cobrar'])
        if con_ganancia:
            respuesta['ganancia_sin_itbms'] = self._b_ganancia(totales['ganancia'])
        return respuesta

    @staticmethod
    def _b_cambio(cambio):
        """«▲ 27.6 %», «▼ 5.4 pts», «▲ 1», «llevas 58.3 %»; sin base positiva, «—»."""
        if not cambio or cambio['valor'] is None:
            return '—'
        if cambio['tipo'] == 'llevas':
            return f'llevas {cambio["valor"]:,.1f} %'
        flecha = {'sube': '▲ ', 'baja': '▼ '}.get(cambio['sentido'], '')
        valor = abs(cambio['valor'])
        if cambio['tipo'] == 'num':
            return f'{flecha}{valor:,.0f}'
        return f'{flecha}{valor:,.1f}' + (' pts' if cambio['tipo'] == 'pts' else ' %')

    @staticmethod
    def _b_fechas(texto, nombre):
        """«01/10/2026-07/10/2026», «del 01/10/2026 al 07/10/2026» o una sola fecha → [fechas] (1 o 2)."""
        encontradas = re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{1,2}-\d{1,2}', str(texto or ''))
        if not 1 <= len(encontradas) <= 2:
            raise BrianError(f'No entendí las fechas de {nombre} «{texto}». Escríbelas como «01/10/2026-07/10/2026».')
        return [c.leer_fecha(fecha, f'fecha de {nombre}') for fecha in encontradas]

    @herramienta(
        nombre='comparar_ventas',
        descripcion='Compara ventas como «Comparar» del Inicio de Gerencia (mismas cifras): ventas, ganancia, margen, '
                    'n.º de ventas, ticket promedio, cobrado y, con abonos, falta por cobrar. Si A termina hoy, hoy '
                    'va hasta la hora actual y el otro día hasta la misma hora.',
        parametros={
            'comparacion': {
                'type': 'string', 'enum': list(COMPARACIONES),
                'description': '«ayer»: hoy contra ayer. «dia_mes_pasado»: hoy contra el mismo día del mes pasado. '
                               '«semana_pasada»: hoy contra el mismo día de la semana pasada. «mes_a_la_fecha»: del 1 '
                               'a hoy contra los mismos días del mes pasado. «mes»: lo que va del mes contra un mes '
                               'completo (en «b»). «rango»: las fechas de «a» contra las de «b».'},
            'a': {'type': 'string',
                  'description': 'Solo con «rango»: las fechas de A, p. ej. «01/10/2026-07/10/2026».'},
            'b': {'type': 'string',
                  'description': 'Con «rango»: dónde empieza B («01/09/2026»: dura lo mismo que A) o B entero si es de '
                                 'otro largo («01/09/2026-30/09/2026»: el % va por día). Con «mes»: el mes completo, '
                                 'p. ej. «septiembre» o «09/2026» (por defecto, el mes pasado).'},
            'base': PARAM_BASE,
            'vendedora': {**PARAM_VENDEDORA,
                          'description': PARAM_VENDEDORA['description'] + ' «por vendedora»: agrega una fila por '
                                                                          'cada una (ventas A, B y el cambio).'},
        },
        requeridos=['comparacion'],
        nivel='lectura', categoria='ventas', grupos=GERENCIA,
        ejemplos=['¿cómo vamos contra septiembre? → comparacion=mes, b=septiembre',
                  '¿cómo vamos hoy contra ayer? → comparacion=ayer',
                  '¿cómo va el mes contra el mes pasado? → comparacion=mes_a_la_fecha',
                  '¿cómo va Ana este mes? → comparacion=mes_a_la_fecha, vendedora=Ana',
                  '¿quién vendió más este mes? → comparacion=mes_a_la_fecha, vendedora=por vendedora',
                  'del 1 al 7 de octubre contra el 1 al 7 de septiembre → comparacion=rango, '
                  'a=01/10/2026-07/10/2026, b=01/09/2026'],
    )
    def _h_comparar_ventas(self, comparacion, a=None, b=None, base=None, vendedora=None):
        argumentos = {}
        if comparacion == 'mes' and b:
            argumentos['mes'] = self._b_mes_completo(b)
        if comparacion == 'rango':
            if not a or not b:
                raise BrianError('Con «rango» dime las fechas de A («a») y dónde empieza B («b»).')
            fechas_a, fechas_b = self._b_fechas(a, 'A'), self._b_fechas(b, 'B')
            if len(fechas_a) != 2:
                raise BrianError('A necesita dos fechas, p. ej. «01/10/2026-07/10/2026».')
            argumentos.update(a_desde=str(fechas_a[0]), a_hasta=str(fechas_a[1]), b_desde=str(fechas_b[0]),
                              b_hasta=str(fechas_b[1]) if len(fechas_b) == 2 else None, libre=len(fechas_b) == 2)
        por_vendedora = c.normalizar_texto(vendedora or '') in ('por vendedora', 'cada una', 'todas una por una')
        resultado = self.env['dcasa.tablero'].comparar_ventas(
            comparacion, base=base, vendedor=None if por_vendedora else self._b_vendedora(vendedora),
            por_vendedora=por_vendedora, **argumentos)

        def valor(fila, numero):
            if numero is None:
                return '—'
            if fila['formato'] == 'moneda':
                return c.moneda(numero)
            return f'{numero:,.1f} %' if fila['formato'] == 'porcentaje' else numero

        def lado(cual):
            datos = resultado[cual]
            return f'{datos["etiqueta"]} ({c.fecha(datos["desde"])} al {c.fecha(datos["hasta"])})'

        respuesta = {
            'a': lado('a'),
            'b': lado('b'),
            'cuenta': self._b_base(resultado['base']),
            'filas': [{'cifra': fila['nombre'] + (f' ({fila["nota"]})' if fila['nota'] else ''),
                       'a': valor(fila, fila['a']), 'b': valor(fila, fila['b']),
                       'cambio': self._b_cambio(fila['cambio'])}
                      for fila in resultado['filas']],
        }
        if resultado['vendedor']:
            respuesta['vendedora'] = ('Sin vendedora' if resultado['vendedor'] == SIN_VENDEDORA
                                      else self.env['res.users'].sudo().browse(resultado['vendedor']).name)
        if resultado['hora']:
            respuesta['hasta_la_hora'] = (f'Hoy cuenta hasta las {resultado["hora"]} y el otro día hasta la misma '
                                          'hora.')
        if resultado['modo'] == 'por_dia':
            respuesta['por_dia'] = 'A y B no tienen los mismos días: el % es sobre el promedio por día.'
        if resultado['llevas']:
            pct = resultado['llevas']['pct']
            respuesta['llevas'] = (f'Llevas {pct:,.0f} % de {resultado["llevas"]["mes"]}' if pct is not None
                                   else f'Llevas — de {resultado["llevas"]["mes"]} (ese mes no tuvo ventas)')
        if resultado['por_vendedora'] is not None:
            respuesta['por_vendedora'] = [
                {'vendedora': fila['nombre'], 'a': c.moneda(fila['a']), 'b': c.moneda(fila['b']),
                 'cambio': self._b_cambio(fila['cambio'])} for fila in resultado['por_vendedora']]
        return respuesta

    @herramienta(
        nombre='buscar_ventas',
        descripcion='Busca ventas y cotizaciones por cliente o número, estado y periodo.',
        parametros={
            'texto': {'type': 'string', 'description': 'Cliente o número, p. ej. «Juan Pérez» o «S00012». Opcional.'},
            'estado': {'type': 'string', 'enum': ['cotizacion', 'confirmada', 'cancelada', 'todas'],
                       'description': 'Filtrar por estado. Por defecto «todas».'},
            'periodo': c.PARAM_PERIODO,
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['cotizaciones abiertas → estado=cotizacion', 'ventas de María este mes'],
    )
    def _h_buscar_ventas(self, texto=None, estado='todas', periodo=None, limite=10):
        dominio = []
        if estado and estado != 'todas':
            if estado not in ESTADOS:
                raise BrianError('Estado desconocido. Usa cotizacion, confirmada, cancelada o todas.')
            dominio.append(('state', 'in', ESTADOS[estado]))
        if texto:
            dominio += ['|', ('name', 'ilike', texto), ('partner_id', 'ilike', texto)]
        if periodo:
            inicio, fin, _etiqueta = self._b_rango(periodo)
            d_inicio, d_fin = self._b_limites(inicio, fin)
            dominio += [('date_order', '>=', d_inicio), ('date_order', '<', d_fin)]
        Order = self.env['sale.order']
        total = Order.search_count(dominio)
        ordenes = Order.search(dominio, limit=c.limite(limite), order='date_order desc, id desc')
        return {'encontradas': total, 'mostradas': len(ordenes), 'ventas': [self._b_fila_venta(o) for o in ordenes]}

    @herramienta(
        nombre='ver_venta',
        descripcion='Detalle de una venta o cotización: cliente, productos, total, facturación y entrega.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['ver S00012', '¿qué lleva la cotización de Juan?'],
    )
    def _h_ver_venta(self, venta):
        orden = self._b_venta(venta)
        facturacion = {'no': 'nada que facturar', 'to invoice': 'por facturar', 'invoiced': 'facturada',
                       'upselling': 'facturada (con extra)'}
        resumen = self._b_resumen_orden(orden)
        resumen.update({
            'fecha': c.fecha(orden.date_order),
            'vendedor': orden.user_id.name or '',
            'facturacion': facturacion.get(orden.invoice_status, orden.invoice_status or ''),
            'facturas': [f'{self._b_numero_factura(f)} ({self._b_estado_factura(f)})' for f in orden.invoice_ids],
        })
        if orden.state == 'sale' and 'delivery_status' in orden._fields:
            resumen['entrega'] = {'pending': 'por entregar', 'started': 'entregada en parte', 'partial':
                                  'entregada en parte', 'full': 'entregada'}.get(orden.delivery_status, 'sin entregas')
        return resumen

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    @api.model
    def _b_productos_de(self, producto, cantidad, precio, lineas):
        """Un producto (con cantidad y precio) y/o varias líneas «SOF-001 x 2; MES-003 x 1»."""
        items = []
        if producto:
            items.append((self._b_producto(producto), cantidad, precio))
        if lineas:
            items += self._b_lineas_productos(lineas)
        if not items:
            raise BrianError('Dime qué productos: «producto» para uno, o «lineas» para varios '
                             '(p. ej. «SOF-001 x 2; MES-003 x 1»).')
        return items

    @herramienta(
        nombre='crear_cotizacion',
        descripcion='Crea una cotización en borrador para un cliente con uno o varios productos '
                    '(«lineas»: «SOF-001 x 2; MES-003 x 1»).',
        parametros={
            'cliente': {'type': 'string', 'description': 'Nombre, celular o RUC del cliente, p. ej. «6123-4567».'},
            'producto': PARAM_PRODUCTO, 'cantidad': PARAM_CANTIDAD, 'precio': PARAM_PRECIO,
            'lineas': c.PARAM_LINEAS,
        },
        requeridos=['cliente'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['cotiza 2 sillas SIL-010 para Ana Gómez',
                  'cotiza a 6123-4567 el SOF-001 y 2 MES-003 → lineas=«SOF-001 x 1; MES-003 x 2»'],
    )
    def _h_crear_cotizacion(self, cliente, producto=None, cantidad=1, precio=None, lineas=None):
        partner = self._b_contacto(cliente)
        items = self._b_productos_de(producto, cantidad, precio, lineas)
        orden = self.env['sale.order'].create({'partner_id': partner.id})
        for variante, cant, prec in items:
            self._b_linea_venta(orden, variante, cant, prec)
        return {'mensaje': f'Cotización {orden.name} creada en borrador.', **self._b_resumen_orden(orden),
                'abrir': {'modelo': 'sale.order', 'res_id': orden.id, 'titulo': orden.name}}

    @herramienta(
        nombre='agregar_linea_cotizacion',
        descripcion='Agrega uno o varios productos a una cotización que no se ha confirmado.',
        parametros={'venta': PARAM_VENTA, 'producto': PARAM_PRODUCTO, 'cantidad': PARAM_CANTIDAD,
                    'precio': PARAM_PRECIO, 'lineas': c.PARAM_LINEAS},
        requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['agrega una mesa de noche a S00012', 'agrega a S00012 → lineas=«SIL-010 x 4; MES-003 x 1»'],
    )
    def _h_agregar_linea_cotizacion(self, venta, producto=None, cantidad=1, precio=None, lineas=None):
        orden = self._b_cotizacion_editable(venta)
        for variante, cant, prec in self._b_productos_de(producto, cantidad, precio, lineas):
            self._b_linea_venta(orden, variante, cant, prec)
        return {'mensaje': f'Agregado a {orden.name}.', **self._b_resumen_orden(orden)}

    @herramienta(
        nombre='quitar_linea_cotizacion',
        descripcion='Quita un producto de una cotización que no se ha confirmado.',
        parametros={'venta': PARAM_VENTA, 'producto': PARAM_PRODUCTO},
        requeridos=['venta', 'producto'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['quita el sofá de la cotización S00012'],
    )
    def _h_quitar_linea_cotizacion(self, venta, producto):
        orden = self._b_cotizacion_editable(venta)
        lineas = orden.order_line.filtered(lambda ln: not ln.display_type)
        texto = c.normalizar_texto(producto)
        coinciden = lineas.filtered(lambda ln: texto in c.normalizar_texto(ln.product_id.display_name)
                                    or texto == c.normalizar_texto(ln.product_id.default_code or ''))
        if not coinciden:
            raise BrianError(f'{orden.name} no tiene «{producto}». Lleva: '
                             + '; '.join(lineas.mapped('product_id.display_name')) + '.')
        if len(coinciden) > 1:
            raise BrianError(f'En {orden.name} hay varias líneas con «{producto}»: '
                             + '; '.join(coinciden.mapped('product_id.display_name')) + '. Dime cuál.')
        nombre = coinciden.product_id.display_name
        coinciden.unlink()
        return {'mensaje': f'Quité {nombre} de {orden.name}.', **self._b_resumen_orden(orden)}

    @herramienta(
        nombre='enviar_cotizacion_whatsapp',
        descripcion='Prepara el mensaje de WhatsApp con la cotización (total y enlace) para el celular del cliente '
                    'y devuelve el enlace para abrirlo. La marca como enviada.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['mándale la cotización S00012 por WhatsApp'],
    )
    def _h_enviar_cotizacion_whatsapp(self, venta):
        orden = self._b_venta(venta)
        if orden.state == 'cancel':
            raise BrianError(f'{orden.name} está cancelada: no se envía.')
        accion = orden.action_dcasa_whatsapp()
        return {'mensaje': f'Listo el mensaje de {orden.name} para {orden.partner_id.display_name}. '
                           'Abre el enlace para enviarlo por WhatsApp.',
                'enlace': accion['url'], 'abrir': {'url': accion['url'], 'titulo': 'Enviar por WhatsApp'}}

    # ------------------------------------------------------------------
    # Sensibles
    # ------------------------------------------------------------------

    @herramienta(
        nombre='confirmar_venta',
        descripcion='Confirma una cotización y la convierte en venta (reserva y crea la entrega).',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='sensible', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['confirma la cotización S00012'],
    )
    def _h_confirmar_venta(self, venta):
        orden = self._b_cotizacion_editable(venta)
        if not orden.order_line.filtered(lambda ln: not ln.display_type):
            raise BrianError(f'{orden.name} no tiene productos: agrega al menos uno antes de confirmar.')
        orden.action_confirm()
        return {'mensaje': f'{orden.name} confirmada.', **self._b_resumen_orden(orden)}

    @herramienta(
        nombre='cancelar_cotizacion',
        descripcion='Cancela una cotización que no se ha confirmado. Las ventas confirmadas las cancela una persona.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='sensible', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['cancela la cotización S00012'],
    )
    def _h_cancelar_cotizacion(self, venta):
        orden = self._b_venta(venta)
        if orden.state not in ('draft', 'sent'):
            raise BrianError(f'{orden.name} es una {self._b_estado_venta(orden)}: cancelar una venta confirmada '
                             '(con entregas o facturas) lo hace una persona desde Ventas.')
        orden.action_cancel()
        return {'mensaje': f'Cotización {orden.name} cancelada.', 'numero': orden.name,
                'estado': self._b_estado_venta(orden)}
