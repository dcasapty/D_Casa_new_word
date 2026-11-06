"""«Cargar lugares y tarifa desde el archivo» (Envíos › Tarifa, solo Gerencia y administradores).

Gerencia sube el mismo ``envios-dcasa.html`` de la propuesta (o un JSON con su forma) y el módulo lee sus tres bloques
(lugares, tarifa y lugares agregados a mano). Volver a cargar es seguro:

* actualiza sin duplicar (llave: nombre + tipo + distrito + corregimiento; si dos lugares distintos comparten la llave,
  se emparejan por sus coordenadas);
* no toca los lugares agregados en Odoo por el equipo, ni los del archivo que Gerencia cambió o archivó en Odoo;
* archiva (no borra) los que ya no vienen en el archivo;
* la tarifa del archivo reemplaza a la de Odoo solo si se marca, y si cambia algo vuelve a revisión (la aprobación es
  siempre en Odoo, con quién y cuándo: el «aprobada» del archivo no cuenta);
* al terminar muestra un resumen y lo deja en el historial de la tarifa.
"""
import base64
import math
from collections import Counter, defaultdict

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.lugar import CONTEXTO_IMPORTANDO, IMPORTANDO
from ..motor import archivo

MAX_BYTES = 30 * 1024 * 1024
CAMPOS_COMPARADOS = ('name', 'alias', 'tipo', 'cat', 'corr', 'corr_exacto', 'dist', 'prov', 'km', 'km_medido', 'peaje',
                     'estado', 'fuente_km', 'lat', 'lon', 'nota', 'agregado', 'active')
CAMPOS_TARIFA = ('minimo', 'ancla_a_km', 'ancla_a_precio', 'ancla_b_km', 'ancla_b_precio', 'ancla_b_nombre',
                 'ajuste_pct', 'paso', 'modo', 'max_km', 'nota', 'version_archivo', 'fecha_archivo')
CAMPOS_CARGO = ('name', 'como', 'monto', 'desde', 'ajusta', 'activo', 'sequence')
TANDA = 2000


def _igual(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a or 0.0), float(b or 0.0), rel_tol=0, abs_tol=1e-9)
    return (a or False) == (b or False)


def _emparejar(nuevos, viejos):
    """Empareja los lugares del archivo con los de Odoo que tienen la misma llave: el más cercano primero (casi
    siempre es uno con uno). Devuelve ``[(nuevo o None, viejo o None)]``."""
    if len(nuevos) == 1 and len(viejos) == 1:
        return [(nuevos[0], viejos[0])]

    def distancia(n, v):
        if not (n['lat'] or n['lon']) or not (v['lat'] or v['lon']):
            return math.inf
        return math.hypot(n['lat'] - v['lat'], n['lon'] - v['lon'])
    candidatos = sorted(((distancia(n, v), i, j) for i, n in enumerate(nuevos) for j, v in enumerate(viejos)),
                        key=lambda x: (x[0], x[1], x[2]))
    usados_n, usados_v, pares = set(), set(), []
    for _d, i, j in candidatos:
        if i in usados_n or j in usados_v:
            continue
        usados_n.add(i)
        usados_v.add(j)
        pares.append((nuevos[i], viejos[j]))
    pares += [(n, None) for i, n in enumerate(nuevos) if i not in usados_n]
    pares += [(None, v) for j, v in enumerate(viejos) if j not in usados_v]
    return pares


