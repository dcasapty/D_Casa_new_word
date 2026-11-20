"""Segunda revision adversarial, parte A: cierre de B1 (origen), versiones, ajustes, anticipos.

Cada prueba dice en su nombre lo que se intento. Las que FALLAN hoy demuestran un hallazgo; las que PASAN dejan
constancia de lo que se intento y no se pudo romper. Cifras y personas de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012  (pruebas de la segunda revision: se conservan tal como se escribieron)
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged

from .test_comision import ComisionReloj
from .test_endurecimiento import Liquida
from .test_vendedoras import VendedoraCommon


@tagged('post_install', '-at_install')
class TestRevision2OrigenPorContexto(VendedoraCommon):
    """B1: ¿se fabrica el origen «venta online» de un pedido que no lo es? Vector nuevo: las claves ``default_*`` del
    contexto (el contexto SI viaja por RPC). ``create`` limpia los valores, pero Odoo pone los defaults del contexto
    DESPUES de que el metodo propio ya limpio."""

    def _crear(self, usuario, contexto, **extra):
        return self.env['sale.order'].with_user(usuario).with_context(**contexto).create({
            'partner_id': self.cliente.id, 'company_id': self.company.id, **extra,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1,
                                           'price_unit': 1000.0})]})

    def test_revision2_01a_default_dcasa_nacio_en_web_en_el_contexto_fabrica_el_origen(self):
        for usuario in (self.u_vendedora, self.u_gerencia):
            with self.subTest(usuario=usuario.login):
                orden = self._crear(usuario, {'default_dcasa_nacio_en_web': True})
                self.assertFalse(orden.dcasa_nacio_en_web, 'un pedido tecleado nacio «en la web» por el contexto')
                self.assertFalse(orden.dcasa_venta_online)

    def test_revision2_01b_default_dcasa_creada_por_id_y_via_andres_en_el_contexto_se_ignoran(self):
        """Quien fabrica el origen tambien puede borrar su rastro: ``dcasa_creada_por_id`` = un visitante."""
        publico = self.env.ref('base.public_user')
        orden = self._crear(self.u_gerencia, {'default_dcasa_creada_por_id': publico.id,
                                              'default_dcasa_via_andres': True})
        self.assertFalse(orden.dcasa_creada_por_id, 'se fabrico quien abrio el carrito')
        self.assertFalse(orden.dcasa_via_andres)

    def test_revision2_01c_copy_con_default_en_el_contexto_no_hereda_ni_fabrica_el_origen(self):
        base = self._crear(self.u_gerencia, {})
        copia = base.with_user(self.u_gerencia).with_context(default_dcasa_nacio_en_web=True).copy()
        self.assertFalse(copia.dcasa_nacio_en_web)
        self.assertFalse(copia.dcasa_venta_online)

    def test_revision2_01d_de_punta_a_punta_un_pedido_de_mostrador_fabricado_por_el_contexto_cobra_la_comision_web(self):
        """El escenario de B1 con otro vector: Gerencia (o Nomina) teclea una venta de la tienda de una vendedora, la
        marca «online» con el contexto, y termina en el libro de quienes reciben y fuera del bono de la vendedora."""
        self.version(10.0)
        orden = self._crear(self.u_gerencia, {'default_dcasa_nacio_en_web': True}, user_id=self.u_vendedora.id)
        orden.action_confirm()
        factura = self.facturar(orden, '2030-03-05')
        self.pagar(factura, '2030-03-05')
        self.assertEqual(self.bono().cobrado, 1000.0, 'una venta de mostrador debe seguir siendo de la vendedora')
        self.assertFalse(self.libro(), 'una venta de mostrador no debe comisionar como venta del sitio')

    def test_revision2_01e_el_estado_de_una_liquidacion_no_se_fabrica_por_el_contexto(self):
        """La misma familia de hueco en otro modelo: ``create`` descarta ``estado`` del valor pero no del contexto."""
        liq = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).with_context(
            default_estado='aprobada').create({'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31'})
        self.assertEqual(liq.estado, 'borrador', 'se creo una liquidacion ya «aprobada» sin pasar por la aprobacion')

    def test_revision2_01f_el_contexto_no_crea_renglones_de_liquidacion(self):
        self.rechaza(lambda: self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).with_context(
            default_linea_ids=[(0, 0, {'empleado_id': self.ana.id, 'concepto': 'comision', 'centavos': 99999})]
        ).create({'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31'}))

    def test_revision2_01g_una_version_no_nace_anulada_por_el_contexto(self):
        version = self.env['dcasa.web.reglas'].with_user(self.u_nomina).with_context(default_anulada=True).create({
            'company_id': self.company.id, 'porcentaje': 0, 'tarifa_fija': 0})
        self.assertFalse(version.anulada)

    def test_revision2_02_importar_con_la_columna_del_origen_no_la_fabrica(self):
        """``load`` (la importacion de Odoo) recibe columnas por nombre."""
        resultado = self.env['sale.order'].with_user(self.u_gerencia).load(
            ['partner_id/.id', 'dcasa_nacio_en_web', 'website_id/.id'],
            [[str(self.cliente.id), '1', str(self.website.id)]])
        ids = [i for i in (resultado.get('ids') or []) if i]
        if ids:
            orden = self.env['sale.order'].browse(ids)
            self.assertFalse(orden.dcasa_nacio_en_web)


@tagged('post_install', '-at_install')
class TestRevision2Versiones(ComisionReloj):

    def test_revision2_03_una_version_guardada_despues_con_fecha_mas_cercana_manda_tambien_despues_de_la_fecha_de_otra(self):
        """HALLAZGO (importante): Gerencia guarda A (10 %) para el 20 y luego B (5 %, otro reparto) «desde el 10». La
        ayuda del campo dice que no se acepta una fecha anterior a otra ya programada, pero se acepta; y desde el 20 la
        version A, que se guardo ANTES, vuelve a mandar y tapa a B en silencio."""
        A = self.version(10.0, rige_desde=fields.Datetime.now() + timedelta(days=16))
        B = self.version(5.0, reparto=[(self.ana, 100.0)], rige_desde=fields.Datetime.now() + timedelta(days=6))
        Reglas = self.env['dcasa.web.reglas']
        despues_del_20 = fields.Datetime.now() + timedelta(days=21)
        self.assertEqual(Reglas._vigente(self.company, despues_del_20), B,
                         'la ultima version guardada debe mandar desde su fecha en adelante; hoy manda %s (la anterior)'
                         % Reglas._vigente(self.company, despues_del_20).numero)

    def test_revision2_04_dos_versiones_el_mismo_dia_manda_la_de_hora_mas_tardia_aunque_se_guardo_antes(self):
        """HALLAZGO (menor): ``rige_desde`` guarda hora; el mismo dia de Panama gana la de hora mas tardia, no la
        ultima guardada. Una pausa («porcentaje 0») puesta con la hora de las 00:00 queda tapada por la de las 10:00."""
        v1 = self.version(10.0)            # rige desde ahora (10:00 en Panama)
        pausa = self.version(0.0, rige_desde='2030-03-04 05:00:00')    # «desde hoy», inicio del dia en Panama
        Reglas = self.env['dcasa.web.reglas']
        self.assertEqual(Reglas._vigente(self.company), pausa,
                         'la pausa guardada despues debe mandar; hoy manda la v%s' % Reglas._vigente(self.company).numero)
        self.assertEqual(v1.estado, 'anterior')


@tagged('post_install', '-at_install')
class TestRevision2AjusteALoPropio(Liquida):

    def test_revision2_05_quien_cobra_se_anota_un_ajuste_a_si_mismo_y_la_liquidacion_no_lo_avisa(self):
        """HALLAZGO (importante): ana (usuario de Nomina, ligada a su ficha) se anota +500 con un motivo cualquiera;
        al armar, el renglon de ana sube y NADA en la liquidacion (ni en los avisos) dice que viene de un ajuste a
        mano hecho por ella misma. Quien aprueba solo ve «Ana: 500»."""
        self.version(10.0)
        self.venta_web()
        self.assertEqual(self.ana.user_id, self.u_ana)
        asistente = self.env['dcasa.web.ajuste'].with_user(self.u_ana).create({
            'empleado_id': self.ana.id, 'concepto': 'comision', 'monto': 500.0, 'motivo': 'correccion'})
        asistente.action_anotar()
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        linea = liq.sudo().linea_ids.filtered(lambda ln: ln.empleado_id == self.ana)
        self.assertEqual(linea.centavos, 6000 + 50000, 'el ajuste de ana entro en lo que se le paga')
        self.assertTrue(liq.avisos and 'ajuste' in (liq.avisos or '').lower(),
                        'quien aprueba debe ver que hay un ajuste a mano, y de quien: avisos=%r' % liq.avisos)


    def test_revision2_05b_un_ajuste_se_anota_a_cualquier_empleado_aunque_nunca_haya_figurado_entre_quienes_reciben(self):
        """HALLAZGO (importante, junto con el anterior): el asistente solo filtra en pantalla (``dcasa_en_planilla``);
        por el servidor se le anota un ajuste a CUALQUIER empleado, incluso a uno que ninguna version del reparto
        nombro, y la siguiente liquidacion se lo paga."""
        self.version(10.0)
        ajeno = self._empleado('Empleado ajeno rv2', 1000, '2029-01-01')
        self.rechaza(lambda: self.env['dcasa.web.ajuste'].with_user(self.u_nomina).create({
            'empleado_id': ajeno.id, 'concepto': 'comision', 'monto': 300.0, 'motivo': 'ajuste a un ajeno'
        }).action_anotar())


@tagged('post_install', '-at_install')
class TestRevision2Anticipos(ComisionReloj):
    """«Antes de los descuentos» + un anticipo (apartado con adelanto facturado aparte)."""

    def _con_anticipo(self, **opciones):
        self.version(10.0, **opciones)
        orden = self.orden(lineas=[(self.mueble, 1000.0, 1, {})])
        asistente = self.env['sale.advance.payment.inv'].with_context(
            active_model='sale.order', active_ids=orden.ids).create({
                'advance_payment_method': 'fixed', 'fixed_amount': 300.0})
        asistente.create_invoices()
        anticipo = orden.invoice_ids.filtered(lambda f: f.state == 'draft')
        anticipo.invoice_date = '2030-03-04'
        anticipo.action_post()
        self.pagar(anticipo, '2030-03-04')
        final = orden._create_invoices(final=True)
        final.invoice_date = '2030-03-05'
        final.action_post()
        self.pagar(final, '2030-03-05')
        return anticipo, final

    def test_revision2_06_con_descuentos_despues_el_anticipo_y_la_factura_final_suman_lo_vendido_una_sola_vez(self):
        anticipo, final = self._con_anticipo()
        base = self.venta(anticipo).base_centavos + self.venta(final).base_centavos
        self.assertEqual(base, 100000, 'entre las dos facturas la base es lo vendido: 1,000')

    def test_revision2_07_con_descuentos_antes_el_anticipo_se_cuenta_dos_veces(self):
        """HALLAZGO (menor, solo con ese interruptor): el anticipo que se resta en la factura final es una linea
        negativa; con «antes de descuentos» no se resta, asi que los 300 ya contados en la factura del anticipo se
        cuentan otra vez en la final."""
        anticipo, final = self._con_anticipo(base_descuentos='antes')
        base = self.venta(anticipo).base_centavos + self.venta(final).base_centavos
        self.assertEqual(base, 100000, 'la venta es de 1,000 y no puede comisionar mas de 1,000 (hoy: %s)' % base)
