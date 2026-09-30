# Informe final de la auditoría D'CASA

Auditoría multi-agente (9 agentes en paralelo, coordinados por la bitácora
`BITACORA.md`) sobre el código en `main` tras el merge del PR #1 (commit `48b5429`).
Informes completos por área en esta misma carpeta; aquí va la síntesis.

## Alcance y límites

- Auditoría **estática** del código propio (`addons/`, `edge/`, `docker/`, `.github/`,
  `scripts/`), contrastada con el fuente de Odoo 19 (`vendor/odoo`, inicializado durante
  la sesión). No se vio la app en pantalla ni se midió en un navegador real.
- Se corrieron de verdad: `scripts/test.sh` sobre los 8 módulos (**264 tests, 0 fallos,
  0 errores**), `ruff` (sin errores), `py_compile`, validación de XML y manifiestos,
  los 20 tests y `tsc` del Worker (`npm audit`: 0 vulnerabilidades) y la compilación de
  los bundles SCSS de Odoo.
- **No se ejecutaron**: los 4 tests de navegador (panel de Brian, barra lateral, filtros
  rápidos; falta Chrome/`websocket-client`), una actualización `-u` sobre una base con
  datos ni las migraciones `post-migrate`.
- Precios y límites de Cloudflare y Neon salen de memoria de un agente: **por verificar**
  con el MCP de Cloudflare y la consola de Neon.
- Hallazgos marcados «por verificar con PoC» no deben tratarse como confirmados.

## Veredicto

El código está en **muy buen estado técnico** (convenciones Odoo 19 aplicadas de forma
consistente, tests sólidos, sin secretos en el repo, sin XSS, SQL parametrizado,
Brian ejecuta como el usuario real y audita antes de actuar). Lo que frena el
lanzamiento no es la calidad del código sino cuatro cosas concretas:

1. **Una duda de precio de 7 %** (ITBMS) en los 199 productos.
2. **Una familia de fallos de seguridad con una misma causa**: métodos públicos de
   modelos Odoo que se pueden llamar por RPC sin control de permisos.
3. **Faltantes legales** del sitio (privacidad, políticas) y la factura electrónica DGI.
4. **Decisiones de infraestructura**: el presupuesto previsto no cubre Odoo en Containers.

Recuento aproximado de hallazgos (sin contar «lo bien hecho»): 1 crítico probable,
~13 altos, ~60 medios, ~70 bajos, repartidos entre los nueve informes.

## Verificado por mí (no solo reportado por agentes)

| Tema | Verificación |
|---|---|
| **ITBMS** | `up media/DCASA_listado_productos.xlsx`, hoja «Notas»: «Todos los precios son +ITBMS». El combo Queen `1062010734/5/6N` = $329,99 = base imponible de INV/2026/00821 (329,99 + 23,10 = 353,09). `catalogo.py:50-65` los carga como «ITBMS incluido» y `docs/CATALOGO.md:20` lo afirma; `docs/PLAN.md` lo deja como pregunta abierta. Confirmado por `enterprise-gap`, `sitio-web` y `contabilidad`. |
| **RPC de Brian (B-01)** | `procesar_update` (`models/telegram.py:304`) es público en `brian.telegram.enlace` (modelo normal, con lectura para `base.group_user`). `vendor/odoo/odoo/service/model.py` solo bloquea nombres con `_` y `@api.private`. Es invocable por RPC; **el impacto (actuar como un admin vinculado) está sin probar con PoC**. |
| **Tests** | 264 tests pasan (ver arriba; los corrió `calidad-codigo`). |

## Causa raíz común de la seguridad

Odoo expone por RPC **todo método público** de cualquier modelo (`call_kw`). Varios
métodos de D'CASA están pensados como «botón de la vista» o «punto de entrada interno»
pero son públicos, y muchos usan `sudo()` sin comprobar grupo. Mismo patrón, distintos
módulos:

