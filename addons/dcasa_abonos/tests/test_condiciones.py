"""La hoja «Condiciones de abono» en dos copias (COPIA CLIENTE y COPIA EMPRESA).

Lo pidió la dueña (16 oct 2026): imprimir la hoja de condiciones que la tienda entrega con el abono, en dos copias y
con la marca de las facturas, con el código del producto. Lo que se comprueba:

* El texto inicial es la hoja transcrita, se escribe una sola vez y no pisa lo que el administrador cambie o borre.
* El informe trae las dos copias, el código público (DC-…) en la del cliente y la referencia del proveedor SOLO en la
  de la empresa; las fechas, el total, lo abonado y el saldo salen de ``_dcasa_estado_abono``.
* Vacío, no se imprime; sin pagos (o si no es una factura de cliente publicada), un error que se entiende.
* Cada copia cabe en UNA hoja (comprobado con el PDF de verdad): con muchos muebles solo se achica la tabla; en una
  factura enorme la lista se corta y dice cuántos faltan. Sin «Página 1 / 2» en el pie.
* La casilla del cuadro «Imprimir documentos»: marcada en el primer abono, desmarcada en los demás; el orden del PDF
  unido: factura/ABONO del cliente → condiciones (cliente y empresa) → lo demás.
* Nada de esto cambia un asiento.
"""
import shutil
from unittest import skipUnless
from unittest.mock import patch

from lxml import html as lxml_html

from odoo import Command, fields
from odoo.addons.dcasa_base.nombres import nombre_para_cliente
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.addons.dcasa_invoice.tests.documentos import DocumentosDePrueba
from odoo.addons.dcasa_invoice.tests.test_paquete import (
    PaqueteComun,
    _renderizar_falso,
    textos,
    textos_de_pdf_real,
)
from odoo.addons.dcasa_invoice.wizard.impresion_paquete import DcasaImpresionPaquete
from odoo.exceptions import AccessError, UserError
from odoo.tests import BaseCase, HttpCase, TransactionCase, tagged

from ..models import condiciones
from ..models.res_company import CONDICIONES_PUESTAS

INFORME = 'dcasa_abonos.action_report_condiciones_abono'
NOMBRE_INFORME = 'dcasa_abonos.report_condiciones_abono'
INFORME_FACTURA = 'account.report_invoice_with_payments'


def _texto(elemento):
    return ' '.join(elemento.text_content().split()) if elemento is not None else ''


def _monto(valor):
    """Como se imprime un monto en el papel: «$1,070.50» (pegado al símbolo)."""
    return f'${valor:,.2f}'


def foto_de_la_contabilidad(env):
    """Todo lo que la hoja NO puede cambiar: apuntes, conciliaciones y el estado de cada factura."""
    env.flush_all()
    env.invalidate_all()
    return (
        [(linea.id, linea.move_id.id, linea.account_id.id, linea.debit, linea.credit, linea.balance,
          linea.amount_residual, linea.reconciled, linea.tax_ids.ids)
         for linea in env['account.move.line'].search([], order='id')],
        env['account.partial.reconcile'].search_count([]),
        [(m.id, m.state, m.payment_state, m.amount_total, m.amount_residual)
         for m in env['account.move'].search([], order='id')],
    )


