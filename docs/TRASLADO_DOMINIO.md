# Traslado del sitio de `*.workers.dev` a `dcasapty.com`

Lista completa y en orden de lo que cambia cuando producción pase de `https://dcasa.dcasapty.workers.dev` a
`https://dcasapty.com`. Sale de buscar en el código (`workers.dev`, `CANONICAL_HOST`, `web.base.url`, `URL_SITIO`,
`dcasapty.com`) el 2026-10-18. La idea: dejar todo listo antes y que el traslado sea **un despliegue**.

> Quién: **D** = la dueña (Cloudflare, GitHub, Resend, Meta, Google: cuentas suyas). **C** = Claude (repositorio y
> despliegue, con su «sí»). Ningún secreto pasa por el chat.

## Cómo funciona hoy (lo que manda)

- El borde toma `CANONICAL_HOST` del **anfitrión de `URL_SITIO`** (variable del environment `production` de GitHub, hoy
  `https://dcasa.dcasapty.workers.dev`): lo dice el paso «wrangler deploy» de cada despliegue («▶ CANONICAL_HOST vacío:
  se usa el de URL_SITIO»). El `"CANONICAL_HOST": "dcasapty.com"` de `edge/wrangler.jsonc` hoy no manda.
- El contenedor fija y congela `web.base.url = https://CANONICAL_HOST` en cada arranque (`docker/entrypoint.sh`).
  **Cambiarlo a mano en Odoo no sirve**: el siguiente arranque lo vuelve a poner.
- De `web.base.url` salen: enlaces y logo de los correos (`dcasa_correo`), el dominio impreso en factura y PDF y el QR
  `/dcasa/doc/…` (`dcasa_invoice`), el QR del código público (`dcasa_base`), el webhook de Telegram de Brian
  (`dcasa_brian`), los orígenes permitidos del MCP de Brian, los enlaces de Conversaciones y Juan
  (`dcasa_conversaciones`), el aviso de la caché de páginas (`TIENDA_AVISO_URL` por defecto) y el `canonical` de cada
  página.
- El sitemap y `robots.txt` los arma Odoo con el anfitrión de quien los pide: en el dominio salen con el dominio solos.
- El borde ya manda `www.dcasapty.com` → `dcasapty.com` (301) cuando `CANONICAL_HOST` es `dcasapty.com`.

## Antes del día (se puede hacer ya, no cambia nada visible)

| # | Quién | Qué | Cómo se comprueba | Cómo se vuelve atrás |
|---|---|---|---|---|
| 1 | D | Agregar `dcasapty.com` a Cloudflare (Add a site, plan Free) y cambiar los *nameservers* en el registrador. **Antes**, copiar los registros DNS que ya existen (correo `info@`, MX, TXT) | En Cloudflare el dominio dice **Active**; el correo de `info@` sigue llegando | Volver a los nameservers anteriores en el registrador |
| 2 | D | Resend › Domains › Add `dcasapty.com` y copiar sus registros DNS en Cloudflare (nube gris) — [CORREO.md §5](CORREO.md) | Resend dice **Verified** | Borrar esos registros (no afecta al sitio) |
| 3 | D | Zero Trust › Access › la aplicación «Master (producción)» › **agregar** el destino `dcasapty.com` + Path `master` (sin quitar el de workers.dev). El AUD **no cambia**: GitHub no se toca | `https://dcasapty.com/master` pide el PIN (el sitio aún no responde ahí: es normal) | Quitar ese destino |
| 4 | D | Turnstile (si está en uso) › el widget › Hostnames: agregar `dcasapty.com` y `www.dcasapty.com` | El widget los lista | Quitarlos |
| 5 | C | Confirmar con `/__edge/health` que `"puerta"` dice `lista` y que `/master` abre en workers.dev ([PUERTA_MASTER.md](PUERTA_MASTER.md)) | El equipo entra por `/master` | — |
| 6 | C | Juan: `juan/wrangler.jsonc` ya tiene `URL_SITIO = https://dcasapty.com` en producción. **Hallazgo:** hoy eso hace que los enlaces relativos que completa Juan apunten a un dominio que todavía no es el sitio. Revisar con la dueña si pasarlo a workers.dev hasta el día, o dejarlo así | Una respuesta de Juan con enlace a un producto abre bien | Volver el valor y «Desplegar Juan» |

