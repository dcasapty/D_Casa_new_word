# up media: qué pasó con lo que subiste

Procesado el 2026-10-12 por `scripts/procesar_up_media.py` (lo corre GitHub solo, con cada subida: `.github/workflows/up-media.yml`; cómo leer esto: `docs/OPERACION.md` › «Cómo subir fotos»).

Cómo funciona esta carpeta: aquí solo queda lo **pendiente**. Lo que ya se cargó al catálogo está en `fuentes/<pedido>/` y lo que no era de ningún producto, en `descartado/<fecha>/` (con el motivo en su LEEME.md). Las dudas del catálogo (precios, fotos, medidas) están en `docs/CATALOGO_REVISAR.md`.

## Excel cargados

- Ninguno.

## Fotos cargadas: a qué producto fue cada una

| Foto | Producto | Cómo se asignó | Ahora está en |
|---|---|---|---|
| — | — | — | — |

## Lo que no se asignó y por qué

### Se queda aquí, pendiente de alguien

- `inventario-anterior`: carpeta: la procesa otro flujo (ver su LEEME); este script no la toca.

### Se guardó sin cargar (no es foto de producto)

- Nada.

### Descartado

- Nada.

## Cómo subir más

- Foto de un producto que ya existe: el nombre es el código (`CODIGO.jpg`, `CODIGO_2.jpg`…).
- Pedido nuevo: el Excel del proveedor **y** sus fotos con el código al inicio del nombre (`908K - Cama tapizada King – negro.jpg`). El programador registra el pedido antes de la carga.
- Si una foto queda «pendiente», basta renombrarla con el código y volver a subirla.