@tagged('post_install', '-at_install')
class TestCondicionesSinBase(BaseCase):
    """Las funciones puras: el texto inicial y cómo se lee lo que escribe la dueña."""

    def test_el_texto_inicial_es_la_hoja_de_la_tienda(self):
        lista = condiciones.lista_de_condiciones(condiciones.CONDICIONES_INICIALES)
        self.assertEqual(len(lista), 7)
        self.assertEqual(lista[0], 'Deberá presentar la factura original para poder retirar la mercancía abonada.')
        self.assertEqual(lista[1], 'Los artículos abonados no podrán ser cambiados por ningún otro artículo.')
        self.assertIn('se le penalizará con el 10% del valor total de la factura', lista[2])
        self.assertIn('en un periodo de tiempo no mayor a 3 meses', lista[3])
        self.assertEqual(lista[4], 'No podrá abonarse mercancía en ofertas, promociones o con descuentos.')
        self.assertIn('recargo sobre el valor de la factura del 15%', lista[5])
        self.assertEqual(lista[6], 'No hay devolución de dinero.')
        self.assertEqual(condiciones.TITULO_POR_DEFECTO, 'Condiciones de abono')

    def test_una_condicion_por_renglon_y_sin_el_numero_escrito_a_mano(self):
        self.assertEqual(condiciones.lista_de_condiciones('1) Uno\n\n  2. Dos  \n3 - Tres\n4: Cuatro\nCinco'),
                         ['Uno', 'Dos', 'Tres', 'Cuatro', 'Cinco'])
        self.assertEqual(condiciones.lista_de_condiciones('10% de penalidad'), ['10% de penalidad'],
                         'una cifra al inicio no es un número de renglón')
        self.assertEqual(condiciones.lista_de_condiciones(''), [])
        self.assertEqual(condiciones.lista_de_condiciones(None), [])
        self.assertEqual(condiciones.lista_de_condiciones(' \n \n'), [])

    def test_la_descripcion_del_cliente_no_repite_la_referencia_del_proveedor(self):
        quitar = condiciones.sin_referencia
        self.assertEqual(quitar('SOFÁ MODULAR (REF-9988) GRIS', 'REF-9988'), 'SOFÁ MODULAR GRIS')
        self.assertEqual(quitar('CAMA QUEEN / 1062010735N', '1062010735N'), 'CAMA QUEEN')
        self.assertEqual(quitar('ref-9988 Sofá', 'REF-9988'), 'Sofá')
        self.assertEqual(quitar('Sofá de 10 plazas', '10'), 'Sofá de 10 plazas', 'una referencia corta no se toca')
        self.assertEqual(quitar('MESA AB1234X', 'AB1234'), 'MESA AB1234X', 'solo la referencia suelta y completa')
        self.assertEqual(quitar('Silla', ''), 'Silla')

    def test_cada_copia_cabe_en_una_hoja(self):
        """Pocos muebles: tal cual. Muchos: solo la tabla se achica lo justo. Una factura enorme: la lista se corta a la
        escala mínima (y la hoja dice cuántos faltan). Lo medido en el PDF real está en ``TestCondicionesEnPdf``."""
        ajuste = condiciones.ajuste_a_una_hoja
        iniciales = condiciones.lista_de_condiciones(condiciones.CONDICIONES_INICIALES)
        largo = 'JUEGO DE SALA MODULAR 1 PIEZAS EN TELA ANTIMANCHAS COLOR GRIS OSCURO CON COJINES Y PATAS DE MADERA'
        self.assertEqual(ajuste(['COLCHON IMPERIAL TWIN', 'CAMA QUEEN GREY CON ESTANTES'], iniciales), (1.0, 2))
        self.assertEqual(ajuste([], iniciales), (1.0, 0))
        escala, cuantos = ajuste([largo] * 10, iniciales)
        self.assertEqual(cuantos, 10, 'diez muebles de nombre largo: todos, achicados')
        self.assertTrue(condiciones.ESCALA_MINIMA <= escala < 1, escala)
        lugar = condiciones.ALTO_DISPONIBLE - condiciones.ALTO_FIJO - condiciones.alto_condiciones(iniciales)
        self.assertLessEqual(condiciones.alto_tabla([largo] * 10, escala), lugar)
        self.assertGreater(condiciones.alto_tabla([largo] * 10, escala + 0.01), lugar, 'lo justo, ni más ni menos')
        escala, cuantos = ajuste(['SILLA COMEDOR'] * 40, iniciales)
        self.assertEqual(escala, condiciones.ESCALA_MINIMA)
        self.assertTrue(0 < cuantos < 40, cuantos)
        self.assertLessEqual(condiciones.alto_tabla(['SILLA COMEDOR'] * cuantos, escala, fila_extra=True), lugar)
        self.assertGreater(condiciones.alto_tabla(['SILLA COMEDOR'] * (cuantos + 1), escala, fila_extra=True), lugar)
        # Si lo que no cabe es el texto de las condiciones, no se esconden muebles: es el texto lo que hay que acortar.
        self.assertEqual(ajuste(['SILLA'] * 3, ['x' * 6000]), (condiciones.ESCALA_MINIMA, 3))
        # Achicada caben más letras por renglón; un salto de renglón escrito cuenta.
        self.assertEqual(condiciones.renglones(largo, condiciones.LETRAS_POR_RENGLON_MUEBLE), 2)
        self.assertEqual(condiciones.renglones(largo, condiciones.LETRAS_POR_RENGLON_MUEBLE / 0.6), 1)
        self.assertEqual(condiciones.renglones('SOFÁ\nCOLOR GRIS', 60), 2)
        self.assertEqual(condiciones.renglones('', 60), 1)

    def test_aviso_si_las_condiciones_no_dejan_lugar(self):
        self.assertFalse(condiciones.demasiado_largas(condiciones.lista_de_condiciones(condiciones.CONDICIONES_INICIALES)))
        self.assertFalse(condiciones.demasiado_largas([]))
        self.assertTrue(condiciones.demasiado_largas(['Una condición larguísima, repetida. ' * 12] * 8))


