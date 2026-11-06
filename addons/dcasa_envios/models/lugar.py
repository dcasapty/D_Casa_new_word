"""Los lugares a donde D'CASA lleva (corregimientos, barrios, edificios y lugares conocidos) y el buscador.

* Los del archivo de Gerencia (``origen = archivo``) los carga «Cargar lugares y tarifa desde el archivo»; volver a
  cargar los actualiza sin duplicar (``llave``) y respeta lo que Gerencia cambió en Odoo (``editado_el``).
* Cualquier persona del equipo agrega el que falta desde la calculadora (``origen = mano``): queda su nombre y la
  fecha. Solo Gerencia y los administradores editan o archivan.
* El buscador es el del motor (``motor/buscador.py``). Su índice se arma una vez por base de datos y por proceso, y se
  vuelve a armar cuando cambia ``dcasa_envios.version_lugares`` (sube en cada alta, cambio o baja de un lugar o de la
  tarifa). Es un valor al azar, no un contador: si una transacción que lo subió se deshace, nadie vuelve a usar ese
  valor con otros datos. Funciona igual con varios procesos (cada uno compara la versión con la de la base).

Punto de entrada para la web y Juan (mañana): :meth:`buscar_para_cotizar` (aquí) y ``cotizar_lugar`` / ``cotizar_km``
de ``dcasa.envio.tarifa``. Devuelven datos puros, iguales para cualquier usuario. Ver docs/ENVIOS.md.
"""
import threading
import uuid

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..motor import buscador
from ..motor import tarjeta as motor_tarjeta
from ..motor.tarifa import Tarifa
from ..motor.texto import dinero, js_round

PARAMETRO_VERSION = 'dcasa_envios.version_lugares'
CONTEXTO_IMPORTANDO = 'dcasa_envios_importando'
# El valor de esa clave es este objeto, no un «True»: un contexto que llega por RPC es JSON y nunca lo puede traer
# (así nadie escribe por RPC los campos del sistema, como quién agregó un lugar).
IMPORTANDO = object()
TIPOS = [('corregimiento', 'Corregimiento'), ('barrio', 'Barrio o urbanización'), ('edificio', 'Edificio o PH'),
         ('referencia', 'Lugar conocido')]
TIPOS_A_MANO = ('barrio', 'edificio', 'referencia')
ESTADOS = [('ok', 'Con carretera'), ('revisar', 'Revisar la distancia'), ('lancha', 'Con lancha'),
           ('sin_carretera', 'Sin carretera'), ('no_encontrado', 'No encontrado'),
           ('fuera', 'Más lejos de lo que se cotiza'), ('sin_dato', 'Sin dato')]
CAT_DE_TIPO = {'barrio': 'barrio o urbanización', 'edificio': 'edificio o PH', 'referencia': 'lugar conocido',
               'corregimiento': 'corregimiento'}
FUENTE_A_MANO = 'a mano (Google Maps)'
# Lo que una persona del equipo (no Gerencia) puede escribir al agregar un lugar.
CAMPOS_DEL_EQUIPO = ('name', 'alias', 'tipo', 'dist', 'corr', 'km', 'peaje')
CAMPOS_DE_GERENCIA = CAMPOS_DEL_EQUIPO + ('cat', 'prov', 'corr_exacto', 'estado', 'nota', 'fuente_km', 'lat', 'lon',
                                          'km_medido', 'active')
# Los pone el sistema: nadie los escribe a mano (ni Gerencia).
CAMPOS_DEL_SISTEMA = ('origen', 'llave', 'secuencia', 'agregado', 'agregado_por', 'agregado_el', 'editado_por',
                      'editado_el')
MAX_TEXTO = 120
MAX_LIMITE = 200
MAX_KM = 2000

_INDICES = {}                   # base de datos → (versión, Indice, ids)
_CANDADO = threading.Lock()


def es_gerencia(env):
    return env.su or env.user._dcasa_es_gerencia()


