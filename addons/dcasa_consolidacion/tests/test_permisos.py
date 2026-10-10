"""Quién puede qué: la vendedora no entra, contabilidad (solo lectura) lee, el contador calcula, y nadie
consolida empresas a las que no tiene acceso. Se llama por ``odoo.service.model.call_kw``, la misma puerta que
``/web/dataset/call_kw``."""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import ConsolidacionCommon

MODELO = 'dcasa.consolidacion'


@tagged('post_install', '-at_install')
class TestPermisosConsolidacion(ConsolidacionCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ambas = [Command.set(cls.grupo.ids)]
        sola = [Command.set(cls.empresa_a.ids)]

        def usuario(login, grupo, empresas):
            return new_test_user(cls.env, login=login, groups=f'base.group_user,{grupo}',
                                 company_id=cls.empresa_a.id, company_ids=empresas)

        cls.vendedora = usuario('cons_ventas', 'sales_team.group_sale_salesman', ambas)
        cls.facturacion = usuario('cons_factura', 'account.group_account_invoice', ambas)
        cls.lectura = usuario('cons_lectura', 'account.group_account_readonly', ambas)
        cls.contador = usuario('cons_contador', 'account.group_account_user', ambas)
        cls.contador_a = usuario('cons_contador_a', 'account.group_account_user', sola)

    def rpc(self, usuario, modelo, metodo, ids=(), kwargs=None):
        return call_kw(self.env(user=usuario)[modelo], metodo, [list(ids)], kwargs or {})

    def _calculada(self, tipo='balance', **valores):
        return self.consolidacion(tipo, **valores)

    # ------------------------------------------------------------------
    # Sin contabilidad: no entra
    # ------------------------------------------------------------------

    def test_vendedora_y_facturacion_no_leen_ni_calculan(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0)
        consolidacion = self._calculada()
        lineas = consolidacion.linea_ids
        for usuario in (self.vendedora, self.facturacion):
            with self.subTest(usuario=usuario.login):
                Consolidacion = self.env[MODELO].with_user(usuario)
                with self.assertRaises(AccessError):
                    Consolidacion.search([])
                with self.assertRaises(AccessError):
                    consolidacion.with_user(usuario).read(['name'])
                with self.assertRaises(AccessError):
                    Consolidacion.create({'name': 'Intento'})
                for metodo in ('action_calcular', 'action_borrador', 'action_ver_pivote'):
                    with self.assertRaises(AccessError, msg=metodo):
                        self.rpc(usuario, MODELO, metodo, consolidacion.ids)
                with self.assertRaises(AccessError):
                    self.env['dcasa.consolidacion.linea'].with_user(usuario).search([])
                with self.assertRaises(AccessError):
                    lineas.with_user(usuario).read(['importe'])
                with self.assertRaises(AccessError):
                    self.env['dcasa.consolidacion.mapa'].with_user(usuario).search([])
                with self.assertRaises(AccessError):
                    self.env['ir.actions.report'].with_user(usuario)._render_qweb_html(
                        'dcasa_consolidacion.reporte_consolidacion', consolidacion.ids)
        self.assertEqual(consolidacion.estado, 'calculada')
        self.assertEqual(consolidacion.linea_ids, lineas)

    # ------------------------------------------------------------------
    # Solo lectura de contabilidad: lee, no calcula
    # ------------------------------------------------------------------

    def test_solo_lectura_lee_pero_no_calcula(self):
        consolidacion = self._calculada()
        mia = consolidacion.with_user(self.lectura)
        self.assertEqual(mia.read(['name', 'estado'])[0]['estado'], 'calculada')
        self.assertTrue(mia.linea_ids)
        self.assertTrue(mia.cuadra)
        self.assertTrue(mia._matriz()['secciones'])
        html, _formato = self.env['ir.actions.report'].with_user(self.lectura)._render_qweb_html(
            'dcasa_consolidacion.reporte_consolidacion', consolidacion.ids)
        self.assertIn('Balance general consolidado', html.decode())
        self.assertEqual(self.env['dcasa.consolidacion.mapa'].with_user(self.lectura).search_count([]), 0)
        for metodo in ('action_calcular', 'action_borrador'):
            with self.assertRaises(AccessError, msg=metodo):
                self.rpc(self.lectura, MODELO, metodo, consolidacion.ids)
        with self.assertRaises(AccessError):
            self.env[MODELO].with_user(self.lectura).create({'name': 'Intento'})
        with self.assertRaises(AccessError):
            mia.write({'name': 'Otro nombre'})
        with self.assertRaises(AccessError):
            mia.unlink()
        with self.assertRaises(AccessError):
            self.env['dcasa.consolidacion.mapa'].with_user(self.lectura).create({
                'company_id': self.empresa_a.id, 'account_id': self.cuenta(self.empresa_a, 'income').id,
                'codigo_consolidado': 'X'})
        self.assertEqual(consolidacion.estado, 'calculada')
        self.assertEqual(consolidacion.name, 'Prueba balance')

    # ------------------------------------------------------------------
    # Contador: crea, calcula, lee e imprime
    # ------------------------------------------------------------------

    def test_contador_crea_calcula_lee_e_imprime(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        consolidacion = self.env[MODELO].with_user(self.contador).create({
            'name': 'Consolidado del contador', 'tipo_reporte': 'balance', 'fecha_desde': '2030-03-01',
            'fecha_hasta': '2030-03-31', 'company_ids': [Command.set(self.grupo.ids)]})
        self.assertEqual(consolidacion.estado, 'borrador')
        self.assertTrue(self.rpc(self.contador, MODELO, 'action_calcular', consolidacion.ids))
        self.assertEqual(consolidacion.estado, 'calculada')
        self.assertEqual(consolidacion.calculada_por, self.contador)
        self.assertTrue(consolidacion.linea_ids)
        self.assertIn('Descuadre entre', consolidacion.advertencias)
        self.assertIn('Calculada por', consolidacion.message_ids[:1].body)
        self.assertEqual(self.env['dcasa.consolidacion.linea'].with_user(self.contador).search_count(
            [('consolidacion_id', '=', consolidacion.id)]), len(consolidacion.linea_ids))
        html, _formato = self.env['ir.actions.report'].with_user(self.contador)._render_qweb_html(
            'dcasa_consolidacion.reporte_consolidacion', consolidacion.ids)
        self.assertIn('Descuadre entre', html.decode())
        self.assertEqual(self.rpc(self.contador, MODELO, 'action_ver_pivote', consolidacion.ids)['res_model'],
                         'dcasa.consolidacion.linea')
        self.rpc(self.contador, MODELO, 'action_borrador', consolidacion.ids)
        self.assertEqual((consolidacion.estado, len(consolidacion.linea_ids)), ('borrador', 0))
        mapa = self.env['dcasa.consolidacion.mapa'].with_user(self.contador).create({
            'company_id': self.empresa_a.id, 'account_id': self.cuenta(self.empresa_a, 'income').id,
            'codigo_consolidado': 'Z'})
        mapa.write({'codigo_consolidado': 'ZZ'})
        mapa.unlink()

    def test_el_contador_no_fabrica_un_resultado(self):
        """Estado, advertencias y líneas solo los pone «Calcular»: ni por write, ni por create, ni por las líneas."""
        consolidacion = self._calculada(tipo='resultados')
        avisos, lineas = consolidacion.advertencias, consolidacion.linea_ids
        mia = consolidacion.with_user(self.contador)
        for valores in ({'estado': 'borrador'}, {'advertencias': 'Todo bien'}, {'calculada_por': self.lectura.id},
                        {'linea_ids': [Command.clear()]}):
            with self.assertRaises(AccessError, msg=str(valores)):
                mia.write(valores)
            with self.assertRaises(AccessError, msg=str(valores)):
                call_kw(mia, 'write', [mia.ids, valores], {})
        with self.assertRaises(AccessError):
            self.env[MODELO].with_user(self.contador).create({'name': 'Falso', 'estado': 'calculada'})
        with self.assertRaises(AccessError):
            self.env[MODELO].with_user(self.contador).create({'name': 'Falso', 'advertencias': 'Nada que ver'})
        # Con el resultado calculado, lo que lo define no se cambia sin volver a borrador.
        with self.assertRaises(UserError):
            mia.write({'fecha_hasta': '2030-03-15'})
        with self.assertRaises(UserError):
            mia.write({'tipo_reporte': 'balance'})
        # Las líneas no se editan a mano.
        linea = lineas[0].with_user(self.contador)
        with self.assertRaises(AccessError):
            linea.write({'importe': 1.0})
        with self.assertRaises(AccessError):
            linea.unlink()
        with self.assertRaises(AccessError):
            self.env['dcasa.consolidacion.linea'].with_user(self.contador).create({
                'consolidacion_id': consolidacion.id, 'seccion': 'ventas', 'columna': 'X', 'tipo_columna': 'empresa'})
        self.assertEqual((consolidacion.estado, consolidacion.advertencias, consolidacion.linea_ids),
                         ('calculada', avisos, lineas))
        # El nombre sí se edita.
        mia.write({'name': 'Otro nombre'})
        self.assertEqual(consolidacion.name, 'Otro nombre')

    # ------------------------------------------------------------------
    # Empresas a las que se tiene acceso
    # ------------------------------------------------------------------

    def test_no_se_incluyen_empresas_sin_acceso(self):
        with self.assertRaises(AccessError):
            self.env[MODELO].with_user(self.contador_a).create({
                'name': 'Con una ajena', 'company_ids': [Command.set(self.grupo.ids)]})
        propia = self.env[MODELO].with_user(self.contador_a).create({
            'name': 'Solo la mía', 'tipo_reporte': 'balance', 'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31',
            'company_ids': [Command.set(self.empresa_a.ids)]})
        with self.assertRaises(AccessError):
            propia.write({'company_ids': [Command.link(self.empresa_b.id)]})
        self.assertEqual(propia.sudo().company_ids, self.empresa_a)
        propia.action_calcular()
        self.assertEqual(set(propia.linea_ids.mapped('columna')), {self.empresa_a.name, 'Consolidado'})
        # Calcular con una sola empresa nunca lee los apuntes de la otra.
        self.assertNotIn(self.empresa_b.name, ' '.join(propia.linea_ids.mapped('columna')))

    def test_no_se_ve_ni_se_calcula_un_grupo_con_empresas_ajenas(self):
        grupo = self._calculada()
        lineas = grupo.linea_ids
        ajeno = grupo.with_user(self.contador_a)
        self.assertEqual(self.env[MODELO].with_user(self.contador_a).search_count([('id', '=', grupo.id)]), 0)
        self.assertEqual(self.env['dcasa.consolidacion.linea'].with_user(self.contador_a).search_count(
            [('consolidacion_id', '=', grupo.id)]), 0)
        with self.assertRaises(AccessError):
            ajeno.read(['name'])
        with self.assertRaises(AccessError):
            lineas.with_user(self.contador_a).read(['importe'])
        with self.assertRaises(AccessError):
            self.rpc(self.contador_a, MODELO, 'action_calcular', grupo.ids)
        with self.assertRaises(AccessError):
            self.rpc(self.contador_a, MODELO, 'action_borrador', grupo.ids)
        with self.assertRaises(AccessError):
            self.env['ir.actions.report'].with_user(self.contador_a)._render_qweb_html(
                'dcasa_consolidacion.reporte_consolidacion', grupo.ids)
        self.assertEqual((grupo.estado, grupo.linea_ids), ('calculada', lineas))
        # El mapa de la otra empresa tampoco se ve.
        self.env['dcasa.consolidacion.mapa'].create({
            'company_id': self.empresa_b.id, 'account_id': self.cuenta(self.empresa_b, 'income').id,
            'codigo_consolidado': 'B1'})
        self.assertEqual(self.env['dcasa.consolidacion.mapa'].with_user(self.contador_a).search_count([]), 0)

    def test_el_selector_de_empresas_no_recorta_el_grupo(self):
        """Con una sola empresa activa en el selector, un consolidado de las dos sigue siendo de las dos."""
        grupo = self._calculada()
        con_una = grupo.with_user(self.contador).with_context(allowed_company_ids=[self.empresa_a.id])
        con_una.action_calcular()
        self.assertEqual(set(grupo.linea_ids.filtered(lambda ln: ln.tipo_columna == 'empresa').mapped('columna')),
                         {self.empresa_a.name, self.empresa_b.name})
        self.assertEqual(grupo.empresas_resumen, f'{self.empresa_a.name}, {self.empresa_b.name}')

    def test_el_formulario_se_lee_como_contador(self):
        """Lo mismo que pide la pantalla al abrir la consolidación (con una empresa activa en el selector)."""
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        consolidacion = self._calculada()
        mia = consolidacion.with_user(self.contador).with_context(allowed_company_ids=[self.empresa_a.id])
        especificacion = {campo: {} for campo in (
            'name', 'tipo_reporte', 'fecha_desde', 'fecha_hasta', 'estado', 'advertencias', 'una_empresa',
            'monedas_distintas', 'utilidad_neta', 'diferencia', 'cuadra', 'calculada_el', 'empresas_resumen')}
        especificacion['company_ids'] = {'fields': {'display_name': {}}}
        especificacion['calculada_por'] = {'fields': {'display_name': {}}}
        especificacion['linea_ids'] = {'fields': {campo: {} for campo in (
            'seccion', 'cuenta', 'columna', 'tipo_columna', 'importe', 'inicial', 'debe', 'haber')}}
        datos = mia.web_read(especificacion)[0]
        self.assertEqual(datos['estado'], 'calculada')
        self.assertFalse(datos['cuadra'])
        self.assertIn('Descuadre', datos['advertencias'])
        self.assertEqual(len(datos['linea_ids']), len(consolidacion.linea_ids))
        self.assertEqual(datos['empresas_resumen'], f'{self.empresa_a.name}, {self.empresa_b.name}')

    def test_el_boton_pide_el_grupo_aunque_el_acl_dejara_escribir(self):
        """La comprobación del grupo contable está en el servidor, no solo en los permisos de la tabla: aunque
        alguien le diera escritura a «solo lectura», calcular y volver a borrador siguen siendo del contador."""
        modelo = self.env.ref('dcasa_consolidacion.model_dcasa_consolidacion')
        self.env['ir.model.access'].create({
            'name': 'prueba: lectura escribe', 'model_id': modelo.id,
            'group_id': self.env.ref('account.group_account_readonly').id,
            'perm_read': 1, 'perm_write': 1, 'perm_create': 1, 'perm_unlink': 0})
        consolidacion = self._calculada()
        lineas = consolidacion.linea_ids
        for metodo in ('action_calcular', 'action_borrador'):
            with self.assertRaises(AccessError, msg=metodo):
                self.rpc(self.lectura, MODELO, metodo, consolidacion.ids)
        with self.assertRaises(AccessError):
            consolidacion.with_user(self.lectura)._exigir_contador()
        self.assertEqual((consolidacion.estado, consolidacion.linea_ids), ('calculada', lineas))
        consolidacion.with_user(self.contador)._exigir_contador()

    def test_las_empresas_se_comprueban_aunque_la_regla_de_registro_no_estuviera(self):
        """Segunda línea de defensa: quien no tiene acceso a una empresa no la mete en un grupo ni lo calcula."""
        self.env.ref('dcasa_consolidacion.regla_consolidacion_empresas').active = False
        self.env.ref('dcasa_consolidacion.regla_consolidacion_linea_empresas').active = False
        consolidacion = self._calculada()
        with self.assertRaises(AccessError):
            self.env[MODELO].with_user(self.contador_a).create({
                'name': 'Con una ajena', 'company_ids': [Command.set(self.grupo.ids)]})
        with self.assertRaises(AccessError):
            self.rpc(self.contador_a, MODELO, 'action_calcular', consolidacion.ids)
        with self.assertRaises(AccessError):
            consolidacion.with_user(self.contador_a)._comprobar_empresas_permitidas()
        consolidacion.with_user(self.contador)._comprobar_empresas_permitidas()