@tagged('post_install', '-at_install')
class TestTextoInicial(TransactionCase):
    """Se escribe una vez por base y nunca pisa lo que el administrador cambie o borre."""

    def test_al_instalar_quedo_la_hoja_de_la_tienda(self):
        empresa = self.env.ref('base.main_company')
        self.assertEqual(empresa.dcasa_abono_condiciones, condiciones.CONDICIONES_INICIALES)
        self.assertTrue(self.env['ir.config_parameter'].sudo().get_param(CONDICIONES_PUESTAS))
        self.assertFalse(empresa.dcasa_abono_condiciones_titulo, 'el título vacío imprime «Condiciones de abono»')
        self.assertEqual(empresa._dcasa_abono_condiciones_titulo(), 'Condiciones de abono')

    def test_no_pisa_lo_que_cambio_ni_lo_que_borro_el_administrador(self):
        Empresa = self.env['res.company']
        param = self.env['ir.config_parameter'].sudo()
        empresa = self.env.ref('base.main_company')
        empresa.dcasa_abono_condiciones = 'Mi condición propia.'
        Empresa._dcasa_abonos_poner_condiciones_iniciales()   # lo que hace cada actualización del módulo
        self.assertEqual(empresa.dcasa_abono_condiciones, 'Mi condición propia.')

        # Aunque se volviera a correr desde cero, solo se llenan las vacías.
        otra = Empresa.create({'name': 'Otra empresa abonos'})
        self.assertFalse(otra.dcasa_abono_condiciones)
        param.set_param(CONDICIONES_PUESTAS, False)
        Empresa._dcasa_abonos_poner_condiciones_iniciales()
        self.assertEqual(empresa.dcasa_abono_condiciones, 'Mi condición propia.')
        self.assertEqual(otra.dcasa_abono_condiciones, condiciones.CONDICIONES_INICIALES)
        self.assertTrue(param.get_param(CONDICIONES_PUESTAS))

        # Borrado a propósito (para no imprimir la hoja): sigue vacío.
        empresa.dcasa_abono_condiciones = False
        Empresa._dcasa_abonos_poner_condiciones_iniciales()
        self.assertFalse(empresa.dcasa_abono_condiciones)

    def test_aviso_en_ajustes_si_el_texto_no_deja_lugar(self):
        empresa = self.env.ref('base.main_company')
        empresa.dcasa_abono_condiciones = condiciones.CONDICIONES_INICIALES
        self.assertFalse(empresa.dcasa_abono_condiciones_larga)
        empresa.dcasa_abono_condiciones = '\n'.join(['Una condición larguísima, repetida. ' * 12] * 8)
        self.assertTrue(empresa.dcasa_abono_condiciones_larga)
        empresa.dcasa_abono_condiciones = False
        self.assertFalse(empresa.dcasa_abono_condiciones_larga)
        vista = self.env.ref('dcasa_abonos.view_company_form_dcasa_abonos')
        self.assertIn('invisible="not dcasa_abono_condiciones_larga"', vista.arch_db)

    def test_ajustes_solo_para_administradores(self):
        vista = self.env.ref('dcasa_abonos.view_company_form_dcasa_abonos')
        self.assertIn('groups="base.group_system"', vista.arch_db)
        admin = self.env.ref('base.user_admin')
        self.assertTrue(admin.has_group('base.group_system'))
        arch = self.env['res.company'].with_user(admin).get_view(
            self.env.ref('base.view_company_form').id, 'form')['arch']
        self.assertIn('name="dcasa_abono_condiciones"', arch)
        self.assertIn('name="dcasa_abono_condiciones_titulo"', arch)
        self.assertIn('name="dcasa_factura_garantia"', arch, 'junto a los textos de la factura')
        gerencia = crear_usuario(self.env, 'abono_gerencia_ajustes', 'dcasa_base.group_gerencia')
        arch_gerencia = self.env['res.company'].with_user(gerencia).get_view(
            self.env.ref('base.view_company_form').id, 'form')['arch']
        self.assertNotIn('name="dcasa_abono_condiciones"', arch_gerencia,
                         'la empresa solo la cambia un administrador; Gerencia no la ve editable')


