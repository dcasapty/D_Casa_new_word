/**
 * La imagen de la cámara del lector de códigos se pinta en un lienzo encima del video.
 *
 * En el iPhone de la dueña (Chrome en iOS, motor WebKit) el diálogo «Lector de códigos de barras» de Odoo lee los
 * códigos pero no muestra la imagen: salía en blanco y, con camara.scss, en negro (2026-10-19). El video sí recibe los
 * cuadros (el lector los copia de ahí a un lienzo para leer el código), pero ese motor no lo pinta en pantalla. Aquí se
 * hace lo mismo que el lector, a la vista: cada cuadro del video se copia a un lienzo del mismo tamaño y en el mismo
 * lugar, encima del video y debajo del recuadro. Donde el video sí se ve (Android, la compu), el lienzo muestra la
 * misma imagen. El video sigue en su sitio y visible para el navegador (si no, iOS podría pausarlo) y el lienzo no
 * recibe toques: el ícono para mover el recuadro sigue funcionando.
 */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { BarcodeVideoScanner } from "@web/core/barcode/barcode_video_scanner";

patch(BarcodeVideoScanner.prototype, {
    setup() {
        super.setup(...arguments);
        let cuadro = null;
        let lienzo = null;
        let pincel = null;
        const pintar = () => {
            cuadro = requestAnimationFrame(pintar);
            const video = this.videoPreviewRef.el;
            if (!video || !video.isConnected || video.readyState < 2 || !video.videoWidth) {
                return;
            }
            if (!lienzo) {
                lienzo = document.createElement("canvas");
                lienzo.className = "o_dcasa_camara_lienzo";
                lienzo.setAttribute("aria-hidden", "true");
                // Justo después del video: el recuadro y el ícono de Odoo van después y quedan encima.
                video.after(lienzo);
                pincel = lienzo.getContext("2d", { alpha: false });
            }
            if (lienzo.width !== video.videoWidth || lienzo.height !== video.videoHeight) {
                lienzo.width = video.videoWidth;
                lienzo.height = video.videoHeight;
            }
            const caja = {
                left: `${video.offsetLeft}px`,
                top: `${video.offsetTop}px`,
                width: `${video.offsetWidth}px`,
                height: `${video.offsetHeight}px`,
            };
            for (const [lado, valor] of Object.entries(caja)) {
                if (lienzo.style[lado] !== valor) {
                    lienzo.style[lado] = valor;
                }
            }
            pincel.drawImage(video, 0, 0, lienzo.width, lienzo.height);
        };
        onMounted(() => {
            cuadro = requestAnimationFrame(pintar);
        });
        onWillUnmount(() => {
            cancelAnimationFrame(cuadro);
            lienzo?.remove();
        });
    },
});
