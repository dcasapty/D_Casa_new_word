"""Herramientas de clientes y proveedores (y los puntos del programa Socios D'CASA).

Reglas de Socios que se respetan aquí:
* Un cliente y un socio son la misma ficha (``res.partner``) y la llave es el celular:
  crear o cambiar un celular nunca duplica una ficha existente.
* El saldo de puntos ES la suma de ``dcasa.movimiento``: se lee, nunca se escribe aquí.
  El único ajuste que se ofrece pasa por el asistente del propio módulo (con motivo).
"""
from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import bien_escrito as B
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.addons.dcasa_socios.models.dcasa_movimiento import TIPOS

from . import herramientas_comun as c
from .registro import BrianError, herramienta

INTERNO = ('base.group_user',)
FACTURACION = ('account.group_account_invoice',)
PARAM_CLIENTE = {'type': 'string', 'description': 'Nombre, celular, RUC/cédula o código de socio, '
                                                   'p. ej. «Ana Gómez» o «6123-4567».'}
CAMPOS_CONTACTO = {'nombre': 'name', 'celular': 'phone', 'telefono_fijo': 'dcasa_telefono_fijo', 'correo': 'email',
                   'direccion': 'street', 'ruc': 'vat', 'dv': 'l10n_pa_dv'}
# Lo que se escribe en «correo» cuando el cliente de verdad no tiene: marca «Cliente no tiene correo electrónico»
# (decisión de la dueña, 2026-10-17). Solo exime del correo; el celular sigue obligatorio.
SIN_CORREO = frozenset({'no tiene', 'no tiene correo', 'no tiene correo electronico', 'no tiene correo electrónico',
                        'sin correo', 'sin correo electronico', 'sin correo electrónico'})
TIPOS_MOVIMIENTO = dict(TIPOS)


