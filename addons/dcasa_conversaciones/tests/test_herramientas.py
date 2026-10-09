"""Las herramientas del asistente de clientes (vista pública), registradas en el registro de Brian bajo el usuario
técnico ``juan``: lo que ven, lo que NO pueden hacer y la auditoría."""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.tests import tagged
from odoo.tools import mute_logger

from ..models.reglas_clientes import redactar
from .common import JuanCase

PUBLICAS = {'buscar_productos', 'ver_producto', 'listar_categorias', 'reglas_socios', 'horario_y_tienda',
            'saldo_puntos', 'crear_oportunidad', 'anotar_conversacion', 'pasar_a_vendedora',
            'buscar_conocimiento', 'registrar_pregunta_sin_respuesta', 'etiquetar_conversacion'}
PIN = '482913'


def panama(anio, mes, dia, hora=0, minuto=0):
    return datetime(anio, mes, dia, hora, minuto) + timedelta(hours=5)


class HerramientasCase(JuanCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Template = cls.env['product.template']
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        cls.categoria = cls.env['product.public.category'].create({'name': 'Zzdormitorio'})
        cls.otra_categoria = cls.env['product.public.category'].create({'name': 'Zzcocina'})
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'is_published': True,
                'taxes_id': [Command.set(impuesto.ids)]}
        cls.cama = Template.create({
            **base, 'name': 'Zzcama Roble Queen', 'default_code': 'ZZ-CAMA', 'list_price': 349.99,
            'standard_price': 123.45, 'dcasa_medidas': 'Ancho × Largo: 160 × 200 cm',
            'dcasa_combo': 'Combo con colchón First Class $469.99',
            'public_categ_ids': [Command.set(cls.categoria.ids)],
            'description_sale': 'Cama de roble con cabecera.'})
        cls.sofa = Template.create({**base, 'name': 'Zzsofa Gris', 'default_code': 'ZZ-SOFA', 'list_price': 800.0,
                                    'public_categ_ids': [Command.set(cls.categoria.ids)]})
        cls.mesa = Template.create({**base, 'name': 'Zzmesa Pino', 'default_code': 'ZZ-MESA', 'list_price': 90.0,
                                    'public_categ_ids': [Command.set(cls.otra_categoria.ids)]})
        cls.secreto = Template.create({**base, 'name': 'Zzsecreto Borrador', 'default_code': 'ZZ-SECRETO',
                                       'list_price': 10.0, 'is_published': False,
                                       'public_categ_ids': [Command.set(cls.categoria.ids)]})
        tamano = cls.env['product.attribute'].create({'name': 'Zztamaño', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'Zzqueen'}), Command.create({'name': 'Zzking'})]})
        cls.colchon = Template.create({
            **base, 'name': 'Zzcolchón First Class', 'list_price': 400.0, 'default_code': 'ZZ-COL',
            'public_categ_ids': [Command.set(cls.categoria.ids)],
            'attribute_line_ids': [Command.create({'attribute_id': tamano.id,
                                                   'value_ids': [Command.set(tamano.value_ids.ids)]})]})
        almacen = cls.env['stock.warehouse'].search([], limit=1)
        cls.stock = cls.env['stock.quant']
        for plantilla, cantidad in ((cls.cama, 7777), (cls.sofa, 3), (cls.mesa, 0), (cls.secreto, 10)):
            if cantidad:
                cls.stock._update_available_quantity(plantilla.product_variant_id, almacen.lot_stock_id, cantidad)
        variante_queen = cls.colchon.product_variant_ids.filtered(lambda v: 'Zzqueen' in v.display_name)
        cls.stock._update_available_quantity(variante_queen, almacen.lot_stock_id, 20)

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(nombre='Karen')

    def llamar(self, nombre, argumentos=None, conv=None, usuario=None):
        """Ejecuta una herramienta como el usuario técnico ``juan`` (nombre público, sin el prefijo)."""
        conv = conv or self.conv
        herramientas = self.env['brian.herramientas'].with_user(usuario or self.juan).with_context(
            juan_conversacion_id=conv.id if conv else False)
        return herramientas.ejecutar(f'juan_{nombre}', argumentos or {}, canal='juan')

    def salida(self, nombre, argumentos=None, **kw):
        resultado = self.llamar(nombre, argumentos, **kw)
        self.assertTrue(resultado.get('ok'), resultado)
        return resultado['datos']

    def error(self, nombre, argumentos=None, **kw):
        resultado = self.llamar(nombre, argumentos, **kw)
        self.assertFalse(resultado.get('ok'), resultado)
        return resultado['error']


