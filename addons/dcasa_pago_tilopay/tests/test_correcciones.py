"""Las correcciones de la revisión independiente (RV-1 a RV-10, 2026-11-19) que no cubren sus propias pruebas
(``test_revision.py``): el aviso a Gerencia, el reintento de lo rechazado, el ritmo de la tarea programada, los topes y
los montos de más de mil dólares."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_pago_tilopay.models import payment_transaction as modulo_tx
from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from .common import ComunTilopay, SimuladorTilopay, entorno

RESUMEN_TOTAL = 'Tilopay: cobro que no cuadra con el pedido'
RESUMEN_MUERTO = 'Tilopay: cobro de un pedido que ya no está vivo'


class BaseCorreccion(ComunTilopay, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(
            cls.env, login='til_gerencia_rv', groups='base.group_user,dcasa_base.group_gerencia')

    def cron(self):
        return self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()

    def actividades(self, pedido, resumen=None):
        """Las actividades de Tilopay del pedido (todas, o las de ese resumen)."""
        dominio = [('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id), ('summary', 'like', 'Tilopay')]
        if resumen:
            dominio.append(('summary', '=', resumen))
        return self.env['mail.activity'].sudo().search(dominio)

    def notas(self, pedido, *palabras):
        nota = self.env.ref('mail.mt_note')
        return pedido.message_ids.filtered(
            lambda m: m.subtype_id == nota and all(p.lower() in (m.body or '').lower() for p in palabras))

    def consultas_hechas(self, tilopay):
        return len(tilopay.rutas(api.RUTA_CONSULTA))


@tagged('post_install', '-at_install')
class TestSoloElEquipoAbreLoQueNoSePublico(BaseCorreccion):
    """RV-1: Odoo solo filtra por «Publicado» al MOSTRAR; abrir la página a mano (mandando el número del proveedor) lo
    tiene que impedir el propio proveedor."""

    def abrir_como(self, usuario, pedido):
        tx = self.transaccion(pedido)
        return tx, tx.with_user(usuario).sudo()._get_processing_values()

    def test_sin_publicar_un_visitante_no_abre_la_pagina_pero_el_equipo_si(self):
        self.proveedor.is_published = False
        publico = self.env.ref('base.public_user')
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            with self.assertRaises(ValidationError):
                self.abrir_como(publico, pedido)
            self.assertEqual(tilopay.rutas(api.RUTA_PAGO), [], 'ni se le pidió una página a Tilopay')
            tx, valores = self.abrir_como(self.gerencia, pedido)
            self.assertTrue(tx.dcasa_tilopay_orden)
            self.assertIn('redirect_form_html', valores)
            self.assertEqual(len(tilopay.rutas(api.RUTA_PAGO)), 1)

    def test_publicado_el_visitante_si_paga(self):
        self.proveedor.is_published = True
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, _valores = self.abrir_como(self.env.ref('base.public_user'), pedido)
            self.assertEqual(len(tilopay.rutas(api.RUTA_PAGO)), 1)
        self.assertTrue(tx.dcasa_tilopay_orden)

    def test_un_pago_de_prueba_deja_la_marca_en_el_pedido_y_uno_real_no(self):
        """RV-9: el pedido confirmado con una tarjeta de prueba lo dice; con dinero real no hay nota de prueba."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        self.assertTrue(self.notas(pedido, 'tarjeta de PRUEBA'))
        self.assertFalse(tx.is_live)


