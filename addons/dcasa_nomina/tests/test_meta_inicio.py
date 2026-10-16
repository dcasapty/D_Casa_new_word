"""La vendedora ve en su Inicio qué porcentaje de la meta lleva (pedido de la dueña, 2026-10-16): «si el administrador
pone que la meta al mes son 30 mil, que ellos vayan viendo un porcentaje para llegar a esa meta»."""
from odoo import Command, fields
from odoo.tests import HttpCase, new_test_user, tagged

ESPERAR_JS = """
    const esperar = async (fn, que) => {
        for (let i = 0; i < 150; i++) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('no apareció: ' + que);
    };
"""


@tagged('post_install', '-at_install')
class TestMetaEnElInicio(HttpCase):

    def test_la_vendedora_ve_el_porcentaje_de_su_meta(self):
        if 'dcasa.tablero' not in self.env:
            self.skipTest('El Inicio es de dcasa_interfaz.')
        company = self.env.company
        hoy = fields.Date.context_today(self.env['res.users'].with_context(tz='America/Panama'))
        mes = hoy.replace(day=1)
        Regla = self.env['dcasa.nomina.meta.regla']
        regla = Regla._vigente(mes, company) or Regla.create({
            'company_id': company.id, 'fecha_desde': mes, 'meta_mensual': 30000, 'porcentaje': 1})
        ventas = self.env['hr.department'].create({'name': 'Ventas meta en el Inicio', 'dcasa_meta_ventas': True,
                                                   'company_id': company.id})
        vendedora = new_test_user(self.env, login='meta_inicio_vera', tz='America/Panama',
                                  groups='base.group_user,dcasa_base.group_vendedora')
        self.env['hr.employee'].create({'name': 'Vera Meta Inicio', 'user_id': vendedora.id,
                                        'department_id': ventas.id, 'company_id': company.id})
        # Cobra completa una venta de la cuarta parte de la meta (sin ITBMS): lleva el 25 %.
        cliente = self.env['res.partner'].create({'name': 'Cliente meta Inicio'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id,
            'invoice_date': hoy, 'invoice_user_id': vendedora.id,
            'invoice_line_ids': [Command.create({'name': 'Mueble', 'quantity': 1, 'price_unit': regla.meta_mensual / 4,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({'payment_date': hoy})._create_payments()

        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', '(async () => {' + ESPERAR_JS + """
            const numero = await esperar(() => document.querySelector('.o_dcasa_meta .o_dcasa_meta_porcentaje strong'),
                                         'el porcentaje de la meta');
            const dice = numero.textContent.trim();
            if (dice !== '25 %') { throw new Error('el porcentaje de la meta dice «' + dice + '» y no «25 %»'); }
            const barra = document.querySelector('.o_dcasa_meta .o_dcasa_meta_barra');
            if (barra.getAttribute('aria-valuenow') !== '25') { throw new Error('la barra no va en 25'); }
            const animo = document.querySelector('.o_dcasa_meta .o_dcasa_meta_animo');
            if (!animo || !animo.textContent.includes('Paso a paso')) {
                throw new Error('faltan las palabras de ánimo junto a la barra');
            }
            console.log('test successful');
        })();""", login='meta_inicio_vera')
