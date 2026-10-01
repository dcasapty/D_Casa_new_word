"""Datos del tablero «Inicio»: cómo va el día en D'CASA, en una sola pantalla.

Cada cifra respeta los permisos de quien mira: si una vendedora no ve contabilidad,
su tablero simplemente no trae «Por cobrar». Nada se inventa: todo sale de la base.
Los accesos («Registrar cobro», «Nueva cotización»…) también: ``permisos`` dice cuáles
puede usar quien mira, y el Inicio solo muestra esos (UI-02).
"""
from datetime import datetime, time, timedelta

import pytz
from babel.dates import format_date

from odoo import api, fields, models

DIAS_CORTOS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']


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

    def _permisos(self):
        """Qué accesos y paneles del Inicio puede usar quien mira."""
        return {
            'cotizar': self._puede('sale.order', 'create'),
            'crear_cliente': self._puede('res.partner', 'create'),
            # Registrar un cobro exige Facturación (ACL de account.payment).
            'cobrar': self._puede('account.payment', 'create'),
            'ver_cobros': self._puede('account.payment'),
            'catalogo': self._puede('product.template'),
        }

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------

    @api.model
    def obtener_datos(self):
        hoy = fields.Date.context_today(self)
        inicio, fin = self._limites_del_dia(hoy)
        moneda = self.env.company.currency_id
        datos = {
            'saludo': (self.env.user.name or '').split(' ')[0],
            'fecha': format_date(hoy, "EEEE d 'de' MMMM", locale='es'),
            'moneda': {'simbolo': moneda.symbol, 'antes': moneda.position == 'before'},
            'cifras': [],
            'cobros': [],
            'semana': [],
            'top': [],
            'permisos': self._permisos(),
        }
        if self._puede('sale.order'):
            self._cifras_de_ventas(datos, hoy, inicio, fin)
        if datos['permisos']['ver_cobros']:
            self._cobros_de_hoy(datos, hoy)
            # Sin acceso a cobros, «Por cobrar» saldría de las pocas facturas que deja ver Ventas
            # (las propias): una cifra parcial que parece total. Mejor no mostrarla.
            if self._puede('account.move'):
                self._por_cobrar(datos)
        if self._puede('stock.picking'):
            self._entregas(datos)
        if self._puede('res.partner'):
            self._socios(datos, hoy)
        return datos

    def _cifras_de_ventas(self, datos, hoy, inicio, fin):
        Order = self.env['sale.order']
        de_hoy = [('state', '=', 'sale'), ('date_order', '>=', inicio), ('date_order', '<', fin)]
        ventas = Order.search(de_hoy)
        datos['cifras'].append({
            'clave': 'ventas_hoy', 'titulo': 'Vendido hoy', 'valor': sum(ventas.mapped('amount_total')),
            'formato': 'moneda', 'detalle': f'{len(ventas)} venta' + ('' if len(ventas) == 1 else 's'),
            'accion': _accion('Ventas de hoy', 'sale.order', de_hoy),
        })
        abiertas = [('state', 'in', ('draft', 'sent')), ('website_id', '=', False)]
        cotizaciones = Order.search_read(abiertas, ['amount_total'])
        datos['cifras'].append({
            'clave': 'cotizaciones', 'titulo': 'Cotizaciones abiertas', 'valor': len(cotizaciones),
            'formato': 'numero', 'detalle_moneda': sum(c['amount_total'] for c in cotizaciones),
            'accion': _accion('Cotizaciones abiertas', 'sale.order', abiertas),
        })
        web = [('website_id', '!=', False), ('state', '=', 'sale'), ('delivery_status', '!=', 'full')]
        datos['cifras'].append({
            'clave': 'web', 'titulo': 'Pedidos web por atender', 'valor': Order.search_count(web),
            'formato': 'numero', 'detalle': 'Confírmalos por WhatsApp',
            'accion': _accion('Pedidos web por atender', 'sale.order', web),
        })
        # Ventas de los últimos 7 días (barras del tablero).
        for atras in range(6, -1, -1):
            dia = hoy - timedelta(days=atras)
            d_inicio, d_fin = self._limites_del_dia(dia)
            monto = sum(Order.search([
                ('state', '=', 'sale'), ('date_order', '>=', d_inicio), ('date_order', '<', d_fin),
            ]).mapped('amount_total'))
            datos['semana'].append({'dia': DIAS_CORTOS[dia.weekday()], 'monto': monto, 'hoy': atras == 0})
        # Lo más vendido del mes.
        lineas = self.env['sale.order.line'].read_group(
            [('order_id.state', '=', 'sale'), ('order_id.date_order', '>=', inicio - timedelta(days=30)),
             ('product_id.type', '!=', 'service'), ('is_downpayment', '=', False)],
            ['product_uom_qty:sum'], ['product_id'])
        por_plantilla = {}
        productos = self.env['product.product'].browse([g['product_id'][0] for g in lineas if g['product_id']])
        cantidades = {g['product_id'][0]: g['product_uom_qty'] for g in lineas if g['product_id']}
        for producto in productos:
            plantilla = producto.product_tmpl_id
            por_plantilla.setdefault(plantilla, 0)
            por_plantilla[plantilla] += cantidades[producto.id]
        for plantilla, cantidad in sorted(por_plantilla.items(), key=lambda pc: -pc[1])[:5]:
            datos['top'].append({
                'id': plantilla.id, 'nombre': plantilla.name, 'cantidad': int(cantidad),
                'imagen': f'/web/image/product.template/{plantilla.id}/image_128',
            })

    def _cobros_de_hoy(self, datos, hoy):
        dominio = [('payment_type', '=', 'inbound'), ('state', '!=', 'canceled'), ('date', '=', hoy)]
        grupos = self.env['account.payment'].read_group(dominio, ['amount:sum'], ['journal_id'])
        for grupo in grupos:
            if grupo['journal_id']:
                datos['cobros'].append({'forma': grupo['journal_id'][1], 'monto': grupo['amount']})
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
        apps = self.env.ref('base.open_module_tree', raise_if_not_found=False)
        if apps:
            apps.domain = "[('to_buy', '=', False)]"
