"""Las pantallas se arman y dicen lo que tienen que decir (sin JS propio: son vistas de Odoo)."""
from lxml import etree

from odoo.tests import tagged

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
