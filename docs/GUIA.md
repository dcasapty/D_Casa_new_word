# La Guía del negocio (`dcasa_guia`)

**«¿Qué necesitas hacer hoy?»** Una pantalla para quien administra el negocio sin ser contador. Muchas veces la
persona no sabe que existe una pantalla (la declaración de renta, el cierre de mes, una nota de crédito) ni en qué menú
está. La Guía le deja **escoger un tema o escribir lo que quiere lograr**, le explica **en palabras sencillas qué va a
lograr** al llegar a la pantalla y la abre con un clic en **«Llévame ahí»**. Arriba muestra **lo que más se usa en su
puesto** y, cuando ya hay costumbre, **lo que ella o él más usa**.

## Dónde está

- Menú de la izquierda: **Guía** (el ícono de la brújula, justo debajo de Inicio). Lo ve todo el equipo, pero **cada
  persona ve solo lo que puede abrir** (ver «Permisos»).
- En el **Inicio**: botón **¿Qué necesito hacer?** junto a los accesos del día.
- En cada tarea: **Llévame ahí** (abre la pantalla justa) y **Preguntarle a Brian**, que abre el panel de Brian con la
  pregunta ya escrita (la persona decide si la envía).

## Cómo se usa

1. **Arriba, lo que más se usa.** Dos listas cortas, cada una con su botón **Llévame ahí**:
   - **«Lo que tú más usas»** (solo cuando ya hay costumbre: por ejemplo, 3 tareas usadas 2 veces o más). Dice cuántas
     veces la usaste. Es solo tuyo: nadie ve lo que usas ni tú lo de otros.
   - **«En tu puesto lo que más se usa»**: la lista curada para tu puesto (Vendedora, Gerencia, Contabilidad o, si no
     tienes uno de esos, una general). Lo que ya sale en «Lo que tú más usas» no se repite aquí.
2. **Escoge un tema** (11 temas): Vender y cobrar · Facturas y pagos · Bancos · Cómo va el negocio · Impuestos y
   obligaciones · Personal y nómina · Productos e inventario · Compras y proveedores · Clientes, socios y vendedores ·
   Tienda en línea y conversaciones · Administrar el sistema. Cada tema tiene subtemas («Una vez al año», «Cada mes»,
   «Cambiar el estado de algo»…).
3. **O escribe** lo que quieres lograr («declaración de renta», «cobrar a un cliente», «cerrar el mes»). Busca sin
   tildes ni mayúsculas y por trozos de palabra; solo salen las tareas que coinciden con más palabras de lo escrito.
4. **Cada tarea tiene su «Llévame ahí»**, a la derecha de su título, también en los resultados del buscador: un clic y
   estás en la pantalla justa (el menú con sus filtros, o un formulario nuevo). **Toca el título** para leer antes: se
   despliega *Qué vas a lograr*, los pasos (si los tiene), una nota, *Dónde queda* en el menú (para que la próxima vez
   llegues solo) y **Llévame ahí** y **Preguntarle a Brian**.
5. **Los pasos**: cada paso que tiene pantalla lleva su propio **Llévame ahí**; un paso sin pantalla (por ejemplo
   «Entrégale esos reportes a tu contador») se lee como una instrucción, con el número en gris y sin botón.
6. «**Lo que más se necesita**» (las 10 tareas de `empezar`) solo sale cuando tu puesto no tiene lista.

Hay tareas con **pasos**: **Preparar la declaración de renta**, **Pasarle los números a mi contador**, imprimir un
cheque, el combo de cama y colchón, imprimir documentos. Y tareas **para cambiar el estado de algo**: confirmar una
factura en borrador, corregir o anular una factura publicada, reabrir un mes cerrado.

### La cinta «Estás haciendo»

Al llegar con **Llévame ahí**, abajo de la pantalla queda una cinta pequeña y discreta:

- Dice **«Estás haciendo: <tarea>»** y, si venías de un paso, **«Paso 3 de 7»** y **«Siguiente: …»**. Si el siguiente paso
  tiene pantalla, la cinta trae su **Llévame ahí**; si se hace en la misma pantalla, trae **Ya lo hice** (avanza sin
  moverte). El último paso dice «Es el último paso».
- **Volver a la Guía** te regresa a la Guía con esa tarea abierta y con el foco puesto en ella.
- La **x** la cierra. Se va sola cuando sales de las pantallas de la tarea (otra app, otro menú) o vuelves a la Guía.
  Nunca vuelve sola; si recargas la página, desaparece.

