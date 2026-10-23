"""El panel de Bodega en el servidor: la lista, abrir una entrega (también con el QR de su nota) y validarla."""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .bodega_comun import BASE, BodegaCommon


@tagged('post_install', '-at_install')
class TestBodegaLista(BodegaCommon):

    def test_solo_salen_las_salidas_a_clientes_pendientes(self):
        hecha_pedido, hecha = self.venta(self.cliente_retiro, [(self.mesa, 1)])
        hecha.move_ids.quantity = 1
        hecha.move_ids.picked = True
        hecha.button_validate()
        self.assertEqual(hecha.state, 'done')
        _cancelada_pedido, cancelada = self.venta(self.cliente_retiro, [(self.mesa, 1)])
        cancelada.action_cancel()
        almacen = self.almacen
        recepcion = self.env['stock.picking'].create({
            'picking_type_id': almacen.in_type_id.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': almacen.lot_stock_id.id,
            'move_ids': [Command.create({
                'product_id': self.cama.id, 'product_uom_qty': 3, 'product_uom': self.cama.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': almacen.lot_stock_id.id})]})
        recepcion.action_confirm()
        ids = set(self.tarjetas())
        for entrega in (self.entrega_envio, self.entrega_retiro, self.entrega_flete, self.entrega_sin):
            self.assertIn(entrega.id, ids, entrega.name)
        for fuera in (hecha, cancelada, recepcion):
            self.assertNotIn(fuera.id, ids, fuera.name)
        respuesta = self.Bodega.with_user(self.bodeguero).pendientes()
        self.assertEqual(respuesta['cuantas'], len(respuesta['entregas']))
        self.assertFalse(respuesta['recortada'])
        self.assertRegex(respuesta['hora'], r'^\d\d:\d\d$')

    def test_envio_retiro_o_sin_definir_sin_adivinar(self):
        tarjetas = self.tarjetas()
        self.assertEqual(tarjetas[self.entrega_envio.id]['como'], 'envio', 'método de entrega que no es retiro')
        self.assertEqual(tarjetas[self.entrega_retiro.id]['como'], 'retiro', 'método marcado «Es retiro en la tienda»')
        self.assertEqual(tarjetas[self.entrega_flete.id]['como'], 'envio', 'sin método pero con flete en el pedido')
        self.assertEqual(tarjetas[self.entrega_sin.id]['como'], 'sin_definir', 'nada lo dice: no se adivina')
        self.assertEqual(tarjetas[self.entrega_retiro.id]['como_texto'], 'Retira en la tienda')
        self.assertEqual(tarjetas[self.entrega_envio.id]['como_texto'], 'Envío a domicilio')

    def test_estado_en_palabras_sencillas(self):
        _pedido, parcial = self.venta(self.cliente_sin, [(self.mesa, 9)])   # hay 5 (4 tras las otras ventas)
        tarjetas = self.tarjetas()
        self.assertEqual(tarjetas[self.entrega_envio.id]['estado'], 'lista')
        self.assertEqual(tarjetas[self.entrega_envio.id]['estado_texto'], 'Lista para salir')
        self.assertEqual(tarjetas[self.entrega_sin.id]['estado'], 'esperando')
        self.assertEqual(tarjetas[self.entrega_sin.id]['estado_texto'], 'Esperando producto')
        self.assertEqual(tarjetas[parcial.id]['estado'], 'parcial')
        self.assertEqual(tarjetas[parcial.id]['estado_texto'], 'Falta una parte')

    def test_la_tarjeta_trae_cliente_pedido_fecha_y_productos_sin_precios(self):
        tarjeta = self.tarjetas()[self.entrega_envio.id]
        self.assertEqual(tarjeta['nombre'], self.entrega_envio.name)
        self.assertEqual(tarjeta['cliente'], 'CLIENTE DE PRUEBA ENVIO')
        self.assertEqual(tarjeta['pedido'], self.pedido_envio.name)
        self.assertRegex(tarjeta['fecha'], r'^\d\d/\d\d/\d{4}$')
        self.assertEqual(tarjeta['fecha_tipo'], 'programada', 'sin «Fecha de entrega» en el pedido')
        # Bodega es una pantalla interna: el nombre como se guarda, en MAYÚSCULAS (F5).
        self.assertEqual({(p['nombre'], p['cantidad']) for p in tarjeta['productos']},
                         {('ZZCAMA DE PRUEBA', '2'), ('ZZMESA DE PRUEBA', '1')}, 'sin la referencia delante')
        self.assertEqual(tarjeta['mas'], 0)
        self.assertEqual(set(tarjeta['producto_ids']), {self.cama.id, self.mesa.id})
        for buscado in ('CLIENTE DE PRUEBA ENVIO', self.pedido_envio.name, self.entrega_envio.name):
            self.assertIn(buscado, tarjeta['buscar'])
        self.assertNotIn('50.0', str(tarjeta), 'bodega no ve precios')

    def test_la_fecha_prometida_y_atrasada(self):
        self.pedido_envio.commitment_date = '2020-01-15 15:00:00'
        tarjeta = self.tarjetas()[self.entrega_envio.id]
        self.assertEqual((tarjeta['fecha'], tarjeta['fecha_tipo'], tarjeta['atrasada']),
                         ('15/01/2020', 'prometida', True))
        self.assertEqual(next(iter(self.tarjetas().values()))['id'], self.entrega_envio.id, 'la más vieja primero')

    def test_mas_de_tres_productos_dice_cuantos_mas(self):
        otros = [self.producto(f'Zzsilla {n} de prueba', f'ZZT-SILLA-{n}', unidades=3) for n in range(4)]
        _pedido, entrega = self.venta(self.cliente_sin, [(p, 1) for p in otros])
        tarjeta = self.tarjetas()[entrega.id]
        self.assertEqual((len(tarjeta['productos']), tarjeta['mas']), (3, 1))

    def test_solo_salen_los_pedidos_con_pago_o_abono(self):
        """Decisión de la dueña (2026-10-22): «solo pueden ver el pedido si pagaron o abonaron»."""
        _sin, sin_pago = self.venta(self.cliente_sin, [(self.mesa, 1)], pago=0)
        con_abono_pedido, con_abono = self.venta(self.cliente_sin, [(self.mesa, 1)], pago=0.6)
        sin_cobro_pedido, sin_cobro = self.venta(self.cliente_sin, [(self.mesa, 1)], pago=0)
        sin_cobro_pedido._create_invoices().action_post()   # facturada pero sin ningún cobro: tampoco
        tarjetas = self.tarjetas()
        self.assertNotIn(sin_pago.id, tarjetas)
        self.assertNotIn(sin_cobro.id, tarjetas)
        self.assertEqual((tarjetas[con_abono.id]['pago'], tarjetas[con_abono.id]['pago_texto']),
                         ('abono', 'Con abono: falta una parte'))
        self.assertEqual(tarjetas[self.entrega_envio.id]['pago'], 'pagada')
        self.assertNotIn(str(con_abono_pedido.amount_total), str(tarjetas[con_abono.id]), 'sin montos')
        self.assertEqual(self.Bodega.with_user(self.bodeguero).pendientes()['cuantas'], len(tarjetas))
        atajo = next(a for a in self.env['dcasa.tablero'].with_user(self.bodeguero).obtener_datos()['atajos']
                     if a['clave'] == 'bodega')
        self.assertEqual(atajo['cuenta'], len(tarjetas), 'el Inicio cuenta las mismas')

    def test_una_nota_de_credito_no_es_un_pago(self):
        pedido, entrega = self.venta(self.cliente_sin, [(self.mesa, 1)], pago=0)
        factura = pedido._create_invoices()
        factura.action_post()
        # La nota de crédito se publica y se concilia con la factura (cancel=True): queda «pagada», pero no es dinero.
        factura._reverse_moves([{'invoice_date': factura.invoice_date, 'date': factura.date}], cancel=True)
        self.assertEqual(factura.amount_residual, 0)
        self.assertNotIn(entrega.id, self.tarjetas())

    def test_una_diferencia_de_cambio_no_es_un_pago(self):
        """Una venta en otra moneda: la factura y su nota de crédito con tasas distintas dejan un asiento de diferencia
        de cambio conciliado con la factura. Odoo no lo cuenta como pago (``is_exchange``) y aquí tampoco."""
        euro = self.env.ref('base.EUR')
        euro.active = True
        empresa = self.env.company
        self.env['res.currency.rate'].create([
            {'currency_id': euro.id, 'name': '2026-09-01', 'rate': 0.5, 'company_id': empresa.id},
            {'currency_id': euro.id, 'name': '2026-10-01', 'rate': 1.0, 'company_id': empresa.id},
        ])
        lista = self.env['product.pricelist'].create({'name': 'Lista en euros', 'currency_id': euro.id})
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente_sin.id,
            'pricelist_id': lista.id,
            'order_line': [Command.create({'product_id': self.mesa.id, 'product_uom_qty': 1, 'price_unit': 100.0,
                                           'tax_ids': []})],
        })
        pedido.action_confirm()
        entrega = pedido.picking_ids.filtered(lambda e: e.picking_type_code == 'outgoing')
        factura = pedido._create_invoices()
        factura.write({'invoice_date': '2026-09-15', 'date': '2026-09-15'})
        factura.action_post()
        nota = factura._reverse_moves([{'invoice_date': '2026-10-15', 'date': '2026-10-15'}])
        nota.action_post()
        por_cobrar = (factura + nota).line_ids.filtered(
            lambda linea: linea.account_id.account_type == 'asset_receivable')
        por_cobrar.filtered(lambda linea: not linea.reconciled).reconcile()
        self.assertTrue(por_cobrar.matched_debit_ids.exchange_move_id + por_cobrar.matched_credit_ids.exchange_move_id,
                        'la prueba necesita la diferencia de cambio')
        self.assertEqual(self.Bodega._pago(pedido), 'sin_pago')
        self.assertNotIn(entrega.id, self.tarjetas())

    def test_las_consultas_no_crecen_con_las_entregas(self):
        """Producción, 23 oct: el Inicio de cada persona y el panel (cada minuto) miraban los pagos factura por factura
        y los nombres producto por producto: 1.800 consultas y ~3 s con 230 entregas en el servidor chico, y todo lo
        demás esperaba. Ahora cuántas consultas hacen no depende de cuántas entregas haya."""
        Bodega = self.Bodega.with_user(self.bodeguero)

        def consultas():
            self.env.flush_all()   # lo pendiente de guardar no cuenta
            self.env.invalidate_all()
            antes = self.env.cr.sql_log_count
            Bodega.pendientes()
            Bodega._despachables()   # el número del acceso «Bodega» del Inicio
            return self.env.cr.sql_log_count - antes

        consultas()   # cachés de permisos y vistas
        pocas = consultas()
        tarjetas_antes = len(self.tarjetas())
        otros = [self.producto(f'Zzbanco {n} de prueba', f'ZZT-BANCO-{n}', unidades=3) for n in range(8)]
        for n, producto in enumerate(otros):
            self.venta(self.cliente_sin, [(producto, 1)], pago=0.5 if n % 2 else 1.0)
        consultas()   # crear productos limpia cachés de Odoo: se llenan una vez
        muchas = consultas()
        self.assertEqual(len(self.tarjetas()), tarjetas_antes + 8, 'con pago o abono: salen las 8')
        self.assertLessEqual(muchas - pocas, 2, f'{pocas} → {muchas} consultas con 8 entregas más')

    def test_sin_pago_no_se_abre_ni_se_valida_y_el_qr_lo_dice(self):
        pedido, entrega = self.venta(self.cliente_sin, [(self.mesa, 1)], pago=0)
        Bodega = self.Bodega.with_user(self.bodeguero)
        aviso = f'Este pedido ({pedido.name}) todavía no tiene pago ni abono: no se entrega.'
        with self.assertUserError(aviso):
            Bodega.abrir(entrega.id)
        with self.assertUserError(aviso):
            Bodega.validar(entrega.id, self.marcas(entrega, {self.mesa: 1}))
        for texto in (f'{BASE}/dcasa/doc/ENT/{entrega.name}', entrega.name, pedido.name):
            r = Bodega.leer(texto)
            self.assertEqual((r['resultado'], r['mensaje'], r.get('sin_pago')), ('aviso', aviso, True), texto)
        factura = self.cobrar(pedido, 0.6)   # con un abono ya se abre
        r = self.Bodega.with_user(self.caja).leer(f'{BASE}/dcasa/doc/FAC/{factura.name}')
        self.assertEqual((r['resultado'], r['entrega']['id'], r['entrega']['pago']), ('entrega', entrega.id, 'abono'))
        self.assertEqual(Bodega.validar(entrega.id, self.marcas(entrega, {self.mesa: 1}))['resultado'], 'hecha')

    def test_una_entrega_que_no_viene_de_un_pedido_no_se_despacha_aqui(self):
        clientes = self.env.ref('stock.stock_location_customers')
        suelta = self.env['stock.picking'].create({
            'picking_type_id': self.almacen.out_type_id.id, 'partner_id': self.cliente_sin.id,
            'location_id': self.bodega.id, 'location_dest_id': clientes.id,
            'move_ids': [Command.create({
                'product_id': self.mesa.id, 'product_uom_qty': 1, 'product_uom': self.mesa.uom_id.id,
                'location_id': self.bodega.id, 'location_dest_id': clientes.id})]})
        suelta.action_confirm()
        self.assertNotIn(suelta.id, self.tarjetas())
        with self.assertUserError('no viene de un pedido de venta'):
            self.Bodega.with_user(self.bodeguero).abrir(suelta.id)

    def test_sin_inventario_no_puede_nada(self):
        Bodega = self.Bodega.with_user(self.sin_inventario)
        for llamada in (Bodega.pendientes, lambda: Bodega.abrir(self.entrega_envio.id),
                        lambda: Bodega.leer(f'{BASE}/dcasa/doc/ENT/{self.entrega_envio.name}'),
                        lambda: Bodega.validar(self.entrega_envio.id, self.marcas(self.entrega_envio, {}))):
            with self.assertRaises(AccessError):
                llamada()
        self.assertEqual(self.entrega_envio.state, 'assigned')

    def test_el_menu_esta_en_inventario_y_el_acceso_en_el_inicio(self):
        menu = self.env.ref('dcasa_barras.menu_dcasa_bodega')
        self.assertEqual(menu.parent_id, self.env.ref('stock.menu_stock_root'))
        self.assertEqual(menu.group_ids, self.env.ref('stock.group_stock_user'))
        accion = self.env.ref('dcasa_barras.accion_bodega')
        self.assertEqual((menu.action, accion.tag, accion.path), (accion, 'dcasa_barras_bodega', 'bodega'))
        for usuario in (self.bodeguero, self.vendedora, self.gerencia):
            atajos = self.env['dcasa.tablero'].with_user(usuario).obtener_datos()['atajos']
            claves = [a['clave'] for a in atajos]
            self.assertIn('bodega', claves, usuario.login)
            self.assertEqual(claves.index('bodega') + 1, claves.index('escaner'), 'justo antes del Escáner')
            bodega = atajos[claves.index('bodega')]
            self.assertEqual((bodega['titulo'], bodega['accion'], bodega['icono']),
                             ('Bodega', 'dcasa_barras.accion_bodega', 'fa-truck'))
        bodega = next(a for a in self.env['dcasa.tablero'].with_user(self.bodeguero).obtener_datos()['atajos']
                      if a['clave'] == 'bodega')
        cuantas = len(self.tarjetas())
        self.assertEqual((bodega['cuenta'], bodega['detalle']), (cuantas, f'{cuantas} entregas por despachar'))
        sin = [a['clave'] for a in self.env['dcasa.tablero'].with_user(self.sin_inventario).obtener_datos()['atajos']]
        self.assertNotIn('bodega', sin)

    def test_el_retiro_en_tienda_de_la_web_es_retiro(self):
        servicio = self.env['product.product'].create({'name': 'Zz otra entrega', 'type': 'service'})
        retiro = self.env['delivery.carrier'].create({
            'name': 'Retiro en tienda (Zz prueba)', 'product_id': servicio.id, 'delivery_type': 'fixed'})
        domicilio = self.env['delivery.carrier'].create({
            'name': 'Entrega a domicilio Zz', 'product_id': servicio.id, 'delivery_type': 'fixed'})
        self.env['delivery.carrier']._dcasa_marcar_retiro_inicial()
        self.assertTrue(retiro.dcasa_es_retiro)
        self.assertFalse(domicilio.dcasa_es_retiro)
        # El de la tienda web (website_dcasa) ya quedó marcado al instalar.
        web = self.env['delivery.carrier'].with_context(active_test=False).search(
            [('name', '=', 'Retiro en tienda (La Chorrera)')])
        self.assertTrue(all(web.mapped('dcasa_es_retiro')))


@tagged('post_install', '-at_install')
class TestBodegaAbrirYLeer(BodegaCommon):

    def leer(self, texto, usuario=None, abierta=False):
        return self.Bodega.with_user(usuario or self.bodeguero).leer(texto, abierta)

    def test_abrir_trae_cliente_telefono_direccion_y_productos(self):
        detalle = self.Bodega.with_user(self.bodeguero).abrir(self.entrega_envio.id)
        self.assertEqual((detalle['cliente'], detalle['telefono'], detalle['pedido']),
                         ('CLIENTE DE PRUEBA ENVIO', '6000-0001', self.pedido_envio.name))
        self.assertIn('Calle de prueba 1', detalle['direccion'])
        self.assertIn('La Chorrera', detalle['direccion'])
        self.assertEqual((detalle['estado'], detalle['como'], detalle['deja_pendiente']), ('lista', 'envio', True))
        lineas = {linea['producto_id']: linea for linea in detalle['lineas']}
        self.assertEqual(set(lineas), {self.cama.id, self.mesa.id})
        cama = lineas[self.cama.id]
        self.assertEqual((cama['pedida'], cama['pedida_texto'], cama['apartada'], cama['unidad']), (2.0, '2', 2.0, ''))
        self.assertEqual(cama['codigo'], 'ZZT-CAMA-1')
        self.assertEqual(cama['foto'], f'/web/image/product.product/{self.cama.id}/image_128')
        self.assertEqual(detalle['imprimir']['report_name'], 'stock.report_deliveryslip')
        self.assertNotIn('50.0', str(detalle), 'bodega no ve precios')

    def test_abrir_una_recepcion_o_algo_que_no_existe_avisa(self):
        recepcion = self.env['stock.picking'].create({
            'picking_type_id': self.almacen.in_type_id.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.almacen.lot_stock_id.id})
        Bodega = self.Bodega.with_user(self.bodeguero)
        with self.assertUserError('no es una entrega a un cliente'):
            Bodega.abrir(recepcion.id)
        with self.assertUserError('ya no existe'):
            Bodega.abrir(999999999)
        with self.assertUserError('no existe'):
            Bodega.abrir('1')

    def test_el_qr_de_la_nota_de_entrega_la_abre(self):
        nombre = self.entrega_envio.name
        for texto in (f'{BASE}/dcasa/doc/ENT/{nombre}', f'/dcasa/doc/ent/{nombre.lower()}',
                      f'httpsÑ--x.co-dcasa-doc-ENT-{nombre.replace("/", "_")}'):
            r = self.leer(texto)
            self.assertEqual((r['resultado'], r['entrega']['id']), ('entrega', self.entrega_envio.id), texto)
        self.assertEqual(self.leer(f'{BASE}/dcasa/doc/ENT/{nombre}', abierta=self.entrega_envio.id)['resultado'],
                         'misma')

    def test_el_qr_de_una_entrega_ya_hecha_o_que_no_existe_solo_avisa(self):
        self.Bodega.with_user(self.bodeguero).validar(
            self.entrega_retiro.id, self.marcas(self.entrega_retiro, {self.mesa: 1}))
        r = self.leer(f'{BASE}/dcasa/doc/ENT/{self.entrega_retiro.name}')
        self.assertEqual(r['resultado'], 'aviso')
        self.assertIn('ya se entregó', r['mensaje'])
        r = self.leer(f'{BASE}/dcasa/doc/ENT/WH/OUT/99999')
        self.assertEqual(r['resultado'], 'aviso')
        self.assertIn('No encontramos', r['mensaje'])

    def test_el_qr_de_la_factura_abre_su_entrega_si_puedes_ver_la_factura(self):
        factura = self.pedido_flete.invoice_ids[:1]   # la factura ya cobrada de la venta de prueba
        url = f'{BASE}/dcasa/doc/FAC/{factura.name}'
        r = self.leer(url, usuario=self.caja)
        self.assertEqual((r['resultado'], r['entrega']['id']), ('entrega', self.entrega_flete.id))
        r = self.leer(url)   # bodega pura no lee facturas: solo el aviso, nada del documento
        self.assertEqual(r['resultado'], 'aviso')
        self.assertIn('No tienes permiso', r['mensaje'])
        self.assertNotIn('CLIENTE', str(r))
        r = self.leer(f'{BASE}/dcasa/doc/COT/{self.pedido_retiro.name}', usuario=self.caja)
        self.assertEqual((r['resultado'], r['entrega']['id']), ('entrega', self.entrega_retiro.id))

    def test_el_qr_con_la_camara_del_telefono_o_el_escaner_abre_bodega(self):
        """Decisión de la dueña (2026-10-22): el QR de la nota de entrega abre esa entrega en el panel de Bodega para
        quien usa Inventario (la cámara normal del teléfono y el Escáner). Quien no usa Inventario, una recepción y
        los demás documentos siguen abriendo su formulario de Odoo."""
        Documento = self.env['dcasa.documento']
        entrega = self.entrega_envio
        self.assertEqual(Documento.with_user(self.bodeguero)._dcasa_ruta_odoo(entrega), f'/odoo/bodega/{entrega.id}')
        solo_ventas = new_test_user(self.env, login='bodega_solo_ventas', groups='sales_team.group_sale_salesman')
        self.assertTrue(Documento.with_user(solo_ventas)._dcasa_ruta_odoo(entrega).startswith('/odoo/action-'))
        recepcion = self.env['stock.picking'].create({
            'picking_type_id': self.almacen.in_type_id.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.almacen.lot_stock_id.id})
        self.assertTrue(Documento.with_user(self.bodeguero)._dcasa_ruta_odoo(recepcion).startswith('/odoo/action-'))
        r = self.env['dcasa.barras'].with_user(self.bodeguero).buscar(f'{BASE}/dcasa/doc/ENT/{entrega.name}')
        accion = r['documento']['accion']
        self.assertEqual((r['resultado'], accion['type'], accion['tag'], accion['path'], accion['params']),
                         ('documento', 'ir.actions.client', 'dcasa_barras_bodega', 'bodega',
                          {'entrega_id': entrega.id}))
        factura = self.pedido_envio.invoice_ids[:1]
        r = self.env['dcasa.barras'].with_user(self.caja).buscar(f'{BASE}/dcasa/doc/FAC/{factura.name}')
        self.assertEqual((r['documento']['accion']['res_model'], r['documento']['accion']['res_id']),
                         ('account.move', factura.id), 'la factura sigue abriendo la factura')

    def test_el_numero_de_la_entrega_o_del_pedido_la_abre(self):
        self.assertEqual(self.leer(self.entrega_sin.name)['entrega']['id'], self.entrega_sin.id)
        self.assertEqual(self.leer(self.entrega_sin.name.lower())['entrega']['id'], self.entrega_sin.id)
        self.assertEqual(self.leer(self.pedido_sin.name)['entrega']['id'], self.entrega_sin.id)

    def test_el_codigo_de_un_producto_lo_dice(self):
        r = self.leer('ZZT-CAMA-1')
        self.assertEqual((r['resultado'], r['producto_ids'], r['nombre']),
                         ('producto', [self.cama.id], 'ZZCAMA DE PRUEBA'))
        r = self.leer('ZZT-MESA-9-BAR')
        self.assertEqual(r['producto_ids'], [self.mesa.id])
        self.assertEqual(self.leer('algo que no es nada')['resultado'], 'nada')
        self.assertEqual(self.leer('')['resultado'], 'nada')
        self.assertEqual(self.leer(None)['resultado'], 'nada')


@tagged('post_install', '-at_install')
class TestBodegaValidar(BodegaCommon):

    def validar(self, entrega, cantidades, parcial=False, usuario=None):
        return self.Bodega.with_user(usuario or self.bodeguero).validar(
            entrega.id, self.marcas(entrega, cantidades), parcial)

    def test_todo_marcado_se_valida_y_queda_quien_fue(self):
        r = self.validar(self.entrega_envio, {self.cama: 2, self.mesa: 1})
        self.assertEqual((r['resultado'], r['pendiente']), ('hecha', False))
        self.assertIn('quedó entregada completa', r['mensaje'])
        self.assertEqual(r['imprimir']['report_name'], 'stock.report_deliveryslip')
        entrega = self.entrega_envio
        self.assertEqual(entrega.state, 'done')
        self.assertTrue(entrega.date_done)
        self.assertEqual({m.product_id: m.quantity for m in entrega.move_ids}, {self.cama: 2, self.mesa: 1})
        self.assertFalse(entrega.backorder_ids)
        nota = entrega.message_ids.filtered(lambda m: 'panel de Bodega' in (m.body or ''))
        self.assertEqual(nota.author_id, self.bodeguero.partner_id, 'queda quién la despachó')
        self.assertEqual(self.existencia(self.cama), 12 - 2, 'salió de la bodega (lo apartado para el flete sigue ahí)')
        self.assertNotIn(entrega.id, self.tarjetas())

    def test_si_falta_algo_primero_pregunta_y_no_toca_nada(self):
        r = self.validar(self.entrega_envio, {self.cama: 1, self.mesa: 1})
        self.assertEqual(r['resultado'], 'confirmar_parcial')
        self.assertEqual(r['faltan'], [{'nombre': 'ZZCAMA DE PRUEBA', 'marcada': '1', 'pedida': '2'}])
        self.assertTrue(r['deja_pendiente'])
        self.assertEqual(self.entrega_envio.state, 'assigned')
        self.assertFalse(any(self.entrega_envio.move_ids.mapped('picked')))
        self.assertEqual(sum(self.entrega_envio.move_ids.mapped('quantity')), 3, 'lo apartado sigue igual')

    def test_entregar_solo_lo_marcado_deja_lo_demas_pendiente(self):
        r = self.validar(self.entrega_envio, {self.cama: 1}, parcial=True)
        entrega = self.entrega_envio
        pendiente = entrega.backorder_ids
        self.assertEqual(entrega.state, 'done')
        self.assertEqual(len(pendiente), 1)
        self.assertEqual((r['resultado'], r['pendiente'], r['pendiente_id']), ('hecha', pendiente.name, pendiente.id))
        self.assertIn(pendiente.name, r['mensaje'])
        self.assertEqual({m.product_id: m.quantity for m in entrega.move_ids if m.state == 'done'}, {self.cama: 1})
        self.assertEqual({m.product_id: m.product_uom_qty for m in pendiente.move_ids}, {self.cama: 1, self.mesa: 1})
        self.assertIn(pendiente.state, ('assigned', 'confirmed'))
        tarjeta = self.tarjetas()[pendiente.id]
        self.assertEqual((tarjeta['pendiente_de'], tarjeta['como'], tarjeta['pedido']),
                         (entrega.name, 'envio', self.pedido_envio.name))
        nota = entrega.message_ids.filtered(lambda m: 'panel de Bodega' in (m.body or ''))
        self.assertIn('salieron 1 de 2', nota.body)
        self.assertIn(pendiente.name, nota.body)

    def test_no_se_entrega_mas_de_lo_pedido_ni_nada_raro(self):
        entrega = self.entrega_envio
        Bodega = self.Bodega.with_user(self.bodeguero)
        with self.assertUserError('no puedes entregar más de lo pedido'):
            self.validar(entrega, {self.cama: 3, self.mesa: 1})
        with self.assertUserError('Marca lo que sale'):
            self.validar(entrega, {})
        ajena = self.entrega_retiro.move_ids[:1]
        with self.assertUserError('cambió mientras la tenías abierta'):
            Bodega.validar(entrega.id, [{'id': ajena.id, 'cantidad': 1}])
        for mala in (-1, True, '2', float('nan'), None):
            with self.assertUserError('no es válida'):
                Bodega.validar(entrega.id, [{'id': entrega.move_ids[0].id, 'cantidad': mala}])
        for basura in ('x', [1], {'id': 1}):
            with self.assertUserError('No se entendió'):
                Bodega.validar(entrega.id, basura)
        self.assertEqual(entrega.state, 'assigned', 'nada se validó')

    def test_una_entrega_ya_validada_no_se_valida_otra_vez(self):
        self.validar(self.entrega_retiro, {self.mesa: 1})
        with self.assertUserError('ya se entregó'):
            self.validar(self.entrega_retiro, {self.mesa: 1})

    def test_sale_aunque_el_sistema_no_lo_tenga_y_queda_anotado(self):
        r = self.validar(self.entrega_sin, {self.zapatera: 1})
        self.assertEqual(r['resultado'], 'hecha')
        self.assertEqual(self.entrega_sin.state, 'done')
        nota = self.entrega_sin.message_ids.filtered(lambda m: 'panel de Bodega' in (m.body or ''))
        self.assertIn('sin estar apartado', nota.body)
        self.assertIn('ZZZAPATERA DE PRUEBA', nota.body)

    def test_un_producto_con_numero_de_serie_no_sale_sin_su_numero(self):
        serie = self.producto('Zzcolchon con serie', 'ZZT-SERIE-1', tracking='serial')
        _pedido, entrega = self.venta(self.cliente_sin, [(serie, 1)])
        with self.assertUserError('número de serie'):
            self.validar(entrega, {serie: 1})
        self.assertNotEqual(entrega.state, 'done')

    def test_la_vendedora_tambien_despacha(self):
        r = self.validar(self.entrega_retiro, {self.mesa: 1}, usuario=self.vendedora)
        self.assertEqual(r['resultado'], 'hecha')
