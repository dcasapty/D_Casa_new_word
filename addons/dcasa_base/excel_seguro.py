"""El Excel de «Acción › Exportar» no vuelve fórmula lo que escribió un cliente.

``/web/export/xlsx`` del núcleo escribe cada texto con ``worksheet.write`` y xlsxwriter, con sus opciones de fábrica,
convierte en **fórmula** un texto que empiece con «=» y en **vínculo** uno que parezca una dirección web. El nombre
de un cliente, una referencia, el nombre de un diario o lo que alguien escribió en un campo libre puede empezar con
«=», «+», «-» o «@» (``=HYPERLINK(...)``, ``=2+2``): al abrir el Excel, la fórmula corre en la computadora de quien
lo abre. El CSV del núcleo ya lo evita (antepone una comilla); el xlsx no.

Aquí se cambia, para todo el sistema, el punto único por donde el exportador escribe cada celda
(``ExportXlsxWriter.write``): los textos se escriben como texto (``write_string``: nunca fórmula ni vínculo) y todo
lo demás (números, fechas, booleanos) sigue yendo por ``worksheet.write`` y queda como número o fecha.

Vive en ``dcasa_base``, que todos los módulos de D'CASA cargan, y no en ``dcasa_interfaz``: el exportar es de todas
las listas. No toca ``vendor/odoo``. Los otros Excel de la tienda (Contabilidad, Compras › Reponer) arman su libro
aparte con xlsxwriter: no pasan por aquí y cuidan lo suyo (``dcasa_contabilidad/controllers/main.py`` y
``dcasa_interfaz/models/reponer.py``).
"""
from odoo.addons.web.controllers import export as exportar_del_nucleo


def escribir_sin_formulas(self, row, column, cell_value, style=None):
    """Como ``ExportXlsxWriter.write`` del núcleo, pero un texto es siempre texto."""
    if isinstance(cell_value, str):
        if not cell_value:
            return self.worksheet.write_blank(row, column, None, style)
        return self.worksheet.write_string(row, column, cell_value, style)
    return self.worksheet.write(row, column, cell_value, style)


exportar_del_nucleo.ExportXlsxWriter.write = escribir_sin_formulas
