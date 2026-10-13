# Ronda 6 · Auditoría final de la integración

Fecha: 02/10/2026 · Alcance: `git diff d1c0413..40bf560` (sin «up media»): caché del HTML de Odoo en
el borde (`edge/src/tienda/paginas.ts`, `dcasa_tienda_borde`), factura electrónica DGI (`dcasa_fe_pa`,
apagada), Brian (operación, consumo, adjuntos), seguridad (`dcasa_seguridad`, `edge/src/bots.ts`,
robots, Turnstile, 2FA), panel (`dcasa_interfaz`, `dcasa_base`, `dcasa_socios`) y contabilidad
fase 1. No se tocó `website_dcasa` (lo rediseña otro equipo) ni ningún recurso de Cloudflare.

## Cómo se revisó

- Lectura del diff completo, con foco en las **interacciones entre equipos**: caché del borde ×
  cookies × CSRF × Turnstile × 2FA × límites de intentos × aviso de regeneración.
- Odoo 19 con **todos** los módulos en una base limpia (`dcasa_t_audit`, puerto 8498) y datos
  sembrados (facturas de cliente y proveedor vencidas, movimientos de banco, una regla de
  conciliación y un cierre de mes). **Chromium real** (Playwright) como contadora (gerencia
  contable) y como administrador, con la consola JS vigilada:
  - Contabilidad: Resumen (con descarga de Excel), Estado de resultados / Balance / Flujo de
    efectivo en modo **comparativo**, Por cobrar y Por pagar (clic al detalle), Conciliación
    (regla ofrecida y aplicada con un clic, «Conciliar automático»), Importar extracto CSV (vista
    previa e importación desde la conciliación), Reglas de conciliación, Formatos de extracto,
    Cierre de mes (revisar y cerrar).
  - Panel: Inicio, Ventas de hoy, Cotizaciones, Clientes, «Consumo de IA», «Accesos al panel».
  - **Enrolamiento 2FA** con la obligatoriedad encendida: login de admin → pantalla con QR →
    código equivocado (mensaje en español) → código correcto (TOTP calculado) → panel.
  - Resultado: **ningún error de consola ni diálogo de error** en ninguna pantalla. Lo encontrado
    en el navegador fue de forma (ver C-7 y observaciones).
- Al final: `scripts/test.sh` equivalente con todos los módulos en una sola base (**609 tests, 0
  fallos, 0 errores**; la base se borró al terminar), `ruff check addons`, `shellcheck` de
  `docker/`, `scripts/` y `.github/scripts/`, y `cd edge && npm test && npm run typecheck`
  (**116 tests**, sin errores de tipos).

## Hallazgos corregidos