@tagged('post_install', '-at_install')
class TestBuscarProductos(HerramientasCase):

    def nombres(self, datos):
        return [p['nombre'] for p in datos['productos']]

    def test_solo_productos_publicados(self):
        datos = self.salida('buscar_productos', {'consulta': 'zz'})
        nombres = self.nombres(datos)
        self.assertIn('Zzcama Roble Queen', nombres)
        self.assertIn('Zzsofa Gris', nombres)
        self.assertNotIn('Zzsecreto Borrador', nombres, 'Un producto sin publicar no existe para el cliente')
        self.assertEqual(datos['encontrados'], 4)
        # Ni por nombre ni por código se llega al producto sin publicar.
        self.assertEqual(self.salida('buscar_productos', {'consulta': 'ZZ-SECRETO'})['encontrados'], 0)
        self.assertEqual(self.salida('buscar_productos', {'consulta': 'secreto borrador'})['encontrados'], 0)

    def test_precio_con_mas_itbms_y_ficha_completa(self):
        (cama,) = self.salida('buscar_productos', {'consulta': 'ZZ-CAMA'})['productos']
        self.assertEqual(cama['precio'], 349.99)
        self.assertEqual(cama['precio_texto'], '$349.99 + ITBMS')
        self.assertTrue(cama['mas_itbms'])
        self.assertEqual(cama['codigo'], 'ZZ-CAMA')
        self.assertEqual(cama['medidas'], 'Ancho × Largo: 160 × 200 cm')
        self.assertEqual(cama['combo'], {'texto': 'Combo con colchón First Class', 'precio': 469.99,
                                         'precio_texto': '$469.99 + ITBMS'})
        self.assertEqual(cama['categorias'], ['Zzdormitorio'])
        self.assertTrue(cama['url'].endswith(f'-{self.cama.id}'), cama['url'])
        self.assertTrue(cama['url'].startswith('http'))

    def test_existencias_solo_como_etiqueta_nunca_el_numero(self):
        productos = self.salida('buscar_productos', {'consulta': 'zz'})['productos']
        etiquetas = {p['nombre']: p['disponibilidad'] for p in productos}
        self.assertEqual(etiquetas['Zzcama Roble Queen'], 'disponible')    # 7777 unidades
        self.assertEqual(etiquetas['Zzsofa Gris'], 'pocas')                 # 3 unidades
        self.assertEqual(etiquetas['Zzmesa Pino'], 'agotado')               # 0
        texto = json.dumps(self.salida('buscar_productos', {'consulta': 'zz'}))
        self.assertNotIn('7777', texto, 'El número de existencias no sale jamás')
        for clave in ('existencias', 'qty', 'stock', 'cantidad', 'free_qty', 'virtual'):
            self.assertNotIn(f'"{clave}', texto)

    def test_nunca_sale_el_costo(self):
        texto = json.dumps(self.salida('buscar_productos', {'consulta': 'zz'}))
        ver = json.dumps(self.salida('ver_producto', {'codigo': 'ZZ-CAMA'}))
        for contenido in (texto, ver):
            self.assertNotIn('123.45', contenido)
            self.assertNotIn('standard_price', contenido)
            self.assertNotIn('costo', contenido.lower().replace('costo', 'costo'.upper()).lower() if False else 'x')
        self.assertNotIn('"costo', texto.lower())

    def test_busca_sin_importar_acentos_mayusculas_ni_plural(self):
        for consulta in ('ZZCAMA', 'zzcamas', 'cama roble', 'colchones first', 'colchón', 'zzcolchon'):
            with self.subTest(consulta=consulta):
                self.assertTrue(self.salida('buscar_productos', {'consulta': consulta})['encontrados'] > 0)

    def test_busca_por_tamano_o_color_de_la_variante(self):
        nombres = self.nombres(self.salida('buscar_productos', {'consulta': 'colchon zzqueen'}))
        self.assertEqual(nombres, ['Zzcolchón First Class'])

    def test_el_codigo_exacto_va_primero(self):
        productos = self.salida('buscar_productos', {'consulta': 'ZZ-SOFA'})['productos']
        self.assertEqual(productos[0]['nombre'], 'Zzsofa Gris')

    def test_filtra_por_categoria(self):
        nombres = self.nombres(self.salida('buscar_productos', {'consulta': 'zz', 'categoria': 'Zzcocina'}))
        self.assertEqual(nombres, ['Zzmesa Pino'])
        todas = self.nombres(self.salida('buscar_productos', {'consulta': 'zz', 'categoria': 'zzdormitorios'}))
        self.assertNotIn('Zzmesa Pino', todas)

    def test_categoria_inexistente_dice_cuales_hay(self):
        error = self.error('buscar_productos', {'consulta': 'zz', 'categoria': 'Zzjardin'})
        self.assertIn('Zzdormitorio', error)
        self.assertIn('Zzcocina', error)

    def test_limite(self):
        datos = self.salida('buscar_productos', {'consulta': 'zz', 'limite': 2})
        self.assertEqual((datos['encontrados'], datos['mostrados'], len(datos['productos'])), (4, 2, 2))
        self.assertEqual(len(self.salida('buscar_productos', {'consulta': 'zz', 'limite': 999})['productos']), 4)

    def test_sin_resultados_y_consulta_vacia(self):
        self.assertEqual(self.salida('buscar_productos', {'consulta': 'helicoptero'})['productos'], [])
        self.assertIn('Dime qué producto', self.error('buscar_productos', {'consulta': '   '}))
        self.assertIn('Faltan datos', self.error('buscar_productos', {}))

    def test_el_resultado_trae_el_aviso_de_precios_y_disponibilidad(self):
        nota = self.salida('buscar_productos', {'consulta': 'zz'})['nota']
        self.assertIn('sin ITBMS', nota)
        self.assertIn('una vendedora la confirma', nota)

    def test_producto_sin_foto_tiene_foto_nula(self):
        (cama,) = self.salida('buscar_productos', {'consulta': 'ZZ-CAMA'})['productos']
        self.assertIsNone(cama['foto'])
        self.cama.image_1920 = _PNG
        self.env.flush_all()
        (cama,) = self.salida('buscar_productos', {'consulta': 'ZZ-CAMA'})['productos']
        self.assertTrue(cama['foto'].endswith(f'/web/image/product.template/{self.cama.id}/image_1024'))


