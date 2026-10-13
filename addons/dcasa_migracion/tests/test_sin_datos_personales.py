"""El módulo nunca trae datos de personas: solo código y archivos de ejemplo inventados."""
import os
import re

from odoo.tests import BaseCase, tagged

PERMITIDOS = {'ejemplo.com', 'empresa-prueba.com'}


@tagged('post_install', '-at_install')
class TestSinDatosPersonales(BaseCase):

    def _archivos(self):
        raiz = os.path.join(os.path.dirname(__file__), '..')
        for carpeta, _dirs, archivos in os.walk(raiz):
            if '__pycache__' in carpeta:
                continue
            for archivo in archivos:
                yield os.path.join(carpeta, archivo), archivo

    def test_no_hay_csv_ni_excel_con_datos_dentro_del_modulo(self):
        sobrantes = [a for _r, a in self._archivos() if a.lower().endswith(('.csv', '.xlsx', '.xls', '.zip', '.json'))
                     and a != 'ir.model.access.csv']
        self.assertFalse(sobrantes, 'Los archivos de datos viajan por la pantalla de Odoo, no por el repositorio')

    def test_los_unicos_correos_son_de_ejemplo(self):
        encontrados = set()
        for ruta, archivo in self._archivos():
            if not archivo.endswith(('.py', '.xml', '.md')):
                continue
            with open(ruta, encoding='utf-8') as f:
                for dominio in re.findall(r'[\w.+-]+@([\w-]+(?:\.[\w-]+)+)', f.read()):
                    if dominio.lower() not in PERMITIDOS:
                        encontrados.add((archivo, dominio))
        self.assertFalse(encontrados, 'Hay correos reales dentro del módulo')
