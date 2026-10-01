// Servidor de medición (sin dependencias). Simula lo que hace el borde de Cloudflare
// con el contenido: compresión Brotli/gzip de los tipos de texto y Cache-Control.
//   node servir.js proxy  <puerto> <origen>   -> reenvía a Odoo y comprime (línea base justa)
//   node servir.js static <puerto> <carpeta>  -> sirve el prototipo estático (como Static Assets)
const http = require('http'), zlib = require('zlib'), fs = require('fs'), path = require('path');
const [mode, port, target] = process.argv.slice(2);
const TEXT = /text\/|javascript|json|xml|svg|font\/ttf|application\/ld/;
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript',
  '.json': 'application/json', '.webp': 'image/webp', '.avif': 'image/avif', '.jpg': 'image/jpeg',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ico': 'image/x-icon', '.txt': 'text/plain' };
function send(req, res, status, headers, body) {
  const type = headers['content-type'] || '';
  const ae = req.headers['accept-encoding'] || '';
  if (TEXT.test(type) && body.length > 512) {
    delete headers['content-length'];
    if (/\bbr\b/.test(ae)) { body = zlib.brotliCompressSync(body, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 } }); headers['content-encoding'] = 'br'; }
    else if (/gzip/.test(ae)) { body = zlib.gzipSync(body); headers['content-encoding'] = 'gzip'; }
    headers['vary'] = 'Accept-Encoding';
  }
  headers['content-length'] = body.length;
  res.writeHead(status, headers); res.end(body);
}
if (mode === 'proxy') {
  const t = new URL(target);
  http.createServer((req, res) => {
    const h = { ...req.headers, host: t.host }; delete h['accept-encoding'];
    const up = http.request({ host: t.hostname, port: t.port, path: req.url, method: req.method, headers: h }, (r) => {
      const chunks = []; r.on('data', c => chunks.push(c)); r.on('end', () => {
        const headers = {}; for (const [k, v] of Object.entries(r.headers)) headers[k] = v;
        delete headers['transfer-encoding'];
        send(req, res, r.statusCode, headers, Buffer.concat(chunks));
      });
    });
    up.on('error', e => { res.writeHead(502); res.end(String(e)); });
    req.pipe(up);
  }).listen(+port, () => console.log(`proxy :${port} -> ${target}`));
} else {
  const root = path.resolve(target);
  http.createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    let f = path.join(root, p);
    if (!f.startsWith(root)) { res.writeHead(403); return res.end(); }
    if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, 'index.html');
    else if (!fs.existsSync(f) && fs.existsSync(f + '.html')) f = f + '.html';
    if (!fs.existsSync(f)) { f = path.join(root, '404.html'); if (!fs.existsSync(f)) { res.writeHead(404); return res.end('404'); } }
    const ext = path.extname(f);
    const immutable = /\/(img|fonts|assets)\//.test(f);
    send(req, res, 200, { 'content-type': TYPES[ext] || 'application/octet-stream',
      'cache-control': immutable ? 'public, max-age=31536000, immutable' : 'public, max-age=0, must-revalidate' }, fs.readFileSync(f));
  }).listen(+port, () => console.log(`static :${port} -> ${root}`));
}
