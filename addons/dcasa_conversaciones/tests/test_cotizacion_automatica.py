"""La herramienta ``cotizar`` de Juan: arma la cotización sola, la deja en PDF y respeta el interruptor de Ajustes."""
import json
import re
import shutil
from unittest import skipUnless
from unittest.mock import patch

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from ..models.herramientas_juan_cotizacion import MAX_LINEAS_AUTOMATICAS, TOPE_NUEVAS_POR_DIA
from .test_herramientas import HerramientasCase
from .test_panel_catalogo import _pypdf2_compatible

RENDER = 'odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf'
PDF_DE_PRUEBA = (b'%PDF-1.4 cotizacion de prueba', 'pdf')


class CotizarCase(HerramientasCase):

    def setUp(self):
        super().setUp()
        self.parche_pdf = patch(RENDER, return_value=PDF_DE_PRUEBA)
        self.pdf = self.parche_pdf.start()
        self.addCleanup(self.parche_pdf.stop)

    def cotizar(self, *lineas, conv=None):
        return self.salida('cotizar', {'lineas': list(lineas)}, conv=conv)

    def ordenes(self, conv=None):
        return self.env['sale.order'].search([('partner_id', '=', (conv or self.conv).partner_id.id)], order='id')

    def avisos_con_pdf(self, conv=None):
        return (conv or self.conv).mensaje_ids.filtered(lambda m: m.tipo == 'aviso' and m.adjunto_ids)


