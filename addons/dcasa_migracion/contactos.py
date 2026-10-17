"""Carga de clientes y proveedores del sistema anterior (``reglas.filas_contactos``).

* Una ficha por persona, con su número del sistema anterior como id externo (``__import__.dcasa_contacto_<n>``):
  volver a cargar el mismo archivo no crea nada y NO pisa lo que ya se cambió aquí. Quien es cliente y proveedor
  tiene UNA sola ficha (mismo número en los dos archivos): la segunda carga solo le agrega el otro papel.
  El id externo es de «__import__», como los de la importación de Odoo, y NO de este módulo: desinstalar un módulo
  borra todo lo que tiene id externo suyo, y las fichas no pueden desaparecer si algún día se quita esta pantalla.
* El candado de contactos NO se salta: si el celular o el correo ya son de otra ficha, esa fila no se crea y queda en
  el informe con el motivo, para resolverla a mano (fusionando, o corrigiendo el dato).
* Mismo RUC o cédula = misma persona («un RUC, una persona»): esa fila no crea otra ficha; su número del sistema
  anterior queda enlazado a la que ya existe (mismo id externo ``__import__.dcasa_contacto_<n>``) y sus órdenes,
  facturas y pagos se cargan a ella. Va en el informe («enlazados») para revisar que sea la misma persona.
* Un cliente no es un socio: no se le pone PIN ni celular de Socios, así que no reclama ficha ni junta puntos. Tampoco
  se le escribe nada: Juan solo contesta a quien le escribe.
* Cada fila va en su propio savepoint: una ficha mala no tumba a las demás.
"""
import logging

import psycopg2

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)

MODULO = '__import__'
ETIQUETA = 'Sistema anterior'


def xmlid_contacto(id_viejo):
    return f'dcasa_contacto_{id_viejo}'


def _etiqueta_de_origen(env):
    """La etiqueta «Sistema anterior» (se crea la primera vez): sirve para filtrar lo que vino de la carga."""
    Etiqueta = env['res.partner.category']
    return Etiqueta.search([('name', '=', ETIQUETA)], limit=1) or Etiqueta.create({'name': ETIQUETA})


ROLES = {'cliente': ('customer_rank', 'Cliente'), 'proveedor': ('supplier_rank', 'Proveedor')}


def _valores(fila, pais, etiqueta, rol):
    campo_rol, nombre_rol = ROLES[rol]
    notas = [f'{nombre_rol} n.º {fila["id_viejo"]} del sistema anterior.'] + fila['notas']
    valores = {
        'name': fila['nombre'],
        'is_company': fila['es_empresa'],
        campo_rol: 1,
        'category_id': [(4, etiqueta.id)],
        'comment': plaintext2html('\n'.join(notas)),
    }
    for campo, clave in (('vat', 'vat'), ('l10n_pa_dv', 'dv'), ('phone', 'telefono'), ('email', 'correo'),
                         ('street', 'direccion'), ('city', 'ciudad')):
        if fila[clave]:
            valores[campo] = fila[clave]
    if pais:
        valores['country_id'] = pais.id
    return valores


def _pais(env, nombre, por_defecto):
    """El país por su nombre (en español o en inglés); Panamá si el archivo no dice; vacío si no se encuentra."""
    if not nombre:
        return por_defecto
    Pais = env['res.country']
    return (Pais.with_context(lang='es_419').search([('name', '=ilike', nombre)], limit=1)
            or Pais.with_context(lang='en_US').search([('name', '=ilike', nombre)], limit=1))


def _motivo(error):
    if isinstance(error, psycopg2.Error):
        return 'la base de datos rechazó la ficha'
    return ' '.join(str(error).split()) or error.__class__.__name__


def _ficha_con_el_mismo_ruc(env, fila):
    """La ficha que ya tiene el mismo RUC o cédula que esta fila (con las mismas reglas del candado), o vacío."""
    if not fila['vat']:
        return env['res.partner']
    return env['res.partner']._dcasa_buscar_ficha(ruc=fila['vat'])


def _numero_viejo_de(env, ficha):
    """El número del sistema anterior con que se creó esta ficha (``None`` si ya existía por otro lado)."""
    dato = env['ir.model.data'].search([
        ('module', '=', MODULO), ('model', '=', 'res.partner'), ('res_id', '=', ficha.id),
        ('name', '=like', 'dcasa_contacto_%')], order='id', limit=1)
    return dato.name.removeprefix('dcasa_contacto_') if dato else None