@tagged('post_install', '-at_install')
class TestElPedidoCambioMientrasPagaba(BaseCorreccion):
    """RV-2 y RV-2b: lo cobrado tiene que ser lo que vale el pedido AHORA; si no, el dinero entró y no se paga solo."""

    def cobrar_con_el_pedido_cambiado(self, cantidad_nueva, cantidad_inicial=1):
        pedido = self.pedido(cantidad=cantidad_inicial)
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            cobrado = pedido.amount_total
            pedido.order_line.product_uom_qty = cantidad_nueva
            tilopay.aprobar(orden, cobrado)
            veredicto = tx._dcasa_tilopay_confirmar('retorno')
        return pedido, tx, orden, tilopay, cobrado, veredicto

    def test_no_se_paga_cierra_con_mensaje_claro_y_avisa_a_gerencia(self):
        pedido, tx, _orden, _tilopay, cobrado, veredicto = self.cobrar_con_el_pedido_cambiado(5)
        self.assertEqual(veredicto, api.TOTAL_PEDIDO)
        self.assertEqual(tx.state, 'error')
        self.assertIn('Tu pedido cambió mientras pagabas', tx.state_message)
        self.assertEqual(tx.dcasa_tilopay_veredicto, api.TOTAL_PEDIDO)
        tx._post_process()
        self.assertNotEqual(pedido.state, 'sale', 'el pedido no se confirma con el total nuevo')
        self.assertTrue(self.notas(pedido, 'Tilopay cobró', 'cambió mientras el cliente pagaba'))
        actividades = self.actividades(pedido, RESUMEN_TOTAL)
        self.assertIn(self.gerencia, actividades.user_id, 'la actividad le llega a Gerencia')
        self.assertIn(f'{cobrado:.2f}', actividades[0].note)

    def test_si_el_total_baja_tambien_se_avisa_que_se_cobro_de_mas(self):
        pedido, tx, _orden, _tilopay, _cobrado, veredicto = self.cobrar_con_el_pedido_cambiado(1, cantidad_inicial=3)
        self.assertEqual(veredicto, api.TOTAL_PEDIDO)
        self.assertEqual(tx.state, 'error')
        self.assertTrue(self.actividades(pedido, RESUMEN_TOTAL))

    def test_volver_a_preguntar_no_repite_la_nota_ni_la_actividad(self):
        pedido, tx, _orden, tilopay, _cobrado, _veredicto = self.cobrar_con_el_pedido_cambiado(5)
        notas_antes = len(self.notas(pedido, 'Tilopay cobró'))
        with tilopay:
            for _i in range(3):
                tx.dcasa_tilopay_consulta = False
                self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.TOTAL_PEDIDO)
        self.assertEqual(len(self.notas(pedido, 'Tilopay cobró')), notas_antes)
        propias = self.actividades(pedido, RESUMEN_TOTAL).filtered(lambda a: a.user_id == self.gerencia)
        self.assertEqual(len(propias), 1, 'una sola actividad por persona, por más consultas que haya')

    def test_si_el_pedido_vuelve_a_valer_lo_cobrado_no_se_paga_solo(self):
        """N-6: el equipo pudo devolver el cobro en el panel de Tilopay; dar por pagado un cobro ya devuelto es peor que
        esperar. Queda marcado para que lo resuelva una persona."""
        pedido, tx, _orden, tilopay, _cobrado, _veredicto = self.cobrar_con_el_pedido_cambiado(5)
        self.assertTrue(tx.dcasa_tilopay_revision)
        pedido.order_line.product_uom_qty = 1
        with tilopay:
            tx.dcasa_tilopay_consulta = False
            self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.TOTAL_PEDIDO)
        self.assertEqual(tx.state, 'error')
        tx._post_process()
        self.assertNotEqual(pedido.state, 'sale')

    def test_la_ultima_puerta_si_cambia_entre_el_pago_y_la_tarea_del_cierre(self):
        """El total coincidía al consultar (la transacción quedó pagada) pero cambia antes de que Odoo termine el
        trabajo: el pedido no se confirma solo y Gerencia se entera. El dinero ya entró."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), api.APROBADO)
        self.assertEqual(tx.state, 'done')
        pedido.order_line.product_uom_qty = 5
        tx._post_process()
        self.assertNotEqual(pedido.state, 'sale')
        self.assertTrue(self.actividades(pedido, RESUMEN_TOTAL))
        self.assertTrue(self.notas(pedido, 'NO se confirmó solo'))

    def test_con_el_total_igual_no_hay_actividad_de_mas(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')
        self.assertFalse(self.actividades(pedido))


@tagged('post_install', '-at_install')
class TestPedidoCanceladoPagado(BaseCorreccion):
    """RV-4: dinero de un pedido que ya no está vivo."""

    def test_el_equipo_recibe_nota_y_actividad(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            pedido._action_cancel()
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        self.assertEqual(pedido.state, 'cancel')
        self.assertTrue(self.notas(pedido, 'cancelado', 'el dinero entró'))
        self.assertIn(self.gerencia, self.actividades(pedido, RESUMEN_MUERTO).user_id)

    def test_un_pedido_vivo_no_levanta_ese_aviso(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        self.assertFalse(self.actividades(pedido, RESUMEN_MUERTO))

    def test_un_pedido_ya_confirmado_si_se_puede_pagar(self):
        """El cliente paga después de que el pedido se confirmó (p. ej. «pago al recibir» que cambió a tarjeta)."""
        pedido = self.pedido()
        pedido.action_confirm()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), api.APROBADO)
        self.assertEqual(tx.state, 'done')


@tagged('post_install', '-at_install')
class TestLoCerradoSeRevisaDeNuevo(BaseCorreccion):
    """RV-5: error y cancelada se vuelven a preguntar, menos seguido y por pocos días."""

    def cerrada(self, tilopay, estado, **delta):
        pedido = self.pedido()
        tx, orden = self.abrir(tilopay, pedido)
        if estado == 'error':
            tilopay.rechazar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        else:
            tx._dcasa_tilopay_confirmar('retorno', navegador_cancelo=True)
        self.assertEqual(tx.state, estado)
        tx.dcasa_tilopay_senal = False           # el retorno que la cerró ya se atendió: sin señal pendiente
        self.envejecer(tx, **delta)
        return pedido, tx, orden

    def test_cada_tres_horas_y_solo_tres_dias(self):
        for estado in ('error', 'cancel'):
            with self.subTest(estado=estado), SimuladorTilopay() as tilopay:
                _pedido, tx, _orden = self.cerrada(tilopay, estado, hours=5)
                antes = self.consultas_hechas(tilopay)
                tx.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(hours=1)
                self.assertEqual(self.cron(), 0, 'se preguntó hace una hora: todavía no toca')
                tx.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(hours=4)
                self.assertEqual(self.cron(), 1)
                self.assertEqual(self.consultas_hechas(tilopay), antes + 1)
                self.envejecer(tx, days=4)
                tx.dcasa_tilopay_consulta = False
                self.assertEqual(self.cron(), 0, 'pasados los 3 días ya no se pregunta')

    def test_el_pago_que_llego_despues_de_un_rechazo_se_recupera_y_deja_nota(self):
        with SimuladorTilopay() as tilopay:
            pedido, tx, orden = self.cerrada(tilopay, 'error', minutes=30)
            tilopay.aprobar(orden, pedido.amount_total)
            tx.dcasa_tilopay_consulta = False
            self.assertEqual(self.cron(), 1)
        self.assertEqual(tx.state, 'done')
        self.assertTrue(self.notas(pedido, 'llegó después de marcarse «error»'))

    def test_un_rechazo_que_sigue_siendo_rechazo_no_repite_la_nota(self):
        with SimuladorTilopay() as tilopay:
            pedido, tx, _orden = self.cerrada(tilopay, 'error', minutes=30)
            notas = len(self.notas(pedido, 'no aprobó'))
            for _i in range(3):
                tx.dcasa_tilopay_consulta = False
                self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.RECHAZADO)
        self.assertEqual(tx.state, 'error')
        self.assertEqual(len(self.notas(pedido, 'no aprobó')), notas)

    def test_un_estado_intermedio_queda_pendiente_y_se_recupera(self):
        """Supuesto 3: un Yappy que todavía no responde (código no numérico) no se vuelve «error»."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.envejecer(tx, minutes=10)
            tilopay.pagos[orden] = [tilopay.fila(orden, pedido.amount_total, code='pendiente')]
            self.assertEqual(self.cron(), 1)
            self.assertEqual(tx.state, 'draft', 'sigue esperando; no es un rechazo')
            self.assertFalse(self.notas(pedido, 'no aprobó'))
            tilopay.pagos[orden] = [tilopay.fila(orden, pedido.amount_total)]
            tx.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(minutes=9)
            self.assertEqual(self.cron(), 1)
        self.assertEqual(tx.state, 'done')