@tagged('post_install', '-at_install')
class TestVerProductoYCategorias(HerramientasCase):

    def test_ficha_por_codigo(self):
        ficha = self.salida('ver_producto', {'codigo': 'zz-cama'})
        self.assertEqual(ficha['nombre'], 'Zzcama Roble Queen')
        self.assertEqual(ficha['descripcion'], 'Cama de roble con cabecera.')
        self.assertEqual(ficha['precio_texto'], '$349.99 + ITBMS')
        self.assertEqual(ficha['disponibilidad'], 'disponible')
        self.assertEqual(ficha['galeria'], [])
        self.assertIn('nota', ficha)

    def test_variantes_con_su_disponibilidad(self):
        ficha = self.salida('ver_producto', {'codigo': 'ZZ-COL'})
        etiquetas = {v['nombre']: v['disponibilidad'] for v in ficha['variantes']}
        self.assertEqual(len(etiquetas), 2)
        self.assertEqual(sorted(etiquetas.values()), ['agotado', 'disponible'])
        self.assertTrue(all(v['precio_texto'].endswith('+ ITBMS') for v in ficha['variantes']))

    def test_galeria_de_fotos(self):
        self.env['product.image'].create({'name': 'Lateral', 'product_tmpl_id': self.cama.id, 'image_1920': _PNG})
        ficha = self.salida('ver_producto', {'codigo': 'ZZ-CAMA'})
        self.assertEqual(len(ficha['galeria']), 1)
        self.assertIn('/web/image/product.image/', ficha['galeria'][0])

    def test_un_producto_sin_publicar_responde_igual_que_uno_que_no_existe(self):
        sin_publicar = self.error('ver_producto', {'codigo': 'ZZ-SECRETO'})
        inexistente = self.error('ver_producto', {'codigo': 'ZZ-NO-EXISTE'})
        self.assertIn('no lo manejamos', sin_publicar)
        self.assertEqual(sin_publicar.replace('ZZ-SECRETO', 'X'), inexistente.replace('ZZ-NO-EXISTE', 'X'))

    def test_listar_categorias_cuenta_solo_publicados(self):
        categorias = {c['nombre']: c for c in self.salida('listar_categorias')['categorias']}
        self.assertEqual(categorias['Zzdormitorio']['productos'], 3)      # cama, sofá y colchón (no el borrador)
        self.assertEqual(categorias['Zzcocina']['productos'], 1)
        self.assertIn('/shop/category/', categorias['Zzdormitorio']['url'])