def cargar_clientes(env, filas):
    return cargar_contactos(env, filas, 'cliente')


def cargar_proveedores(env, filas):
    return cargar_contactos(env, filas, 'proveedor')


def cargar_contactos(env, filas, rol):
    """Crea las fichas que faltan. Devuelve ``{'creados': [(id_viejo, nombre)], 'ya_estaban': [id_viejo],
    'ampliados': [id_viejo], 'enlazados': [(id_viejo, n.º de la ficha o None, nombre de la ficha)],
    'con_error': [(id_viejo, nombre, motivo)]}``. ``ampliados`` son fichas que ya estaban con el otro papel (cliente o
    proveedor) y ahora tienen también este. ``enlazados`` son filas con el mismo RUC o cédula que otra ficha: su número
    quedó apuntando a esa ficha (el n.º que ella tiene del sistema anterior, si lo tiene). No hace commit: lo decide
    quien llama."""
    # no_vat_validation: el RUC o la cédula se guardan como estaban (un proveedor del extranjero no sigue el formato de
    # Panamá). El candado de contactos sigue comparando el RUC con el de las demás fichas.
    # dcasa_sin_exigir_contacto: lo viejo entra como estaba (el celular y el correo los exige la venta nueva); los
    # correos mal escritos ya quedaron vacíos y anotados al leer el archivo.
    Partner = env['res.partner'].with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True, no_reset_password=True,
        no_vat_validation=True, dcasa_sin_exigir_contacto=True)
    panama = env.ref('base.pa', raise_if_not_found=False)
    etiqueta = _etiqueta_de_origen(env)
    campo_rol = ROLES[rol][0]
    resumen = {'creados': [], 'ya_estaban': [], 'ampliados': [], 'enlazados': [], 'con_error': []}
    for fila in filas:
        id_viejo = fila['id_viejo']
        nombre_externo = xmlid_contacto(id_viejo)
        existente = env['ir.model.data']._xmlid_to_res_id(f'{MODULO}.{nombre_externo}', raise_if_not_found=False)
        ficha = env['res.partner'].browse(existente).exists() if existente else env['res.partner']
        if existente and not ficha:
            # El id externo apuntaba a una ficha que ya no existe: se limpia para poder crearla de nuevo.
            env['ir.model.data'].search([('module', '=', MODULO), ('name', '=', nombre_externo)]).unlink()
        if ficha:
            if ficha[campo_rol]:
                resumen['ya_estaban'].append(id_viejo)
            else:
                ficha.write({campo_rol: 1})
                resumen['ampliados'].append(id_viejo)
            continue
        igual = _ficha_con_el_mismo_ruc(env, fila)
        if igual:
            otro_numero = _numero_viejo_de(env, igual)   # antes de enlazar: si no, se encontraría a sí mismo
            try:
                with env.cr.savepoint():
                    env['ir.model.data'].create({
                        'module': MODULO, 'name': nombre_externo, 'model': 'res.partner', 'res_id': igual.id,
                        'noupdate': True})
                    if not igual[campo_rol]:
                        igual.write({campo_rol: 1})
            except (ValidationError, UserError, AccessError, psycopg2.Error) as error:
                resumen['con_error'].append((id_viejo, fila['nombre'], _motivo(error)))
                continue
            resumen['enlazados'].append((id_viejo, otro_numero, igual.name))
            continue
        pais = _pais(env, fila['pais'], panama)
        datos = fila
        if fila['pais'] and not pais:
            datos = dict(fila, notas=fila['notas'] + [f'País en el sistema anterior: {fila["pais"]}'])
        try:
            with env.cr.savepoint():
                ficha = Partner.create(_valores(datos, pais, etiqueta, rol))
                env['ir.model.data'].create({
                    'module': MODULO, 'name': nombre_externo, 'model': 'res.partner', 'res_id': ficha.id,
                    'noupdate': True})
        except (ValidationError, UserError, AccessError, psycopg2.Error) as error:
            resumen['con_error'].append((id_viejo, fila['nombre'], _motivo(error)))
            continue
        resumen['creados'].append((id_viejo, fila['nombre']))
    # Solo cantidades en el registro del servidor: los nombres de las personas no van a los logs.
    _logger.info('Carga de %ss: %s creados, %s ya estaban, %s ampliados, %s enlazados, %s con error.', rol,
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['ampliados']),
                 len(resumen['enlazados']), len(resumen['con_error']))
    return resumen
