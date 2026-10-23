"""Herramientas de dominio de Brian, ejecutadas como las usaría el modelo: ``ejecutar(nombre, args)``."""
from odoo import Command
from odoo.addons.dcasa_brian.models import herramientas_comun as c
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestHerramientas(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login,
                                    'group_ids': [Command.set([ref(g).id for g in ('base.group_user', *grupos)])]})

        cls.vendedor = usuario('brian_h_vendedor', ('sales_team.group_sale_salesman', 'stock.group_stock_user'))
        cls.contador = usuario('brian_h_contador', ('account.group_account_manager',
                                                    'sales_team.group_sale_salesman_all_leads'))
        cls.gerente = usuario('brian_h_gerente', ('base.group_system', 'sales_team.group_sale_manager',
                                                  'account.group_account_manager', 'stock.group_stock_manager'))
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        Template = cls.env['product.template']
        base = {'type': 'consu', 'is_storable': True, 'taxes_id': [Command.set(impuesto.ids)]}
        cls.sofa = Template.create({**base, 'name': 'Brianzeta Sofá Prueba', 'default_code': 'BRN-SOF',
                                    'list_price': 107.0, 'dcasa_medidas': '200 × 90 × 85 cm'})
        cls.mesa_a = Template.create({**base, 'name': 'Brianzeta Mesa Roble', 'list_price': 50.0})
        cls.mesa_b = Template.create({**base, 'name': 'Brianzeta Mesa Pino', 'list_price': 40.0})
        # Con celular y correo: sin ellos no se confirma la venta ni se publica la factura (dcasa_contactos).
        cls.cliente = cls.env['res.partner'].create({'name': 'Brianzeta Cliente Uno', 'phone': '6123-4501',
                                                     'email': 'brianzeta.uno@example.com'})

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def confirmar(self, usuario, respuesta):
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        return self.env['brian.herramientas'].with_user(usuario).confirmar(respuesta['accion_id'])

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    # ------------------------------------------------------------------
    # Contrato del catálogo
    # ------------------------------------------------------------------

    def test_contrato_para_modelos_pequenos(self):
        """Verbo_objeto, ≤5 parámetros de tipos simples y descripciones cortas."""
        simples = {'string', 'number', 'integer', 'boolean'}
        mias = {'ventas', 'catalogo', 'clientes', 'contabilidad', 'usuarios'}
        for nombre, spec in self.env['brian.herramientas']._todas().items():
            if spec['categoria'] not in mias and nombre not in ('buscar_en_todo', 'abrir'):
                continue
            if nombre.startswith(('prueba_', 'eliminar_prueba')):
                continue
            self.assertLessEqual(len(spec['parametros']), 5, nombre)
            self.assertEqual(nombre, nombre.lower(), nombre)
            # Las herramientas de Juan (``juan_*``, solo para su usuario técnico) comparten el registro. Una cotización
            # lleva varios productos: su única lista de líneas (``juan_cotizar.lineas``) es la excepción; el Worker de
            # Juan la prueba con su propio contrato y le devuelve al modelo el texto para corregirse (422).
            tipos = simples | {'array'} if nombre.startswith('juan_') else simples
            for parametro, esquema in spec['parametros'].items():
                self.assertIn(esquema['type'], tipos, f'{nombre}.{parametro}')
                self.assertTrue(esquema.get('description'), f'{nombre}.{parametro}')
            self.assertLess(len(spec['descripcion']), 260, nombre)

    def test_vendedor_no_ve_usuarios_ni_contabilidad(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedor).catalogo()}
        self.assertIn('crear_cotizacion', nombres)
        self.assertIn('buscar_productos', nombres)
        for prohibida in ('listar_usuarios', 'cambiar_rol_usuario', 'reporte_contable', 'publicar_factura',
                          'registrar_pago', 'conciliar_movimiento', 'guia_cierre_mes', 'ajustar_existencias'):
            self.assertNotIn(prohibida, nombres)
        respuesta = self.ejecutar(self.vendedor, 'listar_usuarios')
        self.assertFalse(respuesta['ok'])
        self.assertIn('no tienes permiso', respuesta['error'])

    # ------------------------------------------------------------------
    # Ventas
    # ------------------------------------------------------------------

    def test_reporte_del_dia_coincide_con_tablero(self):
        # De la vendedora: sus reglas de registro le muestran sus propias ventas.
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': self.vendedor.id,
            'order_line': [Command.create({'product_id': self.sofa.product_variant_id.id, 'product_uom_qty': 2})]})
        orden.action_confirm()
        # «Vendido» es lo facturado por completo (2026-10-15): confirmada y por facturar todavía no suma.
        orden._create_invoices().action_post()
        datos = self.ok(self.ejecutar(self.vendedor, 'reporte_del_dia'))
        tablero = self.env['dcasa.tablero'].with_user(self.vendedor).obtener_datos()
        vendido = next(x for x in tablero['cifras'] if x['clave'] == 'ventas_hoy')
        fila = next(x for x in datos['cifras'] if x['titulo'] == vendido['titulo'])
        self.assertEqual(fila['valor'], c.moneda(vendido['valor']))
        self.assertGreaterEqual(vendido['valor'], 214.0)
        self.assertEqual(len(datos['cifras']), len(tablero['cifras']))

    def test_cotizacion_de_punta_a_punta(self):
        datos = self.ok(self.ejecutar(self.vendedor, 'crear_cotizacion', {
            'cliente': '6123 4501', 'producto': 'BRN-SOF', 'cantidad': 2}))
        numero = datos['numero']
        self.assertEqual(datos['cliente'], 'Brianzeta Cliente Uno')
        self.assertEqual(datos['total'], '$228.98')  # 2 × $107 + ITBMS 7 % que se suma
        datos = self.ok(self.ejecutar(self.vendedor, 'agregar_linea_cotizacion', {
            'venta': numero, 'producto': 'Brianzeta Mesa Roble', 'precio': 45}))
        self.assertEqual(datos['total'], '$277.13')  # (214 + 45) + 18.13 de ITBMS
        datos = self.ok(self.ejecutar(self.vendedor, 'quitar_linea_cotizacion', {'venta': numero, 'producto': 'mesa'}))
        self.assertEqual(len(datos['lineas']), 1)
        # Confirmar es sensible: primero propone, luego el humano confirma.
        respuesta = self.ejecutar(self.vendedor, 'confirmar_venta', {'venta': numero})
        orden = self.env['sale.order'].search([('name', '=', numero)])
        self.assertEqual(orden.state, 'draft')
        self.ok(self.confirmar(self.vendedor, respuesta))
        self.assertEqual(orden.state, 'sale')
        # Ya confirmada: no se cambia ni se cancela desde Brian.
        self.assertFalse(self.ejecutar(self.vendedor, 'agregar_linea_cotizacion', {
            'venta': numero, 'producto': 'BRN-SOF'})['ok'])
        respuesta = self.confirmar(self.vendedor, self.ejecutar(self.vendedor, 'cancelar_cotizacion',
                                                                {'venta': numero}))
        self.assertFalse(respuesta['ok'])
        self.assertIn('una persona', respuesta['error'])
        datos = self.ok(self.ejecutar(self.vendedor, 'buscar_ventas', {'texto': 'Brianzeta', 'estado': 'confirmada'}))
        self.assertIn(numero, [v['numero'] for v in datos['ventas']])

    def test_precio_libre_respeta_el_tope_de_descuento(self):
        """H-02: Brian actúa como la vendedora; el tope del modelo (10 %) también lo frena a él."""
        self.env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        Order = self.env['sale.order']
        antes = Order.search_count([])
        respuesta = self.ejecutar(self.vendedor, 'crear_cotizacion', {
            'cliente': 'Brianzeta Cliente Uno', 'producto': 'BRN-SOF', 'precio': 53.5})  # 50 % de 107
        self.assertFalse(respuesta['ok'])
        self.assertIn('Gerencia', respuesta['error'])
        self.assertEqual(Order.search_count([]), antes, 'La cotización a medias se deshace')
        numero = self.ok(self.ejecutar(self.vendedor, 'crear_cotizacion', {
            'cliente': 'Brianzeta Cliente Uno', 'producto': 'BRN-SOF', 'precio': 96.3}))['numero']  # 10 %: vale
        respuesta = self.ejecutar(self.vendedor, 'agregar_linea_cotizacion', {
            'venta': numero, 'producto': 'Brianzeta Mesa Roble', 'precio': 44.99})
        self.assertFalse(respuesta['ok'])
        self.assertIn('Gerencia', respuesta['error'])
        self.assertEqual(len(Order.search([('name', '=', numero)]).order_line), 1)
        # Gerencia (admin de Ventas) sí puede dar más.
        datos = self.ok(self.ejecutar(self.gerente, 'agregar_linea_cotizacion', {
            'venta': numero, 'producto': 'Brianzeta Mesa Roble', 'precio': 25}))
        self.assertEqual(datos['lineas'][-1]['precio'], '$25.00')

    def test_whatsapp_devuelve_enlace(self):
        datos = self.ok(self.ejecutar(self.vendedor, 'crear_cotizacion', {
            'cliente': 'Brianzeta Cliente Uno', 'producto': 'BRN-SOF'}))
        datos = self.ok(self.ejecutar(self.vendedor, 'enviar_cotizacion_whatsapp', {'venta': datos['numero']}))
        self.assertTrue(datos['enlace'].startswith('https://wa.me/50761234501?text='))
        self.assertEqual(datos['abrir']['url'], datos['enlace'])

    def test_resolucion_ambigua_da_opciones(self):
        respuesta = self.ejecutar(self.vendedor, 'ver_producto', {'producto': 'Brianzeta Mesa'})
        self.assertFalse(respuesta['ok'])
        # Los nombres de productos se guardan en MAYÚSCULAS (F5).
        self.assertIn('BRIANZETA MESA ROBLE', respuesta['error'])
        self.assertIn('BRIANZETA MESA PINO', respuesta['error'])
        respuesta = self.ejecutar(self.vendedor, 'ver_producto', {'producto': 'zzz-no-existe-zzz'})
        self.assertIn('No encontré', respuesta['error'])

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------

    def test_ver_y_buscar_productos(self):
        datos = self.ok(self.ejecutar(self.vendedor, 'ver_producto', {'producto': 'brn-sof'}))
        self.assertEqual(datos['medidas'], '200 × 90 × 85 cm')
        # El precio de lista es sin ITBMS: el 7 % se suma encima.
        self.assertFalse(self.sofa.taxes_id.price_include)
        self.assertEqual(datos['precio_sin_itbms'], '$107.00')
        self.assertEqual(datos['precio_con_itbms'], '$114.49')
        datos = self.ok(self.ejecutar(self.vendedor, 'buscar_productos', {
            'texto': 'Brianzeta', 'precio_max': 60, 'disponibilidad': 'agotados'}))
        self.assertEqual({p['producto'] for p in datos['productos']}, {'BRIANZETA MESA ROBLE', 'BRIANZETA MESA PINO'})

    def test_catalogo_constructor_y_sensibles(self):
        self.assertFalse(self.ejecutar(self.vendedor, 'crear_producto', {'nombre': 'X', 'precio': 1})['ok'])
        datos = self.ok(self.ejecutar(self.gerente, 'crear_producto', {
            'nombre': 'Brianzeta Silla Nueva', 'precio': 25.5, 'codigo': 'BRN-SIL'}))
        self.assertFalse(datos['publicado_en_web'])
        # El precio que dicta la dueña es sin ITBMS: el producto lleva el ITBMS por defecto, que se suma.
        self.assertEqual((datos['precio_sin_itbms'], datos['precio_con_itbms']), ('$25.50', '$27.29'))
        nueva = self.env['product.template'].search([('default_code', '=', 'BRN-SIL')])
        self.assertEqual(nueva.taxes_id, self.env.company.account_sale_tax_id)
        self.assertFalse(nueva.taxes_id.price_include)
        respuesta = self.ejecutar(self.gerente, 'crear_producto', {'nombre': 'Otra', 'precio': 1, 'codigo': 'brn-sil'})
        self.assertIn('Ya existe', respuesta['error'])
        self.ok(self.ejecutar(self.gerente, 'actualizar_producto', {
            'producto': 'BRN-SIL', 'campo': 'precio', 'valor': '$29.99'}))
        silla = self.env['product.template'].search([('default_code', '=', 'BRN-SIL')])
        self.assertEqual(silla.list_price, 29.99)
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'publicar_producto_web', {
            'producto': 'BRN-SIL', 'publicar': True})))
        self.assertTrue(silla.is_published)
        almacenes = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)])
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'ajustar_existencias', {
            'producto': 'BRN-SIL', 'cantidad': 4, 'almacen': almacenes[:1].name, 'motivo': 'conteo de prueba'})))
        self.assertEqual(silla.qty_available, 4)

    # ------------------------------------------------------------------
    # Clientes y puntos
    # ------------------------------------------------------------------

    def test_crear_cliente_no_duplica_celular(self):
        for celular in ('6123-4501', '+507 6123 4501'):
            respuesta = self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Duplicado', 'celular': celular,
                                                                       'correo': 'duplicado@example.com'})
            self.assertFalse(respuesta['ok'])
            self.assertIn('Brianzeta Cliente Uno', respuesta['error'])
        datos = self.ok(self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Brianzeta Nueva',
                                                                       'celular': '61234502',
                                                                       'correo': 'brianzeta.nueva@example.com'}))
        self.assertEqual(datos['celular'], '6123-4502')
        respuesta = self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Nueva', 'campo': 'celular', 'valor': '6123-4501'})
        self.assertFalse(respuesta['ok'])
        respuesta = self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Y', 'celular': '123',
                                                                   'correo': 'y@example.com'})
        self.assertIn('en Panamá son 8 números', respuesta['error'])

    def test_crear_cliente_con_celular_y_correo_bien_escritos(self):
        """Celular y correo obligatorios y bien escritos (pedido de la dueña, 2026-10-16), como en la ficha."""
        respuesta = self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Brianzeta Sin Correo',
                                                                   'celular': '6123-4503'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('correo', respuesta['error'])
        respuesta = self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Brianzeta Dedo', 'celular': '6123-4503',
                                                                   'correo': 'dedo@gmial.com'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('¿Quisiste decir dedo@gmail.com?', respuesta['error'])
        datos = self.ok(self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Brianzeta Limpia',
                                                                       'celular': '6123 4503',
                                                                       'correo': ' Limpia@Example.com '}))
        ficha = self.env['res.partner'].search([('name', '=', 'Brianzeta Limpia')])
        self.assertEqual((ficha.phone, ficha.email), ('+507 6123-4503', 'limpia@example.com'))
        self.assertEqual(datos['correo'], 'limpia@example.com')
        extranjero = self.ok(self.ejecutar(self.vendedor, 'crear_cliente', {
            'nombre': 'Brianzeta Miami', 'celular': '+1 305 555 1234', 'correo': 'miami@example.com'}))
        self.assertEqual(extranjero['celular'], '+13055551234')
        respuesta = self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Limpia', 'campo': 'correo', 'valor': 'limpia@hotmail.con'})
        self.assertIn('¿Quisiste decir limpia@hotmail.com?', respuesta['error'])

    def test_cliente_con_telefono_fijo(self):
        """Un cliente sin celular, con teléfono fijo de 7 números (la dueña, 2026-10-22): Brian lo crea igual que la
        ficha, y un fijo escrito como «celular» va a su campo."""
        datos = self.ok(self.ejecutar(self.vendedor, 'crear_cliente', {
            'nombre': 'Brianzeta Fijo', 'celular': '234 5678', 'correo': 'fijo@example.com'}))
        self.assertEqual((datos['celular'], datos['telefono_fijo']), ('', '+507 234-5678'))
        ficha = self.env['res.partner'].search([('name', '=', 'Brianzeta Fijo')])
        self.assertEqual((ficha.phone, ficha.dcasa_telefono_fijo), (False, '+507 234-5678'))
        # «Brianzeta Fijo Dos» se parece a «Brianzeta Fijo» (Etapa 3): ya confirmado que es otra persona, se usa
        # crear_cliente_distinto, que trata el fijo igual.
        datos = self.ok(self.ejecutar(self.vendedor, 'crear_cliente_distinto', {
            'nombre': 'Brianzeta Fijo Dos', 'celular': '2345679', 'correo': 'fijo2@example.com'}))
        self.assertEqual((datos['celular'], datos['telefono_fijo']), ('', '+507 234-5679'))
        respuesta = self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Brianzeta Sin Números', 'celular': '',
                                                                   'correo': 'sinnumeros@example.com'})
        self.assertFalse(respuesta['ok'])
        respuesta = self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Fijo', 'campo': 'telefono_fijo', 'valor': '6123-4567'})
        self.assertIn('es un celular', respuesta['error'])
        datos = self.ok(self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Cliente Uno', 'campo': 'telefono_fijo', 'valor': '734-5678'}))
        self.assertEqual(datos['telefono_fijo'], '+507 734-5678')
        self.assertIn('el teléfono fijo', datos['mensaje'])
        encontrados = self.ok(self.ejecutar(self.vendedor, 'buscar_clientes', {'texto': '234-5678'}))
        self.assertIn('Brianzeta Fijo', [c['nombre'] for c in encontrados['contactos']])

    def test_cliente_que_no_tiene_correo(self):
        """«no tiene» en el correo marca «Cliente no tiene correo electrónico» (decisión de la dueña, 2026-10-17)."""
        datos = self.ok(self.ejecutar(self.vendedor, 'crear_cliente', {
            'nombre': 'Brianzeta Abuela', 'celular': '6123-4504', 'correo': 'No tiene'}))
        self.assertTrue(datos['no_tiene_correo'])
        ficha = self.env['res.partner'].search([('name', '=', 'Brianzeta Abuela')])
        self.assertTrue(ficha.dcasa_sin_correo)
        self.assertFalse(ficha.email)
        # El celular sigue siendo obligatorio.
        respuesta = self.ejecutar(self.vendedor, 'crear_cliente', {'nombre': 'Brianzeta Sin Nada', 'celular': '',
                                                                   'correo': 'no tiene'})
        self.assertFalse(respuesta['ok'])
        # A una ficha que ya existe: con un correo bueno no se borra; con uno de relleno, sí.
        respuesta = self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Cliente Uno', 'campo': 'correo', 'valor': 'uno@example.com'})
        self.assertTrue(respuesta['ok'], respuesta)
        respuesta = self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Cliente Uno', 'campo': 'correo', 'valor': 'sin correo'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('ya tiene el correo uno@example.com', respuesta['error'])
        self.cliente.with_context(dcasa_sin_exigir_contacto=True).email = 'no@no.com'
        datos = self.ok(self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Cliente Uno', 'campo': 'correo', 'valor': 'sin correo'}))
        self.assertTrue(datos['no_tiene_correo'])
        self.assertFalse(self.cliente.email)
        # Y si después le escriben un correo, la casilla se desmarca sola.
        self.ok(self.ejecutar(self.vendedor, 'actualizar_cliente', {
            'cliente': 'Brianzeta Cliente Uno', 'campo': 'correo', 'valor': 'uno.nuevo@example.com'}))
        self.assertFalse(self.cliente.dcasa_sin_correo)

    def test_puntos_se_leen_del_libro_y_se_ajustan_con_el_asistente(self):
        ficha = self.cliente._dcasa_asegurar_ficha()
        datos = self.ok(self.ejecutar(self.vendedor, 'saldo_puntos', {'cliente': ficha.dcasa_socio_codigo}))
        self.assertEqual(datos['puntos'], ficha.dcasa_saldo)
        self.assertEqual(datos['puntos'], sum(ficha.dcasa_movimiento_ids.mapped('puntos')))
        # Un vendedor no ajusta puntos; un gerente sí, con confirmación y como asiento nuevo.
        self.assertNotIn('ajustar_puntos', {h['name'] for h in
                                            self.env['brian.herramientas'].with_user(self.vendedor).catalogo()})
        antes = len(ficha.dcasa_movimiento_ids)
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'ajustar_puntos', {
            'cliente': 'Brianzeta Cliente Uno', 'puntos': 150, 'motivo': 'Compra no registrada'})))
        ficha.invalidate_recordset()
        self.assertEqual(len(ficha.dcasa_movimiento_ids), antes + 1)
        self.assertEqual(ficha.dcasa_saldo, datos['puntos'] + 150)

    # ------------------------------------------------------------------
    # Contabilidad
    # ------------------------------------------------------------------

    def test_factura_publicada_no_se_edita(self):
        datos = self.ok(self.ejecutar(self.contador, 'crear_factura', {
            'tipo': 'cliente', 'tercero': 'Brianzeta Cliente Uno', 'producto': 'BRN-SOF'}))
        referencia = datos['factura']
        self.assertEqual(datos['estado'], 'borrador')
        self.ok(self.ejecutar(self.contador, 'agregar_linea_factura', {
            'factura': referencia, 'producto': 'Brianzeta Mesa Pino', 'cantidad': 2}))
        self.ok(self.ejecutar(self.contador, 'editar_factura', {
            'factura': referencia, 'campo': 'vencimiento', 'valor': '31/12/2026'}))
        respuesta = self.ejecutar(self.contador, 'publicar_factura', {'factura': referencia})
        publicada = self.ok(self.confirmar(self.contador, respuesta))
        self.assertEqual(publicada['total'], '$200.09')  # 107 + 2 × 40 + 13.09 de ITBMS
        numero = publicada['factura']
        for nombre, argumentos in (('editar_factura', {'campo': 'referencia', 'valor': 'X'}),
                                   ('agregar_linea_factura', {'producto': 'BRN-SOF'}),
                                   ('quitar_linea_factura', {'producto': 'BRN-SOF'})):
            respuesta = self.ejecutar(self.contador, nombre, {'factura': numero, **argumentos})
            self.assertFalse(respuesta['ok'], nombre)
            self.assertIn('nota de crédito', respuesta['error'])
        # Pago parcial y luego el resto.
        self.ok(self.confirmar(self.contador, self.ejecutar(self.contador, 'registrar_pago', {
            'factura': numero, 'monto': 100.09, 'forma_pago': 'Efectivo'})))
        factura = self.env['account.move'].search([('name', '=', numero)])
        self.assertEqual(factura.amount_residual, 100.0)
        pagada = self.ok(self.confirmar(self.contador, self.ejecutar(self.contador, 'registrar_pago', {
            'factura': numero, 'forma_pago': 'Efectivo'})))
        self.assertEqual(pagada['pendiente'], '$0.00')
        datos = self.ok(self.ejecutar(self.contador, 'ver_factura', {'factura': numero}))
        self.assertEqual(datos['pendiente'], '$0.00')

    def test_reportes_y_cierre(self):
        for reporte in ('estado_resultados', 'balance_general', 'balance_comprobacion', 'itbms', 'analitica'):
            datos = self.ok(self.ejecutar(self.contador, 'reporte_contable', {'reporte': reporte,
                                                                             'periodo': 'este_anio'}))
            self.assertTrue(datos['reporte'])
        respuesta = self.ejecutar(self.contador, 'reporte_contable', {'reporte': 'libro_mayor'})
        self.assertIn('cuenta', respuesta['error'])
        datos = self.ok(self.ejecutar(self.contador, 'guia_cierre_mes', {'mes': '09/2026'}))
        self.assertEqual(datos['desde'], '01/09/2026')
        self.assertEqual(datos['hasta'], '30/09/2026')
        self.assertTrue(any('ITBMS' in p['tarea'] for p in datos['pasos']))
        self.ok(self.ejecutar(self.contador, 'facturas_pendientes', {'tipo': 'por_pagar'}))
        self.ok(self.ejecutar(self.contador, 'movimientos_por_conciliar'))
        self.ok(self.ejecutar(self.contador, 'clientes_que_deben', {'solo_vencido': False}))

    def test_conciliar_con_sugerencia(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-09-01',
            'invoice_line_ids': [Command.create({'product_id': self.sofa.product_variant_id.id})]})
        factura.action_post()
        banco = self.env['account.journal'].search([('type', '=', 'bank'),
                                                    ('company_id', '=', self.env.company.id)], limit=1)
        linea = self.env['account.bank.statement.line'].create({
            'journal_id': banco.id, 'date': '2026-09-02', 'amount': factura.amount_total,
            'payment_ref': f'Pago {factura.name}', 'partner_id': self.cliente.id})
        datos = self.ok(self.ejecutar(self.contador, 'movimientos_por_conciliar', {'banco': banco.name}))
        fila = next(m for m in datos['movimientos'] if m['movimiento'] == linea.move_id.name)
        self.assertIn(factura.name, fila['sugerencia'])
        self.ok(self.confirmar(self.contador, self.ejecutar(self.contador, 'conciliar_movimiento', {
            'movimiento': linea.move_id.name})))
        self.assertTrue(linea.is_reconciled)
        self.assertEqual(factura.payment_state in ('paid', 'in_payment'), True)

    # ------------------------------------------------------------------
    # Usuarios
    # ------------------------------------------------------------------

    def test_admin_y_uno_mismo_no_se_tocan(self):
        admin = self.env.ref('base.user_admin')
        for nombre, argumentos in (('cambiar_rol_usuario', {'usuario': admin.login, 'rol': 'vendedor'}),
                                   ('desactivar_usuario', {'usuario': admin.login}),
                                   ('desactivar_usuario', {'usuario': self.gerente.login})):
            respuesta = self.ejecutar(self.gerente, nombre, argumentos)
            self.assertFalse(respuesta['ok'], nombre)
            self.assertFalse(respuesta.get('requiere_confirmacion'), nombre)
        self.assertTrue(admin.active)
        self.assertTrue(admin.has_group('base.group_system'))

    def test_roles_simples(self):
        datos = self.ok(self.ejecutar(self.gerente, 'listar_usuarios'))
        fila = next(u for u in datos['usuarios'] if u['login'] == self.vendedor.login)
        # Ventas puesto a mano, sin el rol «D'CASA / Vendedora»: Brian no lo llama Vendedor/a (2026-10-17).
        self.assertEqual(fila['rol'], 'Otro (permisos a medida)')
        respuesta = self.ejecutar(self.gerente, 'cambiar_rol_usuario', {'usuario': self.vendedor.login,
                                                                        'rol': 'cajero'})
        self.assertFalse(self.vendedor.has_group('account.group_account_invoice'))
        self.ok(self.confirmar(self.gerente, respuesta))
        self.assertTrue(self.vendedor.has_group('account.group_account_invoice'))
        self.assertTrue(self.vendedor.has_group('dcasa_base.group_caja'))
        fila = next(u for u in self.ok(self.ejecutar(self.gerente, 'listar_usuarios'))['usuarios']
                    if u['login'] == self.vendedor.login)
        self.assertEqual(fila['rol'], 'Caja')
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'crear_usuario', {
            'nombre': 'Brianzeta Nueva Usuaria', 'correo': 'brianzeta@example.com', 'rol': 'vendedor'})))
        nueva = self.env['res.users'].search([('login', '=', 'brianzeta@example.com')])
        self.assertTrue(nueva.has_group('sales_team.group_sale_salesman'))
        self.assertTrue(nueva.has_group('dcasa_base.group_vendedora'))
        self.assertFalse(nueva.has_group('base.group_system'))
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'desactivar_usuario', {
            'usuario': 'brianzeta@example.com'})))
        self.assertFalse(nueva.active)

    # ------------------------------------------------------------------
    # Generales
    # ------------------------------------------------------------------

    def test_buscar_en_todo_y_abrir(self):
        datos = self.ok(self.ejecutar(self.vendedor, 'buscar_en_todo', {'texto': 'Brianzeta'}))
        tipos = {r['tipo'] for r in datos['resultados']}
        self.assertTrue({'producto', 'cliente'} <= tipos)
        datos = self.ok(self.ejecutar(self.vendedor, 'abrir', {'que': 'producto', 'referencia': 'BRN-SOF'}))
        self.assertEqual(datos['abrir'], {'modelo': 'product.template', 'res_id': self.sofa.id,
                                          'titulo': self.sofa.display_name})
        datos = self.ok(self.ejecutar(self.vendedor, 'abrir', {'que': 'cotizaciones_abiertas'}))
        self.assertEqual(datos['abrir']['modelo'], 'sale.order')

    def test_lecturas_responden(self):
        """Toda consulta responde con datos compactos (sin excepciones) para quien tiene todos los permisos."""
        casos = {
            'resumen_ventas': {'periodo': 'este_mes'},
            'buscar_ventas': {'estado': 'cotizacion'},
            'buscar_clientes': {'texto': '6123-4501'},
            'ver_cliente': {'cliente': 'Brianzeta Cliente Uno'},
            'clientes_que_deben': {},
            'existencias_bajas': {'umbral': 0},
            'listar_categorias': {},
            'facturas_pendientes': {'solo_vencidas': True},
        }
        for nombre, argumentos in casos.items():
            self.ok(self.ejecutar(self.gerente, nombre, argumentos))
        datos = self.ok(self.ejecutar(self.gerente, 'buscar_clientes', {'texto': '6123-4501'}))
        self.assertEqual(datos['contactos'][0]['celular'], '6123-4501')
        respuesta = self.ejecutar(self.gerente, 'resumen_ventas', {'desde': '31/09/2026'})
        self.assertIn('dd/mm/aaaa', respuesta['error'])
