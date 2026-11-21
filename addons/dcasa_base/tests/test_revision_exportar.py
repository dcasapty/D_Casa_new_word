"""Revisión adversarial independiente de «Exportar» para Gerencia (``base.group_allow_export``).

Cada prueba afirma lo que DEBERÍA pasar: si falla es un hallazgo. Se pasó al repositorio con nombres propios.
"""
import io
import json
import zipfile
from contextlib import contextmanager

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from .test_roles import crear_usuario


@contextmanager
def niega():
    """El cuerpo tiene que fallar con un error de permisos (o de uso); si no falla, la prueba falla."""
    try:
        yield
    except (AccessError, UserError, ValueError):
        return
    raise AssertionError('no se negó')


@tagged('post_install', '-at_install')
class TestRevisionExportar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.exportar = cls.env.ref('base.group_allow_export')
        cls.gerencia = crear_usuario(cls.env, 'revision_gerencia', 'dcasa_base.group_gerencia')
        cls.caja = crear_usuario(cls.env, 'revision_caja', 'dcasa_base.group_caja')

    def test_el_id_externo_no_se_entrega_de_un_modelo_que_gerencia_no_puede_leer(self):
        """``export_data(['id'])`` no lee el registro: solo arma su id externo (y lo CREA si no existe, con permisos de
        sistema). Quien exporta no debería poder pedirlo de un modelo que no puede leer."""
        parametro = self.env['ir.config_parameter'].sudo().create({'key': 'revision.exportar.prueba', 'value': 'x'})
        con_gerencia = parametro.with_user(self.gerencia)
        with niega():
            con_gerencia.read(['key'])
        self.env.cr.execute("SELECT count(*) FROM ir_model_data WHERE model = 'ir.config_parameter' AND res_id = %s",
                            (parametro.id,))
        antes = self.env.cr.fetchone()[0]
        try:
            filas = con_gerencia.export_data(['id'])['datas']
        except (AccessError, UserError):
            return
        self.env.cr.execute("SELECT count(*) FROM ir_model_data WHERE model = 'ir.config_parameter' AND res_id = %s",
                            (parametro.id,))
        despues = self.env.cr.fetchone()[0]
        self.fail(f'Gerencia sacó el id externo de un parámetro del sistema que no puede leer: {filas} '
                  f'(ir.model.data antes={antes}, después={despues})')

    def test_gerencia_no_busca_por_un_campo_cerrado_al_exportar(self):
        """Fuga por búsqueda: el dominio del exportador no puede filtrar por un campo que Gerencia no lee."""
        Partner = self.env['res.partner']
        if 'dcasa_pin_hash' not in Partner._fields:
            self.skipTest('sin dcasa_socios')
        socio = Partner.create({'name': 'Socio revision exportar', 'phone': '+507 6000-1111'})
        socio.sudo().dcasa_pin_hash = 'abcdef0123'
        con_gerencia = Partner.with_user(self.gerencia)
        for dominio in ([('dcasa_pin_hash', '=like', 'a%')], [('dcasa_pin_hash', '!=', False)],
                        [('dcasa_pin_hash', 'ilike', 'abc')]):
            with self.subTest(dominio), niega():
                con_gerencia.search(dominio)
        with niega():
            con_gerencia.search([], order='dcasa_pin_hash')
        with niega():
            con_gerencia._read_group([], ['dcasa_pin_hash'], ['__count'])

    def test_gerencia_no_exporta_a_traves_de_una_relacion_lo_que_no_lee(self):
        """Ruta con relación: ``partner_id/dcasa_pin_hash`` desde una factura o un pedido."""
        Partner = self.env['res.partner']
        if 'dcasa_pin_hash' not in Partner._fields:
            self.skipTest('sin dcasa_socios')
        socio = Partner.create({'name': 'Socio revision exportar 2'})
        socio.sudo().dcasa_pin_hash = 'abcdef0123'
        orden = self.env['sale.order'].create({'partner_id': socio.id})
        with niega():
            orden.with_user(self.gerencia).export_data(['name', 'partner_id/dcasa_pin_hash'])
        # La clave del usuario no sale: Odoo la devuelve vacía en cualquier lectura (desde una factura, por la relación
        # al vendedor; la lista de usuarios ya no la baja Gerencia: ver ``test_exportar.py``).
        usuario = self.caja
        self.env.flush_all()
        self.env.cr.execute("UPDATE res_users SET password = 'HASH-SECRETO-REVISION' WHERE id = %s", (usuario.id,))
        self.env.invalidate_all()
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': usuario.partner_id.id, 'invoice_user_id': usuario.id})
        campos = ['name', 'invoice_user_id/login', 'invoice_user_id/password']
        filas = factura.with_user(self.gerencia).export_data(campos)['datas']
        self.assertEqual(filas[0][1], usuario.login)
        self.assertNotIn('HASH-SECRETO-REVISION', json.dumps(filas))

    def test_quienes_tienen_el_permiso_en_una_base_nueva(self):
        quienes = self.env['res.users'].with_context(active_test=False).search(
            [('all_group_ids', 'in', self.exportar.ids)])
        permitidos = {'__system__', 'admin'}
        gerencia = self.env.ref('dcasa_base.group_gerencia')
        for usuario in quienes:
            with self.subTest(usuario.login):
                self.assertTrue(usuario.login in permitidos or gerencia in usuario.all_group_ids
                                or usuario.has_group('base.group_system'), usuario.login)