class EnvioImportar(models.TransientModel):
    _name = 'dcasa.envio.importar'
    _description = 'Cargar lugares y tarifa de envíos desde el archivo'

    archivo = fields.Binary('Archivo', attachment=False, help='El envios-dcasa.html de la calculadora o su JSON.')
    nombre_archivo = fields.Char('Nombre del archivo')
    cargar_lugares = fields.Boolean('Cargar los lugares', default=True)
    cargar_tarifa = fields.Boolean('Cargar la tarifa del archivo', default=True,
                                   help='Reemplaza la tarifa de Odoo por la del archivo. Si cambia algo, vuelve a '
                                        'revisión hasta que Gerencia la apruebe.')
    estado = fields.Selection([('elegir', 'Elegir el archivo'), ('hecho', 'Listo')], default='elegir', readonly=True)
    resumen = fields.Text('Resumen', readonly=True)
    tarifa_aprobada = fields.Boolean(compute='_compute_tarifa_aprobada')

    @api.depends('estado')
    def _compute_tarifa_aprobada(self):
        aprobada = bool(self.env['dcasa.envio.tarifa']._vigente().aprobada)
        for asistente in self:
            asistente.tarifa_aprobada = aprobada

    def action_cargar(self):
        self.ensure_one()
        self.env['dcasa.envio.lugar']._exigir_gerencia()
        if not self.cargar_lugares and not self.cargar_tarifa:
            raise UserError(self.env._('Marca qué quieres cargar: los lugares, la tarifa o los dos.'))
        datos = base64.b64decode(self.archivo or b'')
        if not datos:
            raise UserError(self.env._('Elige el archivo envios-dcasa.html (o su JSON).'))
        if len(datos) > MAX_BYTES:
            raise UserError(self.env._('El archivo pesa más de 30 MB: revisa que sea el correcto.'))
        try:
            lugares, ajustes, agregados = archivo.leer_archivo(datos)
            # La tarifa se revisa ANTES de tocar los lugares: si está mal, no cambia nada.
            tarifa_del_archivo = (archivo.normalizar_ajustes(ajustes)
                                  if self.cargar_tarifa and ajustes is not None else None)
        except archivo.ArchivoInvalido as error:
            raise UserError(str(error)) from error
        lineas = []
        if self.cargar_lugares:
            lineas += self._cargar_lugares(lugares, agregados)
        if self.cargar_tarifa:
            lineas += self._cargar_tarifa(tarifa_del_archivo)
        resumen = '\n'.join(lineas)
        tarifa = self.env['dcasa.envio.tarifa']._vigente()
        if tarifa:
            titulo = self.env._('%(quien)s cargó %(archivo)s:', quien=self.env.user.name,
                                archivo=self.nombre_archivo or self.env._('el archivo'))
            tarifa.sudo().message_post(body=Markup('<br/>').join([titulo, *lineas]))
        self.write({'estado': 'hecho', 'resumen': resumen, 'archivo': False})
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
            'target': 'new', 'name': self.env._('Listo: así quedó'),
        }

    # --- Lugares ---------------------------------------------------------------------------------------------------
    def _cargar_lugares(self, lugares, agregados):
        Lugar = self.env['dcasa.envio.lugar'].with_context(active_test=False, **{CONTEXTO_IMPORTANDO: IMPORTANDO})
        entrantes, omitidos, avisos = self._entrantes(lugares, agregados)
        viejos = defaultdict(list)
        campos = list(CAMPOS_COMPARADOS) + ['llave', 'editado_el', 'secuencia']
        for fila in Lugar.search_read([('origen', '=', 'archivo')], campos):
            viejos[fila['llave']].append(fila)
        plan = self._comparar(entrantes, viejos)
        for inicio in range(0, len(plan['crear']), TANDA):
            Lugar.create(plan['crear'][inicio:inicio + TANDA])
        actualizados = 0
        for diferencias, ids in plan['cambios'].items():
            Lugar.browse(ids).write(dict(diferencias))
            actualizados += len(ids)
        self._poner_secuencias(Lugar, plan['secuencias'])
        if plan['archivar']:
            Lugar.browse(plan['archivar']).write({'active': False})
        Lugar._subir_version()
        lineas = [self.env._('Lugares del archivo: %s.', len(lugares) + len(agregados)),
                  self.env._('· Nuevos: %s', len(plan['crear'])),
                  self.env._('· Actualizados: %s', actualizados),
                  self.env._('· Sin cambios: %s', plan['iguales'])]
        if plan['archivar']:
            lineas.append(self.env._('· Archivados porque ya no vienen en el archivo: %s', len(plan['archivar'])))
        if plan['respetados']:
            lineas.append(self.env._('· Cambiados o archivados en Odoo por Gerencia (se respetó lo de Odoo): %s',
                                     plan['respetados']))
        lineas += [self.env._('· No se cargaron (%(motivo)s): %(cuantos)s', motivo=motivo, cuantos=cuantos)
                   for motivo, cuantos in sorted(omitidos.items())]
        lineas += [self.env._('· Cargados como «sin dato» (%(motivo)s): %(cuantos)s', motivo=motivo, cuantos=cuantos)
                   for motivo, cuantos in sorted(avisos.items())]
        a_mano = Lugar.search_count([('origen', '=', 'mano'), ('active', '=', True)])
        lineas.append(self.env._('Lugares agregados en Odoo por el equipo (no se tocan): %s.', a_mano))
        return lineas

    @staticmethod
    def _entrantes(lugares, agregados):
        """Los lugares del archivo ya revisados, agrupados por su llave; y cuántos no se cargaron (y por qué)."""
        omitidos, avisos, entrantes = Counter(), Counter(), defaultdict(list)
        for posicion, dato in enumerate(list(lugares) + list(agregados)):
            limpio, motivo = archivo.normalizar_lugar(dato)
            if not limpio:
                omitidos[motivo] += 1
                continue
            if motivo:
                avisos[motivo] += 1
            limpio.update(origen='archivo', agregado=posicion >= len(lugares), secuencia=posicion + 1, active=True)
            limpio['llave'] = archivo.llave(limpio)
            entrantes[limpio['llave']].append(limpio)
        return entrantes, omitidos, avisos

    @staticmethod
    def _comparar(entrantes, viejos):
        """Qué hacer con cada lugar: crear, actualizar (agrupados por cambio), archivar, el nuevo orden y cuántos
        quedan igual o se respetan (los que Gerencia cambió o archivó en Odoo)."""
        plan = {'crear': [], 'cambios': defaultdict(list), 'archivar': [], 'secuencias': [], 'iguales': 0,
                'respetados': 0}
        for clave in list(entrantes) + [c for c in viejos if c not in entrantes]:
            for nuevo, viejo in _emparejar(entrantes.get(clave, []), viejos.get(clave, [])):
                if viejo is None:
                    plan['crear'].append(nuevo)
                elif viejo['editado_el']:
                    plan['respetados'] += 1
                elif nuevo is None:
                    if viejo['active']:
                        plan['archivar'].append(viejo['id'])
                else:
                    diferencias = {c: nuevo[c] for c in CAMPOS_COMPARADOS if not _igual(nuevo[c], viejo[c])}
                    if diferencias:
                        plan['cambios'][tuple(sorted(diferencias.items()))].append(viejo['id'])
                    else:
                        plan['iguales'] += 1
                    if nuevo['secuencia'] != viejo['secuencia']:
                        plan['secuencias'].append((viejo['id'], nuevo['secuencia']))
        return plan

    def _poner_secuencias(self, Lugar, secuencias):
        """El orden en el archivo (solo desempata la búsqueda) va por SQL en tandas: un lugar nuevo al principio del
        archivo corre el orden de todos los demás, y escribirlos uno por uno con el ORM tardaría minutos. Es un campo
        de solo lectura que no usa ningún cálculo."""
        Lugar.flush_model()
        for inicio in range(0, len(secuencias), TANDA):
            tanda = secuencias[inicio:inicio + TANDA]
            self.env.cr.execute(
                'UPDATE dcasa_envio_lugar AS l SET secuencia = v.s FROM (SELECT unnest(%s::int[]) AS id, '
                'unnest(%s::int[]) AS s) AS v WHERE l.id = v.id', [[i for i, _s in tanda], [s for _i, s in tanda]])
        if secuencias:
            Lugar.invalidate_model(['secuencia'])

    # --- Tarifa ----------------------------------------------------------------------------------------------------
    def _cargar_tarifa(self, tarifa_del_archivo):
        if tarifa_del_archivo is None:
            return [self.env._('El archivo no trae tarifa: la de Odoo no cambió.')]
        valores, cargos = tarifa_del_archivo
        Tarifa = self.env['dcasa.envio.tarifa']
        tarifa = Tarifa.search([], limit=1) or Tarifa.create({})
        antes = tarifa._firma()
        estaba_aprobada = tarifa.aprobada
        comandos, por_codigo = [], {c.codigo: c for c in tarifa.cargo_ids if c.codigo}
        for cargo in cargos:
            actual = por_codigo.pop(cargo['codigo'], None)
            if actual is None:
                comandos.append((0, 0, cargo))
            elif any(not _igual(cargo[c], actual[c]) for c in CAMPOS_CARGO):
                comandos.append((1, actual.id, {c: cargo[c] for c in CAMPOS_CARGO}))
        del_archivo = {c['codigo'] for c in cargos}
        comandos += [(2, sobra.id, 0) for sobra in tarifa.cargo_ids if sobra.codigo not in del_archivo]
        cambios = {c: valores[c] for c in CAMPOS_TARIFA if not _igual(valores[c], tarifa[c] if c != 'fecha_archivo'
                                                                       else fields.Date.to_string(tarifa[c]) or False)}
        cambios.update(cargada_por=self.env.uid, cargada_el=fields.Datetime.now())
        if comandos:
            cambios['cargo_ids'] = comandos
        tarifa.write(cambios)
        if tarifa._firma() == antes:
            return [self.env._('Tarifa: igual a la de Odoo (%s).',
                               self.env._('sigue aprobada') if estaba_aprobada else self.env._('sigue en revisión'))]
        return [self.env._('Tarifa: cargada del archivo. Queda en revisión: estos precios todavía no se usan con '
                           'clientes hasta que Gerencia la apruebe en Envíos › Tarifa.')]
