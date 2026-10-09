"""Base común de los tests de Conversaciones: usuarios, mensajes de prueba y un Worker falso."""
import itertools
import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, new_test_user

TOKEN_ODOO = 'o' * 40       # JUAN_ODOO_TOKEN de prueba (no es un secreto real)
TOKEN_WORKER = 'w' * 40     # JUAN_WORKER_TOKEN de prueba
URL_WORKER = 'https://juan.prueba.example.com'
_contador = itertools.count(1)


def respuesta_http(cuerpo=None, estado=200):
    """Lo que devolvería ``requests`` desde el Worker."""
    respuesta = MagicMock()
    respuesta.status_code = estado
    respuesta.content = json.dumps(cuerpo if cuerpo is not None else {'ok': True}).encode()
    respuesta.json.return_value = cuerpo if cuerpo is not None else {'ok': True}
    return respuesta


class JuanCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Conversacion = cls.env['dcasa.conversacion']
        cls.Mensaje = cls.env['dcasa.mensaje']
        cls.Partner = cls.env['res.partner']
        cls.ajustes = cls.env['dcasa.juan.ajustes'].obtener()
        cls.juan = cls.env.ref('dcasa_conversaciones.user_juan')
        cls.vendedora = new_test_user(
            cls.env, login='juan_vendedora', name='Vendedora Prueba',
            groups='base.group_user,sales_team.group_sale_salesman')
        cls.gerente = new_test_user(
            cls.env, login='juan_gerente', name='Gerente Prueba',
            groups='base.group_user,sales_team.group_sale_manager')
        cls.interno = new_test_user(cls.env, login='juan_interno', name='Interno sin ventas',
                                    groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='juan_portal', name='Portal', groups='base.group_portal')

    def setUp(self):
        super().setUp()
        # Sin Worker real: nada sale a internet. Los tests que lo necesitan lo configuran y lo simulan.
        entorno = patch.dict(os.environ, {'JUAN_ODOO_TOKEN': '', 'JUAN_WORKER_TOKEN': '', 'JUAN_WORKER_URL': '',
                                          'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        entorno.start()
        self.addCleanup(entorno.stop)
        # Si algo intentara hablar con internet, el test falla en vez de salir de verdad.
        for destino in ('requests.request', 'requests.get', 'requests.post'):
            parche = patch(destino, side_effect=AssertionError(f'{destino} no debe llamarse en los tests'))
            parche.start()
            self.addCleanup(parche.stop)

    # ------------------------------------------------------------------
    # Mensajes
    # ------------------------------------------------------------------

    def datos(self, texto='Hola, ¿tienen camas queen?', canal='whatsapp_qr', id_externo='50760261919',
              autor='cliente', ts=None, **extra):
        direccion = 'entrante' if autor == 'cliente' else 'saliente'
        return {
            'canal': canal, 'id_externo': id_externo, 'id_mensaje': f'wamid.{next(_contador)}',
            'direccion': direccion, 'autor': autor, 'texto': texto, 'ts': ts or datetime(2026, 10, 9, 15, 0),
            'nombre': None, 'celular': None, 'adjuntos': [], **extra,
        }

    def registrar(self, texto='Hola, ¿tienen camas queen?', **kw):
        """Registra un mensaje como lo hace la API. Devuelve ``(conversacion, mensaje, creado)``."""
        return self.Conversacion._registrar_mensaje(self.datos(texto, **kw))

    def conversacion(self, **kw):
        return self.registrar(**kw)[0]

    # ------------------------------------------------------------------
    # Worker falso
    # ------------------------------------------------------------------

    def configurar_worker(self):
        """Pone URL y token del Worker (de prueba) y devuelve el parche de ``requests.request`` para ir viendo las llamadas."""
        entorno = patch.dict(os.environ, {'JUAN_WORKER_URL': URL_WORKER, 'JUAN_WORKER_TOKEN': TOKEN_WORKER})
        entorno.start()
        self.addCleanup(entorno.stop)
        parche = patch('requests.request', return_value=respuesta_http({'ok': True, 'id_mensaje': 'wamid.worker.1'}))
        simulado = parche.start()
        self.addCleanup(parche.stop)
        return simulado
