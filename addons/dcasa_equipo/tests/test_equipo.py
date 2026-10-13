"""El ícono de Empleados es de la marca; nadie se da de alta pegando texto; y el módulo no trae datos de personas."""
import os
import re

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEquipo(TransactionCase):

    def test_el_menu_empleados_tiene_el_icono_de_la_marca(self):
        menu = self.env.ref('hr.menu_hr_root')
        self.assertEqual(menu.web_icon, 'dcasa_equipo,static/src/img/empleados.svg')
        self.assertTrue(menu.web_icon_data)
        ruta = os.path.join(os.path.dirname(__file__), '..', 'static', 'src', 'img', 'empleados.svg')
        with open(ruta, encoding='utf-8') as f:
            svg = f.read()
        self.assertIn('#1340B1', svg)
        self.assertIn('#FED00F', svg)
        self.assertNotIn('gradient', svg.lower())

    def test_no_hay_alta_de_personas_por_texto(self):
        """La dueña pidió que las personas no se creen pegando una lista (2026-10-11); se retiró la pantalla."""
        self.assertNotIn('dcasa.equipo.alta', self.env)
        self.assertNotIn('dcasa.equipo.alta.linea', self.env)
        self.assertFalse(self.env['ir.ui.menu'].search([('name', '=', 'Alta del equipo')]))
        self.assertFalse(self.env['ir.actions.act_window'].search([('res_model', '=', 'dcasa.equipo.alta')]))

    def test_el_modulo_no_trae_datos_de_personas(self):
        """Los nombres y correos del equipo viven solo en la base de datos de Odoo, nunca en el repositorio."""
        raiz = os.path.join(os.path.dirname(__file__), '..')
        permitidos = {'equipo-prueba.test', 'ejemplo.com'}
        encontrados = set()
        for carpeta, _dirs, archivos in os.walk(raiz):
            for archivo in archivos:
                if not archivo.endswith(('.py', '.xml', '.csv', '.json', '.md', '.svg')):
                    continue
                with open(os.path.join(carpeta, archivo), encoding='utf-8') as f:
                    for dominio in re.findall(r'[\w.+-]+@([\w-]+(?:\.[\w-]+)+)', f.read()):
                        if dominio.lower() not in permitidos:
                            encontrados.add((archivo, dominio))
        self.assertFalse(encontrados, "Hay correos reales dentro del módulo")
