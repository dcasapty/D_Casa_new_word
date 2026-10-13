"""Proveedores: mismo cargador que los clientes; quien es cliente y proveedor tiene una sola ficha."""
from odoo.addons.dcasa_migracion import contactos as C
from odoo.addons.dcasa_migracion import reglas
from odoo.tests import TransactionCase, tagged

from . import ejemplos


def _proveedores():
    filas, errores = reglas.filas_proveedores(ejemplos.PROVEEDORES)
    assert not errores
    return filas


def _clientes():
    filas, errores = reglas.filas_clientes(ejemplos.CLIENTES)
    assert not errores
    return filas


@tagged('post_install', '-at_install')
class TestCargaDeProveedores(TransactionCase):

    def _ficha(self, id_viejo):
        return self.env.ref(f'__import__.{C.xmlid_contacto(id_viejo)}', raise_if_not_found=False)

    def test_un_proveedor_es_proveedor_y_no_cliente(self):
        resumen = C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual([i for i, _n in resumen['creados']], [70001, 90002, 70003])
        ficha = self._ficha(70001)
        self.assertEqual((ficha.supplier_rank, ficha.customer_rank), (1, 0))
        self.assertTrue(ficha.is_company)
        self.assertEqual((ficha.vat, ficha.l10n_pa_dv), ('0000000-0-000101', '77'))
        self.assertEqual(ficha.category_id.mapped('name'), ['Sistema anterior'])
        self.assertIn('Proveedor n.º 70001 del sistema anterior', ficha.comment)

    def test_quien_es_cliente_y_proveedor_tiene_una_sola_ficha(self):
        C.cargar_clientes(self.env, _clientes())
        fichas = self.env['res.partner'].search_count([])
        resumen = C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual(resumen['ampliados'], [90002])
        self.assertEqual([i for i, _n in resumen['creados']], [70001, 70003])
        self.assertEqual(self.env['res.partner'].search_count([]), fichas + 2)
        doble = self._ficha(90002)
        self.assertEqual((doble.customer_rank, doble.supplier_rank), (1, 1))

    def test_volver_a_cargar_no_repite_nada(self):
        C.cargar_clientes(self.env, _clientes())
        C.cargar_proveedores(self.env, _proveedores())
        segunda = C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual((segunda['creados'], segunda['ampliados']), ([], []))
        self.assertEqual(segunda['ya_estaban'], [70001, 90002, 70003])

    def test_el_candado_tambien_vale_para_proveedores(self):
        self.env['res.partner'].create({'name': 'Ya Estaba Aquí', 'email': 'ventas@proveedor-prueba.com'})
        resumen = C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual([i for i, _n, _m in resumen['con_error']], [70001])
        self.assertIn('Ya Estaba Aquí', resumen['con_error'][0][2])
        self.assertEqual([i for i, _n in resumen['creados']], [90002, 70003])
