"""Datos del tablero «Inicio»: cómo va el día en D'CASA, en una sola pantalla.

Cada cifra respeta los permisos de quien mira: si una vendedora no ve contabilidad,
su tablero simplemente no trae «Por cobrar». Nada se inventa: todo sale de la base.
Los accesos («Registrar cobro», «Nueva cotización»…) también: ``permisos`` dice cuáles
puede usar quien mira, y el Inicio solo muestra esos (UI-02).

Dos paneles según el rol (pedido de la dueña, 2026-10-14):

* **Completo** (Gerencia, administradores y contabilidad): las cifras de toda la tienda.
* **Propio** (quien vende pero no controla, p. ej. la Vendedora): solo lo que esa persona vendió hoy y sus
  cotizaciones abiertas. Sin lo que falta por cobrar, lo cobrado hoy, las barras ni los totales de la tienda.

«Vendido» siempre significa lo mismo: pedidos facturados por completo, con todas sus facturas publicadas
(``sale.order._dcasa_dominio_vendido``). Una cotización, un borrador o un pedido por facturar no es una venta. Encima de
eso, las tarjetas de Ventas y Ganancia de Gerencia siguen el interruptor «Completadas» / «Con abonos»
(``ventas_bases.py``, 2026-10-17) y el bloque «Comparar» pone periodos lado a lado (``comparar.py``).

ITBMS (decisión por mejor práctica contable, 2026-10-16): las ventas, el costo y la ganancia se miden **sin ITBMS**
(es un impuesto de la DGI, no ingreso ni costo); el dinero que se mueve (por cobrar, cobrado) va **con** ITBMS. Cada
cifra de ventas trae sus tres números (sin ITBMS · ITBMS · total) y la etiqueta dice cuál es cuál.

La ganancia (``dcasa_base/models/utilidad.py``) solo la ven Gerencia y los administradores.
"""
import base64
from datetime import datetime, time, timedelta

import pytz
from babel.dates import format_date

from odoo import api, fields, models
from odoo.exceptions import UserError

DIAS_CORTOS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']
APPS_SIN_PAGO = "[('to_buy', '=', False)]"
PERIODOS = ('hoy', 'semana', 'mes', 'rango')
MAXIMO_DIAS_DE_RANGO = 366
PARAM_STOCK_BAJO = 'dcasa.stock_bajo_umbral'
STOCK_BAJO_DEFECTO = 5
FILAS_DE_LISTA = 5
# Las bases de las ventas (``ventas_bases.py``): la de siempre y las dos del interruptor del Inicio de Gerencia.
BASE_VENDIDO = 'vendido'
BASE_COMPLETADAS = 'completadas'
BASE_CON_ABONOS = 'con_abonos'
BASES_DE_GERENCIA = (BASE_COMPLETADAS, BASE_CON_ABONOS)
SIN_VENDEDORA = 'sin'


def _accion(nombre, modelo, dominio, vista='list'):
    """Lo que el tablero abre al tocar una cifra."""
    return {'name': nombre, 'res_model': modelo, 'domain': dominio, 'vista': vista}


