# La puerta `/master` en producción (paso a paso para la dueña)

Cómo dejar funcionando la entrada del equipo (`/master`: PIN al correo → correo y clave → código de la app) en
producción, cómo comprobarlo y cómo encender `DCASA_PUERTA_OBLIGATORIA`. El detalle técnico está en
[SEGURIDAD_ACCESO.md §8](SEGURIDAD_ACCESO.md#8-la-puerta-del-equipo-cloudflare-access--clave--código-de-la-app).
**Nunca pegues un secreto en el chat**: se ponen en GitHub o en Cloudflare, y Claude solo confirma que el nombre existe.

## 0. Lo que se encontró (2026-10-18)

- **El código y las variables son iguales en staging y en producción**, salvo el interruptor (staging en `"1"`,
  producción en `"0"`). Los dos entornos cargan los mismos cuatro secretos de la puerta en cada despliegue (registro
  «Secretos a subir con el despliegue» de Desplegar 18 y del CI #196), y en producción `DCASA_PUERTA_RUTA` es `/master`
  (en el registro del CI #132, GitHub tapó con `***` el texto «/master» del título del commit: solo tapa los secretos).
- **Lo que no se puede ver desde el código son dos datos de Cloudflare Access de producción:** en qué dirección está
  puesta la aplicación de Access y qué «AUD tag» tiene. Si uno de los dos no corresponde, el borde rechaza el pase.
  Eso pasa **igual con el interruptor en «0»**: hoy `/master` de producción no abre, y el equipo entra por `/web/login`.
- Causa más probable (error humano, como sospecha la dueña): en GitHub › Environments › **production** ›
  `DCASA_ACCESS_AUD` está el AUD de la aplicación de **staging** (o de otra aplicación), o la aplicación de producción
  quedó con el dominio `dcasapty.com` (así lo decía esta guía antes) en vez de `dcasa.dcasapty.workers.dev`, que es
  donde vive hoy el sitio.
- Hasta ahora el borde respondía un «Not Found» pelado y no se sabía cuál de las dos era. **Desde este cambio, `/master`
  dice por qué no abre** (ver el paso 3).

## 1. Cloudflare › Zero Trust › Access (la aplicación de producción)

1. Entra a <https://dash.cloudflare.com> › **Zero Trust** › **Access controls** › **Applications**.
2. Busca la aplicación del equipo de producción (se llama «Master (producción)»; si no la encuentras, la de staging se
   llama «Master (staging)»). Ábrela con **Configure**.
3. En **Public hostname** (o *Destinations*) tiene que estar:
   - **Dominio:** `dcasa.dcasapty.workers.dev` (la dirección de producción hoy; cuando se traslade el dominio se
     **agrega** `dcasapty.com`, ver [TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md));
   - **Path:** `master`.
   Si dice `dcasapty.com` o `dcasa-staging…`, agrega la de producción y guarda. Una aplicación puede tener varias
   direcciones: su AUD no cambia.
4. **Policies:** la política «Equipo D'CASA», acción **Allow**, regla **Include › Emails** con los correos del equipo.
5. **Login methods:** solo **One-time PIN**.
6. En la pestaña **Overview** (o *Basic information*) copia el **Application Audience (AUD) Tag**: un texto largo de
   letras y números. Fíjate en sus **últimas 6 letras**: sirven para comparar en el paso 3.
7. En **Zero Trust › Settings** mira el **Team domain** (algo como `algo.cloudflareaccess.com`).

## 2. GitHub › Environments › production (los cuatro secretos)

En <https://github.com/dcasapty/D_Casa_new_word/settings/environments> › **production** › **Environment secrets**
(no en «Repository secrets»: esos los comparten staging y producción):

| Secreto | Qué tiene que tener |
|---|---|
| `DCASA_PUERTA_RUTA` | `/master` (ya está bien) |
| `DCASA_PUERTA_SECRETO` | 32 o más letras al azar, **distinto del de staging** (`openssl rand -hex 32`) |
| `DCASA_ACCESS_EQUIPO` | `https://` + el Team domain del paso 1.7, sin barra al final |
| `DCASA_ACCESS_AUD` | el AUD del paso 1.6 (el de **producción**, no el de staging) |

GitHub no deja ver el valor guardado: si dudas del AUD, **vuelve a pegarlo** (Update secret). Después hay que desplegar
para que llegue al sitio (Actions › **Desplegar**, como siempre; lo hace Claude con tu «sí»).

## 3. Comprobar (con el interruptor todavía en «0»)

1. Abre `https://dcasa.dcasapty.workers.dev/master` en una ventana de incógnito.
2. **Lo correcto:** Cloudflare pide tu correo → llega el PIN → aparece «Acceso del equipo» → correo y clave → código de
   Google Authenticator → el panel.
3. **Si algo falla, la página lo dice** (fondo azul, «Acceso del equipo»), con un **Código** abajo:

| Código | Qué significa | Qué hacer |
|---|---|---|
| `sin token` | No te pidió el PIN: la aplicación de Access no está en esta dirección | Paso 1.3 |
| `audiencia` | Te pidió el PIN, pero de otra aplicación (muestra las 6 últimas letras de cada AUD) | Paso 1.6 y 2 (`DCASA_ACCESS_AUD`) |
| `emisor`, `llave desconocida`, `llaves no disponibles` | El pase es de otro equipo, o el Team domain está mal escrito | Paso 1.7 y 2 (`DCASA_ACCESS_EQUIPO`) |
| `vencido` | El pase de Access venció | Botón «Pedir un PIN nuevo» |
| `sin correo` | Access no mandó el correo | Paso 1.5; usar un correo sin tildes ni ñ |
| `puerta_incompleta` | Falta (o está mal escrito) uno de los cuatro secretos: la página dice cuál | Paso 2 |

4. También se ve en `https://dcasa.dcasapty.workers.dev/__edge/health`: el bloque `"puerta"` dice `"estado": "lista"`
   (las cuatro bien escritas), `"incompleta"` (con los nombres que faltan) o `"apagada"`, y el `"modo"`.
5. Repite hasta entrar al panel por `/master`. Pídele a cada persona del equipo que entre una vez así.

## 4. Encender `DCASA_PUERTA_OBLIGATORIA` (por pasos, sin quedarte fuera)

Lo cambia Claude en `edge/wrangler.jsonc` (bloque de producción, arriba; staging tiene el suyo) y se despliega:

1. **`"avisar"`**: nadie se queda fuera, pero quien entra sin la puerta queda anotado en Odoo › Ajustes › Usuarios ›
   **Accesos al panel** (filtro «Sin pasar por la puerta») y, si es administrador, llega un aviso a Telegram. Uno o dos
   días, hasta que no aparezca nadie del equipo.
2. **`"1"`**: el equipo solo entra por `/master`; `/odoo` sin la puerta da «no existe»; quien abre
   `/web/login?redirect=/odoo` (sesión vencida) va solo a `/master`; en `/web/login` la clave del equipo no sirve (ese
   login queda para los clientes) y el código de la app es obligatorio para todo el personal.
3. Opcional, después: `DCASA_PUERTA_EXIGIR_CORREO` en `"1"` (el correo del PIN tiene que ser el de la cuenta de Odoo).

**Rescate** (si la puerta no abre con «1»): poner `DCASA_PUERTA_OBLIGATORIA` en `"0"` y desplegar. Surte efecto en cuanto
termina el despliegue; no hay que tocar Cloudflare ni Odoo.

## 5. «Iniciar sesión» en la web

Los clientes entran por **Mi cuenta** (`/mi-cuenta`: celular y PIN, o su correo). La cabecera y el pie ya decían «Mi
cuenta»; desde el 2026-10-18 también el botón del checkout («¿Ya tienes cuenta? **Entra a tu cuenta**»), los avisos de
puntos del carrito y «¿Ya tienes cuenta?» de crear cuenta llevan a Mi cuenta, y de ahí vuelven a la tienda. Ninguna página
pública enlaza al panel. El equipo entra solo por `/master`.