class EnvioLugar(models.Model):
    _name = 'dcasa.envio.lugar'
    _description = 'Lugar de envío'
    _order = 'name, id'

    name = fields.Char('Lugar', required=True, index='trigram')
    alias = fields.Text('Otros nombres', help='Como lo dicen los clientes: uno por renglón.')
    tipo = fields.Selection(TIPOS, string='Qué es', required=True, default='barrio', index=True)
    cat = fields.Char('Tipo de lugar', help='Para los lugares conocidos: hospital, centro comercial, iglesia…')
    corr = fields.Char('Corregimiento')
    corr_exacto = fields.Boolean('Corregimiento exacto',
                                 help='Apagado: el corregimiento es el más cercano (el mapa no tenía su límite).')
    dist = fields.Char('Distrito', required=True, index=True)
    prov = fields.Char('Provincia', index=True)
    km = fields.Float('Km desde la tienda', help='Por carretera, en carro desde D\'CASA (La Chorrera).')
    km_medido = fields.Boolean('Km medido', default=True,
                               help='Apagado: no se pudo medir la distancia (se cotiza aparte).')
    peaje = fields.Boolean('Pasa por peaje')
    estado = fields.Selection(ESTADOS, required=True, default='ok', index=True)
    fuente_km = fields.Char('Medido con')
    lat = fields.Float('Latitud')
    lon = fields.Float('Longitud')
    nota = fields.Char('Nota')
    active = fields.Boolean('Activo', default=True)
    origen = fields.Selection([('archivo', 'Del archivo'), ('mano', 'Agregado en Odoo')], required=True,
                              default='mano', readonly=True, index=True)
    agregado = fields.Boolean('Agregado a mano', readonly=True,
                              help='Lo agregó una persona (en Odoo o en el archivo de Gerencia), no salió del mapa.')
    agregado_por = fields.Many2one('res.users', 'Lo agregó', readonly=True)
    agregado_el = fields.Datetime('Agregado el', readonly=True)
    editado_por = fields.Many2one('res.users', 'Lo cambió en Odoo', readonly=True)
    editado_el = fields.Datetime('Cambiado en Odoo el', readonly=True,
                                 help='Un lugar del archivo que Gerencia cambió en Odoo: al volver a cargar el '
                                      'archivo se respeta lo de Odoo.')
    llave = fields.Char(readonly=True, copy=False, index=True)
    secuencia = fields.Integer(readonly=True, default=0, help='Orden en el archivo (desempata la búsqueda).')
    precio_envio = fields.Float('Precio del envío', compute='_compute_precio', digits=(10, 2),
                                help='Con la tarifa vigente; 0 si se cotiza aparte.')
    precio_envio_txt = fields.Char('Precio', compute='_compute_precio')
    tarifa_base = fields.Float('Tarifa base', compute='_compute_precio', digits=(10, 2))
    cargos_txt = fields.Char('Cargos aparte', compute='_compute_precio')
    cotizar_aparte = fields.Boolean('Se cotiza aparte', compute='_compute_precio')

    _km_positivo = models.Constraint('CHECK(km >= 0)', 'Los kilómetros no pueden ser negativos.')

    # --- Precio (lista, ficha y exportar a Excel) ---------------------------------------------------------------------
    @api.depends('km', 'km_medido', 'estado', 'peaje')
    def _compute_precio(self):
        tarifa = self.env['dcasa.envio.tarifa']._vigente_motor()
        for lugar in self:
            cotizacion = motor_tarjeta.cotizar_lugar(tarifa, lugar._como_motor()) if tarifa else None
            if cotizacion:
                lugar.precio_envio = cotizacion['total']
                lugar.tarifa_base = cotizacion['base']
                lugar.precio_envio_txt = dinero(cotizacion['total'])
                lugar.cargos_txt = ', '.join(f"{c['nombre']} {dinero(c['v'])}"
                                             for c in cotizacion['extras'])
                lugar.cotizar_aparte = False
            else:
                lugar.precio_envio = lugar.tarifa_base = 0.0
                lugar.precio_envio_txt = 'Cotizar aparte' if tarifa else 'Sin tarifa'
                lugar.cargos_txt = ''
                lugar.cotizar_aparte = True

    def _como_motor(self):
        """El lugar con la forma del HTML (la que entiende el motor)."""
        self.ensure_one()
        return lugar_para_el_motor({
            'name': self.name, 'tipo': self.tipo, 'cat': self.cat, 'corr': self.corr, 'corr_exacto': self.corr_exacto,
            'dist': self.dist, 'prov': self.prov, 'km': self.km, 'km_medido': self.km_medido, 'peaje': self.peaje,
            'estado': self.estado, 'fuente_km': self.fuente_km, 'alias': self.alias, 'lat': self.lat,
            'lon': self.lon, 'nota': self.nota, 'agregado': self.agregado,
        })

    # --- Quién puede qué ----------------------------------------------------------------------------------------------
    @api.model
    def _exigir_lectura(self):
        """Cotizar es para quien puede ver los lugares (todo el equipo) o para el sistema (``sudo``): un usuario del
        portal o de la web no llega aquí por RPC."""
        if not self.env.su:
            self.browse().check_access('read')

    @api.model
    def _exigir_gerencia(self):
        if not es_gerencia(self.env):
            raise AccessError(self.env._('Solo Gerencia y los administradores cambian los lugares y la tarifa de '
                                         'envíos.'))

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """A quien no es Gerencia la lista y la ficha no le ofrecen «Nuevo», editar ni borrar (agrega desde la
        calculadora). Después de la caché de vistas, que es la misma para todos."""
        resultado = super().get_view(view_id, view_type, **options)
        if view_type in ('list', 'form', 'kanban') and not es_gerencia(self.env):
            nodo = etree.fromstring(resultado['arch'])
            for atributo in ('create', 'edit', 'delete'):
                nodo.set(atributo, '0')
            resultado = dict(resultado, arch=etree.tostring(nodo, encoding='unicode'))
        return resultado

    # --- Alta, cambio y baja ---------------------------------------------------------------------------------------
    def _importando(self):
        return self.env.context.get(CONTEXTO_IMPORTANDO) is IMPORTANDO and es_gerencia(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        importando = self._importando()
        if not importando:
            gerencia = es_gerencia(self.env)
            vals_list = [self._valores_a_mano(vals, gerencia) for vals in vals_list]
        registros = super().create(vals_list)
        if not importando:
            self._subir_version()
        return registros

    def _valores_a_mano(self, vals, gerencia):
        """Un lugar agregado en Odoo: solo los datos que la persona puede escribir, más lo que pone el sistema."""
        permitidos = CAMPOS_DE_GERENCIA if gerencia else CAMPOS_DEL_EQUIPO
        ajenos = sorted(set(vals) - set(permitidos))
        if ajenos:
            raise UserError(self.env._('Al agregar un lugar no se puede escribir: %s.', ', '.join(ajenos)))
        nombre = ' '.join(str(vals.get('name') or '').split())[:MAX_TEXTO]
        dist = ' '.join(str(vals.get('dist') or '').split())
        tipo = vals.get('tipo') or 'barrio'
        if not nombre:
            raise ValidationError(self.env._('Escribe el nombre del lugar.'))
        if not dist:
            raise ValidationError(self.env._('Elige el distrito del lugar.'))
        if tipo not in dict(TIPOS) or (tipo not in TIPOS_A_MANO and not gerencia):
            raise ValidationError(self.env._('Un lugar nuevo es un barrio o urbanización, un edificio o PH, o un '
                                             'lugar conocido. Los corregimientos los agrega Gerencia.'))
        km_medido = vals.get('km_medido', True)
        try:
            km = float(vals.get('km'))
        except (TypeError, ValueError):
            km = None
        if km_medido and (km is None or not 0 <= km <= MAX_KM):
            raise ValidationError(self.env._('Escribe los kilómetros por carretera desde la tienda (mídelos en Google '
                                             'Maps, «Cómo llegar» en carro desde D\'CASA).'))
        if self._ya_esta(nombre, dist, tipo):
            raise ValidationError(self.env._('«%(nombre)s» ya está en la lista (%(dist)s): búscalo en la calculadora.',
                                             nombre=nombre, dist=dist))
        alias = '\n'.join(a.strip() for a in str(vals.get('alias') or '').splitlines() if a.strip())
        corr = ' '.join(str(vals.get('corr') or '').split())
        salida = dict(vals, name=nombre, dist=dist, tipo=tipo, corr=corr, alias=alias,
                      km=js_round(km * 10) / 10 if km is not None else 0.0, km_medido=bool(km_medido))
        salida.setdefault('corr_exacto', True)
        salida['cat'] = salida.get('cat') or CAT_DE_TIPO[tipo]
        salida['prov'] = salida.get('prov') or self._provincia_de(dist)
        salida['estado'] = salida.get('estado') or 'ok'
        salida['fuente_km'] = salida.get('fuente_km') or FUENTE_A_MANO
        salida.update(origen='mano', agregado=True, agregado_por=self.env.uid, agregado_el=fields.Datetime.now(),
                      llave=False, secuencia=0)
        return salida

    @api.model
    def _ya_esta(self, nombre, dist, tipo):
        indice, _ids = self._indice()
        buscado = buscador.sin_tildes(nombre)
        return any(lugar['dist'] == dist and lugar['tipo'] == tipo and buscador.sin_tildes(lugar['nombre']) == buscado
                   for lugar in indice.lugares)

    @api.model
    def _provincia_de(self, dist):
        self.env.cr.execute("""
            SELECT prov FROM dcasa_envio_lugar
             WHERE dist = %s AND prov IS NOT NULL AND prov != '' AND active
          ORDER BY (tipo = 'corregimiento') DESC, id LIMIT 1""", [dist])
        fila = self.env.cr.fetchone()
        return fila[0] if fila else ''

    def write(self, vals):
        if not self._importando():
            protegidos = sorted(set(vals) & set(CAMPOS_DEL_SISTEMA))
            if protegidos:
                raise UserError(self.env._('Esto lo pone el sistema y no se cambia a mano: %s.', ', '.join(protegidos)))
            del_archivo = self.filtered(lambda lugar: lugar.origen == 'archivo')
            if vals and del_archivo:
                # Gerencia corrigió un lugar del archivo: al volver a cargarlo, manda lo de Odoo.
                super(EnvioLugar, del_archivo).write({'editado_por': self.env.uid,
                                                      'editado_el': fields.Datetime.now()})
        resultado = super().write(vals)
        if not self._importando():
            self._subir_version()
        return resultado

    def unlink(self):
        resultado = super().unlink()
        self._subir_version()
        return resultado

    def action_volver_al_archivo(self):
        """Quita la marca «cambiado en Odoo»: la próxima carga del archivo vuelve a mandar en este lugar."""
        self._exigir_gerencia()
        self.check_access('write')
        super(EnvioLugar, self.filtered(lambda lugar: lugar.origen == 'archivo')).write(
            {'editado_por': False, 'editado_el': False})
        return True

    # --- El índice en memoria --------------------------------------------------------------------------------------
    @api.model
    def _subir_version(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAMETRO_VERSION, uuid.uuid4().hex)

    @api.model
    def _version(self):
        self.env['ir.config_parameter'].flush_model()      # la versión recién subida puede no estar escrita todavía
        self.env.cr.execute('SELECT value FROM ir_config_parameter WHERE key = %s', [PARAMETRO_VERSION])
        fila = self.env.cr.fetchone()
        return fila[0] if fila else ''

    @api.model
    def _indice(self):
        """``(Indice, ids)`` de los lugares activos, armado una vez por versión (en la memoria de este proceso)."""
        self.env.flush_all()           # que se vea lo recién escrito (también la versión)
        version = self._version()
        clave = self.env.cr.dbname
        guardado = _INDICES.get(clave)
        if guardado and guardado[0] == version:
            return guardado[1], guardado[2]
        with _CANDADO:
            guardado = _INDICES.get(clave)
            if guardado and guardado[0] == version:
                return guardado[1], guardado[2]
            self.env.cr.execute("""
                SELECT id, name, tipo, cat, corr, corr_exacto, dist, prov, km, km_medido, peaje, estado, fuente_km,
                       alias, lat, lon, nota, agregado
                  FROM dcasa_envio_lugar
                 WHERE active
              ORDER BY CASE WHEN origen = 'archivo' THEN 0 ELSE 1 END, secuencia, id""")
            ids, lugares = [], []
            for fila in self.env.cr.dictfetchall():
                ids.append(fila['id'])
                lugares.append(lugar_para_el_motor(fila))
            indice = buscador.Indice(lugares)
            _INDICES[clave] = (version, indice, ids)
            return indice, ids

    # --- La API para cotizar (pantalla, Brian y, mañana, la web) ---------------------------------------------------
    @api.model
    def buscar_para_cotizar(self, texto, tipo=None, distrito=None, limite=20):
        """Busca un lugar como lo escribe el cliente y devuelve cada uno con su precio.

        Datos puros, iguales para cualquier usuario: ``{'texto', 'total', 'resultados': [tarjeta + id, dist, prov,
        corr, cat], 'sugerencias': [{'id', 'nombre'}] (solo si no encontró nada), 'tarifa': {aprobada, configurada,
        aviso}}``. ``tipo``: corregimiento, barrio, edificio o referencia. ``distrito``: un distrito o una provincia.
        ``limite``: de 1 a 200.

        Lo puede llamar quien ve los lugares (el equipo) o el sistema con ``sudo()`` (así lo llamará la web)."""
        self._exigir_lectura()
        texto = texto[:MAX_TEXTO] if isinstance(texto, str) else ''
        tipo = tipo if tipo in buscador.TIPOS else None
        distrito = distrito[:80] if isinstance(distrito, str) and distrito.strip() else None
        try:
            limite = max(1, min(int(limite), MAX_LIMITE))
        except (TypeError, ValueError):
            limite = 20
        indice, ids = self._indice()
        Tarifa_ = self.env['dcasa.envio.tarifa']
        tarifa = Tarifa_._vigente_motor() or Tarifa({})
        posiciones = indice.buscar(texto, tipo, distrito)
        resultados = []
        for posicion in posiciones[:limite]:
            lugar = indice.lugares[posicion]
            datos = motor_tarjeta.tarjeta(lugar, tarifa)
            datos.update(id=ids[posicion], dist=lugar['dist'], prov=lugar['prov'], corr=lugar['corr'],
                         cat=lugar['cat'], agregado=bool(lugar.get('agregado')))
            resultados.append(datos)
        sugerencias = [] if posiciones else [{'id': ids[p], 'nombre': indice.lugares[p]['nombre']}
                                             for p in indice.sugerir(texto)]
        return {'texto': texto, 'total': len(posiciones), 'resultados': resultados, 'sugerencias': sugerencias,
                'tarifa': Tarifa_._estado_publico()}

    @api.model
    def datos_de_la_calculadora(self):
        """Lo que la pantalla necesita al abrir: si hay datos, los distritos y provincias para el filtro, los
        corregimientos de cada distrito (para agregar un lugar), la tarifa (regla y tramos) y si quien mira es Gerencia.
        Solo lectura, para quien ve los lugares."""
        self._exigir_lectura()
        indice, _ids = self._indice()
        distritos, provincias, corregimientos = set(), set(), {}
        for lugar in indice.lugares:
            if lugar['dist']:
                distritos.add(lugar['dist'])
            if lugar['prov']:
                provincias.add(lugar['prov'])
            if lugar['tipo'] == 'corregimiento' and lugar['corr']:
                corregimientos.setdefault(lugar['dist'], set()).add(lugar['corr'])

        def orden(lista):
            return sorted(lista, key=lambda x: (buscador.sin_tildes(x), x))
        Tarifa_ = self.env['dcasa.envio.tarifa']
        return {
            'total_lugares': len(indice),
            'distritos': orden(distritos),
            'provincias': orden(provincias),
            'corregimientos': {d: orden(c) for d, c in corregimientos.items()},
            'tarifa': Tarifa_._para_la_pantalla(),
            'es_gerencia': es_gerencia(self.env),
            'tienda': motor_tarjeta.TIENDA,
            'atribucion': motor_tarjeta.ATRIBUCION,
        }


def lugar_para_el_motor(fila):
    """Una fila de la base (o los valores de un registro) con la forma del HTML que entiende el motor."""
    lat, lon = fila.get('lat') or 0.0, fila.get('lon') or 0.0
    con_coordenadas = bool(lat or lon)          # (0, 0) es el golfo de Guinea: en Panamá nunca es un lugar real
    alias = [a for a in (fila.get('alias') or '').splitlines() if a.strip()]
    return {
        'nombre': fila.get('name') or '',
        'tipo': fila.get('tipo'),
        'cat': fila.get('cat') or '',
        'corr': fila.get('corr') or '',
        'corr_exacto': bool(fila.get('corr_exacto')),
        'dist': fila.get('dist') or '',
        'prov': fila.get('prov') or '',
        'km': float(fila.get('km') or 0.0) if fila.get('km_medido') else None,
        'peaje': bool(fila.get('peaje')),
        'estado': fila.get('estado'),
        'fuente_km': fila.get('fuente_km') or '',
        'alias': alias,
        'lat': float(lat) if con_coordenadas else None,
        'lon': float(lon) if con_coordenadas else None,
        'nota': fila.get('nota') or '',
        'agregado': bool(fila.get('agregado')),
    }
