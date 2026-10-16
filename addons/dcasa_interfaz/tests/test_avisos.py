"""Los avisos del equipo llegan en Odoo, no al correo (la dueña, 2026-10-16: «los vendedores no contestan mis chats»).

Odoo trae a cada usuario con «Notificación: por correo»: los mensajes y las menciones en un pedido o una ficha se iban
al correo y el contador del chat no los mostraba. Todo usuario interno queda «En Odoo»; el portal sigue por correo."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAvisosEnOdoo(TransactionCase):

    def test_el_equipo_recibe_los_avisos_en_odoo(self):
        vendedora = new_test_user(self.env, login='avisos_vendedora',
                                  groups='base.group_user,dcasa_base.group_vendedora')
        self.assertEqual(vendedora.notification_type, 'inbox')
        self.assertTrue(vendedora.has_group('mail.group_mail_notification_type_inbox'))

    def test_el_cliente_del_portal_sigue_por_correo(self):
        cliente = new_test_user(self.env, login='avisos_portal', groups='base.group_portal')
        self.assertEqual(cliente.notification_type, 'email')

    def test_quienes_ya_existian_quedan_en_odoo(self):
        internos = self.env['res.users'].search([('share', '=', False), ('active', '=', True)])
        self.assertEqual(set(internos.mapped('notification_type')), {'inbox'})
