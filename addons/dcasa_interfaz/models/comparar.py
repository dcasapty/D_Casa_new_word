"""«Comparar» del Inicio de Gerencia: números lado a lado, sin frases (pedido del jefe, aprobado por la dueña,
2026-10-17).

Una fila de botones; cada uno es una comparación completa (A contra B):

1. ``ayer``: hoy contra ayer.
2. ``dia_mes_pasado``: hoy contra el mismo número de día del mes pasado (el 31 contra el último día del mes pasado; el
   29 o 30 de marzo, contra el último de febrero).
3. ``semana_pasada``: hoy contra el mismo día de la semana pasada (7 días atrás).
4. ``mes_a_la_fecha``: del 1 a hoy contra los mismos días del mes pasado (hasta su último día si es más corto).
5. ``mes``: lo que va del mes contra **un mes completo** que se elige (por defecto el pasado; los últimos 24). Arriba,
   un número grande: «Llevas 58 % de septiembre»; la última columna es «Llevas» (lo alcanzado de cada fila).
6. ``rango``: dos rangos libres. B es del mismo largo que A (solo se elige dónde empieza) salvo con «Libre». Si A y B
   no tienen los mismos días, el porcentaje es sobre el **promedio por día** («% por día»).

**Hasta la misma hora:** si A termina hoy, el día de hoy cuenta hasta la hora actual y el último día de B hasta la misma
hora de Panamá (``ventas_bases``: «lo que a esa hora ya estaba registrado»). En ``mes`` B es un mes completo: no se
corta.

Las filas salen de una sola función (``_filas_de_comparacion``) y siguen la base del interruptor (``facturado``,
``con_abonos`` o ``completadas``: las facturas de cliente, ``ventas_bases.py``) y la vendedora elegida: Ventas y
Ganancia (sin ITBMS, las mismas de las tarjetas del Inicio), Margen (ganancia ÷ venta de mercancía de esas mismas
facturas, el porcentaje que ya muestra la tarjeta de Ganancia; su cambio en puntos), N.º de ventas (facturas; una nota
de crédito resta del monto, no del número), Ticket promedio (ventas ÷ N.º de ventas; sin ventas, «—»; en «Mes», sin
«llevas»), Falta por cobrar (solo «Con abonos», con ITBMS) y Cobrado (con ITBMS). Sin base positiva no hay
porcentaje («—»): nunca se inventa uno.

Solo Gerencia y los administradores (los que ven la ganancia); el servidor lo exige en cada llamada.
"""
from datetime import date, datetime, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, UserError

from .tablero import BASE_CON_ABONOS, SIN_VENDEDORA

COMPARACIONES = ('ayer', 'dia_mes_pasado', 'semana_pasada', 'mes_a_la_fecha', 'mes', 'rango')
ZONA_PANAMA = 'America/Panama'
MESES_PARA_ELEGIR = 24
MAXIMO_DIAS = 366
MESES_CORTOS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')
MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre')
DIAS = ('Lun.', 'Mar.', 'Mié.', 'Jue.', 'Vie.', 'Sáb.', 'Dom.')


def _corta(dia, con_anio=False):
    """«17 oct» (y «17 oct 2025» si hace falta el año)."""
    texto = f'{dia.day} {MESES_CORTOS[dia.month - 1]}'
    return f'{texto} {dia.year}' if con_anio else texto


def _rango_texto(d0, d1, hoy):
    """«17 oct» · «1–17 oct» · «26 sep–2 oct» · con el año solo si no es el de hoy."""
    con_anio = d0.year != hoy.year or d1.year != hoy.year
    if d0 == d1:
        return _corta(d0, con_anio)
    if (d0.year, d0.month) == (d1.year, d1.month):
        return f'{d0.day}–{_corta(d1, con_anio)}'
    if d0.year == d1.year:
        return f'{_corta(d0)}–{_corta(d1, con_anio)}'
    return f'{_corta(d0, True)}–{_corta(d1, True)}'


def _mes_completo(dia, hoy):
    """«Sep completo» (y «Sep 2025 completo» si no es de este año)."""
    nombre = MESES_CORTOS[dia.month - 1].capitalize()
    return f'{nombre} completo' if dia.year == hoy.year else f'{nombre} {dia.year} completo'


