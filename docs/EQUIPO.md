# Alta del equipo (`dcasa_equipo`)

Para dar de alta a las personas del equipo en **un solo paso**: el usuario, su ficha de empleado, su departamento y su
rol, **sin mandar ninguna invitación**. También cambia el ícono del menú **Empleados** por uno de la marca.

> **Los datos de las personas viven solo en Odoo.** Este módulo no trae ninguna lista de nombres ni correos: se pegan en
> la pantalla y quedan en la base de datos. Nada de eso se guarda en el repositorio.

## Cómo se usa

1. Entra a Odoo como administrador de Ajustes o de accesos (quien puede crear usuarios).
2. **Empleados › Alta del equipo**.
3. Pega una persona por línea, con cinco datos separados por `|` (también sirven `;` o tabulador):

   ```
   nombre | correo | departamento | cargo | rol
   ```

   El **rol** es uno de estos (con las mayúsculas que quieras):

   | Escribes | Qué recibe |
   |---|---|
   | `Vendedora` (o `Vendedor`, `Ventas`) | El rol **Vendedora** de D'CASA: vende, cobra y despacha. |
   | `Gerencia` (o `Gerente`) | El rol **Gerencia** de D'CASA: lo de Vendedora más reportes, contabilidad, compras, inventario y **nómina**. |
   | `Administrador` (o `Admin`, `Control total`) | Gerencia **más** Ajustes de Odoo (control total). Solo lo puede dar un administrador de Ajustes. |

   Las líneas en blanco y las que empiezan con `#` se ignoran.
4. **Leer lista**: se arma una tabla para revisar. Lo que esté mal sale en rojo con el motivo y se corrige ahí mismo.
5. **Crear al equipo**. Cada fila queda *Creado*, *Ya estaba* o *Revisar*. Un error en una persona no frena a las demás
   ni deja nada a medias.

## Qué se crea por persona

* El **usuario** (el correo es su acceso), de la empresa, con zona horaria de Panamá y el rol elegido.
* Su **ficha de empleado**, enlazada al usuario y a su contacto, con su departamento y su cargo (el departamento se crea
  si no existe; se compara sin importar mayúsculas).
* **Nada más**: ni sueldo ni cédula ni datos de nómina (eso lo carga quien lleva la nómina, ver [NOMINA.md](NOMINA.md)).

## Sin invitación

En Odoo, crear un usuario con correo **manda solo** la invitación para elegir clave, y la importación normal también.
Aquí no: el usuario queda como **«Nunca conectado»** y **no puede entrar** hasta que alguien lo decida.

Cuando quieras que entre: **Ajustes › Usuarios › abrir a la persona › Enviar correo de invitación**. Ella elige su clave
y después entra por `/master` (correo y clave, y el código de Google Authenticator). Si el correo no está en
**Cloudflare Access › Política «Equipo D'CASA»**, la puerta no la deja pasar: agrégalo también ahí
([SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) §8).

## Repetir es seguro

* Quien **ya tiene usuario** (activo o archivado, por su acceso o por el correo de su contacto) **no se toca**: ni sus
  grupos, ni su nombre, ni su ficha. Si le faltaba la ficha de empleado, se le crea.
* Los **roles no se vuelven a aplicar**: si a alguien le quitaste Gerencia a mano, repetir el alta no se la devuelve.
* Para cambiar el rol de alguien ya creado: Ajustes › Usuarios (selector «D'CASA»).

## Quién puede

* La pantalla es de quien administra accesos (`base.group_erp_manager`); se comprueba en el servidor, no solo en el menú.
* El rol **Administrador** exige además ser administrador de Ajustes (`base.group_system`).
* Con 2FA obligatorio para administradores, la primera vez que entre cada administrador enrola su app de códigos.

## Notas

* No se crean permisos nuevos: los tres roles se arman con los grupos de siempre (`dcasa_base`).
* El ícono de **Empleados** se cambia desde este módulo (`hr.menu_hr_root`), igual que los demás íconos de la marca.
