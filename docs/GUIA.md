# La Guía del negocio (`dcasa_guia`)

**«¿Qué necesitas hacer hoy?»** Una pantalla para quien administra el negocio sin ser contador. Muchas veces la
persona no sabe que existe una pantalla (la declaración de renta, el cierre de mes, una nota de crédito) ni en qué menú
está. La Guía le deja **escoger un tema o escribir lo que quiere lograr**, le explica **en palabras sencillas qué va a
lograr** al llegar a la pantalla y la abre con un botón.

## Dónde está

- Menú de la izquierda: **Guía** (el ícono de la brújula, justo debajo de Inicio). Lo ve todo el equipo, pero **cada
  persona ve solo lo que puede abrir** (ver «Permisos»).
- En el **Inicio**: botón **¿Qué necesito hacer?** junto a los accesos del día.
- En cada tarea: **Preguntarle a Brian**, que abre el panel de Brian con la pregunta ya escrita (la persona decide si
  la envía).

## Cómo se usa

1. **Escoge un tema** (11 temas): Vender y cobrar · Facturas y pagos · Bancos · Cómo va el negocio · Impuestos y
   obligaciones · Personal y nómina · Productos e inventario · Compras y proveedores · Clientes, socios y vendedores ·
   Tienda en línea y conversaciones · Administrar el sistema. Cada tema tiene subtemas («Una vez al año», «Cada mes»,
   «Cambiar el estado de algo»…).
2. **O escribe** lo que quieres lograr («declaración de renta», «cobrar a un cliente», «cerrar el mes»). Busca sin
   tildes ni mayúsculas y por trozos de palabra; solo salen las tareas que coinciden con más palabras de lo escrito.
3. **Toca una tarea**: se despliega *Qué vas a lograr*, los pasos (si los tiene), una nota, *Dónde queda* en el menú
   (para que la próxima vez llegue solo) y los botones **Ir ahora** y **Preguntarle a Brian**.
4. «**Lo que más se necesita**» (10 tareas) está abajo de los temas.

Hay tareas con **pasos**, cada uno con su botón *Abrir*: **Preparar la declaración de renta** y **Pasarle los números a
mi contador**. Y tareas **para cambiar el estado de algo**: confirmar una factura en borrador, corregir o anular una
factura publicada, reabrir un mes cerrado.

## Qué contiene hoy

Unas 90 tareas. Las de **Impuestos y obligaciones** (declaración de renta, ITBMS, seguro social y seguro educativo,
décimo tercer mes, facturación electrónica de la DGI y un recordatorio de otras obligaciones) existen para que el
administrador *se entere* de que están. **No presentan nada por él**: el sistema deja los números listos y la
presentación la hace el contador (o él en el portal de la DGI).

## Reglas (no negociables)

1. **No se inventan fechas ni montos de impuestos.** Donde hay una fecha límite, la nota manda a **confirmarla con el
   contador**. Una prueba (`test_no_se_inventan_fechas_ni_montos_de_impuestos`) vigila que el catálogo no afirme «el 15
   de marzo» ni cifras en dólares.
2. **Cada tarea se muestra solo si la persona puede abrir su pantalla.** Se usan los permisos del menú de la izquierda
   (`ir.ui.menu._visible_menu_ids`) **y de todos sus menús padre**: Odoo marca visible a un menú sin grupos aunque su
   app no lo sea (la barra lateral lo esconde porque esconde la app), y la Guía no puede ofrecerlo. Una vendedora no
   ve contabilidad; Gerencia sí.
3. **Cada atajo debe existir.** Una prueba recorre el catálogo y falla si un menú ya no existe o no abre ninguna
   pantalla, y si un filtro (`search_default_*`) no está en la vista de búsqueda. Si un módulo cambia un menú, la prueba lo dice.
4. **Palabras sencillas.** Una frase completa en «qué vas a lograr», sin jerga contable cuando se puede evitar.

## Cómo agregar o cambiar una tarea

Todo está en `addons/dcasa_guia/data/guia.json` (no hay código por tarea). Una tarea:

```json
{"id": "cierre-mes", "categoria": "reportes", "grupo": "Cerrar",
 "titulo": "Cerrar el mes",
 "logras": "El sistema revisa una lista … y, si todo está bien, bloquea el mes ….",
 "destino": {"menu": "dcasa_contabilidad.menu_cierre_mes"},
 "palabras": ["cierre", "bloquear mes", "fin de mes"],
 "tambien": ["impuestos"], "nota": "…", "brian": "¿…?",
 "pasos": [{"texto": "…", "destino": {"menu": "…"}}, {"texto": "Última, sin pantalla", "destino": null}]}
```

- `destino`: `{"menu": "modulo.xmlid"}` abre ese menú (con `"contexto": {"search_default_draft": 1}` para filtrar);
  `{"nuevo": "modelo"}` abre un formulario nuevo; `null` = solo explicación (entonces lleva `nota` o `brian`).
- `palabras`: cómo lo dice la gente («isr» para la renta). Una palabra que la tarea declara tal cual pesa más en la búsqueda.
- `tambien`: otras categorías donde también aparece. `empezar` (arriba del archivo) es la lista ordenada de «Lo que más
  se necesita» (máximo 10).
- Para encontrar el xmlid de un menú: Ajustes › Técnico › Menús (modo desarrollador), o el nombre externo en la base.

**Regla del repositorio:** cuando se construye una pantalla nueva que un administrador debería encontrar, se agrega su
tarea aquí en el mismo PR.

## Brian

La herramienta **`buscar_en_guia(consulta)`** (lectura, cualquier usuario interno) devuelve las tareas que coinciden con lo
que la persona quiere hacer: **qué logra, dónde queda en el menú, los pasos y la nota**, y un botón *abrir* cuando el
menú abre la lista de un modelo. Solo trae lo que quien pregunta puede abrir. Así Brian responde «para la declaración de
renta, abre Facturación › Reportes contables › Estado de resultados…» con la misma fuente que la pantalla. El servicio
`dcasa_brian` ganó `preguntar(texto)` (abre el panel con la pregunta escrita).

## Técnico

- `models/guia.py`: modelo abstracto `dcasa.guia` con `obtener()` (para la pantalla) y `buscar(consulta, limite)`;
  funciones puras `normalizar`, `palabras_de`, `puntaje`.
- Pantalla: acción de cliente `dcasa_guia` (`static/src/js/guia.js`, `xml/guia.xml`, `scss/guia.scss`), registrada con el
  menú `dcasa_guia.menu_guia`. Se prueba en navegador a 1360 px y 390 px.
- El Inicio (`dcasa_interfaz`) muestra el botón solo si el módulo está instalado (`datos.guia`).
- Pruebas: `scripts/test.sh dcasa_guia` (catálogo coherente, atajos existentes, permisos por rol, buscador, pantalla) y
  `dcasa_brian/tests/test_guia_brian.py`. Los dos métodos públicos están en la lista blanca de
  `dcasa_base/tests/test_superficie_rpc.py` (sin `sudo()`; el catálogo es un archivo del repositorio, sin datos del negocio).
- Datos personales: ninguno. El catálogo no lleva nombres ni cifras del negocio.

## Lo que la Guía no hace (todavía)

- No presenta ni calcula impuestos, ni recuerda fechas: no hay alertas automáticas («te toca declarar el ITBMS»).
  Se puede construir cuando el contador confirme el calendario que aplica a D'CASA.
- No explica cada pantalla *por dentro*: lleva hasta ella y dice qué se logra; el detalle lo da Brian.
- El catálogo no se edita desde Odoo: es un archivo del repositorio (así lo revisan las pruebas).