| Id | Dónde | Efecto |
|---|---|---|
| S-01 | `dcasa_socios/models/res_partner.py:349-373` | Cualquier usuario interno reinicia el PIN de un socio (recibe el temporal) y lo desbloquea. |
| S-02 | `dcasa_socios/models/dcasa_canje.py:159,173` | Entregar/cancelar canjes ajenos con `sudo`; con registro libre (`b2c`) activo, alcanza a un visitante con usuario portal. |
| B-01 | `dcasa_brian/models/telegram.py:304` | Posible suplantación de un admin vinculado (PoC pendiente). |
| B-02 | `dcasa_brian/models/proveedores.py:366-386` | `configuracion()` devuelve la clave de API de IA a cualquier usuario interno. |
| B-03 | `dcasa_brian/models/accion.py:62-91` | Se puede escribir/crear el registro de auditoría «inmutable». |
| B-04 | `dcasa_brian/models/registro.py:166,224` | `ejecutar(confirmado=True)` y `confirmar()` saltan la confirmación humana. |
| S-09 | `brian.herramientas`, `brian.proveedores` | Modelos abstractos sin ACL; `probar()` gasta la clave de IA. |
| C-07 | `dcasa_contabilidad` | Reportes y API de conciliación por RPC sin control de grupo. |

**Arreglo sistémico recomendado**: barrer `addons/` buscando métodos públicos con
`sudo()`; renombrarlos con `_`, marcarlos `@api.private` o verificar grupo al entrar, y
añadir una prueba que falle si reaparece el patrón. Hoy `api.private` no aparece en
ninguna parte de `addons/`.

## Plan de arreglo por prioridad

### P0 — antes de publicar

1. **Aclarar el ITBMS con la dueña** usando la factura 00821 (ver «Decisiones»). Si los
   precios son +ITBMS: impuesto «se suma al precio», `list_price` = cifra del Excel, y la
   web muestra el precio con impuesto. Ajustar tests (hoy usan el atajo del impuesto
   «se suma»).
2. **Cerrar la superficie RPC** (tabla de arriba), con pruebas por RPC como usuario
   interno sin privilegios. Incluye renombrar `procesar_update` y verificar B-01 con PoC.
3. **S-03, pimienta del PIN** (`ci.yml:229`): si `wrangler secret list` falla, el flujo
   sobrescribe `DCASA_PIN_PEPPER` e invalida todos los PIN sin vuelta atrás. Abortar si el
   comando falla y respaldar la pimienta fuera de Cloudflare.
4. **S-04** (`entrypoint.sh:57-66`: si el contenedor muere entre instalar y cambiar la
   clave, queda `admin/admin`) y **S-07** (bloquear `/jsonrpc` con `service=db` en el
   borde y normalizar rutas).
5. **Roles** (UI-02, UI-03, UI-08): no hay grupos Vendedora/Gerencia definidos. La
   vendedora ve reportes antifraude, «Registrar cobro» sin permiso y descuentos sin tope.
   Definir los roles antes de Brian por perfiles (depende de esto).
6. **Legal del sitio** (SW-01..03): política de privacidad y cookies, Google Fonts/Maps
   propios o tras consentimiento, páginas de entregas/garantía/términos, razón social y
   RUC en el pie, retirar «financiamiento» y «tarjeta» hasta que existan. Revisar con un
   asesor (Ley 81 de 2019: por verificar).
7. **Barra lateral** (N-01..N-05): quitar el modo «auto» por hover, barra fija en ≥1200 px,
   anillo de foco con contraste, «saltar al contenido» y gestión de foco. Código listo en
   `navbar.md` §5. Un solo cambio del token `--dc-foco` (1,5:1) arregla además UI-04.

### P1 — primeras semanas

- Factura electrónica DGI (obligación legal; elegir PAC en paralelo) y CUFE/QR.
- Listas vacías (UI-01): el parche de `sin_odoo.js:38-40` oculta los `help` propios.
- Costos e inventario (`dcasa_inventario`): sin costo el margen sale 100 % y el costo de
  ventas 0; plantilla de conteo inicial (hoy todo «Sin confirmar» y habrá stock negativo).
