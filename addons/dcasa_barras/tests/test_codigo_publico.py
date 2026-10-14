"""El código público (DC-K7M4PX, el que ve el cliente) también lo encuentra el Escáner, sin chocar con las etiquetas
numeradas del rollo (DC0001…, ver docs/BARRAS.md)."""
from odoo import Command
from odoo.tests import tagged

from .comun import BarrasCommon


@tagged('post_install', '-at_install')
class TestBuscarPorCodigoPublico(BarrasCommon):

    def test_el_codigo_que_dice_el_cliente_encuentra_el_producto(self):
        codigo = self.cama.dcasa_codigo_publico
        self.assertRegex(codigo, r'^DC-[2-9B-Z]{6}$')
        for escrito in (codigo, codigo.lower(), codigo.replace('-', ''), codigo.replace('-', '_'), f'\r\n{codigo}\n'):
            r = self.Barras.buscar(escrito)
            self.assertEqual((r['resultado'], r['forma']), ('ok', 'codigo_publico'), escrito)
            self.assertEqual(r['productos'][0]['id'], self.cama.id, escrito)
            self.assertEqual(r['productos'][0]['codigo_publico'], codigo)
            self.assertEqual(r['productos'][0]['referencia'], 'ZZT-CAMA-1', 'la referencia interna sigue a la vista')

    def test_un_producto_con_medidas_sale_con_todas_para_elegir(self):
        talla = self.env['product.attribute'].create({'name': 'Zztalla', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'Zztwin'}), Command.create({'name': 'Zzqueen'})]})
        plantilla = self.env['product.template'].create({
            'name': 'Zzcolchón con medidas', 'type': 'consu', 'is_storable': True,
            'attribute_line_ids': [Command.create({'attribute_id': talla.id,
                                                   'value_ids': [Command.set(talla.value_ids.ids)]})]})
        r = self.Barras.buscar(plantilla.dcasa_codigo_publico)
        self.assertEqual((r['resultado'], r['forma']), ('varios', 'codigo_publico'))
        self.assertEqual({p['id'] for p in r['productos']}, set(plantilla.product_variant_ids.ids))

    def test_no_se_confunde_con_las_etiquetas_del_rollo(self):
        """Una etiqueta del rollo es el código de barras de un producto: gana el código de barras exacto."""
        self.zapatera.barcode = 'DC0001'
        r = self.Barras.buscar('DC0001')
        self.assertEqual((r['resultado'], r['forma']), ('ok', 'codigo_de_barras'))
        self.assertEqual(r['productos'][0]['id'], self.zapatera.id)
        self.assertEqual(self.Barras.buscar('dc0001')['productos'][0]['id'], self.zapatera.id)
        # Y un número del rollo que nadie ha asignado no cae en ningún código público.
        self.assertEqual(self.Barras.buscar('DC0999')['resultado'], 'no_encontrado')
        self.assertEqual(self.Barras.buscar('DC999999')['resultado'], 'no_encontrado')

    def test_un_codigo_publico_que_no_existe_o_esta_mal_escrito(self):
        for escrito in ('DC-BCDFGH', 'DC-BCDFG', 'DC-ABCDEF', 'DC-'):
            self.assertEqual(self.Barras.buscar(escrito)['resultado'], 'no_encontrado', escrito)

    def test_de_un_producto_archivado_no_sale_en_consultar(self):
        archivado = self.producto('Zzarchivado con código', 'ARCH-1')
        codigo = archivado.dcasa_codigo_publico
        archivado.action_archive()
        self.assertEqual(self.Barras.buscar(codigo)['resultado'], 'no_encontrado')

    def test_buscar_por_nombre_tambien_acepta_el_codigo(self):
        codigo = self.cama.dcasa_codigo_publico
        self.assertEqual([p['id'] for p in self.Barras.buscar_por_nombre(codigo)], self.cama.ids)
        self.assertEqual([p['id'] for p in self.Barras.buscar_por_nombre(codigo[3:7])], self.cama.ids)

    def test_el_permiso_sigue_igual(self):
        r = self.como(self.vendedora).buscar(self.cama.dcasa_codigo_publico)
        self.assertEqual(r['resultado'], 'ok')
        self.assertNotIn('costo', str(r).lower())
        self.assertNotIn('77.77', str(r))
