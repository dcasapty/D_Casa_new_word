"""La carga de clientes: una ficha por cliente, idempotente, sin saltarse el candado y sin tocar Socios."""
from odoo.addons.dcasa_migracion import contactos as C
from odoo.addons.dcasa_migracion import documentos, informe, reglas
from odoo.tests import TransactionCase, tagged

from . import ejemplos


def _filas():
    filas, errores = reglas.filas_clientes(ejemplos.CLIENTES)
    assert not errores
    return filas


@tagged('post_install', '-at_install')
class TestCargaDeClientes(TransactionCase):

    def _ficha(self, id_viejo):
        return self.env.ref(f'__import__.{C.xmlid_contacto(id_viejo)}', raise_if_not_found=False)

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
        self.assertEqual(dos.dcasa_telefono_fijo, '+507 200-0005', 'el fijo, a su campo (2026-10-22)')
        self.assertFalse(persona.dcasa_telefono_fijo)

    def test_el_id_externo_no_es_del_modulo_asi_quitarlo_no_borra_clientes(self):
        """Desinstalar un módulo borra lo que tiene id externo suyo: los clientes llevan el de «__import__»."""
        C.cargar_clientes(self.env, _filas())
        externos = self.env['ir.model.data'].search(
            [('model', '=', 'res.partner'), ('name', '=like', 'dcasa_contacto_%')])
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

    def test_quien_carga_desde_la_pantalla_no_choca_con_celular_y_correo_obligatorios(self):
        """La carga corre como la persona de la pantalla (no como superusuario): lo viejo entra como estaba, sin correo
        o con un número incompleto, y el celular y el correo se piden en su próxima venta (2026-10-16)."""
        texto = ejemplos.BOM + '\n'.join([
            'id_viejo,nombre,tipo,cedula_ruc,dv,celular,correo,direccion,ciudad',
            '92001,Cliente Viejo Sin Correo,persona,,,6000-0201,,,',
            '92002,Cliente Viejo Corto,persona,,,345-678,,,',
            '',
        ])
        filas, errores = reglas.filas_clientes(texto)
        self.assertFalse(errores)
        administrador = self.env.ref('base.user_admin')
        resumen = C.cargar_clientes(self.env(user=administrador), filas)
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual([i for i, _n in resumen['creados']], [92001, 92002])
        self.assertEqual(self._ficha(92002).phone, '345-678', 'lo viejo entra como estaba')

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

    def test_el_mismo_ruc_de_otra_ficha_enlaza_el_numero_viejo_a_esa_ficha(self):
        """Un RUC, una persona: no se crea otra ficha ni se pisa la que ya existe; el número viejo apunta a ella."""
        dueno = self.env['res.partner'].create({'name': 'Dueño del RUC', 'vat': '0-000-0005'})
        antes = self.env['res.partner'].search_count([])
        resumen = C.cargar_clientes(self.env, _filas())
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual(resumen['enlazados'], [(90005, None, 'Dueño del RUC')])
        self.assertEqual([i for i, _n in resumen['creados']], [90001, 90002, 90003, 90004])
        self.assertEqual(self.env['res.partner'].search_count([]), antes + 4)
        self.assertEqual(self._ficha(90005), dueno)
        self.assertEqual((dueno.name, dueno.customer_rank), ('Dueño del RUC', 1))

    def test_dos_numeros_con_el_mismo_ruc_quedan_en_una_sola_ficha(self):
        texto = ejemplos.BOM + '\n'.join([
            'id_viejo,nombre,tipo,cedula_ruc,dv,celular,correo,direccion,ciudad',
            '91001,Cliente Repetido A,persona,0-000-0091,,6000-0091,,,',
            '91002,Cliente Repetido B,persona,0 000 0091,,6000-0092,otro@ejemplo.com,,',
            '91003,Otra Persona,persona,0-000-0093,,6000-0093,,,',
            '',
        ])
        filas, errores = reglas.filas_clientes(texto)
        self.assertFalse(errores)
        resumen = C.cargar_clientes(self.env, filas)
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual([i for i, _n in resumen['creados']], [91001, 91003])
        self.assertEqual(resumen['enlazados'], [(91002, '91001', 'Cliente Repetido A')])
        self.assertEqual(self._ficha(91002), self._ficha(91001))
        self.assertEqual(self._ficha(91001).name, 'Cliente Repetido A')
        # Las órdenes, facturas y pagos del número repetido buscan su ficha por el mismo id externo.
        self.assertEqual(documentos._contacto(self.env, 91002), self._ficha(91001).id)
        # Volver a cargar no cambia nada: los tres números ya apuntan a su ficha.
        segunda = C.cargar_clientes(self.env, filas)
        self.assertEqual((segunda['creados'], segunda['enlazados'], segunda['con_error']), ([], [], []))
        self.assertEqual(segunda['ya_estaban'], [91001, 91002, 91003])

    def test_el_informe_dice_cuales_se_enlazaron_para_revisarlos(self):
        self.env['res.partner'].create({'name': 'Dueño del RUC', 'vat': '0-000-0005'})
        resumen = C.cargar_clientes(self.env, _filas())
        html = str(informe._seccion_contactos('Clientes', resumen))
        self.assertIn('Repetidos enlazados', html)
        self.assertIn('n.º 90005 usa la ficha que ya existía de «Dueño del RUC»', html)
        self.assertIn('No se pudieron crear: <b>0</b>', html)

    def test_los_nombres_de_las_personas_no_van_al_log(self):
        with self.assertLogs('odoo.addons.dcasa_migracion.contactos', level='INFO') as registro:
            C.cargar_clientes(self.env, _filas())
        texto = '\n'.join(registro.output)
        self.assertIn('5 creados', texto)
        for nombre in ('Cliente de Prueba', 'Empresa de Prueba', '0-000-0001', 'ejemplo.com'):
            self.assertNotIn(nombre, texto)
