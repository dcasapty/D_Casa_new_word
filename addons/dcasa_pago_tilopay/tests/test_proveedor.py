"""El proveedor: nace apagado, se ofrece solo si está listo, la pantalla nunca muestra una clave y «Probar conexión»."""
import json
import logging

from lxml import etree

from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from .common import SECRETOS, PreparaPedido, SimuladorTilopay, entorno


def todo_el_texto(valor):
    return json.dumps(valor, default=str, ensure_ascii=False)


@tagged('post_install', '-at_install')
class TestNaceApagado(PreparaPedido, TransactionCase):

    def test_el_proveedor_nace_apagado_y_sin_publicar(self):
        proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        self.assertEqual(proveedor.code, 'tilopay')
        self.assertEqual(proveedor.state, 'disabled')
        self.assertFalse(proveedor.is_published)
        self.assertFalse(self.env.ref('dcasa_pago_tilopay.payment_method_tilopay').active)

    def test_el_metodo_y_el_nombre_estan_en_espanol(self):
        proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        self.assertEqual(proveedor.with_context(active_test=False).payment_method_ids.name,
                         'Tarjeta, Yappy y más (Tilopay)')
        mensaje = str(proveedor.with_context(lang='es_419').pre_msg)
        self.assertIn('Pagar con tarjeta o Yappy', mensaje)
        self.assertIn('Tilopay', mensaje)
        for campo in ('pre_msg', 'pending_msg', 'done_msg', 'cancel_msg'):
            texto = str(proveedor.with_context(lang='es_419')[campo])
            self.assertNotIn('CORRE', texto.upper())
            self.assertNotIn('!!', texto)

    def test_el_cobro_cae_en_el_diario_tilopay(self):
        proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        diario = self.env['account.journal'].search(
            [('code', '=', 'TLP'), ('company_id', '=', proveedor.company_id.id)])
        self.assertEqual(len(diario), 1)
        self.assertEqual((diario.name, diario.type), ('Tilopay', 'bank'))
        self.assertEqual(proveedor.journal_id, diario)
        linea = diario.inbound_payment_method_line_ids.filtered(lambda linea: linea.payment_provider_id == proveedor)
        self.assertEqual(len(linea), 1)

    def test_preparar_se_puede_repetir_sin_duplicar_el_diario(self):
        proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        proveedor._dcasa_tilopay_preparar()
        proveedor._dcasa_tilopay_preparar()
        self.assertEqual(self.env['account.journal'].search_count([('code', '=', 'TLP')]), 1)

    def test_al_encender_se_asegura_el_diario_aunque_el_plan_contable_lo_haya_borrado(self):
        """En una base nueva Odoo carga el plan contable al final y borra los diarios que había: al encender el
        proveedor el diario «Tilopay» vuelve a existir y el cobro no cae en el primer banco que haya."""
        proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        self.env['account.payment.method.line'].search([('payment_provider_id', '=', proveedor.id)]).unlink()
        self.env['account.journal'].search([('code', '=', 'TLP')]).unlink()
        proveedor.state = 'test'
        self.assertEqual(proveedor.journal_id.code, 'TLP')
        self.assertEqual(proveedor.journal_id.name, 'Tilopay')
        proveedor.state = 'disabled'
        proveedor.state = 'test'
        self.assertEqual(self.env['account.journal'].search_count([('code', '=', 'TLP')]), 1)

    def test_en_una_base_nueva_el_diario_se_crea_despues_del_plan_contable(self):
        """``post_init_hook`` se cuelga del mismo punto que dcasa_base: primero el plan, luego el diario."""
        from odoo.addons.dcasa_pago_tilopay import post_init_hook
        registro = self.env.registry
        llamadas = []
        registro._auto_install_template = lambda entorno: llamadas.append('plan')
        try:
            post_init_hook(self.env)
            self.assertEqual(llamadas, [], 'todavía no: el plan va primero')
            registro._auto_install_template(self.env)
            self.assertEqual(llamadas, ['plan'])
        finally:
            del registro._auto_install_template
        self.assertEqual(self.env['account.journal'].search_count([('code', '=', 'TLP')]), 1)

    def test_sin_claves_el_sistema_sigue_normal(self):
        """Odoo no se entera de que faltan las claves: nada lanza, el proveedor solo dice por qué no se ofrece."""
        with entorno(TILOPAY_API_KEY=None, TILOPAY_API_USER=None, TILOPAY_API_PASSWORD=None):
            proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
            proveedor.state = 'test'
            proveedor.invalidate_recordset()
            self.assertEqual(proveedor.dcasa_tilopay_conectado, 'no')
            self.assertIn('Faltan las claves', proveedor.dcasa_tilopay_aviso)