class BrianHerramientasClientes(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _b_dice_sin_correo(texto):
        """¿Escribieron «no tiene» (o «sin correo») en vez del correo?"""
        return ' '.join(str(texto or '').lower().replace('.', ' ').split()) in SIN_CORREO

    @api.model
    def _b_correo(self, texto):
        """El correo bien escrito y limpio (``ana@gmail.com``), o BrianError con «¿Quisiste decir…?»."""
        codigo, sugerencia = B.problema_del_correo(texto)
        if codigo == 'vacio':
            raise BrianError('Falta el correo del cliente: ahí le llegan su factura y cómo ver sus puntos. Pídeselo; '
                             'si de verdad no tiene, escribe «no tiene» en el correo.')
        if codigo:
            raise BrianError(B.mensaje_del_correo(self.env, texto, codigo, sugerencia))
        return B.correo_limpio(texto)

    @api.model
    def _b_celular(self, texto):
        """``(como se guarda, 8 dígitos)``: «+507 6123-4567» y «61234567» (Panamá), o «+13055551234» y ``None`` (otro
        país). BrianError con lo que está mal escrito (las mismas reglas que la ficha del cliente)."""
        codigo = B.problema_del_telefono(texto)
        if codigo:
            raise BrianError(B.mensaje_del_telefono(self.env, texto, codigo))
        guardar = B.telefono_para_guardar(texto)
        return guardar, (R.celular_normal(guardar) if guardar.startswith(f'+{B.PANAMA} ') else None)

    @api.model
    def _b_fijo(self, texto):
        """El teléfono fijo como se guarda («+507 234-5678»), o BrianError con lo que está mal escrito (las mismas
        reglas que la ficha del cliente). No es una llave: no se busca si ya lo tiene otra ficha."""
        codigo = B.problema_del_fijo(texto)
        if codigo:
            raise BrianError(B.mensaje_del_fijo(self.env, texto, codigo))
        return B.fijo_para_guardar(texto)

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
        deuda = {'por_cobrar': c.moneda(sum(facturas.mapped('amount_residual'))),
                 'vencido': c.moneda(sum(vencidas.mapped('amount_residual'))),
                 'facturas_abiertas': len(facturas)}
        if nota := c.alcance(self.env):
            deuda['alcance'] = nota
        return deuda

    @api.model
    def _b_ficha_contacto(self, partner):
        guardado = B.telefono_para_guardar(partner.phone) if partner.phone else None
        if guardado and not guardado.startswith(f'+{B.PANAMA} '):
            celular = guardado  # de otro país, con su «+»
        else:
            celular = R.celular_fmt(R.celular_normal(partner.phone)) if partner.phone else ''
        ficha = {
            'nombre': partner.display_name,
            'celular': celular,
            'telefono_fijo': partner.dcasa_telefono_fijo or '',
            'correo': partner.email or '',
            'no_tiene_correo': bool(partner.commercial_partner_id.dcasa_sin_correo),
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
        descripcion='Busca clientes o proveedores por nombre, celular, teléfono fijo, RUC/cédula o correo.',
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
            'telefono_fijo': p.dcasa_telefono_fijo or '',
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
        resultado = {
            'criterio': 'vencido' if solo_vencido or solo_vencido is None else 'todo lo pendiente',
            'clientes_con_deuda': len(grupos),
            'total': c.moneda(total),
            'clientes': [{'cliente': p.display_name, 'debe': c.moneda(m), 'facturas': n}
                         for p, m, n in grupos[:c.limite(limite)]],
        }
        if nota := c.alcance(self.env):
            resultado['alcance'] = nota
        return resultado

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
        descripcion='Crea un cliente con su celular (o su fijo de 7 números) y su correo, bien escritos. Antes busca: '
                    'si su celular, correo o RUC ya es de otra ficha, o hay una con un nombre parecido, no crea nada '
                    'y te dice cuál es.',
        parametros={
            'nombre': {'type': 'string', 'description': 'Nombre completo o razón social, p. ej. «Ana Gómez».'},
            'celular': {'type': 'string', 'description': 'Celular de Panamá, p. ej. «6123-4567». Si no tiene '
                                                         'celular: su teléfono fijo, p. ej. «234-5678».'},
            'correo': {'type': 'string', 'description': 'Correo, obligatorio, p. ej. «ana@gmail.com». Solo si el '
                                                        'cliente dice que NO tiene correo: «no tiene».'},
            'ruc': {'type': 'string', 'description': 'RUC o cédula, p. ej. «8-888-888». Opcional.'},
            'es_empresa': {'type': 'boolean', 'description': 'true si es una empresa. Por defecto false.'},
        },
        requeridos=['nombre', 'celular', 'correo'],
        nivel='construccion', categoria='clientes', grupos=INTERNO,
        ejemplos=['crea a Ana Gómez, 6123-4567, ana@gmail.com',
                  'crea a Pedro Pérez, no tiene celular, su fijo es 234-5678, pedro@gmail.com'],
    )
    def _h_crear_cliente(self, nombre, celular=None, correo=None, ruc=None, es_empresa=False):
        return self._b_crear_cliente(nombre, celular, correo, ruc, es_empresa, revisar_parecidas=True)

    @herramienta(
        nombre='crear_cliente_distinto',
        descripcion='Igual que crear_cliente, pero úsala SOLO si crear_cliente encontró fichas con un nombre '
                    'parecido y la persona te confirmó que es otra persona. El celular, correo y RUC siguen sin '
                    'poder repetirse.',
        parametros={
            'nombre': {'type': 'string', 'description': 'Nombre completo o razón social.'},
            'celular': {'type': 'string', 'description': 'Celular de Panamá, p. ej. «6123-4567», o su fijo.'},
            'correo': {'type': 'string', 'description': 'Correo, o «no tiene» si de verdad no tiene.'},
            'ruc': {'type': 'string', 'description': 'RUC o cédula. Opcional.'},
            'es_empresa': {'type': 'boolean', 'description': 'true si es una empresa. Por defecto false.'},
        },
        requeridos=['nombre', 'celular', 'correo'],
        nivel='construccion', categoria='clientes', grupos=INTERNO,
        ejemplos=['sí, es otra Ana Gómez: créala'],
    )
    def _h_crear_cliente_distinto(self, nombre, celular=None, correo=None, ruc=None, es_empresa=False):
        return self._b_crear_cliente(nombre, celular, correo, ruc, es_empresa, revisar_parecidas=False)

    @api.model
    def _b_crear_cliente(self, nombre, celular, correo, ruc, es_empresa, revisar_parecidas):
        """Buscar antes de crear (etapa 3): celular, correo y RUC de otra ficha bloquean; un nombre parecido
        pregunta."""
        nombre = (nombre or '').strip()
        if not nombre:
            raise BrianError('El cliente necesita un nombre.')
        if not (celular or '').strip():
            raise BrianError('Falta el celular del cliente: pídeselo. Si de verdad no tiene, dime su teléfono fijo.')
        fijo = False
        if B.problema_del_telefono(celular) == 'fijo':  # 7 números: su teléfono fijo, no un celular incompleto
            fijo, celular = self._b_fijo(celular), None
        telefono, normal = self._b_celular(celular) if celular else (False, None)
        sin_correo = self._b_dice_sin_correo(correo)
        correo = False if sin_correo else self._b_correo(correo)
        otro = self._b_duplicado_celular(normal) if normal else None
        if otro:
            raise BrianError(f'El {R.celular_fmt(normal)} ya es de {otro.display_name}: un celular, un cliente. '
                             'Usa esa ficha (ver_cliente) o actualízala en vez de crear otra.')
        Partner = self.env['res.partner']
        ruc = (ruc or '').strip() or False
        por_dato = Partner._dcasa_buscar_ficha(correo=correo or None, ruc=ruc or None)
        if por_dato:
            raise BrianError(f'Ese correo o RUC ya es de {por_dato.sudo().display_name}: es la misma persona. Usa esa '
                             'ficha (ver_cliente) o actualízala en vez de crear otra.')
        if revisar_parecidas:
            parecidas = Partner._dcasa_fichas_parecidas(nombre)
            if parecidas:
                lista = ', '.join(Partner._dcasa_describir_ficha(f) for f in parecidas)
                raise BrianError(f'No lo creé: ya hay fichas con un nombre parecido: {lista}. Pregúntale a la persona '
                                 'si es alguna de ellas (entonces usa esa ficha). Si confirma que es otra persona, usa '
                                 'crear_cliente_distinto.')
        partner = Partner.create({
            'name': nombre, 'phone': telefono, 'dcasa_telefono_fijo': fijo, 'email': correo,
            'dcasa_sin_correo': sin_correo, 'vat': ruc, 'is_company': bool(es_empresa), 'customer_rank': 1,
        })
        return {'mensaje': f'Cliente «{partner.name}» creado.', **self._b_ficha_contacto(partner)}

    @herramienta(
        nombre='actualizar_cliente',
        descripcion='Cambia un dato de contacto de un cliente o proveedor: nombre, celular, teléfono fijo, correo, '
                    'dirección, RUC o DV.',
        parametros={
            'cliente': PARAM_CLIENTE,
            'campo': {'type': 'string', 'enum': list(CAMPOS_CONTACTO), 'description': 'Qué dato cambiar.'},
            'valor': {'type': 'string', 'description': 'El dato nuevo, p. ej. «ana@correo.com». Correo «no tiene»: el '
                                                       'cliente no tiene correo.'},
        },
        requeridos=['cliente', 'campo', 'valor'],
        nivel='construccion', categoria='clientes', grupos=INTERNO,
        ejemplos=['el correo de Ana Gómez es ana@correo.com → campo=correo',
                  'el teléfono de la casa de Pedro es 234-5678 → campo=telefono_fijo'],
    )
    def _h_actualizar_cliente(self, cliente, campo, valor):
        if campo not in CAMPOS_CONTACTO:
            raise BrianError(f'Solo puedo cambiar: {", ".join(CAMPOS_CONTACTO)}.')
        partner = self._b_contacto(cliente)
        valor = (valor or '').strip()
        if campo == 'celular' and B.problema_del_telefono(valor) == 'fijo':
            campo = 'telefono_fijo'  # 7 números: es su teléfono fijo, no un celular incompleto
        if campo == 'nombre' and not valor:
            raise BrianError('El nombre no puede quedar vacío.')
        if campo == 'celular':
            valor, normal = self._b_celular(valor)
            otro = self._b_duplicado_celular(normal, excepto=partner) if normal else None
            if otro:
                raise BrianError(f'El {R.celular_fmt(normal)} ya es de {otro.display_name}: un celular, un cliente. '
                                 'Si son la misma persona, que una persona una las fichas desde Contactos.')
            if partner.dcasa_celular and partner.dcasa_celular != normal:
                llave = R.celular_fmt(partner.dcasa_celular)
                raise BrianError(f'{partner.display_name} es socio con el celular {llave}'
                                 ', que es la llave de su cuenta de puntos. Cambiarlo lo hace una persona desde '
                                 'la ficha del socio.')
        if campo == 'correo' and self._b_dice_sin_correo(valor):
            if partner.email and not B.problema_del_correo(partner.email)[0]:
                raise BrianError(f'{partner.display_name} ya tiene el correo {partner.email}. Si está mal, dime el '
                                 'correcto; si de verdad no tiene, que lo borre una persona desde su ficha.')
            if partner.email:  # lo que había estaba mal escrito o era de relleno («no@no.com»)
                partner.write({'email': False})
            partner.commercial_partner_id.write({'dcasa_sin_correo': True})
            return {'mensaje': f'Marqué que {partner.display_name} no tiene correo electrónico.',
                    **self._b_ficha_contacto(partner)}
        if campo == 'correo':
            valor = self._b_correo(valor)
        if campo == 'telefono_fijo' and valor:
            valor = self._b_fijo(valor)
        partner.write({CAMPOS_CONTACTO[campo]: valor or False})
        que = 'el teléfono fijo' if campo == 'telefono_fijo' else campo
        return {'mensaje': f'Actualicé {que} de {partner.display_name}.', **self._b_ficha_contacto(partner)}

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