- Brian: confirmaciones con resumen real (monto), caducidad de acciones pendientes,
  control de costo/tiempo, endurecer vinculación de Telegram, `confirmar_accion` para
  herramientas de construcción por MCP, purga de conversaciones.
- Contabilidad: fechas de bloqueo de periodo, reversa de puntos al cancelar/desconciliar
  un pago (C-10), nota de crédito parcial (C-12), libro mayor truncado (C-06), validación
  de RUC/DV.
- CI: instalar `websocket-client` y fallar si hay tests saltados (Q-01); migraciones en un
  job previo al deploy (I-02); reutilizar la imagen probada (I-08); respaldo diario a R2 y
  ensayo de restauración (I-03).
- Limitar intentos en `/web/login`, `/socios/*` y `/brian/mcp` (S-06); verificar celular
  en `/socios/registro` (S-05).

### P2 — después

- Brian «constructor total» por fases (perfiles 0-5 por rol y área, diario de cambios con
  deshacer, CRUD genérico con lista blanca, personalización tipo Studio en Community,
  cambios de código solo vía pull request, pruebas en rama de base de datos,
  evaluaciones continuas). Detalle y 80+ escenarios de prueba en `brian.md`.
- Brecha Enterprise en el orden de `enterprise-gap.md`: costos/valoración → compras y
  reorden → antigüedad de saldos y cobranza → factura electrónica → nómina → activos.
- Rendimiento y SEO del sitio (fuentes propias, caché de HTML, `og:image`, refracción del
  navbar solo en escritorio), `read_group` → `_read_group` (Q-02), cabeceras de seguridad
  en respuestas cacheadas del borde (Q-03).

## Infraestructura y costo (a decidir)

Con la información del agente `infra` (por verificar con el MCP de Cloudflare):

| Escenario | Total mensual aprox. |
|---|---|
| Container `standard-2` 24/7 (estado actual) | ~$70 |
| `standard-1` 24/7 | ~$53 |
| `standard-1` ~12 h/día | ~$30 |
| VPS con PostgreSQL local + túnel de Cloudflare | ~$6–12 |

El plan de $5 cubre el Worker; el contenedor se factura aparte. El cron de 10 min mantiene
el contenedor encendido (contradice `docs/ARQUITECTURA.md`). El plan gratuito de Neon no
sirve (Odoo consulta cada ~60 s y nunca permite el autosuspend). Medir la latencia
contenedor↔Neon **antes** de migrar.

## Decisiones que necesitan a la dueña/dirección

1. ¿Los precios del Excel son +ITBMS? (factura 00821 como prueba).
2. ¿Existe financiamiento o pago con tarjeta hoy? Si no, se retira del sitio.
3. Presupuesto de infraestructura: Cloudflare Containers + Neon (~$30–70) vs VPS + túnel.
4. Política de datos hacia el proveedor de IA (datos personales de clientes viajan a Brian).
5. Canje en mostrador para clientes sin PIN; tope de descuento por rol; cliente genérico
   («Consumidor final») y puntos.
6. Precios por tamaño incoherentes (`ZEM-KING`, `81904`, `XHT022-F-W`) y categorías mal
   asignadas (las «Cama con estantes» caen en «Estantes y organización»).
7. Niveles de ayuda de Brian por rol (punto de partida en `brian.md` §6).

## Lo que está bien hecho (conservar)

Convenciones Odoo 19 consistentes y tests de calidad (264 verdes); marca disciplinada y
contrastes medidos en el sitio; facturación y monto en letras correctos; libro de puntos
inmutable con centavos enteros; reportes contables con chequeo de cuadre; conciliación
prudente y reversible; Brian sin `sudo`, con auditoría previa y política de herramientas;
Markdown sin HTML y Telegram en texto plano; webhook con doble secreto y comparación en
tiempo constante; imagen Docker multi-etapa sin root; CI con permisos mínimos; lógica del
Worker pura y testeada; documentación honesta sobre alternativas.

## Discrepancias entre agentes y correcciones

