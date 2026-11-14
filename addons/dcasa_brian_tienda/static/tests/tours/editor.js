/**
 * La trampa del lote 1: con el editor del sitio, un t-call metido por xpath en una plantilla de Odoo daba error 500.
 * Aquí la administradora abre el sitio en modo edición y la página (con la burbuja de Brian) carga entera.
 * Lo corre tests/test_navegador.py (TestConElEditor).
 */
import { registerWebsitePreviewTour } from "@website/js/tours/tour_utils";

registerWebsitePreviewTour("dcasa_brian_tienda_editor", { url: "/", edition: true }, () => [
    {
        content: "El editor abrió",
        trigger: ".o_builder_sidebar_open",
    },
    {
        content: "La página carga entera, con la burbuja de Brian",
        trigger: ":iframe #wrapwrap #o_dcasa_brian a.o_dcbt_burbuja[href]",
    },
    {
        content: "Y sin la burbuja de WhatsApp (la reemplaza)",
        trigger: ":iframe body:not(:has(.o_dcasa_wa_float))",
    },
]);
