"""Tests del procesador de la bandeja «up media/» (sin Odoo): python -m unittest discover -s scripts/tests

Prueban la clasificación (qué archivo va a dónde y por qué), los movimientos sobre un árbol
temporal, los LEEME históricos, el RESUMEN para la dueña y la búsqueda de originales
(bandeja → fuentes/ → archivados en R2) del importador. No corren el importador real.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importar_catalogo as importador  # noqa: E402
import procesar_up_media as proc  # noqa: E402

FECHA = '2026-10-03'

# Lo que devuelve importar_catalogo.main(): qué original usó cada carga.
RESULTADO = {
    'excel_inicial': 'DCASA_listado_productos.xlsx',
    'fotos_inicial': {'ZQ063605_1.png': 'ZQ063605', '1062010734-5-6N.png': '1062010734/5/6N'},
    'pedidos': [{
        'pedido': 'LTSC-07',
        'excel': 'Catalogo_LTSC-07.xlsm',
        'asignadas': [('908K - Cama tapizada King – negro.webp', '908K negro', '908K-negro_1.jpg',
                       'por código', 'código 908K, color negro')],
        'dudosas': [('Cama tapizada Queen – beige 213 × 158 × 120 cm.jpg', 'tanto 809Q como 811Q')],
        'ajenas': ['selfie.jpg'],
    }],
}
SIN_PEDIDOS = {'excel_inicial': 'DCASA_listado_productos.xlsx', 'fotos_inicial': {}, 'pedidos': []}


def _bandeja(tmp, nombres, carpetas=()):
    bandeja = Path(tmp) / 'up media'
    bandeja.mkdir()
    for n in nombres:
        (bandeja / n).write_bytes(b'x')
    for c in carpetas:
        (bandeja / c).mkdir()
    return bandeja


class TestClasificar(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def clasificar(self, nombres, carpetas=(), resultado=RESULTADO):
        bandeja = _bandeja(tempfile.mkdtemp(dir=self.tmp), nombres, carpetas)
        return {m.archivo: m for m in proc.clasificar(list(bandeja.iterdir()), resultado, FECHA)}

    def test_la_bandeja_misma_no_se_clasifica(self):
        movs = self.clasificar(['.gitkeep', 'RESUMEN.md', 'LEEME.md'])
        self.assertEqual(movs, {})

    def test_excel(self):
        movs = self.clasificar(['DCASA_listado_productos.xlsx', 'Catalogo_LTSC-07.xlsm', 'otro.xlsx'])
        self.assertEqual((movs['DCASA_listado_productos.xlsx'].estado, movs['DCASA_listado_productos.xlsx'].destino),
                         ('cargado', 'fuentes/carga-inicial'))
        self.assertEqual((movs['Catalogo_LTSC-07.xlsm'].estado, movs['Catalogo_LTSC-07.xlsm'].destino),
                         ('cargado', 'fuentes/LTSC-07'))
        self.assertEqual(movs['otro.xlsx'].estado, 'pendiente')
        self.assertIn('PEDIDOS', movs['otro.xlsx'].motivo)

    def test_fotos_cargadas(self):
        movs = self.clasificar(['ZQ063605_1.png', '908K - Cama tapizada King – negro.webp'])
        inicial = movs['ZQ063605_1.png']
        self.assertEqual((inicial.estado, inicial.destino, inicial.producto),
                         ('cargado', 'fuentes/carga-inicial', 'ZQ063605'))
        pedido = movs['908K - Cama tapizada King – negro.webp']
        self.assertEqual((pedido.estado, pedido.destino), ('cargado', 'fuentes/LTSC-07'))
        self.assertEqual(pedido.producto, '908K negro (`908K-negro_1.jpg`)')
        self.assertIn('por código', pedido.motivo)

    def test_foto_dudosa_se_queda_con_su_motivo(self):
        m = self.clasificar(['Cama tapizada Queen – beige 213 × 158 × 120 cm.jpg']).popitem()[1]
        self.assertEqual((m.estado, m.destino), ('pendiente', None))
        self.assertIn('tanto 809Q como 811Q', m.motivo)
        self.assertIn('LTSC-07', m.motivo)

    def test_graficas_black_weekend_se_conservan(self):
        movs = self.clasificar(['115.png', '153.png', '154.png', '114.png'])
        for n in ('115.png', '153.png'):
            self.assertEqual((movs[n].estado, movs[n].destino),
                             ('conservado', f'fuentes/{importador.CARPETA_GRAFICAS_BW}'))
        for n in ('154.png', '114.png'):
            self.assertEqual(movs[n].estado, 'descartado', n)

    def test_foto_ajena_se_descarta_con_fecha_solo_si_hubo_pedidos(self):
        con = self.clasificar(['selfie.jpg'])['selfie.jpg']
        self.assertEqual((con.estado, con.destino), ('descartado', f'descartado/{FECHA}'))
        sin = self.clasificar(['selfie.jpg'], resultado=SIN_PEDIDOS)['selfie.jpg']
        self.assertEqual((sin.estado, sin.destino), ('pendiente', None))

    def test_otros_tipos_y_carpetas_quedan_pendientes(self):
        movs = self.clasificar(['factura.pdf'], carpetas=['inventario-anterior'])
        self.assertEqual(movs['factura.pdf'].estado, 'pendiente')
        self.assertEqual(movs['factura.pdf'].motivo, proc.MOTIVOS['otro_tipo'])
        self.assertEqual(movs['inventario-anterior'].estado, 'pendiente')
        self.assertEqual(movs['inventario-anterior'].motivo, proc.MOTIVOS['carpeta'])

    def test_orden_estable(self):
        movs = proc.clasificar(list(_bandeja(self.tmp, ['b.pdf', 'a.pdf']).iterdir()), RESULTADO, FECHA)
        self.assertEqual([m.archivo for m in movs], ['a.pdf', 'b.pdf'])


class TestEjecutar(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bandeja = _bandeja(self.tmp, ['ZQ063605_1.png', '115.png', 'selfie.jpg', 'factura.pdf', 'otro.xlsx'])
        self.movs = proc.clasificar(list(self.bandeja.iterdir()), RESULTADO, FECHA)

    def test_mueve_y_deja_lo_pendiente(self):
        finales = proc.ejecutar(self.movs, self.tmp, self.bandeja, FECHA)
        self.assertTrue((self.tmp / 'fuentes/carga-inicial/ZQ063605_1.png').exists())
        self.assertTrue((self.tmp / f'fuentes/{importador.CARPETA_GRAFICAS_BW}/115.png').exists())
        self.assertTrue((self.tmp / f'descartado/{FECHA}/selfie.jpg').exists())
        self.assertEqual(sorted(p.name for p in self.bandeja.iterdir()), ['factura.pdf', 'otro.xlsx'])
        self.assertEqual({m.estado for m in finales if m.archivo in ('factura.pdf', 'otro.xlsx')}, {'pendiente'})

    def test_destino_ocupado_no_pisa(self):
        destino = self.tmp / 'fuentes/carga-inicial/ZQ063605_1.png'
        destino.parent.mkdir(parents=True)
        destino.write_bytes(b'original')
        finales = proc.ejecutar(self.movs, self.tmp, self.bandeja, FECHA)
        m = next(m for m in finales if m.archivo == 'ZQ063605_1.png')
        self.assertEqual((m.estado, m.destino), ('pendiente', None))
        self.assertIn('ya existe', m.motivo)
        self.assertEqual(destino.read_bytes(), b'original')
        self.assertTrue((self.bandeja / 'ZQ063605_1.png').exists())

    def test_leeme_por_carpeta_con_historico(self):
        proc.ejecutar(self.movs, self.tmp, self.bandeja, FECHA)
        leeme = self.tmp / 'fuentes/carga-inicial/LEEME.md'
        texto = leeme.read_text(encoding='utf-8')
        self.assertIn('originales ya procesados', texto)
        self.assertIn(f'## {FECHA}', texto)
        self.assertIn('`ZQ063605_1.png` → ZQ063605', texto)
        descartado = (self.tmp / f'descartado/{FECHA}/LEEME.md').read_text(encoding='utf-8')
        self.assertIn('Nada de esta carpeta se cargó', descartado)
        self.assertIn('`selfie.jpg`:', descartado)
        # Segunda tanda: se agrega al final, sin borrar lo anterior.
        _bandeja_2 = self.bandeja / '1062010734-5-6N.png'
        _bandeja_2.write_bytes(b'y')
        movs2 = proc.clasificar([_bandeja_2], RESULTADO, '2026-10-04')
        proc.ejecutar(movs2, self.tmp, self.bandeja, '2026-10-04')
        texto2 = leeme.read_text(encoding='utf-8')
        self.assertTrue(texto2.startswith(texto.rstrip('\n')))
        self.assertIn('## 2026-10-04', texto2)
        self.assertIn('1062010734/5/6N', texto2)

    @unittest.skipUnless(shutil.which('git'), 'sin git')
    def test_git_mv_conserva_el_historial(self):
        def git(*args):
            return subprocess.run(['git', *args], cwd=self.tmp, capture_output=True, text=True, check=True).stdout

        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'bandeja')
        proc.ejecutar(self.movs, self.tmp, self.bandeja, FECHA)
        estado = git('status', '--porcelain')
        self.assertIn('R  "up media/ZQ063605_1.png" -> fuentes/carga-inicial/ZQ063605_1.png', estado)
        self.assertNotIn('?? fuentes/carga-inicial/ZQ063605_1.png', estado)


class TestResumen(unittest.TestCase):

    def test_resumen_para_la_duena(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        bandeja = _bandeja(tmp, ['DCASA_listado_productos.xlsx', 'ZQ063605_1.png', '115.png', 'selfie.jpg',
                                 'factura.pdf', 'Cama tapizada Queen – beige 213 × 158 × 120 cm.jpg'])
        texto = proc.resumen(proc.clasificar(list(bandeja.iterdir()), RESULTADO, FECHA), FECHA)
        self.assertIn('# up media: qué pasó con lo que subiste', texto)
        self.assertIn('- `DCASA_listado_productos.xlsx` → todos los productos de la hoja «Productos»; '
                      'ahora en `fuentes/carga-inicial/`.', texto)
        self.assertIn('| `ZQ063605_1.png` | ZQ063605 |', texto)
        self.assertIn('- `factura.pdf`: ' + proc.MOTIVOS['otro_tipo'] + '.', texto)
        self.assertIn('tanto 809Q como 811Q', texto)
        self.assertIn(f'- `selfie.jpg` → `descartado/{FECHA}/`', texto)
        self.assertIn(f'- `115.png` → `fuentes/{importador.CARPETA_GRAFICAS_BW}/`', texto)
        self.assertIn('## Cómo subir más', texto)

    def test_resumen_vacio(self):
        texto = proc.resumen([], FECHA)
        for frase in ('- Ninguno.', '| — | — | — | — |', '- Nada pendiente.', '- Nada.'):
            self.assertIn(frase, texto)


class TestFuentesDelImportador(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bandeja = _bandeja(self.tmp, ['A.png', 'RESUMEN.md'], carpetas=['inventario-anterior'])
        (self.bandeja / 'inventario-anterior' / 'pagina-1.webp').write_bytes(b'x')
        self.fuentes = self.tmp / 'fuentes'
        (self.fuentes / 'carga-inicial').mkdir(parents=True)
        for n in ('A.png', 'B.png', 'LEEME.md'):
            (self.fuentes / 'carga-inicial' / n).write_bytes(b'y')

    def test_bandeja_manda_y_fuentes_completa(self):
        rutas = importador.fuentes_disponibles(self.bandeja, self.fuentes)
        self.assertEqual(list(rutas), ['A.png', 'B.png'])
        self.assertEqual(rutas['A.png'], self.bandeja / 'A.png')
        self.assertEqual(rutas['B.png'], self.fuentes / 'carga-inicial' / 'B.png')

    def test_archivados_en_r2_cuentan_pero_avisan(self):
        (self.fuentes / 'ARCHIVADO.tsv').write_text(
            '# ruta\tsha256\tbytes\tfecha\nfuentes/carga-inicial/C.png\tabc\t12\t2026-10-03\n', encoding='utf-8')
        rutas = importador.fuentes_disponibles(self.bandeja, self.fuentes)
        self.assertIn('C.png', rutas)
        self.assertIsNone(rutas['C.png'])
        with self.assertRaises(FileNotFoundError) as ctx:
            importador.ruta_fuente('C.png', rutas)
        self.assertIn('archivar_fuentes.sh traer', str(ctx.exception))
        with self.assertRaises(FileNotFoundError):
            importador.ruta_fuente('no-existe.png', rutas)


if __name__ == '__main__':
    unittest.main()
