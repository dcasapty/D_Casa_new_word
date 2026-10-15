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
(``sale.order._dcasa_dominio_vendido``). Una cotización, un borrador o un pedido por facturar no es una venta.
"""
from datetime import datetime, time, timedelta

import pytz
from babel.dates import format_date

from odoo import api, fields, models

DIAS_CORTOS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']
APPS_SIN_PAGO = "[('to_buy', '=', False)]"


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
        cotización», ni «Ver la tienda»: solo las herramientas del día (UI-02, 2026-10-14).
        """
        return {
            'cotizar': self._puede('sale.order', 'create'),
            'crear_cliente': self._puede('res.partner', 'create'),
            'facturar': self._puede('account.move', 'create'),
            # Registrar un cobro exige Facturación (ACL de account.payment).
            'cobrar': not propio and self._puede('account.payment', 'create'),
            'ver_cobros': not propio and self._puede('account.payment'),
            'catalogo': self._puede('product.template'),
            # El panel completo de la tienda (cifras de todos, barras, lo más vendido) y los botones de la dueña.
            'completo': not propio,
        }

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------

    def _atajos(self, permisos):
        """Los accesos grandes del Inicio, en este orden: Productos, Facturas, Conversaciones, Oportunidades y
        Resumen contable.

        Solo los que quien mira puede abrir. Conversaciones, Oportunidades y el Resumen contable viven en otros
        módulos: si no están instalados (o la persona no tiene permiso) simplemente no salen. ``vista`` es la vista
        con la que abre. Productos es la lista donde se ordena y filtra por stock, precio y categoría
        (dcasa_catalogo): marketing arma ahí las campañas. Facturas es la lista de facturas a clientes (la misma de
        Facturación › Clientes › Facturas). Quien vende sin controlar (``permisos['completo']`` en falso) tiene solo
        Productos, Facturas y Conversaciones; Oportunidades y el Resumen contable son de quien controla la tienda.
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
            'semana': [],
            'top': [],
            'permisos': self._permisos(propio),
            # La Guía («¿Qué necesitas hacer hoy?») vive en otro módulo: si no está instalado, no hay botón.
            'guia': bool(self.env.ref('dcasa_guia.accion_guia', raise_if_not_found=False)),
        }
        datos['atajos'] = self._atajos(datos['permisos'])
        if self._puede('sale.order'):
            self._cifras_de_ventas(datos, hoy, propio)
        # Lo que quien vende sin controlar no ve: lo cobrado y lo por cobrar, las entregas y los socios.
        if datos['permisos']['ver_cobros']:
            self._cobros_de_hoy(datos, hoy)
            # Sin acceso a cobros, «Por cobrar» saldría de las pocas facturas que deja ver Ventas
            # (las propias): una cifra parcial que parece total. Mejor no mostrarla.
            if self._puede('account.move'):
                self._por_cobrar(datos)
        if not propio and self._puede('stock.picking'):
            self._entregas(datos)
        if not propio and self._puede('res.partner'):
            self._socios(datos, hoy)
        return datos

    def _cifras_de_ventas(self, datos, hoy, propio=False):
        """Las cifras de ventas. «Vendido» = pedidos facturados por completo (``_dcasa_dominio_vendido``), contados
        en el día de su última factura: la tarjeta, la lista que abre, las barras y «lo más vendido» salen todos de
        ese mismo dominio. ``propio``: solo los pedidos de quien mira (y nada de barras ni totales de la tienda)."""
        Order = self.env['sale.order']
        vendedor = self.env.uid if propio else None
        # Una sola lectura para «Vendido hoy» y las barras de la semana. El día de la venta ya es una fecha de
        # Panamá (la de la factura): no hay conversión de horas.
        ventas = Order.search_read(
            Order._dcasa_dominio_vendido(desde=hoy if propio else hoy - timedelta(days=6), hasta=hoy,
                                         vendedor=vendedor),
            ['dcasa_fecha_venta', 'amount_total'])
        por_dia = {}
        for venta in ventas:
            cuenta, monto = por_dia.get(venta['dcasa_fecha_venta'], (0, 0.0))
            por_dia[venta['dcasa_fecha_venta']] = (cuenta + 1, monto + venta['amount_total'])
        cuantas, vendido = por_dia.get(hoy, (0, 0.0))
        datos['cifras'].append({
            'clave': 'ventas_hoy', 'titulo': 'Vendido hoy', 'valor': vendido, 'formato': 'moneda',
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
        web = [('website_id', '!=', False), ('state', '=', 'sale'), ('delivery_status', '!=', 'full')]
        datos['cifras'].append({
            'clave': 'web', 'titulo': 'Pedidos web por atender', 'valor': Order.search_count(web),
            'formato': 'numero', 'detalle': 'Confírmalos por WhatsApp',
            'accion': _accion('Pedidos web por atender', 'sale.order', web),
        })
        self._barras_y_lo_mas_vendido(datos, hoy, por_dia)

    def _cifra_mis_cotizaciones(self, abiertas, mias):
        return {
            'clave': 'mis_cotizaciones', 'titulo': 'Mis cotizaciones', 'valor': len(mias),
            'formato': 'numero', 'detalle_moneda': sum(c['amount_total'] for c in mias),
            'accion': _accion('Mis cotizaciones abiertas', 'sale.order', abiertas + [('user_id', '=', self.env.uid)]),
        }

    def _barras_y_lo_mas_vendido(self, datos, hoy, por_dia):
        """Las barras de los últimos 7 días y lo más vendido del mes (solo en el panel de la tienda)."""
        for atras in range(6, -1, -1):
            dia = hoy - timedelta(days=atras)
            monto = por_dia.get(dia, (0, 0.0))[1]
            datos['semana'].append({'dia': DIAS_CORTOS[dia.weekday()], 'monto': monto, 'hoy': atras == 0})
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
        dominio = [('payment_type', '=', 'inbound'), ('state', '!=', 'canceled'), ('date', '=', hoy)]
        grupos = self.env['account.payment']._read_group(dominio, ['journal_id'], ['amount:sum'])
        for diario, monto in grupos:
            if diario:
                datos['cobros'].append({'forma': diario.display_name, 'monto': monto})
        datos['cifras'].append({
            'clave': 'cobrado_hoy', 'titulo': 'Cobrado hoy', 'valor': sum(c['monto'] for c in datos['cobros']),
            'formato': 'moneda', 'detalle': ' · '.join(c['forma'] for c in datos['cobros']) or 'Sin cobros todavía',
            'accion': _accion('Cobros de hoy', 'account.payment', dominio),
        })

    def _por_cobrar(self, datos):
        dominio = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                   ('payment_state', 'in', ('not_paid', 'partial'))]
        facturas = self.env['account.move'].search_read(dominio, ['amount_residual'])
        datos['cifras'].append({
            'clave': 'por_cobrar', 'titulo': 'Por cobrar', 'valor': sum(f['amount_residual'] for f in facturas),
            'formato': 'moneda', 'detalle': f'{len(facturas)} factura' + ('' if len(facturas) == 1 else 's'),
            'accion': _accion('Facturas por cobrar', 'account.move', dominio),
        })

    def _entregas(self, datos):
        dominio = [('picking_type_code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'waiting', 'assigned'))]
        datos['cifras'].append({
            'clave': 'entregas', 'titulo': 'Entregas pendientes',
            'valor': self.env['stock.picking'].search_count(dominio),
            'formato': 'numero', 'detalle': 'Por despachar o retirar',
            'accion': _accion('Entregas pendientes', 'stock.picking', dominio),
        })

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
