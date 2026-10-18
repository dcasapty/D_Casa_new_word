/**
 * Lo que ve quien abre la entrada del equipo (`/master`) cuando la puerta NO abre (docs/PUERTA_MASTER.md).
 *
 * Antes era un «Not Found» pelado: el 2026-10-13, con la puerta en «1», producción respondió eso después del PIN y nadie
 * pudo saber si faltaba un secreto, si Access protegía otra dirección o si el «AUD tag» era el de otra aplicación. Ahora
 * la página dice qué pasó y en qué pantalla se arregla, en palabras sencillas y sin mostrar ningún valor secreto:
 *
 * - nombres de variables, la dirección que se abrió y el equipo de Zero Trust (es la página de login de Access);
 * - de la audiencia, solo los últimos 6 caracteres y solo cuando la firma ya se comprobó (quien la ve pasó un PIN de
 *   nuestro equipo de Zero Trust);
 * - del emisor que trae un pase sin firma comprobada, solo si tiene forma de `https://<equipo>.cloudflareaccess.com`.
 *
 * La puerta sigue fallando CERRADO: estas páginas nunca dejan pasar a nadie. Sin dependencias de Cloudflare.
 */
import type { EstadoPuerta, ModoPuerta, MotivoRechazo, RechazoAccess } from "./puerta";

export interface ContextoAviso {
  /** Entrada configurada, p. ej. «/master». */
  ruta: string;
  modo: ModoPuerta;
  /** DCASA_ENTORNO: «staging» o «produccion». */
  entorno?: string;
  /** `https://<equipo>.cloudflareaccess.com` que espera el sitio (no es secreto: es la página del PIN). */
  equipo?: string;
  /** Para pruebas. */
  ahora?: () => number;
}

interface Explicacion {
  titulo: string;
  quePaso: string;
  revisar: string[];
  /** Botón (amarillo sobre azul): a dónde y con qué texto. */
  boton?: { href: string; texto: string };
}