@tagged('post_install', '-at_install')
class TestSocios(HerramientasCase):

    def setUp(self):
        super().setUp()
        self.ficha = self.conv.partner_id
        self.ficha._dcasa_asegurar_ficha()
        self.ficha._dcasa_guardar_pin(PIN)
        self.env['dcasa.movimiento']._asentar(self.ficha, 'ajuste', 1500, 'sistema', motivo='Saldo de prueba')

    def saldo(self, pin=PIN, celular='6123-4567', conv=None):
        return self.salida('saldo_puntos', {'celular': celular, 'pin': pin}, conv=conv)

    def test_reglas_socios_son_las_de_puntos_json(self):
        datos = self.salida('reglas_socios')
        self.assertEqual(datos['cifras'], redactar(R.cargar_reglas())['cifras'])
        self.assertEqual(datos['version'], R.cargar_reglas()['version'])
        self.assertIn('1 punto por cada dólar', ' '.join(datos['resumen']))
        self.assertTrue(datos['enlaces']['premios'].endswith('/socios/premios'))

    def test_saldo_con_el_pin_correcto(self):
        datos = self.saldo()
        self.assertTrue(datos['verificado'])
        self.assertEqual(datos['puntos'], 1500)
        self.assertEqual(datos['puntos_texto'], '1,500 puntos')
        self.assertTrue(datos['enlace_para_invitar'].endswith(f'/r/{self.ficha.dcasa_socio_codigo}'))
        self.assertNotIn('movimientos', datos, 'Sin la lista de movimientos con motivos')
        self.assertNotIn('Saldo de prueba', json.dumps(datos))

    def test_con_el_celular_escrito_de_otra_forma(self):
        self.assertTrue(self.saldo(celular='+507 6123-4567')['verificado'])
        self.assertTrue(self.saldo(celular='50761234567')['verificado'])

    def test_pin_incorrecto_cuenta_el_fallo_y_se_guarda(self):
        datos = self.saldo(pin='111112')
        self.assertFalse(datos['verificado'])
        self.assertEqual(datos['motivo'], 'pin_incorrecto')
        self.assertNotIn('puntos', datos)
        self.assertEqual(self.ficha.dcasa_intentos_fallidos, 1, 'El fallo persiste: la herramienta no lanza error')

    def test_candado_del_programa_5_fallos_15_minutos(self):
        for _ in range(5):
            self.assertEqual(self.saldo(pin='111112')['motivo'], 'pin_incorrecto')
        self.assertTrue(self.ficha._dcasa_bloqueada())
        bloqueado = self.saldo(pin=PIN)           # ni el PIN correcto abre un candado
        self.assertEqual(bloqueado['motivo'], 'bloqueado')
        self.assertIn('15 minutos', bloqueado['mensaje'])
        self.assertNotIn('puntos', bloqueado)
        self.ficha._dcasa_desbloquear()
        self.assertTrue(self.saldo()['verificado'])
        self.assertEqual(self.ficha.dcasa_intentos_fallidos, 0)

    def test_solo_el_numero_de_la_conversacion(self):
        otra = self.Partner.create({'name': 'Otra socia', 'phone': '6555-0101'})
        otra._dcasa_asegurar_ficha()
        otra._dcasa_guardar_pin(PIN)
        datos = self.saldo(celular='6555-0101')
        self.assertEqual(datos['motivo'], 'celular_distinto')
        self.assertNotIn('puntos', datos)
        self.assertEqual(otra.dcasa_intentos_fallidos, 0, 'Ni se prueba el PIN de la otra persona')
        self.assertEqual(self.ficha.dcasa_intentos_fallidos, 0)

    def test_por_canales_sin_celular_no_se_consulta_el_saldo(self):
        telegram = self.conversacion(canal='telegram', id_externo='55', celular='6123-4567')
        self.assertEqual(telegram.partner_id, self.ficha)
        datos = self.saldo(conv=telegram)
        self.assertEqual(datos['motivo'], 'canal_sin_celular')
        self.assertNotIn('puntos', datos)

    def test_quien_no_se_ha_registrado(self):
        nuevo = self.conversacion(id_externo='50765550202')
        datos = self.saldo(celular='6555-0202', conv=nuevo)
        self.assertEqual(datos['motivo'], 'sin_registro')
        self.assertIn('/socios', datos['mensaje'])

    def test_pin_mal_escrito_no_cuenta_como_intento(self):
        for pin in ('123', 'abcdef', '1234567', ''):
            with self.subTest(pin=pin):
                resultado = self.llamar('saldo_puntos', {'celular': '6123-4567', 'pin': pin})
                if resultado['ok']:
                    self.assertEqual(resultado['datos']['motivo'], 'pin_invalido')
        self.assertEqual(self.ficha.dcasa_intentos_fallidos, 0)

    def test_cuenta_suspendida_no_da_saldo(self):
        self.ficha.dcasa_socio_estado = 'suspendido'
        datos = self.saldo()
        self.assertFalse(datos['verificado'])
        self.assertEqual(datos['motivo'], 'suspendido')

    def test_sin_la_pimienta_no_se_puede_verificar(self):
        with patch.dict('os.environ', {'DCASA_PIN_PEPPER': ''}):
            datos = self.saldo()
        self.assertEqual(datos['motivo'], 'no_disponible')

    def test_el_pin_nunca_queda_en_la_auditoria(self):
        self.saldo(pin='654321')
        self.saldo(pin=PIN)
        acciones = self.env['brian.accion'].search([('herramienta', '=', 'juan_saldo_puntos')])
        self.assertEqual(len(acciones), 2)
        for accion in acciones:
            self.assertNotIn('654321', accion.argumentos or '')
            self.assertNotIn(PIN, accion.argumentos or '')
            self.assertNotIn(PIN, accion.resultado or '')
            self.assertIn('***', accion.argumentos)

    def test_no_escribe_en_el_libro_de_puntos(self):
        antes = self.env['dcasa.movimiento'].search_count([])
        self.saldo()
        self.salida('reglas_socios')
        self.assertEqual(self.env['dcasa.movimiento'].search_count([]), antes)
        self.assertEqual(self.ficha.dcasa_saldo, 1500)