@tagged('post_install', '-at_install')
class TestRitmoYTopesDeLaTarea(BaseCorreccion):
    """RV-3: la tarea que rescata pagos no se deja sin servicio y no gasta de más la cuenta de Tilopay."""

    def test_lo_reciente_cada_8_minutos_lo_viejo_cada_hora_o_cada_3_si_tilopay_nunca_lo_vio(self):
        with SimuladorTilopay() as tilopay:
            reciente, _o1 = self.abrir(tilopay)
            viejo, _o2 = self.abrir(tilopay)
            abandonado, _o3 = self.abrir(tilopay)
            self.envejecer(reciente, minutes=10)
            self.envejecer(viejo, hours=2)
            self.envejecer(abandonado, hours=2)
            ahora = fields.Datetime.now()
            viejo.dcasa_tilopay_veredicto = api.PENDIENTE            # Tilopay ya tiene una fila de esa orden
            abandonado.dcasa_tilopay_veredicto = api.SIN_REGISTRO   # Tilopay nunca ha visto nada
            reciente.dcasa_tilopay_consulta = ahora - timedelta(minutes=5)
            viejo.dcasa_tilopay_consulta = ahora - timedelta(minutes=30)
            abandonado.dcasa_tilopay_consulta = ahora - timedelta(minutes=90)
            self.assertEqual(self.cron(), 0)
            reciente.dcasa_tilopay_consulta = ahora - timedelta(minutes=9)
            self.assertEqual(self.cron(), 1)
            viejo.dcasa_tilopay_consulta = ahora - timedelta(minutes=61)
            self.assertEqual(self.cron(), 1)
            abandonado.dcasa_tilopay_consulta = ahora - timedelta(minutes=181)
            self.assertEqual(self.cron(), 1)

    def test_la_que_lleva_mas_tiempo_esperando_va_primero_aunque_haya_nuevas(self):
        """Las nuevas (nunca consultadas) no se cuelan delante de la que ya esperaba."""
        with SimuladorTilopay() as tilopay:
            esperando, _o = self.abrir(tilopay)
            self.envejecer(esperando, minutes=30)
            esperando.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(minutes=20)
            for _i in range(4):
                nueva, _on = self.abrir(tilopay)
                self.envejecer(nueva, minutes=5)
            primeras = self.env['payment.transaction']._dcasa_tilopay_pendientes(
                self.proveedor, fields.Datetime.now(), [], 2)
        self.assertEqual(primeras[0], esperando)

    def test_trabaja_por_lotes_hasta_acabar(self):
        with SimuladorTilopay() as tilopay:
            txs = []
            for _i in range(7):
                tx, _o = self.abrir(tilopay)
                self.envejecer(tx, minutes=10)
                txs.append(tx)
            tilopay.llamadas.clear()
            revisadas = self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar(limite=3)
            self.assertEqual(revisadas, 7, 'tres lotes: 3 + 3 + 1')
            self.assertEqual(self.consultas_hechas(tilopay), 7)
            self.assertEqual(self.cron(), 0, 'lo recién preguntado no se vuelve a preguntar en la misma vuelta')

    def test_si_tilopay_no_contesta_tres_veces_seguidas_se_para(self):
        with SimuladorTilopay() as tilopay:
            for _i in range(8):
                tx, _o = self.abrir(tilopay)
                self.envejecer(tx, minutes=10)
            tilopay.llamadas.clear()
            tilopay.falla = 'red'
            with self.assertLogs('odoo.addons.dcasa_pago_tilopay', 'WARNING') as registros:
                self.cron()
            self.assertEqual(len(tilopay.llamadas), 3, 'tres intentos y a esperar la próxima vuelta')
            self.assertTrue(any('no contestó 3 veces seguidas' in linea for linea in registros.output))
            tilopay.falla = None
            api.olvidar_tokens()
            self.assertEqual(self.cron(), 5, 'al volver Tilopay se atiende el resto; las tres que fallaron esperan')

    def test_respeta_el_presupuesto_de_tiempo(self):
        with SimuladorTilopay() as tilopay:
            tx, _o = self.abrir(tilopay)
            self.envejecer(tx, minutes=10)
            tilopay.llamadas.clear()
            with patch.object(modulo_tx, 'PRESUPUESTO_DEL_CRON', 0):
                self.assertEqual(self.cron(), 0)
            self.assertEqual(tilopay.llamadas, [])

    def test_tope_global_de_paginas_abiertas_por_hora(self):
        with SimuladorTilopay() as tilopay, patch.object(modulo_tx, 'TOPE_PAGINAS_POR_HORA', 3):
            for _i in range(3):
                self.abrir(tilopay)
            llamadas = len(tilopay.rutas(api.RUTA_PAGO))
            with self.assertRaises(ValidationError) as error:
                self.abrir(tilopay)           # otro pedido: el tope por pedido (5) no es el que frena
            self.assertIn('Hay muchos pagos en curso', str(error.exception))
            self.assertEqual(len(tilopay.rutas(api.RUTA_PAGO)), llamadas, 'no se le pidió una página de más a Tilopay')

    def test_las_paginas_de_hace_mas_de_una_hora_no_cuentan_para_el_tope(self):
        with SimuladorTilopay() as tilopay, patch.object(modulo_tx, 'TOPE_PAGINAS_POR_HORA', 2):
            for _i in range(2):
                tx, _o = self.abrir(tilopay)
                self.envejecer(tx, minutes=61)
            tx, _o = self.abrir(tilopay)
            self.assertTrue(tx.dcasa_tilopay_orden)