## El día del traslado (en este orden; ~15 minutos y un despliegue)

| # | Quién | Qué | Cómo se comprueba | Cómo se vuelve atrás |
|---|---|---|---|---|
| 7 | C | `edge/wrangler.jsonc`: descomentar `routes` (`dcasapty.com` y `www.dcasapty.com`, `custom_domain: true`). El token de despliegue necesita *Zone › Workers Routes › Edit* (D lo agrega al token si falta) | Cloudflare › Workers › `dcasa` › Domains & Routes lista los dos | Volver a comentarlas y desplegar (el sitio sigue en workers.dev) |
| 8 | D | GitHub › Settings › Environments › **production** › Variables › `URL_SITIO` = `https://dcasapty.com` (sin barra final). `CANONICAL_HOST` de GitHub, vacío | En el siguiente despliegue: «▶ CANONICAL_HOST vacío: se usa el de URL_SITIO (dcasapty.com)» | Volver `URL_SITIO` a `https://dcasa.dcasapty.workers.dev` y desplegar |
| 9 | C | Desplegar (Actions › Desplegar, misma imagen que ya está en producción: `app_version` y `imagen_digest` del último despliegue sano). El contenedor arranca con `web.base.url = https://dcasapty.com` | `https://dcasapty.com/__edge/health` sano; en Odoo › Parámetros del sistema, `web.base.url` = `https://dcasapty.com`; `www.` redirige | Paso 8 al revés y desplegar de nuevo |
| 10 | C | Brian: Brian › Telegram › **Registrar webhook** (Telegram pasa a `https://dcasapty.com/brian/telegram/…`) | Un mensaje a Brian por Telegram contesta | Volver a registrar con la dirección vieja |
| 11 | D+C | Probar: portada, una ficha, carrito y checkout, `/mi-cuenta`, `/socios`, `/master` (PIN → clave → código), un PDF de factura (dominio impreso y QR), un correo de prueba (Odoo › Ventas › Configuración › Correo a clientes: enlaces y logo con `dcasapty.com`) | Todo abre con `dcasapty.com` | Pasos 8–9 al revés |

## Después del día

| # | Quién | Qué | Cómo se comprueba |
|---|---|---|---|
| 12 | D | Correo a clientes: remitente `ventas@dcasapty.com` y encender «Enviar correos a clientes» (solo con Resend **Verified**) | Llega un correo de prueba sin ir a spam |
| 13 | D | Google Search Console: propiedad de dominio `dcasapty.com` (verifica con un TXT en Cloudflare) y enviar `https://dcasapty.com/sitemap.xml` | Search Console lee el sitemap sin errores |
| 14 | D | Meta: Business Settings › Brand safety › **Domains** › verificar `dcasapty.com`; el catálogo (cuando se una la rama de Meta) usa la dirección que muestra Odoo, que ya saldrá con el dominio ([META_CATALOGO.md](META_CATALOGO.md) en esa rama); el píxel, en el mismo dominio | Meta marca el dominio como verificado; «Subir ahora» del catálogo lee el feed |
| 15 | D | Lo impreso (QR de socios, tarjetas): siempre `https://dcasapty.com/…`, nunca workers.dev | — |
| 16 | C | `workers.dev` sigue respondiendo con el mismo sitio (contenido duplicado para Google; el `canonical` ya apunta al dominio). Propuesta, con su «sí»: que el borde redirija workers.dev al dominio, salvo `/__edge/*` | Abrir workers.dev lleva a dcasapty.com |
| 17 | C | Staging, si se quiere: `staging.dcasapty.com` (descomentar su `routes`, `URL_SITIO` de staging, su aplicación de Access) y `TIENDA_AVISO_URL` de staging | — |

## Lo que NO cambia

- Juan y el puente de WhatsApp viven en sus propios workers.dev (webhooks de Meta y Telegram de Juan): no se tocan.
  Los medios del puente ya aceptan `dcasapty.com` y `dcasapty.workers.dev` (`MEDIOS_HOSTS_PERMITIDOS`).
- Los secretos de la puerta (`DCASA_PUERTA_*`, `DCASA_ACCESS_*`): el AUD sigue igual si se agrega el destino a la misma
  aplicación (paso 3).
- La base, los respaldos y R2.