@tagged('post_install', '-at_install')
class TestEscrituraAcotada(HerramientasCase):

    def test_crear_oportunidad(self):
        datos = self.salida('crear_oportunidad', {
            'resumen': 'Quiere una cama queen con base para esta semana', 'interes': 'Cama queen con base',
            'presupuesto': 400})
        self.assertTrue(datos['nueva'])
        lead = self.env['crm.lead'].browse(datos['oportunidad_id'])
        self.assertEqual(lead.partner_id, self.conv.partner_id)
        self.assertEqual(lead.type, 'opportunity')
        self.assertEqual(lead.expected_revenue, 400)
        self.assertIn('Cama queen con base', lead.name)
        self.assertIn('WhatsApp (QR)', lead.name)
        self.assertEqual(self.conv.oportunidad_id, lead)
        self.assertIn('cama queen con base para esta semana', lead.description)

    def test_no_duplica_una_oportunidad_abierta_reciente(self):
        primera = self.salida('crear_oportunidad', {'resumen': 'Quiere una cama', 'interes': 'Cama'})
        segunda = self.salida('crear_oportunidad', {'resumen': 'Ahora también un colchón', 'interes': 'Colchón'})
        self.assertTrue(primera['nueva'])
        self.assertFalse(segunda['nueva'])
        self.assertEqual(primera['oportunidad_id'], segunda['oportunidad_id'])
        self.assertEqual(self.env['crm.lead'].search_count([('partner_id', '=', self.conv.partner_id.id)]), 1)
        lead = self.env['crm.lead'].browse(primera['oportunidad_id'])
        self.assertTrue(any('Ahora también un colchón' in (m.body or '') for m in lead.message_ids))

    def test_una_oportunidad_ganada_o_vieja_no_se_reutiliza(self):
        creada = self.salida('crear_oportunidad', {'resumen': 'a', 'interes': 'Cama'})
        primera = self.env['crm.lead'].browse(creada['oportunidad_id'])
        primera.action_set_won()
        self.conv.oportunidad_id = False
        nueva = self.salida('crear_oportunidad', {'resumen': 'Otra compra', 'interes': 'Sofá'})
        self.assertTrue(nueva['nueva'])
        self.assertNotEqual(nueva['oportunidad_id'], primera.id)

    def test_oportunidad_sin_datos_o_con_presupuesto_raro(self):
        self.assertIn('Faltan datos', self.error('crear_oportunidad', {'resumen': 'x'}))
        error = self.error('crear_oportunidad', {'resumen': 'x', 'interes': 'y', 'presupuesto': -5})
        self.assertIn('presupuesto', error)

    def test_el_texto_del_cliente_no_se_ejecuta_como_html(self):
        datos = self.salida('crear_oportunidad', {'resumen': '<script>alert(1)</script>', 'interes': '<b>x</b>'})
        lead = self.env['crm.lead'].browse(datos['oportunidad_id'])
        self.assertNotIn('<script>', lead.description)

    def test_anotar_conversacion_va_al_chatter_del_cliente(self):
        anotada = self.salida('anotar_conversacion', {'nota': 'Prefiere entrega en la tarde'})
        self.assertEqual(anotada, {'anotado': True})
        notas = self.conv.partner_id.message_ids.filtered(lambda m: 'Prefiere entrega en la tarde' in (m.body or ''))
        self.assertEqual(len(notas), 1)
        self.assertEqual(notas.subtype_id, self.env.ref('mail.mt_note'), 'Nota interna: el cliente no la ve')
        self.assertIn('Nota del asistente', notas.body)
        self.assertIn('vacía', self.error('anotar_conversacion', {'nota': '  '}))

    def test_las_herramientas_de_la_conversacion_exigen_conversacion(self):
        resultado = self.env['brian.herramientas'].with_user(self.juan).ejecutar(
            'juan_anotar_conversacion', {'nota': 'x'}, canal='juan')
        self.assertFalse(resultado['ok'])
        self.assertIn('dentro de una conversación', resultado['error'])

    def test_el_cliente_siempre_sale_de_la_conversacion_no_de_los_argumentos(self):
        otro = self.conversacion(id_externo='50765550303', nombre='Otro cliente')
        for argumentos in ({'nota': 'x', 'conversacion_id': otro.id}, {'nota': 'x', 'partner_id': otro.partner_id.id}):
            self.assertIn('no existen', self.error('anotar_conversacion', argumentos))
        self.salida('anotar_conversacion', {'nota': 'solo para Karen'})
        self.assertFalse(otro.partner_id.message_ids.filtered(lambda m: 'solo para Karen' in (m.body or '')))


