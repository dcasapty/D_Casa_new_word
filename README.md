# D'CASA Panamá — ERP + sitio web (Odoo 19 en Cloudflare)

Plataforma única de **D'CASA Panamá** (mueblería en La Chorrera): facturación,
inventario, ventas, compras, CRM, clientes, **sitio web con tienda** y **programa
de puntos y referidos (Socios D'CASA)**, todo sobre el código abierto de **Odoo 19 Community**, con el
código fuente en este repositorio y desplegado en **Cloudflare**.

> Por qué: la tienda dependía de un programador externo y no tenía el código
> fuente. Aquí está todo: Odoo como submódulo (`vendor/odoo`) y las
> personalizaciones de D'CASA como módulos propios (`addons/`). Nunca se toca el
> código de Odoo; se extiende.

## Qué hay

| Carpeta | Qué es |
|---|---|
| `vendor/odoo` | Código fuente de Odoo 19.0 (submódulo git, fijado a un commit). |
| `addons/dcasa_base` | Empresa, Panamá (ITBMS 7 %, plan contable), RUC con DV, USD, apps del ERP. |
| `addons/dcasa_invoice` | Formato de factura D'CASA: marca, RUC+DV, sello **PAGADO**, monto en letras. |
| `addons/dcasa_socios` | Socios D'CASA: puntos automáticos al pagarse la factura, referidos, premios, canjes, cumpleaños y app del socio (celular + PIN) en `/socios`. Reglas de [DCasa-Referidos](https://github.com/abrinay1997-stack/DCasa-Referidos). |
| `addons/website_dcasa` | Sitio web y tienda con la marca, editable desde el constructor de Odoo. |
| `addons/dcasa_interfaz` | La cara de Odoo por dentro: «Inicio» con el tablero del día, íconos propios, sin avisos de Enterprise (salen como «En desarrollo»), sin recorrido guiado, OdooBot ni datos de ejemplo. |
| `addons/dcasa_contabilidad` | Contabilidad a medida: estado de resultados, balance general, balance de comprobación, libro mayor, ITBMS y analítica (Excel y PDF); conciliación bancaria con importación de extractos CSV; presupuestos; cheques. Ver [docs/CONTABILIDAD.md](docs/CONTABILIDAD.md). |
| `addons/dcasa_catalogo` | Catálogo real (199 productos, 323 fotos) del Excel y la carpeta `up media`: el mismo producto en inventario, ventas y tienda web. Ver [docs/CATALOGO.md](docs/CATALOGO.md). |
| `edge/` | Cloudflare Worker + Container que sirve Odoo (caché, seguridad, cron). |
| `docker/` | Imagen de producción (Odoo + módulos) y su arranque. |
| `scripts/test.sh` | Instala los módulos en una base limpia y corre todos los tests. |
| `docs/` | [Plan](docs/PLAN.md) · [Arquitectura](docs/ARQUITECTURA.md) · [Despliegue](docs/DESPLIEGUE.md) · [Socios D'CASA](docs/SOCIOS.md) |

## Empezar (desarrollo local)

Opción A — todo en Docker:

```bash
git clone --recurse-submodules --shallow-submodules <este repo>
docker compose up --build          # http://localhost:8069  usuario admin / admin (solo local)
```

Opción B — Python local (más rápido para desarrollar):

```bash
make setup                         # submódulo + .venv con dependencias de Odoo
make init DB=dcasa                 # crea la base con los módulos y español
make run DB=dcasa                  # http://localhost:8069
make test                          # tests de todos los módulos (necesita PostgreSQL)
make edge-test                     # tests del Worker de Cloudflare
```

`scripts/test.sh` usa `DB_HOST/DB_USER/DB_PASSWORD` (por defecto `localhost/odoo/odoo`).

## Tests y despliegue

Cada push corre en GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

1. **Lint** (ruff + XML).
2. **Tests de Odoo**: instala los 6 módulos (164 tests) en PostgreSQL limpio y corre sus tests
   (la factura de prueba reproduce la factura real INV/2026/00821: $329,99 + ITBMS $23,10 = $353,09).
3. **Tests del borde**: typecheck + vitest del Worker.
4. **Prueba de humo de la imagen**: construye la imagen Docker, la arranca contra una
   base vacía y verifica que el sitio responde.
5. **Despliegue** a Cloudflare, solo en `main` y solo si todo lo anterior pasó.

Pasos para dejar Cloudflare listo: [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

## Previsualizar la página (link en línea desde GitHub Actions)

- **En un PR:** ponle la etiqueta **`preview`**. El workflow *Previsualización* construye
  la imagen real, carga datos de demostración y abre un túnel de Cloudflare por
  60 minutos. El link aparece en el **resumen de la ejecución** y en el log del paso
  «Abrir el túnel».
- **A mano (cuando el workflow ya esté en `main`):** *Actions → Previsualización → Run
  workflow*, eligiendo los minutos.

Accesos de la demo: `/socios` con celular `6555-1234` y PIN `482915`; backend
`/web/login` con usuario `admin` y la clave aleatoria que muestra el resumen. La base de
prueba se borra al terminar. Sin la etiqueta, en cada PR solo se guardan capturas
(artefacto **capturas-del-sitio**).

## Cómo se edita el sitio (sin programador)

En Odoo: **Sitio web → Editar**. Textos, imágenes, secciones, colores y fuentes se
cambian desde el editor visual. Los productos se publican desde **Inventario /
Ventas → Productos** (casilla *Publicado* y categoría de la tienda). El número de
WhatsApp de todos los botones está en **Sitio web → Configuración → Ajustes**.

## Capturas (base de demostración)

| Inicio | Inicio (móvil) | Ficha de producto |
|---|---|---|
| ![Inicio](docs/img/sitio-inicio.jpg) | ![Inicio móvil](docs/img/sitio-inicio-movil.jpg) | ![Producto](docs/img/sitio-producto.jpg) |

| Factura con puntos | App del socio (móvil) |
|---|---|
| ![Factura](docs/img/factura.jpg) | ![Socios](docs/img/socios-cuenta-movil.jpg) |

Diseño del sitio, mapa de calor, accesibilidad y SEO: [docs/REDISENO.md](docs/REDISENO.md).
Las fotos de ambiente son del tema Loftspace de Odoo (LGPL-3) hasta tener la sesión de fotos
propia; los productos «(demo)» solo existen en la base de previsualización.

> Las fuentes de marca (Anton/Oswald) se cargan desde Google Fonts en producción;
> en las capturas se ve la tipografía de respaldo.
