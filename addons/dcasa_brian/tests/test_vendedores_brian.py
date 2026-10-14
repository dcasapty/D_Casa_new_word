"""Brian y el programa de vendedores: lee, afilia, suspende y ajusta, siempre con las reglas del programa."""
import copy
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.addons.dcasa_socios.tests.common import VENDEDORES_DE_PRUEBA
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBrianVendedores(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            ids = [cls.env.ref(g).id for g in ('base.group_user', *grupos)]
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login,
                                    'group_ids': [Command.set(ids)]})

        cls.caja = usuario('brian_v_caja', ('sales_team.group_sale_salesman',))
        cls.gerente = usuario('brian_v_gerente', ('sales_team.group_sale_manager',))
        cls.interno = usuario('brian_v_interno', ())
        Partner = cls.env['res.partner']
        cls.ana = Partner.create({'name': 'Brianzeta Ana', 'vat': '8-710-710', 'phone': '6150-0001'})
        cls.luis = Partner.create({'name': 'Brianzeta Luis', 'vat': '8-720-720', 'phone': '6150-0002'})
        cls.sin_cedula = Partner.create({'name': 'Brianzeta Sin Cedula', 'phone': '6150-0003'})

    def setUp(self):
        super().setUp()
        reglas = R.cargar_reglas()
        reglas['vendedores'] = copy.deepcopy(VENDEDORES_DE_PRUEBA)
        self.reglas = reglas
        parche = patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas)
        parche.start()
        self.addCleanup(parche.stop)

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def confirmar(self, usuario, respuesta):
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        return self.env['brian.herramientas'].with_user(usuario).confirmar(respuesta['accion_id'])

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def afiliar(self, persona='Brianzeta Ana', tipo='externo', quien=None, **extra):
        quien = quien or self.caja
        respuesta = self.ejecutar(quien, 'afiliar_vendedor', {
            'persona': persona, 'tipo': tipo, 'acepto_terminos': True, **extra})
        return self.ok(self.confirmar(quien, respuesta))

    def test_quien_ve_que(self):
        def nombres(usuario):
            return {h['name'] for h in self.env['brian.herramientas'].with_user(usuario).catalogo()}
        self.assertNotIn('consultar_vendedor', nombres(self.interno))
        self.assertIn('consultar_vendedor', nombres(self.caja))
        self.assertNotIn('afiliar_vendedor', nombres(self.interno))
        self.assertIn('afiliar_vendedor', nombres(self.caja), 'En caja se afilia')
        for solo_gerencia in ('suspender_vendedor', 'reactivar_vendedor', 'ajustar_puntos_vendedor',
                              'resumen_programa_vendedores'):
            self.assertNotIn(solo_gerencia, nombres(self.caja), solo_gerencia)
            self.assertIn(solo_gerencia, nombres(self.gerente), solo_gerencia)

    def test_afiliar_pide_confirmacion_y_la_tarjeta_dice_que_la_persona_acepto(self):
        respuesta = self.ejecutar(self.caja, 'afiliar_vendedor', {
            'persona': 'Brianzeta Ana', 'tipo': 'empleado', 'acepto_terminos': True})
        self.assertTrue(respuesta['requiere_confirmacion'])
        self.assertIn('ya leyó y aceptó los términos', respuesta['resumen'])
        self.assertFalse(self.ana.dcasa_vendedor_codigo, 'Todavía no se hizo nada')
        datos = self.ok(self.confirmar(self.caja, respuesta))
        self.assertTrue(datos['codigo'].startswith('VEN'))
        self.assertEqual(self.ana.dcasa_vendedor_tipo, 'empleado')
        self.assertEqual(self.ana.dcasa_vendedor_afiliado_por, 'brian_v_caja')

    def test_sin_aceptar_los_terminos_no_se_afilia(self):
        respuesta = self.ejecutar(self.caja, 'afiliar_vendedor', {
            'persona': 'Brianzeta Ana', 'tipo': 'externo', 'acepto_terminos': False})
        self.assertIn('no se puede afiliar', respuesta.get('resumen', '').lower())
        resultado = self.confirmar(self.caja, respuesta)
        self.assertFalse(resultado['ok'])
        self.assertIn('términos', resultado['error'])
        self.assertFalse(self.ana.dcasa_vendedor_codigo)

    def test_lo_que_falta_vuelve_con_las_palabras_del_programa(self):
        respuesta = self.ejecutar(self.caja, 'afiliar_vendedor', {
            'persona': 'Brianzeta Sin Cedula', 'tipo': 'externo', 'acepto_terminos': True})
        resultado = self.confirmar(self.caja, respuesta)
        self.assertFalse(resultado['ok'])
        self.assertIn('cédula o RUC', resultado['error'])

    def test_patrocinador_por_codigo_y_consulta(self):
        padrino = self.afiliar('Brianzeta Ana')
        datos = self.afiliar('Brianzeta Luis', 'empleado', quien=self.gerente, patrocinador=padrino['codigo'])
        self.assertEqual(datos['patrocinador'], self.ana.display_name)
        # En caja no se escribe patrocinador: lo hace Gerencia.
        self.env['res.partner'].create({'name': 'Brianzeta Nueva', 'vat': '8-730-730', 'phone': '6150-0004'})
        intento = self.confirmar(self.caja, self.ejecutar(self.caja, 'afiliar_vendedor', {
            'persona': 'Brianzeta Nueva', 'tipo': 'externo', 'acepto_terminos': True,
            'patrocinador': padrino['codigo']}))
        self.assertFalse(intento['ok'])
        self.assertIn('Gerencia', intento['error'])
        ficha = self.ok(self.ejecutar(self.caja, 'consultar_vendedor', {'vendedor': padrino['codigo']}))
        self.assertEqual((ficha['directos'], ficha['codigo'], ficha['patrocinador']),
                         (1, padrino['codigo'], 'ninguno'))
        otra = self.ok(self.ejecutar(self.caja, 'consultar_vendedor', {'vendedor': 'Brianzeta Luis'}))
        self.assertEqual(otra['patrocinador'], self.ana.display_name)
        self.assertEqual(otra['tipo'], 'Empleado de D’CASA')

    def test_consultar_a_quien_no_es_vendedor_lo_explica(self):
        respuesta = self.ejecutar(self.caja, 'consultar_vendedor', {'vendedor': 'Brianzeta Luis'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('todavía no es vendedor', respuesta['error'])

    def test_suspender_y_reactivar_son_de_gerencia_con_confirmacion_y_motivo(self):
        self.afiliar()
        respuesta = self.ejecutar(self.gerente, 'suspender_vendedor', {
            'vendedor': 'Brianzeta Ana', 'motivo': 'Compraba con su propio código'})
        self.assertIn('Compraba con su propio código', respuesta['resumen'])
        self.ok(self.confirmar(self.gerente, respuesta))
        self.assertEqual(self.ana.dcasa_vendedor_estado, 'suspendido')
        self.assertIn('Compraba con su propio código', ' '.join(self.ana.message_ids.mapped('body')))
        repetida = self.confirmar(self.gerente, self.ejecutar(self.gerente, 'suspender_vendedor', {
            'vendedor': 'Brianzeta Ana', 'motivo': 'Otra vez'}))
        self.assertFalse(repetida['ok'])
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'reactivar_vendedor', {
            'vendedor': 'Brianzeta Ana'})))
        self.assertEqual(self.ana.dcasa_vendedor_estado, 'activo')

    def test_ajuste_de_puntos_de_vendedor_queda_en_su_libro(self):
        self.afiliar()
        datos = self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'ajustar_puntos_vendedor', {
            'vendedor': 'Brianzeta Ana', 'puntos': 250, 'motivo': 'Venta de julio sin registrar'})))
        self.assertEqual((datos['antes'], datos['ahora']), (0, 250))
        asiento = self.env['dcasa.vend.movimiento'].search([('partner_id', '=', self.ana.id)])
        self.assertEqual((asiento.tipo, asiento.puntos, asiento.autor), ('ajuste', 250, 'brian_v_gerente'))
        fallo = self.confirmar(self.gerente, self.ejecutar(self.gerente, 'ajustar_puntos_vendedor', {
            'vendedor': 'Brianzeta Ana', 'puntos': -900, 'motivo': 'Error'}))
        self.assertFalse(fallo['ok'])
        self.assertIn('solo tiene 250', fallo['error'])

    def test_resumen_del_programa(self):
        self.afiliar()
        datos = self.ok(self.ejecutar(self.gerente, 'resumen_programa_vendedores'))
        self.assertEqual(datos['programa'], 'encendido')
        self.assertEqual(datos['vendedores_activos'], 1)
        self.assertEqual(datos['costo_como_porcentaje_de_la_venta'], 'sin ventas todavía')
        self.reglas['vendedores']['programaActivo'] = False
        apagado = self.ok(self.ejecutar(self.gerente, 'resumen_programa_vendedores'))
        self.assertIn('apagado', apagado['programa'])
