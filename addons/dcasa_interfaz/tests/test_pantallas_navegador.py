"""«Por día», «Estadísticas» y «Movimientos» en el navegador, a tamaño computadora (1440×900) y celular (390×844): lo
que de verdad se ve (calendario o lista de días, el detalle de un día que abre el documento, las gráficas, la línea de
tiempo con + verde y − rojo) y nada de desplazamiento de costado."""
from datetime import timedelta

from odoo import Command
from odoo.tests import HttpCase, tagged

from .test_inicio_por_rol import ESPERAR_JS, VentasMixin

TAMANOS = ('1440x900', '390x844')

COMUN_JS = ESPERAR_JS + r"""
    const visible = (selector) => {
        const el = document.querySelector(selector);
        return el && el.offsetParent !== null ? el : null;
    };
    const sinScrollDeCostado = (que) => {
        const raiz = document.querySelector('.o_action');
        if (raiz.scrollWidth > raiz.clientWidth + 1 || document.documentElement.scrollWidth > window.innerWidth + 1) {
            throw new Error(`scroll de costado (${que}): ${raiz.scrollWidth} > ${raiz.clientWidth}`);
        }
        const afuera = [...raiz.querySelectorAll('*')].filter((el) => el.offsetParent !== null
            && el.getBoundingClientRect().right > window.innerWidth + 1);
        if (afuera.length) {
            const el = afuera[0];
            throw new Error(`se sale de la pantalla (${que}): ${el.className} ${el.textContent.slice(0, 40)}`);
        }
    };
    const celular = window.innerWidth < 768;
"""


class PantallasMixin(VentasMixin):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hoy = cls.env['dcasa.tablero']._ahora_en_panama().date()
        cls.mesa = cls.env['product.product'].create({
            'name': 'MESA NAVEGADOR POR DÍA', 'default_code': 'NAV-DIA-1', 'barcode': '7700000000099',
            'is_storable': True, 'list_price': 250.0, 'standard_price': 120.0, 'taxes_id': [Command.clear()]})
        cls.factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.cliente.id, 'invoice_date': cls.hoy,
            'invoice_user_id': cls.vendedora.id,
            # 40 unidades: que esté entre lo más vendido aunque la base ya tenga otras ventas este mes.
            'invoice_line_ids': [Command.create({'product_id': cls.mesa.id, 'quantity': 40, 'price_unit': 12.5})]})
        cls.factura.action_post()
        cls.nota = cls.factura._reverse_moves([{'invoice_date': cls.hoy, 'date': cls.hoy}])
        cls.nota.invoice_line_ids.write({'quantity': 1, 'price_unit': 50.0})
        cls.nota.action_post()


