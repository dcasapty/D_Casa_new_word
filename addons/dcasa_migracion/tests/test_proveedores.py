"""Proveedores: mismo cargador que los clientes; quien es cliente y proveedor tiene una sola ficha."""
from odoo.addons.dcasa_migracion import contactos as C
from odoo.addons.dcasa_migracion import reglas
from odoo.tests import TransactionCase, tagged

from . import ejemplos

# El mismo número que un cliente de ejemplo (90002): es cliente Y proveedor.
PROVEEDOR_QUE_TAMBIEN_ES_CLIENTE = (
    'id_viejo,nombre,tipo,ruc,telefono,correo\n'
    '90002,Cliente de Prueba 2,persona,0-000-0002,+507 6000-0002,prueba2@ejemplo.com\n')


def _proveedores(texto=ejemplos.PROVEEDORES):
    filas, errores = reglas.filas_proveedores(texto)
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

    def test_los_cinco_proveedores_de_ejemplo(self):
        resumen = C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual([i for i, _n in resumen['creados']], [70001, 70002, 70003, 70004, 70005])
        uno = self._ficha(70001)
        self.assertEqual((uno.supplier_rank, uno.customer_rank), (1, 0))
        self.assertTrue(uno.is_company)
        self.assertEqual((uno.vat, uno.l10n_pa_dv, uno.phone, uno.street), (
            '0000000-0-000001', '99', '200-0001', 'Zona de Prueba, Galera 1'))
        self.assertEqual(uno.category_id.mapped('name'), ['Sistema anterior'])
        self.assertIn('Proveedor n.º 70001 del sistema anterior', uno.comment)

    def test_el_pais_se_busca_por_su_nombre_y_sin_pais_es_panama(self):
        C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual(self._ficha(70001).country_id, self.env.ref('base.pa'))
        self.assertEqual(self._ficha(70002).country_id, self.env.ref('base.cn'))
        self.assertEqual(self._ficha(70005).country_id, self.env.ref('base.us'))
        self.assertEqual(self._ficha(70004).country_id, self.env.ref('base.pa'), 'Sin país en el archivo: Panamá')

    def test_un_pais_que_no_se_reconoce_va_a_la_nota(self):
        texto = 'id_viejo,nombre,pais\n1,Proveedor Raro de Prueba,Atlantida\n'
        C.cargar_proveedores(self.env, _proveedores(texto))
        ficha = self._ficha(1)
        self.assertFalse(ficha.country_id)
        self.assertIn('País en el sistema anterior: Atlantida', ficha.comment)

    def test_el_ruc_de_un_proveedor_extranjero_se_guarda_como_estaba(self):
        """El formato del RUC de Panamá no vale para uno de China: no se valida, pero el candado sí lo compara."""
        C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual(self._ficha(70002).vat, 'PRUEBA-0002')
        self.assertEqual(self._ficha(70002).phone, '+86 000 0000 0002')

    def test_quien_es_cliente_y_proveedor_tiene_una_sola_ficha(self):
        C.cargar_clientes(self.env, _clientes())
        fichas = self.env['res.partner'].search_count([])
        resumen = C.cargar_proveedores(self.env, _proveedores(PROVEEDOR_QUE_TAMBIEN_ES_CLIENTE))
        self.assertEqual((resumen['ampliados'], resumen['creados']), ([90002], []))
        self.assertEqual(self.env['res.partner'].search_count([]), fichas)
        doble = self._ficha(90002)
        self.assertEqual((doble.customer_rank, doble.supplier_rank), (1, 1))

    def test_volver_a_cargar_no_repite_nada(self):
        C.cargar_proveedores(self.env, _proveedores())
        segunda = C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual((segunda['creados'], segunda['ampliados']), ([], []))
        self.assertEqual(segunda['ya_estaban'], [70001, 70002, 70003, 70004, 70005])

    def test_dos_cargas_de_quien_es_cliente_y_proveedor_no_repiten_el_papel(self):
        C.cargar_clientes(self.env, _clientes())
        C.cargar_proveedores(self.env, _proveedores(PROVEEDOR_QUE_TAMBIEN_ES_CLIENTE))
        segunda = C.cargar_proveedores(self.env, _proveedores(PROVEEDOR_QUE_TAMBIEN_ES_CLIENTE))
        self.assertEqual((segunda['ampliados'], segunda['ya_estaban']), ([], [90002]))

    def test_el_candado_tambien_vale_para_proveedores(self):
        self.env['res.partner'].create({'name': 'Ya Estaba Aquí', 'email': 'ventas@proveedor1-prueba.com'})
        resumen = C.cargar_proveedores(self.env, _proveedores())
        self.assertEqual([i for i, _n, _m in resumen['con_error']], [70001])
        self.assertIn('Ya Estaba Aquí', resumen['con_error'][0][2])
        self.assertEqual([i for i, _n in resumen['creados']], [70002, 70003, 70004, 70005])