def _nombre_del_mes(dia, hoy):
    """«septiembre» (y «septiembre de 2025» si no es de este año), para «Llevas 58 % de septiembre»."""
    return MESES[dia.month - 1] if dia.year == hoy.year else f'{MESES[dia.month - 1]} de {dia.year}'


def _fin_de_mes(dia):
    return dia + relativedelta(day=31)


def _hora(momento):
    """«11:05 a. m.» (hora de Panamá)."""
    hora12 = momento.hour % 12 or 12
    return f'{hora12}:{momento.minute:02d} {"a. m." if momento.hour < 12 else "p. m."}'


def _variacion(actual, antes):
    """Cuánto subió o bajó ``actual`` contra ``antes``, en %, con un decimal; sin base positiva, ``None``."""
    if actual is None or antes is None or antes <= 0:
        return None
    return round((actual - antes) / antes * 100, 1)


class DcasaTableroComparar(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    # ------------------------------------------------------------------
    # Reloj y permisos
    # ------------------------------------------------------------------

    @api.model
    def _ahora_en_panama(self):
        return pytz.utc.localize(fields.Datetime.now()).astimezone(pytz.timezone(ZONA_PANAMA))

    @api.model
    def _exigir_gerencia(self):
        if not self._ve_utilidad():
            raise AccessError(self.env._('Comparar las ventas es solo para Gerencia y los administradores.'))

    # ------------------------------------------------------------------
    # Las opciones de la pantalla (van con obtener_datos)
    # ------------------------------------------------------------------

    @api.model
    def _opciones_de_comparar(self, hoy=None):
        """Los botones con sus etiquetas de hoy, los meses que se pueden elegir y las vendedoras del selector."""
        hoy = hoy or self._ahora_en_panama().date()
        return {
            'hoy': str(hoy),
            'chips': self._chips_de_comparar(hoy),
            'meses': self._meses_para_elegir(hoy),
            'vendedoras': self._vendedoras_para_elegir(hoy),
        }

    @api.model
    def _chips_de_comparar(self, hoy):
        """«Ayer» · «17 sep» · «Sáb. 10 oct» · «1–17 sep» · «Mes» · «A vs B»."""
        dia_mes_pasado = hoy - relativedelta(months=1)
        semana = hoy - timedelta(days=7)
        b0, b1 = self._rangos_de_comparar('mes_a_la_fecha', hoy)['b']
        return [
            {'clave': 'ayer', 'etiqueta': self.env._('Ayer')},
            {'clave': 'dia_mes_pasado', 'etiqueta': _corta(dia_mes_pasado, dia_mes_pasado.year != hoy.year)},
            {'clave': 'semana_pasada', 'etiqueta': f'{DIAS[semana.weekday()]} {_corta(semana)}'},
            {'clave': 'mes_a_la_fecha', 'etiqueta': _rango_texto(b0, b1, hoy)},
            {'clave': 'mes', 'etiqueta': self.env._('Mes')},
            {'clave': 'rango', 'etiqueta': self.env._('A vs B')},
        ]

    @api.model
    def _meses_para_elegir(self, hoy):
        """Los últimos 24 meses completos, del más reciente al más viejo: ``[{'valor': '2026-09', 'nombre'}]``."""
        primero = hoy.replace(day=1)
        meses = []
        for atras in range(1, MESES_PARA_ELEGIR + 1):
            mes = primero - relativedelta(months=atras)
            meses.append({'valor': mes.strftime('%Y-%m'), 'nombre': f'{MESES[mes.month - 1].capitalize()} {mes.year}'})
        return meses

    @api.model
    def _vendedoras_para_elegir(self, hoy):
        """Quien tiene el rol Vendedora (Gerencia lo incluye: no por eso sale), quien tuvo ventas confirmadas en los
        últimos 24 meses y quien figura como «Vendedor» de una factura sin pedido de esos meses (su vendedora,
        ``ventas_bases._duenas``), por nombre; al final, «Sin vendedora» (ventas de la web o de Juan que nadie tomó, y
        facturas sin vendedor). Las notas de crédito no hacen vendedora a nadie: son de la vendedora de su factura y
        las hace solo Gerencia (su «Vendedor» suele ser quien la autorizó)."""
        ids = set()
        grupo = self.env.ref('dcasa_base.group_vendedora', raise_if_not_found=False)
        if grupo:
            ids |= set(grupo.sudo().all_user_ids.filtered(
                lambda u: u.active and not u.share and not u.has_group('sales_team.group_sale_manager')
                and not u.has_group('base.group_system')).ids)
        primero = hoy.replace(day=1) - relativedelta(months=MESES_PARA_ELEGIR)
        desde = datetime.combine(primero, datetime.min.time())
        grupos = self.env['sale.order']._read_group(
            [('state', '=', 'sale'), ('user_id', '!=', False), ('date_order', '>=', desde)], ['user_id'])
        ids |= {usuario.id for (usuario,) in grupos}
        if self._puede('account.move'):
            sin_pedido = self.env['account.move']._read_group(
                [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                 ('invoice_user_id', 'not in', (False, SUPERUSER_ID)), ('dcasa_historica', '=', False),
                 ('date', '>=', primero), ('line_ids', 'not any', [('sale_line_ids', '!=', False)])],
                ['invoice_user_id'])
            ids |= {usuario.id for (usuario,) in sin_pedido}
        usuarios = self.env['res.users'].sudo().with_context(active_test=False).browse(sorted(ids)).exists()
        filas = [{'id': u.id, 'nombre': u.name} for u in usuarios.sorted(lambda u: (u.name or '').lower())]
        return filas + [{'id': SIN_VENDEDORA, 'nombre': self.env._('Sin vendedora')}]

    # ------------------------------------------------------------------
    # A y B de cada botón
    # ------------------------------------------------------------------

    @api.model
    def _fecha(self, valor, cual):
        if valor in (None, False, ''):
            raise UserError(self.env._('Falta la fecha «%(cual)s».', cual=cual))
        try:
            dia = fields.Date.to_date(valor)
        except (TypeError, ValueError, OverflowError):
            dia = None
        if not dia:
            raise UserError(self.env._('Escribe las fechas completas, por ejemplo 2026-10-01.'))
        return dia

    @api.model
    def _mes_elegido(self, mes, hoy):
        """El primer día del mes elegido (``'2026-09'``); sin mes, el mes pasado. Solo uno de los últimos 24."""
        validos = {m['valor'] for m in self._meses_para_elegir(hoy)}
        if mes in (None, False, ''):
            mes = (hoy.replace(day=1) - relativedelta(months=1)).strftime('%Y-%m')
        if not isinstance(mes, str) or mes not in validos:
            raise UserError(self.env._('Elige uno de los últimos 24 meses.'))
        anio, numero = mes.split('-')
        return date(int(anio), int(numero), 1)

    @api.model
    def _rangos_de_comparar(self, comparacion, hoy, mes=None, a_desde=None, a_hasta=None, b_desde=None,
                            b_hasta=None, libre=False):
        """``{'a': (d0, d1), 'b': (d0, d1), 'modo', 'mes'}``. ``modo``: ``variacion`` (mismo largo), ``por_dia``
        (largos distintos: promedio por día) o ``llevas`` (contra un mes completo)."""
        if comparacion not in COMPARACIONES:
            raise UserError(self.env._('Elige una de las comparaciones.'))
        mes_elegido = None
        if comparacion == 'ayer':
            a = (hoy, hoy)
            b = (hoy - timedelta(days=1),) * 2
        elif comparacion == 'dia_mes_pasado':
            a = (hoy, hoy)
            b = (hoy - relativedelta(months=1),) * 2      # el 31 → el último día del mes pasado
        elif comparacion == 'semana_pasada':
            a = (hoy, hoy)
            b = (hoy - timedelta(days=7),) * 2
        elif comparacion == 'mes_a_la_fecha':
            a = (hoy.replace(day=1), hoy)
            inicio = hoy.replace(day=1) - relativedelta(months=1)
            b = (inicio, min(inicio + timedelta(days=hoy.day - 1), _fin_de_mes(inicio)))
        elif comparacion == 'mes':
            mes_elegido = self._mes_elegido(mes, hoy)
            a = (hoy.replace(day=1), hoy)
            b = (mes_elegido, _fin_de_mes(mes_elegido))
        else:
            a, b = self._rangos_libres(hoy, a_desde, a_hasta, b_desde, b_hasta, libre)
        dias_a, dias_b = (a[1] - a[0]).days + 1, (b[1] - b[0]).days + 1
        if comparacion == 'mes':
            modo = 'llevas'
        else:
            modo = 'variacion' if dias_a == dias_b else 'por_dia'
        return {'a': a, 'b': b, 'modo': modo, 'mes': mes_elegido, 'dias_a': dias_a, 'dias_b': dias_b}

    @api.model
    def _rangos_libres(self, hoy, a_desde, a_hasta, b_desde, b_hasta, libre):
        """«A vs B»: fechas no futuras, «desde» ≤ «hasta» y hasta un año por rango. Sin «Libre», B tiene el largo de A
        y solo se elige dónde empieza."""
        a0, a1 = self._fecha(a_desde, 'A desde'), self._fecha(a_hasta, 'A hasta')
        if a0 > a1:
            raise UserError(self.env._('Escribe un rango válido: «desde» no puede ser después de «hasta».'))
        if a1 > hoy:
            raise UserError(self.env._('Ese rango todavía no llega: elige fechas de hoy hacia atrás.'))
        if (a1 - a0).days + 1 > MAXIMO_DIAS:
            raise UserError(self.env._('Cada rango puede ser de hasta un año.'))
        b0 = self._fecha(b_desde, 'B desde')
        if libre:
            b1 = self._fecha(b_hasta, 'B hasta')
            if b0 > b1:
                raise UserError(self.env._('Escribe un rango válido: «desde» no puede ser después de «hasta».'))
            if (b1 - b0).days + 1 > MAXIMO_DIAS:
                raise UserError(self.env._('Cada rango puede ser de hasta un año.'))
        else:
            b1 = b0 + (a1 - a0)
        if b1 > hoy or b0 > hoy:
            raise UserError(self.env._('B no puede terminar después de hoy: empiézalo más atrás o usa «Libre».'))
        return (a0, a1), (b0, b1)

    # ------------------------------------------------------------------
    # La comparación
    # ------------------------------------------------------------------

    @api.model
    def comparar_ventas(self, comparacion, base=None, vendedor=None, mes=None, a_desde=None, a_hasta=None,
                        b_desde=None, b_hasta=None, libre=False, por_vendedora=False):
        """El bloque «Comparar» del Inicio de Gerencia. Solo lectura; exige Gerencia o administrador y valida todo
        (comparación, base, vendedora, mes, fechas y largo) antes de leer."""
        return self._comparar(comparacion, base=base, vendedor=vendedor, mes=mes, a_desde=a_desde, a_hasta=a_hasta,
                              b_desde=b_desde, b_hasta=b_hasta, libre=libre, por_vendedora=por_vendedora)

    @api.model
    def _comparar(self, comparacion, base=None, vendedor=None, mes=None, a_desde=None, a_hasta=None, b_desde=None,
                  b_hasta=None, libre=False, por_vendedora=False, ahora=None):
        """La comparación completa. ``ahora`` (hora de Panamá) solo lo pasan las pruebas: el reloj real manda."""
        self._exigir_gerencia()
        base = self._base_pedida(base)
        vendedor = self._vendedor_pedido(vendedor)
        zona = pytz.timezone(ZONA_PANAMA)
        if ahora is None:
            ahora = self._ahora_en_panama()
        elif ahora.tzinfo is None:
            ahora = zona.localize(ahora)
        else:
            ahora = ahora.astimezone(zona)
        hoy = ahora.date()
        rangos = self._rangos_de_comparar(comparacion, hoy, mes, a_desde, a_hasta, b_desde, b_hasta, libre is True)
        (a0, a1), (b0, b1) = rangos['a'], rangos['b']

        def en_utc(dia):
            return zona.localize(datetime.combine(dia, ahora.time())).astimezone(pytz.utc).replace(tzinfo=None)

        hasta_la_hora = a1 == hoy
        corte_a = en_utc(a1) if hasta_la_hora else None
        corte_b = en_utc(b1) if hasta_la_hora and comparacion != 'mes' else None
        con_cobrado = self._puede('account.payment')
        medida_a = self._medir(a0, a1, base, vendedor, corte_a, con_ganancia=True, con_cobrado=con_cobrado)
        medida_b = self._medir(b0, b1, base, vendedor, corte_b, con_ganancia=True, con_cobrado=con_cobrado)
        modo, dias_a, dias_b = rangos['modo'], rangos['dias_a'], rangos['dias_b']
        resultado = {
            'comparacion': comparacion, 'base': base, 'vendedor': vendedor, 'modo': modo,
            'a': {'etiqueta': _rango_texto(a0, a1, hoy), 'desde': str(a0), 'hasta': str(a1), 'dias': dias_a},
            'b': {'etiqueta': _mes_completo(b0, hoy) if comparacion == 'mes' else _rango_texto(b0, b1, hoy),
                  'desde': str(b0), 'hasta': str(b1), 'dias': dias_b},
            # La hora del corte, si A termina hoy («11:05 a. m.»).
            'hora': _hora(ahora) if hasta_la_hora else False,
            'filas': self._filas_de_comparacion(medida_a, medida_b, modo, base, dias_a, dias_b),
            'llevas': None,
            'por_vendedora': None,
        }
        if comparacion == 'mes':
            resultado['mes'] = rangos['mes'].strftime('%Y-%m')
            resultado['llevas'] = {
                'pct': self._cambio(medida_a['sin_itbms'], medida_b['sin_itbms'], 'llevas', dias_a, dias_b)['valor'],
                'mes': _nombre_del_mes(rangos['mes'], hoy),
            }
        if por_vendedora is True:
            if vendedor is None:
                equipo_a, equipo_b = medida_a, medida_b
            else:
                equipo_a = self._medir(a0, a1, base, None, corte_a)
                equipo_b = self._medir(b0, b1, base, None, corte_b)
            resultado['por_vendedora'] = self._lista_por_vendedora(equipo_a, equipo_b, modo, dias_a, dias_b)
        return resultado

    # ------------------------------------------------------------------
    # Las filas: una sola función para todas las bases
    # ------------------------------------------------------------------

    @api.model
    def _cambio(self, actual, antes, modo, dias_a, dias_b, tipo='pct', invertido=False):
        """El cambio de una fila: ``{'tipo', 'valor', 'sentido', 'invertido'}``.

        ``tipo``: ``pct`` (porcentaje; con ``por_dia``, sobre el promedio por día), ``pts`` (puntos, para el margen),
        ``num`` (diferencia, para el número de ventas con el mismo largo) o ``llevas`` (lo alcanzado del mes elegido).
        ``valor`` es ``None`` cuando no hay base positiva: la pantalla pone «—». ``invertido``: subir es malo (lo que
        falta por cobrar)."""
        valor = None
        if tipo == 'pts':
            if actual is not None and antes is not None:
                valor = round(actual - antes, 1)
        elif modo == 'llevas':
            tipo = 'llevas'
            if actual is not None and antes is not None and antes > 0:
                valor = round(actual / antes * 100, 1)
        elif tipo == 'num' and modo == 'variacion':
            if actual is not None and antes is not None:
                valor = actual - antes
        else:
            tipo = 'pct'
            if modo == 'por_dia' and actual is not None and antes is not None:
                valor = _variacion(actual / dias_a, antes / dias_b)
            else:
                valor = _variacion(actual, antes)
        if valor is None or tipo == 'llevas':
            sentido = None
        else:
            sentido = 'sube' if valor > 0 else ('baja' if valor < 0 else 'igual')
        return {'tipo': tipo, 'valor': valor, 'sentido': sentido, 'invertido': invertido}

    @staticmethod
    def _margen(ganancia):
        """Ganancia ÷ venta de mercancía de esas mismas ventas, en % (el de la tarjeta de Ganancia), sin redondear."""
        if not ganancia or not ganancia.get('neta') or ganancia['neta'] <= 0:
            return None
        return ganancia['valor'] / ganancia['neta'] * 100

    @api.model
    def _filas_de_comparacion(self, a, b, modo, base, dias_a, dias_b):
        """Las filas de la tabla, en orden, para cualquier base: Ventas, Ganancia, Margen, N.º de ventas, Ticket
        promedio, Falta por cobrar (solo «Con abonos») y Cobrado (si quien mira ve los cobros)."""
        filas = []

        def fila(clave, nombre, nota, formato, actual, antes, cambio):
            filas.append({'clave': clave, 'nombre': nombre, 'nota': nota, 'formato': formato,
                          'a': actual, 'b': antes, 'cambio': cambio})

        sin, con = self.env._('sin ITBMS'), self.env._('con ITBMS')
        fila('ventas', self.env._('Ventas'), sin, 'moneda', a['sin_itbms'], b['sin_itbms'],
             self._cambio(a['sin_itbms'], b['sin_itbms'], modo, dias_a, dias_b))
        ganancia_a = a['ganancia']['valor'] if a['ganancia'] else None
        ganancia_b = b['ganancia']['valor'] if b['ganancia'] else None
        fila('ganancia', self.env._('Ganancia'), sin, 'moneda', ganancia_a, ganancia_b,
             self._cambio(ganancia_a, ganancia_b, modo, dias_a, dias_b))
        margen_a, margen_b = self._margen(a['ganancia']), self._margen(b['ganancia'])
        fila('margen', self.env._('Margen'), None, 'porcentaje',
             None if margen_a is None else round(margen_a, 1), None if margen_b is None else round(margen_b, 1),
             self._cambio(margen_a, margen_b, modo, dias_a, dias_b, tipo='pts'))
        fila('cuantas', self.env._('N.º de ventas'), None, 'numero', a['cuantas'], b['cuantas'],
             self._cambio(a['cuantas'], b['cuantas'], modo, dias_a, dias_b, tipo='num'))
        # El ticket ya es un promedio por venta: con días distintos no se divide otra vez por día, y «llevas» de un
        # promedio no dice nada.
        cambio = self._cambio(a['ticket'], b['ticket'], 'variacion' if modo == 'por_dia' else modo, dias_a, dias_b)
        if modo == 'llevas':
            cambio = {'tipo': 'llevas', 'valor': None, 'sentido': None, 'invertido': False}
        fila('ticket', self.env._('Ticket promedio'), sin, 'moneda', a['ticket'], b['ticket'], cambio)
        if base == BASE_CON_ABONOS:
            cambio = self._cambio(a['falta_por_cobrar'], b['falta_por_cobrar'], modo, dias_a, dias_b, invertido=True)
            if modo == 'llevas':      # «llevas» de una deuda no dice nada
                cambio = {'tipo': 'llevas', 'valor': None, 'sentido': None, 'invertido': True}
            fila('falta', self.env._('Falta por cobrar'), con, 'moneda', a['falta_por_cobrar'], b['falta_por_cobrar'],
                 cambio)
        if a['cobrado'] is not None and b['cobrado'] is not None:
            fila('cobrado', self.env._('Cobrado'), con, 'moneda', a['cobrado'], b['cobrado'],
                 self._cambio(a['cobrado'], b['cobrado'], modo, dias_a, dias_b))
        return filas

    @api.model
    def _lista_por_vendedora(self, equipo_a, equipo_b, modo, dias_a, dias_b):
        """Una fila por vendedora (y «Sin vendedora»): ventas A, ventas B y el cambio, de mayor a menor en A."""
        suma_a = self._por_vendedora(equipo_a)
        suma_b = self._por_vendedora(equipo_b)
        claves = set(suma_a) | set(suma_b)
        ids = [clave for clave in claves if clave != SIN_VENDEDORA]
        nombres = {u.id: u.name for u in self.env['res.users'].sudo().with_context(active_test=False).browse(ids)}
        filas = []
        for clave in claves:
            actual, antes = suma_a[clave][1] if clave in suma_a else 0.0, suma_b[clave][1] if clave in suma_b else 0.0
            filas.append({
                'vendedor': clave,
                'nombre': self.env._('Sin vendedora') if clave == SIN_VENDEDORA else nombres.get(clave, ''),
                'a': round(actual, 2), 'b': round(antes, 2),
                'cambio': self._cambio(actual, antes, modo, dias_a, dias_b),
            })
        return sorted(filas, key=lambda f: (-f['a'], -f['b'], (f['nombre'] or '').lower()))