@tagged('post_install', '-at_install')
class TestCuandoSeOfrece(PreparaPedido, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_tilopay('disabled')

    def ofrecidos(self, **kwargs):
        pedido = self.pedido()
        kwargs.setdefault('sale_order_id', pedido.id)
        proveedores = self.env['payment.provider']._get_compatible_providers(
            self.env.company.id, self.cliente.id, pedido.amount_total, currency_id=pedido.currency_id.id, **kwargs)
        return self.proveedor in proveedores

    def test_apagado_no_se_ofrece_aunque_haya_claves(self):
        with entorno():
            self.assertFalse(self.ofrecidos())

    def test_en_modo_de_prueba_con_claves_y_entorno_prueba_se_ofrece(self):
        self.proveedor.state = 'test'
        with entorno(TILOPAY_ENTORNO='prueba'):
            self.assertTrue(self.ofrecidos())
            self.assertIn('Listo', self.proveedor.dcasa_tilopay_aviso)
            # El aviso nombra la opción tal como la ve el cliente en la tienda, no otra palabra.
            self.assertIn('«Tarjeta, Yappy y más (Tilopay)»', self.proveedor.dcasa_tilopay_aviso)

    def test_en_produccion_hacen_falta_las_dos_llaves(self):
        """«Habilitado» en Odoo y TILOPAY_ENTORNO=produccion en Cloudflare: si uno solo dice «real», no se ofrece."""
        self.proveedor.state = 'enabled'
        with entorno(TILOPAY_ENTORNO='prueba'):
            self.assertFalse(self.ofrecidos())
            self.assertIn('No se ofrece', self.proveedor.dcasa_tilopay_aviso)
        with entorno(TILOPAY_ENTORNO='produccion'):
            self.assertTrue(self.ofrecidos())
        self.proveedor.state = 'test'
        with entorno(TILOPAY_ENTORNO='produccion'):
            self.assertFalse(self.ofrecidos(), 'Cloudflare dice real pero Odoo sigue en modo de prueba')

    def test_sin_las_tres_claves_no_se_ofrece_y_no_falla(self):
        self.proveedor.state = 'test'
        for falta in ('TILOPAY_API_KEY', 'TILOPAY_API_USER', 'TILOPAY_API_PASSWORD'):
            with self.subTest(falta=falta), entorno(**{falta: None}):
                self.assertFalse(self.ofrecidos())

    def test_solo_para_pagar_un_pedido(self):
        """Versión 1: el pedido completo. Sin pedido de venta (una factura suelta, un monto libre) no sale."""
        self.proveedor.state = 'test'
        with entorno():
            self.assertTrue(self.ofrecidos())
            self.assertFalse(self.ofrecidos(sale_order_id=False))

    def test_solo_en_dolares(self):
        self.proveedor.state = 'test'
        self.assertEqual(self.proveedor.available_currency_ids.mapped('name'), ['USD'])
        euro = self.env.ref('base.EUR')
        euro.active = True
        pedido = self.pedido()
        with entorno():
            proveedores = self.env['payment.provider']._get_compatible_providers(
                self.env.company.id, self.cliente.id, 100, currency_id=euro.id, sale_order_id=pedido.id)
        self.assertNotIn(self.proveedor, proveedores)

    def test_el_metodo_aparece_en_el_checkout_solo_cuando_el_proveedor_esta_listo(self):
        """La tienda muestra MÉTODOS: «Tarjeta, Yappy y más (Tilopay)» sale con el proveedor listo y no sale si no."""
        pedido = self.pedido()

        def metodos():
            with entorno():
                proveedores = self.env['payment.provider']._get_compatible_providers(
                    self.env.company.id, self.cliente.id, pedido.amount_total, currency_id=pedido.currency_id.id,
                    sale_order_id=pedido.id)
                return self.env['payment.method']._get_compatible_payment_methods(
                    proveedores.ids, self.cliente.id, currency_id=pedido.currency_id.id, sale_order_id=pedido.id)

        self.assertNotIn(self.metodo, metodos())
        self.assertFalse(self.metodo.active)
        self.proveedor.state = 'test'
        self.assertTrue(self.metodo.active, 'al encender el proveedor se activa su método')
        self.assertIn(self.metodo, metodos())
        self.assertEqual(self.metodo.name, 'Tarjeta, Yappy y más (Tilopay)')
        self.proveedor.state = 'disabled'
        self.assertFalse(self.metodo.active, 'y al apagarlo se desactiva')
        self.assertNotIn(self.metodo, metodos())

    def test_configurar_la_tienda_no_enciende_tilopay(self):
        """``website._dcasa_configurar_tienda`` (se corre al actualizar) deja los métodos de siempre y nunca prende
        Tilopay."""
        self.proveedor.write({'state': 'disabled', 'is_published': False})
        self.website._dcasa_configurar_tienda()
        self.assertEqual(self.proveedor.state, 'disabled')
        self.assertFalse(self.proveedor.is_published)

    def test_los_otros_metodos_de_la_tienda_siguen_igual(self):
        """Con Tilopay encendido o apagado, transferencia, Yappy y pago en la tienda salen igual."""
        pedido = self.pedido()

        def nombres():
            with entorno():
                provs = self.env['payment.provider']._get_compatible_providers(
                    self.env.company.id, self.cliente.id, pedido.amount_total, currency_id=pedido.currency_id.id,
                    sale_order_id=pedido.id)
            return set(provs.filtered(lambda p: p.code != 'tilopay').mapped('name'))
        antes = nombres()
        self.proveedor.state = 'test'
        self.assertEqual(nombres(), antes)
        self.assertTrue(antes, 'sale al menos la transferencia: si no, la prueba no probaría nada')


@tagged('post_install', '-at_install')
class TestLaPantallaNoMuestraClaves(PreparaPedido, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_tilopay('test')

    def test_el_proveedor_no_tiene_ningun_campo_para_una_clave(self):
        for nombre in self.env['payment.provider']._fields:
            if 'tilopay' in nombre:
                for palabra in ('key', 'llave', 'password', 'clave', 'secret', 'secreto', 'token', 'user', 'usuario'):
                    self.assertNotIn(palabra, nombre.replace('dcasa_tilopay_', '', 1), nombre)

    def test_ningun_dato_del_proveedor_ni_su_pantalla_trae_una_clave(self):
        with entorno():
            self.proveedor.invalidate_recordset()
            datos = self.proveedor.read()[0]
            lo_que_ve = todo_el_texto(datos)
            vista = self.env['payment.provider'].get_views([(False, 'form')])
            lo_que_ve += todo_el_texto(vista)
            lo_que_ve += todo_el_texto(self.proveedor.fields_get())
        for secreto in SECRETOS:
            self.assertNotIn(secreto, lo_que_ve)
        self.assertEqual(datos['dcasa_tilopay_conectado'], 'si')
        self.assertEqual(datos['dcasa_tilopay_entorno'], 'prueba')

    def test_la_pantalla_dice_conectado_y_entorno(self):
        with entorno():
            self.proveedor.invalidate_recordset()
            self.assertEqual(self.proveedor.dcasa_tilopay_conectado, 'si')
            self.assertEqual(self.proveedor.dcasa_tilopay_entorno, 'prueba')
        with entorno(TILOPAY_ENTORNO='produccion', TILOPAY_API_KEY=None):
            self.proveedor.invalidate_recordset()
            self.assertEqual(self.proveedor.dcasa_tilopay_conectado, 'no')
            self.assertEqual(self.proveedor.dcasa_tilopay_entorno, 'produccion')

    def test_la_vista_tiene_el_boton_solo_para_gerencia_y_administradores(self):
        # ``get_view`` le quita ``groups`` a quien sí lo tiene: se mira la vista tal como está guardada.
        arbol = etree.fromstring(self.env.ref('dcasa_pago_tilopay.payment_provider_form_tilopay').arch_db)
        boton = arbol.xpath("//button[@name='action_dcasa_tilopay_probar']")
        self.assertEqual(len(boton), 1)
        self.assertEqual(set(boton[0].get('groups', '').split(',')), {'dcasa_base.group_gerencia', 'base.group_system'})
        # Y el administrador (que tiene los dos grupos) sí lo ve en la pantalla.
        vista = etree.fromstring(self.env['payment.provider'].get_view(
            self.env.ref('payment.payment_provider_form').id)['arch'])
        self.assertTrue(vista.xpath("//button[@name='action_dcasa_tilopay_probar']"))


@tagged('post_install', '-at_install')
class TestProbarConexion(PreparaPedido, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_tilopay('test')
        cls.gerencia = new_test_user(cls.env, login='til_gerencia', groups='base.group_user,dcasa_base.group_gerencia')
        cls.vendedora = new_test_user(
            cls.env, login='til_vendedora', groups='base.group_user,sales_team.group_sale_salesman')

    def setUp(self):
        super().setUp()
        api.olvidar_tokens()
        self.addCleanup(api.olvidar_tokens)

    def probar(self, usuario=None):
        proveedor = self.proveedor.with_user(usuario) if usuario else self.proveedor
        return proveedor.action_dcasa_tilopay_probar()

    def test_sale_bien_y_lo_dice_sin_mostrar_datos(self):
        with entorno(), SimuladorTilopay() as tilopay:
            respuesta = self.probar(self.gerencia)
        params = respuesta['params']
        self.assertEqual(params['type'], 'success')
        self.assertTrue(self.proveedor.dcasa_tilopay_prueba_ok)
        self.assertTrue(self.proveedor.dcasa_tilopay_prueba_fecha)
        texto = todo_el_texto(respuesta)
        for secreto in (*SECRETOS, tilopay.token):
            self.assertNotIn(secreto, texto)
        self.assertEqual(len(tilopay.rutas(api.RUTA_LOGIN)), 1)
        self.assertEqual(len(tilopay.llamadas), 1, 'solo abre sesión: no pide nada más')
        self.assertEqual(params['next'], {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                         'la pantalla se refresca para mostrar «Última prueba»')

    def test_claves_que_tilopay_no_acepta(self):
        with entorno(), SimuladorTilopay() as tilopay:
            tilopay.claves_buenas = False
            respuesta = self.probar(self.gerencia)
        self.assertEqual(respuesta['params']['type'], 'danger')
        self.assertFalse(self.proveedor.dcasa_tilopay_prueba_ok)
        self.assertIn('Revisa las claves', respuesta['params']['message'])

    def test_tilopay_caido(self):
        with entorno(), SimuladorTilopay() as tilopay:
            tilopay.falla = 'tiempo'
            respuesta = self.probar(self.gerencia)
        self.assertEqual(respuesta['params']['type'], 'danger')
        self.assertIn('no se pudo hablar con Tilopay', respuesta['params']['message'])

    def test_sin_claves_no_llama_a_nadie(self):
        with entorno(TILOPAY_API_PASSWORD=None), SimuladorTilopay() as tilopay:
            respuesta = self.probar(self.gerencia)
        self.assertEqual(respuesta['params']['type'], 'danger')
        self.assertEqual(tilopay.llamadas, [])

    def test_una_vendedora_no_puede_probarla(self):
        with entorno(), SimuladorTilopay() as tilopay:
            with self.assertRaises(AccessError):
                self.proveedor.with_user(self.vendedora).action_dcasa_tilopay_probar()
            self.assertEqual(tilopay.llamadas, [])
            self.assertFalse(self.proveedor.dcasa_tilopay_prueba_fecha)

    def test_los_registros_no_traen_claves(self):
        with self.assertLogs('odoo', level=logging.INFO) as registros, entorno(), SimuladorTilopay() as tilopay:
            logging.getLogger('odoo.test').info('inicio')
            self.probar(self.gerencia)
            tilopay.claves_buenas = False
            api.olvidar_tokens()
            self.probar(self.gerencia)
        texto = '\n'.join(registros.output)
        for secreto in (*SECRETOS, tilopay.token):
            self.assertNotIn(secreto, texto)
