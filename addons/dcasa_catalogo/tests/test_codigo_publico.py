"""Código público del producto (DC-K7M4PX): el que ve el cliente. Vive en dcasa_base; aquí se prueba con el catálogo
real cargado (Productos, cotizaciones, migración de lo que ya existía).

Pedido de la dueña: cada producto nuevo recibe solo un código que el cliente pueda ver y decir; el cliente no conoce los
códigos del proveedor.
"""
import importlib.util
import re
import time
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import Command
from odoo.addons.dcasa_base.models import codigo_publico as CP
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import file_path, mute_logger
from odoo.tools.safe_eval import safe_eval

FORMA = re.compile(r'^DC-[23456789BCDFGHJKMNPQRSTVWXYZ]{6}$')


@tagged('post_install', '-at_install')
class TestCodigoPublico(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Plantilla = cls.env['product.template']
        cls.admin = new_test_user(cls.env, login='cod_admin', groups='base.group_system,product.group_product_manager')
        cls.gerencia = new_test_user(
            cls.env, login='cod_gerencia', groups='stock.group_stock_manager,product.group_product_manager')
        cls.vendedora = new_test_user(cls.env, login='cod_vendedora', groups='sales_team.group_sale_salesman')

    def producto(self, nombre='Zzmesa de prueba', **extra):
        return self.Plantilla.create({'name': nombre, 'type': 'consu', 'list_price': 10.0, **extra})

    # ------------------------------------------------------------------ el formato

    def test_formato_y_alfabeto(self):
        codigos = {CP.generar_codigo_publico() for _ in range(3000)}
        self.assertGreater(len(codigos), 2990, 'son al azar: casi no se repiten')
        for codigo in codigos:
            self.assertRegex(codigo, FORMA)
            cuerpo = codigo[3:]
            self.assertFalse(set(cuerpo) & set('01OIL'), f'{codigo}: letras que se confunden')
            self.assertFalse(set(cuerpo) & set('AEIOU'), f'{codigo}: sin vocales no se forman palabras')
            self.assertFalse(cuerpo.isdigit(), f'{codigo}: al menos una letra, para no parecer una etiqueta del rollo')
        self.assertEqual(len(CP.ALFABETO), len(set(CP.ALFABETO)))
        self.assertEqual(len(CP.ALFABETO), 28)

    def test_el_codigo_publico_nunca_se_parece_a_una_etiqueta_del_rollo(self):
        """Las etiquetas del rollo (docs/BARRAS.md) son ``DC`` + solo números: ``DC0001``…"""
        for codigo in (CP.generar_codigo_publico() for _ in range(2000)):
            sin_guion = codigo.replace('-', '')
            self.assertFalse(re.fullmatch(r'DC\d+', sin_guion), codigo)
        self.assertIsNone(CP.normalizar_codigo_publico('DC0001'))
        self.assertIsNone(CP.normalizar_codigo_publico('DC1000'))

    def test_normalizar(self):
        self.assertEqual(CP.normalizar_codigo_publico('dc-k7m4px'), 'DC-K7M4PX')
        self.assertEqual(CP.normalizar_codigo_publico(' DC K7M4PX '), 'DC-K7M4PX')
        self.assertEqual(CP.normalizar_codigo_publico('DCK7M4PX'), 'DC-K7M4PX')
        self.assertEqual(CP.normalizar_codigo_publico('dc_k7m4px'), 'DC-K7M4PX', 'un lector con otro teclado')
        for malo in ('', None, 'DC-K7M4P', 'DC-K7M4PXX', 'DC-K7M4P0', 'DC-K7M4PA', 'XX-K7M4PX', 'K7M4PX', 123):
            self.assertIsNone(CP.normalizar_codigo_publico(malo), malo)
        self.assertEqual(CP.patron_de_busqueda('k7m4'), 'K7M4')
        self.assertEqual(CP.patron_de_busqueda('dc-k7m'), 'DC-K7M')
        self.assertIsNone(CP.patron_de_busqueda('dc'), 'muy corto: traería medio catálogo')
        self.assertIsNone(CP.patron_de_busqueda('k7m'))

    # ------------------------------------------------------------------ se asigna solo

    def test_producto_nuevo_nace_con_codigo(self):
        producto = self.producto()
        self.assertRegex(producto.dcasa_codigo_publico, FORMA)
        self.assertEqual(producto.product_variant_id.dcasa_codigo_publico, producto.dcasa_codigo_publico,
                         'la variante muestra el código de su producto')

    def test_todos_los_caminos_de_creacion(self):
        # Por la variante (Odoo crea la plantilla por debajo), con variantes, combos, servicios y archivados.
        por_variante = self.env['product.product'].create({'name': 'Zzcreado por la variante', 'type': 'consu'})
        self.assertRegex(por_variante.product_tmpl_id.dcasa_codigo_publico, FORMA)
        talla = self.env['product.attribute'].create({'name': 'Zztalla', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'Zzs'}), Command.create({'name': 'Zzm'})]})
        con_variantes = self.producto('Zzcon tallas', attribute_line_ids=[Command.create({
            'attribute_id': talla.id, 'value_ids': [Command.set(talla.value_ids.ids)]})])
        self.assertEqual(len(con_variantes.product_variant_ids), 2)
        self.assertEqual(set(con_variantes.product_variant_ids.mapped('dcasa_codigo_publico')),
                         {con_variantes.dcasa_codigo_publico})
        pieza = self.producto('Zzpieza del combo')
        combo = self.producto('Zzcombo de prueba', type='combo', combo_ids=[Command.create({
            'name': 'Zzgrupo', 'combo_item_ids': [Command.create({'product_id': pieza.product_variant_id.id})]})])
        servicio = self.producto('Zzservicio', type='service')
        archivado = self.producto('Zzarchivado', active=False)
        for p in (combo, servicio, archivado):
            self.assertRegex(p.dcasa_codigo_publico, FORMA, p.name)
        self.assertEqual(combo.type, 'combo')

    def test_copiar_un_producto_da_otro_codigo(self):
        original = self.producto()
        copia = original.copy()
        self.assertRegex(copia.dcasa_codigo_publico, FORMA)
        self.assertNotEqual(copia.dcasa_codigo_publico, original.dcasa_codigo_publico)

    def test_ningun_producto_de_la_base_se_queda_sin_codigo(self):
        """Incluye lo que cargó el catálogo, el inventario anterior y los productos de los demás módulos."""
        sin_codigo = self.Plantilla.with_context(active_test=False).search([('dcasa_codigo_publico', '=', False)])
        self.assertFalse(sin_codigo, sin_codigo.mapped('name'))
        self.assertGreater(self.Plantilla.with_context(active_test=False).search_count([]), 100)
        self.env.cr.execute('SELECT count(*), count(DISTINCT dcasa_codigo_publico) FROM product_template')
        total, distintos = self.env.cr.fetchone()
        self.assertEqual(total, distintos, 'cada código es de un solo producto')

    def test_un_codigo_dado_a_mano_se_respeta_si_es_valido(self):
        """Una restauración o una importación que ya trae sus códigos no los pierde."""
        nuevo = self.Plantilla._dcasa_codigos_libres(1)[0]
        producto = self.producto(dcasa_codigo_publico=nuevo)
        self.assertEqual(producto.dcasa_codigo_publico, nuevo)
        with self.assertRaises(ValidationError):
            self.producto(dcasa_codigo_publico='DC-ABC123')   # tiene vocal
        with self.assertRaises(ValidationError):
            self.producto(dcasa_codigo_publico=nuevo)       # ya es de otro

    # ------------------------------------------------------------------ 600 seguidos

    def test_seiscientos_productos_seguidos_no_chocan(self):
        inicio = time.time()
        creados = self.Plantilla.create([{'name': f'Zzlote {i}', 'type': 'consu'} for i in range(600)])
        codigos = creados.mapped('dcasa_codigo_publico')
        self.assertEqual(len(set(codigos)), 600)
        self.assertTrue(all(FORMA.match(c) for c in codigos))
        uno_por_uno = self.env['product.template']
        for i in range(120):
            uno_por_uno |= self.producto(f'Zzsuelto {i}')
        todos = codigos + uno_por_uno.mapped('dcasa_codigo_publico')
        self.assertEqual(len(set(todos)), 720)
        self.assertLess(time.time() - inicio, 120, 'no debe ser lento')

    # ------------------------------------------------------------------ choques

    def test_el_sorteo_no_repite_un_codigo_que_ya_existe_ni_de_archivados(self):
        existente = self.producto().dcasa_codigo_publico
        archivado = self.producto('Zzarchivado', active=False).dcasa_codigo_publico
        with patch.object(CP, 'generar_codigo_publico', side_effect=[existente, archivado, existente, 'DC-BCDFG2']):
            self.assertEqual(self.Plantilla._dcasa_codigos_libres(1), ['DC-BCDFG2'])

    def test_si_otro_proceso_toma_el_mismo_codigo_se_vuelve_a_sortear(self):
        """Dos cajas guardan a la vez y sortean el mismo código: la base lo rechaza y el producto sale con otro."""
        existente = self.producto().dcasa_codigo_publico
        libre = self.Plantilla._dcasa_codigos_libres(1)[0]
        # La consulta de «libres» no vio el código ajeno (otra transacción aún sin confirmar): llega duplicado.
        llamadas = [[existente], [libre]]
        with patch.object(type(self.Plantilla), '_dcasa_codigos_libres', side_effect=lambda *a, **k: llamadas.pop(0)):
            with mute_logger('odoo.sql_db'):
                creado = self.producto('Zzcarrera')
        self.assertEqual(creado.dcasa_codigo_publico, libre)
        self.assertEqual(llamadas, [])

    def test_la_base_rechaza_un_codigo_repetido_o_mal_formado(self):
        a, b = self.producto(), self.producto()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env.cr.execute('UPDATE product_template SET dcasa_codigo_publico = %s WHERE id = %s',
                                [a.dcasa_codigo_publico, b.id])
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env.cr.execute("UPDATE product_template SET dcasa_codigo_publico = 'DC-ABC' WHERE id = %s", [b.id])

    # ------------------------------------------------------------------ no cambia

    def test_el_codigo_no_se_cambia(self):
        producto = self.producto()
        codigo = producto.dcasa_codigo_publico
        otro = self.Plantilla._dcasa_codigos_libres(1)[0]
        for usuario in (self.env.user, self.gerencia, self.admin):
            with self.assertRaises(UserError, msg=usuario.login):
                producto.with_user(usuario).write({'dcasa_codigo_publico': otro})
        with self.assertRaises(UserError):
            producto.write({'dcasa_codigo_publico': False})
        with self.assertRaises(UserError):
            producto.product_variant_id.write({'dcasa_codigo_publico': otro})
        producto.write({'dcasa_codigo_publico': codigo, 'name': 'Zzmismo código, otro nombre'})   # el mismo: nada pasa
        self.assertEqual(producto.dcasa_codigo_publico, codigo)

    def test_el_codigo_no_se_cambia_ni_con_un_contexto_inventado_por_rpc(self):
        """Un cliente RPC puede mandar cualquier contexto; la llave del servidor no se puede escribir en JSON."""
        producto = self.producto()
        otro = self.Plantilla._dcasa_codigos_libres(1)[0]
        for llave in (True, 1, 'true', CP.CLAVE_PASE, {'x': 1}):
            with self.assertRaises(UserError):
                producto.with_context(**{CP.CLAVE_PASE: llave}).write({'dcasa_codigo_publico': otro})

    def test_a_un_producto_sin_codigo_se_le_puede_dar_uno_valido(self):
        producto = self.producto()
        self.env.cr.execute('UPDATE product_template SET dcasa_codigo_publico = NULL WHERE id = %s', [producto.id])
        producto.invalidate_recordset()
        nuevo = self.Plantilla._dcasa_codigos_libres(1)[0]
        producto.write({'dcasa_codigo_publico': nuevo})
        self.assertEqual(producto.dcasa_codigo_publico, nuevo)
        otra = self.producto()
        self.env.cr.execute('UPDATE product_template SET dcasa_codigo_publico = NULL WHERE id = %s', [otra.id])
        otra.invalidate_recordset()
        with self.assertRaises(ValidationError):
            otra.write({'dcasa_codigo_publico': 'DC-ABC123'})

    def test_solo_un_administrador_regenera_y_queda_nota(self):
        producto = self.producto()
        viejo = producto.dcasa_codigo_publico
        for usuario in (self.gerencia, self.vendedora):
            with self.assertRaises(AccessError, msg=usuario.login):
                producto.with_user(usuario).action_dcasa_regenerar_codigo_publico()
        self.assertEqual(producto.dcasa_codigo_publico, viejo)
        producto.with_user(self.admin).action_dcasa_regenerar_codigo_publico()
        nuevo = producto.dcasa_codigo_publico
        self.assertRegex(nuevo, FORMA)
        self.assertNotEqual(nuevo, viejo)
        nota = producto.message_ids[:1].body
        self.assertIn(viejo, nota)
        self.assertIn(nuevo, nota)
        self.assertFalse(self.Plantilla.search([('dcasa_codigo_publico', '=', viejo)]), 'el viejo ya no existe')
        # Después de regenerar vuelve a ser fijo.
        with self.assertRaises(UserError):
            producto.write({'dcasa_codigo_publico': viejo})

    def test_el_campo_es_de_solo_lectura_y_no_se_copia(self):
        campo = self.Plantilla._fields['dcasa_codigo_publico']
        self.assertTrue(campo.readonly)
        self.assertFalse(campo.copy)

    # ------------------------------------------------------------------ relleno de lo que ya existía

    def _sin_codigo(self, cantidad):
        """``cantidad`` productos creados y luego dejados sin código, como estaban los de producción."""
        productos = self.Plantilla.create([{'name': f'Zzviejo {i}', 'type': 'consu'} for i in range(cantidad)])
        self.env.cr.execute('UPDATE product_template SET dcasa_codigo_publico = NULL WHERE id = ANY(%s)',
                            [productos.ids])
        productos.invalidate_recordset()
        return productos

    def test_relleno_de_muchos_productos_por_lotes_y_repetible(self):
        viejos = self._sin_codigo(700)
        archivados = viejos[:5]
        archivados.write({'active': False})
        con_codigo = self.producto('Zzya tenía código')
        codigo_previo = con_codigo.dcasa_codigo_publico
        self.env.cr.execute('SELECT id, write_date FROM product_template WHERE id = ANY(%s)', [viejos.ids])
        fecha_antes = dict(self.env.cr.fetchall())
        self.env.cr.execute('SELECT count(*) FROM product_template WHERE dcasa_codigo_publico IS NULL')
        pendientes = self.env.cr.fetchone()[0]
        self.assertGreaterEqual(pendientes, 700)

        rellenados = self.Plantilla._dcasa_rellenar_codigos_publicos(lote=128)

        self.assertEqual(rellenados, pendientes)
        sin = self.Plantilla.with_context(active_test=False).search([('dcasa_codigo_publico', '=', False)])
        self.assertFalse(sin, 'no queda ninguno sin código')
        codigos = viejos.mapped('dcasa_codigo_publico')
        self.assertEqual(len(set(codigos)), 700)
        self.assertTrue(all(FORMA.match(c) for c in codigos))
        self.assertTrue(all(archivados.mapped('dcasa_codigo_publico')), 'los archivados también')
        self.assertEqual(con_codigo.dcasa_codigo_publico, codigo_previo, 'el que ya tenía código no cambia')
        self.env.cr.execute('SELECT id, write_date FROM product_template WHERE id = ANY(%s)', [viejos.ids])
        self.assertEqual(dict(self.env.cr.fetchall()), fecha_antes,
                         'la fecha de modificación no cambia: las fotos del sitio no se vuelven a pedir')

        # Segunda vez: no hace nada y no cambia ningún código.
        antes = dict(zip(viejos.ids, codigos, strict=True))
        self.assertEqual(self.Plantilla._dcasa_rellenar_codigos_publicos(), 0)
        self.assertEqual(dict(zip(viejos.ids, viejos.mapped('dcasa_codigo_publico'), strict=True)), antes)

    def test_relleno_reintenta_si_un_codigo_choca(self):
        productos = self._sin_codigo(3)
        existente = self.producto().dcasa_codigo_publico
        libres = self.Plantilla._dcasa_codigos_libres(3)
        envio = [[existente, *libres[:2]], libres]    # el primer lote trae uno que otro proceso ya tomó
        resto = self.Plantilla.with_context(active_test=False).search([
            ('dcasa_codigo_publico', '=', False), ('id', 'not in', productos.ids)])
        self.assertFalse(resto)
        with patch.object(type(self.Plantilla), '_dcasa_codigos_libres', side_effect=lambda *a, **k: envio.pop(0)):
            with mute_logger('odoo.sql_db'):
                self.assertEqual(self.Plantilla._dcasa_rellenar_codigos_publicos(), 3)
        self.assertEqual(sorted(productos.mapped('dcasa_codigo_publico')), sorted(libres))

    def test_la_migracion_de_la_version_llena_y_se_puede_repetir(self):
        viejos = self._sin_codigo(40)
        spec = importlib.util.spec_from_file_location(
            'mig_codigo', file_path('dcasa_catalogo/migrations/19.0.1.10.0/post-migrate.py'))
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        migracion.migrate(self.env.cr, '19.0.1.9.0')
        viejos.invalidate_recordset()
        codigos = viejos.mapped('dcasa_codigo_publico')
        self.assertTrue(all(FORMA.match(c) for c in codigos))
        self.assertEqual(len(set(codigos)), 40)
        migracion.migrate(self.env.cr, '19.0.1.9.0')
        viejos.invalidate_recordset()
        self.assertEqual(viejos.mapped('dcasa_codigo_publico'), codigos, 'repetirla no cambia nada')

    # ------------------------------------------------------------------ buscar

    def test_se_encuentra_en_el_buscador_de_productos(self):
        producto = self.producto('Zzmueble buscado por código')
        otro = self.producto('Zzotro mueble')
        codigo = producto.dcasa_codigo_publico
        for escrito in (codigo, codigo.lower(), codigo.replace('-', ''), codigo[3:], codigo[3:7].lower(), codigo[:7]):
            nombres = [n for _id, n in self.Plantilla.name_search(escrito, limit=20)]
            self.assertIn(producto.display_name, nombres, f'{escrito!r} en Productos')
        self.assertNotIn(otro.display_name, [n for _id, n in self.Plantilla.name_search(codigo)])
        variantes = self.env['product.product'].name_search(codigo)
        self.assertEqual([v for v, _n in variantes], producto.product_variant_ids.ids)
        self.assertEqual(self.Plantilla.search([('display_name', 'ilike', codigo)]), producto)

    def test_texto_corto_no_trae_todo_el_catalogo(self):
        self.producto()
        # Si «DC-» buscara dentro de los códigos traería los 600 productos: solo el prefijo no es un código.
        self.assertLess(self.Plantilla.search_count([('display_name', 'ilike', 'DC-')]), 10)
        self.assertLess(self.Plantilla.search_count([('display_name', '=ilike', 'dc')]), 10)
        self.assertEqual(self.Plantilla.name_search('zz-no-existe-nunca'), [])

    def test_se_encuentra_al_cotizar(self):
        """El campo «Producto» de una línea de cotización busca por el nombre que escribe la vendedora."""
        producto = self.producto('Zzcama de la cotización', list_price=100.0)
        cliente = self.env['res.partner'].create({'name': 'Cliente de prueba del código'})
        orden = self.env['sale.order'].create({'partner_id': cliente.id})
        resultado = self.env['product.product'].name_search(producto.dcasa_codigo_publico, limit=8)
        self.assertEqual([r[0] for r in resultado], producto.product_variant_ids.ids)
        linea = self.env['sale.order.line'].create({
            'order_id': orden.id, 'product_id': resultado[0][0], 'product_uom_qty': 1})
        self.assertEqual(linea.product_id.product_tmpl_id, producto)

    def test_la_busqueda_de_varias_palabras_sigue_funcionando(self):
        producto = self.producto('Zzcolchón ortopédico queen')
        Variante = self.env['product.product']
        self.assertEqual(Variante.search([('display_name', 'ilike', 'zzcolchón queen')]), producto.product_variant_id)
        # El código y una palabra del nombre, juntos, también.
        self.assertEqual(Variante.search([('display_name', 'ilike', f'{producto.dcasa_codigo_publico} zzcolchón')]),
                         producto.product_variant_id)
        self.assertFalse(Variante.search([('display_name', 'ilike', f'{producto.dcasa_codigo_publico} zzmesa')]))

    def test_la_busqueda_por_referencia_del_proveedor_sigue_igual(self):
        producto = self.producto('Zzmesa con referencia', default_code='ZZ-PROV-7788')
        self.assertEqual([i for i, _ in self.Plantilla.name_search('ZZ-PROV-7788')], [producto.id])

    # ------------------------------------------------------------------ pantallas de la oficina

    def _vista(self, modelo, tipo, xmlid_busqueda=None):
        return self.env[modelo].get_views([(False, tipo)])['views'][tipo]['arch']

    def test_el_codigo_sale_en_la_ficha_la_lista_y_la_busqueda(self):
        vista = self.env.ref('dcasa_catalogo.product_template_form_codigo_publico')
        self.assertIn('groups="base.group_system"', vista.arch)
        lista = self._vista('product.template', 'list')
        self.assertIn('name="dcasa_codigo_publico"', lista)
        busqueda = self._vista('product.template', 'search')
        self.assertIn('dcasa_codigo_publico', busqueda)
        # El botón de regenerar lo ve un administrador y nadie más.
        vista_ficha = [(self.env.ref('product.product_template_only_form_view').id, 'form')]
        con_boton = self.Plantilla.with_user(self.admin).get_views(vista_ficha)['views']['form']['arch']
        sin_boton = self.Plantilla.with_user(self.gerencia).get_views(vista_ficha)['views']['form']['arch']
        self.assertIn('action_dcasa_regenerar_codigo_publico', con_boton)
        self.assertNotIn('action_dcasa_regenerar_codigo_publico', sin_boton)
        self.assertIn('name="dcasa_codigo_publico"', sin_boton, 'el código lo ve quien edita productos')
        # El cuadro de búsqueda encuentra el producto por su código (y por pedazos).
        producto = self.producto('Zzbuscado en la lista')
        campo = self.env.ref('dcasa_catalogo.product_template_search_codigo_publico')
        dominio = re.search(r'<attribute name="filter_domain">(.*?)</attribute>', campo.arch).group(1)
        for escrito in (producto.dcasa_codigo_publico, producto.dcasa_codigo_publico[3:6].lower()):
            encontrados = self.Plantilla.search(safe_eval(dominio, {'self': escrito}))
            self.assertIn(producto, encontrados)
        otras = self.env.ref('dcasa_catalogo.product_product_search_codigo_publico')
        dominio_variantes = re.search(r'<attribute name="filter_domain">(.*?)</attribute>', otras.arch).group(1)
        encontrados = self.env['product.product'].search(
            safe_eval(dominio_variantes, {'self': producto.dcasa_codigo_publico}))
        self.assertEqual(encontrados, producto.product_variant_ids)

    def test_url_del_qr(self):
        producto = self.producto()
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://dcasapty.com/')
        self.assertEqual(
            producto._dcasa_url_codigo_publico(), f'https://dcasapty.com/codigo/{producto.dcasa_codigo_publico}')
        self.env.cr.execute('UPDATE product_template SET dcasa_codigo_publico = NULL WHERE id = %s', [producto.id])
        producto.invalidate_recordset()
        self.assertEqual(producto._dcasa_url_codigo_publico(), '')

    def test_la_referencia_interna_sigue_siendo_aparte(self):
        """Dos códigos distintos: el del proveedor (interno) no se toca y el público no lo reemplaza."""
        producto = self.producto(default_code='ZZ-INTERNO-1')
        self.assertEqual(producto.default_code, 'ZZ-INTERNO-1')
        self.assertNotEqual(producto.default_code, producto.dcasa_codigo_publico)
        self.assertFalse(producto.barcode, 'el código de barras (etiquetas del rollo) es otro campo')
