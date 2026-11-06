"""Las reglas fijas de Camila, sin base de datos: la revisión de marca, la marca de la campaña, el tope de 15 días y el
permiso que se lee del mensaje de Sofía."""
from datetime import date

from odoo.tests import BaseCase, tagged

from ..models import reglas as R


@tagged('post_install', '-at_install')
class TestRevisionDeMarca(BaseCase):

    def test_un_texto_con_la_voz_de_la_marca_pasa(self):
        for texto in ('Llegaron muebles nuevos que le quedan perfecto a tu sala.',
                      "Lo que hay en D'CASA esta quincena",
                      'Escríbenos y te ayudamos con medidas, colores y la entrega.'):
            with self.subTest(texto):
                self.assertEqual(R.problemas(texto, 300), [])

    def test_sin_cifras_ni_precios(self):
        for texto in ('Desde $499', 'Ahora 20% menos', 'Cama de 2 plazas', 'Precio en B/. de hoy',
                      'Diez por ciento más barato', 'Solo cien dólares'):
            with self.subTest(texto):
                self.assertIn('Sin cifras ni precios: los precios los pone Odoo, del día.', R.problemas(texto))

    def test_sin_remate_ni_gritos_ni_signos_repetidos(self):
        self.assertIn('Sin «remate».', R.problemas('Gran remate de salas'))
        self.assertIn('Sin «remate».', R.problemas('Rematamos todo'))
        self.assertIn('Sin «¡¡» ni signos repetidos.', R.problemas('¡¡Aprovecha!!'))
        self.assertIn('Sin palabras en mayúsculas (se lee como un grito).', R.problemas('CORRE a la tienda'))
        self.assertEqual(R.problemas("Visítanos en D'CASA"), [], "D'CASA no es un grito")

    def test_de_tu_y_sin_promesas_ni_descuentos(self):
        self.assertIn('De tú, no de usted.', R.problemas('Visítenos en la tienda'))
        self.assertIn('De tú, no de usted.', R.problemas('Le esperamos con lo mejor para su hogar'))
        self.assertIn('Sin descuentos, ofertas ni «gratis»: esta campaña no trae ninguno aprobado.',
                      R.problemas('Envío gratis esta semana'))
        self.assertIn('Sin «el mejor» ni promesas que no se pueden comprobar.',
                      R.problemas('El mejor sofá de Panamá'))

    def test_sin_llaves_ni_etiquetas_y_con_su_largo(self):
        self.assertIn('Sin llaves { } ni etiquetas < >.', R.problemas('Hola {{{contact.first_name}}}'))
        self.assertIn('Sin llaves { } ni etiquetas < >.', R.problemas('<b>Hola</b>'))
        self.assertIn('Muy largo: máximo 10 letras.', R.problemas('Un texto bastante largo', 10))
        self.assertEqual(R.problemas('   '), ['Está vacío.'])

    def test_limpiar_quita_llaves_etiquetas_y_espacios(self):
        self.assertEqual(R.limpiar('  Hola\n\t{{{x}}} <b>tú</b>  '), 'Hola (((x))) btú/b')

    def test_lo_de_la_ia_que_no_pasa_queda_con_el_texto_fijo(self):
        self.assertEqual(R.elegir_texto('Lo nuevo para tu sala', 'Fijo', 70), ('Lo nuevo para tu sala', True))
        self.assertEqual(R.elegir_texto('Remate a $99', 'Fijo', 70), ('Fijo', False))
        self.assertEqual(R.elegir_texto(None, 'Fijo', 70), ('Fijo', False))
        self.assertEqual(R.elegir_texto(['no es texto'], 'Fijo', 70), ('Fijo', False))

    def test_los_textos_fijos_pasan_su_propia_revision(self):
        self.assertEqual(R.problemas(R.ASUNTO_FIJO, R.MAX_ASUNTO), [])
        self.assertEqual(R.problemas(R.ENTRADA_FIJA, R.MAX_ENTRADA), [])
        for grupo, texto in R.LINEAS_FIJAS.items():
            with self.subTest(grupo):
                self.assertEqual(R.problemas(texto, R.MAX_LINEA), [])

    def test_leer_json_de_la_ia(self):
        self.assertEqual(R.leer_json('```json\n{"asunto": "Hola"}\n```'), {'asunto': 'Hola'})
        self.assertEqual(R.leer_json('no hay json'), {})
        self.assertEqual(R.leer_json('{roto'), {})
        self.assertEqual(R.leer_json('[1, 2]'), {})


@tagged('post_install', '-at_install')
class TestMarcaYTope(BaseCase):

    def test_la_marca_de_la_campana_va_y_vuelve(self):
        self.assertEqual(R.marca(7), 'DCN-0007')
        texto = R.texto_whatsapp(7)
        self.assertIn('(Ref. DCN-0007)', texto)
        self.assertEqual(R.campana_de_la_marca(texto), 7)
        self.assertEqual(R.campana_de_la_marca('hola, ref dcn 12 por favor'), 12)
        self.assertIsNone(R.campana_de_la_marca('Hola, quiero la cama de 2 plazas'))
        self.assertIsNone(R.campana_de_la_marca(''))

    def test_una_campana_cada_15_dias_en_dias_de_panama(self):
        self.assertTrue(R.puede_salir_hoy(date(2026, 11, 6), None), 'Si nunca salió ninguna, puede salir')
        self.assertEqual(R.proxima_fecha(date(2026, 11, 6)), date(2026, 11, 21))
        self.assertFalse(R.puede_salir_hoy(date(2026, 11, 20), date(2026, 11, 6)))
        self.assertTrue(R.puede_salir_hoy(date(2026, 11, 21), date(2026, 11, 6)))

    def test_solo_cuenta_el_mensaje_de_sofia_que_decia_promociones(self):
        self.assertTrue(R.menciona_promociones('Así te avisamos de promociones, del programa Socios…'))
        self.assertTrue(R.menciona_promociones('Te aviso de PROMOCIÓN y novedades'))
        self.assertFalse(R.menciona_promociones('¿Me regalas tu correo para enviarte la cotización?'))
