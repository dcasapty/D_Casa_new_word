"""El proveedor: nace apagado, se ofrece solo si está listo, reemplaza al «Yappy» manual sin que se vean dos, la
pantalla nunca muestra una clave y «Probar conexión»."""
import json

from lxml import etree

from odoo.addons.dcasa_pago_yappy.models import yappy_api as api
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from .common import DOMINIO, ID_COMERCIO, SECRETOS, PreparaPedido, YappyFalso, entorno


def todo_el_texto(valor):
    return json.dumps(valor, default=str, ensure_ascii=False)


class Base(PreparaPedido, TransactionCase):

    def compatibles(self, pedido=None, usuario=None, informe=None):
        pedido = pedido or self.pedido()
        proveedores = self.env['payment.provider']
        entorno_ = proveedores.with_user(usuario).sudo() if usuario else proveedores.sudo()
        return entorno_._get_compatible_providers(
            self.env.company.id, pedido.partner_id.id, pedido.amount_total, currency_id=pedido.currency_id.id,
            sale_order_id=pedido.id, report=informe)

    def manual(self):
        """El «Yappy» de siempre de la tienda (website_dcasa): el que te escribe por WhatsApp."""
        return self.env['payment.provider'].sudo().with_context(active_test=False).search(
            [('code', '=', 'custom'), ('name', '=', 'Yappy')], limit=1)


@tagged('post_install', '-at_install')
class TestNaceApagado(Base):

    def test_el_proveedor_nace_apagado_y_sin_publicar(self):
        proveedor = self.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        self.assertEqual(proveedor.code, 'yappy')
        self.assertEqual(proveedor.state, 'disabled')
        self.assertFalse(proveedor.is_published)
        self.assertFalse(self.env.ref('dcasa_pago_yappy.payment_method_yappy').active)

    def test_el_metodo_tiene_su_propio_codigo_y_la_tienda_lo_llama_yappy(self):
        proveedor = self.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        metodo = proveedor.with_context(active_test=False).payment_method_ids
        self.assertEqual(metodo.code, 'yappy_directo')
        self.assertEqual(metodo.name, 'Yappy', 'el cliente ve «Yappy»')
        manual = self.manual().with_context(active_test=False).payment_method_ids
        self.assertEqual(manual.code, 'yappy', 'el manual de siempre conserva su código')
        self.assertNotEqual(manual, metodo)

    def test_los_mensajes_estan_en_espanol_de_tu_y_sin_gritos(self):
        proveedor = self.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        for campo in ('pre_msg', 'pending_msg', 'done_msg', 'cancel_msg'):
            texto = str(proveedor.with_context(lang='es_419')[campo])
            self.assertTrue(texto, campo)
            self.assertNotIn('CORRE', texto.upper())
            self.assertNotIn('!!', texto)
            self.assertNotIn('remate', texto.lower())
        self.assertIn('apenas Yappy nos avisa', str(proveedor.with_context(lang='es_419').pre_msg))

    def test_el_cobro_cae_en_el_diario_yappy_de_siempre(self):
        proveedor = self.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        diarios = self.env['account.journal'].search(
            [('company_id', '=', proveedor.company_id.id), ('name', '=', 'Yappy'), ('type', '=', 'bank')])
        self.assertEqual(len(diarios), 1, 'un solo diario «Yappy»: el que ya existía en dcasa_base')
        self.assertEqual(diarios.code, 'YAPPY')
        self.assertEqual(proveedor.journal_id, diarios)
        linea = diarios.inbound_payment_method_line_ids.filtered(lambda linea: linea.payment_provider_id == proveedor)
        self.assertEqual(len(linea), 1)

    def test_preparar_se_puede_repetir_sin_duplicar_el_diario(self):
        proveedor = self.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        antes = self.env['account.journal'].search_count([('name', '=', 'Yappy')])
        proveedor._dcasa_yappy_preparar()
        proveedor._dcasa_yappy_preparar()
        self.assertEqual(self.env['account.journal'].search_count([('name', '=', 'Yappy')]), antes)

    def test_al_encenderlo_sin_diario_se_asegura_uno(self):
        proveedor = self.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        proveedor.state = 'disabled'    # una base de desarrollo puede traerlo encendido: se parte siempre de apagado
        proveedor.journal_id = False
        proveedor.state = 'test'
        proveedor._activate_default_pms()
        self.assertEqual(proveedor.journal_id.name, 'Yappy')


