"""Herramientas de «Por día» y «Movimientos» (2026-10-22): «¿cuánto se vendió el martes?», «ventas por día de este
mes» y «¿qué movimientos tuvo el producto X?». Las mismas cuentas de las pantallas (``dcasa.tablero.por_dia`` y
``dcasa.movimientos``), con los mismos permisos: el servidor de esas pantallas los exige otra vez."""
import re
from datetime import date, timedelta

from odoo import api, models
from odoo.addons.dcasa_interfaz.models.comparar import MESES
from odoo.addons.dcasa_interfaz.models.movimientos import TIPOS
from odoo.addons.dcasa_interfaz.models.por_dia import BASES_POR_DIA

from . import herramientas_comun as c
from .registro import BrianError, herramienta

GERENCIA = ('sales_team.group_sale_manager',)
INVENTARIO_O_ADMIN = (('stock.group_stock_manager', 'base.group_system'),)
DIAS_DE_LA_SEMANA = ('lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo')
DIAS_CORTOS = ('lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom')
PARAM_BASE_POR_DIA = {
    'type': 'string', 'enum': list(BASES_POR_DIA),
    'description': 'Qué contar. «facturado» (por defecto, como abre el Inicio): las facturas publicadas, por su fecha; '
                   'las notas de crédito restan. «confirmado»: lo vendido, los pedidos confirmados, el día que se '
                   'confirmaron. «con_abonos»: facturas con al menos un abono. «completadas»: pagadas por completo, el '
                   'día que se terminó de pagar (el del pago que dejó la factura en cero).',
}


