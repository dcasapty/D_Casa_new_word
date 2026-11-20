"""Exportar a Excel («Acción › Exportar» de las listas): Gerencia baja facturas y ventas; el resto, solo los
administradores (pedido del jefe, 2026-11-19: «bajar las facturas con su forma de pago»).

* El permiso es ``base.group_allow_export`` y Gerencia lo trae por su rol (``dcasa_roles.xml``); los administradores ya
  lo tenían. Caja, la Vendedora, contabilidad sola, un usuario interno cualquiera y el portal no lo tienen y reciben el
  error de siempre.
* El permiso de Odoo es global (toda lista), así que además hay un límite por modelo (``models/exportar.py``): quien lo
  trae sin ser administrador solo baja ``MODELOS_QUE_EXPORTA_GERENCIA`` (facturas, apuntes, pagos y ventas); las demás
  listas (clientes, empleados, chatter, adjuntos, usuarios, conversaciones…), solo los administradores. Una relación se
  sigue (``partner_id/name``), salvo hacia el chatter, los adjuntos, los empleados y las cuentas bancarias de los
  contactos, y por una relación no se piden identificadores externos (Odoo los crea al exportarlos).
* Exportar no abre nada nuevo: el exportador lee con los permisos de quien exporta. Lo que Gerencia no puede leer (la
  clave del PIN de socios, los datos técnicos de Meta, los parámetros del sistema) sigue sin salir en un Excel.
* El costo del producto lo ve Gerencia; el cierre de costos (``costos_cerrados.py``) no cubre ``export_data``: es
  seguro porque quien exporta ya ve los costos, y una prueba lo vigila.

La ruta del botón (xlsx y csv) por HTTP está en ``TestExportarPorHttp``; la revisión independiente, en
``test_revision_exportar.py``.
"""
import io
import json
import zipfile
from types import SimpleNamespace

import xlsxwriter

from odoo import Command, http
from odoo.addons.dcasa_base import excel_seguro
from odoo.addons.dcasa_base.models.costos_cerrados import ve_costos
from odoo.addons.dcasa_base.models.exportar import MODELOS_QUE_EXPORTA_GERENCIA, NO_SE_ATRAVIESAN
from odoo.addons.web.controllers.export import ExportXlsxWriter
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from .test_roles import crear_usuario

# Listas que Gerencia ya ve en pantalla y que, a propósito, no baja a Excel (solo los administradores).
NEGADAS_A_GERENCIA = (
    'res.partner', 'res.users', 'res.partner.bank', 'hr.employee', 'mail.message', 'mail.followers',
    'ir.attachment', 'ir.config_parameter', 'ir.cron', 'product.template', 'product.product', 'stock.picking',
    'stock.quant', 'purchase.order', 'crm.lead', 'dcasa.conversacion', 'account.account', 'account.journal',
)
MENSAJE = 'Ese Excel solo lo bajan los administradores'


