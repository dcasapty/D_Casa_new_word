"""«Por día», «Estadísticas» y «Movimientos» en el navegador, a tamaño computadora (1440×900) y celular (390×844): lo
que de verdad se ve (calendario o lista de días, el detalle de un día que abre el documento, las gráficas, la línea de
tiempo con + verde y − rojo) y nada de desplazamiento de costado."""
import json
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
        # 5000 mesas: que encabecen «Dónde está el dinero» aunque la base ya traiga el catálogo con sus existencias.
        cls.env['stock.quant']._update_available_quantity(cls.mesa, almacen.lot_stock_id, 5000.0)
        # El mes pasado, con cobros en dos formas de pago en tres días (el 5, el 12 y el 20): el 12 está solo en su
        # semana, así «Día» y «Semana» dan lo mismo y «Quincena» y «Mes» dan cada uno otra cifra.
        cls.efectivo = cls.env['account.journal'].create({'name': 'Efectivo navegador', 'type': 'cash', 'code': 'ENAV'})
        cls.mes_pasado = cls.hoy.replace(day=1) - timedelta(days=1)
        cls.doce = cls.mes_pasado.replace(day=12)
        for dia, monto, diario in ((5, 100.0, cls.yappy), (12, 120.0, cls.yappy), (12, 80.0, cls.efectivo),
                                   (20, 311.0, cls.yappy)):
            cls.env['account.payment'].create({
                'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': cls.cliente.id, 'amount': monto,
                'date': cls.mes_pasado.replace(day=dia), 'journal_id': diario.id}).action_post()

    def esperado_de_cobros(self, dia):
        """Lo que el servidor dice de cada periodo de ese día: el título, el total y cada forma de pago."""
        gerencia = self.env['dcasa.tablero'].with_user(self.gerencia)
        hoy = gerencia._ahora_en_panama().date()
        esperado = {}
        for periodo in ('dia', 'semana', 'quincena', 'mes'):
            datos = gerencia._cobros_del_periodo(dia, periodo, hoy)
            etiqueta = datos['etiqueta']
            esperado[periodo] = {
                'titulo': etiqueta[:1].upper() + etiqueta[1:], 'total': f'${datos["cobros"]["total"]:,.2f}',
                'formas': {f['forma']: f'${f["monto"]:,.2f}' for f in datos['cobros']['filas']},
                'cuantos': {f['forma']: f['cuantos'] for f in datos['cobros']['filas']},
                'nota': datos['nota'],
            }
        return esperado

    def test_por_dia_tarjeta_unica_de_cobros_arriba_del_detalle(self):
        """«Cobrado por forma de pago»: una sola tarjeta, a la vista y arriba de las facturas del día, con selector."""
        esperado = self.esperado_de_cobros(self.hoy)
        codigo = '(async () => {' + COMUN_JS + r"""
            const ESPERADO = __ESPERADO__;
            const falla = (mensaje) => { throw new Error(mensaje); };
            const visibles = (sel) => [...document.querySelectorAll(sel)].filter((e) => e.offsetParent !== null);
            const tarjeta = () => visibles('.o_dcasa_pd_cobros')[0];
            const total = () => tarjeta().querySelector('.o_dcasa_cf_total .o_dcasa_cf_monto');
            await esperar(() => tarjeta(), 'la tarjeta de lo cobrado');
            await esperar(() => !total().hasAttribute('data-sube'), 'el total quieto');

            // Una sola tarjeta visible (la otra copia es la del celular o la de la computadora, escondida).
            igual(visibles('.o_dcasa_pd_cobros').length, 1, 'una sola tarjeta de lo cobrado a la vista');
            igual(document.querySelectorAll('.o_dcasa_pd_cobros_dia').length, 0, 'ya no hay bloque al final del día');
            igual(tarjeta().querySelector('h2').textContent.trim().replace(/\s+/g, ' '),
                  'Cobrado por forma de pago con ITBMS', 'se llama como la pidió la dueña');
            igual(tarjeta().querySelector('.o_dcasa_pd_cobros_periodo').textContent, ESPERADO.dia.titulo, 'el periodo');
            igual(textos('.o_dcasa_pd_cobros .o_dcasa_periodo').slice(0, 4), ['Día', 'Semana', 'Quincena', 'Mes'],
                  'los cuatro periodos, en ese orden');

            // Arriba de las facturas del día y sin bajar la pantalla.
            const lista = visibles('.o_dcasa_pd_documentos')[0];
            if (!lista) { falla('la lista de facturas del día'); }
            const caja = tarjeta().getBoundingClientRect();
            if (caja.bottom > lista.getBoundingClientRect().top + 1) { falla('la tarjeta va encima de la lista'); }
            document.querySelector('.o_action').scrollTop = 0;
            const fichaTotal = total().closest('.o_dcasa_cf_ficha').getBoundingClientRect();
            if (!celular) {
                if (tarjeta().getBoundingClientRect().top < 0 || fichaTotal.bottom > window.innerHeight) {
                    falla(`lo cobrado se ve sin bajar: ${fichaTotal.bottom} de ${window.innerHeight}`);
                }
                const calendario = document.querySelector('.o_dcasa_pd_calendario').getBoundingClientRect();
                if (caja.left < calendario.right - 1) { falla('a la derecha del calendario'); }
            }

            // Día (por defecto): lo de hoy, por forma de pago.
            igual(total().textContent, ESPERADO.dia.total, 'el total de hoy');
            const ficha = (forma) => [...tarjeta().querySelectorAll('.o_dcasa_cf_ficha:not(.o_dcasa_cf_total)')]
                .find((f) => f.querySelector('.o_dcasa_cf_forma').textContent.trim() === forma);
            if (!ficha('Yappy navegador') || !ficha('Yappy navegador').textContent.includes('$500.00')
                || !ficha('Yappy navegador').textContent.includes('1 cobro')) {
                falla('Yappy hoy: ' + tarjeta().textContent);
            }
            sinScrollDeCostado('cobrado por forma de pago');

            // Cada periodo: el título, el total y cada forma de pago salen de lo que dice el servidor.
            for (const periodo of ['semana', 'quincena', 'mes', 'dia']) {
                tarjeta().querySelector('.o_dcasa_cf_periodo_' + periodo).click();
                await esperar(() => tarjeta().querySelector('.o_dcasa_pd_cobros_periodo').textContent
                              === ESPERADO[periodo].titulo && !tarjeta().classList.contains('o_cargando'),
                              'el título de ' + periodo);
                await esperar(() => !total().hasAttribute('data-sube'), 'el total quieto de ' + periodo);
                igual(tarjeta().querySelector('.o_dcasa_periodo.o_activo').textContent,
                      {dia: 'Día', semana: 'Semana', quincena: 'Quincena', mes: 'Mes'}[periodo], 'el botón activo');
                igual(total().textContent, ESPERADO[periodo].total, 'el total de ' + periodo);
                for (const [forma, monto] of Object.entries(ESPERADO[periodo].formas)) {
                    if (!ficha(forma) || ficha(forma).querySelector('.o_dcasa_cf_monto').textContent !== monto) {
                        falla(`${forma} en ${periodo}: ${tarjeta().textContent}`);
                    }
                }
                igual(tarjeta().querySelectorAll('.o_dcasa_cf_ficha:not(.o_dcasa_cf_total)').length,
                      Object.keys(ESPERADO[periodo].formas).length, 'una ficha por forma de pago en ' + periodo);
                const nota = tarjeta().querySelectorAll('.o_dcasa_cf_pista');
                igual([...nota].map((n) => n.textContent.trim()).filter(Boolean), ESPERADO[periodo].nota
                      ? [ESPERADO[periodo].nota] : [], 'la nota de «cuenta hasta hoy» de ' + periodo);
                sinScrollDeCostado('cobrado ' + periodo);
            }
            // Una forma de pago de la semana abre los cobros de esa semana y de esa forma.
            tarjeta().querySelector('.o_dcasa_cf_periodo_semana').click();
            await esperar(() => tarjeta().querySelector('.o_dcasa_pd_cobros_periodo').textContent
                          === ESPERADO.semana.titulo && !tarjeta().classList.contains('o_cargando'), 'la semana');
            ficha('Yappy navegador').click();
            await esperar(() => document.querySelector('.o_list_view .o_data_row'), 'los cobros de Yappy de la semana');
            const migas = document.querySelector('.o_breadcrumb').textContent;
            if (!migas.includes('semana del')) { falla('la lista dice de qué semana es: ' + migas); }
            const filas = document.querySelectorAll('.o_list_view .o_data_row').length;
            igual(filas, ESPERADO.semana.cuantos['Yappy navegador'], 'los cobros de esa forma en esa semana');
        """.replace('__ESPERADO__', json.dumps(esperado, ensure_ascii=False)) + "console.log('test successful'); })();"
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol',
                                timeout=120)

    def test_por_dia_los_periodos_siguen_al_dia_elegido_y_sus_cifras_suben(self):
        """Mes pasado → un día: el selector sigue al día; las cifras suben (o bajan) desde donde estaban; si no cambian,
        no se animan; con «reducir movimiento» no se mueve nada."""
        esperado = self.esperado_de_cobros(self.doce)
        mes = self.mes_pasado.strftime('%Y-%m')
        codigo = '(async () => {' + COMUN_JS + r"""
            const ESPERADO = __ESPERADO__;
            const falla = (mensaje) => { throw new Error(mensaje); };
            const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
            const visibles = (sel) => [...document.querySelectorAll(sel)].filter((e) => e.offsetParent !== null);
            const tarjeta = () => visibles('.o_dcasa_pd_cobros')[0];
            const total = () => tarjeta().querySelector('.o_dcasa_cf_total .o_dcasa_cf_monto');
            const titulo = () => tarjeta().querySelector('.o_dcasa_pd_cobros_periodo').textContent;
            const monto = (texto) => Number(String(texto).replace(/[^0-9.-]/g, ''));
            const cargando = () => tarjeta().classList.contains('o_cargando');
            const quieta = () => !cargando() && !total().hasAttribute('data-sube');
            await esperar(() => tarjeta() && quieta(), 'la tarjeta de lo cobrado');
            const totalDeHoy = total().textContent;

            // Un mes que ya pasó, sin ningún día elegido: lo cobrado del mes y los botones de día esperan.
            const lista = document.querySelector('.o_dcasa_pd_mes_select');
            lista.value = '__MES__';
            lista.dispatchEvent(new Event('change', { bubbles: true }));
            await esperar(() => tarjeta() && titulo() === ESPERADO.mes.titulo && quieta(), 'el mes pasado');
            igual(total().textContent, ESPERADO.mes.total, 'lo cobrado del mes pasado');
            igual(tarjeta().querySelector('.o_dcasa_periodo.o_activo').textContent, 'Mes', 'sin día elegido, el mes');
            for (const periodo of ['dia', 'semana', 'quincena']) {
                igual(tarjeta().querySelector('.o_dcasa_cf_periodo_' + periodo).disabled, true, periodo + ' espera');
            }
            igual(tarjeta().querySelector('.o_dcasa_cf_periodo_mes').disabled, false, 'el mes siempre se puede');
            if (!tarjeta().textContent.includes('Toca un día')) { falla('la pista de qué hacer'); }
            if (totalDeHoy === total().textContent) { falla('el mes pasado no puede dar lo mismo que hoy'); }

            // Se toca el día 12: el selector vuelve a «Día» y la tarjeta es la de ese día.
            const doce = () => visibles('[data-fecha="__DOCE__"]')[0];
            await esperar(() => doce(), 'el día 12 del mes pasado');
            doce().click();
            await esperar(() => tarjeta() && titulo() === ESPERADO.dia.titulo && quieta(), 'el día 12');
            igual(tarjeta().querySelector('.o_dcasa_periodo.o_activo').textContent, 'Día', 'con día elegido, el día');
            igual(total().textContent, ESPERADO.dia.total, 'lo cobrado ese día');
            for (const periodo of ['dia', 'semana', 'quincena', 'mes']) {
                const boton = tarjeta().querySelector('.o_dcasa_cf_periodo_' + periodo);
                igual(boton.disabled, false, periodo + ' disponible');
            }
            igual(Object.keys(ESPERADO.dia.formas).length, 2, 'dos formas de pago ese día');

            // Cambia de periodo mirando cada número que se ve en la cifra del total.
            const cambiar = async (periodo) => {
                const antes = monto(total().textContent);
                const espia = [];
                const ojo = new MutationObserver(() => {
                    const texto = total().getAttribute('data-sube');
                    if (texto !== null) { espia.push(monto(texto)); }
                });
                ojo.observe(total(), { attributes: true, attributeFilter: ['data-sube'] });
                tarjeta().querySelector('.o_dcasa_cf_periodo_' + periodo).click();
                await esperar(() => titulo() === ESPERADO[periodo].titulo && !cargando(), 'el título de ' + periodo);
                await esperar(() => !total().hasAttribute('data-sube'), 'el total quieto de ' + periodo, 60);
                await pausa(60);
                ojo.disconnect();
                igual(total().textContent, ESPERADO[periodo].total, 'termina en el total de ' + periodo);
                return { antes, despues: monto(total().textContent), espia };
            };
            // Día → Semana: el 12 está solo en su semana, es la misma cifra: no se anima, solo cambia el título.
            let paso = await cambiar('semana');
            igual(paso.antes, paso.despues, 'la semana del 12 suma lo mismo que el 12');
            igual(paso.espia, [], 'si el valor no cambió, no se anima');
            // Semana → Quincena y Quincena → Mes: sube desde el valor anterior hasta el nuevo.
            for (const siguiente of ['quincena', 'mes']) {
                paso = await cambiar(siguiente);
                if (!(paso.despues > paso.antes)) { falla(`${siguiente} suma más: ${paso.antes} → ${paso.despues}`); }
                if (paso.espia.length < 3) { falla('se esperaban valores a medias: ' + paso.espia.join(', ')); }
                if (Math.abs(paso.espia[0] - paso.antes) > 0.005) {
                    falla(`debía partir de ${paso.antes} y partió de ${paso.espia[0]}`);
                }
                const e = paso.espia;
                // Al final el número ya redondea al valor (299.998 se ve «300.00»): nunca pasa de él, sí llega.
                if (e.some((v, i) => i && v < e[i - 1]) || e.some((v) => v > paso.despues + 0.005)) {
                    falla('sube sin pasarse: ' + paso.espia.join(', '));
                }
            }
            // Mes → Día: baja desde el valor anterior.
            paso = await cambiar('dia');
            if (!(paso.despues < paso.antes) || paso.espia.length < 3 || Math.abs(paso.espia[0] - paso.antes) > 0.005
                || paso.espia.some((v, i) => i && v > paso.espia[i - 1])) {
                falla('baja desde el valor anterior: ' + JSON.stringify(paso));
            }

            // Con «reducir movimiento» no se mueve nada, y el texto es siempre el valor final.
            const { browser } = odoo.loader.modules.get('@web/core/browser/browser');
            const original = browser.matchMedia;
            browser.matchMedia = (consulta) => (/prefers-reduced-motion:\s*reduce/.test(consulta)
                ? { matches: true, media: consulta } : original(consulta));
            try {
                paso = await cambiar('quincena');
                igual(paso.espia, [], 'con menos movimiento nada sube');
                paso = await cambiar('mes');
                igual(paso.espia, [], 'con menos movimiento nada sube (2)');
            } finally {
                browser.matchMedia = original;
            }

            // El día que se toca otra vez se cierra y la tarjeta vuelve a ser la del mes (sin día no hay día).
            await esperar(() => doce(), 'el día 12 otra vez');
            doce().click();
            await esperar(() => tarjeta() && titulo() === ESPERADO.mes.titulo && quieta(), 'de vuelta al mes');
            igual(tarjeta().querySelector('.o_dcasa_cf_periodo_dia').disabled, true, 'sin día, el día espera');
            sinScrollDeCostado('cobrado, sin día elegido');
        """.replace('__ESPERADO__', json.dumps(esperado, ensure_ascii=False)).replace(
            '__MES__', mes).replace('__DOCE__', str(self.doce)) + "console.log('test successful'); })();"
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol',
                                timeout=180)

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
            if (!mesa.textContent.includes('$600,000.00') || !mesa.textContent.includes('$1,250,000.00')) {
                throw new Error('5000 × 120 al costo y 5000 × 250 a precio de venta: ' + mesa.textContent);
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