class BrianHerramientasEstadisticas(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Fechas dichas como las dice la gente
    # ------------------------------------------------------------------

    @api.model
    def _b_dia_dicho(self, texto, hoy):
        """«hoy», «ayer», «el martes» (el último martes, hoy incluido), «el martes pasado» (antes de hoy) o fecha."""
        normal = c.normalizar_texto(texto)
        if normal in ('hoy', 'ayer', 'anteayer', 'antier'):
            return hoy - timedelta(days={'hoy': 0, 'ayer': 1}.get(normal, 2))
        for numero, nombre in enumerate(DIAS_DE_LA_SEMANA):
            if re.search(rf'\b{nombre}\b', normal):
                atras = (hoy.weekday() - numero) % 7
                if atras == 0 and 'pasad' in normal:
                    atras = 7
                return hoy - timedelta(days=atras)
        return c.leer_fecha(normal, 'fecha del día')

    @api.model
    def _b_mes_dicho(self, texto, hoy):
        """«este mes» (o vacío), «mes pasado», «septiembre» (el último que ya empezó), «septiembre 2025», «09/2026» o
        «2026-09» → «aaaa-mm»."""
        normal = c.normalizar_texto(texto or '')
        if not normal or normal in ('este mes', 'mes actual', 'este'):
            return hoy.strftime('%Y-%m')
        if normal in ('mes pasado', 'el mes pasado', 'anterior'):
            return (hoy.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
        if re.fullmatch(r'\d{4}-\d{1,2}', normal):
            anio, mes = (int(x) for x in normal.split('-'))
        elif re.fullmatch(r'\d{1,2}/\d{4}', normal):
            mes, anio = (int(x) for x in normal.split('/'))
        else:
            nombres = [c.normalizar_texto(m) for m in MESES]
            partes = normal.replace(' de ', ' ').split()
            mes = next((nombres.index(p) + 1 for p in partes if p in nombres), None) or next(
                (i + 1 for i, n in enumerate(nombres) for p in partes if len(p) >= 3 and n.startswith(p)), None)
            if not mes:
                raise BrianError(f'No entendí el mes «{texto}». Dilo como «septiembre» o «09/2026».')
            anio = next((int(p) for p in partes if p.isdigit() and len(p) == 4), None)
            if anio is None:
                anio = hoy.year if mes <= hoy.month else hoy.year - 1
        if not 1 <= mes <= 12:
            raise BrianError(f'No entendí el mes «{texto}». Dilo como «septiembre» o «09/2026».')
        return date(anio, mes, 1).strftime('%Y-%m')

    @staticmethod
    def _b_cambio_simple(cambio, sentido):
        if cambio is None:
            return '—'
        flecha = {'sube': '▲ ', 'baja': '▼ '}.get(sentido, '')
        return f'{flecha}{abs(cambio):,.1f} %'

    # ------------------------------------------------------------------
    # Ventas o facturas por día
    # ------------------------------------------------------------------

    @herramienta(
        nombre='ventas_por_dia',
        descripcion='Lo vendido o facturado por día (pantalla Por día): con «dia», el total de ese día y cada factura '
                    'o pedido; sin «dia», cada día del mes, el total, el mejor día y la comparación con el mes '
                    'anterior. Sin ITBMS.',
        parametros={
            'dia': {'type': 'string', 'description': 'Un día: «hoy», «ayer», «el martes», «el martes pasado» o '
                                                     '«20/10/2026». Vacío: el mes entero.'},
            'mes': {'type': 'string', 'description': 'Sin «dia»: «este mes» (por defecto), «mes pasado», «septiembre» '
                                                     'o «09/2026».'},
            'base': PARAM_BASE_POR_DIA,
            'vendedora': {'type': 'string', 'description': 'El nombre de una vendedora o «sin vendedora». Vacío: todo '
                                                           'el equipo.'},
        },
        nivel='lectura', categoria='ventas', grupos=GERENCIA,
        ejemplos=['¿cuánto se facturó el martes? → dia=el martes',
                  '¿cuánto se vendió ayer? → dia=ayer, base=confirmado',
                  'ventas por día de este mes → (sin dia)', 'facturado por día de septiembre → mes=septiembre',
                  '¿qué vendió Ana el 20/10/2026? → dia=20/10/2026, vendedora=Ana'],
    )
    def _h_ventas_por_dia(self, dia=None, mes=None, base=None, vendedora=None):
        Tablero = self.env['dcasa.tablero']
        hoy = Tablero._ahora_en_panama().date()
        vendedor = self._b_vendedora(vendedora)
        pedidos = base == 'confirmado'
        if dia:
            fecha = self._b_dia_dicho(dia, hoy)
            datos = Tablero.ventas_del_dia(str(fecha), base=base, vendedor=vendedor)
            total = datos['total']
            respuesta = {
                'dia': f'{datos["nombre"]} ({c.fecha(fecha)})',
                'cuenta': self._b_base_por_dia(datos['base']),
                'ventas_sin_itbms': c.moneda(total['sin_itbms']),
                'itbms': c.moneda(total['itbms']),
                'total_con_itbms': c.moneda(total['total']),
                'pedidos' if pedidos else 'facturas': total['cuantas'],
                'documentos': [{
                    'numero': fila['numero'], 'cliente': fila['cliente'], 'vendedora': fila['vendedora'],
                    'sin_itbms': c.moneda(fila['sin_itbms']), 'con_itbms': c.moneda(fila['total']),
                    'estado': fila['estado'], **({'detalle': fila['detalle']} if fila['detalle'] else {}),
                } for fila in datos['filas'][:c.MAX_FILAS]],
            }
            if total['notas']:
                respuesta['notas_de_credito'] = total['notas']
            if total.get('falta_por_cobrar') is not None:
                respuesta['falta_por_cobrar_con_itbms'] = c.moneda(total['falta_por_cobrar'])
            if len(datos['filas']) > c.MAX_FILAS:
                respuesta['nota'] = (f'Son {len(datos["filas"])}; aquí van las primeras {c.MAX_FILAS}. La lista '
                                     'completa está en Ventas › Hoy › Ventas por día o en Facturación › Facturado '
                                     'por día.')
            if not datos['filas']:
                respuesta['nota'] = 'Ese día no hubo ' + ('pedidos confirmados.' if pedidos else 'facturas.')
            return respuesta
        datos = Tablero.por_dia(mes=self._b_mes_dicho(mes, hoy), base=base, vendedor=vendedor)
        total, anterior = datos['total'], datos['anterior']
        respuesta = {
            'mes': datos['nombre'] + (f' (del {total["etiqueta"]})' if datos['en_curso'] else ''),
            'cuenta': self._b_base_por_dia(datos['base']),
            'total_sin_itbms': c.moneda(total['sin_itbms']),
            'itbms': c.moneda(total['itbms']),
            'total_con_itbms': c.moneda(total['total']),
            'pedidos' if pedidos else 'facturas': total['cuantas'],
            'ticket_promedio_sin_itbms': '—' if total['ticket'] is None else c.moneda(total['ticket']),
            'dias': [{'dia': f'{DIAS_CORTOS[d["semana"]]} {c.fecha(d["fecha"])}', 'sin_itbms': c.moneda(d['sin_itbms']),
                      'cuantas': d['cuantas'], **({'notas_de_credito': d['notas']} if d['notas'] else {})}
                     for d in datos['dias'] if not d['futuro'] and (d['cuantas'] or d['notas'])],
            'dias_sin_ventas': sum(1 for d in datos['dias'] if not d['futuro'] and not (d['cuantas'] or d['notas'])),
            'contra': f'{anterior["etiqueta"]}: {c.moneda(anterior["sin_itbms"])} sin ITBMS → '
                      f'{self._b_cambio_simple(anterior["cambio"], anterior["sentido"])}',
        }
        if anterior['hora']:
            respuesta['hasta_la_hora'] = (f'El último día del mes anterior cuenta hasta las {anterior["hora"]}, '
                                          'como hoy.')
        if datos['mejor']:
            respuesta['mejor_dia'] = f'{datos["mejor"]["nombre"]}: {c.moneda(datos["mejor"]["sin_itbms"])}'
        if total['notas']:
            respuesta['notas_de_credito'] = total['notas']
        if vendedor:
            respuesta['vendedora'] = Tablero._nombre_de_vendedora(vendedor)
        return respuesta

    @api.model
    def _b_base_por_dia(self, base):
        for opcion in self.env['dcasa.tablero']._bases_por_dia():
            if opcion['clave'] == base:
                return f'{opcion["nombre"]}: {opcion["detalle"][:1].lower()}{opcion["detalle"][1:]}'
        return base

    # ------------------------------------------------------------------
    # Movimientos de inventario
    # ------------------------------------------------------------------

    @herramienta(
        nombre='movimientos_de_producto',
        descripcion='Los movimientos de inventario de un producto, en palabras (Inventario › Movimientos): compra, '
                    'venta, ajuste, devolución o traslado, con la cantidad (+/−), lo que quedó, quién y cuándo. Sin '
                    'producto: los últimos de todos.',
        parametros={
            'producto': {'type': 'string', 'description': 'Nombre, código o código de barras. Vacío: todos.'},
            'desde': c.PARAM_DESDE, 'hasta': c.PARAM_HASTA,
            'tipo': {'type': 'string', 'enum': list(TIPOS),
                     'description': 'Solo un tipo: compra, venta, devolucion, ajuste, traslado u otro.'},
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='catalogo', grupos=INVENTARIO_O_ADMIN,
        ejemplos=['¿qué movimientos tuvo el SOF-001? → producto=SOF-001',
                  '¿cuándo entró la cama queen? → producto=cama queen, tipo=compra',
                  'últimos movimientos del inventario → (sin producto)'],
    )
    def _h_movimientos_de_producto(self, producto=None, desde=None, hasta=None, tipo=None, limite=10):
        variante = self._b_producto(producto) if producto else None
        inicio = c.leer_fecha(desde, 'fecha inicial') if desde else None
        fin = c.leer_fecha(hasta, 'fecha final') if hasta else None
        datos = self.env['dcasa.movimientos'].movimientos(
            producto_id=variante.id if variante else False, desde=str(inicio) if inicio else False,
            hasta=str(fin) if fin else False, tipo=tipo or False, por_pagina=c.limite(limite, 10))
        filas = [{
            'cuando': fila['cuando'], 'que': fila['texto'], 'cantidad': fila['cantidad_texto'],
            **({'quedan': c.cantidad(fila['queda'])} if fila['queda'] is not None else {}),
            'quien': fila['quien'],
            **({'producto': fila['producto']['nombre']} if fila.get('producto') else {}),
        } for fila in datos['filas']]
        respuesta = {'movimientos': filas}
        if variante:
            respuesta = {
                'producto': variante.display_name,
                'hay_hoy': c.cantidad(datos['existencia']),
                'movimientos_en_total': datos['total'],
                **respuesta,
            }
            if datos['cuadra'] is False:
                respuesta['aviso'] = ('No se dice lo que quedó después de cada movimiento: hay '
                                      f'{c.cantidad(abs(datos["diferencia"]))} unidades cargadas sin un movimiento '
                                      '(por ejemplo, la carga inicial).')
        if datos['hay_mas']:
            respuesta['nota'] = 'Hay más: la línea de tiempo completa está en Inventario › Movimientos.'
        if not filas:
            respuesta['nota'] = 'No hay movimientos con esos filtros.'
        return respuesta