**Por qué es segura.** La cinta es un componente aparte (`main_components`, la forma normal de Odoo para cosas que viven
fuera de las pantallas): **no se inyecta dentro de ninguna vista ni formulario de Odoo**, así que no puede romperlos; si
ella fallara, Odoo solo la quita. Va fija abajo (en el escritorio, a la derecha de la barra lateral) y reserva su alto
abajo del contenido para no tapar lo último de la pantalla (escribe una sola variable de estilo, `--dc-cinta-alto`). No se
imprime y cede el lugar a los menús desplegables y diálogos de Odoo.

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
5. **«Llévame ahí» solo donde la persona puede llegar.** Si no puede abrir la pantalla, la tarea ni el paso traen botón
   (el servidor no manda el destino). Esto vale también para las listas de arriba: la lista de un puesto se filtra con
   los mismos permisos, así que una vendedora nunca ve ahí lo de Gerencia.
6. **El uso es de cada persona.** Solo se guarda *quién*, *qué tarea de la Guía*, *cuántas veces* y *la última vez*;
   nada de clientes ni de documentos. Cada quien ve y escribe solo lo suyo (regla de registro; tampoco lo ve un
   administrador desde la pantalla). Los números son de uso real: nada se inventa ni se rellena.
7. **Anotar el uso nunca estorba.** Se anota sin esperar la respuesta; si falla (red, servidor, tarea que ya no existe)
   queda en la consola o en el log y el botón lleva igual.

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
- `grupos` (opcional): la tarea sale solo a quien tiene alguno de esos grupos, además del permiso del menú. Sirve
  cuando todos abren la pantalla pero lo que la tarea explica es de unos pocos («Comparar las ventas»: el Inicio lo
  abren todos; el bloque Comparar es de Gerencia y administradores).
- `tambien`: otras categorías donde también aparece. `empezar` (arriba del archivo) es la lista ordenada de «Lo que más
  se necesita» (máximo 10).
- Para encontrar el xmlid de un menú: Ajustes › Técnico › Menús (modo desarrollador), o el nombre externo en la base.

**Regla del repositorio:** cuando se construye una pantalla nueva que un administrador debería encontrar, se agrega su
tarea aquí en el mismo PR.

## Lo más usado según el puesto

Todo está en `addons/dcasa_guia/data/guia_roles.json` (una lista de ids de `guia.json` por puesto):

| Puesto | A quién le toca | Tareas (en este orden) |
|---|---|---|
| Gerencia | grupo Gerencia o administrador del sistema | resumen · ventas de hoy · cobros de hoy · quién me debe · ITBMS · cerrar el mes · conciliar el banco · ¿gané o perdí? |
| Contabilidad | grupo Contabilidad (`account.group_account_user`) | resumen · quién me debe · a quién le debo · factura de proveedor · conciliar el banco · ITBMS · cerrar el mes · pasarle los números al contador |
| Vendedora | grupo Vendedora (o vendedor de Ventas) | cotizar · por facturar · cobrar · ventas de hoy · encontrar un producto por su código · conversaciones · agregar un cliente |
| Equipo (por defecto) | cualquier otra persona de adentro | conversaciones · buscar un cliente · agregar un cliente · productos · existencias · pedir un reembolso |

- El puesto de cada persona es **el primero de la lista al que pertenece** (Gerencia incluye a Vendedora y a Contabilidad,
  por eso va primero). Para cambiar a quién le toca cada puesto, se cambian sus `grupos` en el archivo.
- Cada lista lleva de **6 a 8** tareas. Una prueba vigila que todos los ids existan, que no se repitan y que la
  vendedora no lleve nada de Gerencia.
- «Lo que tú más usas» sale cuando la persona tiene **al menos 3 tareas con 2 usos o más** y muestra hasta **5** (las más
  usadas primero; a igual uso, la más reciente). Los tres números están en `masUsadas` del mismo archivo. Solo cuenta
  lo que la persona todavía puede abrir.
- Quien quiera cambiar una lista, lo hace en ese archivo (sin código); no hay pantalla para editarlas.

## Brian