@tagged('post_install', '-at_install')
class TestExportar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.exportar = cls.env.ref('base.group_allow_export')
        cls.gerencia = crear_usuario(cls.env, 'exp_gerencia', 'dcasa_base.group_gerencia')
        cls.admin = crear_usuario(cls.env, 'exp_admin', 'base.group_system')
        cls.caja = crear_usuario(cls.env, 'exp_caja', 'dcasa_base.group_caja')
        cls.vendedora = crear_usuario(cls.env, 'exp_vendedora', 'dcasa_base.group_vendedora')
        cls.contador = crear_usuario(cls.env, 'exp_contador', 'account.group_account_user')
        cls.interno = crear_usuario(cls.env, 'exp_interno')
        cls.portal = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Exp Portal', 'login': 'exp_portal',
            'group_ids': [Command.set([cls.env.ref('base.group_portal').id])]})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente para exportar', 'phone': '+507 6000-0000'})
        cls.factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.cliente.id, 'ref': 'Factura para exportar',
            'invoice_user_id': cls.caja.id})

    # --- quién trae el permiso ---------------------------------------------------------------------------
    def test_gerencia_lo_trae_por_su_rol_y_los_demas_no(self):
        gerencia = self.env.ref('dcasa_base.group_gerencia')
        self.assertIn(self.exportar, gerencia.implied_ids, 'viene en el rol, no puesto a mano a cada usuario')
        self.assertNotIn(self.exportar, self.gerencia.group_ids)
        for usuario in (self.gerencia, self.admin):
            with self.subTest(usuario.login):
                self.assertTrue(usuario.has_group('base.group_allow_export'))
        for usuario in (self.caja, self.vendedora, self.contador, self.interno, self.portal):
            with self.subTest(usuario.login):
                self.assertFalse(usuario.has_group('base.group_allow_export'))

    def test_nadie_mas_trae_el_permiso(self):
        """Todo el que lo tiene es de Gerencia, administrador o el sistema: ningún rol de la tienda se coló."""
        gerencia = self.env.ref('dcasa_base.group_gerencia')
        quienes = self.env['res.users'].with_context(active_test=False).search(
            [('all_group_ids', 'in', self.exportar.ids)])
        self.assertTrue(quienes)
        for usuario in quienes:
            with self.subTest(usuario.login):
                self.assertTrue(usuario._is_superuser() or usuario.has_group('base.group_system')
                                or gerencia in usuario.all_group_ids, usuario.login)

    def test_quien_no_trae_el_permiso_recibe_el_error_de_siempre_en_cualquier_lista(self):
        for usuario in (self.caja, self.vendedora, self.contador, self.interno, self.portal):
            for modelo in ('account.move', 'res.partner'):
                with self.subTest(usuario.login, modelo=modelo), self.assertRaisesRegex(UserError, '(?i)export'):
                    self.env[modelo].with_user(usuario).browse().export_data(['display_name'])

    # --- la lista corta de Gerencia ------------------------------------------------------------------------
    def test_la_lista_de_modelos_esta_en_un_solo_lugar_y_es_la_acordada(self):
        self.assertEqual(MODELOS_QUE_EXPORTA_GERENCIA, (
            'account.move', 'account.move.line', 'account.payment', 'sale.order', 'sale.order.line'))
        for modelo in MODELOS_QUE_EXPORTA_GERENCIA:
            self.assertIn(modelo, self.env, modelo)
            self.assertFalse(modelo.startswith(NO_SE_ATRAVIESAN), f'{modelo} está en las dos listas')
        for modelo in NEGADAS_A_GERENCIA:
            self.assertNotIn(modelo, MODELOS_QUE_EXPORTA_GERENCIA)

    def test_gerencia_baja_las_listas_de_finanzas_y_ventas(self):
        for modelo in MODELOS_QUE_EXPORTA_GERENCIA:
            with self.subTest(modelo):
                vacio = self.env[modelo].with_user(self.gerencia).browse()
                self.assertEqual(vacio.export_data(['display_name'])['datas'], [])
        datos = self.factura.with_user(self.gerencia).export_data(['ref', 'partner_id/name'])['datas']
        self.assertEqual(datos, [['Factura para exportar', 'Cliente para exportar']])

    def test_gerencia_no_baja_las_demas_listas(self):
        """Cada lista que Gerencia ya ve en pantalla pero que no es de finanzas ni de ventas: error en español sencillo,
        con registros o sin ellos, y también pidiendo solo el identificador externo."""
        probados = 0
        for modelo in NEGADAS_A_GERENCIA:
            if modelo not in self.env:
                continue
            probados += 1
            for campos in (['display_name'], ['id'], ['.id']):
                with self.subTest(modelo, campos=campos), self.assertRaisesRegex(AccessError, MENSAJE):
                    self.env[modelo].with_user(self.gerencia).browse().export_data(campos)
        self.assertGreaterEqual(probados, 12, 'la prueba tiene que haber mirado la mayoría de las listas')

    def test_los_administradores_bajan_todo_como_siempre(self):
        for modelo in NEGADAS_A_GERENCIA + MODELOS_QUE_EXPORTA_GERENCIA:
            if modelo not in self.env:
                continue
            with self.subTest(modelo):
                self.env[modelo].with_user(self.admin).browse().export_data(['display_name'])
        self.assertEqual(self.cliente.with_user(self.admin).export_data(['name', 'phone'])['datas'],
                         [['Cliente para exportar', '+507 6000-0000']])
        # El sistema (sudo, cron, otros módulos) tampoco cambia.
        self.assertEqual(self.cliente.sudo().export_data(['name'])['datas'], [['Cliente para exportar']])

    # --- las relaciones ---------------------------------------------------------------------------------
    def test_desde_una_factura_se_siguen_las_relaciones_utiles(self):
        factura = self.factura.with_user(self.gerencia)
        for campos, esperado in (
                (['ref', 'partner_id/name'], ['Factura para exportar', 'Cliente para exportar']),
                (['ref', 'invoice_partner_display_name'], ['Factura para exportar', 'Cliente para exportar']),
                (['ref', 'invoice_user_id'], ['Factura para exportar', self.caja.name]),
                (['ref', 'invoice_user_id/name'], ['Factura para exportar', self.caja.name]),
                (['ref', 'partner_id/phone'], ['Factura para exportar', '+507 6000-0000'])):
            with self.subTest(campos):
                self.assertEqual(factura.export_data(campos)['datas'], [esperado])
        producto = self.env['product.product'].create({'name': 'SILLA EXPORTAR', 'list_price': 10.0})
        factura_con_linea = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_line_ids': [Command.create({'product_id': producto.id, 'quantity': 1})]})
        filas = factura_con_linea.with_user(self.gerencia).export_data(
            ['partner_id/name', 'invoice_line_ids/product_id/name'])['datas']
        self.assertIn('SILLA EXPORTAR', [fila[1] for fila in filas])

    def test_por_una_relacion_no_se_llega_a_lo_que_no_se_baja_directo(self):
        """Chatter, seguidores, cuentas bancarias de contactos y empleados: por una factura se llegaría al mismo volcado
        que la lista directa."""
        factura = self.factura.with_user(self.gerencia)
        rutas = [['ref', 'message_ids/body'], ['ref', 'message_follower_ids/partner_id'],
                 ['ref', 'partner_id/bank_ids/acc_number']]
        if 'employee_ids' in self.env['res.users']._fields:
            rutas.append(['ref', 'invoice_user_id/employee_ids/name'])
        for campos in rutas:
            with self.subTest(campos), self.assertRaisesRegex(AccessError, 'no se puede bajar|solo lo bajan'):
                factura.export_data(campos)

    def test_por_una_relacion_no_se_piden_identificadores_externos(self):
        """Odoo CREA el identificador externo al exportarlo (con permisos de sistema), también de un modelo que
        Gerencia no puede leer: ``ir.config_parameter``, ``res.users``, ``ir.cron`` (de la lista y por relación)."""
        parametro = self.env['ir.config_parameter'].sudo().create({'key': 'dcasa.prueba.exportar.id', 'value': 'x'})
        self.env.flush_all()

        def externos():
            self.env.cr.execute("SELECT count(*) FROM ir_model_data WHERE model IN %s",
                                (('ir.config_parameter', 'res.users', 'ir.cron', 'res.partner'),))
            return self.env.cr.fetchone()[0]

        antes = externos()
        for modelo, registros in (('ir.config_parameter', parametro), ('res.users', self.caja),
                                  ('ir.cron', self.env['ir.cron'].sudo().search([], limit=1))):
            with self.subTest(modelo), self.assertRaises(AccessError):
                registros.with_user(self.gerencia).export_data(['id'])
        for campos in (['ref', 'partner_id/id'], ['ref', 'invoice_user_id/id'], ['ref', 'create_uid/id']):
            with self.subTest(campos), self.assertRaises(AccessError):
                self.factura.with_user(self.gerencia).export_data(campos)
        self.assertEqual(externos(), antes, 'no se creó ningún identificador externo')
        # El de la propia lista sí (es lo que usa «exportar para importar» de facturas).
        self.assertTrue(self.factura.with_user(self.gerencia).export_data(['id', 'ref'])['datas'][0][0])

    # --- lo que Gerencia no lee, tampoco sale -----------------------------------------------------------------
    def test_lo_que_gerencia_no_puede_leer_no_sale_en_un_excel(self):
        """El exportador no abre campos cerrados: pedirlos por ``export_data`` falla igual que leerlos."""
        cerrados = []
        if 'dcasa_meta_fbp' in self.env['sale.order']._fields:    # datos del navegador para Meta: solo administradores
            orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
            cerrados.append((orden.with_user(self.gerencia), 'dcasa_meta_fbp'))
        if 'dcasa_pin_hash' in self.env['res.partner']._fields:      # la clave del PIN de Socios, por una relación
            cerrados.append((self.env['sale.order'].create({'partner_id': self.cliente.id}).with_user(self.gerencia),
                             'partner_id/dcasa_pin_hash'))
        self.assertTrue(cerrados, 'la prueba necesita algún campo cerrado a Gerencia')
        for registros, campo in cerrados:
            with self.subTest(campo):
                with self.assertRaises(AccessError):
                    registros.export_data(['name', campo])
                if '/' not in campo:
                    with self.assertRaises(AccessError):
                        registros.read([campo])
                    self.assertNotIn(campo, registros.fields_get(), 'ni en la lista de campos del diálogo')

    def test_lo_que_gerencia_no_puede_leer_en_modelos_cerrados_tampoco(self):
        parametro = self.env['ir.config_parameter'].sudo().create({'key': 'dcasa.prueba.exportar', 'value': 'secreto'})
        with self.assertRaises(AccessError):
            parametro.with_user(self.gerencia).export_data(['key', 'value'])
        # El administrador sí: es suyo.
        self.assertEqual(parametro.with_user(self.admin).export_data(['key', 'value'])['datas'],
                         [['dcasa.prueba.exportar', 'secreto']])

    # --- el costo ----------------------------------------------------------------------------------------
    def test_quien_puede_exportar_ya_ve_los_costos(self):
        """El costo del producto está cerrado para Caja y la Vendedora, pero ``export_data`` no pasa por el cierre de
        ``read`` (``models/costos_cerrados.py``). Lo que lo hace seguro es que quien trae el permiso de exportar ya ve
        los costos (Gerencia y administradores): nadie exporta más de lo que ya ve. Si algún día otro rol recibe el
        permiso de exportar sin ver el costo, esta prueba falla y hay que cerrar ``export_data`` también."""
        quienes = self.env['res.users'].with_context(active_test=False).search(
            [('all_group_ids', 'in', self.exportar.ids)])
        self.assertIn(self.gerencia, quienes)
        for usuario in quienes:
            if usuario._is_superuser():
                continue
            with self.subTest(usuario.login):
                self.assertTrue(ve_costos(self.env(user=usuario)), usuario.login)

    def test_el_costo_lo_baja_el_administrador_y_gerencia_ya_no_baja_la_lista_de_productos(self):
        producto = self.env['product.template'].create({'name': 'MUEBLE EXPORTAR', 'standard_price': 123.0})
        self.assertEqual(producto.with_user(self.admin).export_data(['name', 'standard_price'])['datas'],
                         [['MUEBLE EXPORTAR', 123.0]])
        with self.assertRaisesRegex(AccessError, MENSAJE):
            producto.with_user(self.gerencia).export_data(['name', 'standard_price'])
        for usuario in (self.caja, self.vendedora):
            with self.subTest(usuario.login):
                self.assertFalse(ve_costos(self.env(user=usuario)))
                with self.assertRaises(UserError):
                    producto.with_user(usuario).export_data(['name', 'standard_price'])
                with self.assertRaises(AccessError):
                    producto.with_user(usuario).read(['standard_price'])