- La bitácora decía que `vendor/odoo` estaba vacío; no lo está (se inicializó en la
  sesión). Los agentes que lo notaron verificaron contra el código de Odoo.
- `brian` describió `brian.telegram.enlace` como modelo abstracto; es un modelo normal.
  No cambia el hallazgo.
- `contabilidad` refutó dos sospechas propias tras verificarlas en Odoo
  (`price_include_override='default'` y el uso de `force_delete` en conciliación).

## Pendiente con herramientas que aún no hay

- Navegador real: Lighthouse móvil, prueba a 320 px, contraste del menú de vidrio, los 4
  tests de navegador, la barra lateral en uso.
- MCP de Cloudflare: precios, cuotas y sintaxis vigentes de Containers, R2 y Neon.
- Base con datos: prueba de actualización `-u` y de las migraciones.
- PoC de B-01, B-03 y S-01/S-02 por RPC.

## Índice de informes

`navbar.md` · `ui-backend.md` · `sitio-web.md` · `brian.md` · `seguridad.md` ·
`contabilidad.md` · `infra.md` · `enterprise-gap.md` · `calidad-codigo.md` · `BITACORA.md`

---

# Ronda 2 — Presupuesto sin Neon y Brian como núcleo

Cinco agentes con investigación en internet (informes en `ronda2/`): `cf-costos`,
`brian-modelos`, `brian-excel`, `brian-eventos`, `brian-evals`.

**Límite de método importante:** el proxy de este entorno bloqueó `developers.cloudflare.com`,
los sitios oficiales de OpenAI, Meta, Google y Hetzner, entre otros. Los precios de Anthropic
sí se leyeron en fuente oficial; **todo lo demás viene de resultados de buscador, blogs o
del repo público de documentación de Cloudflare, y está marcado «NO VERIFICADO»**. Antes de
contratar nada hay que reabrir las páginas de precios (MCP de Cloudflare o un entorno sin
bloqueo).

## 1. ¿Puede Cloudflare alojar todo? ¿Resuelve Zero Trust lo de Neon?

- **Zero Trust / Tunnel / Access no alojan PostgreSQL.** Controlan acceso y conectividad.
  Tunnel es gratis y Access es gratis hasta 50 usuarios: sirven para exponer un servidor sin
  IP pública y poner login previo al panel. Ojo: una política de Access a ciegas bloquearía
  a clientes, `/socios` y `/brian/*`; esas rutas necesitan política *bypass*.
- **Cloudflare no tiene Postgres propio.** D1 y Durable Objects (SQLite) no sirven para
  Odoo; Hyperdrive es solo pooling hacia un Postgres externo y rompe `LISTEN/NOTIFY`.
- **Postgres dentro de un Container no es apto para datos contables:** disco efímero;
  los snapshots son beta (máx. 20 GB, atados a la versión de la imagen).

| Opción (mensual, aprox.) | Costo | Veredicto |
|---|---|---|
| Todo en Containers | $34–63 | Descartada (disco efímero, costo) |
| **VPS con Odoo+PostgreSQL + Tunnel + Access + Worker + R2** | **$12–17** | **Recomendada** |
| Container + Postgres en VPS | $44–56 | Descartada |
| Container `standard-1` horario laboral + Neon | $30–40 | Plan B |

Recomendación: VPS tipo Hetzner CX33 (~€8,49 + 20 % por copias) con PostgreSQL local, WAL
a R2 (pgBackRest/WAL-G) para restauración a un punto en el tiempo y prueba mensual de
restauración en CI. Si la latencia Panamá↔Europa es alta: mismo diseño en DigitalOcean o
Vultr en EE. UU. ($20–29). Costo del contenedor de Odoo verificado con cuenta paso a paso:
`standard-2` 24/7 = $45,52; `standard-1` 24/7 = $29,24; `standard-1` 12 h × 22 días = $10,26
(más $5 del plan). Neon queda descartado por tu decisión y por datos: Odoo consulta cada
~60 s y nunca permite el autosuspend (~$20/mes solo de Neon).
**Medir antes de comprometerse:** latencia, RAM real de Odoo, tamaño de la base, tiempo de
restauración de extremo a extremo, y la política de Access sobre tienda/socios/Brian.
Fuentes discrepan en precios de Hetzner (€5,49 vs €5,99) y Contabo: verificar.

