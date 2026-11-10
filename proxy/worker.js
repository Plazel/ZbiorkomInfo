// ZbiorkomInfo – pass-through for live departures and the guide's announcements (Cloudflare Worker, free plan).
//
// 1. Live data: the ZTM Gdańsk API and the GTFS-Realtime feeds of Warszawa, Łódź, Poznań, Kraków and Praga send no CORS
//    header, so a page on another site (e.g. GitHub Pages) cannot read them directly. ?url=… fetches one of the listed
//    hosts and adds the header; the feeds are passed through unchanged (the page reads them itself).
// 2. Announcements: /tts?v=<voice>&t=<text> returns the text spoken (MP3). Every text is synthesised once and then kept in
//    Cloudflare's cache for a year, so each stop name costs the quota only once. The voices are Microsoft Azure's neural
//    voices (the voices Microsoft Edge reads with): AZURE_KEY and AZURE_REGION (the free tier F0 is never billed).
//    Where they do not answer (not set up, quota used up), the page uses the device's own voice.
//
// 3. Bydgoszcz: /byd?p=<stop number> returns the stop's live departures from ZDMiKP's passenger service (the boards at the
//    stops; odjazdy.zdmikp.bydgoszcz.pl, plain http and no CORS header), kept 15 seconds.
//
// 4. ZTM Gdańsk's notices of disruptions: /alerts returns the notices shown in the red "UWAGA" bar on ztm.gda.pl, each with
//    its text from its own page (JSON: [{title, url, text}]), kept 2 minutes.
//
// 5. Accounts (only for people given one): /konto … with the header "Authorization: Bearer <token>". Each account has a long
//    random token instead of a password; the page keeps it on the device. Only the token's SHA-256 is stored, so the
//    store holds nothing that lets anyone in. Kept in a KV namespace bound as KONTA:
//      t:<sha256 of token> → account id     u:<id> → {id, name, role, created}     d:<id> → the account's data (JSON)
//    GET /konto → {id, name, role}; GET /konto/dane → its data; PUT /konto/dane (JSON, at most 200 kB) saves it.
//    Administration with ADMIN_TOKEN (a secret; it also logs in as the administrator):
//      GET /admin/konta → the accounts; POST /admin/konta {name, role: "user"|"driver"|"admin"} → {id, token} (the token shown once);
//      POST /admin/konta/<id>/token → a new token (the old one stops working); GET /admin/konta/<id>/token → the token in use
//        (kept encrypted with ADMIN_TOKEN; null for accounts made earlier); DELETE /admin/konta/<id> → the account removed.
//      PUT /admin/ustawienia {voice, lang, gong, en, msgs, l2, perm} → mKomputer's settings for every driver (null: the driver's
//        own choice; en: stations, the ferry terminal and the airport also named in English; msgs: the special announcements,
//        each [pl, en, de, sk, cs]; l2: their second language; perm: what the drivers may do {ann, spec, mic, free});
//      Messages: POST /admin/komunikat {text, to: "*" (every driver) | [ids], ack} → sent; GET /admin/komunikaty → the last 100
//        with each recipient's status {d: delivered, r: read, c: confirmed}; DELETE /admin/komunikat[/<id>] → removed.
//        The driver: GET /konto/komunikaty → their messages (marked delivered); POST /konto/komunikaty/<id> {c} → read (confirmed).
//
// Set up: dash.cloudflare.com → Workers & Pages → Create → Worker → paste this file → Deploy; then put the worker's
// address (https://….workers.dev) into RT_PROXY in index.html.
// For the voices, Azure: in the worker's Settings → Variables and Secrets add AZURE_KEY (type Secret: the key of an Azure
// "Speech service" resource, pricing tier Free F0) and AZURE_REGION (type Text: the resource's region, e.g. westeurope).
// For the accounts: Storage & Databases → KV → Create namespace (e.g. zbiorkom-konta); in the worker's Settings → Bindings add
// a KV namespace binding named KONTA with it; in Variables and Secrets add ADMIN_TOKEN (type Secret: a long random text,
// at least 8 characters, e.g. 12 random letters and digits; it is your administrator's token).
const ALLOWED = ['ckan2.multimediagdansk.pl', 'cdn.zbiorkom.live', 'www.ztm.poznan.pl', 'gtfs.ztp.krakow.pl', 'api.golemio.cz'];
const VOICES = { 'pl-PL-ZofiaNeural': 'pl-PL', 'pl-PL-MarekNeural': 'pl-PL', 'cs-CZ-VlastaNeural': 'cs-CZ', 'cs-CZ-AntoninNeural': 'cs-CZ',
  'sk-SK-ViktoriaNeural': 'sk-SK', 'sk-SK-LukasNeural': 'sk-SK', 'de-DE-SeraphinaMultilingualNeural': 'de-DE', 'de-DE-FlorianMultilingualNeural': 'de-DE',
  'en-GB-AdaMultilingualNeural': 'en-GB', 'en-GB-OllieMultilingualNeural': 'en-GB' };