| # | Sev. | Hallazgo | Corrección | Test |
|---|---|---|---|---|
| C-1 | **Media** | **La caché del borde seguía sirviendo el HTML de la versión anterior después de un despliegue.** Un despliegue cambia plantillas, estilos y código sin pasar por ningún `write` del ORM que deje marca (el `-u` de `website_dcasa` corre antes de que `dcasa_tienda_borde` se cargue). El borde servía la página vieja como HIT hasta 1 h y una vez más como STALE; esa página pide bundles CSS/JS con el hash viejo, que Odoo redirige a los nuevos: diseño viejo con estilos nuevos justo cuando se publica el rediseño del sitio. | `dcasa.tienda.pendiente._dcasa_revisar_version()`: si `APP_VERSION` cambió respecto de la última avisada, marca «regenerar todo» (motivo `despliegue`) una vez por versión; el cron de aviso lo llama primero. `docker/entrypoint.sh` (sección 2d') adelanta ese cron al arrancar para que el aviso salga apenas Odoo abre. | `dcasa_tienda_borde/tests/test_cambios.py::test_despliegue_nuevo_regenera_todo` |
| C-2 | **Media** | **Un contador podía marcar un mes como cerrado/abierto por RPC sin tocar la fecha de bloqueo.** El ACL da escritura en `dcasa.cierre.mes` a `account.group_account_user` (para notas, motivo y revisar), y `estado`, `cerrado_por`, `cerrado_el` solo eran `readonly` en la vista: un `write` dejaba un mes «Cerrado» sin bloqueo (o «Abierto» con bloqueo), contradiciendo el historial que ve la gerencia. | `write()` rechaza esos tres campos salvo desde «Cerrar mes» / «Reabrir» (contexto interno, que ya exigen la gerencia contable) o sudo. | `dcasa_contabilidad/tests/test_fase1.py::test_contador_no_marca_cerrado_por_rpc` |
| C-3 | **Media** | **Importar un extracto con movimientos de un mes ya cerrado los re-fechaba en silencio.** Odoo respeta la fecha de bloqueo moviendo el asiento a otra fecha (en la prueba, a hoy), y el importador decía «1 movimientos importados» sin más: la contadora no se enteraba de que el banco y el mes cerrado ya no cuadran. | El aviso pasa a `warning` (fijo) y dice cuántos movimientos quedaron con otra fecha y que, si eran de ese mes, la gerencia tiene que reabrirlo con motivo. La fecha de bloqueo sigue mandando (no se esquiva). | `test_fase1.py::test_importar_en_mes_cerrado_avisa` |
| C-4 | Baja (seguridad) | **Inyección de fórmulas en el Excel de los reportes contables.** `libro_excel` usaba `worksheet.write()`, que convierte en fórmula todo texto que empieza con «=». Nombres de clientes (se registran solos en la tienda y en /socios) y conceptos del banco (importados) llegan a «Por cobrar», «Libro mayor», etc.: un `=HYPERLINK(…)` se ejecutaba al abrir el archivo. | Textos con `write_string` y números con `write_number` (también título, periodo y encabezados). | `test_fase1.py::test_excel_sin_formulas_inyectadas` (el XML de la hoja no tiene `<f>`) |
| C-5 | Baja | **La cookie `dcasa_personal` vencía antes que la sesión.** Se ponía una sola vez con vida de 7 días; la sesión de un usuario se rota cada 3 h y sigue viva. A los 7 días el borde le servía la página anónima guardada (sin carrito, sin su cabecera) hasta que pasara por una ruta no guardada. Sin fuga de datos (la página es la anónima), pero el carrito «desaparecía» en portada y tienda. | Mientras la sesión es propia, la cookie se renueva en cada respuesta; sigue borrándose al cerrar sesión. | `dcasa_tienda_borde/tests/test_borde.py::test_logueado_recibe_la_cookie_y_nunca_se_certifica` (ampliado) |
| C-6 | Baja | **`BRIAN_ESFUERZO` y `BRIAN_CACHE` no llegaban a Odoo.** `docs/BRIAN.md` las documenta como variables, pero no estaban en `VARIABLES_DEL_CONTENEDOR` ni en `Env`: puestas en wrangler, el contenedor nunca las veía (solo funcionaba el parámetro del sistema). | Agregadas a `VARIABLES_DEL_CONTENEDOR` y a `Env`. | `edge/test/fase1.test.ts` («pasa R2 y cifrado al contenedor…») |
| C-7 | Cosmético | «Faltan 1 pasos para poder cerrar» en el cierre de mes; `web =[` sin espacio en `tablero.py`. | «Pasos que faltan para poder cerrar: N»; formato. | — (texto) |

## Revisado y correcto (sin cambios)

**Caché del borde × seguridad**
- Solo se guarda lo que Odoo **certifica** (`X-Dcasa-Borde: anonimo`, pedido con el secreto, sin
  cookies, sin IP del visitante, sin rastreo); el borde borra `X-Dcasa-Borde` de toda petición del
  visitante (`forwardedHeaders`). Con `Authorization` o `dcasa_personal` no se sirve nada guardado.
  Rutas guardables: lista cerrada (`/`, `/shop`, categorías y fichas con `-<id>`, `/visitanos`,
  `/privacidad`, `/terminos`, `/black-weekend`); `/web/login`, `/socios`, `/my`, carrito, checkout,
  `/brian/*` y `/dcasa/*` nunca. No vi datos personales posibles en lo guardado.
- CSRF: el token de la página guardada es de una sesión que no existe; `borde_csrf.js` pide uno
  propio (`/dcasa/borde/csrf`, `no-store`) antes del primer envío. Turnstile: la clave pública
  viaja en `session_info` de la página guardada (es pública); el token de Turnstile lo genera el
  widget en el navegador, no queda en la caché. Login, enrolamiento 2FA y /socios no se guardan.
- Límites de intentos (`bots.ts`): solo métodos que escriben; `/__edge/tienda/regenerar` (aviso de
  Odoo), `/__edge/*`, `/brian/mcp`, el webhook de Telegram, los crons y el precalentado no pasan
  por el filtro. Googlebot, Bingbot, previsualizadores y librerías HTTP genéricas no se tocan.
- Staging: `X-Robots-Tag: noindex, nofollow` en **toda** respuesta (incluidas las guardadas, 503 y
  redirecciones). `robots.txt` deja rastrear a propósito: si lo prohibiera, el buscador no vería
  el `noindex`.

**Seguridad de acceso**
- Rutas públicas nuevas: `/web/login/dcasa-2fa` (exige `pre_uid`, CSRF, bloqueo por IP y 5
  códigos/hora como `/web/login/totp`) y `/dcasa/borde/csrf`. `sudo()` nuevos: todos detrás de un
  control de grupo o sobre tablas internas sin datos para quien llama. Métodos nuevos de
  `res.users` privados; `test_superficie_rpc` al día (pasa).
- 2FA obligatorio apagado por defecto (entrypoint y wrangler en `0` en ambos entornos); el rescate
  `DCASA_2FA_RESCATE` valida el login con una expresión estricta antes del SQL y es de un solo uso
  por versión. `TURNSTILE_SECRET` se quita del entorno antes de lanzar Odoo.
- Excel/PDF y pantallas contables exigen `account.group_account_readonly`; reglas, importación y
  conciliación exigen contador; cerrar/reabrir, gerencia contable. Vista previa del extracto con
  `Markup` escapado (probado con `<b>` en el concepto); CAMT con `resolve_entities=False`.

**Contabilidad**
- Partida doble: las contrapartidas de una regla nunca superan ni invierten lo pendiente; el
  resto queda en la cuenta transitoria. Antigüedad = saldo de la cuenta por cobrar (test). El
  cierre usa la fecha de bloqueo «suave» de Odoo; el bloqueo definitivo (`hard_lock_date`) no se
  toca y bloquea la reapertura: coherente con «REQUIERE CONTADOR» para el cierre de año.

**Reglas de CLAUDE.md**
- Convenciones Odoo 19 en el diff: `<list>`, `invisible=`, `models.Constraint`, `group_ids`,
  `self.env._` (en `dcasa_fe_pa` vía alias local `_ = self.env._`, válido). Socios: sin cifras
  nuevas fuera de `puntos.json`; el libro no cambió (solo índices). Marca: pantallas nuevas sin
  amarillo sobre blanco ni degradados; CTA de WhatsApp intacto.

**Despliegue**
- `ODOO_MODULES` incluye `dcasa_seguridad`; `dcasa_fe_pa` queda fuera (apagado). Los módulos de
  Odoo que necesita la seguridad (`auth_passkey`, `auth_timeout`, `website_cf_turnstile`) están
  protegidos de la limpieza de sobrantes. Producción: `TIENDA_ESTATICA=off`,
  `DCASA_2FA_OBLIGATORIO=0`. Staging arranca sin `TURNSTILE_*` (no están entre los obligatorios;
  `secretos_despliegue.sh` descarta los vacíos) y sin `TIENDA_FEED_TOKEN` la caché simplemente no
  existe.

## Observaciones (sin cambio en esta ronda)

1. **Límite de 10 intentos/min por IP en `/socios/entrar|registro|pin` y `/web/login`.** En la
   tienda, clientes y vendedoras comparten la IP del WiFi (y en Panamá muchas líneas móviles salen
   por CGNAT). Hoy el contador es en memoria por isolate (laxo); si se activan los bindings de Rate
   Limiting de `wrangler.jsonc` el límite se vuelve exacto por ubicación: conviene entonces una
   cubeta propia para `/socios/*` (p. ej. 30/min) y dejar 10 para `/web/login`. No se subió ahora
   porque también es la defensa principal contra adivinar PIN.
2. Staging precalienta las páginas con el host de `TIENDA_AVISO_URL` (workers.dev). Si
   `staging.dcasapty.com` pasa a apuntar al Worker, cambiar esa variable (la invalidación es global
   y sigue siendo correcta; solo se precalentaría el host equivocado).
3. Turnstile: quitar `TURNSTILE_*` del despliegue **no** lo apaga (los parámetros quedan en Odoo);
   para apagarlo hay que desplegar con `DCASA_TURNSTILE=off`. Está documentado; recordarlo.
4. Ajustes de Brian pide `/dcasa_brian/static/description/icon.png` (404; el módulo solo trae
   `icon.svg`). «Consumo de IA», agrupado por defecto, muestra el vacío genérico («Toca Nuevo…»)
   aunque la lista no permite crear. Cosméticos.
5. Las tarifas por millón de tokens de `brian.uso.PRECIOS` son cifras escritas en código (con
   fuente y fecha). La dueña debe confirmarlas contra la factura del proveedor; el texto ya aclara
   que es un estimado.
6. `tablero.py` usa `read_group` (deprecado en 19: solo aviso en el log).
