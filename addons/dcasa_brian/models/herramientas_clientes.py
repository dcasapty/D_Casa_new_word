"""Herramientas de clientes y proveedores (y los puntos del programa Socios D'CASA).

Reglas de Socios que se respetan aquí:
* Un cliente y un socio son la misma ficha (``res.partner``) y la llave es el celular:
  crear o cambiar un celular nunca duplica una ficha existente.
* El saldo de puntos ES la suma de ``dcasa.movimiento``: se lee, nunca se escribe aquí.
  El único ajuste que se ofrece pasa por el asistente del propio módulo (con motivo).
"""
from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.addons.dcasa_socios.models.dcasa_movimiento import TIPOS

from . import herramientas_comun as c
from .registro import BrianError, herramienta

INTERNO = ('base.group_user',)
FACTURACION = ('account.group_account_invoice',)
PARAM_CLIENTE = {'type': 'string', 'description': 'Nombre, celular, RUC/cédula o código de socio, '
                                                   'p. ej. «Ana Gómez» o «6123-4567».'}
CAMPOS_CONTACTO = {'nombre': 'name', 'celular': 'phone', 'correo': 'email', 'direccion': 'street',
                   'ruc': 'vat', 'dv': 'l10n_pa_dv'}
TIPOS_MOVIMIENTO = dict(TIPOS)


