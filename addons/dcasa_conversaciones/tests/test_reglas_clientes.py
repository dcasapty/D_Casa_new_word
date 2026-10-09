"""Las reglas de Socios para el cliente: ninguna cifra fuera de puntos.json, y lo ``null`` no se rellena a ojo."""
import copy
import re

from odoo.addons.dcasa_socios.models import reglas as R
from odoo.tests import BaseCase, tagged

from ..models.reglas_clientes import redactar


def numeros_del_json(valor, acumulado=None):
    """Todos los números que existen en puntos.json (en cualquier nivel), como texto, más sus formas de lectura."""
    acumulado = set() if acumulado is None else acumulado
    if isinstance(valor, dict):
        for clave, sub in valor.items():
            if not clave.startswith('$'):
                numeros_del_json(sub, acumulado)
    elif isinstance(valor, (int, float)) and not isinstance(valor, bool):
        acumulado.add(str(valor))
        acumulado.add(R.como_puntos(int(valor)))                 # 5,000
        acumulado.add(f'{valor / 100:,.2f}')                      # 2000 centavos → 20.00
        acumulado.add(f'{int(valor) // 100}')                     # 2000 → 20
    return acumulado


@tagged('post_install', '-at_install')
class TestReglasParaClientes(BaseCase):

    def setUp(self):
        super().setUp()
        self.reglas = R.cargar_reglas()

    def test_explica_el_programa_con_las_cifras_reales(self):
        texto = ' '.join(redactar(self.reglas, 'https://dcasapty.com')['resumen'])
        self.assertIn('1 punto por cada dólar', texto)
        self.assertIn('ITBMS incluido', texto)
        self.assertIn('$20.00', texto)                  # compra mínima
        self.assertIn('500 puntos', texto)              # padrino / canje mínimo / cumpleaños
        self.assertIn('250 puntos', texto)              # invitado
        self.assertIn('72 horas', texto)
        self.assertIn('100 puntos valen $1', texto)
        self.assertIn('hasta 50 personas', texto)
        self.assertIn('5,000 puntos al mes', texto)
        self.assertIn('no tienen fecha de vencimiento', texto)

    def test_ninguna_cifra_sale_de_la_cabeza(self):
        """Cada número de las frases existe en puntos.json (o es el «$1» de la equivalencia)."""
        permitidos = numeros_del_json(self.reglas) | {'1'}
        for linea in redactar(self.reglas)['resumen']:
            for numero in re.findall(r'\d[\d,]*(?:\.\d+)?', linea):
                with self.subTest(linea=linea, numero=numero):
                    self.assertIn(numero, permitidos)

    def test_las_cifras_estructuradas_son_las_del_json(self):
        cifras = redactar(self.reglas)['cifras']
        self.assertEqual(cifras['puntos_por_dolar'], self.reglas['acumulacion']['puntosPorDolar'])
        self.assertEqual(cifras['puntos_al_padrino'], self.reglas['referido']['puntosAlPadrino'])
        self.assertEqual(cifras['puntos_al_invitado'], self.reglas['referido']['puntosAlAhijado'])
        self.assertEqual(cifras['saldo_minimo_para_canjear'], self.reglas['canje']['saldoMinimoParaCanjear'])
        self.assertEqual(cifras['vigencia_del_codigo_horas'], self.reglas['canje']['vigenciaDelCodigoHoras'])
        self.assertEqual(cifras['puntos_de_cumpleanos'], self.reglas['cumpleanos']['puntos'])
        self.assertEqual(cifras['puntos_de_bienvenida'], 0)

    def test_si_el_json_cambia_el_texto_cambia(self):
        cambiadas = copy.deepcopy(self.reglas)
        cambiadas['referido']['puntosAlPadrino'] = 700
        cambiadas['acumulacion']['puntosPorDolar'] = 2
        texto = ' '.join(redactar(cambiadas)['resumen'])
        self.assertIn('700 puntos', texto)
        self.assertIn('2 puntos por cada dólar', texto)

    def test_un_valor_null_no_se_rellena_a_ojo(self):
        pendientes = copy.deepcopy(self.reglas)
        pendientes['referido']['puntosAlPadrino'] = None
        pendientes['acumulacion']['puntosPorDolar'] = None
        pendientes['canje']['saldoMinimoParaCanjear'] = 'PENDIENTE DE CONFIRMAR'
        resultado = redactar(pendientes)
        texto = ' '.join(resultado['resumen'])
        self.assertNotIn('por cada dólar', texto)
        self.assertNotIn('tú ganas', texto)
        self.assertNotIn('Para canjear necesitas', texto)
        self.assertNotIn('PENDIENTE', texto)
        self.assertEqual(sorted(resultado['pendientes']), [
            'acumulacion.puntosPorDolar', 'canje.saldoMinimoParaCanjear', 'referido.puntosAlPadrino'])
        for clave in ('puntos_por_dolar', 'puntos_al_padrino', 'saldo_minimo_para_canjear'):
            self.assertNotIn(clave, resultado['cifras'])

    def test_el_json_real_no_tiene_pendientes_de_cifras_que_se_expliquen(self):
        # El tope por compra («PENDIENTE DE CONFIRMAR POR MARCIAL») es un comentario interno, no una cifra pendiente.
        self.assertEqual(redactar(self.reglas)['pendientes'], [])

    def test_vencimiento_con_cifra_se_dice(self):
        con_vencimiento = copy.deepcopy(self.reglas)
        con_vencimiento['vencimiento']['meses'] = 12
        texto = ' '.join(redactar(con_vencimiento)['resumen'])
        self.assertIn('vencen a los 12 meses', texto)

    def test_nunca_promete_puntos_sin_factura(self):
        resultado = redactar(self.reglas)
        self.assertIn('factura queda pagada', ' '.join(resultado['resumen']))
        self.assertIn('nunca se prometen por una compra sin facturar', resultado['aviso'])

    def test_enlaces(self):
        enlaces = redactar(self.reglas, 'https://dcasapty.com/')['enlaces']
        self.assertEqual(enlaces, {'registro': 'https://dcasapty.com/socios',
                                   'premios': 'https://dcasapty.com/socios/premios'})