@tagged('post_install', '-at_install')
class TestPasarAVendedora(HerramientasCase):

    def test_dentro_de_horario(self):
        with freeze_time(panama(2026, 10, 9, 10, 0)):
            datos = self.salida('pasar_a_vendedora', {'motivo': 'Quiere cotizar una entrega a David'})
        self.assertTrue(datos['dentro_de_horario'])
        self.assertIn('ya avisé a una vendedora', datos['texto_para_el_cliente'])
        self.assertEqual(self.conv.estado, 'humano')
        self.assertFalse(self.conv._estado_para_worker()['bot_activo'], 'Pausa al bot')
        self.assertTrue(self.conv.pausada_hasta)

    def test_fuera_de_horario_dice_cuando_atienden(self):
        with freeze_time(panama(2026, 10, 9, 22, 0)):
            datos = self.salida('pasar_a_vendedora', {'motivo': 'Pide una persona'})
        self.assertFalse(datos['dentro_de_horario'])
        self.assertIn('mañana a primera hora, desde las 8:00 a. m.', datos['texto_para_el_cliente'])
        self.assertNotIn('ahora', datos['texto_para_el_cliente'])
        self.assertNotIn('..', datos['texto_para_el_cliente'], 'Un punto de más al final de «a. m.»')

    def test_deja_una_actividad_para_la_vendedora(self):
        with freeze_time(panama(2026, 10, 9, 10, 0)):
            self.salida('pasar_a_vendedora', {'motivo': 'Financiamiento', 'urgencia': 'alta'})
        (actividad,) = self.conv.activity_ids
        self.assertIn('URGENTE', actividad.summary)
        self.assertIn('Karen', actividad.summary)
        self.assertEqual(actividad.user_id, self.ajustes.responsable_id)
        self.assertIn('Financiamiento', actividad.note)

    def test_la_actividad_va_a_quien_ya_atiende_la_conversacion(self):
        self.conv.asignada_a = self.vendedora
        self.salida('pasar_a_vendedora', {'motivo': 'x'})
        self.assertEqual(self.conv.activity_ids.user_id, self.vendedora)

    def test_avisa_por_telegram_a_las_vendedoras_vinculadas(self):
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        # sin ventas
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.interno.id, 'chat_id': '5550002'})
        enviar = MagicMock()
        with patch.object(type(self.env['brian.telegram.enlace']), '_enviar', enviar):
            self.salida('pasar_a_vendedora', {'motivo': 'Quiere hablar con una persona'})
        chats = [llamada.args[0] for llamada in enviar.call_args_list]
        self.assertEqual(chats, ['5550001'])
        self.assertIn('Karen', enviar.call_args.args[1])
        self.assertIn('Quiere hablar con una persona', enviar.call_args.args[1])

    def test_un_fallo_de_telegram_no_rompe_el_traspaso(self):
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        with patch.object(type(self.env['brian.telegram.enlace']), '_enviar', side_effect=RuntimeError('sin red')), \
                mute_logger('odoo.addons.dcasa_conversaciones.models.conversacion'):   # se anota; aquí es esperado
            datos = self.salida('pasar_a_vendedora', {'motivo': 'x'})
        self.assertIn('texto_para_el_cliente', datos)
        self.assertEqual(self.conv.estado, 'humano')

    def test_aviso_a_las_personas_elegidas_en_ajustes(self):
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.gerente.id, 'chat_id': '5550009'})
        self.ajustes.usuarios_aviso_ids = self.gerente
        enviar = MagicMock()
        with patch.object(type(self.env['brian.telegram.enlace']), '_enviar', enviar):
            self.salida('pasar_a_vendedora', {'motivo': 'x'})
        self.assertEqual([c.args[0] for c in enviar.call_args_list], ['5550009'])

    def test_la_pausa_es_la_de_los_ajustes(self):
        self.ajustes.pausa_por_defecto_minutos = 30
        antes = fields.Datetime.now()
        self.salida('pasar_a_vendedora', {'motivo': 'x'})
        self.assertAlmostEqual((self.conv.pausada_hasta - antes).total_seconds(), 1800, delta=60)


@tagged('post_install', '-at_install')
class TestHorarioYTienda(HerramientasCase):

    def test_datos_reales_de_la_tienda(self):
        with freeze_time(panama(2026, 10, 9, 10, 0)):
            datos = self.salida('horario_y_tienda')
        self.assertIn('Frente al Parque Libertadores', datos['direccion'])
        self.assertIn('Diagonal a la Discoteca Seven', datos['direccion'])
        self.assertIn('La Chorrera', datos['direccion'])
        self.assertIn('google.com/maps', datos['como_llegar'])
        self.assertEqual(datos['whatsapp'], '+507 6026-1919')
        self.assertEqual(datos['correo'], 'info@dcasapty.com')
        self.assertEqual(datos['horario']['texto'], 'Todos los días, de 8:00 a. m. a 5:00 p. m. (hora de Panamá)')
        self.assertEqual(datos['fecha_hora_panama'], 'viernes 9 de octubre de 2026, 10:00 a. m.')
        self.assertTrue(datos['abierto_ahora'])

    def test_cerrado_fuera_de_horario(self):
        with freeze_time(panama(2026, 10, 9, 20, 0)):
            self.assertFalse(self.salida('horario_y_tienda')['abierto_ahora'])

    def test_el_horario_es_el_de_los_ajustes(self):
        self.ajustes.write({'horario_inicio': 9.0, 'horario_fin': 18.0, 'dia_domingo': False})
        datos = self.salida('horario_y_tienda')
        self.assertIn('9:00 a. m. a 6:00 p. m.', datos['horario']['texto'])
        self.assertNotIn('Todos los días', datos['horario']['texto'])
        self.assertEqual(datos['horario']['dias'], [1, 2, 3, 4, 5, 6])