@tagged('post_install', '-at_install')
class TestMontosDeMasDeMilDolares(BaseCorreccion):
    """Supuesto 2: «1,250.00» con coma de miles no deja un cobro real como «cobro distinto»."""

    def pedido_grande(self):
        pedido = self.pedido(cantidad=10)
        self.assertGreater(pedido.amount_total, 1000)
        return pedido

    def test_con_coma_de_miles_se_paga(self):
        pedido = self.pedido_grande()
        total = Decimal(str(pedido.amount_total))
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.assertEqual(tx.amount, pedido.amount_total)
            tilopay.aprobar(orden, pedido.amount_total, amount=f'{total:,.2f}')
            self.assertIn(',', tilopay.pagos[orden][0]['amount'])
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), api.APROBADO)
        self.assertEqual(tx.state, 'done')

    def test_una_forma_rara_no_paga_y_avisa(self):
        pedido = self.pedido_grande()
        total = Decimal(str(pedido.amount_total))
        europeo = f'{total:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total, amount=europeo)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), api.MONTO)
        self.assertEqual(tx.state, 'error')
        self.assertTrue(self.notas(pedido, 'algo distinto al pedido'))

    def test_la_orden_lleva_el_monto_sin_coma(self):
        """Lo que mandamos a Tilopay es siempre «1070.00»: sin coma de miles."""
        pedido = self.pedido_grande()
        with SimuladorTilopay() as tilopay:
            self.abrir(tilopay, pedido)
            enviado = tilopay.rutas(api.RUTA_PAGO)[-1][1]['amount']
        self.assertNotIn(',', enviado)
        self.assertEqual(Decimal(enviado), Decimal(str(pedido.amount_total)))


@tagged('post_install', '-at_install')
class TestApartadoYEntornoDelServidor(BaseCorreccion):

    def test_un_pedido_pagado_con_tilopay_no_queda_como_apartado(self):
        """RV-6, también cuando la cotización ya estaba enviada (así nace el apartado)."""
        pedido = self.pedido()
        pedido.action_quotation_sent()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')
        if 'dcasa_apartado_vence' in pedido._fields:
            self.assertFalse(pedido.dcasa_apartado_vence)

    def test_un_servidor_que_no_es_de_produccion_dice_por_que(self):
        """RV-8: el aviso de la pantalla explica que aquí Tilopay solo cobra en prueba."""
        self.proveedor.state = 'enabled'
        with entorno(TILOPAY_ENTORNO='produccion', DCASA_ENTORNO='staging'):
            self.proveedor.invalidate_recordset()
            self.assertFalse(self.proveedor._dcasa_tilopay_ofrecible())
            self.assertIn('no es el de producción', self.proveedor.dcasa_tilopay_aviso)
