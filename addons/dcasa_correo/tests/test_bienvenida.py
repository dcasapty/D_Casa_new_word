"""La bienvenida: solo a clientes nuevos, una sola vez, con las cifras de puntos.json (nunca a ojo)."""
import copy
from unittest.mock import patch

from odoo.addons.dcasa_socios.models import reglas as R
from odoo.tests import tagged

from ..models.correo import P_BIENVENIDA_DESDE
from .common import CorreoCase

CARGAR_REGLAS = 'odoo.addons.dcasa_socios.models.reglas.cargar_reglas'
MI_CUENTA = 'odoo.addons.dcasa_correo.models.correo.DcasaCorreo._mi_cuenta_instalado'


@tagged('post_install', '-at_install')
class TestBienvenida(CorreoCase):

    def cuerpo(self, ficha=None):
        ficha = ficha or self.ana
        plantilla = self.env.ref('dcasa_correo.plantilla_bienvenida')
        return plantilla._generate_template([ficha.id], ('subject', 'body_html'))[ficha.id]['body_html']

    def test_las_cifras_salen_de_puntos_json(self):
        reglas = copy.deepcopy(R.cargar_reglas())
        reglas['acumulacion']['puntosPorDolar'] = 7
        reglas['referido']['puntosAlPadrino'] = 4321
        with patch(CARGAR_REGLAS, return_value=reglas):
            cuerpo = self.cuerpo()
        self.assertIn('Ganas 7 puntos por cada dólar', cuerpo)
        self.assertIn('4,321 puntos', cuerpo)
        reglas['referido']['puntosAlPadrino'] = 'PENDIENTE'
        with patch(CARGAR_REGLAS, return_value=reglas):
            cuerpo = self.cuerpo()
        self.assertNotIn('Si invitas a alguien', cuerpo, 'Una cifra PENDIENTE no se escribe')
        self.assertNotIn('PENDIENTE', cuerpo)

    def test_sin_reglas_legibles_no_se_inventa_nada(self):
        with patch(CARGAR_REGLAS, side_effect=OSError('no hay archivo')), \
                self.assertLogs('odoo.addons.dcasa_correo.models.correo', level='ERROR'):
            cuerpo = self.cuerpo()
        self.assertNotIn('Ganas', cuerpo)
        self.assertIn('Mira tus puntos en', cuerpo)

    def test_los_enlaces_cambian_con_mi_cuenta(self):
        base = self.ICP.get_param('web.base.url').rstrip('/')
        with patch(MI_CUENTA, return_value=True):
            cuerpo = self.cuerpo()
        self.assertIn(f'{base}/mi-cuenta', cuerpo)
        self.assertIn(f'{base}/mi-cuenta/puntos', cuerpo)
        self.assertIn('En Mi cuenta › Compras ves cuánto has pagado, cuánto te falta y hasta cuándo.', cuerpo)
        with patch(MI_CUENTA, return_value=False):
            cuerpo = self.cuerpo()
        self.assertNotIn('/mi-cuenta', cuerpo)
        self.assertIn(f'{base}/socios/cuenta', cuerpo)
        self.assertIn('Pídenos tu estado de cuenta por WhatsApp.', cuerpo)
        self.assertIn(f'{base}/socios/premios', cuerpo)

    def test_el_texto_cambia_si_la_ficha_ya_tiene_pin(self):
        cuerpo = self.cuerpo()
        self.assertIn('regístrate en', cuerpo)
        self.assertIn('el código de socio que viene impreso en tu factura', cuerpo)
        self.assertNotIn(self.ana.dcasa_socio_codigo or 'DCA-sin-codigo', cuerpo, 'El código no va en el correo')
        self.ana.sudo().write({'dcasa_pin_hash': 'x'})
        self.ana.invalidate_recordset(['dcasa_reclamada'])
        cuerpo = self.cuerpo()
        self.assertIn('Entra con tu celular y tu PIN.', cuerpo)
        self.assertNotIn('regístrate en', cuerpo)

    def test_a_un_cliente_viejo_no_le_llega(self):
        self.encender()
        self.env.cr.execute("UPDATE res_partner SET create_date = '2019-06-01' WHERE id = %s", [self.beto.id])
        self.beto.invalidate_recordset(['create_date'])
        factura = self.factura(self.beto)
        self.pagar(factura)
        self.assertEqual(self.envios().mapped('tipo'), ['factura'], 'La factura sí; la bienvenida no')

    def test_la_fecha_desde_se_guarda_al_instalar_y_sin_ella_nadie_es_nuevo(self):
        Envio = self.env['dcasa.correo.envio'].sudo()
        self.assertTrue(Envio._es_cliente_nuevo(self.ana))
        self.ICP.set_param(P_BIENVENIDA_DESDE, False)
        self.assertFalse(Envio._es_cliente_nuevo(self.ana), 'Sin fecha guardada, nadie recibe la bienvenida')
        self.ICP.set_param(P_BIENVENIDA_DESDE, 'no es una fecha')
        self.assertFalse(Envio._es_cliente_nuevo(self.ana))
        self.ICP.set_param(P_BIENVENIDA_DESDE, '2999-01-01 00:00:00')
        self.assertFalse(Envio._es_cliente_nuevo(self.ana))

    def test_la_instalacion_guarda_la_fecha(self):
        from odoo.addons.dcasa_correo import _dcasa_correo_post_init
        self.ICP.set_param(P_BIENVENIDA_DESDE, False)
        self.ICP.set_param('dcasa_correo.al_pagar', False)
        _dcasa_correo_post_init(self.env)
        self.assertTrue(self.ICP.get_param(P_BIENVENIDA_DESDE))
        self.assertEqual(self.ICP.get_param('dcasa_correo.al_pagar'), 'True')
        self.assertFalse(self.ICP.get_param('dcasa_correo.enviar_a_clientes'), 'El interruptor general, apagado')

    def test_los_del_sistema_anterior_no_son_nuevos(self):
        Envio = self.env['dcasa.correo.envio'].sudo()
        self.env['ir.model.data'].create({'module': '__import__', 'name': 'dcasa_contacto_99001',
                                          'model': 'res.partner', 'res_id': self.beto.id})
        self.assertFalse(Envio._es_cliente_nuevo(self.beto), 'Vino del sistema anterior')
        historica = self.factura(self.ana, publicar=False)
        historica.dcasa_historica = True
        historica.action_post()
        self.assertFalse(Envio._es_cliente_nuevo(self.ana), 'Tiene facturas históricas')

    def test_un_socio_suspendido_no_la_recibe(self):
        self.encender()
        self.ana.sudo().dcasa_socio_estado = 'suspendido'
        self.pagar(self.factura())
        self.procesar()
        (bienvenida,) = self.envios(tipo='bienvenida')
        self.assertEqual((bienvenida.estado, bienvenida.causa), ('omitido', 'suspendido'))
        self.assertFalse(self.correos_de(self.ana))

    def test_con_bienvenida_apagada_no_se_encola(self):
        self.encender()
        self.ICP.set_param('dcasa_correo.bienvenida', False)
        self.pagar(self.factura())
        self.assertEqual(self.envios().mapped('tipo'), ['factura'])