class BrianHerramientasClientes(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @api.model
    def _b_celular(self, texto):
        """Los 8 dígitos de un celular de Panamá, o BrianError."""
        celular = R.celular_normal(texto)
        if not R.celular_valido(celular):
            raise BrianError(f'«{texto}» no parece un celular de Panamá: son 8 números, como 6123-4567.')
        return celular

    @api.model
    def _b_duplicado_celular(self, celular, excepto=None):
        """¿Ya hay una ficha con ese celular? Búsqueda con sudo solo para NO duplicar: devuelve el nombre.

        Justificación del sudo: un vendedor puede no ver algunas fichas (reglas de registro) y
        aun así crear un duplicado; la regla «un celular, una ficha» es de toda la empresa.
        """
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        dominio = ['|', ('dcasa_telefono_digitos', '=', celular), ('dcasa_celular', '=', celular)]
        if excepto:
            dominio = [('id', 'not in', excepto.ids)] + dominio
        return Partner.search(dominio, limit=1)

    @api.model
    def _b_deuda(self, partner):
        """Por cobrar de facturas publicadas: total y vencido. Solo si el usuario ve facturas."""
        if not self.env['account.move'].has_access('read'):
            return None
        facturas = self.env['account.move'].search([
            ('commercial_partner_id', '=', partner.commercial_partner_id.id), ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))])
        hoy = self._b_hoy()
        vencidas = facturas.filtered(lambda f: f.invoice_date_due and f.invoice_date_due < hoy)
        return {'por_cobrar': c.moneda(sum(facturas.mapped('amount_residual'))),
                'vencido': c.moneda(sum(vencidas.mapped('amount_residual'))),
                'facturas_abiertas': len(facturas)}

    @api.model
    def _b_ficha_contacto(self, partner):
        ficha = {
            'nombre': partner.display_name,
            'celular': R.celular_fmt(R.celular_normal(partner.phone)) if partner.phone else '',
            'correo': partner.email or '',
            'ruc_o_cedula': partner.dcasa_ruc_display or '',
            'direccion': ', '.join(p for p in (partner.street, partner.city) if p),
            'es_empresa': partner.is_company,
        }
        return ficha

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @herramienta(
        nombre='buscar_clientes',
        descripcion='Busca clientes o proveedores por nombre, celular, RUC/cédula o correo.',
        parametros={
            'texto': {'type': 'string', 'description': 'Lo que sepas: «Ana», «6123-4567», «8-888-888».'},
            'tipo': {'type': 'string', 'enum': ['clientes', 'proveedores', 'todos'],
                     'description': 'Por defecto «todos».'},
            'limite': c.PARAM_LIMITE,
        },
        requeridos=['texto'],
        nivel='lectura', categoria='clientes', grupos=INTERNO,
        ejemplos=['busca al cliente con celular 6123-4567', 'proveedores de colchones'],
    )
    def _h_buscar_clientes(self, texto, tipo='todos', limite=10):
        dominio = [('parent_id', '=', False), '|', '|', ('display_name', 'ilike', texto), ('email', 'ilike', texto),
                   ('vat', 'ilike', texto)]
        if tipo == 'clientes':
            dominio.append(('customer_rank', '>', 0))
        elif tipo == 'proveedores':
            dominio.append(('supplier_rank', '>', 0))
        Partner = self.env['res.partner']
        total = Partner.search_count(dominio)
        contactos = Partner.search(dominio, limit=c.limite(limite))
        return {'encontrados': total, 'contactos': [{
            'nombre': p.display_name,
            'celular': R.celular_fmt(R.celular_normal(p.phone)) if p.phone else '',
            'ruc_o_cedula': p.dcasa_ruc_display or '',
            'tipo': ', '.join(t for t, ok in (('cliente', p.customer_rank), ('proveedor', p.supplier_rank)) if ok)
                    or 'contacto',
        } for p in contactos]}

    @herramienta(
        nombre='ver_cliente',
        descripcion='Ficha de un cliente o proveedor: contacto, lo que debe, últimas compras y puntos de socio.',
        parametros={'cliente': PARAM_CLIENTE}, requeridos=['cliente'],
        nivel='lectura', categoria='clientes', grupos=INTERNO,
        ejemplos=['¿cuánto debe Ana Gómez?', 'ficha del 6123-4567'],
    )
    def _h_ver_cliente(self, cliente):
        partner = self._b_contacto(cliente)
        ficha = self._b_ficha_contacto(partner)
        deuda = self._b_deuda(partner)
        if deuda:
            ficha['deuda'] = deuda
        if self.env['sale.order'].has_access('read'):
            ventas = self.env['sale.order'].search(
                [('partner_id', 'child_of', partner.id), ('state', '=', 'sale')], limit=5, order='date_order desc')
            ficha['ultimas_compras'] = [{'numero': v.name, 'fecha': c.fecha(v.date_order),
                                         'total': c.moneda(v.amount_total)} for v in ventas]
        if partner.dcasa_socio_codigo:
            ficha['socio'] = {'codigo': partner.dcasa_socio_codigo, 'puntos': partner.dcasa_saldo,
                              'estado': dict(partner._fields['dcasa_socio_estado'].selection).get(
                                  partner.dcasa_socio_estado, '')}
        return ficha

    @herramienta(
        nombre='clientes_que_deben',
        descripcion='Clientes con facturas por cobrar: cuánto deben y cuánto está vencido, de mayor a menor.',
        parametros={'solo_vencido': {'type': 'boolean',
                                     'description': 'true = solo lo vencido (por defecto); false = todo lo pendiente.'},
                    'limite': c.PARAM_LIMITE},
        nivel='lectura', categoria='clientes', grupos=FACTURACION,
        ejemplos=['¿quién nos debe?', 'clientes morosos'],
    )
    def _h_clientes_que_deben(self, solo_vencido=True, limite=10):
        dominio = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                   ('payment_state', 'in', ('not_paid', 'partial'))]
        hoy = self._b_hoy()
        if solo_vencido or solo_vencido is None:
            dominio.append(('invoice_date_due', '<', hoy))
        grupos = self.env['account.move']._read_group(dominio, ['commercial_partner_id'],
                                                      ['amount_residual:sum', '__count'])
        grupos.sort(key=lambda g: -g[1])
        total = sum(g[1] for g in grupos)
        return {
            'criterio': 'vencido' if solo_vencido or solo_vencido is None else 'todo lo pendiente',
            'clientes_con_deuda': len(grupos),
            'total': c.moneda(total),
            'clientes': [{'cliente': p.display_name, 'debe': c.moneda(m), 'facturas': n}
                         for p, m, n in grupos[:c.limite(limite)]],
        }

    @herramienta(
        nombre='saldo_puntos',
        descripcion='Puntos de un socio D\'CASA (la suma de su libro de puntos) y sus últimos movimientos.',
        parametros={'cliente': PARAM_CLIENTE}, requeridos=['cliente'],
        nivel='lectura', categoria='clientes', grupos=INTERNO,
        ejemplos=['¿cuántos puntos tiene Ana?', 'puntos del socio DCA7K2M9P'],
    )
    def _h_saldo_puntos(self, cliente):
        partner = self._b_contacto(cliente, 'socio').commercial_partner_id
        movimientos = self.env['dcasa.movimiento'].search([('partner_id', '=', partner.id)], limit=10)
        return {
            'socio': partner.display_name,
            'codigo': partner.dcasa_socio_codigo or 'todavía no está en el programa',
            'puntos': partner.dcasa_saldo,
            'ultimos_movimientos': [{'fecha': c.fecha(m.ocurrido_en), 'tipo': TIPOS_MOVIMIENTO.get(m.tipo, m.tipo),
                                     'puntos': m.puntos, 'motivo': m.motivo or ''} for m in movimientos],
        }

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    @herramienta(
        nombre='crear_cliente',
        descripcion='Crea un cliente. El celular es la llave: si ya existe una ficha con ese celular, no se '
                    'duplica y te digo de quién es.',
        parametros={
            'nombre': {'type': 'string', 'description': 'Nombre completo o razón social, p. ej. «Ana Gómez».'},
            'celular': {'type': 'string', 'description': 'Celular de Panamá, p. ej. «6123-4567».'},
            'correo': {'type': 'string', 'description': 'Correo electrónico. Opcional.'},
            'ruc': {'type': 'string', 'description': 'RUC o cédula, p. ej. «8-888-888». Opcional.'},
            'es_empresa': {'type': 'boolean', 'description': 'true si es una empresa. Por defecto false.'},
        },
        requeridos=['nombre', 'celular'],
        nivel='construccion', categoria='clientes', grupos=INTERNO,
        ejemplos=['crea a Ana Gómez, 6123-4567'],
    )
    def _h_crear_cliente(self, nombre, celular, correo=None, ruc=None, es_empresa=False):
        nombre = (nombre or '').strip()
        if not nombre:
            raise BrianError('El cliente necesita un nombre.')
        normal = self._b_celular(celular)
        otro = self._b_duplicado_celular(normal)
        if otro:
            raise BrianError(f'El {R.celular_fmt(normal)} ya es de {otro.display_name}: un celular, un cliente. '
                             'Usa esa ficha (ver_cliente) o actualízala en vez de crear otra.')
        partner = self.env['res.partner'].create({
            'name': nombre, 'phone': R.celular_fmt(normal), 'email': (correo or '').strip() or False,
            'vat': (ruc or '').strip() or False, 'is_company': bool(es_empresa), 'customer_rank': 1,
        })
        return {'mensaje': f'Cliente «{partner.name}» creado.', **self._b_ficha_contacto(partner)}

    @herramienta(
        nombre='actualizar_cliente',
        descripcion='Cambia un dato de contacto de un cliente o proveedor: nombre, celular, correo, dirección, '
                    'RUC o DV.',
        parametros={
            'cliente': PARAM_CLIENTE,
            'campo': {'type': 'string', 'enum': list(CAMPOS_CONTACTO), 'description': 'Qué dato cambiar.'},
            'valor': {'type': 'string', 'description': 'El dato nuevo, p. ej. «ana@correo.com».'},
        },
        requeridos=['cliente', 'campo', 'valor'],
        nivel='construccion', categoria='clientes', grupos=INTERNO,
        ejemplos=['el correo de Ana Gómez es ana@correo.com → campo=correo'],
    )
    def _h_actualizar_cliente(self, cliente, campo, valor):
        if campo not in CAMPOS_CONTACTO:
            raise BrianError(f'Solo puedo cambiar: {", ".join(CAMPOS_CONTACTO)}.')
        partner = self._b_contacto(cliente)
        valor = (valor or '').strip()
        if campo == 'nombre' and not valor:
            raise BrianError('El nombre no puede quedar vacío.')
        if campo == 'celular':
            normal = self._b_celular(valor)
            otro = self._b_duplicado_celular(normal, excepto=partner)
            if otro:
                raise BrianError(f'El {R.celular_fmt(normal)} ya es de {otro.display_name}: un celular, un cliente. '
                                 'Si son la misma persona, que una persona una las fichas desde Contactos.')
            if partner.dcasa_celular and partner.dcasa_celular != normal:
                llave = R.celular_fmt(partner.dcasa_celular)
                raise BrianError(f'{partner.display_name} es socio con el celular {llave}'
                                 ', que es la llave de su cuenta de puntos. Cambiarlo lo hace una persona desde '
                                 'la ficha del socio.')
            valor = R.celular_fmt(normal)
        partner.write({CAMPOS_CONTACTO[campo]: valor or False})
        return {'mensaje': f'Actualicé {campo} de {partner.display_name}.', **self._b_ficha_contacto(partner)}

    # ------------------------------------------------------------------
    # Sensibles
    # ------------------------------------------------------------------

    @herramienta(
        nombre='ajustar_puntos',
        descripcion='Ajuste manual de puntos de un socio (suma o resta) con motivo que el socio verá. Pasa por el '
                    'ajuste del programa Socios: queda como asiento en su libro, nunca se edita el saldo.',
        parametros={
            'cliente': PARAM_CLIENTE,
            'puntos': {'type': 'integer', 'description': 'Positivo suma, negativo resta, p. ej. -200.'},
            'motivo': {'type': 'string', 'description': 'Por qué, escrito para el socio, p. ej. «Compra del 12/09 '
                                                        'no registrada».'},
        },
        requeridos=['cliente', 'puntos', 'motivo'],
        nivel='sensible', categoria='clientes', grupos=('sales_team.group_sale_manager',),
        ejemplos=['súmale 300 puntos a Ana por la compra que no se registró'],
    )
    def _h_ajustar_puntos(self, cliente, puntos, motivo):
        partner = self._b_contacto(cliente, 'socio').commercial_partner_id
        if not isinstance(puntos, int) or isinstance(puntos, bool) or not puntos:
            raise BrianError('Los puntos van en un número entero distinto de cero.')
        antes = partner.dcasa_saldo
        asistente = self.env['dcasa.ajuste.wizard'].create(
            {'partner_id': partner.id, 'puntos': puntos, 'motivo': (motivo or '').strip()})
        asistente.action_confirmar()
        partner.invalidate_recordset(['dcasa_saldo'])
        return {'mensaje': f'Ajuste de {puntos:+d} puntos a {partner.display_name}.',
                'antes': antes, 'ahora': partner.dcasa_saldo, 'fecha': c.fecha(fields.Date.context_today(self))}