La herramienta **`buscar_en_guia(consulta)`** (lectura, cualquier usuario interno) devuelve las tareas que coinciden con lo
que la persona quiere hacer: **qué logra, dónde queda en el menú, los pasos y la nota**, y un botón *abrir* cuando el
menú abre la lista de un modelo. Solo trae lo que quien pregunta puede abrir. Así Brian responde «para la declaración de
renta, abre Facturación › Reportes contables › Estado de resultados…» con la misma fuente que la pantalla. El servicio
`dcasa_brian` ganó `preguntar(texto)` (abre el panel con la pregunta escrita).

## Técnico

- `models/guia.py`: modelo abstracto `dcasa.guia` con `obtener()` (para la pantalla: temas, `empezar`, `rol`, `puesto` y
  `mas_usadas`), `buscar(consulta, limite)` y `registrar_uso(tarea_id)`; funciones puras `normalizar`, `palabras_de`,
  `puntaje`, `cargar_catalogo`, `cargar_roles`, `buscar_tarea`.
- `models/uso.py`: modelo `dcasa.guia.uso` (persona, tarea, veces, última vez; una fila por persona y tarea, `veces > 0`,
  la tarea debe existir en `guia.json`). Seguridad: `security/ir.model.access.csv` (personal interno: leer, escribir y
  crear; nadie borra) y la regla global `regla_guia_uso_propio` (`user_id = user.id`). Lo escribe `registrar_uso` con los
  permisos de quien llama, sin `sudo()`.
- `registrar_uso(tarea_id)`: devuelve `True` o `False` y **nunca lanza**: un id que no es texto, que no existe en el
  catálogo o que la persona no puede abrir da `False` sin tocar nada; un error de la base queda en un savepoint y en el
  log (`WARNING`).
- Pantalla: acción de cliente `dcasa_guia` (`static/src/js/guia.js`, `xml/guia.xml`, `scss/guia.scss`), registrada con el
  menú `dcasa_guia.menu_guia`. «Llévame ahí» y la cinta viven en `static/src/js/guia_ruta.js` (servicio
  `dcasa_guia_ruta` y componente `GuiaCinta`), `xml/guia_cinta.xml` y `scss/guia_cinta.scss`. El servicio abre el destino,
  anota el uso con `orm.silent` sin esperar (y encadena los avisos para que dos clics no se pisen) y deja la cinta. Se
  prueba en navegador a 1366 px y 390 px.
- El Inicio (`dcasa_interfaz`) muestra el botón solo si el módulo está instalado (`datos.guia`).
- Pruebas (`scripts/test.sh dcasa_guia,dcasa_brian,dcasa_conversaciones,dcasa_nomina`; las de navegador usan Chrome y se
  saltan si no está): `test_guia.py` (catálogo coherente, atajos existentes, permisos por rol, buscador, pantalla),
  `test_llevame.py` (listas por puesto válidas y filtradas por permisos, uso por persona aislado, registro que tolera lo
  raro y los fallos, «Lo que tú más usas», contrato de la pantalla), `test_llevame_navegador.py` (el botón abre la
  pantalla justa desde la tarjeta, el buscador y cada paso; la cinta; la vendedora; el uso fallando; el celular) y
  `test_scroll.py`; además `dcasa_brian/tests/test_guia_brian.py`. Los tres métodos públicos (`obtener`, `buscar`,
  `registrar_uso`) están en la lista blanca de `dcasa_base/tests/test_superficie_rpc.py` (sin `sudo()`).
- Datos personales: `dcasa.guia.uso` guarda quién usó qué tarea de la Guía y cuántas veces (un dato de la persona, solo
  suyo). No lleva nada de clientes, documentos, montos ni mensajes. El catálogo no lleva nombres ni cifras del negocio.

## Lo que la Guía no hace (todavía)

- No presenta ni calcula impuestos, ni recuerda fechas: no hay alertas automáticas («te toca declarar el ITBMS»).
  Se puede construir cuando el contador confirme el calendario que aplica a D'CASA.
- No explica cada pantalla *por dentro*: lleva hasta ella y dice qué se logra; el detalle lo da Brian.
- El catálogo y las listas por puesto no se editan desde Odoo: son archivos del repositorio (así los revisan las pruebas).
- La cinta no recuerda dónde ibas si recargas la página y no sabe si terminaste la tarea: es un recordatorio, no un
  seguimiento. «Ya lo hice» solo avanza el recordatorio.
- «Lo que tú más usas» cuenta los «Llévame ahí»; no sabe si la tarea se terminó. Un paso cuenta como un uso de su tarea
  (los pasos que se abren desde la cinta no suman).
