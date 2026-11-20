"""Dos avisos de Yappy AL MISMO TIEMPO, con dos conexiones de verdad a PostgreSQL (no la conexión compartida de las
pruebas).

Las demás pruebas del módulo corren dentro de una sola transacción: ahí no puede haber dos avisos a la vez ni un
candado que espere. Esta mira lo único que importa del bloqueo: que el segundo aviso ESPERA al primero (no se descarta
ni se mezcla) y que el pedido queda pagado UNA sola vez.

**Es opt-in** porque escribe datos de verdad (los borra al terminar, pero escribe): se corre a propósito, en una base
de pruebas, con ``DCASA_PRUEBA_CONCURRENCIA=1`` y ``--test-tags dcasa_pago_yappy:TestAvisosAlMismoTiempo``. Sin esa
variable se salta, y así no deja nada en la base compartida del CI.
"""
import os
import threading
import time
import unittest

from psycopg2 import OperationalError

from odoo import SUPERUSER_ID, Command, api
from odoo.addons.dcasa_pago_yappy.models import yappy_api as api_yappy
from odoo.modules.registry import Registry
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tests import tagged
from odoo.tests.common import BaseCase, get_db_name
from odoo.tools import mute_logger

from .common import aviso_de, entorno

ACTIVA = bool(os.environ.get('DCASA_PRUEBA_CONCURRENCIA'))
ESPERA_MAXIMA = 20     # segundos que se espera a que el segundo aviso quede esperando el candado