@tagged('post_install', '-at_install')
class TestPorDiaEnElNavegador(PantallasMixin, HttpCase):

    def test_por_dia_calendario_o_lista_y_el_detalle_abre_el_documento(self):
        codigo = '(async () => {' + COMUN_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_pd_titulo'), 'el título');
            igual(document.querySelector('.o_dcasa_pd_titulo').textContent.trim(), 'Lo facturado por día', 'título');
            igual(textos('.o_dcasa_pd_bases .o_dcasa_interruptor_opcion'),
                  ['Vendido', 'Facturado', 'Con abonos', 'Completadas'], 'las cuatro bases');
            await esperar(() => document.querySelector('.o_dcasa_pd_detalle .o_dcasa_pd_documento'), 'el día de hoy');
            if (celular) {
                if (visible('.o_dcasa_pd_calendario') || !visible('.o_dcasa_pd_lista')) {
                    throw new Error('en el celular va la lista de días, no el calendario');
                }
                const primero = document.querySelector('.o_dcasa_pd_item');
                if (!primero.classList.contains('o_activo') || !primero.querySelector('.o_dcasa_pd_fila.o_hoy')) {
                    throw new Error('el día de hoy va primero y abierto');
                }
            } else {
                if (!visible('.o_dcasa_pd_calendario') || visible('.o_dcasa_pd_lista')) {
                    throw new Error('en la computadora va el calendario');
                }
                if (!document.querySelector('.o_dcasa_pd_celda.o_hoy.o_activo')) {
                    throw new Error('hoy está elegido en el calendario');
                }
                igual(textos('.o_dcasa_pd_semana span'), ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'], 'semana');
            }
            const filas = [...document.querySelectorAll('.o_dcasa_pd_documento')]
                .filter((f) => f.offsetParent !== null);
            const textosFilas = filas.map((f) => f.textContent);
            if (!textosFilas.some((t) => t.includes(__FACTURA__) && t.includes('$500.00'))) {
                throw new Error('la factura del día: ' + textosFilas.join(' | '));
            }
            if (!textosFilas.some((t) => t.includes(__NOTA__) && t.includes('Nota de crédito')
                                  && t.includes('-$50.00'))) {
                throw new Error('la nota de crédito resta: ' + textosFilas.join(' | '));
            }
            sinScrollDeCostado('por día');
            // Tocar la factura la abre.
            filas.find((f) => f.textContent.includes(__FACTURA__)).click();
            await esperar(() => document.querySelector('.o_form_view'), 'el formulario de la factura');
            await esperar(() => document.body.textContent.includes(__FACTURA__), 'el número de la factura');
            history.back();
            await esperar(() => visible('.o_dcasa_pd_bases'), 'de vuelta en Por día');
            // «Vendido»: los pedidos confirmados.
            document.querySelector('.o_dcasa_pd_base_confirmado').click();
            const titulo = () => document.querySelector('.o_dcasa_pd_titulo').textContent.trim();
            await esperar(() => titulo() === 'Lo vendido por día', 'el título de Vendido');
            sinScrollDeCostado('vendido');
        """.replace('__FACTURA__', repr(self.factura.name)).replace('__NOTA__', repr(self.nota.name)) \
            + "console.log('test successful'); })();"
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol',
                                timeout=120)

    def test_estadisticas_graficas_y_una_barra_abre_el_dia(self):
        codigo = '(async () => {' + COMUN_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_es_barra'), 'las barras');
            igual(document.querySelectorAll('.o_dcasa_es_barra').length, __DIA__, 'una barra por día, hasta hoy');
            igual(textos('.o_dcasa_es_numeros .o_dcasa_pd_etiqueta').slice(1),
                  ['Facturas', 'Ticket promedio', 'Unidades'], 'los números del periodo');
            if (textos('.o_dcasa_es_frase').length < 7) { throw new Error('cada número y gráfica con su frase'); }
            if (!textos('.o_dcasa_es_productos .o_dcasa_es_nombre').some((t) => t.includes('MESA NAVEGADOR POR DÍA'))) {
                throw new Error('la mesa está entre lo más vendido');
            }
            if (!textos('.o_dcasa_es_vendedoras .o_dcasa_es_nombre').includes(__VENDEDORA__)) {
                throw new Error('la vendedora está en «Por vendedora»');
            }
            const hoy = document.querySelector('.o_dcasa_es_barra.o_hoy .o_dcasa_es_barra_relleno');
            igual(getComputedStyle(hoy).backgroundColor, 'rgb(14, 42, 107)', 'la barra de hoy, azul oscuro');
            sinScrollDeCostado('estadísticas');
            document.querySelector('.o_dcasa_es_periodo_mes_pasado').click();
            await esperar(() => document.querySelectorAll('.o_dcasa_es_barra').length === __DIAS_MES_PASADO__
                          && !document.querySelector('.o_dcasa_es_cuerpo.o_cargando'), 'el mes pasado');
            document.querySelector('.o_dcasa_es_periodo_mes').click();
            await esperar(() => document.querySelectorAll('.o_dcasa_es_barra').length === __DIA__
                          && !document.querySelector('.o_dcasa_es_cuerpo.o_cargando'), 'este mes otra vez');
            document.querySelector('.o_dcasa_es_barra.o_hoy').click();
            await esperar(() => document.querySelector('.o_dcasa_pd_titulo'), 'Por día');
            await esperar(() => document.querySelector('.o_dcasa_pd_detalle .o_dcasa_pd_documento'),
                          'el día de la barra');
        """.replace('__DIA__', str(self.hoy.day)).replace('__VENDEDORA__', repr(self.vendedora.name)).replace(
            '__DIAS_MES_PASADO__', str((self.hoy.replace(day=1) - timedelta(days=1)).day)) \
            + "console.log('test successful'); })();"
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_estadisticas', codigo, login='gerencia_rol',
                                timeout=120)