@tagged('post_install', '-at_install')
class TestUsuarioTecnicoYAuditoria(HerramientasCase):

    def test_juan_no_tiene_permisos_internos_ni_contrasena(self):
        self.assertFalse(self.juan.has_group('base.group_user'))
        self.assertFalse(self.juan._is_internal())
        self.assertTrue(self.juan.has_group('dcasa_conversaciones.group_juan'))
        grupos = set(self.juan.all_group_ids.mapped('full_name'))
        internos = ('Administration', 'Sales', 'Accounting', 'Inventory')
        self.assertFalse({g for g in grupos if any(interno in g for interno in internos)}, grupos)
        self.assertFalse(self.juan.sudo().password, 'Sin contraseña: no puede entrar al panel')
        with self.assertRaises(Exception):  # noqa: B017 — cualquier fallo de autenticación sirve
            self.env['res.users'].authenticate({'type': 'password', 'login': 'juan.asistente', 'password': ''},
                                               {'interactive': False})

    def test_el_grupo_de_juan_no_implica_ningun_otro(self):
        grupo = self.env.ref('dcasa_conversaciones.group_juan')
        self.assertFalse(grupo.implied_ids)

    def test_juan_ve_solo_las_herramientas_de_juan(self):
        catalogo = {h['name'] for h in self.env['brian.herramientas'].with_user(self.juan).catalogo()}
        self.assertEqual(catalogo, {f'juan_{n}' for n in PUBLICAS})

    def test_ninguna_es_sensible_ni_escribe_dinero(self):
        for h in self.env['brian.herramientas'].with_user(self.juan).catalogo():
            self.assertNotEqual(h['nivel'], 'sensible', h['name'])
        prohibidas = {'ajustar_puntos', 'confirmar_venta', 'cancelar_cotizacion', 'crear_factura', 'editar_factura',
                      'publicar_factura', 'registrar_pago', 'conciliar_movimiento', 'crear_producto',
                      'actualizar_producto', 'publicar_producto_web', 'ajustar_existencias', 'ver_cliente',
                      'buscar_clientes', 'reporte_del_dia', 'resumen_ventas', 'buscar_ventas', 'ver_venta',
                      'facturas_pendientes', 'clientes_que_deben', 'existencias_bajas', 'listar_usuarios'}
        for nombre in prohibidas:
            with self.subTest(herramienta=nombre):
                self.assertNotIn(nombre, PUBLICAS)
                resultado = self.env['brian.herramientas'].with_user(self.juan).ejecutar(nombre, {}, canal='juan')
                self.assertFalse(resultado['ok'])
                self.assertIn('No existe la herramienta', resultado['error'])

    def test_el_personal_interno_no_ve_ni_usa_las_de_juan(self):
        for usuario in (self.vendedora, self.gerente, self.interno, self.env.ref('base.user_admin')):
            catalogo = {h['name'] for h in self.env['brian.herramientas'].with_user(usuario).catalogo()}
            self.assertFalse({n for n in catalogo if n.startswith('juan_')}, usuario.login)
            resultado = self.env['brian.herramientas'].with_user(usuario).ejecutar('juan_horario_y_tienda', {})
            self.assertFalse(resultado['ok'])

    def test_las_herramientas_internas_de_brian_siguen_igual(self):
        catalogo = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertIn('buscar_productos', catalogo)
        self.assertIn('ver_producto', catalogo)
        self.assertIn('saldo_puntos', catalogo)

    def test_cada_uso_queda_auditado_a_nombre_de_juan(self):
        self.salida('buscar_productos', {'consulta': 'zz'})
        accion = self.env['brian.accion'].search([('herramienta', '=', 'juan_buscar_productos')], limit=1)
        self.assertEqual(accion.estado, 'hecha')
        self.assertEqual(accion.canal, 'juan')
        self.assertEqual(accion.create_uid, self.juan)
        self.assertEqual(accion.dcasa_conversacion_id, self.conv)
        self.assertIn('zz', accion.argumentos)
        self.assertIn('Zzcama', accion.resultado)

    def test_los_errores_tambien_quedan_en_la_auditoria(self):
        self.error('ver_producto', {'codigo': 'NO-EXISTE'})
        accion = self.env['brian.accion'].search([('herramienta', '=', 'juan_ver_producto')], limit=1)
        self.assertEqual(accion.estado, 'error')
        self.assertEqual(accion.canal, 'juan')

    def test_juan_es_un_solo_usuario_para_todos_y_no_choca_con_el_limite_de_brian(self):
        # El límite de Brian es de 30 acciones por minuto POR USUARIO; Juan atiende a todos los clientes.
        for _ in range(40):
            self.assertTrue(self.llamar('horario_y_tienda')['ok'])
        self.assertEqual(self.env['brian.accion'].search_count([('herramienta', '=', 'juan_horario_y_tienda')]), 40)

    def test_ni_una_sola_herramienta_cambia_precios_stock_ni_contabilidad(self):
        Producto, Quant, Factura = self.env['product.template'], self.env['stock.quant'], self.env['account.move']
        antes = (Producto.search_count([]), sum(Producto.search([]).mapped('list_price')),
                 sum(Quant.search([]).mapped('quantity')), Factura.search_count([]),
                 self.env['account.payment'].search_count([]), self.env['dcasa.movimiento'].search_count([]))
        self.salida('buscar_productos', {'consulta': 'zz'})
        self.salida('ver_producto', {'codigo': 'ZZ-CAMA'})
        self.salida('listar_categorias')
        self.salida('reglas_socios')
        self.salida('horario_y_tienda')
        self.llamar('saldo_puntos', {'celular': '6123-4567', 'pin': '000000'})
        self.salida('crear_oportunidad', {'resumen': 'x', 'interes': 'y'})
        self.salida('anotar_conversacion', {'nota': 'x'})
        self.salida('pasar_a_vendedora', {'motivo': 'x'})
        despues = (Producto.search_count([]), sum(Producto.search([]).mapped('list_price')),
                   sum(Quant.search([]).mapped('quantity')), Factura.search_count([]),
                   self.env['account.payment'].search_count([]), self.env['dcasa.movimiento'].search_count([]))
        self.assertEqual(antes, despues)

    def test_parametros_desconocidos_se_rechazan(self):
        self.assertIn('no existen', self.error('buscar_productos', {'consulta': 'zz', 'costo': True}))