@tagged('post_install', '-at_install')
class TestHojaDeCondiciones(DocumentosDePrueba):
    """La hoja impresa (HTML que wkhtmltopdf vuelve PDF) de la factura «completa» de los documentos aprobados."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.dcasa_abono_condiciones = condiciones.CONDICIONES_INICIALES
        cls.company.dcasa_abono_condiciones_titulo = False

    def _hoja(self, factura, usuario=None):
        """(árbol del HTML, {'cliente': copia, 'empresa': copia})."""
        informes = self.env['ir.actions.report']
        if usuario:
            informes = informes.with_user(usuario)
        contenido = informes._render_qweb_html(INFORME, factura.ids)[0].decode()
        arbol = lxml_html.document_fromstring(contenido)
        copias = {copia: arbol.xpath(f'//div[@name="dcasa_copia_{copia}"]') for copia in ('cliente', 'empresa')}
        for copia, encontradas in copias.items():
            self.assertEqual(len(encontradas), 1, f'falta (o sobra) la copia {copia}')
        return arbol, {copia: encontradas[0] for copia, encontradas in copias.items()}

    @staticmethod
    def _filas(copia):
        """({etiqueta: valor} de la factura y sus fechas, {etiqueta: monto} del total, lo abonado y el saldo)."""
        datos = {_texto(fila.find('th')): _texto(fila.find('td'))
                 for fila in copia.xpath('.//table[contains(@class, "o_dcasa_tabla_datos")]//tr')}
        totales = {_texto(fila[0]): _texto(fila[1])
                   for fila in copia.xpath('.//table[@name="dcasa_condiciones_totales"]//tr')}
        return datos, totales

    def _abonar(self, factura, monto, fecha='2026-10-14'):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': fecha, 'amount': monto, 'journal_id': self.banco.id})._create_payments()

    def _factura_con(self, cuantos, nombre):
        """Una factura con ``cuantos`` muebles de ese nombre y un abono."""
        producto = self.env['product.product'].create({'name': nombre, 'default_code': 'MUCHOS-1', 'type': 'consu'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': producto.id, 'quantity': 1, 'price_unit': 10.0})
                                 for _ in range(cuantos)]})
        factura.action_post()
        self._abonar(factura, 5.0)
        return factura

    # --- Las dos copias -----------------------------------------------------------------------

    def test_trae_las_dos_copias_con_la_marca_de_las_facturas(self):
        factura = self.factura_completa(abono=100.0)
        arbol, copias = self._hoja(factura)
        rotulos = [_texto(rotulo) for rotulo in arbol.xpath('//span[@name="dcasa_rotulo"]')]
        self.assertEqual(rotulos, ['COPIA CLIENTE', 'COPIA EMPRESA'])
        # La misma placa, banda y pie de las facturas (layout D'CASA), y una sola cabecera <h2> por factura.
        self.assertTrue(arbol.xpath('//div[contains(@class, "o_dcasa_band")]'), 'falta la banda de la placa')
        self.assertTrue(arbol.xpath('//div[contains(@class, "o_report_layout_dcasa")]'))
        self.assertTrue(arbol.xpath('//div[contains(@class, "o_dcasa_footer")]'))
        titulos = arbol.xpath('//h2')
        self.assertEqual(len(titulos), 1, 'una cabecera por factura: así Odoo parte el PDF de varias facturas')
        self.assertTrue(_texto(titulos[0]).startswith('Condiciones de abono'), _texto(titulos[0]))
        self.assertIn('COPIA CLIENTE', _texto(titulos[0]))
        self.assertIn('COPIA EMPRESA', _texto(arbol.xpath('//div[@name="dcasa_titulo_empresa"]')[0]))
        # La copia de la empresa empieza en su propia hoja (después del salto).
        orden = [elemento.get('name') for elemento in arbol.iter()
                 if elemento.get('name') in ('dcasa_copia_cliente', 'dcasa_salto', 'dcasa_copia_empresa')]
        self.assertEqual(orden, ['dcasa_copia_cliente', 'dcasa_salto', 'dcasa_copia_empresa'])

        estado = factura._dcasa_estado_abono()
        for nombre, copia in copias.items():
            with self.subTest(nombre):
                texto = _texto(copia)
                self.assertIn('CLIENTE DE PRUEBA', texto)
                self.assertIn(f'Cédula: {self.cliente.dcasa_ruc_display}', texto)
                datos, totales = self._filas(copia)
                self.assertEqual(datos, {
                    'Número de factura': factura.name,
                    'Fecha de inicio del abono': '14/10/2026',
                    'Fecha de vencimiento': '13/11/2026',   # 30 días continuos (decisión de la gerencia A3)
                })
                self.assertEqual(totales, {
                    'Total de la factura': _monto(estado['total']),
                    'Abonado': _monto(100.0),
                    'Saldo por pagar': _monto(estado['saldo']),
                })
                self.assertEqual(estado['saldo'], factura.amount_residual)
                lista = [_texto(li) for li in copia.xpath('.//div[@name="dcasa_condiciones_lista"]//li')]
                self.assertEqual(lista, condiciones.lista_de_condiciones(condiciones.CONDICIONES_INICIALES))
                self.assertIn('FIRMA DEL CLIENTE', texto)
                self.assertIn('NÚMERO DE CÉDULA', texto)

    def test_la_copia_del_cliente_lleva_el_codigo_publico_y_no_la_referencia_del_proveedor(self):
        factura = self.factura_completa(abono=100.0)
        _arbol, copias = self._hoja(factura)
        colchon, cama = self.colchon.dcasa_codigo_publico, self.cama.dcasa_codigo_publico
        self.assertTrue(colchon.startswith('DC-') and cama.startswith('DC-'))

        cliente = copias['cliente']
        codigos = [_texto(td) for td in cliente.xpath('.//td[@name="dcasa_td_codigo"]')]
        self.assertEqual(codigos, [colchon, cama], 'los muebles, sin el flete')
        self.assertFalse(cliente.xpath('.//*[@name="dcasa_td_referencia" or @name="dcasa_th_referencia"]'))
        texto_cliente = _texto(cliente)
        for referencia in ('IM-2001', '1062010735N'):
            self.assertNotIn(referencia, texto_cliente, 'el cliente no ve la referencia del proveedor')
        # La copia del cliente, en formato título (F5); la de la empresa, con el nombre guardado.
        self.assertIn('Colchon Imperial Twin 3/4 Buen Sueño', texto_cliente)
        self.assertIn('Cama Queen Grey con Estantes', texto_cliente)
        for flete in (self.flete.name, nombre_para_cliente(self.flete.name)):
            self.assertNotIn(flete, texto_cliente, 'el flete no es un mueble abonado')

        empresa = copias['empresa']
        self.assertEqual([_texto(td) for td in empresa.xpath('.//td[@name="dcasa_td_codigo"]')], [colchon, cama])
        self.assertEqual([_texto(td) for td in empresa.xpath('.//td[@name="dcasa_td_referencia"]')],
                         ['IM-2001', '1062010735N'], 'la empresa ve además la referencia del proveedor')
        self.assertIn('COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO', _texto(empresa))

    def test_el_titulo_se_cambia_en_la_empresa(self):
        factura = self.factura_completa(abono=100.0)
        self.company.dcasa_abono_condiciones_titulo = 'Condiciones del apartado'
        arbol, _copias = self._hoja(factura)
        self.assertTrue(_texto(arbol.xpath('//h2')[0]).startswith('Condiciones del apartado'))
        self.assertIn('Condiciones del apartado', _texto(arbol.xpath('//div[@name="dcasa_titulo_empresa"]')[0]))
        # Las condiciones que escriba la dueña, numeradas por la hoja.
        self.company.dcasa_abono_condiciones = '1) Primera condición.\n\nSegunda condición.'
        _arbol, copias = self._hoja(factura)
        lista = [_texto(li) for li in copias['empresa'].xpath('.//div[@name="dcasa_condiciones_lista"]//li')]
        self.assertEqual(lista, ['Primera condición.', 'Segunda condición.'])

    def test_pagada_por_completo_se_puede_reimprimir_sin_vencimiento(self):
        factura = self.factura_completa(abono=100.0)
        self._abonar(factura, factura.amount_residual)
        self.assertTrue(factura._dcasa_is_paid())
        _arbol, copias = self._hoja(factura)
        datos, totales = self._filas(copias['cliente'])
        self.assertEqual(totales['Saldo por pagar'], _monto(0.0))
        self.assertEqual(totales['Abonado'], _monto(factura.amount_total))
        self.assertEqual(datos['Fecha de inicio del abono'], '14/10/2026')
        self.assertEqual(datos['Fecha de vencimiento'], '')
        self.assertTrue(copias['cliente'].xpath('.//span[contains(@class, "o_dcasa_en_blanco")]'),
                        'sin saldo no hay vencimiento: queda la raya en blanco')

    def test_con_muchos_muebles_solo_se_achica_la_tabla_y_si_no_cabe_dice_cuantos_faltan(self):
        pocos = self.factura_completa(abono=100.0)
        self.assertEqual(pocos._dcasa_condiciones_hoja()['escala'], 1.0)
        _arbol, copias = self._hoja(pocos)
        for copia in copias.values():
            self.assertIsNone(copia.xpath('.//table[@name="dcasa_condiciones_muebles"]')[0].get('style'))
            self.assertFalse(copia.xpath('.//*[@name="dcasa_condiciones_faltan"]'))

        largo = 'JUEGO DE SALA MODULAR EN TELA ANTIMANCHAS COLOR GRIS OSCURO CON COJINES Y PATAS DE MADERA'
        diez = self._factura_con(10, largo)
        hoja = diez._dcasa_condiciones_hoja()
        self.assertEqual((len(hoja['muebles']), hoja['faltan']), (10, 0), 'diez muebles: todos')
        self.assertTrue(condiciones.ESCALA_MINIMA <= hoja['escala'] < 1, hoja['escala'])
        _arbol, copias = self._hoja(diez)
        for nombre, copia in copias.items():
            with self.subTest(nombre):
                tabla = copia.xpath('.//table[@name="dcasa_condiciones_muebles"]')[0]
                self.assertEqual(tabla.get('style'), f"zoom: {hoja['escala']};", 'solo la tabla se achica')
                self.assertIsNone(copia.get('style'), 'las condiciones, los totales y las firmas nunca se achican')
                self.assertEqual(len(copia.xpath('.//td[@name="dcasa_td_codigo"]')), 10)

        enorme = self._factura_con(40, 'SILLA COMEDOR')
        hoja = enorme._dcasa_condiciones_hoja()
        self.assertEqual(hoja['escala'], condiciones.ESCALA_MINIMA)
        self.assertTrue(hoja['faltan'] > 0 and len(hoja['muebles']) + hoja['faltan'] == 40, hoja['faltan'])
        _arbol, copias = self._hoja(enorme)
        for nombre, copia in copias.items():
            with self.subTest(nombre):
                self.assertEqual(len(copia.xpath('.//td[@name="dcasa_td_codigo"]')), len(hoja['muebles']))
                self.assertEqual(
                    _texto(copia.xpath('.//*[@name="dcasa_condiciones_faltan"]')[0]),
                    f"Y {hoja['faltan']} muebles más de esta factura: están todos en la factura {enorme.name}.")

    # --- Cuándo no se imprime -----------------------------------------------------------------

    def test_vacio_no_se_imprime(self):
        factura = self.factura_completa(abono=100.0)
        for vacio in (False, '', '  \n\n  '):
            with self.subTest(repr(vacio)):
                self.company.dcasa_abono_condiciones = vacio
                with self.assertRaisesRegex(UserError, 'no hay condiciones de abono escritas'):
                    self._hoja(factura)
                self.assertFalse(factura._dcasa_condiciones_imprimible())

    def test_sin_pagos_o_sin_ser_factura_de_cliente_un_error_claro(self):
        sin_pagos = self.factura_completa(abono=0)
        with self.assertRaisesRegex(UserError, 'todavía no tiene ningún abono registrado'):
            self._hoja(sin_pagos)
        borrador = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': self.cama.id, 'quantity': 1, 'price_unit': 10.0})]})
        proveedor = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': self.cama.id, 'quantity': 1, 'price_unit': 60.0})]})
        proveedor.action_post()
        self._abonar(proveedor, 10.0)
        self.assertEqual(proveedor.payment_state, 'partial')
        for factura in (borrador, proveedor):
            with self.subTest(factura.move_type), \
                    self.assertRaisesRegex(UserError, 'no es una factura de cliente publicada'):
                self._hoja(factura)
        # En el menú «Imprimir» solo aparece en la factura de cliente con algún pago.
        informe = self.env.ref(INFORME)
        con_abono = self.factura_completa(abono=100.0)
        self.assertEqual(informe.get_valid_action_reports('account.move', con_abono.ids), [informe.id])
        for factura in (sin_pagos, borrador, proveedor):
            self.assertEqual(informe.get_valid_action_reports('account.move', factura.ids), [], factura.move_type)
        self.assertEqual((informe.model, informe.binding_model_id.model, informe.binding_type),
                         ('account.move', 'account.move', 'report'))
        self.assertFalse(informe.is_invoice_report, 'no compite con la factura como plantilla del cliente')

    def test_solo_quien_factura_la_imprime_y_no_un_cliente_del_portal(self):
        factura = self.factura_completa(abono=100.0)
        vendedora = crear_usuario(self.env, 'abono_vendedora_hoja', 'dcasa_base.group_vendedora')
        factura.invoice_user_id = vendedora   # «Cada vendedora ve solo sus documentos»: imprime la de ella
        _arbol, copias = self._hoja(factura.with_user(vendedora), usuario=vendedora)
        self.assertIn(self.colchon.dcasa_codigo_publico, _texto(copias['cliente']))
        otra = crear_usuario(self.env, 'abono_otra_vendedora_hoja', 'dcasa_base.group_vendedora')
        with self.assertRaises(AccessError, msg='la hoja de la factura de otra vendedora no se imprime'):
            self._hoja(factura, usuario=otra)
        portal = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Portal abonos', 'login': 'abono_portal_hoja', 'partner_id': self.cliente.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])]})
        with self.assertRaises(AccessError):
            self._hoja(factura, usuario=portal)

    # --- La contabilidad ----------------------------------------------------------------------

    def test_imprimir_la_hoja_no_cambia_ni_un_asiento(self):
        factura = self.factura_completa(abono=100.0)
        antes = foto_de_la_contabilidad(self.env)
        self._hoja(factura)
        factura._dcasa_condiciones_muebles()
        factura._dcasa_primer_abono()
        factura._dcasa_condiciones_imprimible()
        cuadro = self.env['dcasa.impresion.paquete'].browse(factura.action_dcasa_imprimir_documentos()['res_id'])
        self.assertTrue(cuadro.incluir_condiciones)
        cuadro.action_imprimir()
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = cuadro._armar_pdf(factura, cuadro._claves_marcadas())
        self.assertEqual(len(textos(contenido)), 3)
        self.assertEqual(foto_de_la_contabilidad(self.env), antes)


@tagged('post_install', '-at_install')
class TestCuadroConCondiciones(PaqueteComun):
    """La casilla «Condiciones de abono (2 copias)» del cuadro «Imprimir documentos» y el orden del PDF unido."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.dcasa_abono_condiciones = condiciones.CONDICIONES_INICIALES
        cls.company.dcasa_ofrecer_impresion_pago = True

    def _cuadro(self, accion):
        self.assertEqual(accion.get('res_model'), 'dcasa.impresion.paquete', accion)
        return self.Paquete.browse(accion['res_id'])

    def test_marcada_en_el_primer_abono_y_desmarcada_en_los_demas(self):
        _pedido, factura = self._venta()
        primero = self._cuadro(self._pagar(factura, monto=10.0))
        self.assertTrue(factura._dcasa_primer_abono())
        self.assertTrue(primero.condiciones_disponibles)
        self.assertTrue(primero.incluir_condiciones, 'primer abono: la hoja viene marcada')
        self.assertEqual(primero._claves_marcadas(), ['cliente', 'condiciones', 'copia'])
        self.assertEqual(primero.action_imprimir()['params']['url'],
                         f'/dcasa/paquete.pdf?facturas={factura.id}&docs=cliente,condiciones,copia')

        segundo = self._cuadro(self._pagar(factura, monto=10.0))
        self.assertEqual(factura.payment_state, 'partial')
        self.assertFalse(factura._dcasa_primer_abono())
        self.assertTrue(segundo.condiciones_disponibles, 'se puede marcar a mano para volver a imprimirla')
        self.assertFalse(segundo.incluir_condiciones, 'segundo abono: viene desmarcada')
        self.assertEqual(segundo._claves_marcadas(), ['cliente', 'copia'])
        # Abierto a mano desde la factura, igual.
        self.assertFalse(self._cuadro(factura.action_dcasa_imprimir_documentos()).incluir_condiciones)

        ultimo = self._cuadro(self._pagar(factura))
        self.assertTrue(factura._dcasa_is_paid())
        self.assertFalse(ultimo.incluir_condiciones)
        self.assertTrue(ultimo.condiciones_disponibles)

    def test_sin_pagos_o_sin_condiciones_la_casilla_no_se_ofrece(self):
        _pedido, sin_pagos = self._venta()
        cuadro = self._cuadro(sin_pagos.action_dcasa_imprimir_documentos())
        self.assertFalse(cuadro.condiciones_disponibles or cuadro.incluir_condiciones)
        self.assertEqual(cuadro._claves_marcadas(), ['entrega', 'cliente', 'copia'], 'como siempre')

        self.company.dcasa_abono_condiciones = False
        _otro, en_abono = self._venta()
        cuadro = self._cuadro(self._pagar(en_abono, monto=10.0))
        self.assertTrue(en_abono._dcasa_primer_abono())
        self.assertFalse(cuadro.condiciones_disponibles or cuadro.incluir_condiciones, 'vacío: la hoja no se imprime')
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = self.Paquete._armar_pdf(en_abono, ['cliente', 'condiciones', 'copia'])
            self.assertEqual(len(textos(contenido)), 2, 'sin condiciones escritas, la hoja no sale')
            with self.assertRaisesRegex(UserError, 'Ninguna de las facturas elegidas las puede llevar'):
                self.Paquete._armar_pdf(en_abono, ['condiciones'])
            with self.assertRaisesRegex(UserError, 'Ninguna de las facturas elegidas las puede llevar'):
                self.Paquete._armar_pdf(sin_pagos, ['condiciones'])

    def test_el_pdf_va_abono_condiciones_y_lo_demas_aunque_se_pida_al_reves(self):
        pedido, factura = self._venta()
        self._pagar(factura, monto=10.0, contexto={'dcasa_sin_oferta_impresion': True})
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            for claves in (['cliente', 'condiciones', 'copia'], ['copia', 'condiciones', 'cliente']):
                paginas = textos(self.Paquete._armar_pdf(factura, claves)[0])
                self.assertEqual(len(paginas), 3, claves)
                self.assertIn(INFORME_FACTURA, paginas[0], claves)
                self.assertNotIn('COPIA EMPRESA', paginas[0], claves)
                self.assertIn(NOMBRE_INFORME, paginas[1], claves)
                self.assertIn(factura.name, paginas[1], claves)
                self.assertIn(INFORME_FACTURA, paginas[2], claves)
                self.assertIn('COPIA EMPRESA', paginas[2], claves)
            # Con la nota de entrega marcada a mano, la entrega sigue yendo primero (la hoja que se despacha).
            paginas = textos(self.Paquete._armar_pdf(factura, ['entrega', 'cliente', 'condiciones', 'copia'])[0])
        self.assertEqual(len(paginas), 4)
        self.assertIn(pedido.picking_ids.name, paginas[0])
        self.assertIn(INFORME_FACTURA, paginas[1])
        self.assertIn(NOMBRE_INFORME, paginas[2])
        self.assertIn('COPIA EMPRESA', paginas[3])

    def test_varias_facturas_solo_la_que_tiene_abono_lleva_la_hoja(self):
        _p1, en_abono = self._venta()
        _p2, sin_pagos = self._venta()
        self._pagar(en_abono, monto=10.0, contexto={'dcasa_sin_oferta_impresion': True})
        cuadro = self._cuadro((en_abono | sin_pagos).action_dcasa_imprimir_documentos())
        self.assertTrue(cuadro.condiciones_disponibles and cuadro.incluir_condiciones)
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            paginas = textos(self.Paquete._armar_pdf(en_abono | sin_pagos, ['cliente', 'condiciones', 'copia'])[0])
        self.assertEqual(len(paginas), 5)
        self.assertEqual([NOMBRE_INFORME in pagina for pagina in paginas], [False, True, False, False, False])
        self.assertIn(en_abono.name, paginas[1])

    def test_la_casilla_esta_entre_la_factura_y_la_copia(self):
        arch = self.env['dcasa.impresion.paquete'].get_view(view_type='form')['arch']
        self.assertIn('name="incluir_condiciones"', arch)
        self.assertLess(arch.index('name="incluir_cliente"'), arch.index('name="incluir_condiciones"'))
        self.assertLess(arch.index('name="incluir_condiciones"'), arch.index('name="incluir_copia"'))
        campo = self.env['dcasa.impresion.paquete']._fields['incluir_condiciones']
        self.assertEqual(campo.string, 'Condiciones de abono (2 copias)')

    def test_la_vendedora_la_imprime_en_el_paquete(self):
        _pedido, factura = self._venta()
        self._pagar(factura, monto=10.0, contexto={'dcasa_sin_oferta_impresion': True})
        como_vendedora = factura.with_user(self.vendedora)
        cuadro = self.Paquete.with_user(self.vendedora).browse(
            como_vendedora.action_dcasa_imprimir_documentos()['res_id'])
        self.assertTrue(cuadro.incluir_condiciones)
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = self.Paquete.with_user(self.vendedora)._armar_pdf(
                como_vendedora, cuadro._claves_marcadas())
        self.assertEqual(len(textos(contenido)), 3)

    def test_ofrecer_la_hoja_no_cambia_ni_un_asiento(self):
        _p1, con_hoja = self._venta()
        _p2, sin_hoja = self._venta()

        def asientos(factura):
            pagos = factura._get_reconciled_payments()
            lineas = (factura | pagos.move_id).line_ids.sorted(
                lambda linea: (linea.move_id.move_type, linea.account_id.code, linea.debit, linea.credit))
            return [(linea.move_id.move_type, linea.account_id.id, linea.debit, linea.credit, linea.amount_residual,
                     linea.reconciled, linea.tax_ids.ids) for linea in lineas], (
                factura.payment_state, factura.amount_residual, factura.amount_total, factura.amount_tax)

        self.assertTrue(self._cuadro(self._pagar(con_hoja, monto=30.0)).incluir_condiciones)
        self.company.dcasa_abono_condiciones = False
        self.assertFalse(self._cuadro(self._pagar(sin_hoja, monto=30.0)).incluir_condiciones)
        self.assertEqual(asientos(con_hoja), asientos(sin_hoja), 'con o sin la hoja, el abono es el mismo')


