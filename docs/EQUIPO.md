# Equipo (`dcasa_equipo`)

Lo que toca a las personas del equipo (Empleados) y no es de nómina ni de ventas.

> **Los datos de las personas viven solo en Odoo.** Ni nombres ni correos del equipo se guardan en el repositorio
> (una prueba vigila que no entren correos reales al módulo).

## Qué hace hoy

* El menú **Empleados** deja el ícono a colores de Odoo por uno azul D'CASA con trazo blanco (`hr.menu_hr_root`),
  igual que los demás íconos de la marca.

## Lo que se retiró (2026-10-11)

Hubo una pantalla **Empleados › Alta del equipo** (se pegaba una lista de texto y creaba usuario, ficha de empleado,
departamento y rol sin mandar invitaciones). La dueña pidió **quitarla**: las personas no se crean pegando texto. El
código, el menú y los permisos se borraron, y la migración `19.0.2.0.0` elimina las dos tablas temporales que dejaba.
Las personas que ya se habían creado con ella **siguen en Odoo, intactas** (son usuarios y empleados normales).

La dueña dejará un **esquema de ejemplo** de cómo debe organizarse el equipo; cuando llegue se construye sobre eso.

## Cuidado al crear usuarios a mano

En Odoo, guardar un usuario nuevo **que tenga correo manda solo la invitación** para elegir clave (también la importación
normal). Si se quiere crear a alguien sin que le llegue nada todavía, hay que preverlo (por ejemplo, dejando el correo
para el final) o usar el esquema que se defina. Quien entra por `/master` necesita además estar en Cloudflare Access
(política «Equipo D'CASA», [SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) §8).

## Jerarquía del equipo en Odoo (cómo se arma)

Odoo tiene dos niveles, y conviene llenar los dos:

1. **Departamentos** (Empleados › Departamentos): cada uno tiene **Departamento superior** y **Gerente**. Al poner el
   gerente de un departamento, Odoo **asigna ese gerente (y coach) a quien esté en el departamento y no tenga gerente**.
   Por eso se empieza por los departamentos y luego se corrige a mano a quien tenga otro jefe.
2. **Ficha de cada empleado** (campo **Gerente**): es lo que dibuja el **Organigrama** (el ícono de tres nodos en
   Empleados). Cada persona tiene un solo gerente. El campo **Coach** no cambia el organigrama.