@tagged('post_install', '-at_install')
class TestExportarPorHttp(HttpCase):
    """La ruta del botón («Acción › Exportar»): ``/web/export/xlsx`` y ``/web/export/csv`` pasan por ``export_data``."""

    def setUp(self):
        super().setUp()
        for login, grupo in (('http_gerencia', 'dcasa_base.group_gerencia'), ('http_admin', 'base.group_system'),
                             ('http_caja', 'dcasa_base.group_caja'), ('http_vendedora', 'dcasa_base.group_vendedora')):
            crear_usuario(self.env, login, grupo).password = login
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Http Portal', 'login': 'http_portal', 'password': 'http_portal',
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])]})
        self.cliente = self.env['res.partner'].create({'name': 'Cliente http exportar', 'phone': '+507 6000-3333'})
        self.factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'ref': 'Factura http exportar'})

    def bajar(self, login, modelo, campos, formato, ids=None):
        self.authenticate(login, login)
        datos = {'context': {}, 'domain': [], 'groupby': [], 'ids': ids or [], 'import_compat': False,
                 'model': modelo, 'fields': [{'name': n, 'label': n, 'type': 'char'} for n in campos]}
        with mute_logger('odoo.addons.web.controllers.export', 'odoo.http'):
            return self.url_open(f'/web/export/{formato}', data={
                'data': json.dumps(datos), 'csrf_token': http.Request.csrf_token(self)})

    @staticmethod
    def contenido(respuesta):
        if respuesta.content[:2] == b'PK':
            with zipfile.ZipFile(io.BytesIO(respuesta.content)) as libro:
                return ' '.join(libro.read(n).decode(errors='ignore') for n in libro.namelist())
        return respuesta.text

    def test_gerencia_baja_facturas_pero_no_clientes(self):
        for formato in ('xlsx', 'csv'):
            with self.subTest(formato):
                ok = self.bajar('http_gerencia', 'account.move', ['ref', 'partner_id/name'], formato,
                                ids=self.factura.ids)
                self.assertEqual(ok.status_code, 200)
                self.assertIn('Factura http exportar', self.contenido(ok))
                self.assertIn('Cliente http exportar', self.contenido(ok), 'la relación a la factura sí se sigue')
                for modelo, campos in (('res.partner', ['name', 'phone']), ('res.users', ['login']),
                                       ('ir.config_parameter', ['key', 'value']), ('hr.employee', ['name'])):
                    if modelo not in self.env:
                        continue
                    negado = self.bajar('http_gerencia', modelo, campos, formato,
                                        ids=self.cliente.ids if modelo == 'res.partner' else None)
                    self.assertNotEqual(negado.status_code, 200, modelo)
                    self.assertNotIn('Cliente http exportar', self.contenido(negado))
                    self.assertNotIn('+507 6000-3333', self.contenido(negado))

    def test_el_administrador_baja_clientes_como_siempre(self):
        for formato in ('xlsx', 'csv'):
            with self.subTest(formato):
                ok = self.bajar('http_admin', 'res.partner', ['name', 'phone'], formato, ids=self.cliente.ids)
                self.assertEqual(ok.status_code, 200)
                self.assertIn('Cliente http exportar', self.contenido(ok))

    def test_caja_la_vendedora_y_el_portal_no_bajan_nada(self):
        for login in ('http_caja', 'http_vendedora', 'http_portal'):
            for formato in ('xlsx', 'csv'):
                with self.subTest(login, formato=formato):
                    negado = self.bajar(login, 'account.move', ['ref'], formato, ids=self.factura.ids)
                    self.assertNotEqual(negado.status_code, 200)
                    self.assertNotIn('Factura http exportar', self.contenido(negado))


