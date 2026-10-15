"""Borrar un borrador de factura aunque haya dado puntos (o comisión de vendedor).

Lo que se prueba, con la aritmética del libro a la vista:

* un borrador que dio puntos se borra, sin que nadie tenga que archivarlo; el libro no pierde ni una fila y el saldo
  sigue siendo la suma del libro;
* el cliente nuevo de prueba se queda con 0 puntos netos; el que ya tenía puntos conserva los suyos;
* el referido y los topes se deshacen bien (un bono anulado no gasta el tope de nadie);
* una factura publicada sigue sin poder borrarse, y quien no tiene permiso no anula puntos por esa puerta;
* la misma factura (o el mismo número en una factura nueva) vuelve a dar puntos si quedó pagada, una sola vez.
"""
import json
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import SociosCommon
from .test_vendedores import VendedoresCommon


class LibroCommon:
    """Ayudas para mirar el libro: nada se borra y el saldo es la suma."""

    def ids_del_libro(self, modelo='dcasa.movimiento'):
        return set(self.env[modelo].search([]).ids)

    def suma_del_libro(self, partner, modelo='dcasa.movimiento'):
        return sum(self.env[modelo].search([('partner_id', '=', partner.id)]).mapped('puntos'))

    def suma_de_la_compra(self, compra):
        """Todo lo que el libro tiene de una compra (la compra, el referido, lo descontado y sus reversos)."""
        return sum(self.env['dcasa.movimiento'].search([('compra_id', '=', compra.id)]).mapped('puntos'))

    def borrador_sin_pagar(self, partner=None, precio=50.0, vendedor=None):
        return self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': (partner or self.cliente).id,
            'invoice_date': fields.Date.today(),
            'dcasa_vendedor_id': vendedor.id if vendedor else False,
            'invoice_line_ids': [(0, 0, {'product_id': self.producto.id, 'quantity': 1, 'price_unit': precio})],
        })

    def factura_con_el_numero(self, nombre, partner=None, precio=100.0, vendedor=None):
        """Una factura nueva, pagada, que lleva un número que ya existió (una factura borrada cuyo número vuelve a
        usarse, p. ej. porque alguien lo escribe o se reinicia la secuencia)."""
        factura = self.borrador_sin_pagar(partner, precio, vendedor)
        factura.name = nombre
        factura.action_post()
        self.assertEqual(factura.name, nombre)
        self.pagar(factura)
        return factura

    def hay_clave_set_null(self, tabla):
        self.env.cr.execute("""
            SELECT confdeltype FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'f'
               AND conname = %s""", [tabla, f'{tabla}_move_id_fkey'])
        return self.env.cr.fetchone()


