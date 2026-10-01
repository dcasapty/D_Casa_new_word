#!/usr/bin/env node
// Genera la configuración con la que se despliega: la misma edge/wrangler.jsonc, pero
// con la imagen del contenedor apuntando a la imagen YA PROBADA en CI y subida al
// registro de Cloudflare (I-08), en vez de reconstruir desde docker/Dockerfile.
//
// Uso:
//   node preparar_config.mjs <wrangler.jsonc> <salida.json> <entorno> <ref_digest> <ref_tag>
//     entorno     production (raíz del archivo) o el nombre de un env (p. ej. staging)
//     ref_digest  registry.cloudflare.com/<cuenta>/dcasa-odoo@sha256:<64 hex>
//     ref_tag     registry.cloudflare.com/<cuenta>/dcasa-odoo:<sha del commit>
//
// Política de scheduling (https://developers.cloudflare.com/containers/configuration/scheduling-policy/):
//   - "default": campo `image` = Dockerfile → se cambia por ref_tag (referencia de registro
//     documentada para esta política) y se quitan image_build_context/image_vars.
//   - "durable_object": `images.<nombre>.dockerfile` → `images.<nombre>.image` = ref_digest
//     (esta política exige referencia fijada por digest).
// Si no encuentra ninguna imagen construida desde Dockerfile en el entorno pedido, falla:
// nunca se despliega reconstruyendo.
//
// También falla si alguna variable (`vars`) efectiva del entorno tiene un marcador
// (CAMBIAR, PENDIENTE, <...>) (I-11). Escribe en GITHUB_OUTPUT `worker=<nombre del Worker>`.
import { readFileSync, writeFileSync, appendFileSync } from "node:fs";

const [entrada, salida, entorno, refDigest, refTag] = process.argv.slice(2);
if (!entrada || !salida || !entorno || !refDigest || !refTag) {
  console.error("uso: preparar_config.mjs <wrangler.jsonc> <salida.json> <entorno> <ref_digest> <ref_tag>");
  process.exit(2);
}

/** Quita comentarios // y /* *\/ y comas finales de un JSONC, respetando las cadenas. */
export function jsoncAJson(texto) {
  let out = "";
  let i = 0;
  let enCadena = false;
  while (i < texto.length) {
    const c = texto[i];
    const sig = texto[i + 1];
    if (enCadena) {
      out += c;
      if (c === "\\") {
        out += sig ?? "";
        i += 2;
        continue;
      }
      if (c === '"') enCadena = false;
      i += 1;
      continue;
    }
    if (c === '"') {
      enCadena = true;
      out += c;
      i += 1;
    } else if (c === "/" && sig === "/") {
      while (i < texto.length && texto[i] !== "\n") i += 1;
    } else if (c === "/" && sig === "*") {
      i += 2;
      while (i < texto.length && !(texto[i] === "*" && texto[i + 1] === "/")) i += 1;
      i += 2;
    } else {
      out += c;
      i += 1;
    }
  }
  // Comas finales: «, }» o «, ]» fuera de cadenas (tras quitar comentarios).
  let limpio = "";
  enCadena = false;
  for (let j = 0; j < out.length; j += 1) {
    const c = out[j];
    if (enCadena) {
      limpio += c;
      if (c === "\\") {
        limpio += out[j + 1] ?? "";
        j += 1;
      } else if (c === '"') {
        enCadena = false;
      }
      continue;
    }
    if (c === '"') {
      enCadena = true;
      limpio += c;
      continue;
    }
    if (c === ",") {
      let k = j + 1;
      while (k < out.length && /\s/.test(out[k])) k += 1;
      if (out[k] === "}" || out[k] === "]") continue;
    }
    limpio += c;
  }
  return JSON.parse(limpio);
}

const MARCADOR = /CAMBIAR|PENDIENTE|REEMPLAZAR|CHANGEME|PLACEHOLDER|<[^>]*>/i;
if (!/^registry\.cloudflare\.com\/[0-9a-f]{32}\/[a-z0-9._-]+@sha256:[0-9a-f]{64}$/.test(refDigest)) {
  console.error(`::error::Referencia por digest inválida: ${refDigest}`);
  process.exit(1);
}
if (!/^registry\.cloudflare\.com\/[0-9a-f]{32}\/[a-z0-9._-]+:[A-Za-z0-9._-]+$/.test(refTag)) {
  console.error(`::error::Referencia por etiqueta inválida: ${refTag}`);
  process.exit(1);
}

const config = jsoncAJson(readFileSync(entrada, "utf8"));
const raiz = entorno === "production";
const seccion = raiz ? config : config.env?.[entorno];
if (!seccion) {
  console.error(`::error::${entrada} no define env.${entorno}: no hay a dónde desplegar «${entorno}».`);
  process.exit(1);
}

/** Cambia, en una lista de contenedores, toda imagen construida desde Dockerfile. */
function fijarImagenes(contenedores) {
  let cambios = 0;
  for (const c of contenedores ?? []) {
    if (c.scheduling_policy === "durable_object") {
      for (const [nombre, img] of Object.entries(c.images ?? {})) {
        if (img.dockerfile) {
          c.images[nombre] = { image: refDigest };
          cambios += 1;
        }
      }
    } else if (typeof c.image === "string" && /Dockerfile/i.test(c.image)) {
      c.image = refTag;
      delete c.image_build_context;
      delete c.image_vars;
      cambios += 1;
    }
  }
  return cambios;
}

// `containers` no se hereda entre entornos de wrangler: si el env lo define, es el suyo;
// si no, cuenta la raíz. Se exige al menos un cambio en lo que de verdad se despliega.
// Las demás secciones también se fijan, para que nada en este archivo pida un build.
let cambios = fijarImagenes(seccion.containers);
if (!raiz && !seccion.containers) cambios += fijarImagenes(config.containers);
fijarImagenes(config.containers);
for (const otro of Object.values(config.env ?? {})) fijarImagenes(otro.containers);
if (cambios === 0) {
  console.error(
    "::error::No encontré ninguna imagen de contenedor construida desde Dockerfile en " +
      `el entorno «${entorno}». Revisa edge/wrangler.jsonc (containers.image / images.*.dockerfile).`,
  );
  process.exit(1);
}

const vars = seccion.vars ?? {};
const malas = Object.entries(vars).filter(([, v]) => typeof v === "string" && MARCADOR.test(v));
if (malas.length) {
  for (const [k, v] of malas) console.error(`::error::vars.${k} = «${v}» es un marcador (I-11).`);
  process.exit(1);
}

writeFileSync(salida, JSON.stringify(config, null, 2));
const worker = raiz ? config.name : (seccion.name ?? `${config.name}-${entorno}`);
console.log(`Configuración lista: ${cambios} imagen(es) fijadas; Worker «${worker}».`);
if (process.env.GITHUB_OUTPUT) appendFileSync(process.env.GITHUB_OUTPUT, `worker=${worker}\n`);
