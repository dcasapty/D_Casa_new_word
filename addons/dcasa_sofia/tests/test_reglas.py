"""Las reglas fijas de Sofía (funciones puras)."""
from datetime import datetime, timedelta

from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_sofia.models import reglas as R
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install')
class TestReglasDeSofia(BaseCase):

    def test_reconoce_los_nombres_que_no_son_de_una_persona(self):
        casos = {
            '🙏': 'su nombre es un emoji o un símbolo',
            '❤️❤️': 'su nombre es un emoji o un símbolo',
            'Dios te bendiga 🙏': 'su nombre tiene emojis',
            'Dios es amor': 'su nombre parece una frase o una empresa',
            'Muebles y Más S.A.': 'su nombre parece una frase o una empresa',
            'La vida es bella y hay que disfrutarla': 'su nombre parece una frase',
            'Ana': 'solo tiene un nombre: falta el apellido',
            'Ana2024': 'su nombre tiene números',
            '': 'no tiene nombre',
            '   ': 'no tiene nombre',
        }
        for nombre, motivo in casos.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(R.falta_el_nombre(nombre), motivo)
        self.assertEqual(R.falta_el_nombre('WhatsApp (QR) +507 6000-0000', ('WhatsApp (QR) +507 6000-0000',)),
                         'no tiene nombre')

    def test_un_nombre_y_apellido_de_verdad_sirve(self):
        for nombre in ('Ana Pérez', 'Jesús Rodríguez', 'Luz Marina Castillo', 'María de los Ángeles Pérez',
                       'José Ángel De Gracia', "Ana O'Neill"):
            with self.subTest(nombre=nombre):
                self.assertIsNone(R.falta_el_nombre(nombre))

    def test_solo_saluda_por_su_nombre_si_es_un_nombre(self):
        self.assertEqual(R.primer_nombre('ana pérez'), 'Ana')
        self.assertEqual(R.primer_nombre('Luz'), 'Luz', 'un nombre solo sirve para saludar')
        self.assertEqual(R.primer_nombre('🙏'), '')
        self.assertEqual(R.primer_nombre('Dios te bendiga 🙏'), '')
        self.assertEqual(R.primer_nombre('Muebles y Más S.A.'), '')

    def test_el_correo(self):
        self.assertTrue(R.falta_el_correo(False))
        self.assertTrue(R.falta_el_correo('ana@gmial'))
        self.assertFalse(R.falta_el_correo('ana.perez@example.com'))
        self.assertEqual(R.correos_en('Mi correo es Ana.Perez@Example.com. Gracias, ana.perez@example.com'),
                         ['ana.perez@example.com'])
        self.assertEqual(R.correos_en('sin correo'), [])

    def test_que_falta(self):
        self.assertEqual(R.que_falta(True, True), 'tu nombre y apellido y tu correo')
        self.assertEqual(R.que_falta(True, False), 'tu nombre y apellido')
        self.assertEqual(R.que_falta(False, True), 'tu correo')
        self.assertEqual(R.que_falta(False, False), '')

    def test_rellenar_no_deja_huecos_ni_claves(self):
        texto = R.rellenar('¡Hola {nombre}! Soy {vendedora} de D\'CASA.', {'nombre': '', 'vendedora': 'Ana'})
        self.assertEqual(texto, "¡Hola! Soy Ana de D'CASA.")
        self.assertEqual(R.rellenar('¿Me regalas {que_falta} ?', {'que_falta': 'tu correo'}), '¿Me regalas tu correo?')
        self.assertNotIn('{', R.rellenar('{nombre} {interes}', {}))
        self.assertEqual(R.claves_desconocidas('Hola {nombre}, te damos {descuento} y {precio}'),
                         ['descuento', 'precio'])
        self.assertEqual(R.claves_desconocidas('Hola {nombre}'), [])

    def test_la_ventana_de_24_horas_solo_en_los_canales_de_meta(self):
        ahora = datetime(2026, 11, 5, 15, 0)
        self.assertTrue(R.ventana_abierta('whatsapp_qr', None, ahora))
        self.assertTrue(R.ventana_abierta('telegram', ahora - timedelta(days=9), ahora))
        for canal in ('whatsapp_cloud', 'messenger', 'instagram'):
            with self.subTest(canal=canal):
                self.assertTrue(R.ventana_abierta(canal, ahora - timedelta(hours=22), ahora))
                self.assertFalse(R.ventana_abierta(canal, ahora - timedelta(hours=23, minutes=30), ahora))
                self.assertFalse(R.ventana_abierta(canal, None, ahora))

    def test_prioridad(self):
        self.assertEqual(R.prioridad('contestar'), R.ALTA)
        self.assertEqual(R.prioridad('vence', vence_hoy=True), R.ALTA)
        self.assertEqual(R.prioridad('vence'), R.MEDIA)
        self.assertEqual(R.prioridad('escribir', CRM.CALIENTE), R.ALTA)
        self.assertEqual(R.prioridad('escribir', CRM.TIBIO), R.MEDIA)
        self.assertEqual(R.prioridad('pedir_datos', CRM.CALIENTE), R.MEDIA)
        self.assertEqual(R.prioridad('pedir_datos', CRM.TIBIO), R.BAJA)
        self.assertEqual(R.prioridad('sincronizar', CRM.CALIENTE), R.BAJA)
