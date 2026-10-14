"""El programa de vendedores: afiliación, colmena de un nivel, comisiones, antifraude, anulaciones y canje."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import SociosCommon


class VendedoresCommon(SociosCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerente = new_test_user(cls.env, login='vend_gerente',
                                    groups='sales_team.group_sale_manager,account.group_account_invoice')
        cls.mostrador = new_test_user(cls.env, login='vend_mostrador',
                                      groups='sales_team.group_sale_salesman,account.group_account_invoice')

    def setUp(self):
        super().setUp()
        self.activar_vendedores()
        self.ana = self.vendedor('Ana Vendedora', '8-111-111', '6100-0001')
        self.juan = self.vendedor('Juan Directo', '8-222-222', '6100-0002', patrocinador=self.ana)

    def ayer(self):
        return fields.Datetime.now() - timedelta(days=1)

    def dar_puntos_disponibles(self, vendedor, puntos):
        """Puntos ya liberados (como si hubieran pasado la ventana de devoluciones)."""
        return self.env['dcasa.vend.movimiento']._asentar(
            vendedor, 'ajuste', puntos, 'prueba', motivo='Saldo de prueba', disponible_desde=self.ayer())


@tagged('post_install', '-at_install')
class TestAfiliacion(VendedoresCommon):

    def test_afiliar_da_codigo_abre_la_ficha_de_socio_y_deja_rastro(self):
        self.assertRegex(self.ana.dcasa_vendedor_codigo, r'^VEN[2-9A-HJKMNP-Z]{6}$')
        self.assertEqual(self.ana.dcasa_vendedor_estado, 'activo')
        self.assertEqual(self.ana.dcasa_vendedor_tipo, 'externo')
        self.assertEqual(self.ana.dcasa_vend_terminos_version, 1)
        self.assertTrue(self.ana.dcasa_socio_codigo, 'La misma ficha entra a /socios con su celular')
        self.assertEqual(self.ana.dcasa_celular, '61000001')
        self.assertEqual(self.ana.dcasa_vendedor_afiliado_por, 'prueba')
        self.assertIn('Afiliado como vendedor', self.ana.message_ids[:1].body)

    def test_sin_cedula_sin_celular_o_sin_terminos_no_se_afilia(self):
        Partner = self.env['res.partner']
        sin_cedula = Partner.create({'name': 'Sin Cédula', 'phone': '6100-0010'})
        with self.assertRaisesRegex(UserError, 'cédula o RUC'):
            sin_cedula._dcasa_afiliar_vendedor('externo', acepto_terminos=True)
        sin_celular = Partner.create({'name': 'Sin Celular', 'vat': '8-333-333'})
        with self.assertRaisesRegex(UserError, 'celular'):
            sin_celular._dcasa_afiliar_vendedor('externo', acepto_terminos=True)
        completa = Partner.create({'name': 'Completa', 'vat': '8-444-444', 'phone': '6100-0011'})
        with self.assertRaisesRegex(UserError, 'términos'):
            completa._dcasa_afiliar_vendedor('externo', acepto_terminos=False)
        with self.assertRaisesRegex(UserError, 'empleado o persona de afuera'):
            completa._dcasa_afiliar_vendedor('otro', acepto_terminos=True)
        self.assertFalse(completa.dcasa_vendedor_codigo)

    def test_ya_es_vendedor(self):
        with self.assertRaisesRegex(UserError, 'ya es vendedor'):
            self.ana._dcasa_afiliar_vendedor('externo', acepto_terminos=True)

    def test_el_patrocinador_se_escribe_una_vez_y_no_se_cambia(self):
        self.assertEqual(self.juan.dcasa_vendedor_patrocinador_id, self.ana)
        otra = self.vendedor('Otra Vendedora', '8-555-555', '6100-0003')
        with self.assertRaisesRegex(UserError, 'no se cambia nunca'):
            self.juan.write({'dcasa_vendedor_patrocinador_id': otra.id})
        with self.assertRaisesRegex(UserError, 'no se borra'):
            self.juan.write({'dcasa_vendedor_patrocinador_id': False})

    def test_nadie_se_patrocina_a_si_mismo_ni_se_cierra_un_circulo(self):
        with self.assertRaisesRegex(UserError, 'sí mismo'):
            self.ana._dcasa_validar_patrocinador(self.ana, self.ana)
        # Ana → Juan: no se puede hacer que Ana sea patrocinada por Juan (círculo).
        with self.assertRaisesRegex(ValidationError, 'círculo'):
            self.ana.write({'dcasa_vendedor_patrocinador_id': self.juan.id})

    def test_quien_patrocina_tiene_que_ser_un_vendedor_activo(self):
        persona = self.env['res.partner'].create({'name': 'Nueva', 'vat': '8-666-666', 'phone': '6100-0004'})
        cliente = self.env['res.partner'].create({'name': 'Cliente Común', 'phone': '6100-0005'})
        with self.assertRaisesRegex(UserError, 'vendedor activo'):
            persona._dcasa_afiliar_vendedor('externo', cliente, acepto_terminos=True)
        self.ana.action_dcasa_suspender_vendedor()
        self.env.invalidate_all()
        # Suspender exige Gerencia: el superusuario de las pruebas pasa; la persona se vuelve a probar.
        with self.assertRaisesRegex(UserError, 'vendedor activo'):
            persona._dcasa_afiliar_vendedor('externo', self.ana, acepto_terminos=True)

    def test_tope_de_directos_por_colmena(self):
        self.reglas['vendedores']['patrocinio']['topeDeDirectos'] = 2
        self.vendedor('Directo Dos', '8-777-777', '6100-0006', patrocinador=self.ana)
        with self.assertRaisesRegex(UserError, 'máximo de una colmena'):
            self.vendedor('Directo Tres', '8-888-888', '6100-0007', patrocinador=self.ana)
        self.assertEqual(self.ana.dcasa_vend_directos_count, 2)

    def test_la_colmena_no_tiene_mas_de_un_nivel_de_pago_pero_si_puede_crecer(self):
        luis = self.vendedor('Luis Del Directo', '8-999-999', '6100-0008', patrocinador=self.juan)
        self.assertEqual(luis.dcasa_vendedor_patrocinador_id, self.juan)
        self.assertEqual(self.ana.dcasa_vend_directos_count, 1, 'Luis no cuenta como directo de Ana')

    def test_quien_comparte_datos_con_el_patrocinador_no_puede_ser_su_directo(self):
        # Misma cédula: el candado de contactos impide crear la ficha, así que se prueba la regla sobre registros
        # sin guardar (lo que importa es la regla, no el candado).
        Partner = self.env['res.partner']
        igual = Partner.new({'name': 'Otra Ana', 'vat': '8111111', 'phone': '6100-9999'})
        self.assertTrue(self.ana._dcasa_es_la_misma_persona(igual), 'La cédula sin guiones es la misma')
        celular = Partner.new({'name': 'Mismo Cel', 'phone': '+507 6100-0001'})
        self.assertTrue(self.ana._dcasa_es_la_misma_persona(celular))
        correo = Partner.new({'name': 'Mismo Correo', 'email': 'ANA@correo.com'})
        self.ana.email = 'ana@correo.com'
        self.assertTrue(self.ana._dcasa_es_la_misma_persona(correo))
        distinta = Partner.new({'name': 'Distinta', 'vat': '8-000-000', 'phone': '6100-4444', 'email': 'd@c.com'})
        self.assertFalse(self.ana._dcasa_es_la_misma_persona(distinta))

    def test_suspender_y_reactivar_son_de_gerencia(self):
        with self.assertRaises(AccessError):
            self.ana.with_user(self.mostrador).action_dcasa_suspender_vendedor()
        self.ana.with_user(self.gerente).action_dcasa_suspender_vendedor()
        self.assertEqual(self.ana.dcasa_vendedor_estado, 'suspendido')
        self.ana.with_user(self.gerente).action_dcasa_reactivar_vendedor()
        self.assertEqual(self.ana.dcasa_vendedor_estado, 'activo')

    def test_el_mostrador_afilia_pero_no_ajusta(self):
        persona = self.env['res.partner'].create({'name': 'En Caja', 'vat': '8-121-121', 'phone': '6100-0020'})
        asistente = self.env['dcasa.afiliar.vendedor.wizard'].with_user(self.mostrador).create({
            'partner_id': persona.id, 'tipo': 'empleado', 'acepta': True})
        asistente.action_confirmar()
        self.assertEqual(persona.dcasa_vendedor_tipo, 'empleado')
        self.assertEqual(persona.dcasa_vendedor_afiliado_por, 'vend_mostrador')
        with self.assertRaises(AccessError):
            persona.with_user(self.mostrador).action_dcasa_ajustar_vendedor()

    def test_la_caja_afilia_sin_patrocinador_y_solo_gerencia_arma_la_colmena(self):
        persona = self.env['res.partner'].create({'name': 'Con Padrino', 'vat': '8-131-131', 'phone': '6100-0021'})
        asistente = self.env['dcasa.afiliar.vendedor.wizard'].with_user(self.mostrador).create({
            'partner_id': persona.id, 'tipo': 'externo', 'acepta': True, 'patrocinador_id': self.ana.id})
        with self.assertRaisesRegex(UserError, 'Gerencia lo escribe después'):
            asistente.action_confirmar()
        asistente.with_user(self.gerente).action_confirmar()
        self.assertEqual(persona.dcasa_vendedor_patrocinador_id, self.ana)
        otra = self.env['res.partner'].create({'name': 'Sin Padrino', 'vat': '8-141-141', 'phone': '6100-0022'})
        otra._dcasa_afiliar_vendedor('externo', autor='prueba', acepto_terminos=True)
        with self.assertRaisesRegex(UserError, 'Solo Gerencia escribe'):
            otra.with_user(self.mostrador).write({'dcasa_vendedor_patrocinador_id': self.ana.id})
        otra.with_user(self.gerente).write({'dcasa_vendedor_patrocinador_id': self.ana.id})
        self.assertEqual(otra.dcasa_vendedor_patrocinador_id, self.ana)

    def test_afiliar_a_un_cliente_ligado_corta_su_vinculo(self):
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        self.factura(vendedor=self.ana)
        self.assertEqual(self.cliente.dcasa_vendedor_ligado_id, self.ana)
        self.cliente.vat = '8-151-151'
        self.cliente._dcasa_afiliar_vendedor('externo', autor='prueba', acepto_terminos=True)
        self.assertFalse(self.cliente.dcasa_vendedor_ligado_id)

    def test_ajuste_de_gerencia_con_motivo_y_sin_saldo_negativo(self):
        Asistente = self.env['dcasa.vend.ajuste.wizard'].with_user(self.gerente)
        Asistente.create({'partner_id': self.ana.id, 'puntos': 300, 'motivo': 'Venta de julio sin registrar'}
                         ).action_confirmar()
        self.assertEqual(self.ana.dcasa_vend_saldo, 300)
        with self.assertRaisesRegex(UserError, 'solo tiene 300'):
            Asistente.create({'partner_id': self.ana.id, 'puntos': -500, 'motivo': 'Error'}).action_confirmar()

    def test_el_libro_no_se_edita_ni_se_borra(self):
        asiento = self.dar_puntos_disponibles(self.ana, 100)
        with self.assertRaisesRegex(UserError, 'no se edita'):
            asiento.write({'puntos': 999})
        with self.assertRaisesRegex(UserError, 'no se borra'):
            asiento.unlink()


@tagged('post_install', '-at_install')
class TestComisiones(VendedoresCommon):

    def test_factura_pagada_con_codigo_da_comision_y_espera_la_ventana_de_devoluciones(self):
        factura = self.factura(vendedor=self.ana)            # neto $100.00, total $107.00
        comision = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa')
        self.assertEqual((comision.neto_centavos, comision.puntos, comision.resultado), (10000, 400, 'pagada'))
        self.assertEqual(comision.cliente_id, self.cliente)
        self.assertEqual(comision.via, 'codigo')
        self.assertEqual(self.ana.dcasa_vend_saldo, 400)
        self.assertEqual(self.ana.dcasa_vend_disponible, 0)
        self.assertEqual(self.ana.dcasa_vend_por_liberar, 400)
        asiento = self.env['dcasa.vend.movimiento'].search([('partner_id', '=', self.ana.id)])
        self.assertGreaterEqual(asiento.disponible_desde, fields.Datetime.now() + timedelta(days=29))
        a_los_31_dias = fields.Datetime.now() + timedelta(days=31)
        saldos = self.env['dcasa.vend.movimiento']._saldos_disponibles(self.ana, a_los_31_dias)
        self.assertEqual(saldos[self.ana.id], 400)

    def test_el_cliente_sigue_ganando_sus_puntos_de_cliente(self):
        self.factura(vendedor=self.ana)
        self.assertEqual(self.cliente.dcasa_saldo, 107)

    def test_la_comision_sale_de_la_venta_neta_sin_itbms_y_con_los_descuentos(self):
        factura = self.factura(precio=329.99, vendedor=self.ana)       # total $353.09
        self.assertEqual(factura.dcasa_vend_comision_ids.neto_centavos, 32999)
        self.assertEqual(factura.dcasa_vend_comision_ids.puntos, 1319)  # 329.99 × 4 = 1,319.96

    def test_factura_sin_pagar_o_sin_codigo_no_da_nada(self):
        sin_pagar = self.factura(vendedor=self.ana, pagar=False)
        self.assertFalse(sin_pagar.dcasa_vend_comision_ids)
        self.pagar(sin_pagar)
        self.assertEqual(len(sin_pagar.dcasa_vend_comision_ids), 1, 'Al pagarse sí')
        sin_codigo = self.factura()
        self.assertFalse(sin_codigo.dcasa_vend_comision_ids)

    def test_apagado_no_se_crea_nada_y_la_venta_sigue(self):
        self.reglas['vendedores']['programaActivo'] = False
        factura = self.factura(vendedor=self.ana)
        self.assertFalse(factura.dcasa_vend_comision_ids)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'), 'La venta se cobró igual')
        self.assertTrue(factura.dcasa_compra_ids, 'Socios sigue funcionando')

    def test_con_cifras_en_null_queda_escrito_que_falta_configurar_y_la_venta_sigue(self):
        self.reglas['vendedores']['comision']['puntosPorDolarNeto'] = None
        factura = self.factura(vendedor=self.ana)
        comision = factura.dcasa_vend_comision_ids
        self.assertEqual((comision.puntos, comision.resultado), (0, 'sin-configurar'))
        self.assertFalse(self.env['dcasa.vend.movimiento'].search([('partner_id', '=', self.ana.id)]))

    def test_una_factura_una_comision(self):
        factura = self.factura(vendedor=self.ana)
        factura._invoice_paid_hook()
        self.assertEqual(len(self.comisiones(self.ana)), 1)
        self.assertEqual(self.ana.dcasa_vend_saldo, 400)

    def test_facturas_del_sistema_anterior_no_dan_comision(self):
        factura = self.factura(vendedor=self.ana, pagar=False)
        factura.dcasa_historica = True
        self.pagar(factura)
        self.assertFalse(factura.dcasa_vend_comision_ids)

    def test_por_debajo_de_la_venta_minima_queda_en_cero_y_dice_por_que(self):
        factura = self.factura(precio=18.0, vendedor=self.ana)
        self.assertEqual((factura.dcasa_vend_comision_ids.puntos, factura.dcasa_vend_comision_ids.resultado),
                         (0, 'bajo-el-minimo'))

    # --- Colmena de un nivel -----------------------------------------------------------------

    def test_el_patrocinador_gana_por_la_venta_de_su_directo_sin_restarle_nada(self):
        factura = self.factura(vendedor=self.juan)
        directa = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa')
        patrocinio = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((directa.partner_id, directa.puntos), (self.juan, 400))
        self.assertEqual((patrocinio.partner_id, patrocinio.puntos), (self.ana, 40))
        self.assertEqual(patrocinio.directo_id, self.juan)
        self.assertEqual(self.juan.dcasa_vend_saldo, 400)
        self.assertEqual(self.ana.dcasa_vend_saldo, 40)

    def test_un_solo_nivel_el_abuelo_no_gana(self):
        luis = self.vendedor('Luis Nieto', '8-909-909', '6100-0009', patrocinador=self.juan)
        factura = self.factura(vendedor=luis)
        ganadores = factura.dcasa_vend_comision_ids.mapped('partner_id')
        self.assertEqual(ganadores, luis | self.juan, 'Ana, que patrocina a Juan, no gana por Luis')
        self.assertEqual(self.ana.dcasa_vend_saldo, 0)

    def test_sin_cifra_de_patrocinio_gana_el_directo_y_el_patrocinador_queda_en_cero(self):
        self.reglas['vendedores']['patrocinio']['puntosPorDolarNetoDelDirecto'] = None
        factura = self.factura(vendedor=self.juan)
        patrocinio = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((patrocinio.puntos, patrocinio.resultado), (0, 'sin-configurar'))
        self.assertEqual(self.juan.dcasa_vend_saldo, 400)

    def test_si_la_venta_directa_no_paga_no_hay_patrocinio(self):
        self.juan.action_dcasa_suspender_vendedor()
        factura = self.factura(vendedor=self.juan)
        self.assertEqual(factura.dcasa_vend_comision_ids.mapped('resultado'), ['vendedor-suspendido'])
        self.assertEqual(self.ana.dcasa_vend_saldo, 0)

    # --- Antifraude -----------------------------------------------------------------------------

    def test_el_vendedor_no_gana_por_sus_propias_compras(self):
        factura = self.factura(partner=self.ana, vendedor=self.ana)
        self.assertEqual((factura.dcasa_vend_comision_ids.puntos, factura.dcasa_vend_comision_ids.resultado),
                         (0, 'compra-propia'))
        self.assertEqual(self.ana.dcasa_vend_saldo, 0)

    def test_tampoco_por_la_ficha_de_una_persona_de_su_misma_empresa(self):
        contacto = self.env['res.partner'].create({'name': 'Contacto de Ana', 'parent_id': self.ana.id,
                                                   'type': 'invoice'})
        factura = self.factura(partner=contacto, vendedor=self.ana)
        self.assertEqual(factura.dcasa_vend_comision_ids.resultado, 'compra-propia')

    def test_el_mostrador_no_puede_anotar_el_vendedor_en_la_venta_de_el_mismo(self):
        orden = self.env['sale.order'].create({'partner_id': self.ana.id})
        with self.assertRaisesRegex(ValidationError, 'propias compras'):
            orden.dcasa_vendedor_id = self.ana

    def test_quien_registra_la_venta_en_caja_no_se_paga_a_si_mismo(self):
        cajera = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Ana en caja', 'login': 'ana_en_caja', 'partner_id': self.ana.id,
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('sales_team.group_sale_salesman').id])]})
        factura = self.factura(vendedor=self.ana, pagar=False)
        factura.dcasa_vendedor_anotado_por = cajera
        self.pagar(factura)
        comision = factura.dcasa_vend_comision_ids
        self.assertEqual((comision.puntos, comision.resultado), (0, 'registrada-por-el-vendedor'))
        otra = self.factura(vendedor=self.ana)             # la registra otra persona: sí se paga
        self.assertEqual(otra.dcasa_vend_comision_ids.puntos, 400)

    def test_la_compra_de_cualquier_vendedor_solo_da_puntos_de_cliente(self):
        otro = self.vendedor('Otro Vendedor', '8-313-313', '6100-0030')       # sin parentesco con Ana
        factura = self.factura(partner=otro, vendedor=self.ana)
        comision = factura.dcasa_vend_comision_ids
        self.assertEqual((comision.puntos, comision.resultado), (0, 'comprador-es-vendedor'))
        self.assertTrue(factura.dcasa_compra_ids.puntos, 'Como cliente sí gana sus puntos')

    def test_un_cliente_que_no_se_puede_identificar_no_cuenta_como_nuevo(self):
        self.reglas['vendedores']['comision']['factorClienteExistente'] = 0.5
        anonimo = self.env['res.partner'].create({'name': 'Cliente sin datos'})
        self.assertEqual(self.factura(partner=anonimo, vendedor=self.ana).dcasa_vend_comision_ids.puntos, 200)

    def test_las_primeras_ventas_de_un_vendedor_esperan_mas_dias(self):
        self.reglas['vendedores']['retencion'].update({'dias': 30, 'primerasVentas': 2, 'diasPrimerasVentas': 60})
        esperas = []
        for _i in range(3):
            comision = self.factura(vendedor=self.ana).dcasa_vend_comision_ids
            esperas.append((comision.disponible_desde - comision.registrada_en).days)
        self.assertEqual(esperas, [60, 60, 30])

    def test_un_pago_que_se_revierte_sin_nota_de_credito_quita_los_puntos(self):
        factura = self.factura(vendedor=self.juan)
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (400, 40))
        factura.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable') \
            .remove_move_reconcile()                       # se deshace la conciliación del pago
        self.assertNotIn(factura.payment_state, ('paid', 'in_payment'))
        self.assertEqual(self.env['dcasa.vend.comision']._revisar_pagos(), 2)
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (0, 0))
        self.assertEqual(self.env['dcasa.vend.comision']._revisar_pagos(), 0, 'Ya no queda nada que revisar')

    def test_compras_dentro_de_la_colmena_no_pagan(self):
        # El patrocinador compra con el código de su directo…
        factura = self.factura(partner=self.ana, vendedor=self.juan)
        self.assertEqual(factura.dcasa_vend_comision_ids.mapped('resultado'), ['dentro-de-la-colmena'])
        # …y el directo con el de su patrocinador.
        factura2 = self.factura(partner=self.juan, vendedor=self.ana)
        self.assertEqual(factura2.dcasa_vend_comision_ids.mapped('resultado'), ['dentro-de-la-colmena'])
        self.assertEqual((self.ana.dcasa_vend_saldo, self.juan.dcasa_vend_saldo), (0, 0))

    def test_vendedor_suspendido_no_gana(self):
        self.ana.action_dcasa_suspender_vendedor()
        factura = self.factura(vendedor=self.ana)
        self.assertEqual(factura.dcasa_vend_comision_ids.resultado, 'vendedor-suspendido')

    # --- Topes --------------------------------------------------------------------------------------

    def test_el_techo_por_venta_recorta_y_nunca_hace_fallar_la_venta(self):
        # Techo 3 % de $100 = 300; el cliente ya tiene 107 → quedan 193 para el vendedor y el patrocinador.
        self.reglas['vendedores']['techos']['totalPorVentaPorcentajeDelNeto'] = 3
        factura = self.factura(vendedor=self.juan)
        directa = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa')
        patrocinio = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((directa.puntos_calculados, directa.puntos, directa.resultado), (400, 193, 'recortada'))
        self.assertEqual((patrocinio.puntos_calculados, patrocinio.puntos, patrocinio.resultado),
                         (40, 0, 'techo-agotado'))

    def test_tope_mensual_del_vendedor(self):
        self.reglas['vendedores']['techos']['porVendedorAlMesPuntos'] = 500
        primera = self.factura(vendedor=self.ana)
        segunda = self.factura(vendedor=self.ana)
        self.assertEqual(primera.dcasa_vend_comision_ids.puntos, 400)
        self.assertEqual((segunda.dcasa_vend_comision_ids.puntos, segunda.dcasa_vend_comision_ids.resultado),
                         (100, 'recortada'))
        tercera = self.factura(vendedor=self.ana)
        self.assertEqual((tercera.dcasa_vend_comision_ids.puntos, tercera.dcasa_vend_comision_ids.resultado),
                         (0, 'tope-del-mes'))

    def test_tope_mensual_del_patrocinio(self):
        self.reglas['vendedores']['techos']['patrocinioPorPatrocinadorAlMesPuntos'] = 50
        self.factura(vendedor=self.juan)
        segunda = self.factura(vendedor=self.juan)
        patrocinio = segunda.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((patrocinio.puntos, patrocinio.resultado), (10, 'recortada'))

    def test_solo_la_primera_compra_si_asi_se_decide(self):
        self.reglas['vendedores']['comision']['pagaEn'] = 'primera-compra'
        self.assertEqual(self.factura(vendedor=self.ana).dcasa_vend_comision_ids.puntos, 400)
        segunda = self.factura(vendedor=self.ana)
        self.assertEqual((segunda.dcasa_vend_comision_ids.puntos, segunda.dcasa_vend_comision_ids.resultado),
                         (0, 'ya-pago-la-primera'))

    def test_escalones_por_ventas_de_los_ultimos_dias(self):
        self.reglas['vendedores']['comision']['escalones'] = [
            {'desdeVentasNetasCentavos': 10000, 'puntosPorDolarNeto': 5}]
        self.assertEqual(self.factura(vendedor=self.ana).dcasa_vend_comision_ids.puntos, 400)
        self.assertEqual(self.factura(vendedor=self.ana).dcasa_vend_comision_ids.puntos, 500)

    def test_el_tope_del_mes_sube_con_el_escalon_alcanzado(self):
        """Quien lleva ventas sostenidas (escalón alto) tiene un tope mensual más alto que quien empieza."""
        self.reglas['vendedores']['techos']['porVendedorAlMesPuntos'] = 500
        self.reglas['vendedores']['comision']['escalones'] = [
            {'desdeVentasNetasCentavos': 10000, 'puntosPorDolarNeto': 5, 'topeAlMesPuntos': 2000}]
        primera = self.factura(vendedor=self.ana)           # escalón base: 400 (cabe en el tope base de 500)
        self.assertEqual(primera.dcasa_vend_comision_ids.puntos, 400)
        for _ in range(3):                                   # ya vendió $100: escalón de 5 % y tope de 2,000
            self.assertEqual(self.factura(vendedor=self.ana).dcasa_vend_comision_ids.puntos, 500)
        quinta = self.factura(vendedor=self.ana)             # 400 + 3 × 500 = 1,900: caben 100 de los 500
        self.assertEqual((quinta.dcasa_vend_comision_ids.puntos, quinta.dcasa_vend_comision_ids.resultado),
                         (100, 'recortada'))
        sexta = self.factura(vendedor=self.ana)
        self.assertEqual((sexta.dcasa_vend_comision_ids.puntos, sexta.dcasa_vend_comision_ids.resultado),
                         (0, 'tope-del-mes'))

    def test_el_tope_base_sigue_frenando_a_quien_no_ha_subido_de_escalon(self):
        self.reglas['vendedores']['techos']['porVendedorAlMesPuntos'] = 500
        self.reglas['vendedores']['comision']['escalones'] = [
            {'desdeVentasNetasCentavos': 99999999, 'puntosPorDolarNeto': 8, 'topeAlMesPuntos': 90000}]
        self.factura(vendedor=self.ana)
        segunda = self.factura(vendedor=self.ana)
        self.assertEqual((segunda.dcasa_vend_comision_ids.puntos, segunda.dcasa_vend_comision_ids.resultado),
                         (100, 'recortada'))

    def test_el_resumen_del_panel_trae_el_nivel(self):
        self.reglas['vendedores']['comision']['escalones'] = [
            {'desdeVentasNetasCentavos': 10000, 'puntosPorDolarNeto': 5, 'topeAlMesPuntos': 2000}]
        self.reglas['vendedores']['techos']['porVendedorAlMesPuntos'] = 500
        nivel = self.ana._dcasa_vend_resumen_panel()['nivel']
        self.assertEqual((nivel['puntos_por_dolar'], nivel['tope_al_mes'], nivel['ventas_centavos']), (4, 500, 0))
        self.assertEqual(nivel['siguiente'], {'puntos_por_dolar': 5, 'falta_centavos': 10000})
        self.factura(vendedor=self.ana)
        nivel = self.ana._dcasa_vend_resumen_panel()['nivel']
        self.assertEqual((nivel['puntos_por_dolar'], nivel['tope_al_mes'], nivel['siguiente']), (5, 2000, None))

    # --- Vínculo del cliente ---------------------------------------------------------------------------

    def test_sin_vinculacion_solo_cuenta_la_compra_con_el_codigo(self):
        self.factura(vendedor=self.ana)
        sin_codigo = self.factura()
        self.assertFalse(sin_codigo.dcasa_vend_comision_ids)
        self.assertFalse(self.cliente.dcasa_vendedor_ligado_id)

    def test_con_vinculacion_el_cliente_queda_ligado_y_sus_compras_siguientes_cuentan(self):
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        self.factura(vendedor=self.ana)
        self.assertEqual(self.cliente.dcasa_vendedor_ligado_id, self.ana)
        sin_codigo = self.factura()
        comision = sin_codigo.dcasa_vend_comision_ids
        self.assertEqual((comision.partner_id, comision.puntos, comision.via), (self.ana, 400, 'vinculo'))

    def test_el_codigo_de_otro_vendedor_no_le_quita_al_cliente_ligado(self):
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        otro = self.vendedor('Otro Vendedor', '8-313-313', '6100-0030')
        self.factura(vendedor=self.ana)
        con_otro_codigo = self.factura(vendedor=otro)
        comision = con_otro_codigo.dcasa_vend_comision_ids
        self.assertEqual(comision.partner_id, self.ana)
        self.assertEqual(otro.dcasa_vend_saldo, 0)

    def test_vencido_el_vinculo_vuelve_a_valer_el_codigo(self):
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        otro = self.vendedor('Otro Vendedor', '8-313-313', '6100-0030')
        self.factura(vendedor=self.ana)
        self.cliente.sudo().dcasa_vendedor_ligado_en = fields.Datetime.now() - timedelta(days=400)
        nueva = self.factura(vendedor=otro)
        self.assertEqual(nueva.dcasa_vend_comision_ids.partner_id, otro)

    def test_la_recompra_sin_codigo_paga_una_fraccion(self):
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        self.reglas['vendedores']['comision']['factorDeRecompra'] = 0.5
        con_codigo = self.factura(vendedor=self.ana)
        self.assertEqual(con_codigo.dcasa_vend_comision_ids.puntos, 400, 'La compra con el código paga entera')
        recompra = self.factura().dcasa_vend_comision_ids
        self.assertEqual((recompra.via, recompra.puntos_calculados, recompra.puntos, recompra.resultado),
                         ('vinculo', 200, 200, 'pagada'))

    def test_la_recompra_no_da_patrocinio_salvo_que_se_decida(self):
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        self.factura(vendedor=self.juan)
        recompra = self.factura()
        self.assertEqual(recompra.dcasa_vend_comision_ids.mapped('tipo'), ['directa'])
        self.assertEqual(self.ana.dcasa_vend_saldo, 40, 'Ana solo ganó por la primera venta')
        self.reglas['vendedores']['vinculacion']['pagaPatrocinio'] = True
        con_patrocinio = self.factura()
        self.assertEqual(sorted(con_patrocinio.dcasa_vend_comision_ids.mapped('tipo')), ['directa', 'patrocinio'])
        self.assertEqual(self.ana.dcasa_vend_saldo, 80)

    def cliente_nuevo(self, nombre='Cliente Nuevo', celular='6000-0077'):
        return self.env['res.partner'].create({'name': nombre, 'phone': celular})

    def test_el_cliente_que_ya_compro_paga_una_fraccion_aunque_traiga_codigo(self):
        self.reglas['vendedores']['comision']['factorClienteExistente'] = 0.5
        nuevo = self.factura(partner=self.cliente_nuevo(), vendedor=self.ana).dcasa_vend_comision_ids
        self.assertEqual((nuevo.puntos, nuevo.resultado), (400, 'pagada'), 'El cliente nuevo paga entero')
        self.factura(partner=self.cliente)                # ya era cliente de la tienda: compra sin código
        existente = self.factura(partner=self.cliente, vendedor=self.ana).dcasa_vend_comision_ids
        self.assertEqual((existente.via, existente.puntos), ('codigo', 200))

    def test_la_primera_factura_sin_pagar_todavia_no_vuelve_existente_al_cliente(self):
        self.reglas['vendedores']['comision']['factorClienteExistente'] = 0.5
        cliente = self.cliente_nuevo()
        self.factura(partner=cliente, pagar=False)        # otra factura abierta, sin pagar
        self.assertEqual(self.factura(partner=cliente, vendedor=self.ana).dcasa_vend_comision_ids.puntos, 400)

    def test_el_patrocinio_solo_nace_de_clientes_nuevos_si_asi_se_decide(self):
        self.reglas['vendedores']['patrocinio']['soloClientesNuevos'] = True
        nueva = self.factura(partner=self.cliente_nuevo(), vendedor=self.juan)
        self.assertEqual(sorted(nueva.dcasa_vend_comision_ids.mapped('tipo')), ['directa', 'patrocinio'])
        self.factura(partner=self.cliente)
        existente = self.factura(partner=self.cliente, vendedor=self.juan)
        self.assertEqual(existente.dcasa_vend_comision_ids.mapped('tipo'), ['directa'])

    def test_el_techo_cuenta_tambien_el_referido_que_disparo_la_compra(self):
        # El cliente viene invitado: 107 de su compra + 750 de referido (500 y 250) = 857, más que el techo (800).
        cliente = self.cliente_nuevo()
        cliente.dcasa_referido_por_id = self.padrino
        factura = self.factura(partner=cliente, vendedor=self.ana)
        comision = factura.dcasa_vend_comision_ids
        self.assertEqual((comision.puntos, comision.resultado), (0, 'techo-agotado'))
        self.assertTrue(factura.dcasa_compra_ids.puntos, 'El cliente y su padrino no pierden nada')

    def test_el_patrocinador_sin_ventas_propias_este_mes_no_cobra_patrocinio(self):
        self.reglas['vendedores']['patrocinio']['ventasPropiasMinimasAlMes'] = 1
        primera = self.factura(vendedor=self.juan)
        patrocinio = primera.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((patrocinio.puntos, patrocinio.resultado), (0, 'patrocinador-sin-ventas'))
        self.assertEqual(primera.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa').puntos, 400)
        self.factura(vendedor=self.ana)                   # Ana vende por su cuenta
        segunda = self.factura(vendedor=self.juan)
        patrocinio = segunda.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((patrocinio.puntos, patrocinio.resultado), (40, 'pagada'))

    def test_las_ventas_minimas_cuentan_clientes_distintos(self):
        self.reglas['vendedores']['patrocinio']['ventasPropiasMinimasAlMes'] = 2
        self.factura(vendedor=self.ana)
        self.factura(vendedor=self.ana)                   # dos ventas al mismo cliente: cuenta como una
        sin = self.factura(vendedor=self.juan).dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual(sin.resultado, 'patrocinador-sin-ventas')
        self.factura(partner=self.cliente_nuevo(), vendedor=self.ana)
        con = self.factura(vendedor=self.juan).dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual(con.resultado, 'pagada')

    def test_el_patrocinio_se_topa_contra_la_comision_propia_del_patrocinador(self):
        self.reglas['vendedores']['patrocinio']['topeComoMultiploDeSuComisionDelMes'] = 0.1
        sin_ventas = self.factura(vendedor=self.juan).dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((sin_ventas.puntos, sin_ventas.resultado), (0, 'tope-del-mes'))
        self.factura(vendedor=self.ana)                   # Ana gana 400: puede cobrar hasta 40 de patrocinio
        primera = self.factura(vendedor=self.juan).dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((primera.puntos, primera.resultado), (40, 'pagada'))
        segunda = self.factura(vendedor=self.juan).dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((segunda.puntos, segunda.resultado), (0, 'tope-del-mes'))

    def test_el_freno_global_cuenta_la_venta_de_toda_la_tienda_y_los_puntos_emitidos(self):
        Comision = self.env['dcasa.vend.comision']
        emitido, ventas = Comision._datos_del_freno_global()
        self.factura(vendedor=self.juan)                  # $100 neto; 400 + 40 puntos
        emitido_despues, ventas_despues = Comision._datos_del_freno_global()
        self.assertEqual(ventas_despues - ventas, 10000)
        self.assertEqual(emitido_despues - emitido, 440)

    def test_el_freno_global_recorta_primero_el_patrocinio_y_la_venta_sigue(self):
        self.reglas['vendedores']['techos']['frenoGlobalPorcentajeDeLaVentaNeta'] = 3      # 3 % de $100 = 300
        with patch.object(type(self.env['dcasa.vend.comision']), '_datos_del_freno_global',
                          return_value=(0, 10000)):
            factura = self.factura(vendedor=self.juan)
        directa = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa')
        patrocinio = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'patrocinio')
        self.assertEqual((directa.puntos_calculados, directa.puntos, directa.resultado), (400, 300, 'recortada'))
        self.assertEqual((patrocinio.puntos, patrocinio.resultado), (0, 'freno-global'))
        self.assertEqual(factura.payment_state, 'paid', 'El freno nunca hace fallar el cobro')

    def test_con_el_freno_ya_gastado_nadie_gana_y_queda_escrito_por_que(self):
        self.reglas['vendedores']['techos']['frenoGlobalPorcentajeDeLaVentaNeta'] = 1      # 1 % de $100 = 100
        with patch.object(type(self.env['dcasa.vend.comision']), '_datos_del_freno_global',
                          return_value=(100, 10000)):
            factura = self.factura(vendedor=self.juan)
        self.assertEqual(sorted(factura.dcasa_vend_comision_ids.mapped('resultado')), ['freno-global'] * 2)
        self.assertEqual(self.juan.dcasa_vend_saldo, 0)

    # --- Anular --------------------------------------------------------------------------------------------

    def test_nota_de_credito_total_devuelve_los_puntos_de_vendedor_y_de_la_colmena(self):
        factura = self.factura(vendedor=self.juan)
        factura._reverse_moves([{'ref': 'Devolución'}], cancel=True)
        self.assertTrue(all(c.anulada_en for c in factura.dcasa_vend_comision_ids))
        self.assertEqual((self.juan.dcasa_vend_saldo, self.ana.dcasa_vend_saldo), (0, 0))
        reversos = self.env['dcasa.vend.movimiento'].search([('tipo', '=', 'reverso')])
        self.assertEqual(len(reversos), 2)
        self.assertTrue(all('Nota de crédito' in r.motivo for r in reversos))

    def test_nota_de_credito_parcial_descuenta_lo_proporcional(self):
        factura = self.factura(vendedor=self.ana)                       # 400 puntos
        nota = factura._reverse_moves([{'ref': 'Devolución parcial'}])
        nota.invoice_line_ids.price_unit = 25.0                        # devuelve $25 de $100 neto
        nota.action_post()
        self.assertEqual(self.ana.dcasa_vend_saldo, 300)
        ajuste = self.env['dcasa.vend.movimiento'].search([('partner_id', '=', self.ana.id), ('tipo', '=', 'ajuste')])
        self.assertEqual(ajuste.puntos, -100)
        self.assertIn('Devolución parcial', ajuste.motivo)

    def test_la_factura_que_vuelve_a_borrador_o_se_cancela_anula_la_comision(self):
        factura = self.factura(vendedor=self.ana)
        factura.button_draft()
        self.assertTrue(all(c.anulada_en for c in factura.dcasa_vend_comision_ids))
        self.assertEqual(self.ana.dcasa_vend_saldo, 0)

    def test_anular_dos_veces_no_devuelve_dos_veces(self):
        factura = self.factura(vendedor=self.ana)
        comision = factura.dcasa_vend_comision_ids
        comision._anular('Se registró mal', 'prueba')
        comision._anular('Otra vez', 'prueba')
        self.assertEqual(self.ana.dcasa_vend_saldo, 0)
        with self.assertRaisesRegex(UserError, 'por qué se anula'):
            self.factura(vendedor=self.ana).dcasa_vend_comision_ids._anular('  ', 'prueba')

    # --- Atribución en la venta y en la factura ------------------------------------------------------------

    def orden_con_vendedor(self, vendedor=None):
        return self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'dcasa_vendedor_id': (vendedor or self.ana).id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1, 'price_unit': 100.0})],
        })

    def test_el_codigo_de_la_cotizacion_viaja_a_la_factura_y_deja_rastro(self):
        orden = self.orden_con_vendedor()
        self.assertEqual(orden.dcasa_vendedor_anotado_por, self.env.user)
        orden.action_confirm()
        factura = orden._create_invoices()
        self.assertEqual(factura.dcasa_vendedor_id, self.ana)
        self.assertEqual(factura.dcasa_vendedor_anotado_por, self.env.user)
        factura.action_post()
        self.pagar(factura)
        self.assertEqual(factura.dcasa_vend_comision_ids.partner_id, self.ana)

    def test_confirmada_la_venta_solo_gerencia_cambia_el_vendedor(self):
        orden = self.orden_con_vendedor()
        orden.action_confirm()
        with self.assertRaisesRegex(UserError, 'solo lo cambia Gerencia'):
            orden.with_user(self.mostrador).write({'dcasa_vendedor_id': self.juan.id})
        orden.with_user(self.gerente).write({'dcasa_vendedor_id': self.juan.id})
        self.assertEqual(orden.dcasa_vendedor_id, self.juan)
        self.assertEqual(orden.dcasa_vendedor_anotado_por, self.gerente)

    def test_con_comision_ya_pagada_el_vendedor_no_se_cambia_sin_anularla(self):
        factura = self.factura(vendedor=self.ana)
        with self.assertRaisesRegex(UserError, 'primero se anula'):
            factura.write({'dcasa_vendedor_id': self.juan.id})
        factura.dcasa_vend_comision_ids._anular('Vendedor equivocado', 'prueba')
        self.assertTrue(factura.dcasa_vend_comision_ids.anulada_en)

    def test_factura_publicada_solo_gerencia_cambia_el_vendedor(self):
        factura = self.factura(vendedor=self.ana, pagar=False)
        with self.assertRaisesRegex(UserError, 'solo lo cambia Gerencia'):
            factura.with_user(self.mostrador).write({'dcasa_vendedor_id': self.juan.id})
        factura.with_user(self.gerente).write({'dcasa_vendedor_id': self.juan.id})
        self.assertEqual(factura.dcasa_vendedor_id, self.juan)


@tagged('post_install', '-at_install')
class TestCanjeDeVendedores(VendedoresCommon):

    def setUp(self):
        super().setUp()
        self.premio = self.env['dcasa.premio'].create({
            'name': 'Cama box Twin', 'tipo': 'producto', 'puntos': 1500, 'valor': 39.99, 'costo': 14.0,
            'para_vendedores': True, 'stock_limitado': True, 'stock': 3})

    def test_un_premio_de_vendedores_no_se_vende_por_debajo_de_su_costo(self):
        with self.assertRaisesRegex(ValidationError, 'al menos 2000'):
            self.env['dcasa.premio'].create({'name': 'Regalo', 'tipo': 'producto', 'puntos': 1500, 'costo': 20.0,
                                             'para_vendedores': True})

    def test_el_peso_del_punto_de_vendedor_sube_el_minimo_de_puntos_del_premio(self):
        self.reglas['vendedores']['techos']['pesoDelPuntoDeVendedor'] = 0.5
        # costo $10 a 100 puntos por dólar son 1,000 puntos; con peso 0.5 el premio pide al menos 2,000.
        with self.assertRaisesRegex(ValidationError, 'al menos 2000'):
            self.env['dcasa.premio'].create({'name': 'Regalo', 'tipo': 'producto', 'puntos': 1500, 'costo': 10.0,
                                             'para_vendedores': True})
        self.env['dcasa.premio'].create({'name': 'Regalo', 'tipo': 'producto', 'puntos': 2000, 'costo': 10.0,
                                         'para_vendedores': True})

    def test_el_canje_de_externos_espera_la_revision_del_abogado_y_los_puntos_no_se_pierden(self):
        self.reglas['vendedores']['canje']['externosHabilitado'] = False
        self.dar_puntos_disponibles(self.ana, 2000)
        with self.assertRaisesRegex(UserError, 'externos todavía no está habilitado'):
            self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        self.assertEqual(self.ana.dcasa_vend_saldo, 2000)
        empleado = self.vendedor('Elena Empleada', '8-555-555', '6100-0055', tipo='empleado')
        self.dar_puntos_disponibles(empleado, 2000)
        self.assertEqual(self.env['dcasa.vend.canje']._pedir(empleado, self.premio).estado, 'solicitado')

    def test_los_socios_no_ven_los_premios_de_vendedores_y_viceversa(self):
        self.assertNotIn(self.premio, self.env['dcasa.premio']._catalogo())
        self.assertIn(self.premio, self.env['dcasa.premio']._catalogo_vendedores())
        premio_socios = self.env.ref('dcasa_socios.premio_desc_10')
        self.assertNotIn(premio_socios, self.env['dcasa.premio']._catalogo_vendedores())

    def test_pedir_gasta_puntos_disponibles_y_da_codigo(self):
        self.dar_puntos_disponibles(self.ana, 2000)
        canje = self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        self.assertEqual((canje.estado, canje.puntos, canje.premio_nombre), ('solicitado', 1500, 'Cama box Twin'))
        self.assertRegex(canje.codigo, r'^[2-9A-HJKMNP-Z]{6}$')
        self.assertEqual(self.ana.dcasa_vend_saldo, 500)
        self.assertEqual(self.premio.stock, 2)
        self.assertGreater(canje.expira_en, fields.Datetime.now() + timedelta(hours=71))

    def test_los_puntos_por_liberar_no_se_pueden_canjear(self):
        self.factura(vendedor=self.ana)                                  # 400 puntos esperando 30 días
        self.dar_puntos_disponibles(self.ana, 1200)                       # 1,600 en total, solo 1,200 disponibles
        with self.assertRaisesRegex(UserError, 'Te faltan 300 puntos disponibles'):
            self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)

    def test_el_minimo_de_canje_y_el_premio_equivocado(self):
        barato = self.env['dcasa.premio'].create({'name': 'Cojín', 'tipo': 'producto', 'puntos': 300, 'costo': 2.0,
                                                  'para_vendedores': True})
        self.dar_puntos_disponibles(self.ana, 5000)
        with self.assertRaisesRegex(UserError, 'mínimo es de 500'):
            self.env['dcasa.vend.canje']._pedir(self.ana, barato)
        de_socios = self.env.ref('dcasa_socios.premio_desc_10')
        with self.assertRaisesRegex(UserError, 'no está disponible para vendedores'):
            self.env['dcasa.vend.canje']._pedir(self.ana, de_socios)

    def test_un_pendiente_por_premio_y_el_tope_mensual(self):
        self.reglas['vendedores']['canje']['canjesPorVendedorAlMes'] = 1
        self.dar_puntos_disponibles(self.ana, 9000)
        self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        with self.assertRaisesRegex(UserError, 'Ya tienes ese premio pedido'):
            self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        otro = self.env['dcasa.premio'].create({'name': 'Cama box Full', 'tipo': 'producto', 'puntos': 3000,
                                                'costo': 29.0, 'para_vendedores': True})
        with self.assertRaisesRegex(UserError, 'máximo de 1 canjes'):
            self.env['dcasa.vend.canje']._pedir(self.ana, otro)

    def test_un_vendedor_suspendido_no_canjea_y_el_programa_apagado_tampoco(self):
        self.dar_puntos_disponibles(self.ana, 2000)
        self.ana.action_dcasa_suspender_vendedor()
        with self.assertRaisesRegex(UserError, 'no está activa'):
            self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        self.ana.action_dcasa_reactivar_vendedor()
        self.reglas['vendedores']['programaActivo'] = False
        with self.assertRaisesRegex(UserError, 'todavía no está encendido'):
            self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)

    def test_cancelar_devuelve_los_puntos_y_el_stock_una_sola_vez(self):
        self.dar_puntos_disponibles(self.ana, 2000)
        canje = self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        canje.with_user(self.mostrador).action_cancelar()
        canje.with_user(self.mostrador).action_cancelar()
        self.assertEqual((canje.estado, self.ana.dcasa_vend_saldo, self.premio.stock), ('cancelado', 2000, 3))

    def test_entregar_es_del_equipo_de_ventas(self):
        self.dar_puntos_disponibles(self.ana, 2000)
        canje = self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        usuario_sin_permiso = new_test_user(self.env, login='vend_otro', groups='base.group_user')
        with self.assertRaises(AccessError):
            canje.with_user(usuario_sin_permiso).action_entregar()
        canje.with_user(self.mostrador).action_entregar()
        self.assertEqual((canje.estado, canje.entregado_por), ('entregado', 'vend_mostrador'))
        with self.assertRaisesRegex(UserError, 'ya no está pendiente'):
            canje.with_user(self.mostrador).action_entregar()

    def test_el_cron_vence_los_codigos_y_devuelve_los_puntos(self):
        self.dar_puntos_disponibles(self.ana, 2000)
        canje = self.env['dcasa.vend.canje']._pedir(self.ana, self.premio)
        canje.sudo().expira_en = fields.Datetime.now() - timedelta(hours=1)
        self.env['dcasa.canje']._cron_programa()
        self.assertEqual((canje.estado, self.ana.dcasa_vend_saldo), ('vencido', 2000))