// stop names the voices say wrongly: their sounds (IPA), and each voice's speed (_tempo), from the site's own file
// data/wymowa.json (read again every 10 minutes, so a name or a speed is put right there, with no change here)
const SAY_URL = 'https://raw.githubusercontent.com/Plazel/ZbiorkomInfo/main/data/wymowa.json';
let SAY = { t: 0, map: {}, re: null, tempo: {} };
async function sayDict() {
  if (Date.now() - SAY.t < 600000) return SAY;
  try {
    const r = await fetch(SAY_URL, { cf: { cacheTtl: 600 } });
    if (r.ok) { const j = await r.json(); const map = {}; for (const [k, v] of Object.entries(j)) if (!k.startsWith('_') && typeof v === 'string' && v) map[k] = v.replace(/^[\[\/]|[\]\/]$/g, '');
      const ks = Object.keys(map).sort((a, b) => b.length - a.length).map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
      const tempo = {}; for (const [k, v] of Object.entries(j._tempo || {})) if (VOICES[k] && /^[+-]?\d{1,2}%$/.test(v)) tempo[k] = v;
      SAY = { t: Date.now(), map, tempo, re: ks.length ? new RegExp('(?<!\\p{L})(' + ks.join('|') + ')(?!\\p{L})', 'gu') : null }; }
    else SAY.t = Date.now() - 540000;   // (not to be had: tried again in a minute)
  } catch (e) { SAY.t = Date.now() - 540000; }
  return SAY;
}
const xml = s => s.replace(/[<>&'"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[c]));

async function byd(req, cors) {
  const p = new URL(req.url).searchParams.get('p') || '';
  if (!/^\d{1,6}$/.test(p)) return new Response('bad request', { status: 400, headers: cors });
  const r = await fetch('http://odjazdy.zdmikp.bydgoszcz.pl/PresenterService.asmx/GetLCDEntries', {
    method: 'POST', body: JSON.stringify({ iIdParada: +p, iIdLinea: 0 }),
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'ZbiorkomInfo/1.0' }, cf: { cacheTtl: 15 } });
  const h = new Headers(cors); h.set('Content-Type', 'application/json; charset=utf-8'); h.set('Cache-Control', 'max-age=15');
  return new Response(r.ok ? await r.text() : '{"d":null}', { status: r.ok ? 200 : 502, headers: h });
}

const ent = t => t.replace(/&nbsp;/g, ' ').replace(/&quot;/g, '"').replace(/&#0?39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n)).replace(/&amp;/g, '&');
const strip = h => ent(h.replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|li|h\d)>/gi, '\n').replace(/<li[^>]*>/gi, '• ').replace(/<[^>]+>/g, ''))
  .split('\n').map(x => x.replace(/[ \t]+/g, ' ').trim()).filter(Boolean).join('\n');