@tagged('post_install', '-at_install')
class TestExcelSinFormulas(TransactionCase):
    """El escritor del «Exportar» del núcleo escribe los textos como texto (``excel_seguro.py``)."""

    def escribir(self, valores):
        salida = io.BytesIO()
        libro = xlsxwriter.Workbook(salida, {'in_memory': True})
        escritor = SimpleNamespace(worksheet=libro.add_worksheet())
        for fila, valor in enumerate(valores):
            ExportXlsxWriter.write(escritor, fila, 0, valor)
        libro.close()
        with zipfile.ZipFile(io.BytesIO(salida.getvalue())) as archivo:
            return archivo.read('xl/worksheets/sheet1.xml').decode(), archivo.read('xl/sharedStrings.xml').decode()

    def test_el_exportador_del_nucleo_usa_la_escritura_segura(self):
        self.assertIs(ExportXlsxWriter.write, excel_seguro.escribir_sin_formulas)

    def test_un_texto_nunca_es_formula_ni_vinculo(self):
        peligrosos = ['=2+2', '+1+1', '-1-1', '@SUMA(A1)', '=HYPERLINK("http://ejemplo.invalid/","x")',
                      'http://ejemplo.invalid/', 'mailto:alguien@ejemplo.invalid', 'Texto normal', 'ñandú «con» tilde']
        hoja, textos = self.escribir(peligrosos)
        self.assertNotIn('<f>', hoja, 'ningún texto quedó como fórmula')
        self.assertNotIn('hyperlink', hoja, 'ningún texto quedó como vínculo')
        for texto in peligrosos:
            self.assertIn(texto.replace('&', '&amp;').replace('<', '&lt;'), textos, texto)
        self.assertEqual(hoja.count('t="s"'), len(peligrosos), 'todos son texto')

    def test_lo_que_no_es_texto_sigue_siendo_numero_o_booleano(self):
        hoja, _textos = self.escribir([12.5, 3, True, ''])
        self.assertIn('<v>12.5</v>', hoja)
        self.assertIn('<v>3</v>', hoja)
        self.assertRegex(hoja, r't="b"[^>]*><v>1</v>')
        self.assertNotIn('t="s"', hoja, 'ni los números ni el texto vacío pasaron a ser texto')
