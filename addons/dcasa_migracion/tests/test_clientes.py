"""La carga de clientes: una ficha por cliente, idempotente, sin saltarse el candado y sin tocar Socios."""
from odoo.addons.dcasa_migracion import clientes as C
from odoo.addons.dcasa_migracion import reglas
from odoo.tests import TransactionCase, tagged

from . import ejemplos


def _filas():
    filas, errores = reglas.filas_clientes(ejemplos.CLIENTES)
    assert not errores
    return filas


@tagged('post_install', '-at_install')
class TestCargaDeClientes(TransactionCase):

    def _ficha(self, id_viejo):
        return self.env.ref(f'__import__.{C.xmlid_cliente(id_viejo)}', raise_if_not_found=False)

    def test_crea_una_ficha_por_cliente_con_sus_datos(self):
        resumen = C.cargar_clientes(self.env, _filas())
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual([i for i, _n in resumen['creados']], [90001, 90002, 90003, 90004, 90005])

        persona = self._ficha(90001)
        self.assertEqual((persona.name, persona.vat, persona.phone), ('Cliente de Prueba 1', '0-000-0001', '6000-0001'))
        self.assertEqual(persona.country_id, self.env.ref('base.pa'))
        self.assertFalse(persona.is_company)
        self.assertEqual(persona.customer_rank, 1)
        self.assertEqual(persona.category_id.mapped('name'), ['Sistema anterior'])
        self.assertIn('Cliente n.º 90001 del sistema anterior', persona.comment)

        empresa = self._ficha(90003)
        self.assertTrue(empresa.is_company)
        self.assertEqual((empresa.l10n_pa_dv, empresa.email, empresa.street, empresa.city),
                         ('99', 'contacto@empresa-prueba.com', 'Edificio Prueba, Local 3', 'Ciudad de Prueba'))

        dos = self._ficha(90005)
        self.assertEqual(dos.phone, '60000005', 'Solo el número principal va al campo que identifica a la persona')
        self.assertIn('Otros teléfonos en el sistema anterior: 2000005', dos.comment)

    def test_el_id_externo_no_es_del_modulo_asi_quitarlo_no_borra_clientes(self):
        """Desinstalar un módulo borra lo que tiene id externo suyo: los clientes llevan el de «__import__»."""
        C.cargar_clientes(self.env, _filas())
        externos = self.env['ir.model.data'].search(
            [('model', '=', 'res.partner'), ('name', '=like', 'dcasa_cliente_%')])
        self.assertEqual(len(externos), 5)
        self.assertEqual(set(externos.mapped('module')), {'__import__'})

    def test_un_cliente_no_es_un_socio(self):
        """Nada de PIN, de celular de Socios ni de ficha reclamada: no junta puntos ni recibe nada."""
        C.cargar_clientes(self.env, _filas())
        for id_viejo in (90001, 90002, 90005):
            ficha = self._ficha(id_viejo)
            with self.subTest(id_viejo=id_viejo):
                self.assertFalse(ficha.dcasa_celular)
                self.assertFalse(ficha.dcasa_pin_hash)
                self.assertFalse(ficha.dcasa_reclamada)
                self.assertEqual(ficha.dcasa_saldo, 0)
                self.assertFalse(ficha.dcasa_movimiento_ids)

    def test_no_llena_el_chatter_de_cada_ficha(self):
        C.cargar_clientes(self.env, _filas())
        self.assertFalse(self._ficha(90001).message_ids)

    def test_volver_a_cargar_no_crea_nada_ni_pisa_lo_que_se_cambio(self):
        C.cargar_clientes(self.env, _filas())
        self._ficha(90001).write({'name': 'Nombre corregido aquí'})
        total = self.env['res.partner'].search_count([])
        segunda = C.cargar_clientes(self.env, _filas())
        self.assertEqual(segunda['creados'], [])
        self.assertEqual(segunda['ya_estaban'], [90001, 90002, 90003, 90004, 90005])
        self.assertEqual(self.env['res.partner'].search_count([]), total)
        self.assertEqual(self._ficha(90001).name, 'Nombre corregido aquí')

    def test_el_candado_de_contactos_no_se_salta_y_las_demas_filas_siguen(self):
        existente = self.env['res.partner'].create({'name': 'Ya Estaba Aquí', 'phone': '6000-0001'})
        otro_correo = self.env['res.partner'].create({'name': 'Otro Ya Estaba', 'email': 'prueba2@ejemplo.com'})
        resumen = C.cargar_clientes(self.env, _filas())
        errores = {i: motivo for i, _n, motivo in resumen['con_error']}
        self.assertEqual(sorted(errores), [90001, 90002])
        self.assertIn('Ya Estaba Aquí', errores[90001])
        self.assertIn('Otro Ya Estaba', errores[90002])
        self.assertFalse(self._ficha(90001))
        self.assertFalse(self._ficha(90002))
        self.assertEqual([i for i, _n in resumen['creados']], [90003, 90004, 90005])
        self.assertEqual(existente.name, 'Ya Estaba Aquí')
        self.assertTrue(otro_correo.exists())

    def test_el_mismo_ruc_ya_registrado_tampoco_pasa(self):
        self.env['res.partner'].create({'name': 'Dueño del RUC', 'vat': '0-000-0005'})
        resumen = C.cargar_clientes(self.env, _filas())
        self.assertEqual([i for i, _n, _m in resumen['con_error']], [90005])
        self.assertIn('Dueño del RUC', resumen['con_error'][0][2])

    def test_los_nombres_de_las_personas_no_van_al_log(self):
        with self.assertLogs('odoo.addons.dcasa_migracion.clientes', level='INFO') as registro:
            C.cargar_clientes(self.env, _filas())
        texto = '\n'.join(registro.output)
        self.assertIn('5 creados', texto)
        for nombre in ('Cliente de Prueba', 'Empresa de Prueba', '0-000-0001', 'ejemplo.com'):
            self.assertNotIn(nombre, texto)
