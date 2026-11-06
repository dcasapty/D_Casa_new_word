"""Brian lee el Resumen, el Reparto y las cotizaciones que vencen solas (2026-11-06, «Brian al día»).

Las mismas cifras de las pantallas de Juan, como quien pregunta: la vendedora ve lo suyo, Gerencia todo el equipo.
"""
from datetime import datetime, time, timedelta

from odoo.tests import tagged

from ..models.sale_origen import hoy_en_panama
from .test_cotizacion_automatica import CotizarCase


@tagged('post_install', '-at_install')
class TestBrianConversaciones(CotizarCase):

    def brian(self, usuario, nombre, argumentos=None):
        respuesta = self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def test_las_tres_son_de_lectura_y_las_ve_la_vendedora(self):
        catalogo = {e['name']: e for e in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        for nombre in ('resumen_de_conversaciones', 'reparto_de_conversaciones', 'cotizaciones_que_vencen'):
            self.assertIn(nombre, catalogo)
            self.assertEqual(catalogo[nombre]['nivel'], 'lectura')
        interno = {e['name'] for e in self.env['brian.herramientas'].with_user(self.interno).catalogo()}
        self.assertNotIn('resumen_de_conversaciones', interno, 'quien no es de ventas no ve las pantallas de Juan')

    def test_el_resumen_es_el_de_la_pantalla(self):
        self.conversacion('Hola, ¿tienen camas queen?', ts=hoy_en_panama_utc())
        datos = self.brian(self.vendedora, 'resumen_de_conversaciones', {'periodo': '7_dias'})
        pantalla = self.env['dcasa.juan.panel'].with_user(self.vendedora).resumen('7_dias')
        self.assertEqual(datos['conversaciones'], pantalla['conversaciones'])
        self.assertEqual(datos['clientes_que_escribieron'], pantalla['clientes_unicos'])
        self.assertEqual(datos['periodo'], 'Últimos 7 días')
        self.assertIn('Hoy', datos['tasa_de_cierre_por_periodo'])
        self.assertIn('no causalidad', datos['como_se_cuenta'])
        respuesta = self.env['brian.herramientas'].with_user(self.vendedora).ejecutar(
            'resumen_de_conversaciones', {'periodo': 'semana'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('Periodo desconocido', respuesta['error'])

    def test_el_reparto_la_vendedora_ve_lo_suyo_y_gerencia_el_equipo(self):
        suyo = self.brian(self.vendedora, 'reparto_de_conversaciones')
        self.assertEqual(suyo['tu']['nombre'], 'Vendedora Prueba')
        self.assertNotIn('equipo', suyo, 'los números de las demás los ve Gerencia')
        self.assertIn('alcance', suyo)
        self.ajustes.reparto_modo = 'parejo'
        equipo = self.brian(self.gerente, 'reparto_de_conversaciones')
        self.assertIn('Vendedora Prueba', [f['nombre'] for f in equipo['equipo']])
        self.assertIn('esperan_sin_duena', equipo)
        self.assertIn('Parejo', equipo['modo'])

    def test_el_reparto_apagado_lo_dice(self):
        self.ajustes.reparto_modo = 'manual'
        datos = self.brian(self.gerente, 'reparto_de_conversaciones')
        self.assertIn('apagado', datos['nota'])

    def test_cotizaciones_que_vencen_solo_las_que_se_cancelan_solas(self):
        web = self.env['sale.order'].create({
            'partner_id': self.conv.partner_id.id, 'website_id': self.env['website'].search([], limit=1).id,
            'order_line': [(0, 0, {'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        de_vendedora = self.env['sale.order'].create({
            'partner_id': self.conv.partner_id.id, 'validity_date': hoy_en_panama() + timedelta(days=1),
            'order_line': [(0, 0, {'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        bloqueada = self.env['sale.order'].create({
            'partner_id': self.conv.partner_id.id, 'website_id': self.env['website'].search([], limit=1).id,
            'order_line': [(0, 0, {'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        bloqueada.locked = True
        datos = self.brian(self.gerente, 'cotizaciones_que_vencen', {'dias': 5})
        numeros = [c['numero'] for c in datos['cotizaciones']]
        self.assertIn(web.name, numeros)
        self.assertNotIn(de_vendedora.name, numeros, 'las de las vendedoras no vencen solas')
        self.assertNotIn(bloqueada.name, numeros, 'el cron no cancela una bloqueada')
        fila = next(c for c in datos['cotizaciones'] if c['numero'] == web.name)
        self.assertEqual(fila['origen'], 'Web')
        self.assertEqual(fila['valida_hasta'], (hoy_en_panama() + timedelta(days=3)).strftime('%d/%m/%Y'))
        self.assertEqual(datos['dias_que_queda_abierta'], 3)
        # Con 1 día de margen, la de 3 días todavía no sale.
        self.assertNotIn(web.name, [c['numero'] for c in self.brian(self.gerente, 'cotizaciones_que_vencen',
                                                                      {'dias': 1})['cotizaciones']])
        self.ajustes.cotizacion_dias_abierta = 0
        self.assertIn('apagado', self.brian(self.gerente, 'cotizaciones_que_vencen')['dias_que_queda_abierta'])

    def test_cotizaciones_que_vencen_rechaza_dias_fuera_de_rango(self):
        respuesta = self.env['brian.herramientas'].with_user(self.vendedora).ejecutar(
            'cotizaciones_que_vencen', {'dias': 90})
        self.assertFalse(respuesta['ok'])
        self.assertIn('0 a 30', respuesta['error'])


def hoy_en_panama_utc():
    """Un momento de hoy (UTC) que cae dentro de «hoy» en Panamá (17:00 UTC = 12:00 de Panamá)."""
    return datetime.combine(hoy_en_panama(), time(17, 0))