@tagged('post_install', '-at_install')
class TestCondicionesEnPdf(HttpCase):
    """El PDF de verdad (wkhtmltopdf): dos páginas por factura y el orden del paquete."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('base.main_company').dcasa_abono_condiciones = condiciones.CONDICIONES_INICIALES
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE PDF CONDICIONES'})
        cls.producto = cls.env['product.product'].create({
            'name': 'SOFÁ PDF CONDICIONES', 'default_code': 'REFPDF-77', 'type': 'consu'})

    def _factura_con_abono(self, total=500.0, abono=120.0):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': total,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': fields.Date.today(), 'amount': abono})._create_payments()
        return factura

    @skipUnless(shutil.which('wkhtmltopdf') and shutil.which('pdftotext'), 'sin wkhtmltopdf o pdftotext')
    def test_dos_paginas_y_el_orden_del_paquete(self):
        factura = self._factura_con_abono()
        codigo = self.producto.dcasa_codigo_publico
        pdf, _tipo = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
            INFORME, factura.ids)
        paginas = textos_de_pdf_real(pdf)
        self.assertEqual(len(paginas), 2, 'COPIA CLIENTE y COPIA EMPRESA, una hoja cada una')
        cliente, empresa = paginas
        self.assertIn('COPIA CLIENTE', cliente)
        self.assertNotIn('COPIA EMPRESA', cliente)
        self.assertIn('COPIA EMPRESA', empresa)
        for pagina in paginas:
            self.assertIn('CONDICIONES DE ABONO', pagina.upper())
            self.assertIn(codigo, pagina)
            self.assertIn('$380.00', pagina)
            self.assertIn('FIRMA DEL CLIENTE', pagina)
            self.assertIn('NÚMERO DE CÉDULA', pagina)
            self.assertIn('No hay devolución de dinero.', pagina)
            self.assertNotIn('Página', pagina, 'cada copia es una hoja suelta: sin «Página 1 / 2» en el pie')
        self.assertNotIn('REFPDF-77', cliente)
        self.assertIn('REFPDF-77', empresa)

        # El paquete: ABONO del cliente → condiciones (cliente y empresa) → copia de la empresa de la factura.
        contenido, _nombre = self.env['dcasa.impresion.paquete'].with_context(force_report_rendering=True)._armar_pdf(
            factura, ['copia', 'condiciones', 'cliente'])
        paginas = textos_de_pdf_real(contenido)
        self.assertEqual(len(paginas), 4)
        self.assertIn('SALDO POR PAGAR', paginas[0])
        self.assertIn('COPIA CLIENTE', paginas[1])
        self.assertIn('COPIA EMPRESA', paginas[2])
        self.assertIn('CONDICIONES DE ABONO', paginas[2].upper())
        self.assertIn('SALDO POR PAGAR', paginas[3])
        self.assertIn('COPIA EMPRESA', paginas[3], 'la cinta de la copia de la factura')
        self.assertIn('Página 1 / 1', paginas[0], 'la factura conserva su número de página')

        # Dos facturas: Odoo parte el PDF por factura (una cabecera <h2> por factura) y cada una lleva sus dos hojas.
        otra = self._factura_con_abono(total=300.0, abono=50.0)
        contenido, _nombre = self.env['dcasa.impresion.paquete'].with_context(force_report_rendering=True)._armar_pdf(
            factura | otra, ['condiciones'])
        paginas = textos_de_pdf_real(contenido)
        self.assertEqual(len(paginas), 4)
        for pagina, (nombre, saldo) in zip(paginas, [(factura.name, '$380.00')] * 2 + [(otra.name, '$250.00')] * 2,
                                           strict=True):
            self.assertIn(nombre, pagina)
            self.assertIn(saldo, pagina)

    @skipUnless(shutil.which('wkhtmltopdf') and shutil.which('pdftotext'), 'sin wkhtmltopdf o pdftotext')
    def test_con_muchos_muebles_cada_copia_sigue_en_una_hoja(self):
        """Lo que estima ``ajuste_a_una_hoja``, comprobado con el PDF de verdad: muebles de nombre largo (la tabla se
        achica) y una factura enorme (la lista se corta y dice cuántos faltan). Siempre dos hojas, una por copia."""
        largo = 'JUEGO DE SALA MODULAR {n} PIEZAS EN TELA ANTIMANCHAS COLOR GRIS OSCURO CON COJINES Y PATAS DE MADERA'
        for cuantos, nombre in ((7, largo), (12, largo), (40, 'SILLA COMEDOR {n}')):
            with self.subTest(cuantos=cuantos):
                productos = self.env['product.product'].create([
                    {'name': nombre.format(n=n), 'default_code': f'MUCHOS-{n:04d}', 'type': 'consu'}
                    for n in range(1, cuantos + 1)])
                factura = self.env['account.move'].create({
                    'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
                    'invoice_line_ids': [Command.create({'product_id': producto.id, 'quantity': 1, 'price_unit': 10.0,
                                                         'tax_ids': [Command.clear()]}) for producto in productos]})
                factura.action_post()
                self.env['account.payment.register'].with_context(
                    active_model='account.move', active_ids=factura.ids,
                ).create({'payment_date': fields.Date.today(), 'amount': 5.0})._create_payments()
                hoja = factura._dcasa_condiciones_hoja()
                pdf, _tipo = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
                    INFORME, factura.ids)
                paginas = textos_de_pdf_real(pdf)
                self.assertEqual(len(paginas), 2, f'{cuantos} muebles, escala {hoja["escala"]}: una hoja por copia')
                self.assertIn('COPIA CLIENTE', paginas[0])
                self.assertIn('COPIA EMPRESA', paginas[1])
                for pagina in paginas:
                    self.assertIn('FIRMA DEL CLIENTE', pagina)
                    self.assertIn('No hay devolución de dinero.', pagina)
                    self.assertIn(productos[0].dcasa_codigo_publico, pagina)
                    if hoja['faltan']:
                        self.assertIn(f"Y {hoja['faltan']} muebles más de esta factura", pagina)
                    else:
                        self.assertIn(productos[-1].dcasa_codigo_publico, pagina)
                self.assertEqual(bool(hoja['faltan']), cuantos == 40)
