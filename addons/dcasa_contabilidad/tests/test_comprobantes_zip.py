"""ZIP de comprobantes (I6): todo lo del periodo, por carpetas, con índice, en piezas y sin dejar entrar documentos que
quien lo pide no puede ver."""
import base64
import csv
import io
import os
import zipfile
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_contabilidad import ContabilidadCommon

MODULO = 'odoo.addons.dcasa_contabilidad.models.comprobantes_zip'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5E'
                       'rkJggg==')


@tagged('post_install', '-at_install')
class TestComprobantesZip(ContabilidadCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contador = new_test_user(cls.env, login='zip_contador', name='Zip Contador',
                                     groups='base.group_user,account.group_account_user')
        cls.vendedora = new_test_user(cls.env, login='zip_vendedora', name='Zip Vendedora',
                                      groups='base.group_user,dcasa_base.group_vendedora')

    def _datos(self):
        factura = self._factura(100.0, '2030-03-10')
        nota = self._factura(20.0, '2030-03-11', tipo='out_refund')
        compra_con = self._factura(50.0, '2030-03-12', tipo='in_invoice')
        compra_sin = self._factura(30.0, '2030-03-13', tipo='in_invoice')
        self.env['ir.attachment'].create({'name': 'factura proveedor.png', 'raw': PNG, 'res_model': 'account.move',
                                          'res_id': compra_con.id})
        cobro = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 107.0,
            'journal_id': self.banco.id, 'date': '2030-03-14'})
        cobro.action_post()
        pago = self.env['account.payment'].create({
            'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.proveedor.id, 'amount': 53.5,
            'journal_id': self.banco.id, 'date': '2030-03-15'})
        pago.action_post()
        self.env['ir.attachment'].create({'name': 'transferencia.pdf', 'raw': b'%PDF-1.4 prueba',
                                          'res_model': 'account.payment', 'res_id': pago.id})
        fuera = self._factura(999.0, '2030-05-01')            # fuera del rango: no entra
        return factura, nota, compra_con, compra_sin, cobro, pago, fuera

    def _paquete(self, usuario=None):
        return self.env['dcasa.comprobantes.paquete'].with_user(usuario or self.contador).create({
            'periodo': 'rango', 'desde': '2030-03-01', 'hasta': '2030-03-31'})

    def _abrir(self, adjunto):
        return zipfile.ZipFile(io.BytesIO(adjunto.raw))

    def test_todo_el_periodo_por_carpetas_con_indice(self):
        factura, nota, compra_con, compra_sin, cobro, pago, fuera = self._datos()
        paquete = self._paquete()
        paquete.action_preparar()
        self.assertEqual(paquete.estado, 'preparando')
        self.assertEqual(paquete.total, 6, 'factura, nota, 2 compras, cobro y el pago con adjunto')
        self.assertTrue(paquete._procesar())
        self.assertEqual(paquete.estado, 'listo')
        self.assertEqual(len(paquete.adjunto_ids), 1)
        with self._abrir(paquete.adjunto_ids) as zip_:
            nombres = zip_.namelist()
            carpetas = {n.split('/')[0] for n in nombres if '/' in n}
            self.assertEqual(carpetas, {'01 Facturas de clientes', '02 Notas de credito',
                                        '03 Recibos de cobros y abonos', '04 Compras', '05 Pagos a proveedores'})
            self.assertIn('INDICE.csv', nombres)
            self.assertIn('5 años', zip_.read('LEEME.txt').decode())
            indice = list(csv.DictReader(io.StringIO(zip_.read('INDICE.csv').decode('utf-8-sig'))))
            self.assertIn(b'%PDF-1.4 prueba', [zip_.read(n) for n in nombres if n.startswith('05 ')])
        numeros = {fila['Número'] for fila in indice}
        self.assertTrue({factura.name, nota.name, compra_con.name, compra_sin.name}.issubset(numeros))
        self.assertNotIn(fuera.name, numeros)
        sin_adjunto = [f for f in indice if f['Número'] == compra_sin.name]
        self.assertIn('papel', sin_adjunto[0]['Nota'])
        self.assertIn('sin documento adjunto', paquete.resumen)
        self.assertTrue(any(m.partner_ids == self.contador.partner_id for m in paquete.message_ids),
                        'le avisa a quien lo pidió')

    def test_en_piezas_y_solo_la_ultima_lleva_el_indice(self):
        self._datos()
        paquete = self._paquete()
        paquete.action_preparar()
        with patch(f'{MODULO}.MAX_PARTE', 1):
            paquete._procesar()
        self.assertGreater(len(paquete.adjunto_ids), 1)
        partes = paquete.adjunto_ids.sorted('id')
        self.assertTrue(partes[0].name.endswith('_parte_1.zip'))
        for parte in partes[:-1]:
            with self._abrir(parte) as zip_:
                self.assertNotIn('INDICE.csv', zip_.namelist())
        with self._abrir(partes[-1]) as zip_:
            indice = zip_.read('INDICE.csv').decode('utf-8-sig')
        self.assertEqual(indice.count('\n') - 1, len(paquete.linea_ids))

    def test_si_el_servidor_se_reinicia_a_media_pieza_se_rehace_sin_duplicar(self):
        self._datos()
        paquete = self._paquete()
        paquete.action_preparar()
        self.assertFalse(paquete._procesar(tiempo_disponible=lambda: 0))      # una tanda corta: queda a medias
        self.assertEqual(paquete.hechos, 1)
        os.remove(paquete._ruta_temporal())                                    # el contenedor perdió el disco
        self.assertTrue(paquete._procesar())
        with self._abrir(paquete.adjunto_ids) as zip_:
            documentos = [n for n in zip_.namelist() if '/' in n]
        self.assertEqual(len(documentos), len(set(documentos)))
        self.assertEqual(len(paquete.linea_ids), 6)

    def test_sin_comprobantes_en_el_periodo_lo_dice(self):
        paquete = self.env['dcasa.comprobantes.paquete'].with_user(self.contador).create(
            {'periodo': 'anio', 'anio': 1990})
        self.assertEqual(paquete.name, 'Comprobantes del año 1990')
        with self.assertRaisesRegex(UserError, 'No hay comprobantes'):
            paquete.action_preparar()

    def test_quien_no_es_contabilidad_no_lo_pide_ni_mete_documentos_a_mano(self):
        with self.assertRaises(AccessError):
            self._paquete(self.vendedora)
        paquete = self._paquete()
        with self.assertRaises(AccessError):
            paquete.write({'documentos': '[["factura", "res.partner", 1]]'})
        with self.assertRaises(AccessError):
            paquete.write({'estado': 'listo'})
        paquete.sudo().write({'documentos': '[["factura", "res.users", 2]]', 'total': 1, 'estado': 'preparando'})
        with self.assertRaisesRegex(UserError, 'desconocido'):
            paquete._procesar()

    def test_nombres_de_archivo_seguros(self):
        from odoo.addons.dcasa_contabilidad.models.comprobantes_zip import nombre_seguro
        self.assertEqual(nombre_seguro('INV/2030/0001 Ñandú «café»'), 'INV_2030_0001 Nandu cafe')
        self.assertEqual(nombre_seguro(''), 'documento')
