"""Las pantallas se arman y dicen lo que tienen que decir (vistas de Odoo; el único JS propio es que el formulario de
una versión nueva no se guarda solo: ``test_version_nueva_navegador``)."""
from lxml import etree

from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from .common import ComisionCommon

ACCIONES = ('accion_ventas', 'accion_liquidaciones', 'accion_reglas', 'accion_libro', 'accion_reparto')


@tagged('post_install', '-at_install')
class TestPantallas(ComisionCommon):

    def test_cada_accion_abre_con_sus_vistas(self):
        for nombre in ACCIONES:
            with self.subTest(accion=nombre):
                accion = self.env.ref(f'dcasa_comision_web.{nombre}')
                modelo = self.env[accion.res_model].with_user(self.u_nomina)
                vistas = [[False, tipo] for tipo in accion.view_mode.split(',')]
                datos = modelo.get_views(vistas)
                self.assertEqual(set(datos['views']), set(accion.view_mode.split(',')))

    def test_las_ventas_del_sitio_tienen_lista_grafico_y_pivote_por_mes(self):
        accion = self.env.ref('dcasa_comision_web.accion_ventas')
        self.assertEqual(accion.view_mode, 'list,pivot,graph,form')
        self.venta_web()
        pivote = self.env['dcasa.web.venta'].with_user(self.u_nomina).read_group(
            [], ['productos:sum', 'base:sum'], ['mes:month'])
        self.assertEqual(pivote[0]['productos'], 1000.0)

    def test_el_formulario_de_reglas_explica_la_base_con_un_ejemplo_y_el_reparto(self):
        vista = self.env['dcasa.web.reglas'].with_user(self.u_nomina).get_views([[False, 'form']])
        arch = etree.fromstring(vista['views']['form']['arch'])
        campos = {n.get('name') for n in arch.iter('field')}
        self.assertTrue({'base_itbms', 'base_envio', 'base_descuentos', 'base_devoluciones', 'base_pasarela',
                         'ejemplo_html', 'reparto_ids', 'porcentaje', 'tarifa_fija', 'tarifa_periodo',
                         'rige_desde'} <= campos)
        texto = ' '.join(arch.itertext())
        self.assertIn('solo hacia', texto)
        self.assertIn('no se edita', texto)

    def test_la_liquidacion_explica_que_quien_cobra_no_aprueba(self):
        vista = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).get_views([[False, 'form']])
        texto = ' '.join(etree.fromstring(vista['views']['form']['arch']).itertext())
        self.assertIn('Tú figuras entre quienes cobran', texto)
        self.assertIn('Nada se paga solo', texto)

    def test_quienes_reciben_muestra_lo_que_se_le_debe_a_cada_quien(self):
        self.version(10.0)
        self.venta_web()
        reparto = self.env['dcasa.web.reparto'].with_user(self.u_nomina).search([])
        por_persona = {r.empleado_id: r.por_pagar_comision for r in reparto}
        self.assertEqual(por_persona, {self.ana: 60.0, self.beto: 40.0})

    def _invisible(self, arch, **ruta):
        """La condición ``invisible`` del nodo que cumple ``ruta`` (``name=...`` y/o ``string``) ya evaluada."""
        for nodo in arch.iter():
            if all(nodo.get(clave) == valor for clave, valor in ruta.items()):
                return nodo.get('invisible')
        self.fail(f'No está el nodo {ruta}')

    def test_anular_y_su_motivo_solo_se_ven_en_una_version_ya_guardada_y_que_todavia_no_rige(self):
        """Una versión nueva y sin guardar (su ``estado`` sale «programada») no ofrece «Anular» ni el motivo."""
        vista = self.env['dcasa.web.reglas'].with_user(self.u_nomina).get_views([[False, 'form']])
        arch = etree.fromstring(vista['views']['form']['arch'])
        boton = self._invisible(arch, name='action_anular')
        motivo = self._invisible(arch, name='motivo_anulacion')
        casos = (({'id': False, 'estado': 'programada'}, True), ({'id': 7, 'estado': 'programada'}, False),
                 ({'id': 7, 'estado': 'tapada'}, False), ({'id': 7, 'estado': 'vigente'}, True),
                 ({'id': 7, 'estado': 'anterior'}, True))
        for valores, oculto in casos:
            with self.subTest(valores=valores):
                self.assertEqual(bool(safe_eval(boton, valores)), oculto)
        self.assertTrue(safe_eval(motivo, {'id': False, 'estado': 'programada'}), 'no sale en la versión nueva')
        self.assertFalse(safe_eval(motivo, {'id': 7, 'estado': 'programada'}))
        self.assertFalse(safe_eval(motivo, {'id': 7, 'estado': 'anulada'}))

    def test_el_formulario_de_una_version_nueva_no_se_guarda_solo(self):
        vista = self.env['dcasa.web.reglas'].with_user(self.u_nomina).get_views([[False, 'form']])
        arch = etree.fromstring(vista['views']['form']['arch'])
        self.assertEqual(arch.get('js_class'), 'dcasa_reglas_form')
        texto = ' '.join(arch.itertext())
        self.assertIn('No se guarda sola', texto)

    def test_los_botones_de_la_cabecera_de_cada_lista_se_ven_sin_escoger_filas(self):
        """En Odoo 19 un botón de la cabecera de una lista («Anotar un ajuste», «Nueva versión», «Cambiar quiénes
        reciben») solo sale al escoger filas, salvo con ``display="always"``; con él, en el celular queda en el menú
        de los tres puntos de la lista. Sin esto, ni en computadora se encontraba el botón."""
        for modelo, texto in (('dcasa.web.movimiento', 'Anotar un ajuste'), ('dcasa.web.reglas', 'Nueva versión'),
                              ('dcasa.web.reparto', 'Cambiar quiénes reciben')):
            with self.subTest(modelo=modelo):
                vista = self.env[modelo].with_user(self.u_nomina).get_views([[False, 'list']])
                arch = etree.fromstring(vista['views']['list']['arch'])
                botones = [b for b in arch.iter('button') if b.get('string') == texto]
                self.assertEqual(len(botones), 1)
                self.assertEqual(botones[0].get('display'), 'always')

    def test_anotar_un_ajuste_tambien_esta_en_el_menu_para_el_celular(self):
        """El botón de la lista del libro no se ve en pantallas chicas: el menú sí (un solo ajuste, la misma acción)."""
        menu = self.env.ref('dcasa_comision_web.menu_anotar_ajuste')
        self.assertEqual(menu.action, self.env.ref('dcasa_comision_web.accion_ajuste'))
        self.assertEqual(menu.parent_id, self.env.ref('dcasa_comision_web.menu_comision_web'))
        self.assertEqual(menu.group_ids, self.env.ref('dcasa_nomina.group_nomina'))
        visibles = self.env['ir.ui.menu'].with_user(self.u_nomina)._visible_menu_ids()
        self.assertIn(menu.id, visibles)
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(self.u_vendedora)._visible_menu_ids())
