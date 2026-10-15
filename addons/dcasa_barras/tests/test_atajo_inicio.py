"""El Escáner es un acceso directo del Inicio para todos los que mueven mercancía (pedido de la dueña, 2026-10-15)."""
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .comun import BarrasCommon


@tagged('post_install', '-at_install')
class TestAtajoDelEscaner(BarrasCommon):

    def atajos(self, usuario):
        return self.env['dcasa.tablero'].with_user(usuario).obtener_datos()['atajos']

    def escaner(self, usuario):
        return next((a for a in self.atajos(usuario) if a['clave'] == 'escaner'), None)

    def test_lo_tienen_la_vendedora_el_inventario_y_gerencia(self):
        """Los tres abren la misma pantalla que el menú Inventario › Escáner."""
        for usuario in (self.vendedora, self.solo_inventario, self.gerencia):
            atajo = self.escaner(usuario)
            self.assertTrue(atajo, f'{usuario.login} debe ver el Escáner en el Inicio')
            self.assertEqual(atajo['titulo'], 'Escáner')
            self.assertEqual(atajo['accion'], 'dcasa_barras.accion_escaner')
            self.assertIsNone(atajo['vista'])
            self.assertTrue(atajo['icono'].startswith('fa-') and atajo['detalle'])
        self.assertEqual(self.env.ref('dcasa_barras.menu_dcasa_escaner').action,
                         self.env.ref('dcasa_barras.accion_escaner'))

    def test_quien_no_tiene_inventario_no_lo_ve_porque_no_podria_usarlo(self):
        self.assertIsNone(self.escaner(self.sin_inventario))
        with self.assertRaises(AccessError):
            self.como(self.sin_inventario).buscar('ZZT-CAMA-1')

    def test_el_rol_vendedora_de_dcasa_lo_ve(self):
        rol = self.env.ref('dcasa_base.group_vendedora')
        usuario = new_test_user(self.env, login='barras_rol_vendedora', groups='base.group_user')
        usuario.write({'group_ids': [(4, rol.id)]})
        self.assertTrue(self.escaner(usuario), 'el rol Vendedora trae Inventario usuario: ve el Escáner')

    def test_va_despues_de_productos_facturas_y_conversaciones(self):
        claves = [a['clave'] for a in self.atajos(self.gerencia)]
        for antes in ('productos', 'facturas', 'conversaciones'):
            if antes in claves:
                self.assertLess(claves.index(antes), claves.index('escaner'), antes)
        for despues in ('oportunidades', 'resumen_contable'):
            if despues in claves:
                self.assertGreater(claves.index(despues), claves.index('escaner'), despues)
