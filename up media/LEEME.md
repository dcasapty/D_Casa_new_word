# up media: bandeja de entrada

Aquí se suben las fotos y los Excel (GitHub → *Add file* → *Upload files* → *Commit changes*).
GitHub los procesa solo y deja el resultado en `RESUMEN.md`, en esta misma carpeta.

- Foto de un producto que ya existe: el nombre es el código (`CODIGO.jpg`, `CODIGO_2.jpg`…).
- Pedido nuevo: el Excel del proveedor **y** sus fotos con el código al inicio del nombre.
- Lo ya cargado se va a `fuentes/<pedido>/`; lo que no era de ningún producto, a `descartado/<fecha>/`
  (con el motivo). Aquí solo queda lo pendiente. Nada se borra.
- `inventario-anterior/` es otra carga (capturas del sistema anterior): tiene su propio LEEME.

Cómo subir y cómo leer el RESUMEN: `docs/OPERACION.md` › «Cómo subir fotos».