const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (texto: string) => texto.replace(/[&<>"']/g, (letra) => ESCAPES[letra]);
const b = (texto: string) => `<b>${esc(texto)}</b>`;

/** El nombre del environment de GitHub donde viven los secretos de este entorno. */
export function entornoDeGithub(entorno?: string): string {
  return entorno === "staging" ? "staging" : "production";
}

function secretos(entorno?: string): string {
  return `GitHub › Settings › Environments › ${b(entornoDeGithub(entorno))} › Environment secrets`;
}

const PASOS_EQUIPO = (ctx: ContextoAviso) => [
  `En Cloudflare › ${b("Zero Trust")} › ${b("Settings")} mira el ${b("Team domain")} (algo como ` +
    `${b("tuequipo.cloudflareaccess.com")}).`,
  `En ${secretos(ctx.entorno)} › ${b("DCASA_ACCESS_EQUIPO")} tiene que estar ${b("https://")} + ese team domain, sin ` +
    `barra al final${ctx.equipo ? ` (hoy el sitio espera ${b(ctx.equipo)})` : ""}. Si cambias algo, vuelve a desplegar.`,
];

function explicar(rechazo: RechazoAccess, host: string, ctx: ContextoAviso): Explicacion {
  const direccion = `${host}${ctx.ruta}`;
  const reintentar = { href: ctx.ruta, texto: "Volver a intentar" };
  const motivo: MotivoRechazo = rechazo.motivo;
  switch (motivo) {
    case "sin token":
      return {
        titulo: "Cloudflare Access no protege esta dirección",
        quePaso:
          `Llegaste a ${b(direccion)} sin pasar por el PIN al correo. Sin ese paso la puerta no abre: la aplicación de ` +
          "Access del equipo está puesta en otra dirección, o no existe para este sitio.",
        revisar: [
          `En Cloudflare › ${b("Zero Trust")} › ${b("Access controls")} › ${b("Applications")}, abre la aplicación del ` +
            `equipo de este sitio («Master (${ctx.entorno === "staging" ? "staging" : "producción"})»).`,
          `En ${b("Public hostname")} tiene que estar exactamente ${b(host)} y en ${b("Path")} ${b(ctx.ruta.slice(1))}. ` +
            "Si dice otro dominio (por ejemplo dcasapty.com mientras el sitio vive en otra dirección), agrega este y guarda.",
          `Vuelve a abrir ${b(direccion)}: antes de esta página te tiene que pedir el correo y mandarte el PIN.`,
        ],
        boton: reintentar,
      };
    case "audiencia":
      return {
        titulo: "El PIN lo pidió otra aplicación de Access",
        quePaso:
          "Pasaste el PIN, pero el pase es de otra aplicación de Access (por ejemplo, la de staging). El sitio solo acepta " +
          "el pase de su propia aplicación.",
        revisar: [
          `En Cloudflare › ${b("Zero Trust")} › ${b("Access controls")} › ${b("Applications")}, abre la aplicación de ` +
            `${b(direccion)} y copia su ${b("Application Audience (AUD) Tag")}.`,
          `Pégalo en ${secretos(ctx.entorno)} › ${b("DCASA_ACCESS_AUD")} (reemplaza el que está) y vuelve a desplegar.`,
          (rechazo.audRecibida
            ? `Para comparar: el pase que trajiste termina en ${b("…" + rechazo.audRecibida)}; `
            : "Para comparar: ") +
            `el sitio espera uno que termina en ${b("…" + (rechazo.audEsperada ?? ""))}.`,
        ],
        boton: reintentar,
      };
    case "emisor":
    case "llave desconocida":
      return {
        titulo: "El pase viene de otro equipo de Zero Trust",
        quePaso:
          (rechazo.emisor && rechazo.emisor !== ctx.equipo
            ? `El pase dice venir de ${b(rechazo.emisor)}`
            : "La firma del pase no es de las llaves del equipo que espera el sitio") +
          (ctx.equipo ? `, y el sitio espera ${b(ctx.equipo)}.` : "."),
        revisar: PASOS_EQUIPO(ctx),
        boton: reintentar,
      };
    case "llaves no disponibles":
      return {
        titulo: "No pude comprobar el pase",
        quePaso:
          `No pude bajar las llaves de ${ctx.equipo ? b(ctx.equipo) : "tu equipo de Zero Trust"} para comprobar el pase: ` +
          "el nombre del equipo puede estar mal escrito, o Cloudflare no respondió.",
        revisar: [...PASOS_EQUIPO(ctx), "Si está bien escrito, espera un minuto y vuelve a intentar."],
        boton: reintentar,
      };
    case "vencido":
    case "todavía no vale":
    case "emitido en el futuro":
      return {
        titulo: "Tu pase ya no vale",
        quePaso: "El pase de Access venció (o la hora no cuadra). Hay que pedir un PIN nuevo.",
        revisar: ["Toca «Pedir un PIN nuevo»: Cloudflare cierra el pase viejo y te vuelve a pedir el correo."],
        boton: { href: "/cdn-cgi/access/logout", texto: "Pedir un PIN nuevo" },
      };
    case "sin correo":
      return {
        titulo: "Access no mandó tu correo",
        quePaso: "Pasaste Access, pero el pase no trae un correo que el sitio pueda usar.",
        revisar: [
          `En la aplicación de Access › ${b("Login methods")}, deja solo ${b("One-time PIN")}.`,
          "Usa un correo sin tildes ni ñ (las cabeceras de internet no los aceptan).",
        ],
        boton: reintentar,
      };
    default:
      return {
        titulo: "No pude comprobar el pase",
        quePaso: "El pase que llegó a la puerta no se pudo comprobar.",
        revisar: [
          `Si te pidió el PIN y aun así llegas aquí, revisa ${b("DCASA_ACCESS_EQUIPO")} y ${b("DCASA_ACCESS_AUD")} en ` +
            `${secretos(ctx.entorno)}.`,
          "Si no te pidió el PIN, la aplicación de Access no está en esta dirección: mira docs/PUERTA_MASTER.md.",
        ],
        boton: reintentar,
      };
  }
}

function mientrasTanto(modo: ModoPuerta, entorno?: string): string {
  if (modo === "1") {
    return (
      "Con la puerta obligatoria, nadie del equipo entra al panel hasta arreglarlo. Rescate: " +
      `${b("DCASA_PUERTA_OBLIGATORIA")} en ${b("0")} en edge/wrangler.jsonc` +
      (entornoDeGithub(entorno) === "staging" ? " (staging)" : "") +
      " y desplegar."
    );
  }
  return "Mientras tanto, el equipo entra al panel como hasta ahora (clave y código de la app).";
}

function pagina(titulo: string, cuerpo: string, pie: string): string {
  // Marca: navy de fondo y la tarjeta azul de «Acceso del equipo»; el amarillo solo sobre el azul; sin degradados.
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>D'CASA · Acceso del equipo</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#0b2160;color:#fff;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    min-height:100vh;padding:16px;line-height:1.5}
  main{max-width:560px;margin:6vh auto 4vh;background:#1340b1;border-radius:4px;padding:28px 24px}
  h1{font-family:Anton,Impact,"Arial Narrow",sans-serif;font-weight:400;text-transform:uppercase;letter-spacing:.03em;
    font-size:2rem;margin:0 0 4px}
  .sub{font-family:Oswald,"Arial Narrow",sans-serif;font-size:1.25rem;margin:0 0 20px}
  h2{font-family:Oswald,"Arial Narrow",sans-serif;font-weight:500;font-size:1.05rem;text-transform:uppercase;
    letter-spacing:.04em;margin:20px 0 6px}
  p,li{margin:0 0 8px;overflow-wrap:anywhere}
  ol,ul{padding-left:22px;margin:0}
  b{font-weight:700}
  .boton{display:inline-block;margin-top:20px;background:#fed00f;color:#0b2160;font-weight:700;text-decoration:none;
    padding:12px 18px;border-radius:4px}
  .pie{margin-top:24px;font-size:.85rem;opacity:.9}
  code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.85rem}
</style>
</head>
<body>
<main>
  <h1>Acceso del equipo</h1>
  <p class="sub">${esc(titulo)}</p>
${cuerpo}
  <p class="pie">${pie}</p>
</main>
</body>
</html>
`;
}

function cabeceras(): Headers {
  return new Headers({
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
  });
}

function fecha(ctx: ContextoAviso): string {
  return new Date((ctx.ahora ?? Date.now)()).toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

/** 403 con la explicación de por qué la entrada no abrió. */
export function respuestaPuertaNoAbre(request: Request, rechazo: RechazoAccess, ctx: ContextoAviso): Response {
  const host = new URL(request.url).host;
  const x = explicar(rechazo, host, ctx);
  const cuerpo = [
    "  <h2>Qué pasó</h2>",
    `  <p>${x.quePaso}</p>`,
    "  <h2>Qué revisar</h2>",
    `  <ol>${x.revisar.map((paso) => `<li>${paso}</li>`).join("")}</ol>`,
    `  <p style="margin-top:16px">${mientrasTanto(ctx.modo, ctx.entorno)}</p>`,
    x.boton ? `  <a class="boton" href="${esc(x.boton.href)}">${esc(x.boton.texto)}</a>` : "",
  ].join("\n");
  const pie =
    `Código: <code>${esc(rechazo.motivo)}</code> · ${esc(host + ctx.ruta)} · ${esc(fecha(ctx))}. ` +
    "Guía paso a paso: docs/PUERTA_MASTER.md.";
  return new Response(request.method === "HEAD" ? null : pagina(x.titulo, cuerpo, pie), { status: 403, headers: cabeceras() });
}

/** 503: la puerta está apagada porque le falta configuración. Dice QUÉ falta (nombres, nunca valores). */
export function respuestaPuertaIncompleta(request: Request, estado: EstadoPuerta, ctx: Omit<ContextoAviso, "ruta" | "modo">): Response {
  const host = new URL(request.url).host;
  const faltan = estado.faltan ?? [];
  const cuerpo = [
    "  <h2>Qué pasó</h2>",
    "  <p>A la puerta del equipo le falta configuración (o algo está mal escrito), así que quedó <b>apagada</b>: esta " +
      "dirección no pide el PIN ni protege nada.</p>",
    `  <ul>${faltan.map((problema) => `<li><code>${esc(problema)}</code></li>`).join("")}</ul>`,
    "  <h2>Qué revisar</h2>",
    `  <ol><li>En ${secretos(ctx.entorno)} revisa esos nombres (los valores nunca se muestran).</li>` +
      "<li>Las cuatro van juntas: DCASA_PUERTA_RUTA, DCASA_PUERTA_SECRETO, DCASA_ACCESS_EQUIPO y DCASA_ACCESS_AUD.</li>" +
      "<li>Vuelve a desplegar y abre esta dirección otra vez.</li></ol>",
    estado.aviso ? `  <p style="margin-top:16px"><b>Ojo:</b> ${esc(estado.aviso)}</p>` : "",
    `  <p style="margin-top:16px">${mientrasTanto("0", ctx.entorno)}</p>`,
  ].join("\n");
  const pie =
    `Código: <code>puerta_incompleta</code> · ${esc(host + estado.ruta)} · ${esc(fecha({ ...ctx, ruta: estado.ruta, modo: estado.modo }))}. ` +
    "Guía paso a paso: docs/PUERTA_MASTER.md.";
  return new Response(request.method === "HEAD" ? null : pagina("La puerta del equipo está apagada", cuerpo, pie), {
    status: 503,
    headers: cabeceras(),
  });
}
