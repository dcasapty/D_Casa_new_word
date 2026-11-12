"""Juan y los envíos: ``cotizar_envio`` (los seis estados, la promoción con la compra real de la cotización) y
``agregar_envio`` (sumar o reemplazar el envío en la cotización de ESTA conversación y volver a armar el PDF).

Los lugares y la tarifa son los del fixture sintético de dcasa_envios (precios de juguete: Costa Inventada, en la
provincia de Panamá, $45; Villa Prueba, en Panamá Oeste, $15; Barrio Simulado, en Colón, $105). La promoción es la de
noviembre que viene cargada, y las pruebas fijan la fecha de Panamá en el 12 de noviembre de 2026."""
import json
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.tests import new_test_user, tagged

from ..models import crm_reglas as R
from .test_api import ApiCase
from .test_cotizacion_automatica import CotizarCase

HOY = 'odoo.addons.dcasa_envios.models.promocion.EnvioPromocion._hoy'
FECHA_COTIZACION = 'odoo.addons.dcasa_envios.models.venta.SaleOrder._dcasa_promocion_fecha'
COSTA = ('Costa Inventada', 'Santa Prueba', 'Panamá')         # cómo se nombra el lugar (respaldo de la guardia)


class EnviosJuanCase(CotizarCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(cls.env, login='ger_envios_juan', name='Gerencia Envíos Juan',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, cls.gerencia)
        cls.tarifa = cls.env['dcasa.envio.tarifa'].search([], limit=1)
        cls.tarifa.with_user(cls.gerencia).action_aprobar()
        Lugar = cls.env['dcasa.envio.lugar']
        cls.costa = Lugar.search([('name', '=', 'Costa Inventada')])
        cls.colon = Lugar.search([('name', '=', 'Barrio Simulado')])

    def setUp(self):
        super().setUp()
        self.startPatcher(patch(HOY, return_value=date(2026, 11, 12)))
        # Las cotizaciones se tienen por creadas «hoy» (la fecha de creación es la que decide la promoción).
        self.startPatcher(patch(FECHA_COTIZACION, autospec=True,
                                side_effect=lambda orden: orden.env['dcasa.envio.promocion']._hoy()))

    @staticmethod
    def papeles(datos):
        """El respaldo de la guardia del Worker (un lugar): ``(nombres, normal, final, ahorro, gratis, condicional,
        minimo, compra)`` y el total de la cotización."""
        (lugar,) = datos['respaldo_envio']['lugares']
        return (tuple(lugar['nombres']),) + tuple(lugar[k] for k in (
            'normal', 'final', 'ahorro', 'gratis', 'condicional', 'minimo', 'compra')), datos['respaldo_envio']['total']

    def envio(self, conv=None, **argumentos):
        return self.salida('cotizar_envio', argumentos, conv=conv)

    def agregar(self, lugar, conv=None, **argumentos):
        """agregar_envio a secas (solo suma un lugar cuyo precio ya dio cotizar_envio en esta conversación)."""
        return self.salida('agregar_envio', dict(argumentos, lugar_id=lugar.id), conv=conv)

    def sumar(self, lugar, conv=None, **argumentos):
        """Como Juan: primero le da el precio al cliente (cotizar_envio) y, si dice que sí, lo suma (agregar_envio)."""
        self.envio(conv=conv, lugar_id=lugar.id)
        return self.agregar(lugar, conv=conv, **argumentos)


@tagged('post_install', '-at_install')
class TestCotizarEnvio(EnviosJuanCase):

    def test_las_dos_herramientas_estan_publicadas_para_juan(self):
        catalogo = {t['name']: t for t in self.env['brian.herramientas'].with_user(self.juan).catalogo()}
        self.assertIn('lugar', catalogo['juan_cotizar_envio']['input_schema']['properties'])
        self.assertEqual(catalogo['juan_agregar_envio']['input_schema']['required'], ['lugar_id'])
        self.assertTrue(self.ajustes.cotizar_envios, 'encendido de fábrica: la dueña dijo que sí')

    def test_precio_claro_sin_cotizacion_dice_las_condiciones_de_la_promocion(self):
        datos = self.envio(lugar='Costa Inventada')
        self.assertEqual(datos['estado'], 'precio')
        self.assertEqual(datos['lugar']['lugar_id'], self.costa.id)
        self.assertEqual((datos['envio_normal'], datos['envio_normal_texto']), (45.0, '$45'))
        self.assertIsNone(datos['cotizacion'])
        self.assertEqual(datos['frase_para_el_cliente'],
                         "El envío a Costa Inventada (Santa Prueba, Panamá) cuesta normalmente $45. Con la promoción "
                         "de noviembre, en compras de más de $200 sin ITBMS, D'CASA te regala el envío: te sale gratis "
                         "(te ahorras $45). La promoción es hasta el 30 de noviembre; después, el envío vuelve a su "
                         "precio normal. No aplica si la compra lleva colchón.")
        self.assertFalse(datos['promocion']['aplica'])
        self.assertTrue(datos['promocion']['condicional'])
        # Cada cifra con su papel (revisión adversarial I1, I2, I5): sin compra, el beneficio va con la condición.
        self.assertEqual(self.papeles(datos), ((COSTA, 45.0, 0.0, 45.0, True, True, 200.0, None), None))
        self.assertEqual(datos['respaldo_envio']['lugares'][0]['lleva_itbms'], False)
        self.assertIn('cotizar', datos['instruccion'])
        self.assertIn('vendedora', datos['instruccion'], 'la fecha de entrega la confirma una vendedora')
        self.assertNotIn('precio', json.dumps(list(datos)), 'ninguna clave dice «precio» (el Worker pondría + ITBMS)')

    def test_en_colon_el_abono_y_sin_promocion_el_precio_normal(self):
        colon = self.envio(lugar='Barrio Simulado')
        self.assertEqual(colon['frase_para_el_cliente'],
                         "El envío a Barrio Simulado (Colón) cuesta normalmente $105. Con la promoción de noviembre, "
                         "en compras de más de $200 sin ITBMS, D'CASA te abona $20 del envío: te queda en $85. La "
                         "promoción es hasta el 30 de noviembre; después, el envío vuelve a su precio normal. No "
                         "aplica si la compra lleva colchón.")
        self.assertNotIn('gratis', colon['frase_para_el_cliente'].lower())
        self.assertEqual(self.papeles(colon), ((('Barrio Simulado', 'Colón'), 105.0, 85.0, 20.0, False, True, 200.0,
                                                 None), None), 'lo abonado es un ahorro, no un costo')
        with patch(HOY, return_value=date(2026, 12, 1)):
            diciembre = self.envio(lugar='Costa Inventada')
        self.assertEqual(diciembre['frase_para_el_cliente'], 'Envío a Costa Inventada (Santa Prueba, Panamá): $45.')
        self.assertIsNone(diciembre['promocion'])
        self.assertEqual(self.papeles(diciembre), ((COSTA, 45.0, None, None, False, False, None, None), None))

    def test_varios_parecidos_pregunta_cual_y_con_el_que_elige_da_el_precio(self):
        datos = self.envio(lugar='ensayo')
        self.assertEqual(datos['estado'], 'varios')
        self.assertGreater(len(datos['opciones']), 1)
        self.assertTrue(all(set(o) == {'lugar_id', 'nombre', 'zona'} for o in datos['opciones']), 'sin precios')
        self.assertNotIn('$', json.dumps(datos))
        self.assertIn('¿Cuál es el tuyo?', datos['frase_para_el_cliente'])
        # El lugar como en «Copiar el precio»: nombre (corregimiento, distrito).
        self.assertIn('PH Torre Ensayo (Santa Prueba, Panamá)', datos['frase_para_el_cliente'])
        self.assertNotIn('Zona:', datos['frase_para_el_cliente'])
        elegido = self.envio(lugar_id=datos['opciones'][1]['lugar_id'])
        self.assertEqual((elegido['estado'], elegido['lugar']['lugar_id']),
                         ('precio', datos['opciones'][1]['lugar_id']))
        self.assertEqual(self.envio(lugar='villa prueba')['lugar']['nombre'], 'Villa Prueba',
                         'se llama exactamente así: no hace falta preguntar (Villa Prueba II es otro)')

    def test_dos_lugares_iguales_para_el_cliente(self):
        # El fixture trae dos «El Duplicado» en la misma zona (como el archivo real): si cuestan lo mismo, es uno.
        datos = self.envio(lugar='el duplicado')
        self.assertEqual((datos['estado'], datos['envio_normal_texto']), ('precio', '$25'))
        # Si no cuestan lo mismo, el cliente no puede decir cuál: se pide un punto de referencia, sin precios.
        uno = self.env['dcasa.envio.lugar'].search([('name', '=', 'El Duplicado')], limit=1)
        uno.with_user(self.gerencia).write({'km': 30})
        datos = self.envio(lugar='el duplicado')
        self.assertEqual((datos['estado'], datos['motivo']), ('no_encontrado', 'mismo_nombre'))
        self.assertIn('punto de referencia', datos['frase_para_el_cliente'])
        self.assertNotIn('$', json.dumps(datos))

    def test_h7_dos_iguales_con_otro_precio_nunca_dan_un_precio_aunque_vengan_de_varios(self):
        """Revisión adversarial (I4): «El Duplicado» ×2 en la misma zona con precios distintos y, además, otro lugar
        parecido (estado «varios»): al elegir la opción de los gemelos se pide un punto de referencia."""
        Lugar = self.env['dcasa.envio.lugar']
        duplicados = Lugar.search([('name', '=', 'El Duplicado')], order='km')
        duplicados[1].with_user(self.gerencia).write({'km': 60})
        Lugar.with_user(self.gerencia).create({
            'name': 'Duplicado Norte', 'tipo': 'barrio', 'corr': 'Vista Inventada', 'dist': 'Arraiján',
            'prov': 'Panamá Oeste', 'km': 20.0, 'estado': 'ok'})
        datos = self.envio(lugar='duplicados')
        self.assertEqual(datos['estado'], 'varios', datos)
        gemelo = [o for o in datos['opciones'] if o['nombre'] == 'El Duplicado']
        self.assertEqual(len(gemelo), 1, 'el cliente los ve iguales: una sola opción')
        for lugar_id in (gemelo[0]['lugar_id'], (duplicados - Lugar.browse(gemelo[0]['lugar_id'])).id):
            elegido = self.envio(lugar_id=lugar_id)
            self.assertEqual((elegido['estado'], elegido['motivo']), ('no_encontrado', 'mismo_nombre'))
            self.assertNotIn('$', json.dumps(elegido))
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual(self.agregar(duplicados[0])['motivo'], 'mismo_nombre')

    def test_h19_el_lugar_claro_se_decide_con_todas_las_coincidencias(self):
        """Revisión adversarial (M3): cinco «Calle Repetida» iguales cerca (las que se muestran) y una sexta en Colón:
        no es un lugar claro, se pregunta cuál."""
        from odoo.addons.dcasa_envios.tests.common import fixture
        datos_archivo = fixture()
        base = {'nombre': 'Calle Repetida', 'tipo': 'barrio', 'cat': 'barrio o urbanización', 'corr_exacto': True,
                'estado': 'ok'}
        for km in (12.1, 12.2, 12.3, 12.4, 12.5):
            datos_archivo['lugares'].append(dict(base, corr='Los Ensayos', dist='La Chorrera', prov='Panamá Oeste',
                                                 km=km))
        datos_archivo['lugares'].append(dict(base, corr='Barrio Simulado', dist='Colón', prov='Colón', km=91.0))
        importar(self.env, self.gerencia, datos=datos_archivo, tarifa=False)
        self.assertEqual(self.env['dcasa.envio.lugar'].search_count([('name', '=', 'Calle Repetida')]), 6)
        datos = self.envio(lugar='Calle Repetida')
        self.assertEqual(datos['estado'], 'varios', datos)
        self.assertIn('Calle Repetida (Barrio Simulado, Colón)', datos['frase_para_el_cliente'])
        self.assertNotIn('$', json.dumps(datos))

    def test_no_encontrado_pide_un_punto_de_referencia(self):
        datos = self.envio(lugar='pruebaxx zzz')
        self.assertEqual(datos['estado'], 'no_encontrado')
        self.assertIn('Villa Prueba', datos['parecidos'])
        self.assertIn('punto de referencia', datos['frase_para_el_cliente'])
        self.assertIn('pasar_a_vendedora', datos['instruccion'])
        self.assertIn('pregúntale al cliente a dónde va', self.error('cotizar_envio', {'lugar': '¿cuánto cuesta?'})
                      .lower())

    def test_lo_que_se_cotiza_aparte_pasa_a_una_vendedora(self):
        for nombre, por_que in (('Pueblo Lejano', 'más de 300 km'), ('Monte Sin Camino', 'sin carretera')):
            with self.subTest(nombre=nombre):
                datos = self.envio(lugar=nombre)
                self.assertEqual((datos['estado'], datos['por_que']), ('aparte', por_que))
                self.assertIn('pasar_a_vendedora', datos['instruccion'])
                self.assertNotIn('$', json.dumps(datos))

    def test_tarifa_sin_aprobar_no_da_precios(self):
        self.tarifa.with_user(self.gerencia).action_quitar_aprobacion()
        for argumentos in ({'lugar': 'Costa Inventada'}, {'lugar_id': self.costa.id}):
            datos = self.envio(**argumentos)
            self.assertEqual(datos['estado'], 'en_revision')
            self.assertIn('pasar_a_vendedora', datos['instruccion'])
            self.assertNotIn('$', json.dumps(datos))
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual(self.sumar(self.costa)['motivo'], 'en_revision')
        self.assertFalse(self.ordenes().order_line.filtered('is_delivery'))

    def test_con_el_interruptor_apagado_pasa_a_una_vendedora(self):
        self.ajustes.cotizar_envios = False
        datos = self.envio(lugar='Costa Inventada')
        self.assertEqual(datos['estado'], 'apagado')
        self.assertNotIn('$', json.dumps(datos))
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual(self.sumar(self.costa)['motivo'], 'apagado')

    def test_h20_un_lugar_que_agrego_una_vendedora_no_tiene_precio_para_el_cliente(self):
        """Revisión adversarial (I7): hasta que Gerencia lo revise, el costo se lo confirma una vendedora."""
        vendedora = new_test_user(self.env, login='vend_h20', name='Vendedora H20',
                                  groups='base.group_user,dcasa_base.group_vendedora')
        nuevo = self.env['dcasa.envio.lugar'].with_user(vendedora).create({
            'name': 'Residencial Inventado H20', 'tipo': 'barrio', 'dist': 'Colón', 'corr': 'Barrio Simulado',
            'km': 1.0})
        self.assertTrue(self.env['dcasa.envio.tarifa']._estado_publico()['aprobada'], 'la tarifa sigue aprobada')
        for argumentos in ({'lugar': 'Residencial Inventado H20'}, {'lugar_id': nuevo.id}):
            with self.subTest(argumentos=argumentos):
                datos = self.envio(**argumentos)
                self.assertEqual(datos['estado'], 'aparte')
                self.assertEqual(datos['frase_para_el_cliente'],
                                 'El costo del envío a Residencial Inventado H20 te lo confirma una vendedora.')
                self.assertIn('pasar_a_vendedora', datos['instruccion'])
                self.assertNotIn('$', json.dumps(datos))
        self.cotizar({'codigo': 'ZZ-SOFA'})
        no = self.sumar(nuevo)
        self.assertEqual((no['sumado'], no['motivo']), (False, 'sin_revisar'))
        self.assertFalse(self.ordenes().order_line.filtered('is_delivery'))
        nuevo.with_user(self.gerencia).action_marcar_revisado()
        self.assertEqual(self.envio(lugar='Residencial Inventado H20')['estado'], 'precio')

    def test_la_direccion_exacta_no_se_usa_para_buscar(self):
        self.assertEqual(R.quitar_direccion_exacta('Costa Inventada, calle 3, casa 45'), 'Costa Inventada, calle 3')
        self.assertEqual(R.quitar_direccion_exacta('PH Torre Ensayo, apto 4B, piso 12'), 'PH Torre Ensayo')
        self.assertEqual(self.envio(lugar='Costa Inventada, casa 45')['lugar']['nombre'], 'Costa Inventada')

    def test_la_promocion_se_aplica_con_la_compra_real_de_la_cotizacion(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})                      # $800 sin ITBMS
        (orden,) = self.ordenes()
        datos = self.envio(lugar='Costa Inventada')
        self.assertEqual(datos['cotizacion'], {'numero': orden.name, 'envio_ya_sumado': False})
        self.assertTrue(datos['promocion']['aplica'])
        self.assertEqual((datos['promocion']['envio_con_promocion'], datos['promocion']['ahorro']), (0.0, 45.0))
        self.assertEqual(datos['frase_para_el_cliente'],
                         "El envío a Costa Inventada (Santa Prueba, Panamá) cuesta normalmente $45. Con la promoción "
                         "de noviembre, como tu compra pasa de $200 sin ITBMS, D'CASA te regala el envío: te sale "
                         "gratis (te ahorras $45). La promoción es hasta el 30 de noviembre; después, el envío vuelve "
                         "a su precio normal.")
        self.assertIn('¿Quieres que te lo sume a la cotización?', datos['instruccion'])
        self.assertIn(f'agregar_envio con lugar_id={self.costa.id}', datos['instruccion'])

    def test_compra_chica_o_con_colchon_no_tiene_promocion(self):
        self.cotizar({'codigo': 'ZZ-MESA'})                      # $90
        chica = self.envio(lugar='Costa Inventada')
        self.assertEqual(chica['promocion']['motivo'], 'monto')
        self.assertEqual(chica['frase_para_el_cliente'],
                         'Envío a Costa Inventada (Santa Prueba, Panamá): $45. La promoción de noviembre es para '
                         'compras de más de $200 sin ITBMS; tu cotización suma $90 sin ITBMS, así que el envío va a '
                         'su precio normal.')
        self.assertEqual(self.papeles(chica), ((COSTA, 45.0, None, None, False, False, 200.0, 90.0), None))
        otra = self.conversacion(nombre='Otra', id_externo='50769990001')
        self.colchon.dcasa_tipo_combo = 'colchon'            # (el nombre de prueba «ZZCOLCHÓN» no lo sugiere solo)
        self.cotizar({'codigo': self.colchon.dcasa_codigo_publico, 'opcion': 'Zzqueen'}, conv=otra)
        con_colchon = self.envio(conv=otra, lugar='Costa Inventada')
        self.assertEqual(con_colchon['promocion']['motivo'], 'colchon')
        self.assertIn('no aplica cuando la compra lleva colchón', con_colchon['frase_para_el_cliente'])