async function alerts(cors) {
  const h = new Headers(cors); h.set('Content-Type', 'application/json; charset=utf-8'); h.set('Cache-Control', 'max-age=120');
  const get = async u => { const r = await fetch(u, { headers: { 'User-Agent': 'ZbiorkomInfo/1.0' }, cf: { cacheTtl: 120 } }); return r.ok ? r.text() : ''; };
  let out = [];
  try {
    const home = await get('https://ztm.gda.pl/');
    const box = (home.match(/class="[^"]*danger-box[^"]*"[\s\S]*?<\/ul>/) || [''])[0];
    const items = [...box.matchAll(/<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)].map(m => ({ url: m[1], title: strip(m[2]) })).filter(x => x.title).slice(0, 6);
    out = await Promise.all(items.map(async x => {
      let text = '';
      if (/^https:\/\/ztm\.gda\.pl\//.test(x.url)) { try { const a = await get(x.url); const c = (a.match(/class="article-content[^"]*">([\s\S]*?)<div class="row">/) || ['', ''])[1]; text = strip(c).slice(0, 2000); } catch (e) {} }
      return { title: x.title, url: x.url, text };
    }));
  } catch (e) {}
  return new Response(JSON.stringify(out), { status: 200, headers: h });
}

async function tts(req, env, ctx, cors) {
  const u = new URL(req.url), voice = u.searchParams.get('v') || '', text = (u.searchParams.get('t') || '').trim();
  if (!VOICES[voice] || !text || text.length > 160) return new Response('bad request', { status: 400, headers: cors });
  if (!env.AZURE_KEY || !env.AZURE_REGION) return new Response('voice not set up', { status: 503, headers: cors });
  // (a text with such a name: its sounds are part of its place in the cache, so a name put right is heard at once)
  const D = await sayDict(); const said = D.re ? [...new Set(text.match(D.re) || [])].map(w => w + '=' + D.map[w]).join(',') : '';
  const rate = D.tempo[voice] || '-5%';
  const key = new Request('https://tts.cache/az2/' + (rate !== '-5%' ? 'r' + encodeURIComponent(rate) + '/' : '') + (said ? 'say/' + encodeURIComponent(said) + '/' : '') + encodeURIComponent(voice) + '/' + encodeURIComponent(text));
  const cache = caches.default;
  let res = await cache.match(key), err = '';
  const keep = (buf, by) => { const r = new Response(buf, { headers: { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'public, max-age=31536000', 'X-Voice-By': by } }); ctx.waitUntil(cache.put(key, r.clone())); return r; };
  // Microsoft Azure: the voice itself (the same neural voices as Microsoft Edge reads with), free tier F0; at 48 kHz, 96 kbit/s
  //    (at 24 kHz and 48 kbit/s it sounds muffled on a phone's speaker)
  if (!res) {
    const ssml = `<speak version="1.0" xml:lang="${VOICES[voice]}"><voice name="${voice}"><prosody rate="${rate}">${said ? xml(text).replace(D.re, w => `<phoneme alphabet="ipa" ph="${xml(D.map[w])}">${w}</phoneme>`) : xml(text)}</prosody></voice></speak>`;
    try {
      const r = await fetch(`https://${env.AZURE_REGION}.tts.speech.microsoft.com/cognitiveservices/v1`, {
        method: 'POST', body: ssml,
        headers: { 'Ocp-Apim-Subscription-Key': env.AZURE_KEY, 'Content-Type': 'application/ssml+xml',
          'X-Microsoft-OutputFormat': 'audio-48khz-96kbitrate-mono-mp3', 'User-Agent': 'ZbiorkomInfo' } });
      if (r.ok) res = keep(await r.arrayBuffer(), 'Microsoft Azure'); else err += 'azure: ' + r.status + ' ' + (await r.text()).slice(0, 200) + '; ';
    } catch (e) { err += 'azure: ' + e.message + '; '; }
  }
  if (!res) return new Response(err || 'voice error', { status: 502, headers: cors });
  const h = new Headers(res.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v); h.set('Access-Control-Expose-Headers', 'X-Voice-By');
  return new Response(res.body, { status: 200, headers: h });
}

// ---- accounts
const ROLES = ['user', 'driver', 'admin'];   // (an administrator may make other administrators)
const b64u = a => btoa(String.fromCharCode(...a)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
// a token: 12 characters of 31 that cannot be mistaken for each other (no 0/o, 1/l/i), about 59 bits – far beyond guessing
// through the worker; drawn evenly (bytes past the last whole multiple of 31 are drawn again)
const TOK_ABC = 'abcdefghjkmnpqrstuvwxyz23456789';
function newTok(n = 12) { let t = ''; while (t.length < n) for (const b of crypto.getRandomValues(new Uint8Array(n * 2))) { if (b < 248 && t.length < n) t += TOK_ABC[b % 31]; } return t; }
async function sha(t) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t)))].map(b => b.toString(16).padStart(2, '0')).join(''); }
function same(a, b) { if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false; let x = 0; for (let i = 0; i < a.length; i++) x |= a.charCodeAt(i) ^ b.charCodeAt(i); return x === 0; }
async function who(req, env) {
  const m = (req.headers.get('Authorization') || '').match(/^Bearer\s+([A-Za-z0-9_\-+/=]{8,200})$/);
  if (!m) return null;
  if (env.ADMIN_TOKEN && same(m[1], env.ADMIN_TOKEN)) return { id: 'admin', name: 'Administrator', role: 'admin' };
  const id = await env.KONTA.get('t:' + await sha(m[1]));
  if (!id) return null;
  return await env.KONTA.get('u:' + id, 'json');
}
// a token kept for the administrator's preview: encrypted (AES-GCM) with a key made from the ADMIN_TOKEN secret, so the
// stored data alone does not give it away (without ADMIN_TOKEN nothing is kept and there is no preview)
async function tokKey(env) { const raw = await crypto.subtle.digest('SHA-256', new TextEncoder().encode('konta-podglad:' + env.ADMIN_TOKEN)); return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']); }
const b64 = a => btoa(String.fromCharCode(...new Uint8Array(a))), unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
async function tokSeal(env, t) { if (!env.ADMIN_TOKEN) return null; const iv = crypto.getRandomValues(new Uint8Array(12)); return b64(iv) + '.' + b64(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await tokKey(env), new TextEncoder().encode(t))); }
async function tokOpen(env, x) { if (!env.ADMIN_TOKEN || !x) return null; try { const [iv, c] = x.split('.'); return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(iv) }, await tokKey(env), unb64(c))); } catch (e) { return null; } }
async function konta(req, env, cors) {
  const h = new Headers(cors); h.set('Content-Type', 'application/json; charset=utf-8'); h.set('Cache-Control', 'no-store');
  const J = (o, st) => new Response(JSON.stringify(o), { status: st || 200, headers: h });
  if (!env.KONTA) return J({ error: 'accounts not set up' }, 503);
  const p = new URL(req.url).pathname.replace(/\/+$/, ''), u = await who(req, env);
  if (!u) return J({ error: 'unauthorized' }, 401);
  // (with the administrator's settings for mKomputer: voice, language, gong – or null, the driver's own choice)
  if (p === '/konto' && req.method === 'GET') return J({ id: u.id, name: u.name, role: u.role, mk: await env.KONTA.get('cfg:mk', 'json') });
  // the administrator's messages: those for this account, newest first; fetching marks them delivered, opening read
  // ("every driver": the administrators too, who can use the drivers' mode)
  const forMe = x => x.to === '*' ? u.role === 'driver' || u.role === 'admin' : Array.isArray(x.to) && x.to.includes(u.id);
  const mine = x => { const s = (x.st || {})[u.id] || {}; return { id: x.id, t: x.t, text: x.text, from: x.from, ack: !!x.ack, r: s.r || null, c: s.c || null }; };
  if (p === '/konto/komunikaty' && req.method === 'GET') {
    const L = (await env.KONTA.get('msg:list', 'json')) || [], now = new Date().toISOString(); let ch = false;
    const out = L.filter(forMe).map(x => { x.st = x.st || {}; const s = x.st[u.id] = x.st[u.id] || {}; if (!s.d) { s.d = now; ch = true; } return mine(x); });
    if (ch) await env.KONTA.put('msg:list', JSON.stringify(L));
    return J(out);
  }
  {const mm = p.match(/^\/konto\/komunikaty\/([a-z0-9]{6,16})$/);
  if (mm && req.method === 'POST') {
    let b = {}; try { b = await req.json(); } catch (e) {}
    const L = (await env.KONTA.get('msg:list', 'json')) || [], x = L.find(x => x.id === mm[1]); if (!x || !forMe(x)) return J({ error: 'not found' }, 404);
    const now = new Date().toISOString(); x.st = x.st || {}; const s = x.st[u.id] = x.st[u.id] || {}; s.d = s.d || now; s.r = s.r || now; if (b.c) s.c = s.c || now;
    await env.KONTA.put('msg:list', JSON.stringify(L)); return J(mine(x));
  }}
  if (p === '/konto/dane') {
    if (req.method === 'GET') return new Response((await env.KONTA.get('d:' + u.id)) || '{}', { headers: h });
    if (req.method === 'PUT') {
      const t = await req.text(); if (t.length > 200000) return J({ error: 'too large' }, 413);
      try { const o = JSON.parse(t); if (!o || typeof o !== 'object' || Array.isArray(o)) throw 0; } catch (e) { return J({ error: 'bad json' }, 400); }
      await env.KONTA.put('d:' + u.id, t); return J({ ok: true });
    }
  }
  if (p.startsWith('/admin/')) {
    if (u.role !== 'admin') return J({ error: 'forbidden' }, 403);
    if (p === '/admin/ustawienia' && req.method === 'PUT') {
      let b; try { b = await req.json(); } catch (e) { return J({ error: 'bad json' }, 400); }
      // fields left out of the body keep their stored values
      const c = (await env.KONTA.get('cfg:mk', 'json')) || {};
      if ('voice' in b) c.voice = ['m', 'f'].includes(b.voice) ? b.voice : null;
      if ('lang' in b) c.lang = ['auto', 'pl', 'en', 'de', 'sk', 'cs'].includes(b.lang) ? b.lang : null;
      if ('gong' in b) c.gong = typeof b.gong === 'string' && /^[a-z]{2,8}$/.test(b.gong) ? b.gong : null;
      if ('en' in b) c.en = b.en === true;
      // special announcements: up to 30, each [pl, en, de, sk, cs] of at most 300 characters (null: the built-in set)
      if ('msgs' in b) c.msgs = Array.isArray(b.msgs) ? b.msgs.slice(0, 30).map(m => (Array.isArray(m) ? m : []).slice(0, 5).map(x => String(x || '').trim().slice(0, 300)))
        .map(m => { while (m.length < 5) m.push(''); return m; }).filter(m => m.some(Boolean)) : null;
      if ('l2' in b) c.l2 = ['pl', 'en', 'de', 'sk', 'cs'].includes(b.l2) ? b.l2 : null;
      // what the drivers may do: change the announcements' settings, use the special announcements, the microphone, trips without a duty
      if ('perm' in b && b.perm && typeof b.perm === 'object') { c.perm = c.perm || {}; for (const k of ['ann', 'spec', 'mic', 'free']) if (k in b.perm) c.perm[k] = b.perm[k] !== false; }
      await env.KONTA.put('cfg:mk', JSON.stringify(c)); return J(c);
    }
    if (p === '/admin/komunikaty' && req.method === 'GET') return J((await env.KONTA.get('msg:list', 'json')) || []);
    if (p === '/admin/komunikat' && req.method === 'POST') {
      let b; try { b = await req.json(); } catch (e) { return J({ error: 'bad json' }, 400); }
      const text = String(b.text || '').trim().slice(0, 500); if (!text) return J({ error: 'text' }, 400);
      const to = b.to === '*' ? '*' : Array.isArray(b.to) ? [...new Set(b.to.filter(x => typeof x === 'string' && /^[a-z0-9]{3,32}$/.test(x)))].slice(0, 200) : null;
      if (!to || (Array.isArray(to) && !to.length)) return J({ error: 'to' }, 400);
      const L = (await env.KONTA.get('msg:list', 'json')) || []; L.unshift({ id: newTok(8), t: new Date().toISOString(), text, from: u.name, to, ack: !!b.ack, st: {} }); L.splice(100);
      await env.KONTA.put('msg:list', JSON.stringify(L)); return J(L);
    }
    {const mm = p.match(/^\/admin\/komunikat(?:\/([a-z0-9]{6,16}))?$/);
    if (mm && req.method === 'DELETE') { const L = mm[1] ? ((await env.KONTA.get('msg:list', 'json')) || []).filter(x => x.id !== mm[1]) : []; await env.KONTA.put('msg:list', JSON.stringify(L)); return J(L); }}
    const m = p.match(/^\/admin\/konta(?:\/([a-z0-9]{8,32})(\/token)?)?$/); if (!m) return J({ error: 'not found' }, 404);
    // (the account's list entry carries its name, role and date as the key's metadata: the list needs no read per account)
    const putU = a => env.KONTA.put('u:' + a.id, JSON.stringify(a), { metadata: { name: a.name, role: a.role, created: a.created } });
    const newToken = async a => { const t = newTok(), th = await sha(t), old = a.th; a.th = th; a.tk = await tokSeal(env, t);
      await Promise.all([env.KONTA.put('t:' + th, a.id), putU(a), old ? env.KONTA.delete('t:' + old) : null]); return t; };
    if (!m[1] && req.method === 'GET') {
      const keys = []; let cur;
      do { const l = await env.KONTA.list({ prefix: 'u:', cursor: cur }); keys.push(...l.keys); cur = l.list_complete ? null : l.cursor; } while (cur);
      const out = await Promise.all(keys.map(async k => { const a = k.metadata && k.metadata.name ? k.metadata : await env.KONTA.get(k.name, 'json');
        return a ? { id: k.name.slice(2), name: a.name, role: a.role, created: a.created } : null; }));
      return J(out.filter(Boolean).sort((a, b) => (a.created || '').localeCompare(b.created || '')));
    }
    if (!m[1] && req.method === 'POST') {
      let b; try { b = await req.json(); } catch (e) { return J({ error: 'bad json' }, 400); }
      const name = String(b.name || '').trim().slice(0, 60), role = ROLES.includes(b.role) ? b.role : 'user';
      if (!name) return J({ error: 'name' }, 400);
      const id = newTok(10), a = { id, name, role, created: new Date().toISOString() };
      const token = await newToken(a);
      return J({ id, name, role, created: a.created, token });
    }
    const a = m[1] && await env.KONTA.get('u:' + m[1], 'json'); if (!a) return J({ error: 'not found' }, 404);
    if (m[2] && req.method === 'POST') return J({ id: a.id, token: await newToken(a) });
    // the token now in use, for the administrator (null: made before tokens were kept – a new one is needed)
    if (m[2] && req.method === 'GET') return J({ id: a.id, token: await tokOpen(env, a.tk) });
    if (!m[2] && req.method === 'DELETE') { await Promise.all([a.th ? env.KONTA.delete('t:' + a.th) : null, env.KONTA.delete('u:' + a.id), env.KONTA.delete('d:' + a.id)]); return J({ ok: true }); }
  }
  return J({ error: 'not found' }, 404);
}

export default {
  async fetch(req, env, ctx) {
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, PUT, POST, DELETE, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type', 'Access-Control-Max-Age': '86400' };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (new URL(req.url).pathname === '/tts') return tts(req, env, ctx, cors);
    if (new URL(req.url).pathname === '/byd') return byd(req, cors);
    if (new URL(req.url).pathname === '/alerts') return alerts(cors);
    if (/^\/(konto|admin)(\/|$)/.test(new URL(req.url).pathname)) return konta(req, env, cors);
    const target = new URL(req.url).searchParams.get('url');
    let u; try { u = new URL(target); } catch (e) { return new Response('url?', { status: 400, headers: cors }); }
    if (u.protocol !== 'https:' || !ALLOWED.includes(u.hostname)) return new Response('host not allowed', { status: 403, headers: cors });
    const r = await fetch(u.toString(), { headers: { 'User-Agent': 'ZbiorkomInfo/1.0' }, cf: { cacheTtl: 15 } });
    const h = new Headers(r.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v); h.set('Cache-Control', 'max-age=15');
    return new Response(r.body, { status: r.status, headers: h });
  }
};
