"""«Por día» (Ventas y Facturación) y las «Estadísticas» claras (pedido del jefe, 2026-10-22).

La dueña: «al jefe le gustaría poder ver organizado fácilmente lo vendido o facturado por día de los días del mes, poder
ver fácilmente lo que se hizo x día» y «tenemos estadísticas pero muy poco intuitivas y limitadas».

Cuenta con las mismas bases del Inicio de Gerencia (``ventas_bases.py``) y una más, la de Ventas:

* ``confirmado`` («Vendido»): los **pedidos confirmados**, el día de Panamá en que se confirmaron (``date_order``: Odoo
  le pone la hora de la confirmación). Un pedido cancelado deja de contar; una cotización no cuenta. Sin ITBMS
  (``amount_untaxed``), con el ITBMS y el total aparte.
* ``facturado``, ``con_abonos`` y ``completadas``: exactamente las del interruptor del Inicio (las facturas de cliente
  publicadas; las notas de crédito restan; una factura anulada no cuenta). El total del mes es el mismo ``_medir`` del
  Inicio para esas fechas, y cada día es la suma de esas mismas filas: los días suman el mes al centavo.

«Mes anterior» es la misma cuenta que «Comparar › del 1 a hoy» del Inicio cuando el mes está en curso (los mismos días
del mes pasado, el último hasta la misma hora de Panamá) y el mes anterior completo cuando el mes ya terminó.

Solo Gerencia y los administradores (``_exigir_gerencia``, igual que Comparar): el servidor lo exige en cada llamada.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, models
from odoo.exceptions import UserError

from .comparar import MESES, MESES_CORTOS, MESES_PARA_ELEGIR, ZONA_PANAMA, _fin_de_mes, _hora, _rango_texto, _variacion
from .tablero import BASE_CON_ABONOS, BASE_FACTURADO, BASES_DE_GERENCIA, SIN_VENDEDORA, _accion

BASE_CONFIRMADO = 'confirmado'
# El orden de los botones de «Por día» y de «Estadísticas».
BASES_POR_DIA = (BASE_CONFIRMADO,) + BASES_DE_GERENCIA
DIAS_LARGOS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
DIAS_CORTOS = ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom')
# Estadísticas: los periodos de los botones; hasta DIAS_EN_BARRAS días, una barra por día; más largo, una por mes.
PERIODOS_ESTADISTICAS = ('semana', 'mes', 'mes_pasado', 'tres_meses', 'anio', 'rango')
DIAS_EN_BARRAS = 62
TIPOS_A_LA_VISTA = 8
PRODUCTOS_A_LA_VISTA = 10
CAMPOS_DEL_PEDIDO = ['name', 'partner_id', 'user_id', 'date_order', 'amount_untaxed', 'amount_tax', 'amount_total',
                     'invoice_status']
ESTADO_DE_PEDIDO = {'invoiced': 'Facturado', 'upselling': 'Facturado', 'to invoice': 'Por facturar',
                    'no': 'Por facturar'}
ESTADO_DE_FACTURA = {'paid': 'Pagada', 'in_payment': 'Pagada', 'partial': 'Con abono', 'not_paid': 'Por cobrar',
                     'reversed': 'Revertida', 'invoicing_legacy': 'Del sistema anterior'}


def _zona():
    return pytz.timezone(ZONA_PANAMA)


def _dia_en_panama(momento):
    """El día de Panamá de un ``datetime`` guardado en UTC sin zona (como guarda Odoo)."""
    return pytz.utc.localize(momento).astimezone(_zona()).date()


def _inicio_en_utc(dia):
    """Las 00:00 de un día de Panamá, en UTC sin zona."""
    return _zona().localize(datetime.combine(dia, time.min)).astimezone(pytz.utc).replace(tzinfo=None)


def _nombre_del_dia(dia, con_anio=False):
    """«Jueves 22 de octubre» (y «de 2025» si hace falta)."""
    texto = f'{DIAS_LARGOS[dia.weekday()].capitalize()} {dia.day} de {MESES[dia.month - 1]}'
    return f'{texto} de {dia.year}' if con_anio else texto


def _nombre_del_mes(primero):
    return f'{MESES[primero.month - 1].capitalize()} {primero.year}'


class DcasaTableroPorDia(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    # ------------------------------------------------------------------
    # Bases y opciones de la pantalla
    # ------------------------------------------------------------------

    @api.model
    def _bases_por_dia(self):
        """«Vendido» (pedidos confirmados) y las tres del Inicio de Gerencia, con su línea corta."""
        vendido = {'clave': BASE_CONFIRMADO, 'nombre': self.env._('Vendido'),
                   'detalle': self.env._('Pedidos confirmados, el día que se confirmaron')}
        return [vendido] + self._bases_de_ventas()

    @api.model
    def _base_por_dia(self, base, defecto=BASE_FACTURADO):
        if base in (None, False, ''):
            return defecto
        if base not in BASES_POR_DIA:
            raise UserError(self.env._('Elige «Vendido», «Facturado», «Con abonos» o «Completadas».'))
        return base

    @api.model
    def _meses_por_dia(self, hoy):
        """Este mes y los 24 anteriores, del más reciente al más viejo: ``[{'valor': '2026-10', 'nombre'}]``."""
        actual = hoy.replace(day=1)
        return [{'valor': actual.strftime('%Y-%m'), 'nombre': _nombre_del_mes(actual)}] + self._meses_para_elegir(hoy)

    @api.model
    def _mes_por_dia(self, mes, hoy):
        """El primer día del mes pedido (``'2026-10'``); sin mes, este. Solo este mes o uno de los últimos 24."""
        if mes in (None, False, ''):
            return hoy.replace(day=1)
        if not isinstance(mes, str) or mes not in {m['valor'] for m in self._meses_por_dia(hoy)}:
            raise UserError(self.env._('Elige este mes o uno de los últimos 24.'))
        anio, numero = mes.split('-')
        return date(int(anio), int(numero), 1)

    # ------------------------------------------------------------------
    # «Vendido»: los pedidos confirmados
    # ------------------------------------------------------------------

    @api.model
    def _pedidos_confirmados(self, d0, d1, vendedor=None, corte=None):
        """Los pedidos confirmados (``state = 'sale'``) de las empresas de quien mira, confirmados entre las 00:00 de
        ``d0`` y el fin de ``d1`` en hora de Panamá. ``corte`` (UTC sin zona): el último día solo hasta esa hora.
        Corre como quien mira (Gerencia y administradores ven todos los pedidos)."""
        hasta = ('date_order', '<=', corte) if corte else ('date_order', '<', _inicio_en_utc(d1 + timedelta(days=1)))
        dominio = [('state', '=', 'sale'), ('company_id', 'in', self.env.companies.ids),
                   ('date_order', '>=', _inicio_en_utc(d0)), hasta] + self._clausula_vendedor(vendedor)
        return self.env['sale.order'].search_fetch(dominio, CAMPOS_DEL_PEDIDO, order='date_order, id')

    @api.model
    def _medir_confirmados(self, d0, d1, vendedor=None, corte=None):
        """Las cifras de los pedidos confirmados, con la forma de ``_medir`` (``pedidos`` en vez de ``filas``)."""
        pedidos = self._pedidos_confirmados(d0, d1, vendedor, corte)
        redondear = self.env.company.currency_id.round
        sin_itbms = redondear(sum(pedidos.mapped('amount_untaxed')))
        return {
            'pedidos': pedidos, 'confirmados': True,
            'cuantas': len(pedidos), 'notas': 0, 'de_pedido': len(pedidos),
            'sin_itbms': sin_itbms,
            'itbms': redondear(sum(pedidos.mapped('amount_tax'))),
            'total': redondear(sum(pedidos.mapped('amount_total'))),
            'ticket': self._ticket_promedio(sin_itbms, len(pedidos)),
            'ganancia': None, 'falta_por_cobrar': None, 'cobrado': None,
        }

    @api.model
    def _medir_por_dia(self, d0, d1, base, vendedor=None, corte=None):
        """Las cifras de un periodo en cualquiera de las cuatro bases (las de facturas: el ``_medir`` del Inicio)."""
        if base == BASE_CONFIRMADO:
            return self._medir_confirmados(d0, d1, vendedor, corte)
        return self._medir(d0, d1, base, vendedor, corte)

    @api.model
    def _sumas_por_dia(self, medida):
        """``{día: [sin_itbms, itbms, total, cuantas, notas]}`` de lo que se contó en una medida."""
        por_dia = defaultdict(lambda: [0.0, 0.0, 0.0, 0, 0])
        if 'pedidos' in medida:
            for pedido in medida['pedidos']:
                suma = por_dia[_dia_en_panama(pedido.date_order)]
                suma[0] += pedido.amount_untaxed
                suma[1] += pedido.amount_tax
                suma[2] += pedido.amount_total
                suma[3] += 1
        else:
            for fila in medida['filas']:
                suma = por_dia[fila['dia']]
                suma[0] += fila['sin_itbms']
                suma[1] += fila['itbms']
                suma[2] += fila['total']
                suma[3 if not fila['es_nota'] else 4] += 1
        return por_dia

    @api.model
    def _accion_de_lo_contado(self, nombre, medida):
        """La lista que explica una cifra: los pedidos o las facturas (con las notas de crédito) que se contaron."""
        if 'pedidos' in medida:
            return _accion(nombre, 'sale.order', [('id', 'in', medida['pedidos'].ids)])
        return self._accion_de_facturas(nombre, [fila['id'] for fila in medida['filas']])

    # ------------------------------------------------------------------
    # Por día: el mes como calendario
    # ------------------------------------------------------------------

    @api.model
    def por_dia(self, mes=None, base=None, vendedor=None):
        """El mes día por día en una base (``confirmado``, ``facturado``, ``con_abonos`` o ``completadas``) y, si se
        pide, de una vendedora. Solo lectura; exige Gerencia o administrador y valida todo antes de leer."""
        self._exigir_gerencia()
        base = self._base_por_dia(base)
        vendedor = self._vendedor_pedido(vendedor)
        return self._por_dia(mes, base, vendedor, self._ahora_en_panama())

    @api.model
    def _por_dia(self, mes, base, vendedor, ahora):
        hoy = ahora.date()
        primero = self._mes_por_dia(mes, hoy)
        ultimo = _fin_de_mes(primero)
        hasta = min(ultimo, hoy)
        # El mes de hoy está en curso hasta su último día inclusive (el 31 todavía no terminó).
        en_curso = (primero.year, primero.month) == (hoy.year, hoy.month)
        medida = self._medir_por_dia(primero, hasta, base, vendedor)
        sumas = self._sumas_por_dia(medida)
        redondear = self.env.company.currency_id.round
        dias = []
        for numero in range(1, ultimo.day + 1):
            dia = primero.replace(day=numero)
            sin_itbms, itbms, total, cuantas, notas = sumas.get(dia, (0.0, 0.0, 0.0, 0, 0))
            dias.append({
                'fecha': str(dia), 'numero': numero, 'semana': dia.weekday(),
                'corto': f'{DIAS_CORTOS[dia.weekday()]} {numero}', 'nombre': _nombre_del_dia(dia),
                'sin_itbms': redondear(sin_itbms), 'itbms': redondear(itbms), 'total': redondear(total),
                'cuantas': cuantas, 'notas': notas, 'futuro': dia > hoy, 'hoy': dia == hoy,
            })
        con_ventas = [d for d in dias if d['cuantas'] or d['notas']]
        mejor = max(con_ventas, key=lambda d: (d['sin_itbms'], -d['numero']), default=None)
        nombre_base = next(b['nombre'] for b in self._bases_por_dia() if b['clave'] == base)
        titulo = f'{nombre_base} · {_nombre_del_mes(primero)}'
        if vendedor:
            titulo += ' · ' + self._nombre_de_vendedora(vendedor)
        return {
            'mes': primero.strftime('%Y-%m'), 'nombre': _nombre_del_mes(primero),
            'base': base, 'vendedor': vendedor, 'hoy': str(hoy),
            'primer_dia_semana': primero.weekday(),
            'en_curso': en_curso,
            'dias': dias,
            'total': {
                'sin_itbms': medida['sin_itbms'], 'itbms': medida['itbms'], 'total': medida['total'],
                'cuantas': medida['cuantas'], 'notas': medida['notas'], 'ticket': medida['ticket'],
                'dias_con_ventas': len(con_ventas),
                'etiqueta': _rango_texto(primero, hasta, hoy),
                'desde': str(primero), 'hasta': str(hasta),
            },
            'mejor': {'fecha': mejor['fecha'], 'nombre': mejor['nombre'], 'sin_itbms': mejor['sin_itbms']}
            if mejor and mejor['sin_itbms'] > 0 else None,
            'anterior': self._mes_anterior(primero, en_curso, base, vendedor, ahora, medida),
            'accion': self._accion_de_lo_contado(titulo, medida),
        }

    @api.model
    def _mes_anterior(self, primero, en_curso, base, vendedor, ahora, medida):
        """Contra qué se compara el mes: los mismos días del mes pasado (el último hasta la misma hora) si el mes está
        en curso, o el mes anterior completo. ``cambio``: % sobre las ventas sin ITBMS; sin base positiva, ``None``."""
        hoy = ahora.date()
        if en_curso:
            b0, b1 = self._rangos_de_comparar('mes_a_la_fecha', hoy)['b']
            corte = _zona().localize(datetime.combine(b1, ahora.time().replace(tzinfo=None))).astimezone(
                pytz.utc).replace(tzinfo=None)
            etiqueta, hora = _rango_texto(b0, b1, hoy), _hora(ahora)
        else:
            b0 = primero - relativedelta(months=1)
            b1, corte = _fin_de_mes(b0), None
            etiqueta = f'{MESES[b0.month - 1].capitalize()} completo' if b0.year == hoy.year else \
                f'{MESES[b0.month - 1].capitalize()} {b0.year} completo'
            hora = False
        anterior = self._medir_por_dia(b0, b1, base, vendedor, corte)
        cambio = _variacion(medida['sin_itbms'], anterior['sin_itbms'])
        return {
            'etiqueta': etiqueta, 'desde': str(b0), 'hasta': str(b1), 'hora': hora,
            'sin_itbms': anterior['sin_itbms'], 'cuantas': anterior['cuantas'],
            'cambio': cambio,
            'sentido': None if cambio is None else ('sube' if cambio > 0 else ('baja' if cambio < 0 else 'igual')),
        }

    # ------------------------------------------------------------------
    # Lo que se hizo un día
    # ------------------------------------------------------------------

    @api.model
    def ventas_del_dia(self, dia, base=None, vendedor=None):
        """Los pedidos o las facturas de un día (número, cliente, vendedora, total y estado), en una base. Solo lectura;
        exige Gerencia o administrador; el día no puede ser futuro ni de antes de los últimos 24 meses."""
        self._exigir_gerencia()
        base = self._base_por_dia(base)
        vendedor = self._vendedor_pedido(vendedor)
        hoy = self._ahora_en_panama().date()
        dia = self._fecha(dia, 'día')
        if dia > hoy:
            raise UserError(self.env._('Ese día todavía no llega: elige uno de hoy hacia atrás.'))
        if dia < hoy.replace(day=1) - relativedelta(months=MESES_PARA_ELEGIR):
            raise UserError(self.env._('Elige un día de este mes o de los últimos 24 meses.'))
        return self._del_dia(dia, base, vendedor, hoy)

    @api.model
    def _del_dia(self, dia, base, vendedor, hoy):
        medida = self._medir_por_dia(dia, dia, base, vendedor)
        nombres = {}

        def nombre_de(clave):
            if clave not in nombres:
                nombres[clave] = self._nombre_de_vendedora(clave or SIN_VENDEDORA)
            return nombres[clave]

        filas = []
        if 'pedidos' in medida:
            for pedido in medida['pedidos']:
                momento = pytz.utc.localize(pedido.date_order).astimezone(_zona())
                filas.append({
                    'id': pedido.id, 'modelo': 'sale.order', 'numero': pedido.name,
                    'cliente': pedido.partner_id.display_name or '',
                    'vendedora': nombre_de(pedido.user_id.id or SIN_VENDEDORA),
                    'detalle': _hora(momento),
                    'sin_itbms': pedido.amount_untaxed, 'total': pedido.amount_total,
                    'estado': ESTADO_DE_PEDIDO.get(pedido.invoice_status, ''), 'es_nota': False,
                })
        else:
            for fila in medida['filas']:
                documento = fila['documento']
                if fila['es_nota']:
                    estado = 'Nota de crédito'
                    detalle = self.env._('Resta: %(factura)s', factura=documento.reversed_entry_id.name) \
                        if documento.reversed_entry_id else self.env._('Resta')
                else:
                    estado = ESTADO_DE_FACTURA.get(documento.payment_state, '')
                    detalle = documento.invoice_origin or ''
                filas.append({
                    'id': documento.id, 'modelo': 'account.move', 'numero': documento.name,
                    'cliente': documento.partner_id.display_name or '',
                    'vendedora': nombre_de(fila['vendedora']),
                    'detalle': detalle,
                    'sin_itbms': fila['sin_itbms'], 'total': fila['total'],
                    'estado': estado, 'es_nota': fila['es_nota'],
                })
        nombre_base = next(b['nombre'] for b in self._bases_por_dia() if b['clave'] == base)
        titulo = f'{nombre_base} · {_nombre_del_dia(dia, dia.year != hoy.year)}'
        if vendedor:
            titulo += ' · ' + self._nombre_de_vendedora(vendedor)
        return {
            'dia': str(dia), 'nombre': _nombre_del_dia(dia, dia.year != hoy.year), 'base': base,
            'filas': filas,
            'total': {'sin_itbms': medida['sin_itbms'], 'itbms': medida['itbms'], 'total': medida['total'],
                      'cuantas': medida['cuantas'], 'notas': medida['notas'],
                      'falta_por_cobrar': medida.get('falta_por_cobrar') if base == BASE_CON_ABONOS else None},
            'accion': self._accion_de_lo_contado(titulo, medida),
        }

    # ------------------------------------------------------------------
    # Estadísticas: gráficas simples de un periodo
    # ------------------------------------------------------------------

    @api.model
    def _rango_estadisticas(self, periodo, desde, hasta, hoy):
        """``(d0, d1, etiqueta)`` de los botones de Estadísticas. Un rango, con las reglas del Inicio (hasta un año, no
        futuro)."""
        if periodo not in PERIODOS_ESTADISTICAS:
            raise UserError(self.env._('Elige uno de los periodos de los botones.'))
        if periodo == 'semana':
            return hoy - timedelta(days=hoy.weekday()), hoy, self.env._('Esta semana')
        if periodo == 'mes':
            return hoy.replace(day=1), hoy, self.env._('Este mes')
        if periodo == 'mes_pasado':
            primero = hoy.replace(day=1) - relativedelta(months=1)
            return primero, _fin_de_mes(primero), _nombre_del_mes(primero)
        if periodo == 'tres_meses':
            return hoy.replace(day=1) - relativedelta(months=2), hoy, self.env._('Últimos 3 meses')
        if periodo == 'anio':
            return hoy.replace(month=1, day=1), hoy, self.env._('Este año')
        rango = self._rango_del_periodo('rango', desde, hasta, hoy)
        return rango['desde'], rango['hasta'], _rango_texto(rango['desde'], rango['hasta'], hoy)

    @api.model
    def estadisticas(self, periodo='mes', desde=None, hasta=None, base=None):
        """Las Estadísticas de un periodo en una base: el resumen, las barras por día (o por mes, en periodos largos),
        por tipo de producto, por vendedora y lo más vendido. Solo lectura; exige Gerencia o administrador."""
        self._exigir_gerencia()
        base = self._base_por_dia(base)
        hoy = self._ahora_en_panama().date()
        d0, d1, etiqueta = self._rango_estadisticas(periodo, desde, hasta, hoy)
        return self._estadisticas(d0, d1, etiqueta, periodo, base, hoy)

    @api.model
    def _estadisticas(self, d0, d1, etiqueta, periodo, base, hoy):
        medida = self._medir_por_dia(d0, d1, base)
        redondear = self.env.company.currency_id.round
        por_producto = self._por_producto(medida)
        unidades = round(sum(u for u, _m in por_producto.values()), 2)
        nombre_base = next(b['nombre'] for b in self._bases_por_dia() if b['clave'] == base)
        return {
            'periodo': periodo, 'etiqueta': etiqueta, 'desde': str(d0), 'hasta': str(d1), 'hoy': str(hoy),
            'base': base,
            'resumen': {
                'sin_itbms': medida['sin_itbms'], 'itbms': medida['itbms'], 'total': medida['total'],
                'cuantas': medida['cuantas'], 'notas': medida['notas'], 'ticket': medida['ticket'],
                'unidades': unidades,
            },
            'barras': self._barras(d0, d1, medida, hoy),
            'tipos': self._por_tipo(por_producto, redondear),
            'vendedoras': self._por_vendedora_ordenado(medida, redondear),
            'productos': self._mas_vendidos(por_producto, redondear),
            'accion': self._accion_de_lo_contado(f'{nombre_base} · {etiqueta}', medida),
        }

    @api.model
    def _barras(self, d0, d1, medida, hoy):
        """Una barra por día (hasta ``DIAS_EN_BARRAS`` días) o por mes, sin ITBMS, con su número de ventas."""
        sumas = self._sumas_por_dia(medida)
        redondear = self.env.company.currency_id.round
        filas = []
        if (d1 - d0).days + 1 <= DIAS_EN_BARRAS:
            dia = d0
            while dia <= d1:
                sin_itbms, _itbms, _total, cuantas, _notas = sumas.get(dia, (0.0, 0.0, 0.0, 0, 0))
                filas.append({'clave': str(dia), 'etiqueta': str(dia.day),
                              'detalle': f'{DIAS_CORTOS[dia.weekday()]} {dia.day} {MESES_CORTOS[dia.month - 1]}',
                              'sin_itbms': redondear(sin_itbms), 'cuantas': cuantas, 'hoy': dia == hoy,
                              'mes': dia.strftime('%Y-%m')})
                dia += timedelta(days=1)
            return {'por': 'dia', 'filas': filas}
        por_mes = defaultdict(lambda: [0.0, 0])
        for dia, (sin_itbms, _itbms, _total, cuantas, _notas) in sumas.items():
            por_mes[dia.replace(day=1)][0] += sin_itbms
            por_mes[dia.replace(day=1)][1] += cuantas
        mes = d0.replace(day=1)
        while mes <= d1:
            sin_itbms, cuantas = por_mes.get(mes, (0.0, 0))
            filas.append({'clave': mes.strftime('%Y-%m'), 'etiqueta': MESES_CORTOS[mes.month - 1],
                          'detalle': _nombre_del_mes(mes), 'sin_itbms': redondear(sin_itbms), 'cuantas': cuantas,
                          'hoy': mes == hoy.replace(day=1), 'mes': mes.strftime('%Y-%m')})
            mes += relativedelta(months=1)
        return {'por': 'mes', 'filas': filas}

    @api.model
    def _por_producto(self, medida):
        """``{producto: (unidades, sin_itbms)}`` de la mercancía que se contó (sin servicios, flete, descuentos ni
        anticipos): de las facturas (las notas de crédito restan, ``_unidades_por_producto``) o de los pedidos."""
        if 'filas' in medida:
            return self._unidades_por_producto(medida['filas'])
        if not medida['pedidos']:
            return {}
        grupos = self.env['sale.order.line']._read_group(
            [('order_id', 'in', medida['pedidos'].ids), ('display_type', '=', False), ('is_downpayment', '=', False),
             ('product_id', '!=', False), ('product_id.type', '!=', 'service')],
            ['product_id'], ['product_uom_qty:sum', 'price_subtotal:sum'])
        return {producto: (unidades or 0.0, sin_itbms or 0.0) for producto, unidades, sin_itbms in grupos}

    @api.model
    def _por_tipo(self, por_producto, redondear):
        """La mercancía por tipo (la categoría de primer nivel, como «Unidades vendidas por tipo» del Inicio): dinero
        sin ITBMS y unidades, de más a menos dinero; pasados ``TIPOS_A_LA_VISTA``, los demás juntos en «Otros»."""
        por_tipo = defaultdict(lambda: [0.0, 0.0])
        for producto, (unidades, sin_itbms) in por_producto.items():
            camino = [int(i) for i in (producto.sudo().categ_id.parent_path or '').split('/') if i]
            clave = camino[1] if len(camino) > 1 else (camino[0] if camino else False)
            por_tipo[clave][0] += sin_itbms
            por_tipo[clave][1] += unidades
        nombres = {categoria.id: categoria.name for categoria in
                   self.env['product.category'].sudo().browse([clave for clave in por_tipo if clave])}
        filas = sorted(
            ({'nombre': nombres.get(clave) or self.env._('Sin categoría'), 'sin_itbms': redondear(monto),
              'unidades': round(unidades, 2)}
             for clave, (monto, unidades) in por_tipo.items() if round(unidades, 2) or redondear(monto)),
            key=lambda fila: (-fila['sin_itbms'], -fila['unidades'], fila['nombre'].lower()))
        if len(filas) > TIPOS_A_LA_VISTA:
            resto = filas[TIPOS_A_LA_VISTA:]
            filas = filas[:TIPOS_A_LA_VISTA] + [{
                'nombre': self.env._('Otros'), 'sin_itbms': redondear(sum(f['sin_itbms'] for f in resto)),
                'unidades': round(sum(f['unidades'] for f in resto), 2)}]
        return filas

    @api.model
    def _por_vendedora_ordenado(self, medida, redondear):
        """Una fila por vendedora (y «Sin vendedora»): ventas sin ITBMS y cuántas, de más a menos. Suman el total."""
        filas = [{'vendedor': clave, 'nombre': self._nombre_de_vendedora(clave),
                  'sin_itbms': redondear(monto), 'cuantas': cuantas}
                 for clave, (cuantas, monto) in self._por_vendedora(medida).items()]
        return sorted(filas, key=lambda fila: (-fila['sin_itbms'], -fila['cuantas'], (fila['nombre'] or '').lower()))

    @api.model
    def _mas_vendidos(self, por_producto, redondear, limite=PRODUCTOS_A_LA_VISTA):
        """Los productos con más unidades (juntando las variantes de un mismo producto, como «Lo más vendido» del
        Inicio), con su venta sin ITBMS."""
        por_plantilla = defaultdict(lambda: [0.0, 0.0])
        for producto, (unidades, sin_itbms) in por_producto.items():
            plantilla = producto.sudo().product_tmpl_id
            por_plantilla[plantilla][0] += unidades
            por_plantilla[plantilla][1] += sin_itbms
        filas = [{'id': plantilla.id, 'nombre': plantilla.name, 'unidades': round(unidades, 2),
                  'sin_itbms': redondear(sin_itbms), 'imagen': f'/web/image/product.template/{plantilla.id}/image_128'}
                 for plantilla, (unidades, sin_itbms) in por_plantilla.items() if round(unidades, 2) > 0]
        return sorted(filas, key=lambda fila: (-fila['unidades'], -fila['sin_itbms'], fila['id']))[:limite]

    # ------------------------------------------------------------------
    # Para la pantalla: opciones de una vez
    # ------------------------------------------------------------------

    @api.model
    def opciones_por_dia(self):
        """Las opciones de las pantallas «Por día» y «Estadísticas»: las bases, los meses y las vendedoras. Exige
        Gerencia o administrador."""
        self._exigir_gerencia()
        hoy = self._ahora_en_panama().date()
        moneda = self.env.company.currency_id
        return {
            'hoy': str(hoy),
            'moneda': {'simbolo': moneda.symbol, 'antes': moneda.position == 'before'},
            'bases': self._bases_por_dia(),
            'meses': self._meses_por_dia(hoy),
            'vendedoras': self._vendedoras_para_elegir(hoy),
        }
