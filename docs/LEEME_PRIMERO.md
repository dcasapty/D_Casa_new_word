# Léeme primero (para quien retome el trabajo)

Este archivo existe para que, cuando una sesión de trabajo se reinicie y el contexto se pierda, quien siga (una persona o
Claude) entienda **en cinco minutos** cómo se trabaja aquí, qué está hecho y qué sigue, sin empezar de cero ni preguntarle
a la dueña lo que ya se contestó. `CLAUDE.md` apunta aquí.

> **Regla de oro de este archivo:** al terminar cada sesión se agrega una entrada arriba de la
> [Bitácora](#bitácora-de-sesiones) (qué entró, qué quedó en staging, qué sigue) y se actualiza
> [PRIORIDADES.md](PRIORIDADES.md). Si no se anota, la próxima sesión no lo sabe.

## 1. Con quién se trabaja y cómo hablarle

- La dueña **no es técnica**. Se le habla en español sencillo y corto, de tú, sin jerga ni siglas sin explicar; se usa
  a cada persona se le trata como la persona misma diga; si no lo dijo, en neutro («la persona», «quien»), sin adivinar por el
  nombre. Primero el resultado, después el detalle.
- Lo que pide un **jefe** (el dueño de la empresa) llega a través de ella: se trata como pedido de la dueña, y se le
  responde a ella con lo que pueda reenviarle.
- **Nunca se pide un secreto por el chat** (claves, tokens, contraseñas). Se le dice *dónde* ponerlo (secreto de
  Cloudflare o de GitHub) y se confirma que quedó cargado sin ver su valor.
- **Los datos de personas** (nombres, correos, celulares, cédulas, facturas de clientes) viven solo en Odoo: ni en el
  repositorio, ni en documentos, ni en pruebas. Tampoco se guarda en GitHub un PDF de una entrega o factura real.
- Si una respuesta le va a servir a otra persona (el jefe, la contadora), se entrega como documento en Claude Docs, no
  solo en el chat.

## 2. Autorizaciones (lo que se puede y no se puede hacer solo)

| Acción | ¿Hace falta su «sí»? |
|---|---|
| Programar, probar, subir a la rama de trabajo, desplegar a **staging** | No (autorizado de forma permanente) |
| Crear el PR hacia `main` | Solo cuando lo pide o ya dijo «pásalo a producción» |
| Unir a `main` y desplegar a **producción** | **Sí, un «sí» explícito por cada cambio.** Un «sí» no se arrastra al siguiente cambio |
| Borrar datos, ramas, respaldos, secretos | Sí, y mirando primero qué se borra |
| Cifras de dinero, puntos, comisiones, impuestos | Nunca se inventan (ver `CLAUDE.md`: `puntos.json`, reglas de marca) |

## 3. Cómo se llega a producción (receta)

1. Cambio en la rama `claude/...` con su prueba. Corre `scripts/test.sh <módulos>` en local (PostgreSQL local; si se
   cayó: `pg_ctlcluster 16 main start` y esperar la recuperación), `ruff check addons` y, si tocó Worker, `npm test &&
   npm run typecheck` en la carpeta.
2. Subir la rama. Disparar **CI/CD** (`.github/workflows/ci.yml`) a mano con `desplegar_en = staging`: corre todas las
   pruebas y, si pasan, despliega a staging (unos 14 minutos en total si todo va bien).
3. Con staging **sano**, avisarle. Si dice «sí, pásalo a producción»: crear el PR (plantilla
   `.github/pull_request_template.md`, con su sección de Brian) y unir con *squash* y el título terminado en
   ` [skip ci]` (las pruebas ya pasaron en la rama; no se repiten en `main`).
4. Disparar `.github/workflows/desplegar.yml` en `main` con: `entorno = production`, `imagen_digest` (el `sha256:…` del
   resumen del despliegue de staging de esa misma imagen), `app_version` (el SHA de 40 caracteres del commit que se
   probó) y `respaldo_previo = true`. Tarda unos 3 minutos; el último paso espera a que el sitio responda sano.
5. Avisarle cuando esté sano y qué cambió para ella (sin tecnicismos). Los contenedores reiniciados toman las variables
   nuevas de Cloudflare.

## 4. Trampas ya conocidas (no volver a tropezar)

- **Nunca inventar un SHA** (ni "completar" uno corto): se lee del PR o del run. Ya falló un merge por eso.
- `rerun_failed_jobs` da 403 mientras el run sigue en curso: esperar a que termine. Una prueba que falló en CI no se
  "pausa": se espera o se cancela el run y se corrige.
- Los botones de la cabecera de una lista llaman al método con la lista de ids (vacía si no hay selección): un método
  `@api.model` fallaría. Hay un test guardián en `dcasa_base/tests/test_superficie_rpc.py`.
- PyPDF2 reescribe los textos de un PDF fusionado con escapes octales; las pruebas de PDF usan `textos()` que los
  decodifica (`dcasa_invoice/tests/test_paquete.py`).
- Las variables del Worker (`VARIABLES_DEL_CONTENEDOR`) llegan al contenedor al arrancar: un cambio en el panel de
  Cloudflare se aplica al reiniciar o en el siguiente despliegue. Los IDs (p. ej. `BRIAN_TELEGRAM_CHATS`) son variables
  normales, no secretos.
- Las pruebas de Odoo tardan ~27 minutos; un fallo cuesta un ciclo entero. Antes de subir, correr en local los módulos
  que se tocaron.
- No existe el `gh` CLI aquí: todo GitHub va por las herramientas `mcp__github__*`.
- Cada función nueva de la plataforma debe poder usarla Brian (`docs/BRIAN.md`); el PR lo pregunta.

## 5. Dónde está cada cosa

| Quiero saber… | Voy a… |
|---|---|
| Qué se pidió y en qué orden se hace | [PRIORIDADES.md](PRIORIDADES.md) |
| Cómo está todo (nota y fallas) | [ESTADO.md](ESTADO.md) *(fecha en su primera línea; si es vieja, manda este archivo)* |
| Qué le toca decidir o hacer a la dueña | [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md) |
| Trabajo de desarrollo abierto | Los issues del repositorio (`mcp__github__list_issues`) |
| Cómo se despliega y se vuelve atrás | [DESPLIEGUE.md](DESPLIEGUE.md) y [OPERACION.md](OPERACION.md) |
| Qué ve cada rol | [PERMISOS.md](PERMISOS.md) |
| Cómo hablar con Brian y qué puede hacer | [BRIAN.md](BRIAN.md) |
| Todo lo demás | [README.md](README.md) (índice de `docs/`) |

## Bitácora de sesiones

> Más reciente arriba. Cada entrada: fecha, qué quedó en producción (con el commit), qué quedó solo en staging, qué
> sigue. Se guardan unas diez; las viejas se resumen en una línea.

### 2026-10-16

- **En producción** (02:32 UTC, `baf8975`): «Imprimir documentos» sale en el orden nota de entrega → factura del
  cliente → copia de la empresa (PR #42). Antes (20:01 UTC, `d709cfb`): los botones «Vincular mi Telegram» y «Registrar
  webhook» de Brian ya no fallan (PR #41).
- **Pasó:** el jefe pidió una tanda grande de mejoras (utilidad en el Inicio, rediseño del Inicio, menú de Contabilidad,
  verificación con escáner en bodega, contactos duplicados, alertas, bitácora de bodega, estadísticas, colores del menú,
  categoría «Envíos»). Quedó ordenada en [PRIORIDADES.md](PRIORIDADES.md) y explicada en el documento «Plan de mejoras
  del jefe» de Claude Docs.
- **Hallazgos verificados ese día** (no corregidos todavía): el botón de descuento global y de importe fijo de las
  cotizaciones se salta el tope de descuento de la Vendedora cuando existe el producto de descuento (prueba real en una
  base local); la Vendedora puede corregir existencias a mano en Inventario físico; «Vendido hoy» incluye ITBMS y el
  «Ventas» del Resumen contable no; el tope de gasto de IA de Brian viene en 0 (sin tope); no hay ninguna alerta de
  stock bajo ni de cierre de mes; el asistente de fusión de contactos no le sirve a Gerencia (falta el grupo «Creación») y no copia los datos de Socios de la ficha que se borra (no fusionar socios con él).
- **Sigue:** empezar por lo primero de PRIORIDADES.md. Estudio de envíos para La Chorrera entregado como documento en
  Claude Docs (a la espera de sus respuestas).
