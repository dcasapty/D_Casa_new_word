"""Brian abre las pantallas propias del sistema (2026-11-06, «Brian al día»).

``abrir`` lleva a un registro o a una lista de Odoo; las pantallas hechas a la medida de D'CASA (Conversaciones, Sofía,
Camila, Envíos, Valor del inventario…) no son listas: son acciones de cliente. Esta herramienta las abre con un botón,
solo si quien pregunta ve ese menú en la barra de la izquierda (los mismos permisos que la Guía: el menú y todos sus
padres visibles, con los grupos y el acceso al modelo). Si el módulo de la pantalla no está instalado, lo dice.

Solo navega: no lee ni cambia datos (nivel lectura).
"""
from odoo import api, models

from .registro import BrianError, herramienta

ACCIONES_QUE_SE_ABREN = ('ir.actions.client', 'ir.actions.act_window')

# clave → (xmlid del menú, nombre para la persona)
PANTALLAS = {
    'inicio': ('dcasa_interfaz.menu_dcasa_inicio', 'Inicio'),
    'conversaciones': ('dcasa_conversaciones.menu_dcasa_panel_conversaciones', 'Conversaciones'),
    'resumen_de_juan': ('dcasa_conversaciones.menu_dcasa_panel_resumen', 'Resumen de Juan'),
    'reparto': ('dcasa_conversaciones.menu_dcasa_panel_reparto', 'Reparto de conversaciones'),
    'sofia': ('dcasa_sofia.menu_sofia', 'Sofía'),
    'camila': ('dcasa_camila.menu_camila', 'Camila'),
    'marketing': ('dcasa_marketing.menu_marketing', 'Marketing'),
    'envios': ('dcasa_envios.menu_envios_calculadora', 'Calculadora de envíos'),
    'valor_del_inventario': ('dcasa_interfaz.menu_dcasa_valor_inventario', 'Valor del inventario'),
    'ventas_por_dia': ('dcasa_interfaz.menu_dcasa_ventas_por_dia', 'Ventas por día'),
    'estadisticas': ('dcasa_interfaz.menu_estadisticas_resumen', 'Estadísticas'),
    'movimientos': ('dcasa_interfaz.menu_dcasa_movimientos', 'Movimientos de inventario'),
    'bodega': ('dcasa_barras.menu_dcasa_bodega', 'Bodega'),
    'reponer': ('dcasa_interfaz.menu_dcasa_reponer', 'Reponer'),
    'clientes_repetidos': ('dcasa_contactos.menu_duplicados', 'Posibles duplicados'),
    'guia': ('dcasa_guia.menu_guia', 'Guía'),
}


class BrianHerramientasPantallas(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_menu_visible(self, menu):
        """¿Quien pregunta ve este menú? Él y todos sus padres tienen que estar entre los visibles (Odoo marca visible
        un menú sin grupos aunque su app esté escondida)."""
        visibles = set(self.env['ir.ui.menu']._visible_menu_ids())
        actual = menu.sudo()
        while actual:
            if actual.id not in visibles:
                return False
            actual = actual.parent_id
        return True

    @api.model
    def _b_destino_de_menu(self, menu, titulo):
        """El botón «Abrir» de un menú: la acción que abre (una lista o una pantalla propia) y la ruta del menú.
        ``None`` si el menú no abre nada o abre otra cosa: nunca una acción de servidor (correría código) ni un enlace
        (``ir.actions.act_url``), igual que ``_abrir_de_guia``."""
        accion = menu.sudo().action
        if not accion or accion._name not in ACCIONES_QUE_SE_ABREN:
            return None
        return {'accion': accion.id, 'titulo': titulo, 'ruta': ' › '.join(menu.sudo().complete_name.split('/'))}

    @api.model
    @herramienta(
        nombre='abrir_pantalla',
        descripcion='Abre una pantalla del sistema con un botón: Conversaciones, Resumen y Reparto de Juan, Sofía, '
                    'Camila, Marketing, Envíos, Valor del inventario, Bodega, Reponer, la Guía… Dice también dónde '
                    'queda en el menú.',
        parametros={'pantalla': {'type': 'string', 'enum': list(PANTALLAS),
                                 'description': 'Cuál, p. ej. «sofia», «conversaciones» o «envios».'}},
        requeridos=['pantalla'],
        nivel='lectura', categoria='general',
        ejemplos=['ábreme Sofía', 'llévame a Conversaciones', 'abre la calculadora de envíos'],
    )
    def _h_abrir_pantalla(self, pantalla):
        if pantalla not in PANTALLAS:
            raise BrianError(f'No conozco esa pantalla. Opciones: {", ".join(PANTALLAS)}.')
        xmlid, nombre = PANTALLAS[pantalla]
        menu = self.env.ref(xmlid, raise_if_not_found=False)
        if not menu or menu._name != 'ir.ui.menu':
            raise BrianError(f'La pantalla «{nombre}» no está instalada en este sistema.')
        if not self._b_menu_visible(menu):
            raise BrianError(f'No tienes permiso para abrir «{nombre}».')
        destino = self._b_destino_de_menu(menu, nombre)
        if not destino:
            raise BrianError(f'«{nombre}» no abre ninguna pantalla.')
        return {'pantalla': nombre, 'donde': destino['ruta'], 'abrir': destino}
