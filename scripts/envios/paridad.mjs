// Paridad del motor de envíos (addons/dcasa_envios/motor) con el HTML de la propuesta (envios-dcasa.html).
//
// Saca del HTML el JavaScript de la tarifa y del buscador, lo corre en node sobre los datos y escribe los resultados
// esperados: los primeros 10 lugares de cada búsqueda (con su tarjeta), las sugerencias, una tabla de km → precio con
// varias tarifas y los tramos. scripts/envios/comparar.py los compara con el motor de Python.
//
// Uso:
//   node scripts/envios/paridad.mjs <envios-dcasa.html> <consultas.json> <salida.json> [datos.json]
//
// <consultas.json>: {"busquedas": [{"texto", "tipo"?, "distrito"?}], "km": [números], "variantes": [{"nombre",
// "cambios": {...ajustes...}}]}. [datos.json] (opcional): {"lugares", "ajustes", "agregados"} en vez de los del HTML
// (así se generan los esperados del fixture sintético de las pruebas, sin datos reales).
//
// El HTML NO está en el repositorio (el repo es público): la dueña lo tiene; ver docs/ENVIOS.md.
import { readFileSync, writeFileSync } from 'node:fs';

const [html, consultasRuta, salidaRuta, datosRuta] = process.argv.slice(2);
if (!html || !consultasRuta || !salidaRuta) {
  console.error('Uso: node paridad.mjs <envios-dcasa.html> <consultas.json> <salida.json> [datos.json]');
  process.exit(2);
}
const fuente = readFileSync(html, 'utf8');
const bloque = (id) => {
  const m = fuente.match(new RegExp(`<script id="${id}" type="application/json">([\\s\\S]*?)</script>`));
  if (!m) throw new Error(`No está el bloque ${id}`);
  return JSON.parse(m[1]);
};
const cortar = (desde, hasta) => {
  const i = fuente.indexOf(desde), j = fuente.indexOf(hasta, i);
  if (i < 0 || j < 0) throw new Error(`No encontré ${desde} … ${hasta}`);
  return fuente.slice(i, j);
};
const funcion = (nombre) => {
  const m = fuente.match(new RegExp(`\\n  function ${nombre}\\([^)]*\\) \\{[\\s\\S]*?\\n  \\}\\n`));
  if (!m) throw new Error(`No encontré la función ${nombre}`);
  return m[0];
};
const constante = (nombre) => {
  const m = fuente.match(new RegExp(`\\n  const ${nombre} = [^\\n]*\\n`));
  if (!m) throw new Error(`No encontré la constante ${nombre}`);
  return m[0];
};

const datos = datosRuta ? JSON.parse(readFileSync(datosRuta, 'utf8')) : null;
const LUGARES = datos ? datos.lugares : bloque('lugares');
const ORIGINAL = datos ? datos.ajustes : bloque('ajustes');
const AGREGADOS_ORIGINAL = datos ? (datos.agregados || []) : bloque('agregados-datos');

const codigo = `'use strict';
  const TIENDA = '8.8765881,-79.7867962';
  const copia = (o) => JSON.parse(JSON.stringify(o));
  let A = copia(ORIGINAL);
  let AGREGADOS = copia(AGREGADOS_ORIGINAL);
  const hayBorrador = false;
  const salidaDom = {};
  const $ = (id) => (salidaDom[id] ||= { innerHTML: '', textContent: '', value: '' });
  ${cortar('// --- Tarifa ---', '// --- Pintar ---')}
  ${cortar('const esc = ', '  const $ = ')}
  ${constante('ETIQUETA_TIPO')}
  ${funcion('mapaRuta')}
  ${funcion('desgloseHTML')}
  ${funcion('textoCliente')}
  ${funcion('tarjeta')}
  ${funcion('pintarRegla')}
  ${funcion('tramos')}
  ${funcion('pintarTramos')}
  ${funcion('pintarEfecto')}
  return {
    poner: (a) => { A = a; }, original: () => copia(ORIGINAL),
    filtros: (t, d) => { tipoFiltro = t || ''; distFiltro = d || ''; },
    indexar, buscar, sugerir, cotizar, base, conPrecio, tarjeta, textoCliente, tramos, dinero, kmTxt, tokens,
    pintarRegla, pintarTramos, pintarEfecto, salidaDom,
    constantes: { ABREV, VACIAS: [...VACIAS].sort(), CAT_SIN, DIST_SIN, PROV_SIN, GENERICAS: [...GENERICAS].sort(),
                  PRIORIDAD },
    indice: () => INDICE,
  };`;
