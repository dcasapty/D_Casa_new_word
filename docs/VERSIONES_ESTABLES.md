# Versiones estables (a dónde volver si algo se rompe)

Pedido de la dueña (2026-10-16): guardar una versión que funciona bien para poder volver a ella si un cambio
posterior rompe algo o si no hay tiempo de arreglarlo. Cada vez que una versión queda en producción y la dueña
confirma que se ve bien, se agrega aquí.

## Las versiones guardadas

| Versión | Desde | Qué trae | Código | `app_version` | `imagen_digest` |
|---|---|---|---|---|---|
| **Estable 2** | 2026-10-16, 15:11 UTC (Desplegar 11) | Todo lo de la Estable 1 más: Etapa 3 (cliente una sola vez al cotizar), prueba de humo del arranque y «nunca hacia atrás», Conversaciones #25, el botón para volver, y el Inicio con cotizaciones y entregas arriba y cifras que cuadran con Contabilidad. La dueña confirmó que se ve bien. | rama `estable-2026-10-16-2` (y PR #47) | `9be426a46e15ac124f991648289b41643cf2bfee` | `sha256:876ca5f5c7f14a6fea91d4b0fb0e4f88be485aba5b167cc3566289fb1ac4f078` |
| **Estable 1** | 2026-10-16, 07:27 UTC (Desplegar 9) | Etapas 1 y 2 (Inicio con ganancia, tope de descuento, fusión segura, existencias solo por Gerencia, Estadísticas, íconos de color) y el arreglo del arranque (#97). La dueña confirmó Inicio y conversaciones. | rama `estable-2026-10-16` (y PR #45) | `3570c3a12e5563621be5ef835837a223904b06c5` | `sha256:4e9b915580dd3d346c2d8ec7f3b2b02809c13172e02fd6e9c392b34c239bc2e3` |

Qué se guarda de cada una:

- **El código:** una rama con su nombre (`estable-AAAA-MM-DD`) que no se toca, hecha desde `main` con el PR ya unido
  (mismo código; desde las sesiones de Claude no se pueden crear etiquetas de git). El commit exacto con que se
  construyó la imagen es el `app_version` y queda guardado en su PR.
- **La imagen ya construida y probada:** en el registro de Cloudflare, con la etiqueta `dcasa-odoo:<app_version>`.
  No se reconstruye nada para volver. Ningún flujo de este repositorio la borra; cuánto la guarda Cloudflare por su
  cuenta **no está confirmado**.
- **Los datos:** no se guardan «con la versión». Los cuidan los respaldos: cualquier minuto de los **últimos 7 días**
  (pgBackRest), una copia por día de los **últimos 30 días** y la copia anual de cierre (`docs/OPERACION.md`).

## Cómo volver a una versión estable

**Con el botón** (sin copiar nada): Actions → **Volver a una versión estable** → *Run workflow*, en `main`:

- `entorno`: `production` (o `staging` para ensayar primero);
- `version`: la de la tabla (la más nueva arriba: `estable-2`);
- `respaldo_previo`: marcado (desmarcarlo solo si el sitio está caído y el respaldo no puede hacerse).

Tarda unos 3 minutos más el arranque; el último paso espera a que responda esa versión con la base al día. Los datos
de cada versión viven en `.github/versiones_estables.json` (una prueba de CI revisa que estén bien escritos).

**A mano** (si el botón todavía no está en `main`): Actions → **Desplegar** → *Run workflow*, en `main`, con el mismo
`entorno` y `respaldo_previo` y el `app_version` y el `imagen_digest` de la tabla.

**Si un día Cloudflare ya no tuviera la imagen:** lanzar **CI/CD** sobre la rama `estable-AAAA-MM-DD` con
`desplegar_en = staging` (reconstruye y prueba la misma versión) y después desplegar a producción ese commit con el
digest de su resumen, como siempre.

**Qué pasa con los datos.** Hay dos maneras, y se elige según el problema:

1. **Volver solo el programa (lo normal):** las ventas, facturas, clientes y todo lo que se hizo después **se quedan**.
   Lo que solo existía en las versiones nuevas (campos o pantallas que la estable no tiene) deja de verse y sus datos
   se pierden. Si la versión estable es **anterior** al candado «nunca hacia atrás» (la Estable 1 lo es), la base se
   ajusta sola al arrancar. La Estable 2 ya trae el candado: volver a ella desde una versión más nueva pide
   `DCASA_PERMITIR_BAJAR`. Si es **posterior**, el arranque se niega a bajar la base y hay que pegar en el panel de
   Cloudflare del Worker `DCASA_PERMITIR_BAJAR=<su app_version>` antes de desplegar (y quitarla después).
2. **Volver todo a un momento (programa y datos):** solo si un cambio **dañó datos**. Se pierde todo lo hecho después
   de ese momento: decisión de la dueña. Es una sola operación: `DCASA_RESTAURAR_HASTA` con la hora y, en el mismo
   arranque, el despliegue de la versión estable (`docs/OPERACION.md`, «Volver atrás un despliegue»).

**Antes de necesitarlo:** ensayarlo en staging (desplegar ahí la versión estable y abrir Inicio, Conversaciones y una
cotización). Mientras no se haya ensayado, volver puede dar sorpresas (p. ej. un módulo que la versión nueva instaló y
la vieja no conoce).

## Cómo se agrega una versión estable

Cuando un despliegue a producción queda «Confirmado» y la dueña dice que se ve bien:

1. Crear la rama `estable-AAAA-MM-DD` desde `main` (ya con el PR unido).
2. Agregar la versión a `.github/versiones_estables.json` (con el `app_version` y el `imagen_digest` del resumen del
   despliegue) y su nombre a las opciones de `version` en `.github/workflows/volver-a-estable.yml`.
3. Agregar la fila a la tabla de arriba y anotarlo en la bitácora (`docs/LEEME_PRIMERO.md`).