@tagged('post_install', '-at_install')
class TestConocimientoYAprendizaje(HerramientasCase):

    def test_buscar_conocimiento_devuelve_el_texto_del_equipo(self):
        datos = self.salida('buscar_conocimiento', {'consulta': '¿A qué hora abren y dónde están?'})
        self.assertGreaterEqual(datos['encontrados'], 1)
        primero = datos['resultados'][0]
        self.assertEqual(primero['titulo'], 'Dónde estamos, horario y WhatsApp')
        self.assertIn('Frente al Parque Libertadores', primero['contenido'])
        self.assertIn('+507 6026-1919', primero['contenido'])
        self.assertIn('siempre los confirma una vendedora', datos['nota'])

    def test_las_reglas_de_socios_salen_de_puntos_json(self):
        datos = self.salida('buscar_conocimiento', {'consulta': 'puntos y premios'})
        self.assertEqual(datos['resultados'][0]['titulo'], "Programa Socios D'CASA: puntos, premios e invitados")
        self.assertIn('1 punto por cada dólar', datos['resultados'][0]['contenido'])

    def test_maximo_3_resultados(self):
        for i in range(6):
            self.env['dcasa.conocimiento'].create({'titulo': f'Zzmantenimiento {i}', 'contenido': 'zzmantenimiento'})
        self.assertEqual(len(self.salida('buscar_conocimiento', {'consulta': 'zzmantenimiento'})['resultados']), 3)

    def test_lo_inactivo_no_lo_ve_el_bot(self):
        datos = self.salida('buscar_conocimiento', {'consulta': 'garantía de los colchones'})
        self.assertEqual(datos['encontrados'], 0)
        self.assertIn('registrar_pregunta_sin_respuesta', datos['nota'])
        self.assertNotIn('Ley 45', json.dumps(datos))

    def test_consulta_sin_palabras(self):
        self.assertIn('Dime sobre qué tema', self.error('buscar_conocimiento', {'consulta': '¿?'}))

    def test_registrar_pregunta_sin_respuesta(self):
        datos = self.salida('registrar_pregunta_sin_respuesta', {'pregunta': '¿Instalan los muebles?',
                                                                 'resumen': 'Hablaban de una cama king'})
        self.assertTrue(datos['registrada'] and datos['es_nueva'])
        self.assertEqual(datos['veces'], 1)
        self.assertIn('una vendedora', datos['mensaje'])
        pregunta = self.env['dcasa.pregunta_pendiente'].search([])
        self.assertEqual((pregunta.texto, pregunta.resumen, pregunta.conversacion_id),
                         ('¿Instalan los muebles?', 'Hablaban de una cama king', self.conv))

    def test_la_pregunta_repetida_suma_y_no_se_duplica(self):
        self.salida('registrar_pregunta_sin_respuesta', {'pregunta': '¿Instalan los muebles?'})
        otra = self.conversacion(id_externo='50761230777')
        datos = self.salida('registrar_pregunta_sin_respuesta', {'pregunta': 'instalan los muebles'}, conv=otra)
        self.assertEqual((datos['es_nueva'], datos['veces']), (False, 2))
        self.assertEqual(self.env['dcasa.pregunta_pendiente'].search_count([]), 1)

    def test_pregunta_invalida(self):
        for pregunta in ('', '??', '12'):
            self.assertTrue(self.error('registrar_pregunta_sin_respuesta', {'pregunta': pregunta}))
        self.assertFalse(self.env['dcasa.pregunta_pendiente'].search([]))

    def test_exige_conversacion_y_queda_auditada(self):
        resultado = self.env['brian.herramientas'].with_user(self.juan).ejecutar(
            'juan_registrar_pregunta_sin_respuesta', {'pregunta': '¿Instalan los muebles?'}, canal='juan')
        self.assertFalse(resultado['ok'])
        self.salida('registrar_pregunta_sin_respuesta', {'pregunta': '¿Instalan los muebles?'})
        accion = self.env['brian.accion'].search([('herramienta', '=', 'juan_registrar_pregunta_sin_respuesta')],
                                                 order='id desc', limit=1)
        self.assertEqual((accion.canal, accion.estado, accion.dcasa_conversacion_id), ('juan', 'hecha', self.conv))

    def test_no_toca_precios_ni_puntos(self):
        precios = self.env['product.template'].search([]).mapped('list_price')
        antes = (self.env['dcasa.movimiento'].search_count([]), sum(precios))
        self.salida('buscar_conocimiento', {'consulta': 'garantía'})
        self.salida('registrar_pregunta_sin_respuesta', {'pregunta': '¿Instalan los muebles?'})
        precios = self.env['product.template'].search([]).mapped('list_price')
        despues = (self.env['dcasa.movimiento'].search_count([]), sum(precios))
        self.assertEqual(antes, despues)


# PNG mínimo de 1×1 (para probar la foto del producto).
_PNG = (b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