@tagged('post_install', '-at_install')
class TestBorrarBorradorConPuntos(LibroCommon, SociosCommon):

    # --- El caso de la dueña: pagada, vuelve a borrador, se borra ---------------------------------------------

    def test_cliente_nuevo_de_prueba_se_borra_y_queda_con_cero_puntos(self):
        factura = self.factura()
        self.assertEqual(self.cliente.dcasa_saldo, 107)
        nombre, normal = factura.name, factura.dcasa_compra_ids.factura_normal
        factura.button_draft()
        compra = factura.dcasa_compra_ids
        self.assertEqual(compra.estado, 'anulada')
        libro_antes = self.ids_del_libro()
        factura.unlink()
        self.assertFalse(factura.exists(), 'El borrador se pudo borrar')
        # La compra anulada queda en la historia, sin factura pero con su número.
        self.assertEqual((compra.estado, compra.name, compra.factura_normal), ('anulada', nombre, normal))
        self.assertFalse(compra.move_id)
        # El cliente queda con su ficha y 0 puntos netos; el libro conserva todo y el saldo es la suma.
        self.assertTrue(self.cliente.dcasa_socio_codigo)
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.assertEqual(self.suma_del_libro(self.cliente), 0)
        self.assertEqual(self.ids_del_libro(), libro_antes, 'Borrar la factura no toca el libro')
        self.assertEqual(self.suma_de_la_compra(compra), 0)

    def test_cliente_con_puntos_previos_conserva_los_suyos(self):
        anterior = self.factura()                       # 107
        factura = self.factura(precio=200.0)            # 214
        self.assertEqual(self.cliente.dcasa_saldo, 321)
        factura.button_draft()
        factura.unlink()
        self.assertEqual(self.cliente.dcasa_saldo, 107)
        self.assertEqual(self.suma_del_libro(self.cliente), 107)
        self.assertEqual(anterior.dcasa_compra_ids.estado, 'activa', 'La otra compra no se toca')

    def test_borrador_publicado_que_nunca_se_pago_se_borra(self):
        factura = self.factura(pagar=False)
        self.assertFalse(factura.dcasa_compra_ids)
        factura.button_draft()
        factura.unlink()
        self.assertFalse(factura.exists())
        self.assertFalse(self.env['dcasa.movimiento'].search([('partner_id', '=', self.cliente.id)]))
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_borrador_que_nunca_se_publico_se_borra(self):
        self.factura()                                   # el cliente ya tiene puntos
        borrador = self.borrador_sin_pagar()
        borrador.unlink()
        self.assertFalse(borrador.exists())
        self.assertEqual(self.cliente.dcasa_saldo, 107)

    def test_cancelada_y_a_borrador_tambien_se_borra(self):
        factura = self.factura()
        factura.button_cancel()
        self.assertEqual(factura.dcasa_compra_ids.estado, 'anulada')
        factura.button_draft()
        factura.unlink()
        self.assertFalse(factura.exists())
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_la_factura_publicada_y_pagada_no_se_puede_borrar(self):
        factura = self.factura()
        libro_antes = self.ids_del_libro()
        with self.assertRaises(UserError):
            factura.unlink()
        self.assertTrue(factura.exists())
        self.assertEqual(factura.state, 'posted')
        self.assertEqual(factura.dcasa_compra_ids.estado, 'activa', 'Si Odoo se niega, no se tocó ningún punto')
        self.assertEqual(self.cliente.dcasa_saldo, 107)
        self.assertEqual(self.ids_del_libro(), libro_antes)

    def test_si_una_de_varias_no_se_puede_borrar_no_se_borra_ninguna(self):
        publicada = self.factura()
        borrador = self.factura(precio=300.0)
        borrador.button_draft()
        with self.assertRaises(UserError):
            (borrador | publicada).unlink()
        self.assertTrue(borrador.exists() and publicada.exists())
        self.assertEqual(self.cliente.dcasa_saldo, 107)

    # --- Lo que todavía estaba activo se anula con asiento contrario -----------------------------------------

    def compra_activa_en_un_borrador(self, partner=None):
        """El estado raro que el borrado cuida: un borrador que aún tiene una compra activa (lo normal es que
        ``button_draft`` ya la haya anulado). Se arma volviendo a cargar la factura mientras está en borrador."""
        factura = self.factura(partner)
        factura.button_draft()
        compra = self.env['dcasa.compra']._registrar_desde_factura(factura)
        self.assertEqual(compra.estado, 'activa')
        return factura, compra

    def test_una_compra_todavia_activa_se_anula_con_asiento_contrario_y_no_traba(self):
        factura, compra = self.compra_activa_en_un_borrador()
        self.assertEqual(self.cliente.dcasa_saldo, 107)
        libro_antes = self.ids_del_libro()
        factura.unlink()
        self.assertFalse(factura.exists())
        self.assertEqual(compra.estado, 'anulada')
        self.assertTrue(compra.anulada_por_factura)
        self.assertIn('Se eliminó la factura', compra.anulada_motivo)
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.assertEqual(self.suma_del_libro(self.cliente), 0)
        self.assertEqual(self.suma_de_la_compra(compra), 0)
        nuevos = self.env['dcasa.movimiento'].search([('id', 'not in', list(libro_antes))])
        self.assertEqual(nuevos.mapped('tipo'), ['reverso'])
        self.assertTrue(libro_antes <= self.ids_del_libro(), 'Ninguna fila del libro se borró')

    def test_anular_y_borrar_dos_veces_no_devuelve_dos_veces(self):
        factura, compra = self.compra_activa_en_un_borrador()
        factura._dcasa_anular_compras('Primera vez')
        filas = self.env['dcasa.movimiento'].search_count([('compra_id', '=', compra.id)])
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        factura._dcasa_anular_compras('Segunda vez')       # ya anulada: no hace nada
        factura.unlink()                                    # y borrar tampoco vuelve a devolver
        with self.assertRaises(UserError):
            compra._anular('Tercera vez', 'test')
        self.assertEqual(self.env['dcasa.movimiento'].search_count([('compra_id', '=', compra.id)]), filas)
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.assertEqual(compra.anulada_motivo, 'Primera vez')

    def test_quien_no_puede_borrar_facturas_no_anula_puntos_por_esa_puerta(self):
        factura, compra = self.compra_activa_en_un_borrador()
        vendedora = new_test_user(self.env, login='borrar_vendedora', name='Vendedora',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        interno = new_test_user(self.env, login='borrar_bodega', name='Bodega', groups='base.group_user')
        for usuario in (vendedora, interno):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                factura.with_user(usuario).unlink()
        self.assertTrue(factura.exists())
        self.assertEqual(compra.estado, 'activa')
        self.assertEqual(self.cliente.dcasa_saldo, 107)

    # --- Referido y topes ------------------------------------------------------------------------------------

    def test_referido_se_deshace_al_borrar_y_la_siguiente_compra_real_vuelve_a_pagar(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        factura = self.factura()
        self.assertEqual((self.padrino.dcasa_saldo, self.cliente.dcasa_saldo), (500, 107 + 250))
        libro_antes = self.ids_del_libro()
        factura.button_draft()
        factura.unlink()
        self.assertEqual((self.padrino.dcasa_saldo, self.cliente.dcasa_saldo), (0, 0))
        self.assertFalse(self.cliente.dcasa_referido_pagado_en, 'El sello se suelta: la compra de verdad sí paga')
        self.assertEqual(self.cliente.dcasa_referido_por_id, self.padrino, 'El padrino se escribe una vez y se queda')
        self.assertTrue(libro_antes <= self.ids_del_libro())
        # La compra real que llega después paga el referido otra vez.
        real = self.factura()
        compra = real.dcasa_compra_ids
        self.assertEqual((compra.estado, compra.referido), ('activa', 'pagado'))
        self.assertEqual((self.padrino.dcasa_saldo, self.cliente.dcasa_saldo), (500, 107 + 250))
        for socio in (self.padrino, self.cliente):
            self.assertEqual(socio.dcasa_saldo, self.suma_del_libro(socio))

    def test_una_compra_anulada_no_gasta_el_tope_de_ahijados(self):
        otro = self.env['res.partner'].create({'name': 'Luis Real', 'phone': '6000-0003'})
        otro._dcasa_asegurar_ficha()
        self.cliente.dcasa_referido_por_id = self.padrino
        otro.dcasa_referido_por_id = self.padrino
        with self.reglas_con(referido__topeDeAhijadosPorPadrino=1):
            falsa = self.factura()
            self.assertEqual(falsa.dcasa_compra_ids.referido, 'pagado')
            falsa.button_draft()
            falsa.unlink()
            real = self.factura(otro)
            self.assertEqual(real.dcasa_compra_ids.referido, 'pagado', 'El bono deshecho no cuenta como ahijado')
            # El tope sigue mandando cuando el bono es de verdad: un tercero ya no cobra.
            tercero = self.env['res.partner'].create({'name': 'Rosa Real', 'phone': '6000-0004'})
            tercero._dcasa_asegurar_ficha()
            tercero.dcasa_referido_por_id = self.padrino
            self.assertEqual(self.factura(tercero).dcasa_compra_ids.referido, 'tope-de-ahijados')
        self.assertEqual(self.padrino.dcasa_saldo, 500)

    def test_una_compra_anulada_no_gasta_el_tope_del_mes(self):
        otro = self.env['res.partner'].create({'name': 'Luis Real', 'phone': '6000-0003'})
        otro._dcasa_asegurar_ficha()
        self.cliente.dcasa_referido_por_id = self.padrino
        otro.dcasa_referido_por_id = self.padrino
        with self.reglas_con(referido__topeDePuntosPorPadrinoAlMes=500):
            falsa = self.factura()
            self.assertEqual(falsa.dcasa_compra_ids.referido, 'pagado')
            falsa.button_draft()
            falsa.unlink()
            self.assertEqual(self.factura(otro).dcasa_compra_ids.referido, 'pagado')
        self.assertEqual(self.padrino.dcasa_saldo, 500)

    # --- Aritmética con devoluciones parciales ----------------------------------------------------------------

    def test_anular_una_compra_con_devolucion_parcial_deja_el_saldo_en_cero(self):
        factura = self.factura(precio=200.0)             # 214 puntos
        nota = factura._reverse_moves([{'ref': 'Devolución parcial'}])
        nota.invoice_line_ids.price_unit = 50.0           # devuelve $53.50 → -53
        nota.action_post()
        self.assertEqual(self.cliente.dcasa_saldo, 214 - 53)
        compra = factura.dcasa_compra_ids
        compra._anular('Se registró mal', 'test')
        self.assertEqual(self.cliente.dcasa_saldo, 0, 'Lo descontado por la devolución también se deshace')
        self.assertEqual(self.suma_de_la_compra(compra), 0)
        self.assertEqual(self.suma_del_libro(self.cliente), 0)

    # --- La misma factura (o su número) vuelve a dar puntos, una sola vez ------------------------------------

    def test_factura_corregida_y_pagada_otra_vez_da_sus_puntos_una_sola_vez(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        factura = self.factura()
        factura.button_draft()
        self.assertEqual((self.cliente.dcasa_saldo, self.padrino.dcasa_saldo), (0, 0))
        factura.action_post()                              # el pago sigue puesto: queda pagada otra vez
        self.assertEqual(factura.payment_state, 'paid')
        compras = factura.dcasa_compra_ids.sorted('id')
        self.assertEqual(compras.mapped('estado'), ['anulada', 'activa'])
        self.assertEqual((self.cliente.dcasa_saldo, self.padrino.dcasa_saldo), (107 + 250, 500))
        # Idempotente: ni el aviso de pago repetido ni publicar de nuevo suman otra vez.
        factura._invoice_paid_hook()
        self.env['dcasa.compra']._registrar_desde_factura(factura)
        self.assertEqual(len(factura.dcasa_compra_ids), 2)
        self.assertEqual((self.cliente.dcasa_saldo, self.padrino.dcasa_saldo), (107 + 250, 500))
        for socio in (self.padrino, self.cliente):
            self.assertEqual(socio.dcasa_saldo, self.suma_del_libro(socio))

    def test_desconciliar_el_pago_y_pagar_de_nuevo_da_los_puntos(self):
        factura = self.factura()
        factura.button_draft()
        factura.line_ids.remove_move_reconcile()
        factura.action_post()
        self.assertEqual(factura.payment_state, 'not_paid')
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.pagar(factura)
        self.assertEqual(factura.dcasa_compra_ids.sorted('id').mapped('estado'), ['anulada', 'activa'])
        self.assertEqual(self.cliente.dcasa_saldo, 107)

    def test_si_el_numero_de_una_factura_borrada_se_vuelve_a_usar_la_venta_nueva_da_puntos(self):
        falsa = self.factura(self.cliente)
        nombre = falsa.name
        falsa.button_draft()
        falsa.unlink()
        real = self.factura_con_el_numero(nombre, self.padrino)
        self.assertEqual(real.dcasa_compra_ids.estado, 'activa')
        self.assertEqual(self.padrino.dcasa_saldo, 107)
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_una_devolucion_total_no_reabre_la_factura(self):
        factura = self.factura()
        factura._reverse_moves([{'ref': 'Devolución'}], cancel=True)
        self.assertEqual(factura.dcasa_compra_ids.estado, 'anulada')
        self.assertFalse(factura.dcasa_compra_ids.anulada_por_factura)
        factura._invoice_paid_hook()
        self.assertEqual(factura.dcasa_compra_ids.mapped('estado'), ['anulada'])
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_una_factura_con_devolucion_publicada_no_vuelve_a_dar_puntos(self):
        factura = self.factura(precio=200.0)
        nota = factura._reverse_moves([{'ref': 'Devolución parcial'}])
        nota.invoice_line_ids.price_unit = 50.0
        nota.action_post()
        factura.button_draft()
        factura.action_post()
        self.assertEqual(factura.dcasa_compra_ids.mapped('estado'), ['anulada'])
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_una_anulacion_a_mano_no_se_reabre(self):
        factura = self.factura()
        factura.dcasa_compra_ids._anular('Factura equivocada', 'gerente')
        factura._invoice_paid_hook()
        factura.button_draft()
        factura.action_post()
        self.assertEqual(factura.dcasa_compra_ids.mapped('estado'), ['anulada'])
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_cargar_a_mano_una_factura_que_ya_dio_puntos_sigue_prohibido(self):
        factura = self.factura()
        gerente = new_test_user(self.env, login='borrar_gerente', name='Gerente',
                                groups='base.group_user,sales_team.group_sale_manager')

        def cargar_a_mano():
            wizard = self.env['dcasa.compra.manual.wizard'].with_user(gerente).create(
                {'partner_id': self.cliente.id, 'factura': factura.name, 'monto': 107.0})
            with self.assertRaisesRegex(UserError, 'ya dio puntos'):
                wizard.action_confirmar()
        cargar_a_mano()                                     # activa
        factura.button_draft()
        cargar_a_mano()                                     # anulada porque la factura se deshizo: a mano, no
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_dos_compras_activas_de_la_misma_factura_no_existen(self):
        factura = self.factura()
        with self.assertRaisesRegex(UserError, 'ya dio puntos'):
            self.env['dcasa.compra']._registrar(
                self.cliente, factura.name, 10700, self.env.user, 'test', move=factura)
        datos = {'name': factura.name, 'factura_normal': factura.dcasa_compra_ids.factura_normal,
                 'partner_id': self.cliente.id, 'monto_centavos': 10700, 'base_centavos': 10000, 'puntos': 107,
                 'reglas_version': 1}
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['dcasa.compra'].sudo().create(datos)
            self.env.flush_all()

    def test_la_clave_hacia_la_factura_ya_no_traba(self):
        self.assertEqual(self.env['dcasa.compra']._fields['move_id'].ondelete, 'set null')
        self.assertEqual(self.hay_clave_set_null('dcasa_compra'), ('n',))
        self.assertEqual(self.hay_clave_set_null('dcasa_vend_comision'), ('n',))


@tagged('post_install', '-at_install')
class TestBorrarBorradorConComision(LibroCommon, VendedoresCommon):

    def suma_vend(self, partner):
        return self.suma_del_libro(partner, 'dcasa.vend.movimiento')

    def test_borrador_con_comision_se_borra_y_el_saldo_del_vendedor_no_queda_inflado(self):
        factura = self.factura(vendedor=self.juan)        # Juan 400, y su patrocinadora Ana 40
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (400, 40))
        comisiones = factura.dcasa_vend_comision_ids
        libro_antes = self.ids_del_libro('dcasa.vend.movimiento')
        factura.button_draft()
        self.assertTrue(all(c.anulada_en for c in comisiones))
        factura.unlink()
        self.assertFalse(factura.exists())
        self.assertEqual(len(comisiones.exists()), 2, 'Las comisiones anuladas quedan en la historia')
        self.assertFalse(comisiones.move_id)
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (0, 0))
        self.assertEqual((self.suma_vend(self.juan), self.suma_vend(self.ana)), (0, 0))
        self.assertTrue(libro_antes <= self.ids_del_libro('dcasa.vend.movimiento'))
        # Sin comisión no hay nada más que arreglar en los puntos del cliente: también quedó en cero.
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_el_vendedor_con_puntos_previos_conserva_los_suyos(self):
        self.factura(vendedor=self.ana)                   # 400 de Ana
        factura = self.factura(vendedor=self.ana)
        self.assertEqual(self.ana.dcasa_vend_saldo, 800)
        factura.button_draft()
        factura.unlink()
        self.assertEqual(self.ana.dcasa_vend_saldo, 400)

    def comision_activa_en_un_borrador(self):
        factura = self.factura(vendedor=self.juan)
        factura.button_draft()
        creadas = self.env['dcasa.vend.comision']._registrar_desde_factura(factura)
        self.assertEqual(creadas.mapped('estado'), ['activa', 'activa'])
        return factura, creadas

    def test_una_comision_todavia_activa_se_anula_con_asiento_contrario_y_no_traba(self):
        factura, comisiones = self.comision_activa_en_un_borrador()
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (400, 40))
        libro_antes = self.ids_del_libro('dcasa.vend.movimiento')
        factura.unlink()
        self.assertFalse(factura.exists())
        self.assertEqual(comisiones.mapped('estado'), ['anulada', 'anulada'])
        self.assertTrue(all(c.anulada_por_factura for c in comisiones))
        self.assertIn('Se eliminó la factura', comisiones[0].anulada_motivo)
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (0, 0))
        self.assertEqual((self.suma_vend(self.juan), self.suma_vend(self.ana)), (0, 0))
        nuevos = self.env['dcasa.vend.movimiento'].search([('id', 'not in', list(libro_antes))])
        self.assertEqual(sorted(nuevos.mapped('tipo')), ['reverso', 'reverso'])
        self.assertTrue(libro_antes <= self.ids_del_libro('dcasa.vend.movimiento'))

    def test_quien_no_puede_borrar_facturas_no_anula_comisiones_por_esa_puerta(self):
        factura, comisiones = self.comision_activa_en_un_borrador()
        vendedora = new_test_user(self.env, login='borrar_comision', name='Vendedora',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        with self.assertRaises(AccessError):
            factura.with_user(vendedora).unlink()
        self.assertTrue(factura.exists())
        self.assertEqual(comisiones.mapped('estado'), ['activa', 'activa'])
        self.assertEqual(self.juan.dcasa_vend_saldo, 400)

    def test_la_factura_publicada_con_comision_no_se_puede_borrar(self):
        factura = self.factura(vendedor=self.juan)
        with self.assertRaises(UserError):
            factura.unlink()
        self.assertEqual(factura.dcasa_vend_comision_ids.mapped('estado'), ['activa', 'activa'])
        self.assertEqual(self.juan.dcasa_vend_saldo, 400)

    def test_una_comision_anulada_no_gasta_el_tope_del_mes(self):
        self.reglas['vendedores']['techos']['porVendedorAlMesPuntos'] = 400
        falsa = self.factura(vendedor=self.ana)
        self.assertEqual(falsa.dcasa_vend_comision_ids.puntos, 400)
        falsa.button_draft()
        falsa.unlink()
        real = self.factura(vendedor=self.ana)
        self.assertEqual((real.dcasa_vend_comision_ids.puntos, real.dcasa_vend_comision_ids.resultado),
                         (400, 'pagada'), 'La comisión deshecha no cuenta contra el tope del mes')
        tercera = self.factura(vendedor=self.ana)
        self.assertEqual((tercera.dcasa_vend_comision_ids.puntos, tercera.dcasa_vend_comision_ids.resultado),
                         (0, 'tope-del-mes'), 'El tope sigue mandando con lo que sí se pagó')

    def test_factura_corregida_y_pagada_otra_vez_da_la_comision_una_sola_vez(self):
        factura = self.factura(vendedor=self.juan)
        factura.button_draft()
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (0, 0))
        factura.action_post()
        self.assertEqual(factura.payment_state, 'paid')
        directas = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa').sorted('id')
        self.assertEqual(directas.mapped('estado'), ['anulada', 'activa'])
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (400, 40))
        factura._invoice_paid_hook()
        self.env['dcasa.vend.comision']._registrar_desde_factura(factura)
        self.assertEqual(len(factura.dcasa_vend_comision_ids), 4)
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (400, 40))
        for vendedor in (self.juan, self.ana):
            self.assertEqual(vendedor.dcasa_vend_saldo, self.suma_vend(vendedor))

    def test_si_el_numero_de_una_factura_borrada_se_vuelve_a_usar_la_venta_nueva_da_comision(self):
        falsa = self.factura(vendedor=self.ana)
        nombre = falsa.name
        falsa.button_draft()
        falsa.unlink()
        real = self.factura_con_el_numero(nombre, vendedor=self.ana)
        self.assertEqual(real.dcasa_vend_comision_ids.mapped('estado'), ['activa'])
        self.assertEqual(self.ana.dcasa_vend_saldo, 400)

    def test_una_devolucion_total_no_reabre_la_comision(self):
        factura = self.factura(vendedor=self.ana)
        factura._reverse_moves([{'ref': 'Devolución'}], cancel=True)
        self.assertFalse(factura.dcasa_vend_comision_ids.anulada_por_factura)
        factura._invoice_paid_hook()
        self.assertEqual(factura.dcasa_vend_comision_ids.mapped('estado'), ['anulada'])
        self.assertEqual(self.ana.dcasa_vend_saldo, 0)

    def test_anular_una_comision_con_devolucion_parcial_deja_el_saldo_en_cero(self):
        factura = self.factura(vendedor=self.ana)         # 400
        nota = factura._reverse_moves([{'ref': 'Devolución parcial'}])
        nota.invoice_line_ids.price_unit = 25.0           # $25 de $100 neto → -100
        nota.action_post()
        self.assertEqual(self.ana.dcasa_vend_saldo, 300)
        factura.dcasa_vend_comision_ids._anular('Vendedor equivocado', 'prueba')
        self.assertEqual(self.ana.dcasa_vend_saldo, 0)
        self.assertEqual(self.suma_vend(self.ana), 0)

    def test_dos_comisiones_activas_de_la_misma_factura_no_existen(self):
        factura = self.factura(vendedor=self.ana)
        self.assertFalse(self.env['dcasa.vend.comision']._registrar_desde_factura(factura))
        comision = factura.dcasa_vend_comision_ids
        datos = {'name': comision.name, 'factura_normal': comision.factura_normal, 'partner_id': self.ana.id,
                 'tipo': 'directa', 'neto_centavos': 10000, 'puntos': 400, 'resultado': 'pagada',
                 'reglas_version': 1}
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['dcasa.vend.comision'].sudo().create(datos)
            self.env.flush_all()


