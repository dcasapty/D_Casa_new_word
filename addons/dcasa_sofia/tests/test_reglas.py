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

    def test_quita_el_canal_de_lo_que_le_interesa(self):
        canales = ['WhatsApp (QR)', 'WhatsApp (API oficial)', 'Messenger']
        self.assertEqual(R.sin_canal('WhatsApp (QR): colchón queen', canales), 'colchón queen')
        self.assertEqual(R.sin_canal('Messenger:  juego de sala', canales), 'juego de sala')
        self.assertEqual(R.sin_canal('Juego de sala en L', canales), 'Juego de sala en L')
        self.assertEqual(R.sin_canal('', canales), '')

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

    # ------------------------------------------------------------------
    # «Guarda sus datos»: leer lo que el cliente contestó
    # ------------------------------------------------------------------

    def test_el_nombre_con_nuestro_formato(self):
        self.assertEqual(R.nombre_con_formato('maría DE LOS ángeles  pérez'), 'María de los Ángeles Pérez')
        self.assertEqual(R.nombre_con_formato('ANA o\'neill'), "Ana O'Neill")
        self.assertEqual(R.nombre_con_formato('josé-luis del carmen'), 'José-Luis del Carmen')
        self.assertEqual(R.nombre_con_formato('de gracia luis'), 'De Gracia Luis', 'al empezar, con mayúscula')
        self.assertEqual(R.nombre_con_formato('ana e pérez y'), 'Ana E Pérez', 'una inicial no es partícula')
        self.assertEqual(R.nombre_con_formato('Ana\u200b Pérez\u202e'), 'Ana Pérez',
                         'los caracteres invisibles no entran a la ficha')
        self.assertEqual(R.falta_el_nombre('Ana\u200b Pérez'), 'su nombre tiene emojis')

    def test_lee_el_nombre_solo_cuando_lo_dice_claro(self):
        self.assertEqual(R.nombre_en('Hola, me llamo marisol pérez y mi correo es marisol@example.com'),
                         'Marisol Pérez')
        self.assertEqual(R.nombre_en('Mi nombre es Carla'), 'Carla', 'dicho a propósito, sirve un nombre solo')
        self.assertEqual(R.nombre_en('me llamo Ana Pérez y me interesa la cama queen'), 'Ana Pérez')
        self.assertEqual(R.nombre_en('Nombre: luis de gracia'), 'Luis de Gracia')
        # Sin que nadie se lo pidiera, una línea suelta o «soy …» no es su nombre.
        self.assertIsNone(R.nombre_en('Marisol Pérez'))
        self.assertIsNone(R.nombre_en('Soy Marisol Pérez'))
        # Contestando a quien se lo pidió, sí.
        self.assertEqual(R.nombre_en('Marisol Pérez\nmarisol@example.com', despues_de_pedirlo=True), 'Marisol Pérez')
        self.assertEqual(R.nombre_en('Claro, soy Marisol Pérez', despues_de_pedirlo=True), 'Marisol Pérez')
        self.assertIsNone(R.nombre_en('no me llamo nadie'))
        self.assertIsNone(R.nombre_en('me llamo mucho la atención ese sofá'))
        for texto in ('Hola buenas', 'Ok gracias', 'Cama queen gris', 'Juego de sala', 'soy de La Chorrera',
                      'Ana', '🙏', '6000-1234', 'Mañana paso', 'Ahorita voy', 'Muy amable', 'Excelente servicio',
                      'Lo pienso', 'Muy caro', 'Te aviso', 'Mándame fotos', 'Calle Principal', 'Puerto Caimito',
                      'Ella se llama Ana Gómez'):
            with self.subTest(texto=texto):
                self.assertIsNone(R.nombre_en(texto, despues_de_pedirlo=True))

    def test_mejora_el_nombre_solo_si_el_de_la_ficha_no_sirve(self):
        self.assertTrue(R.mejora_el_nombre('🙏', 'Ana Pérez'))
        self.assertTrue(R.mejora_el_nombre('🙏', 'Ana'), 'un nombre solo es mejor que un emoji')
        self.assertTrue(R.mejora_el_nombre('Ana', 'Ana Pérez'))
        self.assertFalse(R.mejora_el_nombre('Ana', 'Carla'), 'nunca un nombre de pila en lugar de otro')
        self.assertFalse(R.mejora_el_nombre('Ana', 'Carla Ruiz'), 'si ya tiene un nombre de pila, que sea el suyo')
        self.assertTrue(R.mejora_el_nombre('ana', 'Ána María Pérez'))
        self.assertFalse(R.mejora_el_nombre('🙏', 'Dios Te Bendiga'))
        self.assertFalse(R.mejora_el_nombre('Ana Pérez', 'Ana María Pérez Ruiz'), 'lo bueno no se pisa')
        self.assertFalse(R.mejora_el_nombre('🙏', None))
        self.assertTrue(R.mejora_el_nombre('WhatsApp +507 6000', 'Ana Pérez', ('WhatsApp +507 6000',)))

    def test_lee_el_cumpleanos_como_lo_guarda_socios(self):
        self.assertEqual(R.cumple_en('Cumplo el 12 de marzo'), '03-12')
        self.assertEqual(R.cumple_en('mi cumpleaños es marzo 12'), '03-12')
        self.assertEqual(R.cumple_en('Nací el 05/11/1990'), '11-05', 'día primero, como en Panamá')
        self.assertEqual(R.cumple_en('29 de febrero, mi cumpleaños'), '02-29')
        self.assertIsNone(R.cumple_en('Cumplo el 31 de abril'), 'esa fecha no existe')
        self.assertIsNone(R.cumple_en('Lo quiero para el 15/12'), 'una entrega no es su cumpleaños')
        self.assertIsNone(R.cumple_en('La fecha de entrega es el 15/12'))
        self.assertIsNone(R.cumple_en('Cuesta $12/03'), 'nunca con un precio')
        self.assertIsNone(R.cumple_en('Es un regalo para el cumpleaños de mi mamá, es el 20 de diciembre'),
                          'el de otra persona')
        self.assertIsNone(R.cumple_en('Cumplo con el abono el 15/11'))
        self.assertIsNone(R.cumple_en('Nacimiento de mi bebé, marzo 15'))
        # Contestando a quien le pidió el día y el mes: solo una línea que es la fecha.
        for texto in ('¿Me lo pueden entregar el 15 de noviembre?', 'Paso el sábado 8/11', 'Cama 3/4 gris', 'set 2'):
            with self.subTest(texto=texto):
                self.assertIsNone(R.cumple_en(texto, despues_de_pedirlo=True))
        self.assertEqual(R.cumple_en('Ana Pérez\nel 12 de marzo', despues_de_pedirlo=True), '03-12')
        # Caso real (2026-11-05): el año pegado al «del» mal escrito.
        self.assertEqual(R.cumple_en('7 de marzo deln1990', despues_de_pedirlo=True), '03-07')
        self.assertEqual(R.cumple_en('7 de marzo del 1990', despues_de_pedirlo=True), '03-07')
        self.assertIsNone(R.cumple_en('El 7 de marzo paso a las 1990', despues_de_pedirlo=True))
        self.assertEqual(R.cumple_en('15/12', despues_de_pedirlo=True), '12-15')
        self.assertEqual(R.cumple_para_mostrar('03-12'), '12/03')
        self.assertEqual(R.cumple_para_mostrar(''), '')

    def test_sabe_si_le_pidieron_sus_datos_y_su_cumpleanos(self):
        self.assertTrue(R.pide_datos('¿Me regalas tu nombre y apellido y tu correo?'))
        self.assertFalse(R.pide_datos('¡Hola! ¿Te puedo ayudar con el sofá?'))
        self.assertFalse(R.pide_datos('Te envié la cotización a tu correo.'), 'nombra el dato pero no lo pide')
        self.assertFalse(R.pide_datos('Te envié la cotización a tu correo, ¿la recibiste?'))
        self.assertFalse(R.pide_datos('La factura sale a su nombre, ¿verdad?'))
        self.assertTrue(R.pide_datos('¿Cuál es tu correo?'))
        self.assertTrue(R.pide_datos('Tu nombre completo, por favor'))
        self.assertTrue(R.pide_datos('Compárteme tu nombre completo para la factura'))
        self.assertTrue(R.pide_el_cumple('si quieres, dime también el día y el mes'))
        self.assertTrue(R.pide_el_cumple('¿Cuándo es tu cumpleaños?'))
        self.assertFalse(R.pide_el_cumple('Así te avisamos de los beneficios de cumpleaños.'))

    def test_junta_los_datos_de_varios_mensajes(self):
        mensajes = [   # del más nuevo al más viejo
            ('Mi correo es Marisol.P@Example.com', True, True),
            ('Marisol Pérez\n12/03', True, True),
            ('Me llamo Marisol Vieja', False, False),
        ]
        self.assertEqual(R.datos_en(mensajes),
                         {'correo': 'marisol.p@example.com', 'nombre': 'Marisol Pérez', 'cumple': '03-12'})
        self.assertEqual(R.datos_en([('Marisol Pérez\n12/03', True, False)]), {'nombre': 'Marisol Pérez'},
                         'si no le pidieron el cumpleaños, una fecha suelta no lo es')
        self.assertEqual(R.datos_en([('Hola buenas, ¿tienen la cama?', True, True)]), {})
        self.assertEqual(R.datos_en([('mi correo es ana@gmial', False, False)]), {}, 'mal escrito no se propone')
        self.assertEqual(R.datos_en([('Escríbele a ventas@dcasa.example.com', False, False),
                                     ('mi correo es ana@example.com', False, False)],
                                    correos_que_no={'ventas@dcasa.example.com'}),
                         {'correo': 'ana@example.com'}, 'el del equipo no tapa el suyo')
        self.assertEqual(R.correos_en('ana@empresa.com.Saludos'), ['ana@empresa.com'])
        self.assertEqual(R.correos_en('ana@empresa.com.pa'), ['ana@empresa.com.pa'])

    def test_prioridad_de_guardar_sus_datos(self):
        self.assertEqual(R.prioridad('guardar_datos', CRM.CALIENTE), R.MEDIA)
        self.assertEqual(R.prioridad('guardar_datos', CRM.FRIO), R.BAJA)