@tagged('post_install', '-at_install')
class TestAgregarEnvio(EnviosJuanCase):

    def test_suma_el_envio_y_la_promocion_y_rearma_el_pdf(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (orden,) = self.ordenes()
        self.assertEqual(len(self.avisos_con_pdf()), 1)
        datos = self.sumar(self.costa)
        self.assertTrue(datos['sumado'])
        envio = orden.order_line.filtered('is_delivery')
        self.assertEqual(sorted(envio.mapped('price_unit')), [-45.0, 45.0])
        self.assertEqual(orden.carrier_id, self.env['sale.order']._dcasa_envio_transportista())
        self.assertAlmostEqual(orden.amount_untaxed, 800.0)
        cotizacion = datos['cotizacion']
        self.assertEqual([linea['codigo'] for linea in cotizacion['lineas']], [self.sofa.dcasa_codigo_publico],
                         'el envío no va entre los productos')
        self.assertEqual([linea['monto_texto'] for linea in cotizacion['envio']['lineas']], ['$45', '−$45'])
        self.assertEqual(cotizacion['envio']['total_envio_texto'], '$0')
        self.assertEqual(self.papeles(datos), ((COSTA, 45.0, 0.0, 45.0, True, False, 200.0, None),
                                               cotizacion['total']), 'y el total de la cotización (M1)')
        frase = datos['frase_para_el_cliente']
        self.assertTrue(frase.startswith(f'Listo, te sumé el envío a la cotización {orden.name}. El envío a Costa '
                                         'Inventada (Santa Prueba, Panamá) cuesta normalmente $45.'), frase)
        self.assertIn(f'El total de la cotización queda en {cotizacion["total_texto"]}.', frase)
        avisos = self.avisos_con_pdf()
        self.assertEqual(len(avisos), 2, 'el PDF se vuelve a armar con el envío')
        self.assertIn('sumó el envío a Costa Inventada', avisos.sorted('id')[-1].texto)
        self.assertIn(f'/dcasa/adjunto/{avisos.sorted("id")[-1].adjunto_ids.id}/', datos['documento']['url'])
        self.assertEqual(self.envio(lugar='Costa Inventada')['cotizacion']['envio_ya_sumado'], True)

    def test_otro_lugar_reemplaza_el_envio(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (orden,) = self.ordenes()
        self.sumar(self.costa)
        datos = self.sumar(self.colon)
        self.assertEqual(sorted(orden.order_line.filtered('is_delivery').mapped('price_unit')), [-20.0, 105.0])
        self.assertIn("cuesta normalmente $105. Con la promoción de noviembre, como tu compra pasa de $200 sin ITBMS, "
                      "D'CASA te abona $20 del envío: te queda en $85. La promoción es hasta el 30 de noviembre;",
                      datos['frase_para_el_cliente'])
        self.assertAlmostEqual(orden.amount_untaxed, 885.0)

    def test_volver_a_cotizar_lo_mismo_reutiliza_la_cotizacion_con_su_envio(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.sumar(self.costa)
        otra_vez = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertTrue(otra_vez['reutilizada'])
        self.assertEqual(len(self.ordenes()), 1)
        self.assertEqual(len(otra_vez['cotizacion']['lineas']), 1)
        self.assertTrue(otra_vez['cotizacion']['envio'])

    def test_sin_cotizacion_o_confirmada_o_de_otra_conversacion_no_se_toca(self):
        self.assertEqual(self.sumar(self.costa)['motivo'], 'sin_cotizacion')
        # Una cotización del mismo cliente que no salió de esta conversación (sin su origen ni su oportunidad).
        ajena = self.env['sale.order'].create({'partner_id': self.conv.partner_id.id, 'order_line': [
            Command.create({'product_id': self.sofa.product_variant_id.id})]})
        self.assertEqual(self.sumar(self.costa)['motivo'], 'sin_cotizacion')
        self.assertFalse(ajena.order_line.filtered('is_delivery'))
        # La de otra conversación (otro cliente) tampoco.
        otra = self.conversacion(nombre='Otra', id_externo='50769990002')
        self.cotizar({'codigo': 'ZZ-SOFA'}, conv=otra)
        self.assertEqual(self.sumar(self.costa)['motivo'], 'sin_cotizacion')
        self.assertFalse(self.ordenes(otra).order_line.filtered('is_delivery'))
        # Confirmada: nunca.
        self.cotizar({'codigo': 'ZZ-MESA'})
        (orden,) = self.ordenes().filtered(lambda o: o != ajena)
        orden.action_confirm()
        resultado = self.sumar(self.costa)
        self.assertEqual(resultado['motivo'], 'confirmada')
        self.assertIn('pasar_a_vendedora', resultado['instruccion'])
        self.assertFalse(orden.order_line.filtered('is_delivery'))

    def test_el_envio_que_puso_una_vendedora_no_se_cambia(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (orden,) = self.ordenes()
        orden.set_delivery_line(self.env['sale.order']._dcasa_envio_transportista(), 30.0)
        resultado = self.sumar(self.costa)
        self.assertEqual(resultado['motivo'], 'ya_tiene_envio')
        self.assertEqual(orden.order_line.filtered('is_delivery').price_unit, 30.0)

    def test_sin_pdf_avisa_a_las_vendedoras_y_el_envio_queda(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.pdf.return_value = (b'no es un pdf', 'html')
        datos = self.sumar(self.costa)
        self.assertTrue(datos['sumado'])
        self.assertFalse(datos['pdf_adjunto'])
        self.assertNotIn('documento', datos)
        self.assertTrue(self.conv.mensaje_ids.filtered(lambda m: 'no pudo generar el PDF' in (m.texto or '')))

    def test_h8_solo_suma_un_lugar_cuyo_precio_dio_cotizar_envio_en_esta_conversacion(self):
        """Revisión adversarial (M5): un lugar_id cualquiera de la tabla (más barato) no se suma."""
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (orden,) = self.ordenes()
        barato = self.env['dcasa.envio.lugar'].search([('name', '=', 'Villa Prueba')])
        no = self.agregar(barato)
        self.assertEqual((no['sumado'], no['motivo']), (False, 'sin_cotizar_envio'))
        self.assertIn('cotizar_envio', no['instruccion'])
        # El precio que se dio en OTRA conversación no cuenta.
        otra = self.conversacion(nombre='Otra', id_externo='50769990003')
        self.envio(conv=otra, lugar_id=barato.id)
        self.assertEqual(self.agregar(barato)['motivo'], 'sin_cotizar_envio')
        # Uno que se cotizó pero no tuvo precio (se cotiza aparte) tampoco.
        lejano = self.env['dcasa.envio.lugar'].search([('name', '=', 'Pueblo Lejano')])
        self.assertEqual(self.sumar(lejano)['motivo'], 'aparte')
        self.assertFalse(orden.order_line.filtered('is_delivery'))
        self.assertTrue(self.sumar(barato)['sumado'], 'después de darle el precio, sí')
        self.assertEqual(orden.order_line.filtered('dcasa_envio_lugar_id').dcasa_envio_lugar_id, barato)

    def test_h18_con_dos_cotizaciones_abiertas_pregunta_a_cual(self):
        """Revisión adversarial (I6): sofá $800 y, aparte, una mesa $90. Ni la promoción se mide con la más reciente ni
        el envío se suma a una sin que el cliente diga cuál."""
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.cotizar({'codigo': 'ZZ-MESA'})
        sofa, mesa = self.ordenes()
        datos = self.envio(lugar='Costa Inventada')
        self.assertIsNone(datos['cotizacion'])
        self.assertEqual([c['numero'] for c in datos['cotizaciones']], [mesa.name, sofa.name])
        self.assertTrue(all(c['total_texto'].startswith('$') for c in datos['cotizaciones']))
        self.assertTrue(datos['promocion']['condicional'], 'con sus condiciones, sin medirla con ninguna')
        self.assertIn('en compras de más de $200 sin ITBMS', datos['frase_para_el_cliente'])
        self.assertNotIn('tu compra', datos['frase_para_el_cliente'])
        self.assertIn('cotizacion=', datos['instruccion'])
        no = self.sumar(self.costa)
        self.assertEqual((no['sumado'], no['motivo']), (False, 'cual_cotizacion'))
        self.assertEqual({c['numero'] for c in no['cotizaciones']}, {sofa.name, mesa.name})
        self.assertEqual(self.sumar(self.costa, cotizacion='S99999')['motivo'], 'cotizacion_no_encontrada')
        self.assertFalse((sofa | mesa).order_line.filtered('is_delivery'))
        si = self.sumar(self.costa, cotizacion=sofa.name.lower())
        self.assertTrue(si['sumado'])
        self.assertEqual(si['cotizacion']['numero'], sofa.name)
        self.assertEqual(sorted(sofa.order_line.filtered('is_delivery').mapped('price_unit')), [-45.0, 45.0])
        self.assertFalse(mesa.order_line.filtered('is_delivery'))

    def test_un_lugar_que_no_existe_es_un_error_para_corregir(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertIn('ya no está en la tabla de envíos', self.error('agregar_envio', {'lugar_id': 99999999}))
        self.assertIn('número del lugar', self.error('agregar_envio', {'lugar_id': 'Costa'}))


@tagged('post_install', '-at_install')
class TestEnvioPorLaApi(ApiCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gerencia = new_test_user(cls.env, login='ger_envios_api', name='Gerencia Envíos API',
                                 groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(gerencia).action_aprobar()

    def conversacion(self):
        return self.env['dcasa.conversacion'].search(
            [('canal', '=', 'whatsapp_qr'), ('id_externo', '=', '50761230000')])

    def test_la_direccion_exacta_no_queda_en_la_auditoria_ni_se_usa_para_buscar(self):
        self.post('mensaje', self.mensaje(texto='¿Cuánto cuesta el envío a Costa Inventada, calle 3, casa 45?'))
        respuesta = self.post('herramienta', {'nombre': 'cotizar_envio', 'conversacion_id': self.conversacion().id,
                                              'argumentos': {'lugar': 'Costa Inventada, calle 3, casa 45'}})
        self.assertEqual(respuesta.status_code, 200)
        resultado = respuesta.json()['resultado']
        self.assertIn(resultado['estado'], ('precio', 'varios'))
        accion = self.env['brian.accion'].sudo().search([('herramienta', '=', 'juan_cotizar_envio')], limit=1)
        self.assertNotIn('casa 45', accion.argumentos)
        self.assertIn('Costa Inventada', json.loads(accion.argumentos)['lugar'])
        self.assertNotIn('casa 45', json.dumps(resultado))