@unittest.skipUnless(ACTIVA, 'Opt-in: escribe datos de verdad. Se corre con DCASA_PRUEBA_CONCURRENCIA=1')
@tagged('post_install', '-at_install')
class TestAvisosAlMismoTiempo(BaseCase):

    def setUp(self):
        super().setUp()
        self.registry = Registry(get_db_name())
        self.addCleanup(entorno().start().stop)
        self.addCleanup(self._limpiar)
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            proveedor = env.ref('dcasa_pago_yappy.payment_provider_yappy')
            metodo = env.ref('dcasa_pago_yappy.payment_method_yappy')
            self.cliente_id = env['res.partner'].create({
                'name': 'Ana Concurrencia Yappy', 'email': 'ana.concurrencia@example.com',
                'phone': '+507 6000-0101'}).id
            self.producto_id = env['product.product'].create({
                'name': 'Sofá de concurrencia (Yappy)', 'type': 'consu', 'list_price': 100.0}).id
            pedido = env['sale.order'].create({
                'partner_id': self.cliente_id, 'website_id': env.ref('website.default_website').id,
                'order_line': [Command.create({'product_id': self.producto_id, 'product_uom_qty': 1})]})
            self.pedido_id = pedido.id
            tx = env['payment.transaction'].create({
                'provider_id': proveedor.id, 'payment_method_id': metodo.id, 'amount': pedido.amount_total,
                'currency_id': pedido.currency_id.id, 'partner_id': pedido.partner_invoice_id.id,
                'operation': 'online_direct', 'sale_order_ids': [Command.set(pedido.ids)]})
            tx.write({'dcasa_yappy_orden': 'CONC' + str(tx.id).zfill(6) + 'AB', 'state': 'pending'})
            self.tx_id = tx.id
            self.orden = tx.dcasa_yappy_orden

    def _limpiar(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            cr.execute("UPDATE payment_transaction SET state = 'draft' WHERE id = %s", [self.tx_id])
            for modelo, ids in (('payment.transaction', [self.tx_id]), ('sale.order', [self.pedido_id]),
                                ('product.product', [self.producto_id]), ('res.partner', [self.cliente_id])):
                try:
                    with cr.savepoint():
                        registros = env[modelo].browse(ids).exists()
                        if modelo == 'sale.order':
                            registros.action_cancel()
                        registros.unlink()
                except Exception:  # noqa: BLE001 - limpiar es de mejor esfuerzo
                    pass

    def _aviso(self, estado):
        verificado, motivo = api_yappy.verificar_aviso(api_yappy.credenciales(), aviso_de(self.orden, estado))
        self.assertIsNotNone(verificado, motivo)
        return verificado

    def _entornos(self, cuantos=4):
        """Conexiones nuevas, ARMADAS EN EL HILO PRINCIPAL: mientras corren las pruebas de instalación, el hilo
        principal tiene el candado del registro de Odoo y un hilo que arme un ``Environment`` se queda esperándolo (la
        prueba de concurrencia de Odoo, ``website_sale_loyalty``, lo hace igual: arma las conexiones antes y los hilos
        solo las usan)."""
        return [api.Environment(self.registry.cursor(), SUPERUSER_ID, {}) for _i in range(cuantos)]

    def _aplicar(self, estado, entornos, antes_de_soltar=None):
        """Lo que hace el controlador del aviso, con su propia conexión y con los reintentos que Odoo le da a una
        petición que choca con otra (los errores de ``PG_CONCURRENCY_EXCEPTIONS_TO_RETRY``): cada intento usa una
        conexión nueva."""
        aviso = self._aviso(estado)
        for env in entornos:
            try:
                resultado = env['payment.transaction'].browse(self.tx_id)._dcasa_yappy_aplicar_aviso(aviso)
                if antes_de_soltar:
                    antes_de_soltar()
                env.cr.commit()
                return resultado
            except OperationalError as error:
                if not isinstance(error, PG_CONCURRENCY_EXCEPTIONS_TO_RETRY):
                    raise
                env.cr.rollback()
            finally:
                env.cr.close()
        self.fail('el aviso no se pudo aplicar ni con reintentos')

    def _esperando_candado(self):
        with self.registry.cursor() as cr:
            cr.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = 'Lock' "
                "AND query ILIKE '%%payment_transaction%%FOR UPDATE%%'", [self.registry.db_name])
            return cr.fetchone()[0]

    def _dos_avisos(self, primero, segundo):
        """El primer aviso toma el candado y NO lo suelta hasta ver que el segundo de verdad lo está esperando."""
        tiene_el_candado = threading.Event()
        errores, resultados = [], {}
        entornos_del_primero, entornos_del_segundo = self._entornos(), self._entornos()

        def uno():
            def esperar_al_otro():
                tiene_el_candado.set()
                limite = time.monotonic() + ESPERA_MAXIMA
                while time.monotonic() < limite and not self._esperando_candado():
                    time.sleep(0.05)
                resultados['hubo_espera'] = bool(self._esperando_candado())
            try:
                resultados[primero] = self._aplicar(primero, entornos_del_primero, antes_de_soltar=esperar_al_otro)
            except Exception as error:  # noqa: BLE001
                errores.append(error)

        def otro():
            try:
                tiene_el_candado.wait(ESPERA_MAXIMA)
                resultados[segundo + '_segundo'] = self._aplicar(segundo, entornos_del_segundo)
            except Exception as error:  # noqa: BLE001
                errores.append(error)

        hilos = [threading.Thread(target=uno), threading.Thread(target=otro)]
        # El segundo aviso recibe de PostgreSQL «no pude serializar» (otra transacción ganó la fila) y se reintenta: el
        # error es lo esperado y Odoo lo escribe en su registro; se silencia para que no parezca un fallo.
        with mute_logger('odoo.sql_db'):
            for hilo in hilos:
                hilo.start()
            for hilo in hilos:
                hilo.join(ESPERA_MAXIMA * 3)
        for env in (*entornos_del_primero, *entornos_del_segundo):
            env.cr.close()
        self.assertEqual(errores, [])
        self.assertTrue(
            resultados.get('hubo_espera'), 'el segundo aviso tenía que quedar ESPERANDO el candado del primero')
        return resultados

    def _estado(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            tx = env['payment.transaction'].browse(self.tx_id)
            notas = env['mail.message'].search_count([
                ('model', '=', 'sale.order'), ('res_id', '=', self.pedido_id),
                ('body', 'ilike', 'Yappy confirmó el pago de este pedido')])
            alertas = env['mail.activity'].search_count([
                ('res_model', '=', 'sale.order'), ('res_id', '=', self.pedido_id)])
            return {'estado': tx.state, 'avisos': (tx.dcasa_yappy_avisos or '').splitlines(), 'notas': notas,
                    'revision': tx.dcasa_yappy_revision, 'alertas': alertas}

    def test_dos_avisos_E_iguales_a_la_vez_pagan_una_sola_vez(self):
        self._dos_avisos('E', 'E')
        visto = self._estado()
        self.assertEqual(visto['estado'], 'done')
        self.assertEqual(len([linea for linea in visto['avisos'] if linea.startswith('E ')]), 1)
        self.assertEqual(visto['notas'], 1, 'una sola nota «Qué compró» en el pedido')
        self.assertFalse(visto['revision'])

    def test_un_E_y_un_R_a_la_vez_dejan_el_pago_y_una_alerta(self):
        """El E toma el candado primero y el R llega esperando: el pago se conserva (el R no lo deshace) y alguien lo
        mira."""
        self._dos_avisos('E', 'R')
        visto = self._estado()
        self.assertEqual(visto['estado'], 'done')
        self.assertEqual(visto['notas'], 1)
        self.assertEqual(visto['alertas'], 1, 'una alerta de que los avisos se contradicen')
        self.assertFalse(visto['revision'])

    def test_un_R_y_un_E_a_la_vez_nunca_se_pagan_solos(self):
        """El R toma el candado primero (cancela) y el E llega esperando: el dinero pudo entrar, pero un cobro que
        llega a una transacción ya cerrada NO se paga solo: queda para una persona."""
        self._dos_avisos('R', 'E')
        visto = self._estado()
        self.assertNotEqual(visto['estado'], 'done')
        self.assertTrue(visto['revision'])
        self.assertEqual(visto['notas'], 0, 'no hubo nota de pago')