class DcasaTablero(models.AbstractModel):
    _name = 'dcasa.tablero'
    _description = "Tablero de inicio de D'CASA"

    # ------------------------------------------------------------------
    # Fechas en hora de Panamá
    # ------------------------------------------------------------------

    def _zona(self):
        return pytz.timezone(self.env.user.tz or 'America/Panama')

    def _limites_del_dia(self, dia):
        """Inicio y fin de un día de Panamá, en UTC sin zona (como guarda Odoo)."""
        zona = self._zona()
        inicio = zona.localize(datetime.combine(dia, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        return inicio, inicio + timedelta(days=1)

    def _puede(self, modelo, operacion='read'):
        return self.env[modelo].has_access(operacion)

    def _es_gerencia(self):
        """Quien controla la tienda y ve el panel completo: Gerencia (ventas administrador), contabilidad
        (Gerencia la incluye) y los administradores técnicos."""
        usuario = self.env.user
        return any(usuario.has_group(grupo) for grupo in
                   ('sales_team.group_sale_manager', 'account.group_account_readonly', 'base.group_system'))

    def _solo_lo_propio(self):
        """Quien vende (tiene Ventas) pero no controla la tienda: su Inicio trae solo lo suyo."""
        return self._puede('sale.order') and not self._es_gerencia()

    def _permisos(self, propio=False):
        """Qué accesos y paneles del Inicio puede usar quien mira.

        ``propio``: el panel de quien vende sin controlar. Ahí no hay cobros ni «Registrar cobro», ni «Nueva
        cotización», ni «Ver la tienda»: solo las herramientas del día (UI-02, 2026-10-14). Caja (rol D'CASA, ve y
        cobra lo de toda la tienda) sí tiene «Registrar cobro», «Cobros de hoy» y «Por cobrar», pero sigue sin el
        panel completo ni la ganancia (2026-10-17).
        """
        caja = self.env.user.has_group('dcasa_base.group_caja')
        return {
            'cotizar': self._puede('sale.order', 'create'),
            'crear_cliente': self._puede('res.partner', 'create'),
            'facturar': self._puede('account.move', 'create'),
            # Registrar un cobro exige Facturación (ACL de account.payment).
            'cobrar': (not propio or caja) and self._puede('account.payment', 'create'),
            'ver_cobros': (not propio or caja) and self._puede('account.payment'),
            'catalogo': self._puede('product.template'),
            # El panel completo de la tienda (cifras de todos, barras, lo más vendido) y los botones de la dueña.
            'completo': not propio,
        }

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------

    def _atajos(self, permisos):
        """Los accesos grandes del Inicio, en este orden: Productos, Facturas, Conversaciones, Escáner, Oportunidades
        y Resumen contable.

        Solo los que quien mira puede abrir. Conversaciones, Oportunidades y el Resumen contable viven en otros
        módulos: si no están instalados (o la persona no tiene permiso) simplemente no salen. ``vista`` es la vista
        con la que abre. Productos es la lista donde se ordena y filtra por stock, precio y categoría
        (dcasa_catalogo): marketing arma ahí las campañas. Facturas es la lista de facturas a clientes (la misma de
        Facturación › Clientes › Facturas). Quien vende sin controlar (``permisos['completo']`` en falso) tiene solo
        Productos, Facturas, Conversaciones y Escáner; Oportunidades y el Resumen contable son de quien controla la
        tienda.
        """
        atajos = []
        if permisos['catalogo'] and self.env.ref('sale.product_template_action', raise_if_not_found=False):
            atajos.append({
                'clave': 'productos', 'titulo': 'Productos', 'detalle': 'Stock, precio y categoría',
                'icono': 'fa-th-large', 'accion': 'sale.product_template_action', 'vista': 'list'})
        if self._puede('account.move') and self.env.ref('account.action_move_out_invoice_type',
                                                        raise_if_not_found=False):
            atajos.append({
                'clave': 'facturas', 'titulo': 'Facturas', 'detalle': 'Las que ya emitiste',
                'icono': 'fa-file-text-o', 'accion': 'account.action_move_out_invoice_type', 'vista': 'list'})
        conversaciones = self.env.get('dcasa.conversacion')
        if conversaciones is not None and conversaciones.has_access('read') \
                and self.env.ref('dcasa_conversaciones.accion_conversaciones', raise_if_not_found=False):
            sin_leer = len(conversaciones._ids_con_sin_leer())
            atajos.append({
                'clave': 'conversaciones', 'titulo': 'Conversaciones',
                'detalle': 'Todo al día' if not sin_leer else f'{sin_leer} sin leer',
                'icono': 'fa-comments', 'accion': 'dcasa_conversaciones.accion_conversaciones', 'vista': None,
                'cuenta': sin_leer})
        # El Escáner (dcasa_barras) es para todos los que mueven mercancía: el mismo permiso que su menú de Inventario.
        # Vive en otro módulo: si no está instalado, simplemente no sale.
        if self.env.user.has_group('stock.group_stock_user') \
                and self.env.ref('dcasa_barras.accion_escaner', raise_if_not_found=False):
            atajos.append({
                'clave': 'escaner', 'titulo': 'Escáner', 'detalle': 'Lee un código de barras o QR',
                'icono': 'fa-barcode', 'accion': 'dcasa_barras.accion_escaner', 'vista': None})
        if not permisos['completo']:
            return atajos
        oportunidades = self.env.get('crm.lead')
        if oportunidades is not None and 'dcasa_temperatura' in oportunidades._fields \
                and oportunidades.has_access('read') \
                and self.env.ref('dcasa_conversaciones.accion_oportunidades_hoy', raise_if_not_found=False):
            para_hoy = oportunidades.search_count([('dcasa_para_hoy', '=', True)])
            atajos.append({
                'clave': 'oportunidades', 'titulo': 'Oportunidades',
                'detalle': 'Nadie por ahora' if not para_hoy else
                           ('1 para escribirle hoy' if para_hoy == 1 else f'{para_hoy} para escribirles hoy'),
                'icono': 'fa-fire', 'accion': 'dcasa_conversaciones.accion_oportunidades_hoy', 'vista': None,
                'cuenta': para_hoy})
        # El mismo permiso que el menú Facturación › Reportes contables (contabilidad, Gerencia, administradores).
        if self.env.user.has_group('account.group_account_readonly') \
                and self.env.ref('dcasa_contabilidad.accion_resumen', raise_if_not_found=False):
            atajos.append({
                'clave': 'resumen_contable', 'titulo': 'Resumen contable', 'detalle': 'Dinero, deudas y utilidad',
                'icono': 'fa-line-chart', 'accion': 'dcasa_contabilidad.accion_resumen', 'vista': None})
        return atajos

    def _ve_utilidad(self):
        """Los costos son sensibles: la ganancia la ven solo Gerencia y los administradores."""
        usuario = self.env.user
        return usuario.has_group('sales_team.group_sale_manager') or usuario.has_group('base.group_system')

    @api.model
    def obtener_datos(self):
        hoy = fields.Date.context_today(self)
        moneda = self.env.company.currency_id
        propio = self._solo_lo_propio()
        datos = {
            'saludo': (self.env.user.name or '').split(' ')[0],
            'fecha': format_date(hoy, "EEEE d 'de' MMMM", locale='es'),
            'moneda': {'simbolo': moneda.symbol, 'antes': moneda.position == 'before'},
            # «tienda»: las cifras de todos; «propio»: solo lo que vendió quien mira.
            'alcance': 'propio' if propio else 'tienda',
            'cifras': [],
            'cobros': [],
            'total_cobrado': 0.0,
            'semana': [],
            'top': [],
            'ventas': None,
            'cotizaciones': None,
            'entregas': None,
            'atencion': [],
            'meta': None,
            've_utilidad': False,
            'bases': [],
            'comparar': None,
            'permisos': self._permisos(propio),
            # La Guía («¿Qué necesitas hacer hoy?») vive en otro módulo: si no está instalado, no hay botón.
            'guia': bool(self.env.ref('dcasa_guia.accion_guia', raise_if_not_found=False)),
        }
        datos['atajos'] = self._atajos(datos['permisos'])
        datos['meta'] = self._meta_del_mes(hoy)
        if self._puede('sale.order'):
            self._cifras_de_ventas(datos, hoy, propio)
            if not propio:
                datos['ve_utilidad'] = self._ve_utilidad()
                # El interruptor «Completadas» / «Con abonos» (abre en «Completadas»).
                datos['bases'] = self._bases_de_ventas()
                datos['ventas'] = self.ventas_del_periodo('hoy')
                datos['cotizaciones'] = self._lista_de_cotizaciones(hoy)
                # El bloque «Comparar» y el selector de vendedora: solo Gerencia y administradores.
                if datos['ve_utilidad']:
                    datos['comparar'] = self._opciones_de_comparar()
        # Lo que quien vende sin controlar no ve: lo cobrado y lo por cobrar, las entregas y los socios.
        if datos['permisos']['ver_cobros']:
            self._cobros_de_hoy(datos, hoy)
            # Sin acceso a cobros, «Por cobrar» saldría de las pocas facturas que deja ver Ventas
            # (las propias): una cifra parcial que parece total. Mejor no mostrarla.
            if self._puede('account.move'):
                self._por_cobrar(datos)
        if not propio and self._puede('stock.picking'):
            self._entregas(datos, hoy)
        if not propio and self._puede('res.partner'):
            self._socios(datos, hoy)
        if not propio:
            self._atencion(datos, hoy)
        return datos

    def _meta_del_mes(self, hoy):
        """«Tu meta del mes» de quien mira, si participa en el bono por meta de ventas (departamento de Ventas).
        Solo sus cifras, nunca las de la tienda. Vive en Nómina (``dcasa.nomina.meta.bono``): sin ese módulo, no
        sale."""
        Bono = self.env.get('dcasa.nomina.meta.bono')
        if Bono is None:
            return None
        return Bono._para_inicio(self.env.user, hoy)

    # ------------------------------------------------------------------
    # Ventas por periodo (Hoy · Semana · Mes · rango)
    # ------------------------------------------------------------------

    @api.model
    def _rango_del_periodo(self, periodo, desde=None, hasta=None, hoy=None):
        """Los días del periodo, ambos incluidos: hoy, la semana (de lunes a hoy), el mes (del 1 a hoy) o un rango de
        hasta un año (que no pasa de hoy). Las comparaciones viven aparte, en el bloque «Comparar» (``comparar.py``)."""
        hoy = hoy or fields.Date.context_today(self)
        if periodo not in PERIODOS:
            raise UserError(self.env._('Elige Hoy, Esta semana, Este mes o un rango de fechas.'))
        if periodo == 'hoy':
            d0 = d1 = hoy
            etiqueta = 'Hoy'
        elif periodo == 'semana':
            d0, d1 = hoy - timedelta(days=hoy.weekday()), hoy
            etiqueta = 'Esta semana'
        elif periodo == 'mes':
            d0, d1 = hoy.replace(day=1), hoy
            etiqueta = 'Este mes'
        else:
            try:
                d0, d1 = fields.Date.to_date(desde), fields.Date.to_date(hasta)
            except (TypeError, ValueError, OverflowError):
                raise UserError(self.env._('Escribe las fechas completas, por ejemplo 2026-10-01.')) from None
            if not d0 or not d1 or d0 > d1:
                raise UserError(self.env._('Escribe un rango válido: «desde» no puede ser después de «hasta».'))
            if d0 > hoy:
                raise UserError(self.env._('Ese rango todavía no llega: elige fechas de hoy hacia atrás.'))
            if (d1 - d0).days + 1 > MAXIMO_DIAS_DE_RANGO:
                raise UserError(self.env._('El rango puede ser de hasta un año.'))
            d1 = min(d1, hoy)
            d0 = min(d0, d1)
            etiqueta = f'Del {format_date(d0, "d MMM", locale="es")} al {format_date(d1, "d MMM", locale="es")}'
        return {'periodo': periodo, 'desde': d0, 'hasta': d1, 'etiqueta': etiqueta}

    def _totales_de_ventas(self, d0, d1, vendedor=None, con_ganancia=False):
        """Lo vendido entre dos días (la base de siempre: facturado por completo, el día de su última factura): las
        tres cifras (sin ITBMS · ITBMS · total) y, si se pide, la ganancia. Sale de ``_medir`` (``ventas_bases``), el
        mismo cálculo del Inicio de Gerencia y del bloque «Comparar»."""
        medida = self._medir(d0, d1, BASE_VENDIDO, vendedor, con_ganancia=con_ganancia)
        return {clave: medida[clave] for clave in ('cuantas', 'sin_itbms', 'itbms', 'total', 'ganancia')}

    def _ganancia_de(self, dominio):
        """La ganancia de las ventas del dominio: venta neta menos costo, sin ITBMS.

        Un pedido con mercancía sin costo cargado no inventa ganancia: queda fuera y se cuenta aparte."""
        Order = self.env['sale.order'].sudo()
        con_costo = Order._read_group(dominio + [('dcasa_sin_costo', '=', False)], [],
                                      ['dcasa_utilidad:sum', 'dcasa_venta_neta:sum', '__count'])
        utilidad, neta, cuantas = con_costo[0] if con_costo else (0.0, 0.0, 0)
        return {
            'valor': utilidad or 0.0,
            'porcentaje': round((utilidad or 0.0) / neta * 100, 1) if neta else None,
            # La venta de mercancía de esas mismas ventas: el margen sin redondear (Comparar lo da en puntos).
            'neta': neta or 0.0,
            'ventas_con_costo': cuantas or 0,
            'ventas_sin_costo': Order.search_count(dominio + [('dcasa_sin_costo', '=', True)]),
        }

    @api.model
    def ventas_del_periodo(self, periodo='hoy', desde=None, hasta=None, base=None, vendedor=None):
        """La tarjeta de ventas del Inicio para un periodo y (solo Gerencia) la ganancia.

        * Quien vende sin controlar (la Vendedora) ve solo lo que vendió ella misma, con la base de siempre (lo
          facturado por completo, el día de la factura) y sin ganancia. No elige base ni vendedora: un ``vendedor``
          ajeno se rechaza (``AccessError``).
        * El panel completo cuenta según el interruptor ``base``: ``completadas`` (por defecto: pagadas al 100 %, el
          día del último pago) o ``con_abonos`` (con al menos un abono, por su valor total, el día de la venta; trae
          ``falta_por_cobrar``). Gerencia y los administradores pueden filtrar por ``vendedor`` (id o ``'sin'``).

        La lista que abre la cifra (``accion``) es exactamente el mismo conjunto de pedidos."""
        if not self._puede('sale.order'):
            return None
        propio = self._solo_lo_propio()
        filtro = self._vendedor_pedido(vendedor)
        if propio:
            base, filtro = BASE_VENDIDO, self.env.uid
        else:
            base = self._base_pedida(base)
        rango = self._rango_del_periodo(periodo, desde, hasta)
        d0, d1 = rango['desde'], rango['hasta']
        con_ganancia = not propio and self._ve_utilidad()
        medida = self._medir(d0, d1, base, filtro, con_ganancia=con_ganancia)
        pedidos = medida.pop('pedidos')
        Order = self.env['sale.order']
        if base == BASE_VENDIDO:
            dominio = Order._dcasa_dominio_vendido(desde=d0, hasta=d1, vendedor=filtro)
        else:
            dominio = [('id', 'in', pedidos.ids)]
        nombre = {BASE_COMPLETADAS: 'Ventas completadas', BASE_CON_ABONOS: 'Ventas con abonos'}.get(base, 'Ventas')
        if filtro and not propio:
            nombre += ' · ' + (self.env._('Sin vendedora') if filtro == SIN_VENDEDORA
                               else self.env['res.users'].sudo().browse(filtro).name)
        return {
            'base': base,
            'vendedor': None if propio else filtro,
            # En qué se aparta de las «Ventas» de Contabilidad (quien controla y ve la contabilidad; todo el equipo).
            'cuadre': None if (propio or filtro) else self._cuadre_con_contabilidad(d0, d1, medida['sin_itbms'],
                                                                                   pedidos),
            'periodo': rango['periodo'], 'etiqueta': rango['etiqueta'],
            'desde': str(d0), 'hasta': str(d1),
            'actual': medida,
            'accion': _accion(f'{nombre} · {rango["etiqueta"]}', 'sale.order', dominio),
        }

    def _cuadre_con_contabilidad(self, d0, d1, vendido_sin_itbms, pedidos):
        """En qué se aparta lo que cuenta el Inicio de las «Ventas» de Contabilidad para esas fechas, y qué facturas lo
        explican (capturas de la dueña, 2026-10-16: $1,301.04 en el Inicio contra $1,522.42 en Contabilidad; la
        diferencia era una factura sin pedido).

        Las dos pantallas miden distinto a propósito: el Inicio cuenta **ventas** (``pedidos``: el pedido completo, el
        día que dice el interruptor: el del último pago en «Completadas», el de la venta en «Con abonos»);
        Contabilidad, los **apuntes de ingresos** con fecha en el periodo. Se apartan por:

        * facturas con fecha en el periodo que el Inicio no cuenta aquí: sin pedido, de pedidos aún no facturados por
          completo, sin pago o todavía sin pagar completas;
        * facturas de otras fechas de ventas que el Inicio sí cuenta aquí, como el abono de un apartado o la factura de
          una venta que se terminó de pagar en el periodo.

        ``diferencia`` es la resta exacta (Contabilidad − Inicio), con su signo; la lista trae las facturas de esos dos
        grupos para revisarlas. ``None`` si cuadran o si quien mira no ve la contabilidad.
        """
        if not self._puede('account.move.line'):
            return None
        ingresos = self.env['account.move.line']._read_group(
            [('parent_state', '=', 'posted'), ('account_id.account_type', '=', 'income'),
             ('date', '>=', fields.Date.to_string(d0)), ('date', '<=', fields.Date.to_string(d1)),
             ('company_id', 'in', self.env.companies.ids)], [], ['balance:sum'])
        contables = -(ingresos[0][0] or 0.0) if ingresos else 0.0
        diferencia = round(contables - vendido_sin_itbms, 2)
        if abs(diferencia) < 0.01:
            return None
        de_una_venta = [('sale_line_ids', 'any', [('order_id', 'in', pedidos.ids)])]
        desde, hasta = fields.Date.to_string(d0), fields.Date.to_string(d1)
        dominio = [
            ('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted'),
            ('company_id', 'in', self.env.companies.ids),
            '|',
            '&', '&', ('date', '>=', desde), ('date', '<=', hasta), ('invoice_line_ids', 'not any', de_una_venta),
            '&', '|', ('date', '<', desde), ('date', '>', hasta), ('invoice_line_ids', 'any', de_una_venta),
        ]
        vista = self.env.ref('account.view_out_invoice_tree', raise_if_not_found=False)
        return {
            'contables': contables,
            'diferencia': diferencia,
            'cuantas': self.env['account.move'].search_count(dominio),
            'accion': {**_accion('Facturas que explican la diferencia con Contabilidad', 'account.move', dominio),
                       'vista_lista': vista.id if vista else False},
        }

    # ------------------------------------------------------------------
    # Cotizaciones abiertas y entregas pendientes: las dos listas lado a lado
    # ------------------------------------------------------------------

    def _lista_de_cotizaciones(self, hoy):
        """Las cotizaciones abiertas de la tienda (no las de la web), con las más antiguas primero para cerrarlas."""
        Order = self.env['sale.order']
        abiertas = [('state', 'in', ('draft', 'sent')), ('website_id', '=', False)]
        total = Order.search_read(abiertas, ['amount_untaxed', 'amount_total'])
        filas = Order.search_read(abiertas, ['name', 'partner_id', 'amount_total', 'user_id', 'date_order'],
                                  order='date_order asc, id asc', limit=FILAS_DE_LISTA)
        return {
            'cantidad': len(total),
            'sin_itbms': sum(o['amount_untaxed'] for o in total),
            'total': sum(o['amount_total'] for o in total),
            'accion': _accion('Cotizaciones abiertas', 'sale.order', abiertas),
            'filas': [{
                'id': o['id'], 'nombre': o['name'], 'cliente': o['partner_id'] and o['partner_id'][1] or '',
                'total': o['amount_total'], 'vendedora': o['user_id'] and o['user_id'][1] or '',
                'dias': max((hoy - fields.Datetime.context_timestamp(self, o['date_order']).date()).days, 0)
                if o['date_order'] else 0,
            } for o in filas],
        }

    def _cifras_de_ventas(self, datos, hoy, propio=False):
        """Las cifras de ventas. «Vendido» = pedidos facturados por completo (``_dcasa_dominio_vendido``), contados
        en el día de su última factura: la tarjeta, la lista que abre, las barras y «lo más vendido» salen todos de
        ese mismo dominio. ``propio``: solo los pedidos de quien mira (y nada de barras ni totales de la tienda).

        El valor de las ventas es **sin ITBMS**; el ITBMS y el total van aparte en la misma cifra."""
        Order = self.env['sale.order']
        vendedor = self.env.uid if propio else None
        # Una sola lectura para «Vendido hoy» y las barras de la semana. El día de la venta ya es una fecha de
        # Panamá (la de la factura): no hay conversión de horas.
        ventas = Order.search_read(
            Order._dcasa_dominio_vendido(desde=hoy if propio else hoy - timedelta(days=6), hasta=hoy,
                                         vendedor=vendedor),
            ['dcasa_fecha_venta', 'amount_untaxed', 'amount_tax', 'amount_total'])
        por_dia = {}
        for venta in ventas:
            cuenta, base, itbms, total = por_dia.get(venta['dcasa_fecha_venta'], (0, 0.0, 0.0, 0.0))
            por_dia[venta['dcasa_fecha_venta']] = (cuenta + 1, base + venta['amount_untaxed'],
                                                   itbms + venta['amount_tax'], total + venta['amount_total'])
        cuantas, base, itbms, total = por_dia.get(hoy, (0, 0.0, 0.0, 0.0))
        datos['cifras'].append({
            'clave': 'ventas_hoy', 'titulo': 'Vendido hoy', 'valor': base, 'formato': 'moneda',
            'nota': 'sin ITBMS', 'itbms': itbms, 'total_con_itbms': total,
            'detalle': f'{cuantas} venta' + (('' if cuantas == 1 else 's') if not propio else
                                             (' tuya' if cuantas == 1 else 's tuyas')),
            'accion': _accion('Ventas de hoy', 'sale.order',
                              Order._dcasa_dominio_vendido(desde=hoy, hasta=hoy, vendedor=vendedor)),
        })

        abiertas = [('state', 'in', ('draft', 'sent')), ('website_id', '=', False)]
        if propio:
            # Solo las suyas: las que le toca seguir por WhatsApp. Nada más de la tienda.
            mias = Order.search_read(abiertas + [('user_id', '=', self.env.uid)], ['amount_total'])
            datos['cifras'].append(self._cifra_mis_cotizaciones(abiertas, mias))
            return
        cotizaciones = Order.search_read(abiertas, ['amount_total', 'user_id'])
        datos['cifras'].append({
            'clave': 'cotizaciones', 'titulo': 'Cotizaciones abiertas', 'valor': len(cotizaciones),
            'formato': 'numero', 'detalle_moneda': sum(c['amount_total'] for c in cotizaciones),
            'accion': _accion('Cotizaciones abiertas', 'sale.order', abiertas),
        })
        # Quien controla Ventas ya tiene el total de la tienda en la tarjeta anterior; si vende sin ser
        # administrador de Ventas (p. ej. contabilidad), ve aparte las suyas.
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            mias = [c for c in cotizaciones if c['user_id'] and c['user_id'][0] == self.env.uid]
            datos['cifras'].append(self._cifra_mis_cotizaciones(abiertas, mias))
        # Decisión 10 de la dueña (2026-10-16): el título dice qué es, sin jerga («por atender»).
        web = [('website_id', '!=', False), ('state', '=', 'sale'), ('delivery_status', '!=', 'full')]
        datos['cifras'].append({
            'clave': 'web', 'titulo': 'Compraron en la web y aún no se entregan', 'valor': Order.search_count(web),
            'formato': 'numero', 'detalle': 'Pedidos confirmados de la tienda en línea',
            'accion': _accion('Compraron en la web y aún no se entregan', 'sale.order', web),
        })
        self._barras_y_lo_mas_vendido(datos, hoy, por_dia)

    def _cifra_mis_cotizaciones(self, abiertas, mias):
        return {
            'clave': 'mis_cotizaciones', 'titulo': 'Mis cotizaciones', 'valor': len(mias),
            'formato': 'numero', 'detalle_moneda': sum(c['amount_total'] for c in mias),
            'accion': _accion('Mis cotizaciones abiertas', 'sale.order', abiertas + [('user_id', '=', self.env.uid)]),
        }

    def _barras_y_lo_mas_vendido(self, datos, hoy, por_dia):
        """Las barras de los últimos 7 días (sin ITBMS) y lo más vendido del mes (solo en el panel de la tienda)."""
        for atras in range(6, -1, -1):
            dia = hoy - timedelta(days=atras)
            dia_total = por_dia.get(dia, (0, 0.0, 0.0, 0.0))
            datos['semana'].append({'dia': DIAS_CORTOS[dia.weekday()], 'monto': dia_total[1],
                                    'total': dia_total[3], 'hoy': atras == 0})
        # Las líneas de las ventas de los últimos 30 días: el mismo dominio de «vendido», visto desde la línea.
        vendido = self.env['sale.order']._dcasa_dominio_vendido(desde=hoy - timedelta(days=30), hasta=hoy)
        lineas = self.env['sale.order.line']._read_group(
            [(f'order_id.{campo}', operador, valor) for campo, operador, valor in vendido]
            + [('product_id.type', '!=', 'service'), ('is_downpayment', '=', False)],
            ['product_id'], ['product_uom_qty:sum'])
        por_plantilla = {}
        for producto, cantidad in lineas:
            if producto:
                por_plantilla[producto.product_tmpl_id] = por_plantilla.get(producto.product_tmpl_id, 0) + cantidad
        for plantilla, cantidad in sorted(por_plantilla.items(), key=lambda pc: -pc[1])[:5]:
            datos['top'].append({
                'id': plantilla.id, 'nombre': plantilla.name, 'cantidad': int(cantidad),
                'imagen': f'/web/image/product.template/{plantilla.id}/image_128',
            })

    def _cobros_de_hoy(self, datos, hoy):
        """Lo cobrado hoy por forma de pago (con ITBMS: es el dinero que entró). Va en «Caja de hoy»."""
        dominio = self._dominio_de_cobros(hoy, hoy)
        grupos = self.env['account.payment']._read_group(dominio, ['journal_id'], ['amount:sum'])
        for diario, monto in grupos:
            if diario:
                datos['cobros'].append({'forma': diario.display_name, 'monto': monto})
        datos['total_cobrado'] = sum(c['monto'] for c in datos['cobros'])
        datos['accion_cobros'] = _accion('Cobros de hoy', 'account.payment', dominio)

    def _por_cobrar(self, datos):
        dominio = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                   ('payment_state', 'in', ('not_paid', 'partial'))]
        facturas = self.env['account.move'].search_read(dominio, ['amount_residual'])
        datos['cifras'].append({
            'clave': 'por_cobrar', 'titulo': 'Por cobrar', 'valor': sum(f['amount_residual'] for f in facturas),
            'formato': 'moneda', 'nota': 'con ITBMS',
            'detalle': f'{len(facturas)} factura' + ('' if len(facturas) == 1 else 's'),
            'accion': _accion('Facturas por cobrar', 'account.move', dominio),
        })

    def _entregas(self, datos, hoy):
        """Entregas por despachar o retirar: la cifra y la lista de las más antiguas, para entregarlas en orden."""
        Picking = self.env['stock.picking']
        dominio = [('picking_type_code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'waiting', 'assigned'))]
        cantidad = Picking.search_count(dominio)
        datos['cifras'].append({
            'clave': 'entregas', 'titulo': 'Entregas pendientes', 'valor': cantidad,
            'formato': 'numero', 'detalle': 'Por despachar o retirar',
            'accion': _accion('Entregas pendientes', 'stock.picking', dominio),
        })
        filas = Picking.search_read(dominio, ['name', 'partner_id', 'origin', 'scheduled_date', 'state'],
                                    order='scheduled_date asc, id asc', limit=FILAS_DE_LISTA)
        datos['entregas'] = {
            'cantidad': cantidad,
            'accion': _accion('Entregas pendientes', 'stock.picking', dominio),
            'filas': [{
                'id': p['id'], 'nombre': p['name'], 'cliente': p['partner_id'] and p['partner_id'][1] or '',
                'origen': p['origin'] or '', 'listo': p['state'] == 'assigned',
                'dias': max((hoy - fields.Datetime.context_timestamp(self, p['scheduled_date']).date()).days, 0)
                if p['scheduled_date'] else 0,
            } for p in filas],
        }

    def _umbral_de_stock_bajo(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_STOCK_BAJO, STOCK_BAJO_DEFECTO)
        try:
            return max(int(float(valor)), 0)
        except (TypeError, ValueError):
            return STOCK_BAJO_DEFECTO

    def _atencion(self, datos, hoy):
        """La franja de avisos: lo que conviene mirar hoy. Solo lo que quien mira puede abrir."""
        avisos = datos['atencion']
        if self._puede('product.product'):
            Producto = self.env['product.product']
            umbral = self._umbral_de_stock_bajo()
            bajo = [('is_storable', '=', True), ('sale_ok', '=', True), ('qty_available', '<=', umbral)]
            cuantos = Producto.search_count(bajo)
            if cuantos:
                avisos.append({
                    'clave': 'stock_bajo', 'icono': 'fa-exclamation-triangle', 'cuenta': cuantos,
                    'texto': f'{cuantos} producto' + (' se está' if cuantos == 1 else 's se están')
                             + f' agotando ({umbral} unidades o menos)',
                    'accion': _accion('Productos por agotarse', 'product.product', bajo)})
        if self._puede('sale.order'):
            # Pedidos confirmados que parecen la misma venta (mismo cliente, día y total): uno sobra y engorda los
            # pedidos (capturas de la dueña, 2026-10-16).
            repetidos = self.env['sale.order']._dcasa_pedidos_repetidos(hoy - timedelta(days=30))
            if repetidos:
                cuantos = len(repetidos)
                avisos.append({
                    'clave': 'pedidos_repetidos', 'icono': 'fa-clone', 'cuenta': cuantos,
                    'texto': f'{cuantos} pedidos parecen repetidos (mismo cliente, mismo día y mismo total): '
                             'revisa si alguno sobra',
                    'accion': _accion('Pedidos que parecen repetidos', 'sale.order', [('id', 'in', repetidos.ids)])})
        if datos['ve_utilidad']:
            Producto = self.env['product.product']
            # Toda la mercancía (no solo la que lleva inventario): es la misma que deja una venta fuera de la ganancia.
            sin_costo = [('type', '=', 'consu'), ('sale_ok', '=', True), ('standard_price', '<=', 0)]
            cuantos = Producto.search_count(sin_costo)
            if cuantos:
                avisos.append({
                    'clave': 'productos_sin_costo', 'icono': 'fa-tag', 'cuenta': cuantos,
                    'texto': f'{cuantos} producto' + (' vendible no tiene' if cuantos == 1 else 's vendibles no tienen')
                             + ' costo cargado: sus ventas no cuentan en la ganancia',
                    'accion': _accion('Productos sin costo', 'product.product', sin_costo)})

    def _socios(self, datos, hoy):
        Partner = self.env['res.partner']
        socios = [('dcasa_socio_codigo', '!=', False)]
        semana = socios + [('create_date', '>=', fields.Datetime.to_datetime(hoy - timedelta(days=7)))]
        nuevos = Partner.search_count(semana)
        datos['cifras'].append({
            'clave': 'socios', 'titulo': "Socios D'CASA", 'valor': Partner.search_count(socios),
            'formato': 'numero', 'detalle': f'{nuevos} nuevo' + ('' if nuevos == 1 else 's') + ' esta semana',
            'accion': _accion("Socios D'CASA", 'res.partner', socios),
        })

    # ------------------------------------------------------------------
    # Instalación
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_configurar_inicio(self):
        """«Inicio» es la pantalla con la que abre Odoo para todo el equipo; el catálogo de
        apps no ofrece módulos de pago (para eso está «En desarrollo»)."""
        inicio = self.env.ref('dcasa_interfaz.action_dcasa_inicio')
        ventas = self.env.ref('sale.action_quotations_with_onboarding', raise_if_not_found=False)
        usuarios = self.env['res.users'].with_context(active_test=False).search([('share', '=', False)])
        usuarios.filtered(lambda u: not u.action_id or (ventas and u.action_id.id == ventas.id)).action_id = inicio.id
        # Sin recorrido guiado ni conversación de bienvenida de OdooBot.
        usuarios.tour_enabled = False
        usuarios.odoobot_state = 'disabled'
        self._dcasa_ocultar_lo_que_no_se_usa()

    @api.model
    def _dcasa_ocultar_lo_que_no_se_usa(self):
        """Las apps estándar de Odoo que una mueblería no usa (Discuss, Calendario, Tableros, Aplicaciones…) quedan
        solo en modo desarrollador, y el catálogo de apps sin módulos de pago.

        ``dcasa_base`` ya lo hace al instalarse. Aquí se repite en cada actualización de este módulo porque
        ``-u all`` (o actualizar ``mail``, ``calendar``…) vuelve a cargar los menús de Odoo con sus grupos de fábrica y
        la vendedora vería de nuevo esos íconos. El despliegue normal solo actualiza los módulos dcasa_*: no los toca.
        """
        from odoo.addons.dcasa_base import MENUS_OCULTOS
        desarrollador = self.env.ref('base.group_no_one')
        for xmlid in MENUS_OCULTOS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.group_ids != desarrollador:
                menu.group_ids = [(6, 0, desarrollador.ids)]
        apps = self.env.ref('base.open_module_tree', raise_if_not_found=False)
        if apps and apps.domain != APPS_SIN_PAGO:
            apps.domain = APPS_SIN_PAGO
        self._dcasa_refrescar_iconos()

    @api.model
    def _dcasa_refrescar_iconos(self):
        """Odoo guarda la imagen del ícono de cada menú cuando se escribe su ``web_icon``, no cuando cambia el archivo:
        un ícono que se recolorea o se rediseña seguiría viéndose como antes. En cada actualización se vuelve a leer el
        archivo y se guarda si cambió (2026-10-16: un color por familia)."""
        Menu = self.env['ir.ui.menu'].with_context(active_test=False)
        for menu in Menu.search([('web_icon', '!=', False)]):
            nuevo = Menu._compute_web_icon_data(menu.web_icon)
            if nuevo and base64.b64decode(nuevo) != base64.b64decode(menu.web_icon_data or b''):
                menu.web_icon_data = nuevo

    @api.model
    def _dcasa_configurar_panel(self):
        """Ajustes del panel que se repiten en cada actualización (views/panel_views.xml).

        Sin «enriquecimiento» de la empresa con el servicio IAP de Odoo: al primer ingreso de
        un administrador, ``partner_autocomplete`` llamaba a odoo.com en el arranque del panel
        (~70 consultas y una espera de red) y podía reemplazar el logo de D'CASA por el que
        encuentre para el dominio del correo. Los datos de la empresa los pone dcasa_base.
        """
        companias = self.env['res.company'].sudo().search([])
        if 'iap_enrich_auto_done' in companias._fields:
            companias.filtered(lambda c: not c.iap_enrich_auto_done).iap_enrich_auto_done = True
        self._dcasa_ocultar_lo_que_no_se_usa()