@tagged('post_install', '-at_install')
class TestRevisionExportarPorHttp(HttpCase):
    """La ruta del botón (``/web/export/xlsx`` y ``/web/export/csv``) con usuarios de cada rol."""

    def setUp(self):
        super().setUp()
        self.gerencia = crear_usuario(self.env, 'revision_http_gerencia', 'dcasa_base.group_gerencia')
        self.gerencia.password = 'revision_http_gerencia'
        self.caja = crear_usuario(self.env, 'revision_http_caja', 'dcasa_base.group_caja')
        self.caja.password = 'revision_http_caja'
        self.parametro = self.env['ir.config_parameter'].sudo().create(
            {'key': 'revision.http.secreto', 'value': 'VALOR-SECRETO-REVISION'})
        self.cliente = self.env['res.partner'].create({'name': 'Cliente revision http', 'phone': '+507 6000-2222'})

    def bajar(self, login, modelo, campos, ids=None, dominio=None, formato='xlsx'):
        self.authenticate(login, login)
        datos = {'context': {}, 'domain': dominio or [], 'groupby': [], 'ids': ids or [], 'import_compat': False,
                 'model': modelo, 'fields': [{'name': n, 'label': n, 'type': 'char'} for n in campos]}
        with mute_logger('odoo.addons.web.controllers.export', 'odoo.http'):
            return self.url_open(f'/web/export/{formato}', data={
                'data': json.dumps(datos), 'csrf_token': http.Request.csrf_token(self)})

    def contenido(self, respuesta):
        if respuesta.content[:2] == b'PK':
            with zipfile.ZipFile(io.BytesIO(respuesta.content)) as libro:
                return ' '.join(libro.read(n).decode(errors='ignore') for n in libro.namelist())
        return respuesta.text

    def test_gerencia_baja_facturas_pero_no_clientes_ni_parametros_del_sistema(self):
        """Cambió con la decisión del 2026-11-20: Gerencia baja facturas y ventas, no la lista de clientes."""
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'ref': 'Factura revision http'})
        ok = self.bajar('revision_http_gerencia', 'account.move', ['ref', 'partner_id/name'], ids=factura.ids)
        self.assertEqual(ok.status_code, 200)
        self.assertIn('Factura revision http', self.contenido(ok))
        self.assertIn('Cliente revision http', self.contenido(ok))
        for formato in ('xlsx', 'csv'):
            with self.subTest(formato):
                r = self.bajar('revision_http_gerencia', 'res.partner', ['name', 'phone'], ids=self.cliente.ids,
                               formato=formato)
                self.assertNotEqual(r.status_code, 200)
                self.assertNotIn('+507 6000-2222', self.contenido(r))
                r = self.bajar('revision_http_gerencia', 'ir.config_parameter', ['key', 'value'],
                               dominio=[('key', '=', 'revision.http.secreto')], formato=formato)
                self.assertNotIn('VALOR-SECRETO-REVISION', self.contenido(r))
                r = self.bajar('revision_http_gerencia', 'ir.config_parameter', ['key', 'value'],
                               ids=self.parametro.ids, formato=formato)
                self.assertNotIn('VALOR-SECRETO-REVISION', self.contenido(r))

    def test_gerencia_no_baja_la_clave_de_los_usuarios(self):
        for campo in ('password', 'password_crypt', 'totp_secret', 'api_key_ids', 'oauth_access_token'):
            with self.subTest(campo):
                if campo not in self.env['res.users']._fields:
                    continue
                r = self.bajar('revision_http_gerencia', 'res.users', ['login', campo], ids=self.caja.ids)
                texto = self.contenido(r)
                self.assertNotIn('$pbkdf2', texto)
                self.assertNotIn('VALOR-SECRETO', texto)

    def test_caja_no_baja_nada(self):
        r = self.bajar('revision_http_caja', 'res.partner', ['name'], dominio=[('name', '=', 'Cliente revision http')])
        self.assertNotEqual(r.status_code, 200)
        self.assertNotIn('Cliente revision http', self.contenido(r))