@tagged('post_install', '-at_install')
class TestCuandoSeOfrece(Base):
    """Tres llaves: claves cargadas, entorno coherente con el interruptor y que Gerencia lo active."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_yappy('test')

    def setUp(self):
        super().setUp()
        self.addCleanup(entorno().start().stop)

    def test_listo_se_ofrece_y_retira_al_yappy_manual(self):
        pedido = self.pedido()
        manual = self.manual()
        self.assertTrue(manual, 'el Yappy manual de siempre existe en la tienda de D\'CASA')
        proveedores = self.compatibles(pedido)
        self.assertIn(self.proveedor, proveedores)
        self.assertNotIn(manual, proveedores, 'cuando el directo se ofrece, el manual no sale: nunca dos «Yappy»')
        metodos = proveedores.payment_method_ids.filtered(lambda m: m.name == 'Yappy')
        self.assertEqual(len(metodos), 1, 'en la tienda se ve UN solo «Yappy»')

    def test_la_lista_de_metodos_trae_un_solo_yappy(self):
        pedido = self.pedido()
        proveedores = self.compatibles(pedido)
        metodos = self.env['payment.method'].sudo()._get_compatible_payment_methods(
            proveedores.ids, pedido.partner_id.id, currency_id=pedido.currency_id.id)
        self.assertEqual(metodos.filtered(lambda m: m.name == 'Yappy').mapped('code'), ['yappy_directo'])

    def test_apagado_se_ofrece_el_yappy_manual_como_hoy(self):
        self.proveedor.state = 'disabled'
        proveedores = self.compatibles()
        self.assertNotIn(self.proveedor, proveedores)
        self.assertIn(self.manual(), proveedores, 'nada cambia hasta que Gerencia lo enciende')

    def test_sin_las_claves_no_se_ofrece_y_sigue_el_manual(self):
        for variable in ('YAPPY_ID_COMERCIO', 'YAPPY_CLAVE_SECRETA', 'YAPPY_DOMINIO'):
            with self.subTest(falta=variable), entorno(**{variable: None}):
                informe = {}
                proveedores = self.compatibles(informe=informe)
                self.assertNotIn(self.proveedor, proveedores)
                self.assertIn(self.manual(), proveedores)
                self.assertFalse(informe['providers'][self.proveedor]['available'])

    def test_con_una_clave_con_forma_rara_no_se_ofrece(self):
        with entorno(YAPPY_CLAVE_SECRETA='!!no-es-base64!!'):
            self.assertNotIn(self.proveedor, self.compatibles())

    def test_el_entorno_tiene_que_coincidir_con_el_interruptor(self):
        with entorno(YAPPY_ENTORNO='produccion', DCASA_ENTORNO='produccion'):
            self.proveedor.state = 'test'
            self.assertNotIn(
                self.proveedor, self.compatibles(), 'Cloudflare dice produccion y Odoo dice «Modo de prueba»')
        with entorno(YAPPY_ENTORNO='prueba'):
            self.proveedor.state = 'enabled'
            self.assertNotIn(self.proveedor, self.compatibles(), 'Cloudflare dice prueba y Odoo dice «Habilitado»')
        with entorno(YAPPY_ENTORNO='produccion', DCASA_ENTORNO='produccion'):
            self.proveedor.state = 'enabled'
            self.assertIn(self.proveedor, self.compatibles())

    def test_produccion_solo_vale_en_el_servidor_de_produccion(self):
        self.proveedor.state = 'enabled'
        with entorno(YAPPY_ENTORNO='produccion', DCASA_ENTORNO='staging'):
            self.assertNotIn(self.proveedor, self.compatibles(), 'en staging Yappy solo cobra en prueba')
            self.assertIn('no es el de producción', self.proveedor.dcasa_yappy_aviso)

    def test_solo_para_pedidos_de_venta_y_solo_en_dolares(self):
        pedido = self.pedido()
        sin_pedido = self.env['payment.provider'].sudo()._get_compatible_providers(
            self.env.company.id, pedido.partner_id.id, pedido.amount_total, currency_id=pedido.currency_id.id)
        self.assertNotIn(self.proveedor, sin_pedido, 'sin un pedido de venta (v1) no se ofrece')
        euro = self.env.ref('base.EUR')
        self.assertFalse(self.proveedor._get_supported_currencies().filtered(lambda m: m == euro))
        self.assertEqual(self.proveedor._get_supported_currencies().mapped('name'), ['USD'])

    def test_sin_publicar_solo_lo_ve_el_equipo_y_el_visitante_sigue_con_el_manual(self):
        self.proveedor.is_published = False
        visitante = self.env.ref('base.public_user')
        interno = new_test_user(self.env, login='interna_yappy', groups='base.group_user')
        pedido = self.pedido()
        self.assertNotIn(self.proveedor, self.compatibles(pedido, usuario=visitante))
        self.assertIn(self.proveedor, self.compatibles(pedido, usuario=interno), 'el equipo lo prueba sin publicar')
        self.assertNotIn(self.manual(), self.compatibles(pedido, usuario=interno), 'y al equipo tampoco se le ven dos')

    def test_en_modo_de_prueba_en_produccion_es_del_equipo_aunque_este_publicado(self):
        visitante = self.env.ref('base.public_user')
        with entorno(DCASA_ENTORNO='produccion'):
            self.proveedor.state = 'test'
            self.assertTrue(self.proveedor.is_published)
            self.assertNotIn(self.proveedor, self.compatibles(usuario=visitante))

    def test_los_otros_metodos_no_cambian(self):
        pedido = self.pedido()
        con_yappy = self.compatibles(pedido) - self.proveedor - self.manual()
        self.proveedor.state = 'disabled'
        sin_yappy = self.compatibles(pedido) - self.manual()
        self.assertEqual(con_yappy, sin_yappy, 'encender Yappy directo no mueve a ningún otro método')
        self.assertIn(self.env.ref('payment.payment_provider_transfer'), con_yappy, 'la transferencia sigue igual')


@tagged('post_install', '-at_install')
class TestLaPantalla(Base):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_yappy('test')

    def setUp(self):
        super().setUp()
        self.addCleanup(entorno().start().stop)

    def test_dice_cargadas_entorno_y_dominio_pero_ninguna_clave(self):
        self.proveedor.invalidate_recordset()
        self.assertEqual(self.proveedor.dcasa_yappy_conectado, 'si')
        self.assertEqual(self.proveedor.dcasa_yappy_entorno, 'prueba')
        self.assertEqual(self.proveedor.dcasa_yappy_dominio, DOMINIO)
        self.assertIn('Listo', self.proveedor.dcasa_yappy_aviso)
        datos = self.proveedor.read([n for n in self.proveedor._fields if n.startswith('dcasa_yappy')])
        texto = todo_el_texto(datos)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, texto)

    def test_dice_que_falta_por_el_nombre_de_la_variable(self):
        with entorno(YAPPY_CLAVE_SECRETA=None, YAPPY_DOMINIO=None):
            self.proveedor.invalidate_recordset()
            self.assertEqual(self.proveedor.dcasa_yappy_conectado, 'no')
            aviso = self.proveedor.dcasa_yappy_aviso
            self.assertIn('YAPPY_CLAVE_SECRETA', aviso)
            self.assertIn('YAPPY_DOMINIO', aviso)
            self.assertNotIn('YAPPY_ID_COMERCIO', aviso)
            self.assertIn('sigue el «Yappy» de siempre', aviso)

    def test_apagado_lo_dice(self):
        self.proveedor.state = 'disabled'
        self.proveedor.invalidate_recordset()
        self.assertIn('apagado', self.proveedor.dcasa_yappy_aviso)

    def test_la_vista_compila_no_trae_campos_de_claves_y_dice_donde_van(self):
        vista = self.env['payment.provider'].get_view(self.env.ref('payment.payment_provider_form').id)
        arbol = etree.fromstring(vista['arch'])
        campos = {campo.get('name') for campo in arbol.iter('field')}
        for nombre in campos:
            self.assertFalse(any(palabra in nombre for palabra in ('clave', 'secret', 'password', 'merchant')), nombre)
        self.assertIn('dcasa_yappy_conectado', campos)
        texto = etree.tostring(arbol, encoding='unicode')
        self.assertIn('YAPPY_ID_COMERCIO', texto)
        self.assertIn('YAPPY_CLAVE_SECRETA', texto)
        self.assertIn('empieza con', texto, 'explica la equivalencia entre el número del pedido y la orden de Yappy')
        for secreto in SECRETOS:
            self.assertNotIn(secreto, texto)

    def test_la_transaccion_no_tiene_campo_de_claves(self):
        for modelo in ('payment.provider', 'payment.transaction'):
            for nombre in self.env[modelo]._fields:
                if 'yappy' in nombre:
                    palabras = ('clave', 'secret', 'password', 'token', 'key')
                    self.assertFalse(any(palabra in nombre for palabra in palabras), nombre)


@tagged('post_install', '-at_install')
class TestProbarConexion(Base):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_yappy('test')

    def setUp(self):
        super().setUp()
        self.addCleanup(entorno().start().stop)

    def probar(self, usuario=None):
        proveedor = self.proveedor.with_user(usuario) if usuario else self.proveedor
        return proveedor.action_dcasa_yappy_probar()

    def test_con_todo_bien_dice_que_yappy_valido_el_comercio_y_el_dominio(self):
        with YappyFalso() as yappy:
            resultado = self.probar()
        mensaje = resultado['params']['message']
        self.assertIn('validó el ID de comercio y el dominio', mensaje)
        self.assertIn('clave secreta se comprueba en el primer cobro', mensaje)
        self.assertNotEqual(
            resultado['params']['type'], 'success', 'la clave secreta no se comprobó: nunca un «todo bien» a secas')
        self.assertEqual([llamada[0] for llamada in yappy.llamadas], [api.RUTA_VALIDAR], 'ni crea ordenes ni cobra')
        self.assertTrue(self.proveedor.dcasa_yappy_prueba_ok)
        self.assertTrue(self.proveedor.dcasa_yappy_prueba_fecha)

    def test_con_el_dominio_mal_lo_dice_y_no_cuenta_como_bien(self):
        with entorno(YAPPY_DOMINIO='otro-dominio.com'), YappyFalso():
            resultado = self.probar()
        self.assertIn('letra por letra', resultado['params']['message'])
        self.assertFalse(self.proveedor.dcasa_yappy_prueba_ok)
        self.assertTrue(resultado['params']['sticky'])

    def test_yappy_caido_o_raro_no_revienta(self):
        for falla in ('tiempo', 'red', 'html', 'http500'):
            with self.subTest(falla=falla), YappyFalso() as yappy:
                yappy.falla = falla
                resultado = self.probar()
                self.assertEqual(resultado['params']['title'], 'Conexión con Yappy')
                self.assertFalse(self.proveedor.dcasa_yappy_prueba_ok)

    def test_sin_claves_dice_que_faltan(self):
        with entorno(YAPPY_CLAVE_SECRETA=None), YappyFalso() as yappy:
            resultado = self.probar()
        self.assertIn('Faltan', resultado['params']['message'])
        self.assertEqual(yappy.llamadas, [])

    def test_ningun_mensaje_ni_la_pantalla_trae_claves_ni_el_token(self):
        with YappyFalso() as yappy:
            texto = todo_el_texto(self.probar())
        for secreto in SECRETOS + (yappy.token,):
            self.assertNotIn(secreto, texto)
        self.proveedor.invalidate_recordset()
        texto = todo_el_texto(self.proveedor.read([n for n in self.proveedor._fields if n.startswith('dcasa_yappy')]))
        for secreto in SECRETOS + (yappy.token,):
            self.assertNotIn(secreto, texto, 'el token de la sesión de Yappy no se guarda en ningún campo')

    def test_quien_puede_probar_y_quien_no(self):
        gerencia = new_test_user(self.env, login='gerencia_yappy', groups='dcasa_base.group_gerencia')
        vendedora = new_test_user(self.env, login='vendedora_yappy', groups='dcasa_base.group_vendedora')
        caja = new_test_user(self.env, login='caja_yappy', groups='dcasa_base.group_caja')
        admin = new_test_user(self.env, login='admin_yappy', groups='base.group_system')
        with YappyFalso():
            for usuario in (gerencia, admin):
                self.assertTrue(self.probar(usuario))
            for usuario in (vendedora, caja):
                with self.assertRaises(AccessError):
                    self.probar(usuario)

    def test_solo_el_administrador_enciende_o_cambia_el_proveedor(self):
        """Odoo deja el modelo de proveedores solo al administrador del sistema; Yappy no abre ninguna puerta nueva."""
        for login, grupo in (('g2_yappy', 'dcasa_base.group_gerencia'), ('v2_yappy', 'dcasa_base.group_vendedora'),
                             ('c2_yappy', 'dcasa_base.group_caja')):
            usuario = new_test_user(self.env, login=login, groups=grupo)
            with self.subTest(grupo=grupo), self.assertRaises(AccessError):
                self.proveedor.with_user(usuario).write({'state': 'enabled'})

    def test_probar_en_un_proveedor_que_no_es_yappy_no_se_puede(self):
        transferencia = self.env.ref('payment.payment_provider_transfer')
        with self.assertRaises(UserError):
            transferencia.action_dcasa_yappy_probar()

    def test_el_id_de_comercio_no_va_a_ningun_registro(self):
        with self.assertLogs('odoo.addons.dcasa_pago_yappy', level='DEBUG') as registro, YappyFalso() as yappy:
            yappy.falla = 'tiempo'
            self.probar()
        texto = '\n'.join(registro.output)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, texto)
        self.assertNotIn(ID_COMERCIO, texto)