// eslint-disable-next-line no-new-func
const H = new Function('LUGARES', 'ORIGINAL', 'AGREGADOS_ORIGINAL', codigo)(LUGARES, ORIGINAL, AGREGADOS_ORIGINAL);
H.indexar();
const INDICE = H.indice();
const posicion = new Map(INDICE.map((e, i) => [e.l, i]));

// La tarjeta del HTML, de vuelta a datos (para compararla con motor/tarjeta.py).
const desescapar = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
  .replace(/&amp;/g, '&');
const sinEtiquetas = (s) => desescapar(s.replace(/<[^>]+>/g, ''));
function tarjetaComoDatos(l) {
  const h = H.tarjeta(l, '');
  const chips = [...h.matchAll(/<span class="chip chip-(\w+)">([\s\S]*?)<\/span>/g)].map((m) => [m[1], desescapar(m[2])]);
  const donde = h.match(/<div class="donde">([\s\S]*?)<\/div>/)[1];
  const tambien = [...h.matchAll(/<div class="tambien">([\s\S]*?)<\/div>/g)].map((m) => desescapar(m[1]));
  const total = sinEtiquetas(h.match(/<div class="total"[^>]*>([\s\S]*?)<\/div>/)[1]);
  const km = h.match(/<div class="km">([\s\S]*?)<\/div>/);
  const desglose = [...h.matchAll(/<div class="desglose">([\s\S]*?)<\/div>/g)].map((m) =>
    [...m[1].matchAll(/<span>([\s\S]*?)<\/span>/g)].map((x) => sinEtiquetas(x[1])));
  const copiar = h.match(/data-copiar="([^"]*)"/);
  return { chips, zona: desescapar(donde), tambien, total, km: km ? desescapar(km[1]) : null,
           desglose: desglose[0] || [], url: desescapar(h.match(/<a href="([^"]*)"/)[1]),
           copiar: copiar ? desescapar(copiar[1]) : null };
}

const consultas = JSON.parse(readFileSync(consultasRuta, 'utf8'));
const salida = { lugares: INDICE.length, constantes: H.constantes, busquedas: [], precios: [], tramos: [], textos: [] };

for (const c of consultas.busquedas) {
  H.filtros(c.tipo, c.distrito);
  let lista, error = null;
  try { lista = H.buscar(c.texto); } catch (e) { lista = []; error = String(e); }
  const top = lista.slice(0, 10);
  salida.busquedas.push({
    ...c, error, total: lista.length, top: top.map((l) => posicion.get(l)),
    tarjetas: top.map(tarjetaComoDatos),
    sugerencias: lista.length ? [] : H.sugerir(c.texto).map((l) => posicion.get(l)),
  });
}
H.filtros('', '');

const base = H.original();
for (const v of consultas.variantes) {
  const a = { ...JSON.parse(JSON.stringify(base)), ...JSON.parse(JSON.stringify(v.cambios || {})) };
  H.poner(a);
  for (const km of consultas.km) {
    for (const peaje of [false, true]) {
      const c = H.cotizar(km, peaje);
      salida.precios.push({ variante: v.nombre, km, peaje, base: c.base, extras: c.extras, total: c.total,
                            dinero: H.dinero(c.total), km_txt: H.kmTxt(km) });
    }
  }
  H.pintarRegla();
  H.pintarTramos();
  H.pintarEfecto();
  const todos = H.tramos().out;   // sin redondeo son miles (uno por décima de km): ahí basta la tabla que se muestra
  salida.tramos.push({ variante: v.nombre, tramos: todos.length <= 100 ? todos : null,
                       mostrar: sinEtiquetas(H.salidaDom.tramos.innerHTML.replace(/<\/div>/g, '|')),
                       nota: H.salidaDom['tramos-nota'].textContent });
  salida.textos.push({ variante: v.nombre,
                       regla: sinEtiquetas(H.salidaDom.regla.innerHTML.replace(/<\/span>/g, '|')),
                       efecto: sinEtiquetas(H.salidaDom.efecto.innerHTML.replace(/<\/span>/g, '|')),
                       formula: H.salidaDom.formula.textContent });
}
// Un renglón por búsqueda, precio o tramo: cabe en una revisión y los cambios se leen en el diff.
const lista = (xs) => '[\n' + xs.map((x) => JSON.stringify(x)).join(',\n') + '\n]';
writeFileSync(salidaRuta, '{\n' + Object.entries(salida).map(([k, v]) =>
  JSON.stringify(k) + ': ' + (Array.isArray(v) ? lista(v) : JSON.stringify(v))).join(',\n') + '\n}\n');
console.log(`OK: ${salida.busquedas.length} búsquedas, ${salida.precios.length} precios, ${INDICE.length} lugares`);
