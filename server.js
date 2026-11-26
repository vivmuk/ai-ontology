// ai-ontology viewer server — password gate + static assets.
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const PORT = process.env.PORT || 8080;
const APP_PASSWORD = process.env.APP_PASSWORD || 'vivek';
const SESSION_SECRET = process.env.SESSION_SECRET || 'ai-ontology-dev-secret';
const ROOT = __dirname;

// stateless token: HMAC(secret, password) — no session store needed
const TOKEN = crypto
  .createHmac('sha256', SESSION_SECRET)
  .update(APP_PASSWORD)
  .digest('hex');

function parseCookies(req) {
  const out = {};
  const raw = req.headers.cookie || '';
  for (const part of raw.split(';')) {
    const i = part.indexOf('=');
    if (i > -1) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = '';
    req.on('data', (c) => {
      data += c;
      if (data.length > 1e5) req.destroy();
    });
    req.on('end', () => {
      try { resolve(JSON.parse(data || '{}')); } catch { resolve({}); }
    });
  });
}

function send(res, code, body, type) {
  res.writeHead(code, {
    'Content-Type': type || 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const authed = parseCookies(req).aionto === TOKEN;

  if (url.pathname === '/api/login' && req.method === 'POST') {
    const { password } = await readBody(req);
    if (typeof password === 'string' && password.length <= 200 &&
        crypto.timingSafeEqual(
          Buffer.from(password.padEnd(200).slice(0, 200)),
          Buffer.from(APP_PASSWORD.padEnd(200).slice(0, 200))
        )) {
      res.writeHead(200, {
        'Content-Type': 'application/json; charset=utf-8',
        'Set-Cookie': `aionto=${TOKEN}; HttpOnly; Path=/; SameSite=Lax; Max-Age=2592000`,
        'Cache-Control': 'no-store',
      });
      return res.end('{"ok":true}');
    }
    return send(res, 401, '{"ok":false,"error":"wrong password"}');
  }

  if (url.pathname === '/api/ontology') {
    if (!authed) return send(res, 401, '{"error":"unauthorized"}');
    try {
      const body = fs.readFileSync(path.join(ROOT, 'ontology.json'));
      return send(res, 200, body);
    } catch {
      return send(res, 500, '{"error":"ontology.json missing — run verify.sh"}');
    }
  }

  // static: only index.html is served; everything else falls back to it
  try {
    const body = fs.readFileSync(path.join(ROOT, 'index.html'));
    return send(res, 200, body, 'text/html; charset=utf-8');
  } catch {
    return send(res, 500, 'index.html missing');
  }
});

server.listen(PORT, () => console.log(`ai-ontology listening on :${PORT}`));
