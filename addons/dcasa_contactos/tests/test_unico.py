"""Una ficha por persona: mismo nombre sí; mismo celular, correo o RUC/cédula no."""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

SIN = {'dcasa_sin_duplicados': True}


@tagged('post_install', '-at_install')
class TestFichaUnica(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.ana = cls.Partner.create({'name': 'Ana Gómez Contactos', 'phone': '+507 6026-1919',
                                      'email': 'Ana.Gomez@Correo.com', 'vat': '8-123-456'})

    # --- mismo nombre sí ---------------------------------------------------------------------------------------

    def test_dos_personas_pueden_llamarse_igual(self):
        otra = self.Partner.create({'name': 'Ana Gómez Contactos', 'phone': '6111-2222', 'email': 'otra@correo.com'})
        self.assertTrue(otra.id)

    # --- celular ----------------------------------------------------------------------------------------------

    def test_mismo_celular_escrito_de_otra_forma_no_pasa_y_dice_de_quien_es(self):
        for escrito in ('60261919', '507 6026 1919', '00507-6026-1919', '+507 6026-1919'):
            with self.subTest(escrito=escrito), self.assertRaises(ValidationError) as cm:
                self.Partner.create({'name': 'Otra persona', 'phone': escrito})
            self.assertIn('Ana Gómez Contactos', str(cm.exception))
            self.assertIn('6026-1919', str(cm.exception))

    def test_el_celular_se_revisa_tambien_al_editar(self):
        otra = self.Partner.create({'name': 'Beto Contactos', 'phone': '6222-3333'})
        with self.assertRaises(ValidationError):
            otra.write({'phone': '60261919'})
        otra.write({'phone': '6222-4444'})  # uno libre sí
        self.assertEqual(otra.dcasa_telefono_llave, 'pa:62224444')

    def test_el_celular_de_socios_tambien_cuenta_como_telefono(self):
        socia = self.Partner.create({'name': 'Socia Contactos', 'dcasa_celular': '61231234'})
        with self.assertRaises(ValidationError):
            self.Partner.create({'name': 'Otra', 'phone': '+507 6123-1234'})
        with self.assertRaises(ValidationError):
            self.Partner.create({'name': 'Otra', 'dcasa_celular': '60261919'})  # el teléfono de Ana
        self.assertTrue(socia.id)

    def test_un_numero_de_otro_pais_no_se_confunde_con_uno_de_panama(self):
        gringo = self.Partner.create({'name': 'Cliente de Miami', 'phone': '+1 305 555 1234'})
        panameno = self.Partner.create({'name': 'Cliente de Panamá', 'phone': '5555-1234'})  # mismos últimos 8 dígitos
        self.assertNotEqual(gringo.dcasa_telefono_llave, panameno.dcasa_telefono_llave)
        with self.assertRaises(ValidationError):
            self.Partner.create({'name': 'Otro de Miami', 'phone': '1-305-555-1234'})

    # --- correo y RUC ------------------------------------------------------------------------------------------

    def test_mismo_correo_aunque_cambien_mayusculas_o_venga_con_nombre(self):
        for escrito in ('ana.gomez@correo.com', 'ANA.GOMEZ@CORREO.COM', 'Ana <ana.gomez@correo.com>'):
            with self.subTest(escrito=escrito), self.assertRaises(ValidationError) as cm:
                self.Partner.create({'name': 'Otra persona', 'email': escrito})
            self.assertIn('correo', str(cm.exception))

    def test_mismo_ruc_o_cedula_aunque_cambien_los_separadores(self):
        for escrito in ('8 123 456', '8.123.456', '8-123-456'):
            with self.subTest(escrito=escrito), self.assertRaises(ValidationError) as cm:
                self.Partner.create({'name': 'Otra persona', 'vat': escrito})
            self.assertIn('RUC o cédula', str(cm.exception))
        # otra cédula con los mismos dígitos pero distinta no choca
        self.Partner.create({'name': 'Otra cédula', 'vat': '8-12-3456'})

    def test_lo_que_no_identifica_no_cuenta(self):
        for vat in ('/', 'N/A', '0'):
            self.Partner.create({'name': f'Sin RUC {vat}', 'vat': vat})
            self.Partner.create({'name': f'Otra sin RUC {vat}', 'vat': vat})
        self.Partner.create({'name': 'Sin correo 1', 'email': 'no es un correo'})
        self.Partner.create({'name': 'Sin correo 2', 'email': 'no es un correo'})

    def test_una_ficha_archivada_sigue_ocupando_el_dato(self):
        self.ana.active = False
        with self.assertRaises(ValidationError):
            self.Partner.create({'name': 'Otra', 'email': 'ana.gomez@correo.com'})

    # --- quién no cuenta ----------------------------------------------------------------------------------------

    def test_las_direcciones_de_la_misma_persona_comparten_sus_datos(self):
        entrega = self.Partner.create({'name': 'Entrega de Ana', 'parent_id': self.ana.id, 'type': 'delivery',
                                       'phone': '+507 6026-1919', 'email': 'ana.gomez@correo.com'})
        self.assertTrue(entrega.id)
        factura = self.Partner.create({'name': 'Factura de Ana', 'parent_id': self.ana.id, 'type': 'invoice',
                                       'phone': '60261919'})
        self.assertTrue(factura.id)

    def test_un_usuario_no_choca_con_el_cliente_que_es_la_misma_persona(self):
        usuario = new_test_user(self.env, login='ana_usuaria_contactos', name='Ana Usuaria',
                                email='ana.gomez@correo.com', groups='base.group_user')
        self.assertTrue(usuario.partner_id.id)
        self.assertEqual(usuario.partner_id.email, 'ana.gomez@correo.com')

    def test_un_empleado_no_choca_con_el_cliente_que_es_la_misma_persona(self):
        empleado = self.env['hr.employee'].create({'name': 'Ana Empleada', 'work_email': 'ana.gomez@correo.com',
                                                   'work_phone': '+507 6026-1919'})
        self.assertTrue(empleado.work_contact_id)

    def test_el_contacto_de_un_usuario_o_de_un_empleado_no_cuenta_como_otra_ficha(self):
        new_test_user(self.env, login='usuaria_existente_contactos', name='Usuaria Existente',
                      email='usuaria.existente@correo.com', groups='base.group_user')
        self.env['hr.employee'].create({'name': 'Empleado Existente', 'work_email': 'empleado.existente@correo.com',
                                        'work_phone': '+507 6555-0101'})
        # una ficha de cliente nueva puede tener los mismos datos que el contacto de quien ya es del equipo
        self.Partner.create({'name': 'Cliente con el correo de la usuaria', 'email': 'usuaria.existente@correo.com'})
        self.Partner.create({'name': 'Cliente con los datos del empleado', 'email': 'empleado.existente@correo.com',
                             'phone': '6555-0101'})

    def test_la_empresa_propia_no_cuenta(self):
        empresa = self.env['res.company'].create({'name': 'Empresa del grupo prueba', 'vat': '8-123-456',
                                                  'phone': '+507 6026-1919', 'email': 'ana.gomez@correo.com'})
        self.assertTrue(empresa.partner_id)

    # --- lo viejo no se toca ------------------------------------------------------------------------------------

    def test_lo_ya_repetido_se_puede_seguir_editando_pero_no_empeorar(self):
        repetida = self.Partner.with_context(**SIN).create({'name': 'Repetida vieja', 'phone': '60261919'})
        repetida = repetida.with_env(self.env)  # sin la excepción: así edita una persona de verdad
        repetida.write({'name': 'Repetida con otro nombre'})   # no toca el celular: no se revisa
        repetida.write({'phone': '6026-1919'})                  # el mismo celular de antes: no cambió
        with self.assertRaises(ValidationError):
            repetida.write({'phone': '6000-0001', 'email': 'ana.gomez@correo.com'})  # un dato nuevo que choca
        repetida.write({'phone': '6000-0002'})                  # y arreglarla sí

    def test_fusionar_dos_fichas_viejas_funciona(self):
        vieja = self.Partner.with_context(**SIN).create({'name': 'Ana duplicada', 'phone': '60261919',
                                                         'email': 'ana.gomez@correo.com'})
        self.env['base.partner.merge.automatic.wizard']._merge((self.ana + vieja).ids, dst_partner=self.ana)
        self.assertFalse(vieja.exists())
        self.assertTrue(self.ana.exists())

    def test_fusionar_pasa_los_datos_de_la_ficha_que_se_va_a_la_que_queda(self):
        # el asistente copia los datos de la ficha que se borra a la que queda MIENTRAS la primera aún existe
        destino = self.Partner.create({'name': 'Destino sin datos'})
        origen = self.Partner.create({'name': 'Origen con datos', 'phone': '6888-0001', 'email': 'origen@x.com',
                                      'vat': '8-888-001'})
        self.env['base.partner.merge.automatic.wizard']._merge((destino + origen).ids, dst_partner=destino)
        self.assertFalse(origen.exists())
        self.assertEqual((destino.email, destino.dcasa_telefono_llave, destino.dcasa_vat_llave),
                         ('origen@x.com', 'pa:68880001', '8-888-001'))

    # --- quién ve qué mensaje ---------------------------------------------------------------------------------------

    def test_el_publico_no_ve_el_nombre_de_nadie(self):
        publico = self.env.ref('base.public_user')
        with self.assertRaises(ValidationError) as cm:
            self.env(user=publico, su=True)['res.partner'].create(
                {'name': 'Visitante', 'email': 'ana.gomez@correo.com'})
        mensaje = str(cm.exception)
        self.assertNotIn('Ana', mensaje)
        self.assertNotIn('Gómez', mensaje)
        self.assertIn('WhatsApp', mensaje)

    # --- encontrar antes de crear -------------------------------------------------------------------------------

    def test_buscar_ficha_por_celular_correo_o_ruc(self):
        for kwargs in ({'celular': '+507 60261919'}, {'celular': '00507-6026-1919'}, {'correo': 'ANA.GOMEZ@correo.com'},
                       {'ruc': '8 123 456'}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.Partner._dcasa_buscar_ficha(**kwargs), self.ana)
        self.assertFalse(self.Partner._dcasa_buscar_ficha(celular='6999-9999'))
        self.assertFalse(self.Partner._dcasa_buscar_ficha())
        # un número de otro país con los mismos 8 últimos dígitos no encuentra la ficha de Panamá
        self.Partner.create({'name': 'Otra panameña', 'phone': '5555-1234'})
        self.assertFalse(self.Partner._dcasa_buscar_ficha(celular='+1 305 555 1234'))

    def test_el_aviso_antes_de_guardar_dice_de_quien_es(self):
        nueva = self.Partner.new({'name': 'Visitante', 'email': 'ana.gomez@correo.com'})
        aviso = nueva._onchange_dcasa_duplicado()
        self.assertIn('Ana Gómez Contactos', aviso['warning']['message'])
        self.assertIsNone(self.Partner.new({'name': 'Otra', 'email': 'libre@correo.com'})._onchange_dcasa_duplicado())