## 2. Brian como núcleo: hallazgos de la ronda

**Lo más importante: Brian hoy no lee Excel.** `.xlsx`/`.docx` responden «No puedo leer este
tipo de archivo» (`conversacion.py:88-91,487-491`); `.xls` se decodifica como UTF-8; PDF sin
OCR; imágenes >5 MB se rechazan en vez de redimensionarse (`:83`); texto cortado a 20.000
caracteres en silencio (`:82`); no hay carga por lote (219 filas = 219 llamadas a
`crear_producto` y el bucle corta a 8 pasos). Justo lo que más necesita el negocio.

**Tu Excel real, medido:** 4 hojas visibles, **0** imágenes incrustadas, **0** fórmulas, 0
celdas combinadas; 323 PNG externos (993 MB; cada uno es una página completa de Canva; 54
superan 5 MB y 11 superan 10 MB en base64); 219 filas / 199 códigos; 5 códigos con precios
contradictorios más 1 con precio en blanco en una de sus filas (verificado por mí); 11 sin
foto; 8 fotos listadas que no están en disco. **La dificultad es semántica** (precios en
texto, duplicados, cruzar código con nombre de archivo), no de formato. El encabezado
«+ITBMS» aparece en 3 celdas: cuarta confirmación del problema de precios; por eso la
importación debe exigir un parámetro `modo_itbms` y nunca suponerlo. La lectura de
imágenes «en celda» solo se probó con un archivo sintético: hace falta un Excel de muestra
real que las tenga.

**Diseño objetivo de ingesta (`brian-excel.md`):** extracción determinista primero (valores,
fórmulas, anclas de imágenes, combinadas, ocultas), esquema intermedio normalizado,
modelo solo donde hace falta, validación, vista previa, confirmación humana, aplicación
idempotente por lotes y reversión. Herramientas nuevas: `leer_archivo`,
`ver_imagen_de_celda`, `proponer_importacion_catalogo`, `comparar_con_excel` (lectura) y
`aplicar_importacion`/`deshacer_importacion` (sensibles, nunca por MCP).

**Costo de los modelos (precios de Anthropic, fuente oficial; USD/millón entrada/salida):**
Haiku 4.5 1/5 · Sonnet 5.5 2/10 · Opus 5.5 4/20 · Batch −50 % · caché de lectura 0,1× la entrada.
Estimación mensual de Brian (supuestos de `brian-modelos`, no mediciones):

| Uso | Hoy (Sonnet sin caché) | Caché | Ruteo Haiku→Sonnet + Batch |
|---|---|---|---|
| Bajo (400 msg/mes) | ~$23 | ~$13 | ~$8 |
| Medio (1.500) | ~$90 | ~$50 | ~$29 |
| Alto (5.000) | ~$308 | ~$173 | ~$100 |

**El caché hoy está roto por diseño:** hora y usuario van dentro del prompt de sistema
(`conversacion.py:365-366`) y las herramientas cambian por mensaje (`registro.py:141-159`);
además el uso de tokens se descarta (`:272-283`), así que hoy no se sabe cuánto gasta Brian.
El prefijo fijo es de ~8.700–11.300 tokens por llamada (45 herramientas). Con caché tibia un
turno baja de ~$0,06 a ~$0,014.

**Multi-modelo:** hay un solo proveedor global (Anthropic nativo + uno compatible con OpenAI
por `BRIAN_BASE_URL`); Meta, Gemini y Workers AI no existen en el código; no hay ruteo por
tarea ni fallback. **Muse Spark** está en vista previa (1.3 desde septiembre), su
disponibilidad en Panamá no está confirmada y su nivel barato entrena con tus prompts: no
usar con datos de clientes; dejar el adaptador apagado hasta verificarlo en `dev.meta.ai`.
Límites de visión de OpenAI y Meta: NO VERIFICADO.