@tagged('post_install', '-at_install')
class TestMovimientosEnElNavegador(PantallasMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        for cantidad in (3, 1):              # entra 3 y después el conteo deja 1: sale 2
            cls.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': cls.mesa.id, 'location_id': almacen.lot_stock_id.id, 'inventory_quantity': cantidad,
            }).action_apply_inventory()

    def test_buscar_un_producto_y_ver_su_historia(self):
        codigo = '(async () => {' + COMUN_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_mv_fila'), 'los últimos movimientos de todos');
            sinScrollDeCostado('todos');
            const buscar = document.querySelector('.o_dcasa_mv_texto');
            buscar.value = '7700000000099';
            buscar.dispatchEvent(new Event('input', { bubbles: true }));
            await esperar(() => document.querySelector('.o_dcasa_mv_resultado'), 'el producto encontrado');
            igual(textos('.o_dcasa_mv_resultado strong')[0], '[NAV-DIA-1] MESA NAVEGADOR POR DÍA',
                  'por código de barras');
            document.querySelector('.o_dcasa_mv_resultado').click();
            await esperar(() => document.querySelector('.o_dcasa_mv_producto'), 'el producto elegido');
            await esperar(() => document.querySelectorAll('.o_dcasa_mv_fila').length === 2, 'sus dos movimientos');
            igual(textos('.o_dcasa_mv_frase'), ['Ajuste de inventario (−2)', 'Ajuste de inventario (+3)'],
                  'en palabras');
            igual(textos('.o_dcasa_mv_cantidad'), ['−2', '+3'], 'las cantidades');
            igual(textos('.o_dcasa_mv_queda'), ['Queda 1', 'Quedan 3'], 'lo que quedó');
            const [sale, entra] = document.querySelectorAll('.o_dcasa_mv_cantidad');
            igual(getComputedStyle(sale).color, 'rgb(179, 38, 30)', 'lo que sale, en rojo');
            igual(getComputedStyle(entra).color, 'rgb(27, 127, 59)', 'lo que entra, en verde');
            igual(document.querySelector('.o_dcasa_mv_hoy').textContent.trim().replace(/\s+/g, ' '), 'Hay hoy: 1',
                  'lo que hay hoy');
            sinScrollDeCostado('un producto');
            document.querySelector('.o_dcasa_mv_tipo_venta').click();
            await esperar(() => !document.querySelector('.o_dcasa_mv_fila')
                          && document.querySelector('.o_dcasa_mv_tiempo .o_dcasa_vacio'), 'sin ventas');
            document.querySelector('.o_dcasa_mv_tipo_ajuste').click();
            await esperar(() => document.querySelectorAll('.o_dcasa_mv_fila').length === 2, 'los ajustes');
            document.querySelector('.o_dcasa_mv_quitar').click();
            await esperar(() => !document.querySelector('.o_dcasa_mv_producto'), 'de vuelta a todos');
        """ + "console.log('test successful'); })();"
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_movimientos', codigo, login='gerencia_rol',
                                timeout=120)


@tagged('post_install', '-at_install')
class TestCobrosYValorEnElNavegador(PantallasMixin, HttpCase):
    """Lo cobrado por forma de pago en «Por día» y «Valor del inventario» (2026-11-02), en computadora y celular."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.yappy = cls.env['account.journal'].create({'name': 'Yappy navegador', 'type': 'bank', 'code': 'YNAV'})
        cls.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=cls.factura.ids).create({
                'payment_date': cls.hoy, 'amount': 500.0, 'journal_id': cls.yappy.id})._create_payments()
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.mesa, almacen.lot_stock_id, 5.0)

    def test_por_dia_dice_con_que_se_cobro_el_dia_y_el_mes(self):
        codigo = '(async () => {' + COMUN_JS + r"""
            const ficha = (donde) => [...document.querySelectorAll(donde + ' .o_dcasa_cf_ficha')]
                .find((f) => f.offsetParent !== null && f.textContent.includes('Yappy navegador'));
            await esperar(() => ficha('.o_dcasa_pd_cobros_dia'), 'lo cobrado el día de hoy');
            if (!ficha('.o_dcasa_pd_cobros_dia').textContent.includes('$500.00')) {
                throw new Error('el día: ' + ficha('.o_dcasa_pd_cobros_dia').textContent);
            }
            const mes = ficha('.o_dcasa_pd_cobros');
            if (!mes || !mes.textContent.includes('$500.00') || !mes.textContent.includes('1 cobro')) {
                throw new Error('el mes: ' + (mes ? mes.textContent : 'sin la ficha'));
            }
            if (!visible('.o_dcasa_pd_cobros .o_dcasa_cf_total')) { throw new Error('el total cobrado del mes'); }
            sinScrollDeCostado('cobrado por forma de pago');
            mes.click();
            await esperar(() => document.querySelector('.o_list_view .o_data_row'), 'los cobros de Yappy');
        """ + "console.log('test successful'); })();"
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol',
                                timeout=120)

    def test_valor_del_inventario(self):
        codigo = '(async () => {' + COMUN_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_vi_costo .o_dcasa_pd_valor'), 'el valor al costo');
            igual(textos('.o_dcasa_es_numeros .o_dcasa_pd_etiqueta'),
                  ['Al costo', 'A precio de venta', 'Ganancia esperada', 'Unidades'], 'los cuatro números');
            if (!textos('.o_dcasa_vi_productos .o_dcasa_es_nombre').some((t) => t.includes('MESA NAVEGADOR POR DÍA'))) {
                throw new Error('la mesa está donde está el dinero');
            }
            const mesa = [...document.querySelectorAll('.o_dcasa_vi_producto')]
                .find((f) => f.textContent.includes('MESA NAVEGADOR POR DÍA'));
            if (!mesa.textContent.includes('$600.00') || !mesa.textContent.includes('$1,250.00')) {
                throw new Error('5 × 120 al costo y 5 × 250 a precio de venta: ' + mesa.textContent);
            }
            if (!document.querySelector('.o_dcasa_vi_tipo')) { throw new Error('por tipo de producto'); }
            sinScrollDeCostado('valor del inventario');
            document.querySelector('.o_dcasa_vi_costo').click();
            await esperar(() => document.querySelector('.o_list_view .o_data_row'), 'los productos con existencias');
        """ + "console.log('test successful'); })();"
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_valor_inventario', codigo, login='gerencia_rol',
                                timeout=120)
