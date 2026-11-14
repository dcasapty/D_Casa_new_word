"""Revisión adversarial de «Brian de la tienda» y del lote 2 de la web (2026-11-14).

Cada prueba demuestra un hallazgo: FALLA con el código de 66d01ac y pasa cuando se arregla. Datos inventados."""
import json
from unittest.mock import patch

from odoo.addons.dcasa_conversaciones.tests.test_api import ApiCase
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.tests import new_test_user, tagged

from .common import RAIZ, TiendaCase


@tagged('post_install', '-at_install')
class TestRevisionPdf(TiendaCase):

    def test_el_tope_de_cotizaciones_no_se_salta_con_otra_sesion(self):
        """Cada PDF arranca wkhtmltopdf (Odoo corre con workers = 0) y el borde no cuenta los GET. El tope de Odoo es
        por SESIÓN: con una cookie nueva (o varias peticiones a la vez, antes de que la sesión se guarde) no frena."""
        estados = []
        for _ in range(2):
            self.otra_sesion()   # el mismo navegador sin su cookie: misma conexión (127.0.0.1)
            self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
            for _ in range(6):
                estados.append(self.url_open(f'{RAIZ}/carrito/cotizacion.pdf').status_code)
        self.assertIn(429, estados[10:], f'12 PDF desde la misma conexión en la misma hora: {estados}')


@tagged('post_install', '-at_install')
class TestRevisionPorPagarAMeta(TiendaCase):

    def test_lo_que_brian_gasta_en_un_modelo_de_meta_cuenta_en_por_pagar_a_meta(self):
        """El contrato (§5) decía: «nunca se suma a "Por pagar a Meta" si el modelo NO es de Meta». Brian usa los mismos
        modelos y la misma cuenta que Juan: si el modelo es de Meta, Meta lo cobra. Odoo ni guarda el proveedor de
        cada renglón (``tienda_de_costos`` lo tira) y el saldo queda corto."""
        Panel = self.env['dcasa.juan.panel']
        mes = Panel._ahora_local().strftime('%Y-%m')
        Cliente = type(self.env['dcasa.juan.cliente'])
        salud = {'conectado': True, 'error': None, 'cuerpo': {
            'gasto_ia_mes_usd': 10.0, 'tope_usd': 50, 'mes': mes, 'ia': {'proveedor': 'meta'}}}
        costos = {'conectado': True, 'error': None, 'cuerpo': {
            'mes': mes, 'gasto_usd': 10.0, 'turnos': 100,
            'por_modelo': [{'modelo': 'muse-spark-1.3', 'usd': 10.0, 'turnos': 100, 'estimado': False}],
            'tienda': {'mes': mes, 'usd': 5.0, 'turnos': 40, 'presupuesto_usd': 30, 'por_modelo': [
                {'modelo': 'muse-spark-1.3', 'proveedor': 'meta', 'usd': 5.0, 'turnos': 40, 'estimado': False}]}}}
        with patch.object(Cliente, 'configurado', return_value=True), \
                patch.object(Cliente, 'informe_de_salud', return_value=salud), \
                patch.object(Cliente, 'costos', return_value=costos):
            datos = Panel._datos_de_costos()
        self.assertEqual(datos['tienda']['usd'], 5.0)
        self.assertEqual(datos['pagos']['saldo'], 15.0, '10 de Juan + 5 de Brian, los dos en muse-spark (Meta)')


@tagged('post_install', '-at_install')
class TestRevisionApiTienda(ApiCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gerencia = new_test_user(cls.env, login='zzrv_gerencia', name='ZZRV Gerencia',
                                 groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(gerencia).action_aprobar()

    def test_las_coordenadas_solo_se_aceptan_del_chat_de_la_tienda(self):
        """contrato_cambios §7: lat/lon no están en el esquema «para que el modelo de Juan no pueda inventar
        coordenadas». Pero Odoo las acepta de cualquiera: sin ``origen: tienda`` (Juan, WhatsApp) también las cambia por
        el lugar más cercano y da un precio."""
        self.post('mensaje', self.mensaje())
        conversacion = self.env['dcasa.conversacion'].search(
            [('canal', '=', 'whatsapp_qr'), ('id_externo', '=', '50761230000')])
        respuesta = self.post('herramienta', {'nombre': 'cotizar_envio', 'conversacion_id': conversacion.id,
                                              'argumentos': {'lat': 8.94153, 'lon': -79.84153}})
        resultado = respuesta.json().get('resultado') or {}
        self.assertNotEqual(resultado.get('por_ubicacion'), True,
                            f'Juan (sin origen tienda) obtuvo un precio por coordenadas: {json.dumps(resultado)[:200]}')

    def test_lo_que_pregunta_el_visitante_no_queda_para_siempre_en_la_auditoria(self):
        """La privacidad dice «No guardamos la conversación … se borra sola». Cada herramienta del chat de la tienda
        queda en ``brian.accion`` con sus argumentos (el barrio, lo que buscó) y su resultado, sin fecha de borrado y
        con el canal de Juan (no se distingue de lo de WhatsApp; ``origen`` no se guarda)."""
        self.post('herramienta', {'nombre': 'cotizar_envio', 'origen': 'tienda',
                                  'argumentos': {'lugar': 'Costa Inventada, frente al PH Torre Zeta'}})
        guardadas = self.env['brian.accion'].sudo().search([('argumentos', 'ilike', 'PH Torre Zeta')])
        self.assertFalse(guardadas, [(a.canal, a.argumentos) for a in guardadas])



@tagged('post_install', '-at_install')
class TestRevisionCarrito(TiendaCase):

    def test_agregar_desde_el_chat_no_baja_una_linea_que_ya_tenia_mas_de_20(self):
        """``_poner`` (controllers/main.py): ``min(actual + cantidad, 20)``. Si la línea ya tenía 25 (puestas en
        /shop/cart), «Agregar» desde el chat la deja en 20 sin avisar: el carrito pierde 5."""
        variante = self.colchon.product_variant_id
        self.post('carrito/agregar', {'producto_id': variante.id, 'cantidad': 1})
        linea = self.env['sale.order.line'].sudo().search([('product_id', '=', variante.id)], order='id desc', limit=1)
        linea.product_uom_qty = 25   # lo que el cliente puso en la página del carrito
        datos = self.post('carrito/agregar', {'producto_id': variante.id, 'cantidad': 1}).json()
        self.assertGreaterEqual(datos['carrito']['cantidad_total'], 25, datos)
