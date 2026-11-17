# Resumen de la noche (16 de noviembre)

## 1. El Black Friday ya está en producción ✅

Subido y comprobado: el sitio responde, el chat abre diciendo **«Hola, soy Andrés»**, y **«Promociones» no aparece**
todavía porque aún no has creado la campaña (es lo esperado).

### Los pasos para crear la campaña

1. **Sitio web › Configuración › Campaña del sitio.**
2. Toca **«Empezar de cero»**. Las camas del Black Weekend siguen marcadas.
3. Pon el **nombre** («Black Friday»), las **fechas reales** y, si quieres, una frase.
   Las horas son de Panamá: la campaña corre desde las 00:00 del primer día hasta las 23:59 del último.
4. En **«Elegir productos y precios»**, marca **«En la campaña»** y escribe el **precio de campaña sin ITBMS**.
   El precio es opcional: un producto marcado sin precio sale en la página con su precio normal.
5. Para varios productos a la vez: selecciónalos y usa **Acción › «Aplicar un descuento de campaña»** (en %).
6. **«Promociones»** aparece solo en el menú cuando empieza la campaña, y se quita sola cuando termina.

Tienes hasta el **viernes 27**, así que hay días de sobra para marcar los productos con calma.

### Lo nuevo de los combos

Ya no tienes que preocuparte por si un combo queda mal con la oferta. El sistema compara el par completo:

- Si el combo (cama a precio normal + colchón a precio en combo) sale **igual o más barato** que comprar las dos
  piezas sueltas con su precio de Black Friday, el combo se queda como siempre.
- Si sale **más caro**, el combo se deshace solo y cada pieza va a su precio de Black Friday.

**Comprar junto nunca sale más caro que comprar por separado.** Y si el combo se deshizo, en el papel no sale ningún
«descuento combo» inventado.

## 2. Qué decidí yo y por qué

- **El tope de descuento de la vendedora** ahora se mide siempre contra lo que la pieza costaría **suelta ese día**,
  esté o no en un combo. Antes el límite saltaba (de $346.50 a $360 con una cama de $400 que en oferta va a $385)
  según hubiera combo o no, y eso abría un hueco: rebajar la cama al máximo estando sola y armarle el combo después
  dejaba el doble de rebaja sin que nadie lo midiera ni avisara. Si prefieres el comportamiento viejo, se cambia en
  un rato.
- **El ahorro que imprime el papel** se mide contra lo que la pieza cuesta suelta ese día. Antes, durante una oferta,
  la cotización podía decir «precio $300 · descuento combo −$40» cuando ese día el colchón suelto costaba $280.
- **Dejé fuera la pantalla «Armar combo»**. El arreglo (que muestre los precios de la oferta) rompió dos pruebas y
  preferí no retrasar el Black Friday. El trabajo está guardado.

## 3. Lo que falta, por orden

### Lo primero: una decisión tuya sobre Socios y el envío gratis

La revisión independiente encontró esto, y **no lo cambio sin tu «sí»** porque choca con algo que decidiste antes:

> Si un socio usa un premio de puntos en el carrito web y con eso el carrito baja del mínimo de la promoción, **se
> pierde el envío gratis**. Con las cifras de hoy: carrito de $205, premio de $10 (1.000 puntos) → el carrito queda
> en $195.65, la promoción se borra y el socio paga $45 de envío. **Gasta puntos para perder dinero.**

Dos salidas: (a) avisarle y no dejar canjear cuando el premio mata la promoción; o (b) no contar las líneas de premio
al medir la promoción, solo en los carritos de la web.

### La segunda entrega (sin subir)

Andrés vendedor, notas de voz, micrófono del chat y la portada nueva están listos y probados en la rama, pero **no
suben** hasta arreglar lo de arriba. La misma revisión dejó además: que el total puede quedar negativo al cobrar un
premio en el mostrador; que Andrés puede afirmar un cambio del carrito que no ocurrió si escribe «…ok?» sin abrir la
pregunta; y que la línea del premio de Socios viaja al chat y Andrés puede proponer quitarla.

### Dos cosas del Black Friday, anotadas y sin urgencia

- **La web y Juan publican el precio de combo escrito en el Excel** («Combo con colchón $649.99»). Ese número no se
  calcula: lo escribió alguien en la hoja y nadie lo revisa, así que puede no coincidir con lo que cobra la
  cotización. Viene de antes.
- **La pantalla «Armar combo»** le muestra a la vendedora precios sin la oferta.

## 4. Ramas para borrar (necesito tu «sí»)

- `claude/determined-einstein-ouls04` — ya está unida al trabajo.
- `claude/bold-volta-fsqq4c` — nunca se aprobó.
- `claude/black-friday-solo` — ya se unió a `main` con el Black Friday.
- `claude/relaxed-tesla-rwrzst` — rama vacía que no se usó.

Las `estable-*` y las `respaldo/*` **se quedan**.
