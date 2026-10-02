import { describe, expect, it } from "vitest";

import { esAssetCacheable, esAssetVersionado } from "../src/routing";
import { assetsDe, esAssetGuardable, MAX_ASSETS_POR_PAGINA, metaDeAsset, RETOCAR_TRAS_MS, TTL_ASSET_S } from "../src/tienda/assets";
import { TTL_PAGINA_S } from "../src/tienda/paginas";

const ORIGEN = new URL("https://dcasapty.com/shop");

describe("qué assets referencia una página de Odoo (sin DOM)", () => {
  it("estilos y JS (src y data-src del cargador perezoso) son críticos; precargas, logo y LCP no; lo perezoso y lo ajeno se ignora", () => {
    const html = `<!DOCTYPE html><html><head>
      <link rel="canonical" href="https://dcasapty.com/shop"/>
      <link rel="alternate" type="application/rss+xml" href="/blog/feed"/>
      <link rel="preconnect" href="https://fonts.gstatic.com/"/>
      <link rel="preload" href="/website_dcasa/static/src/fonts/anton-latin.woff2" as="font" type="font/woff2" crossorigin=""/>
      <link rel="preload" as="image" fetchpriority="high" href="/website_dcasa/static/src/img/hero.webp"
            imagesrcset="/website_dcasa/static/src/img/hero-800.webp 800w, /website_dcasa/static/src/img/hero.webp 1400w" imagesizes="100vw"/>
      <link rel="icon" href="/web/image/website/1/favicon?unique=1a2b3c"/>
      <link type="text/css" rel="stylesheet" href="/web/assets/8f3a1c2/web.assets_frontend.min.css" data-asset-bundle="web.assets_frontend" data-asset-version="8f3a1c2"/>
      <link rel="stylesheet" href="https://cdn.ajena.example/estilos.css"/>
      <script type="text/javascript" src="/web/assets/0b1c2d3/web.assets_frontend_minimal.min.js" onerror="__odooAssetError=1"></script>
      <script type="text/javascript" data-src="/web/assets/4e5f6a7/web.assets_frontend_lazy.min.js" defer="defer"></script>
      <script type="application/ld+json">{"@type":"Store"}</script>
      <script src='/web/assets/9f8e7d6/web.assets_frontend_extra.min.js' async></script>
      </head><body>
      <img src="/website_dcasa/static/src/img/logo-200.webp" srcset="/website_dcasa/static/src/img/logo-200.webp 1x, /website_dcasa/static/src/img/logo-400.webp 2x" loading="eager" alt="D'CASA"/>
      <picture><source type="image/webp" srcset="/dcasa/img/product.template/5/image_1920/256.webp?v=0123456789ab 256w, /dcasa/img/product.template/5/image_1920/512.webp?v=0123456789ab 512w" sizes="50vw"/>
        <img src="/web/image/product.template/5/image_512?unique=abc&amp;x=1" loading="eager" fetchpriority="high" decoding="async"/></picture>
      <picture><source type="image/webp" srcset="/dcasa/img/product.template/6/image_1920/256.webp?v=0123456789ab 256w"/>
        <img src="/web/image/product.template/6/image_512?unique=def" loading="lazy" decoding="async"/></picture>
      <img src="/web/image/product.template/7/image_512?unique=ghi" loading="lazy"/>
      <img src="https://fotos.ajenas.example/x.webp" loading="eager"/>
      </body></html>`;
    const { criticos, otros } = assetsDe(html, ORIGEN);
    expect(criticos).toEqual([
      "/web/assets/8f3a1c2/web.assets_frontend.min.css",
      "/web/assets/0b1c2d3/web.assets_frontend_minimal.min.js",
      "/web/assets/4e5f6a7/web.assets_frontend_lazy.min.js",
      "/web/assets/9f8e7d6/web.assets_frontend_extra.min.js",
    ]);
    expect(otros).toEqual([
      "/website_dcasa/static/src/fonts/anton-latin.woff2",
      "/website_dcasa/static/src/img/hero.webp",
      "/website_dcasa/static/src/img/hero-800.webp",
      "/web/image/website/1/favicon?unique=1a2b3c",
      "/website_dcasa/static/src/img/logo-200.webp",
      "/website_dcasa/static/src/img/logo-400.webp",
      "/web/image/product.template/5/image_512?unique=abc&x=1", // &amp; decodificado
      "/dcasa/img/product.template/5/image_1920/256.webp?v=0123456789ab",
      "/dcasa/img/product.template/5/image_1920/512.webp?v=0123456789ab",
    ]);
  });

  it("URLs absolutas del mismo origen cuentan; las de otro host, no; sin assets, listas vacías", () => {
    const html =
      `<link rel="stylesheet" href="https://dcasapty.com/web/assets/1234567/a.min.css">` +
      `<link rel="stylesheet" href="https://staging.dcasapty.com/web/assets/1234567/a.min.css">` +
      `<script src="/socios/algo.js"></script>`; // ruta que el borde no guarda
    expect(assetsDe(html, ORIGEN)).toEqual({ criticos: ["/web/assets/1234567/a.min.css"], otros: [] });
    expect(assetsDe("<html><body>hola</body></html>", ORIGEN)).toEqual({ criticos: [], otros: [] });
  });

  it("los no críticos se acotan (una página con cien fotos «eager» no dispara cien peticiones)", () => {
    const imgs = Array.from({ length: 100 }, (_, i) => `<img src="/web/image/product.template/${i}/image_512?unique=u${i}" loading="eager">`).join("");
    expect(assetsDe(imgs, ORIGEN).otros).toHaveLength(MAX_ASSETS_POR_PAGINA);
  });
});

