"""Buscar antes de crear (etapa 3): al crear una ficha se avisa de las que tienen un nombre parecido. No bloquea (dos
personas pueden llamarse igual) y nunca cuenta a los usuarios ni a los empleados del sistema."""
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.tests import Form, TransactionCase, tagged

from ..models.parecidas import palabras, parecidos


@tagged('post_install', '-at_install')
class TestFichasParecidas(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'parec_vendedora', 'dcasa_base.group_vendedora')
        Partner = cls.env['res.partner']
        cls.ana = Partner.create({'name': 'Anabel Gómez Parecida', 'phone': '6000-0081'})
        cls.empleado = cls.env['hr.employee'].create({'name': 'Rigoberta Empleada Parecida'})

    def test_que_es_parecido(self):
        self.assertEqual(palabras('Ana  Gómez-Pérez'), ['ana', 'gomez', 'perez'])
        self.assertTrue(parecidos('ANABEL GOMEZ', 'Anabel Gómez'))
        self.assertTrue(parecidos('Gómez Anabel', 'anabel gomez'))
        self.assertTrue(parecidos('Anabel Gómez', 'Anabel María Gómez Pérez'))
        self.assertFalse(parecidos('Anabel', 'Anabel Gómez'), 'una sola palabra no basta')
        self.assertFalse(parecidos('Anabel Ruiz', 'Anabel Gómez'))

    def test_aviso_al_crear_y_no_bloquea(self):
        with Form(self.env['res.partner'].with_user(self.vendedora)) as ficha:
            ficha.name = 'anabel gomez'
            # El aviso de la ficha es «Ya existe esta persona» (2026-11-04): incluye las de nombre parecido.
            parecida = next(c for c in ficha.dcasa_coincidencias if c['id'] == self.ana.id)
            self.assertFalse(parecida['fuerte'])
            self.assertIn(['Celular', '6000-0081'], parecida['datos'])
            ficha.phone = '6000-0082'
            ficha.email = 'otra.anabel@example.com'
        self.assertTrue(ficha.record.id, 'se puede crear igual: dos personas pueden llamarse igual')
        self.assertFalse(ficha.record.dcasa_coincidencias, 'una ficha ya creada no repite el aviso')
        # El texto (para Brian) sigue calculándose.
        nueva = self.env['res.partner'].with_user(self.vendedora).new({'name': 'anabel gomez'})
        self.assertIn('Anabel Gómez Parecida', nueva.dcasa_parecidas_aviso)

    def test_los_empleados_no_cuentan(self):
        self.assertFalse(self.env['res.partner']._dcasa_fichas_parecidas('Rigoberta Empleada Parecida'))
        self.assertIn(self.ana, self.env['res.partner']._dcasa_fichas_parecidas('Gómez Parecida Anabel'))