@tagged('post_install', '-at_install')
class TestAvisoDelPagoSinAplicar(LibroCommon, SociosCommon):
    """Al devolver a borrador una factura con pago (y al borrarla) se avisa dónde cancelar el pago. El aviso nunca
    cambia ni hace fallar lo que hacen los botones."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contador = new_test_user(cls.env, login='aviso_contador', name='Contadora',
                                     groups='base.group_user,account.group_account_invoice')

    def avisos(self, desde=0):
        """Los avisos emergentes que salieron por el bus después de ``desde``: ``[(canal, contenido)]``."""
        self.env.flush_all()
        self.env.cr.precommit.run()
        salida = []
        for fila in self.env['bus.bus'].sudo().search([('id', '>', desde)], order='id'):
            mensaje = json.loads(fila.message)
            if mensaje['type'] == 'simple_notification':
                salida.append((json.loads(fila.channel), mensaje['payload']))
        return salida

    def cuantos(self):
        """Hasta qué fila del bus hay hoy (para mirar solo lo que salga después)."""
        self.env.flush_all()
        self.env.cr.precommit.run()
        return max(self.env['bus.bus'].sudo().search([], order='id desc', limit=1).ids or [0])

    def ruta(self):
        menu = self.env.ref('account.menu_action_account_payments_receivable')
        return ' › '.join(menu.complete_name.split('/'))

    def test_el_menu_de_pagos_existe_y_la_ruta_sale_de_el(self):
        menu = self.env.ref('account.menu_action_account_payments_receivable')
        self.assertEqual(menu.action.res_model, 'account.payment', 'Es la lista de pagos de clientes')
        self.assertEqual(self.env['account.move']._dcasa_ruta_de_pagos(), self.ruta())
        self.assertTrue(self.ruta().endswith(menu.name) and ' › ' in self.ruta())

    def test_volver_a_borrador_con_pago_avisa_a_quien_lo_hizo(self):
        factura = self.factura()
        pago = factura._get_reconciled_payments()
        self.assertEqual(len(pago), 1)
        antes = self.cuantos()
        resultado = factura.with_user(self.contador).button_draft()
        self.assertTrue(resultado, 'El botón hace lo de siempre')
        self.assertEqual(factura.state, 'draft')
        self.assertEqual(factura.dcasa_compra_ids.estado, 'anulada')
        # Al volver a borrador el pago sigue ligado: el aviso lo dice así, no promete lo que aún no pasó.
        self.assertEqual(factura._get_reconciled_payments(), pago)
        (canal, contenido), = self.avisos(antes)
        self.assertEqual(canal[1:], ['res.partner', self.contador.partner_id.id], 'Le llega a quien lo hizo')
        self.assertEqual((contenido['type'], contenido['sticky']), ('warning', True))
        for texto in (pago.name, factura.name, self.ruta(), 'sigue ligado', 'queda sin aplicar', 'Si era de prueba'):
            self.assertIn(texto, contenido['message'])
        # El rastro queda en la factura y en el pago.
        for nota in (factura.message_ids[:1], pago.message_ids[:1]):
            for texto in (pago.name, factura.name, self.ruta()):
                self.assertIn(texto, nota.body)

    def test_sin_pago_no_hay_aviso(self):
        factura = self.factura(pagar=False)
        notas = len(factura.message_ids)
        antes = self.cuantos()
        self.assertTrue(factura.button_draft())
        self.assertFalse(self.avisos(antes))
        self.assertEqual(len(factura.message_ids), notas, 'Tampoco deja nota')

    def test_dos_pagos_se_listan_en_el_mismo_aviso(self):
        factura = self.factura(pagar=False)
        for monto in (50.0, 57.0):
            self.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=factura.ids,
            ).create({'payment_date': factura.invoice_date, 'amount': monto})._create_payments()
        pagos = factura._get_reconciled_payments()
        self.assertEqual(len(pagos), 2)
        antes = self.cuantos()
        factura.button_draft()
        (_canal, contenido), = self.avisos(antes)
        for pago in pagos:
            self.assertIn(pago.name, contenido['message'])
        self.assertIn('Los pagos', contenido['message'])
        self.assertIn('cancélalos', contenido['message'])

    def test_un_borrado_de_muchas_facturas_no_llena_la_pantalla_de_avisos(self):
        facturas = self.factura() | self.factura() | self.factura() | self.factura()
        antes = self.cuantos()
        facturas.button_draft()
        self.assertEqual(len(self.avisos(antes)), 3, 'Hay un tope de avisos por acción')
        for factura in facturas:
            self.assertIn('sigue ligado', factura.message_ids[:1].body, 'Pero cada factura deja su nota')

    def test_si_el_aviso_falla_el_boton_hace_lo_de_siempre(self):
        factura = self.factura()
        antes = self.cuantos()
        with patch.object(type(self.env['account.move']), '_dcasa_ruta_de_pagos', side_effect=RuntimeError('boom')), \
                self.assertLogs('odoo.addons.dcasa_socios.models.account_move', 'ERROR'):
            self.assertTrue(factura.button_draft())
        self.assertEqual(factura.state, 'draft')
        self.assertEqual(factura.dcasa_compra_ids.estado, 'anulada')
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.assertFalse(self.avisos(antes))
        # ...y la factura sigue pudiéndose borrar.
        factura.unlink()
        self.assertFalse(factura.exists())

    def test_si_no_se_pueden_ver_los_pagos_el_boton_tampoco_falla(self):
        factura = self.factura()
        with patch.object(type(self.env['account.move']), '_get_reconciled_payments',
                          side_effect=RuntimeError('boom')), \
                self.assertLogs('odoo.addons.dcasa_socios.models.account_move', 'ERROR'):
            self.assertTrue(factura.button_draft())
        self.assertEqual(factura.state, 'draft')

    def test_cancelar_una_factura_sin_pago_o_con_el_boton_de_siempre_no_cambia(self):
        factura = self.factura(pagar=False)
        antes = self.cuantos()
        factura.button_cancel()
        self.assertEqual(factura.state, 'cancel')
        self.assertFalse(self.avisos(antes))

    def test_borrar_el_borrador_despues_sigue_funcionando_y_avisa_que_el_pago_quedo_sin_aplicar(self):
        factura = self.factura()
        pago = factura._get_reconciled_payments()
        nombre = factura.name
        factura.button_draft()
        antes = self.cuantos()
        libro_antes = self.ids_del_libro()
        factura.with_user(self.contador).unlink()
        self.assertFalse(factura.exists())
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.assertTrue(libro_antes <= self.ids_del_libro())
        # El pago existe y ya no está aplicado a ninguna factura.
        self.assertTrue(pago.exists())
        self.assertFalse(pago.reconciled_invoice_ids)
        (canal, contenido), = self.avisos(antes)
        self.assertEqual(canal[1:], ['res.partner', self.contador.partner_id.id])
        self.assertEqual((contenido['type'], contenido['sticky']), ('warning', True))
        for texto in (pago.name, nombre, self.ruta(), 'quedó sin aplicar'):
            self.assertIn(texto, contenido['message'])
        self.assertIn('quedó sin aplicar', pago.message_ids[:1].body)

    def test_borrar_un_borrador_sin_pago_no_avisa(self):
        borrador = self.borrador_sin_pagar()
        antes = self.cuantos()
        borrador.unlink()
        self.assertFalse(borrador.exists())
        self.assertFalse(self.avisos(antes))

    def test_la_factura_publicada_y_pagada_sigue_sin_borrarse_y_sin_aviso(self):
        factura = self.factura()
        antes = self.cuantos()
        with self.assertRaises(UserError):
            factura.unlink()
        self.assertTrue(factura.exists())
        self.assertFalse(self.avisos(antes))
