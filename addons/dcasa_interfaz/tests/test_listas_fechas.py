"""Las columnas de fecha con hora de las listas se leen enteras en la computadora.

Salió en la auditoría visual del 2026-11-11: con la barra lateral angosta (como nace), «Fecha de creación» de las
cotizaciones mostraba «11 nov,…» y la hora no se veía; pasaba en todas las listas con fecha y hora.

La causa: Odoo mide cuánto ocupa una fecha colgando un bloque invisible del ``<body>``, y el ``<body>`` de D'CASA es una
rejilla (barra + contenido). El bloque caía en la columna de la barra (68 px), el texto se partía en renglones y medía
de menos. ``barra_lateral.scss`` hace que lo que no es de la rejilla ocupe el ancho entero, y ``listas.js`` deja la
columna en lo que mide una fecha de este año (sin apretar a las de al lado)."""
from odoo.tests import HttpCase, tagged

from .test_inicio_por_rol import ESPERAR_JS, VentasMixin


@tagged('post_install', '-at_install')
class TestFechasEnLasListas(VentasMixin, HttpCase):

    def test_la_fecha_con_hora_se_lee_entera_con_la_barra_angosta(self):
        self.pedido(vendedor=self.vendedora, confirmar=False)
        codigo = '(async () => {' + ESPERAR_JS + r"""
            const celda = 'td[name="create_date"]';
            await esperar(() => document.querySelector('.o_list_view .o_data_row ' + celda), 'la lista con su fecha');
            // La barra nace angosta: es justo el caso en que la medida salía mal.
            if (!document.body.classList.contains('o_dcasa_barra_colapsada')) {
                throw new Error('la barra lateral debía estar angosta: ' + document.body.className);
            }
            // Lo que se cuelga del <body> para medir ocupa el ancho entero, no la columna de la barra.
            const sonda = document.createElement('div');
            sonda.className = 'invisible';
            sonda.textContent = 'x';
            document.body.append(sonda);
            const ancho = sonda.getBoundingClientRect().width;
            sonda.remove();
            if (ancho < window.innerWidth - 2) {
                throw new Error(`el bloque de medir quedó en ${ancho}px (la ventana mide ${window.innerWidth}px)`);
            }
            // Ya dibujada la tabla con sus anchos, ninguna fecha queda cortada y trae su hora.
            await esperar(() => document.querySelector('.o_list_table').style.tableLayout === 'fixed', 'los anchos');
            const celdas = [...document.querySelectorAll('.o_list_view .o_data_row ' + celda)];
            for (const td of celdas) {
                const texto = td.textContent.trim();
                if (td.scrollWidth > td.clientWidth + 1) {
                    throw new Error(`fecha cortada: «${texto}» cabe ${td.clientWidth}px de ${td.scrollWidth}px`);
                }
                if (!/\d{1,2}:\d{2}/.test(texto)) { throw new Error('la fecha debía traer la hora: ' + texto); }
            }
            // Arreglar la fecha no puede cortar otra cosa: las etiquetas de la fila (origen, estado) se leen enteras.
            for (const etiqueta of document.querySelectorAll('.o_list_view .o_data_row .badge')) {
                if (etiqueta.scrollWidth > etiqueta.clientWidth + 1) {
                    throw new Error('etiqueta cortada: «' + etiqueta.textContent.trim() + '»');
                }
            }
            if (!document.querySelector('.o_list_view .o_data_row td[name="dcasa_origen"] .badge')) {
                throw new Error('la fila debía traer la etiqueta de origen');
            }
            // Y no se queda con el hueco del peor caso de Odoo (año y segundos) habiendo columnas que lo necesitan.
            const columna = document.querySelector('.o_list_table thead th[data-name="create_date"]');
            const texto = celdas[0].firstElementChild || celdas[0];
            const sobra = columna.getBoundingClientRect().width - texto.scrollWidth;
            if (sobra > 90) { throw new Error(`a la columna de la fecha le sobran ${Math.round(sobra)}px`); }
            console.log('test successful');
        })();"""
        self.browser_size = '1366x768'
        self.browser_js('/odoo/action-sale.action_quotations_with_onboarding', codigo, login='gerencia_rol',
                        timeout=120)