**Arquitectura por eventos (`brian-eventos.md`):** hoy el bucle de Brian (hasta 8 pasos)
corre síncrono dentro de una petición de Odoo con la transacción abierta; el webhook de
Telegram responde solo tras el modelo y la deduplicación abre una carrera
(`models/telegram.py:325-327`). Recomendada: Worker (ack inmediato + dedupe) + Durable
Object por conversación (memoria, confirmaciones, streaming) + Workflow (tareas largas,
aprobaciones) + Queue/R2 (archivos); Odoo sigue como sistema de registro y ejecutor de
herramientas con la clave de cada persona, **sin token de servicio que actúe como
cualquiera (equivale a sudo)**. La capa cabe en los $5 del plan hasta ~2.700
interacciones/día (supuestos propios); el costo real son los tokens. El diseño no cambia
si Odoo va a un VPS con túnel. Antes: bloquear `/json/2` en el borde (`routing.ts:12`).

**Evaluación (`brian-evals.md`):** 26 casos dorados generados leyendo tu Excel (verdad de
terreno verificable con sha256), evaluador por celda/herramienta/alucinación/permisos/costo,
y comparación entre versiones que detecta regresiones. **La demo usa salidas simuladas:
no mide ningún modelo real.** Falta el ejecutor real que corra Brian dentro de Odoo, el juez
LLM y `pass^k`. Los umbrales propuestos (exactitud ≥ 0,95, alucinación ≤ 0,02, críticos = 0)
no están validados. El proveedor de pruebas `prueba` nunca ejercita la ruta de producción
con las 45 herramientas (`proveedores.py:79`).

## 3. Plan actualizado (se suma al de la ronda 1)

| Orden | Acción |
|---|---|
| 1 | Seguridad P0 de la ronda 1 (superficie RPC, pimienta, admin/admin, `/jsonrpc` y `/json/2`). Bloquea todo lo demás. |
| 2 | Decidir infraestructura: VPS + Tunnel + R2 (recomendada) tras **verificar precios y medir latencia**. |
| 3 | Brian, base: registrar uso de tokens (`brian.uso`), prefijo estable con caché, herramientas bajo demanda, tope de gasto por usuario. Barato y mide todo lo demás. |
| 4 | Brian lee Excel: `leer_archivo` + importación por lotes con vista previa, `modo_itbms` obligatorio, reversión; arrancar con el extractor del prototipo. |
| 5 | Evals reales: ejecutor en Odoo, Excel de muestra con imágenes en celda, CI con el proveedor determinista y nocturna con modelo real. |
| 6 | Roles y perfiles de ayuda por rol (prerrequisito: definir los grupos). |
| 7 | Capa por eventos (Worker + Durable Object + Workflow), por fases, con el bucle actual como respaldo. |
| 8 | Multi-modelo: abstracción y ruteo Haiku→Sonnet, fallback, Batch; OpenAI/Meta solo tras verificar términos y datos. |

## 4. Decisiones adicionales para la dueña/dirección

1. ¿Aceptas el VPS (~$12–17/mes) como infraestructura principal, con Cloudflare al frente?
2. Aprobación de abogado panameño para enviar datos de clientes a proveedores de IA
   (Ley 81 de 2019, transferencias internacionales: POR VERIFICAR).
3. ¿Hay un Excel real con imágenes dentro de las celdas? Hace falta una muestra para probar
   esa parte; el Excel actual no las tiene.
4. Tope mensual de gasto en IA por usuario/rol.

## 5. Pendiente de verificar (ronda 2)

Precios/cuotas oficiales de Cloudflare (Containers, Workflows, Durable Objects, AI Gateway),
Hetzner/Contabo/DigitalOcean, OpenAI y Meta; cold start de Odoo en Containers; retención de
datos de los proveedores de IA; calidad de Haiku 4.5 y de Workers AI con herramientas en
español (se mide con los evals); licencia de `/json/2` en Odoo Community autoalojado.
