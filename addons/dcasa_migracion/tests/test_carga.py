"""El asistente de Ajustes: solo administradores, «Revisar» no cambia nada y «Cargar» exige haber revisado."""
import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged

from . import ejemplos


def _b64(texto):
    return base64.b64encode(ejemplos.como_bytes(texto))


@tagged('post_install', '-at_install')
class TestAsistenteDeCarga(TransactionCase):

    def setUp(self):
        super().setUp()
        self.admin = self.env.ref('base.user_admin')
        self.Carga = self.env['dcasa.migracion.carga'].with_user(self.admin)

    def _fichas(self):
        return self.env['res.partner'].search_count([('category_id.name', '=', 'Sistema anterior')])

    def _asistente(self, **archivos):
        valores = {'archivo_clientes': _b64(ejemplos.CLIENTES)}
        valores.update({k: (_b64(v) if v is not None else False) for k, v in archivos.items()})
        return self.Carga.create(valores)

    def test_solo_los_administradores_lo_pueden_usar(self):
        gerencia = new_test_user(self.env, login='gerencia_prueba', groups='sales_team.group_sale_manager')
        with self.assertRaises(AccessError):
            self.env['dcasa.migracion.carga'].with_user(gerencia).create({})

    def test_el_menu_es_solo_de_administradores(self):
        menu = self.env.ref('dcasa_migracion.menu_carga')
        self.assertEqual(menu.group_ids, self.env.ref('base.group_system'))

    def test_revisar_muestra_que_pasaria_y_no_cambia_nada(self):
        asistente = self._asistente()
        antes = self._fichas()
        asistente.action_revisar()
        self.assertEqual(self._fichas(), antes)
        self.assertIn('ENSAYO', asistente.informe)
        self.assertIn('Fichas nuevas', asistente.informe)
        self.assertIn('<b>5</b>', asistente.informe)
        self.assertTrue(asistente.huella_revisada)

    def test_cargar_sin_revisar_no_se_deja(self):
        asistente = self._asistente()
        with self.assertRaisesRegex(UserError, 'pulsa «Revisar»'):
            asistente.action_cargar()
        self.assertEqual(self._fichas(), 0)

    def test_revisar_y_cargar(self):
        asistente = self._asistente()
        asistente.action_revisar()
        asistente.action_cargar()
        self.assertEqual(self._fichas(), 5)
        self.assertIn('CARGA HECHA', asistente.informe)
        self.assertFalse(asistente.huella_revisada, 'Tras cargar hay que revisar otra vez para cargar de nuevo')

    def test_si_cambia_el_archivo_hay_que_revisar_de_nuevo(self):
        asistente = self._asistente()
        asistente.action_revisar()
        asistente.archivo_clientes = _b64(ejemplos.CLIENTES + '90006,Otro de Prueba,persona,,,,,,\n')
        with self.assertRaisesRegex(UserError, 'Revisar'):
            asistente.action_cargar()
        self.assertEqual(self._fichas(), 0)

    def test_si_cambia_la_casilla_de_precios_hay_que_revisar_de_nuevo(self):
        asistente = self._asistente()
        asistente.action_revisar()
        asistente.actualizar_precios = True
        with self.assertRaisesRegex(UserError, 'Revisar'):
            asistente.action_cargar()

    def test_productos_y_existencias_tambien_pasan_por_el_ensayo(self):
        asistente = self.Carga.create({
            'archivo_productos': _b64(ejemplos.PRODUCTOS), 'archivo_inventario': _b64(ejemplos.INVENTARIO)})
        asistente.action_revisar()
        self.assertIn('Productos nuevos', asistente.informe)
        self.assertFalse(self.env['product.product'].search([('default_code', '=', 'PRUEBA-002')]),
                         'El ensayo no deja ningún producto')
        asistente.action_cargar()
        self.assertTrue(self.env['product.product'].search([('default_code', '=', 'PRUEBA-002')]))

    def test_un_archivo_mal_hecho_se_explica_sin_tocar_nada(self):
        asistente = self.Carga.create({'archivo_clientes': base64.b64encode('ñ'.encode('latin-1'))})
        with self.assertRaisesRegex(UserError, 'UTF-8'):
            asistente.action_revisar()
        asistente = self.Carga.create({'archivo_clientes': _b64('nombre,celular\nAna,1\n')})
        with self.assertRaisesRegex(UserError, 'columna «id_viejo»'):
            asistente.action_revisar()

    def test_existencias_sin_productos_se_rechazan(self):
        asistente = self.Carga.create({'archivo_inventario': _b64(ejemplos.INVENTARIO)})
        with self.assertRaisesRegex(UserError, 'productos.csv'):
            asistente.action_revisar()

    def test_sin_ningun_archivo_se_avisa(self):
        with self.assertRaisesRegex(UserError, 'al menos un archivo'):
            self.Carga.create({}).action_revisar()

    def test_la_pantalla_se_arma_y_el_flujo_funciona_como_en_el_navegador(self):
        """Con ``Form`` se usa la vista de verdad: sube un archivo, revisa, y «Cargar» aparece solo tras revisar."""
        with Form(self.Carga) as formulario:
            formulario.archivo_clientes = _b64(ejemplos.CLIENTES)
        asistente = formulario.record
        asistente.action_revisar()
        self.assertTrue(asistente.huella_revisada)
        self.assertEqual(self._fichas(), 0)
        asistente.action_cargar()
        self.assertEqual(self._fichas(), 5)

    def test_el_menu_lo_ve_el_administrador_y_nadie_mas(self):
        gerencia = new_test_user(self.env, login='gerencia_menu', groups='sales_team.group_sale_manager')

        def xmlids(usuario):
            menus = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
            return {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}

        self.assertIn('dcasa_migracion.menu_carga', xmlids(self.admin))
        self.assertNotIn('dcasa_migracion.menu_carga', xmlids(gerencia))

    def test_la_vista_se_entrega_al_administrador(self):
        vista = self.env['dcasa.migracion.carga'].with_user(self.admin).get_views([(False, 'form')])
        self.assertIn('action_revisar', vista['views']['form']['arch'])
        self.assertIn('action_cargar', vista['views']['form']['arch'])

    def test_proveedores_productos_y_precios_en_una_sola_carga_respetan_el_orden(self):
        """Los precios de proveedor usan a los proveedores y a los productos que se cargan en la misma pasada."""
        asistente = self.Carga.create({
            'archivo_proveedores': _b64(ejemplos.PROVEEDORES), 'archivo_productos': _b64(ejemplos.PRODUCTOS),
            'archivo_inventario': _b64(ejemplos.INVENTARIO), 'archivo_precios': _b64(ejemplos.PRECIOS)})
        asistente.action_revisar()
        self.assertIn('Proveedores', asistente.informe)
        self.assertIn('Precios de proveedor', asistente.informe)
        self.assertFalse(self.env['product.supplierinfo'].search([('price', '=', 85.5)]), 'El ensayo no deja nada')
        asistente.action_cargar()
        precios = self.env['product.supplierinfo'].search([('product_tmpl_id.default_code', '=', 'PRUEBA-001')])
        self.assertEqual(precios.mapped('price'), [85.5])

    def test_ventas_y_compras_pendientes_van_al_final_de_la_misma_carga(self):
        """Las facturas en borrador y las órdenes de compra usan a los contactos y productos de la misma pasada."""
        asistente = self.Carga.create({
            'archivo_clientes': _b64(ejemplos.CLIENTES), 'archivo_proveedores': _b64(ejemplos.PROVEEDORES),
            'archivo_productos': _b64(ejemplos.PRODUCTOS), 'archivo_inventario': _b64(ejemplos.INVENTARIO),
            'archivo_ventas': _b64(ejemplos.VENTAS), 'archivo_ventas_lineas': _b64(ejemplos.VENTAS_LINEAS),
            'archivo_compras': _b64(ejemplos.COMPRAS), 'archivo_compras_lineas': _b64(ejemplos.COMPRAS_LINEAS)})
        asistente.action_revisar()
        for texto in ('Ventas por facturar', 'por entregar', 'Compras por recibir', 'Compras por facturar'):
            self.assertIn(texto, asistente.informe)
        Movimiento = self.env['account.move']
        self.assertFalse(Movimiento.search([('invoice_origin', 'in', ['S99901', 'S99902', 'P99901'])]),
                         'El ensayo no deja ninguna factura')
        self.assertFalse(self.env['purchase.order'].search([('origin', '=', 'P99905')]))
        asistente.action_cargar()
        venta = Movimiento.search([('invoice_origin', '=', 'S99901')])
        self.assertEqual((venta.move_type, venta.state), ('out_invoice', 'draft'))
        compra = Movimiento.search([('invoice_origin', '=', 'P99901')])
        self.assertEqual((compra.move_type, compra.state, compra.ref), ('in_invoice', 'draft', 'FAC-PRUEBA-001'))
        orden = self.env['purchase.order'].search([('origin', '=', 'P99905')])
        self.assertEqual(orden.state, 'purchase')
        # Volver a cargar lo mismo no repite nada.
        repetido = self.Carga.create({
            'archivo_ventas': asistente.archivo_ventas, 'archivo_ventas_lineas': asistente.archivo_ventas_lineas,
            'archivo_compras': asistente.archivo_compras, 'archivo_compras_lineas': asistente.archivo_compras_lineas})
        repetido.action_revisar()
        repetido.action_cargar()
        self.assertEqual(Movimiento.search_count([('invoice_origin', '=', 'S99901')]), 1)
        self.assertEqual(self.env['purchase.order'].search_count([('origin', '=', 'P99905')]), 1)

    def test_las_ordenes_pendientes_se_suben_en_pareja(self):
        asistente = self.Carga.create({'archivo_ventas': _b64(ejemplos.VENTAS)})
        with self.assertRaisesRegex(UserError, 'ventas_pendientes_lineas.csv'):
            asistente.action_revisar()
        asistente = self.Carga.create({'archivo_compras_lineas': _b64(ejemplos.COMPRAS_LINEAS)})
        with self.assertRaisesRegex(UserError, 'compras_pendientes.csv'):
            asistente.action_revisar()

    def test_facturas_y_pagos_del_ano_se_cargan_por_tandas(self):
        Diario = self.env['account.journal']
        Diario.create({'name': 'Caja Ejemplo', 'type': 'cash', 'code': 'CEJ'})
        Diario.create({'name': 'Banco Ejemplo', 'type': 'bank', 'code': 'BEJ'})
        asistente = self.Carga.with_context(dcasa_documentos_por_tanda=4).create({
            'archivo_clientes': _b64(ejemplos.CLIENTES), 'archivo_proveedores': _b64(ejemplos.PROVEEDORES),
            'archivo_facturas_clientes': _b64(ejemplos.FACTURAS_CLIENTES),
            'archivo_facturas_clientes_lineas': _b64(ejemplos.FACTURAS_CLIENTES_LINEAS),
            'archivo_facturas_proveedores': _b64(ejemplos.FACTURAS_PROVEEDORES),
            'archivo_facturas_proveedores_lineas': _b64(ejemplos.FACTURAS_PROVEEDORES_LINEAS),
            'archivo_pagos': _b64(ejemplos.PAGOS)})
        Movimiento = self.env['account.move']
        asistente.action_revisar()
        self.assertIn('Antes de cargar', asistente.informe)
        self.assertIn('El ensayo cubre solo la primera tanda', asistente.informe)
        self.assertFalse(Movimiento.search([('dcasa_historica', '=', True)]), 'El ensayo no deja nada')
        # 15 documentos de 4 en 4: tres tandas incompletas y una última que termina.
        for tanda in range(1, 5):
            asistente.action_cargar()
            cargados = Movimiento.search_count([('dcasa_historica', '=', True)])
            if tanda < 4:
                self.assertTrue(asistente.huella_revisada, 'Quedan documentos: la revisión sigue valiendo')
                self.assertIn('Pulsa «Cargar» otra vez', asistente.informe)
        self.assertFalse(asistente.huella_revisada, 'Ya no falta nada')
        self.assertEqual(cargados, 10)
        self.assertEqual(
            self.env['account.payment'].search_count([('memo', 'ilike', 'Cargado del sistema anterior')]), 5)
        self.assertIn('Cuadre contra el archivo', asistente.informe)
        self.assertIn('CARGA HECHA', asistente.informe)

    def test_las_facturas_del_ano_se_suben_en_pareja(self):
        asistente = self.Carga.create({'archivo_facturas_clientes': _b64(ejemplos.FACTURAS_CLIENTES)})
        with self.assertRaisesRegex(UserError, 'facturas_clientes.csv y facturas_clientes_lineas.csv'):
            asistente.action_revisar()
        asistente = self.Carga.create({
            'archivo_facturas_proveedores_lineas': _b64(ejemplos.FACTURAS_PROVEEDORES_LINEAS)})
        with self.assertRaisesRegex(UserError, 'facturas_proveedores.csv'):
            asistente.action_revisar()