@tagged('post_install', '-at_install')
class TestCotizarAutomatica(CotizarCase):

    def test_viene_encendida_de_fabrica(self):
        self.assertTrue(self.ajustes.cotizacion_automatica)

    def test_la_herramienta_esta_publicada_para_juan_con_su_esquema(self):
        catalogo = {t['name']: t for t in self.env['brian.herramientas'].with_user(self.juan).catalogo()}
        esquema = catalogo['juan_cotizar']['input_schema']
        self.assertEqual(esquema['required'], ['lineas'])
        self.assertEqual(esquema['properties']['lineas']['items']['required'], ['codigo'])

    def test_arma_la_cotizacion_con_los_totales_que_calcula_odoo(self):
        datos = self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 2}, {'codigo': 'zz-cama'})
        (orden,) = self.ordenes()
        self.assertTrue(datos['creada'])
        self.assertFalse(datos['reutilizada'])
        cotizacion = datos['cotizacion']
        self.assertEqual(cotizacion['numero'], orden.name)
        self.assertAlmostEqual(orden.amount_untaxed, 2 * 800.0 + 349.99)
        self.assertAlmostEqual(cotizacion['subtotal'], orden.amount_untaxed)
        self.assertAlmostEqual(cotizacion['itbms'], orden.amount_tax)
        self.assertAlmostEqual(cotizacion['total'], orden.amount_total)
        self.assertAlmostEqual(cotizacion['total'], 1949.99 * 1.07, places=2)
        self.assertEqual(cotizacion['subtotal_texto'], '$1,949.99')
        self.assertEqual(cotizacion['total_texto'], f'${orden.amount_total:,.2f}')
        sofa, cama = cotizacion['lineas']
        self.assertEqual((sofa['codigo'], sofa['cantidad'], sofa['precio_unitario_texto']),
                         ('ZZ-SOFA', 2, '$800.00 + ITBMS'))
        self.assertEqual((cama['codigo'], cama['cantidad'], cama['subtotal_texto']), ('ZZ-CAMA', 1, '$349.99'))
        self.assertEqual((sofa['disponibilidad'], cama['disponibilidad']), ('pocas', 'disponible'))
        self.assertIn('no es una venta', datos['nota'])

    def test_es_un_borrador_enviado_que_nunca_se_confirma_y_sin_descuentos(self):
        self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 1})
        (orden,) = self.ordenes()
        self.assertEqual(orden.state, 'sent', 'Enviada, no confirmada')
        self.assertFalse(orden.picking_ids, 'No reserva ni mueve existencias')
        self.assertFalse(orden.invoice_ids)
        self.assertEqual(orden.order_line.mapped('discount'), [0.0])
        self.assertEqual(orden.order_line.price_unit, 800.0, 'Precio de lista: el modelo no pone precios')
        nota = orden.message_ids.filtered(lambda m: 'Juan' in (m.body or ''))
        self.assertTrue(nota, 'la nota que dice que la armó Juan')
        self.assertIn('Sin confirmar', nota[0].body)

    def test_el_asistente_no_figura_como_vendedor_pero_si_alguien_la_atiende_es_suya(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertFalse(self.ordenes().user_id)
        otra = self.conversacion(nombre='Otra', id_externo='50769990000')
        otra.sudo().asignada_a = self.vendedora
        self.cotizar({'codigo': 'ZZ-SOFA'}, conv=otra)
        self.assertEqual(self.ordenes(otra).user_id, self.vendedora)

    def test_el_pdf_queda_en_un_aviso_del_hilo_con_url_firmada_de_vida_corta(self):
        datos = self.cotizar({'codigo': 'ZZ-CAMA'})
        (orden,) = self.ordenes()
        documento = datos['documento']
        self.assertEqual((documento['tipo'], documento['mime']), ('documento', 'application/pdf'))
        self.assertEqual(documento['nombre'], f'Cotizacion-{orden.name}.pdf')
        self.assertRegex(documento['url'], rf'/dcasa/adjunto/\d+/\d+/[0-9a-f]{{64}}/Cotizacion-{orden.name}\.pdf$')
        (aviso,) = self.avisos_con_pdf()
        self.assertEqual(aviso.direccion, 'interna', 'El aviso no sale por el canal: es para las vendedoras')
        self.assertIn(orden.name, aviso.texto)
        self.assertIn(datos['cotizacion']['total_texto'], aviso.texto)
        (adjunto,) = aviso.adjunto_ids
        self.assertEqual((adjunto.res_model, adjunto.res_id, adjunto.mimetype),
                         ('dcasa.mensaje', aviso.id, 'application/pdf'))
        self.assertEqual(adjunto.raw, PDF_DE_PRUEBA[0])
        self.assertIn(f'/dcasa/adjunto/{adjunto.id}/', documento['url'])
        # Las vendedoras lo ven en la pantalla como cualquier adjunto.
        self.assertEqual(aviso._como_dict()['adjuntos'][0]['nombre'], documento['nombre'])

    def test_no_habla_con_el_canal_ni_manda_nada_por_si_sola(self):
        with patch('odoo.addons.dcasa_conversaciones.models.cliente_worker.JuanCliente.enviar') as enviar:
            self.cotizar({'codigo': 'ZZ-CAMA'})
        enviar.assert_not_called()

    def test_la_misma_cotizacion_pedida_otra_vez_se_reutiliza(self):
        primera = self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 2}, {'codigo': 'ZZ-CAMA'})
        # Mismas líneas aunque lleguen en otro orden o repartidas: es la misma cotización.
        segunda = self.cotizar({'codigo': 'ZZ-CAMA'}, {'codigo': 'ZZ-SOFA', 'cantidad': 1}, {'codigo': 'ZZ-SOFA'})
        self.assertEqual(len(self.ordenes()), 1)
        self.assertTrue(segunda['reutilizada'])
        self.assertEqual(segunda['cotizacion']['numero'], primera['cotizacion']['numero'])
        self.assertTrue(segunda['documento']['url'])
        # Otras cantidades: es otra cotización.
        tercera = self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 3})
        self.assertFalse(tercera['reutilizada'])
        self.assertEqual(len(self.ordenes()), 2)

    def test_una_cotizacion_vieja_o_confirmada_no_se_reutiliza(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        (vieja,) = self.ordenes()
        self.env.cr.execute("UPDATE sale_order SET create_date = create_date - interval '3 hours' WHERE id = %s",
                            [vieja.id])
        self.env.invalidate_all()
        self.assertFalse(self.cotizar({'codigo': 'ZZ-SOFA'})['reutilizada'])
        nueva = self.ordenes()[-1]
        nueva.action_confirm()
        self.assertFalse(self.cotizar({'codigo': 'ZZ-SOFA'})['reutilizada'])
        self.assertEqual(len(self.ordenes()), 3)

    def test_las_de_otro_cliente_nunca_se_mezclan(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        otra = self.conversacion(nombre='Otra', id_externo='50769990000')
        datos = self.cotizar({'codigo': 'ZZ-SOFA'}, conv=otra)
        self.assertFalse(datos['reutilizada'])
        self.assertNotEqual(self.ordenes()[0], self.ordenes(otra)[0])

    def test_tope_de_cotizaciones_nuevas_por_cliente_y_por_dia(self):
        for cantidad in range(1, TOPE_NUEVAS_POR_DIA + 1):
            self.assertTrue(self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': cantidad})['creada'])
        pasada = self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': TOPE_NUEVAS_POR_DIA + 1})
        self.assertEqual((pasada['creada'], pasada['motivo']), (False, 'tope_diario'))
        self.assertIn('pasar_a_vendedora', pasada['mensaje'])
        self.assertEqual(len(self.ordenes()), TOPE_NUEVAS_POR_DIA)
        # Repetir una que ya existe no cuenta como nueva: se sigue pudiendo mandar de nuevo.
        self.assertTrue(self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 1})['reutilizada'])

    def test_cada_uso_queda_auditado_a_nombre_de_juan(self):
        self.cotizar({'codigo': 'ZZ-SOFA'})
        accion = self.env['brian.accion'].search([('herramienta', '=', 'juan_cotizar')], limit=1)
        self.assertTrue(accion)
        self.assertEqual(accion.create_uid, self.juan)


@tagged('post_install', '-at_install')
class TestCotizarApagada(CotizarCase):

    def test_apagada_no_arma_nada_y_manda_a_una_vendedora(self):
        self.ajustes.cotizacion_automatica = False
        datos = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual((datos['creada'], datos['motivo']), (False, 'apagada'))
        self.assertIn('pasar_a_vendedora', datos['mensaje'])
        self.assertNotIn('documento', datos)
        self.assertFalse(self.ordenes())
        self.assertFalse(self.avisos_con_pdf())
        self.pdf.assert_not_called()

    def test_encenderla_de_nuevo_la_deja_funcionando(self):
        self.ajustes.cotizacion_automatica = False
        self.assertFalse(self.cotizar({'codigo': 'ZZ-SOFA'})['creada'])
        self.ajustes.cotizacion_automatica = True
        self.assertTrue(self.cotizar({'codigo': 'ZZ-SOFA'})['creada'])

    def test_apagada_ni_siquiera_revisa_las_lineas(self):
        self.ajustes.cotizacion_automatica = False
        self.assertEqual(self.cotizar({'codigo': 'NO-EXISTE'})['motivo'], 'apagada')


@tagged('post_install', '-at_install')
class TestCotizarProductos(CotizarCase):

    def test_un_producto_sin_publicar_o_que_no_existe_no_se_cotiza(self):
        for codigo in ('ZZ-SECRETO', 'NO-EXISTE'):
            with self.subTest(codigo=codigo):
                datos = self.cotizar({'codigo': codigo})
                self.assertEqual((datos['creada'], datos['motivo']), (False, 'producto_no_encontrado'))
                self.assertIn(codigo, datos['mensaje'])
        self.assertFalse(self.ordenes())

    def test_si_una_linea_no_vale_no_se_arma_ninguna(self):
        datos = self.cotizar({'codigo': 'ZZ-SOFA'}, {'codigo': 'ZZ-SECRETO'})
        self.assertFalse(datos['creada'])
        self.assertFalse(self.ordenes())
        self.assertFalse(self.avisos_con_pdf())

    def test_los_comodines_de_la_busqueda_no_son_codigos(self):
        for codigo in ('ZZ-%', 'ZZ-_OFA', '%'):
            with self.subTest(codigo=codigo):
                self.assertEqual(self.cotizar({'codigo': codigo})['motivo'], 'producto_no_encontrado')
        self.assertFalse(self.ordenes())

    def test_un_producto_con_opciones_pide_elegir_y_con_la_opcion_se_cotiza(self):
        datos = self.cotizar({'codigo': 'ZZ-COL'})
        self.assertEqual((datos['creada'], datos['motivo']), (False, 'elegir_opcion'))
        self.assertEqual(len(datos['opciones']), 2)
        self.assertTrue(any('Zzqueen' in o for o in datos['opciones']))
        self.assertFalse(self.ordenes())
        datos = self.cotizar({'codigo': 'ZZ-COL', 'opcion': 'queen'})
        self.assertTrue(datos['creada'])
        (orden,) = self.ordenes()
        self.assertIn('Zzqueen', orden.order_line.product_id.display_name)
        self.assertEqual(orden.order_line.product_uom_qty, 1)
        # Una opción que no existe no adivina: vuelve a preguntar.
        self.assertEqual(self.cotizar({'codigo': 'ZZ-COL', 'opcion': 'redonda'})['motivo'], 'elegir_opcion')

    def test_cantidades_y_listas_mal_escritas_dan_un_error_que_el_modelo_puede_corregir(self):
        for lineas in ([], 'sofa', [{'codigo': 'ZZ-SOFA'}] * 0, [{'cantidad': 2}], ['ZZ-SOFA'], [{'codigo': ''}],
                       [{'codigo': 'ZZ-SOFA'}] * (MAX_LINEAS_AUTOMATICAS + 1)):
            with self.subTest(lineas=lineas):
                self.assertTrue(self.error('cotizar', {'lineas': lineas}))
        for cantidad in (0, -1, 1000, 2.5, 'dos', True):
            with self.subTest(cantidad=cantidad):
                self.assertIn('cantidad', self.error('cotizar', {'lineas': [{'codigo': 'ZZ-SOFA',
                                                                              'cantidad': cantidad}]}))
        self.assertFalse(self.ordenes())

    def test_tolera_la_lista_como_texto_json_y_la_cantidad_como_texto(self):
        lineas = json.dumps([{'codigo': 'ZZ-SOFA', 'cantidad': '2'}])
        self.assertTrue(self.salida('cotizar', {'lineas': lineas})['creada'])
        self.assertEqual(self.ordenes().order_line.product_uom_qty, 2)

    def test_el_modelo_no_puede_poner_precio_ni_descuento(self):
        datos = self.cotizar({'codigo': 'ZZ-SOFA', 'precio': 1.0, 'descuento': 50, 'precio_unitario': 1})
        self.assertTrue(datos['creada'])
        self.assertEqual(self.ordenes().order_line.price_unit, 800.0)
        self.assertEqual(self.ordenes().order_line.discount, 0)


@tagged('post_install', '-at_install')
class TestCotizarSinPdf(CotizarCase):

    def test_si_el_pdf_no_sale_no_se_cae_y_se_avisa_a_las_vendedoras(self):
        with patch(RENDER, return_value=(b'<html>no es pdf</html>', 'html')):
            datos = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual((datos['creada'], datos['motivo']), (False, 'sin_pdf'))
        self.assertNotIn('documento', datos)
        self.assertEqual(datos['cotizacion']['numero'], self.ordenes().name)
        self.assertIn('pasar_a_vendedora', datos['mensaje'])
        self.assertFalse(self.avisos_con_pdf())
        self.assertTrue(self.conv.mensaje_ids.filtered(lambda m: m.tipo == 'aviso' and 'no pudo generar' in m.texto))

    @mute_logger('odoo.addons.dcasa_conversaciones.models.herramientas_juan_cotizacion')
    def test_si_el_motor_de_pdf_revienta_tampoco(self):
        with patch(RENDER, side_effect=RuntimeError('wkhtmltopdf murió')):
            datos = self.cotizar({'codigo': 'ZZ-SOFA'})
        self.assertEqual(datos['motivo'], 'sin_pdf')


@tagged('post_install', '-at_install')
class TestCotizarPdfDeVerdad(HttpCase, HerramientasCase):
    """El PDF real, bajado por la misma URL firmada que usa el Worker."""

    @skipUnless(shutil.which('wkhtmltopdf') and _pypdf2_compatible(),
                'Falta wkhtmltopdf, o el PyPDF2 instalado no es el que pide Odoo (< 3)')
    def test_el_documento_se_baja_con_la_url_firmada_y_es_un_pdf(self):
        datos = self.salida('cotizar', {'lineas': [{'codigo': 'ZZ-CAMA'}]})
        ruta = re.sub(r'^https?://[^/]+', '', datos['documento']['url'])
        respuesta = self.url_open(ruta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b'%PDF'), 'Es un PDF de verdad, no el HTML del modo de pruebas')
        self.assertEqual(respuesta.headers['Content-Type'], 'application/pdf')