describe("assets con versión en la URL (inmutables) frente a estáticos sin versión", () => {
  it("con versión: bundles de Odoo, /web/image e /web/content con unique, /dcasa/img con v", () => {
    for (const ruta of [
      "/web/assets/8f3a1c2/web.assets_frontend.min.css",
      "/web/assets/1/8f3a1c2/web.assets_frontend.min.css", // con el id del sitio (módulo website)
      "/web/assets/8f3a1c2/web.assets_frontend_lazy.min.js",
      "/web/image/123-abcdef12/logo.png",
      "/web/image/123-abcdef12",
      "/web/image/website/1/favicon?unique=1a2b3c",
      "/web/image/product.template/5/image_512?x=1&unique=abc",
      "/web/content/12-abc/google-font-anton.css?unique=abc",
      "/dcasa/img/product.template/5/image_1920/512.webp?v=0123456789ab",
    ]) {
      expect(esAssetVersionado(ruta), ruta).toBe(true);
      expect(esAssetCacheable(ruta), ruta).toBe(true);
    }
  });

  it("sin versión: estáticos de los módulos, bundles debug/any, imágenes sin unique", () => {
    for (const ruta of [
      "/website_dcasa/static/src/fonts/anton-latin.woff2",
      "/website_dcasa/static/src/img/logo-200.webp",
      "/web/static/img/placeholder.png",
      "/web/assets/debug/web.assets_frontend.css",
      "/web/assets/1/debug/web.assets_frontend.css",
      "/web/assets/any/web.assets_frontend.min.css",
      "/web/image/product.template/5/image_512",
      "/web/image/website/1/favicon?unique=",
      "/dcasa/img/product.template/5/image_1920/512.webp",
      "/shop",
    ]) {
      expect(esAssetVersionado(ruta), ruta).toBe(false);
    }
  });

  it("un asset vive más que cualquier página que lo referencie", () => {
    expect(TTL_ASSET_S).toBeGreaterThan(TTL_PAGINA_S);
    expect(RETOCAR_TRAS_MS + (TTL_PAGINA_S + 24 * 60 * 60) * 1000).toBeLessThanOrEqual(TTL_ASSET_S * 1000);
  });
});

describe("qué respuestas de Odoo se guardan como asset", () => {
  const con = (headers: Record<string, string>, status = 200) => new Response("x", { status, headers });

  it("200 público sin cookies; nunca private, no-store, no-cache, Set-Cookie, Vary: Cookie, parcial o no-200", () => {
    expect(esAssetGuardable(con({ "Cache-Control": "public, max-age=31536000, immutable" }))).toBe(true);
    expect(esAssetGuardable(con({ "Cache-Control": "public, max-age=604800" }))).toBe(true);
    const rechazadas: Record<string, string>[] = [
      { "Cache-Control": "private, max-age=31536000" },
      { "Cache-Control": "public, no-cache" },
      { "Cache-Control": "no-store" },
      { "Cache-Control": "max-age=31536000" },
      { "Cache-Control": "public, max-age=1", "Set-Cookie": "session_id=x" },
      { "Cache-Control": "public, max-age=1", Vary: "Cookie" },
      { "Cache-Control": "public, max-age=1", "Content-Range": "bytes 0-1/2" },
      { "Cache-Control": "public, max-age=1", "Content-Length": String(30 * 1024 * 1024) },
    ];
    for (const headers of rechazadas) {
      expect(esAssetGuardable(con(headers)), JSON.stringify(headers)).toBe(false);
    }
    expect(esAssetGuardable(con({ "Cache-Control": "public, max-age=1" }, 404))).toBe(false);
    expect(esAssetGuardable(con({ "Cache-Control": "public, max-age=1" }, 302))).toBe(false);
  });

  it("los metadatos guardan las cabeceras de Odoo y caben en los 1024 bytes de KV", () => {
    const meta = metaDeAsset(
      new Headers({
        "Content-Type": "font/woff2",
        "Cache-Control": "public, max-age=604800",
        ETag: '"1700000000-20000-123"',
        "Last-Modified": "Thu, 01 Oct 2026 10:00:00 GMT",
        "Content-Disposition": `inline; filename=${"a".repeat(1200)}.woff2`,
        "Content-Security-Policy": "default-src 'none'",
        "Set-Cookie": "nunca",
        "Content-Length": "20000",
      }),
      1_700_000_000_000,
    );
    expect(meta).toMatchObject({ t: "1700000000000", ct: "font/woff2", cc: "public, max-age=604800", csp: "default-src 'none'" });
    expect(meta).not.toHaveProperty("cd");
    expect(JSON.stringify(meta).length).toBeLessThan(1024);
    expect(Object.values(meta).join()).not.toContain("nunca");
  });
});
