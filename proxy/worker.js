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
//    its text from its own page (JSON: [{title, url, text}]), and after them the section "Zmiany na trasach" ({…, info: true,
//    date, lines}), kept 2 minutes.
//
// 5. Accounts (only for people given one): /konto … with the header "Authorization: Bearer <token>". Each account has a long
//    random token instead of a password; the page keeps it on the device. Only the token's SHA-256 is stored, so the
//    store holds nothing that lets anyone in. Logging in (POST /konto/login with the code) gives a session id; the page keeps only the
//    session, never the code (POST /konto/logout ends it; a new code or a deleted account ends all its sessions). Every administrator
//    sees and manages only the accounts they made themselves (own) – also the main administrator (ADMIN_TOKEN) only theirs and the
//    accounts made before this split. Kept in a KV namespace bound as KONTA:
//      t:<sha256 of token> → account id     u:<id> → {id, name, role, created}     d:<id> → the account's data (JSON)
//    GET /konto → {id, name, role, emp, grant, mk}; GET /konto/tm/pliki – pliki NetworkMakera; GET/PUT/DELETE /konto/tm?f=<plik> – jeden plik (najwyżej 20 MB, do 50 plików); GET /konto/dane → its data; PUT /konto/dane (JSON, at most 200 kB) saves it.
//    Administration with ADMIN_TOKEN (a secret; it also logs in as the administrator):
//      GET /admin/konta → the accounts; POST /admin/konta {name, role: "user"|"driver"|"admin"} → {id, token} (the token shown once);
//      POST /admin/konta/<id>/token → a new token (the old one stops working); GET /admin/konta/<id>/token → the token in use
//        (kept encrypted with ADMIN_TOKEN; null for accounts made earlier); DELETE /admin/konta/<id> → the account removed.
//      GET /konto/konfig (anyone) → {comp, ok}: the components each role may use, the approved proposals.
//      PUT /admin/ustawienia {voice, lang, gong, en, msgs, l2, perm, comp, ok, no} → mKomputer's settings for every driver (null: the driver's
//        own choice; en: stations, the ferry terminal and the airport also named in English; msgs: the special announcements,
//        each [pl, en, de, sk, cs]; l2: their second language; perm: what the drivers may do {ann, spec, mic, free});
//      POST /konto/status (mKomputer: on a trip / a break / off) · GET /admin/statusy (the administrator's table)
//      PUT /admin/konta/<id> (the profile: name, role, first and last name, phone, e-mail, note); POST …/token {token} (own code)
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
const NATIVE24 = { 'pl-PL-ZofiaNeural': 1 };
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
    // the section "Zmiany na trasach" below it: changes announced (a route, a stop moved, a new timetable) – shown on the
    // page as information (blue), each with the lines named at the start of its heading ("Linie 124, N1, N2, N6: …")
    const sec = (home.match(/<h2>\s*Zmiany na trasach\s*<\/h2>([\s\S]*?)(?:<div class="grid-item-|Więcej komunikatów)/) || ['', ''])[1];
    const info = [...sec.matchAll(/<div class="date">([^<]*)<\/div>[\s\S]*?<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?<div class="summary">([\s\S]*?)<\/div>/g)]
      .map(m => ({ title: strip(m[3]), url: m[2], date: strip(m[1]), sum: strip(m[4]), info: true })).filter(x => x.title && !items.some(y => y.title === x.title)).slice(0, 8);
    const linesOf = t => { const m = t.match(/^Lini[ae]\s+([^:]+):/); return m ? m[1].split(/\s*,\s*|\s+i\s+|\s+oraz\s+/).map(x => x.trim()).filter(x => /^[A-Z]?\d{1,3}[A-Z]?$|^[A-Z]\d*$/.test(x)) : []; };
    out = await Promise.all(items.concat(info).map(async x => {
      let text = '';
      if (/^https:\/\/ztm\.gda\.pl\//.test(x.url)) { try { const a = await get(x.url); const c = (a.match(/class="article-content[^"]*">([\s\S]*?)<div class="row">/) || ['', ''])[1]; text = strip(c).slice(0, 2000); } catch (e) {} }
      const o = { title: x.title, url: x.url, text: text || x.sum || '' };
      if (x.info) { o.info = true; o.date = x.date; const l = linesOf(x.title); if (l.length) o.lines = l; }
      return o;
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
  // (Zofia: in her own 24 kHz, at a higher bit rate – raised to 48 kHz she was heard crackling now and then; her recordings kept apart)
  const fmt = NATIVE24[voice] ? 'audio-24khz-160kbitrate-mono-mp3' : 'audio-48khz-96kbitrate-mono-mp3';
  const key = new Request('https://tts.cache/' + (NATIVE24[voice] ? 'az3' : 'az2') + '/' + (rate !== '-5%' ? 'r' + encodeURIComponent(rate) + '/' : '') + (said ? 'say/' + encodeURIComponent(said) + '/' : '') + encodeURIComponent(voice) + '/' + encodeURIComponent(text));
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
          'X-Microsoft-OutputFormat': fmt, 'User-Agent': 'ZbiorkomInfo' } });
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
// sesja: po zalogowaniu kodem strona dostaje losowy identyfikator sesji i trzyma tylko jego – kodu logowania w przeglądarce nie ma.
// W KV tylko skrót sesji: s:<sha256> → {id, at}; ss:<id> → lista skrótów sesji konta (nowy kod lub usunięcie konta kończą wszystkie)
const SESS_TTL = 180 * 86400;
const ADMIN0 = { id: 'admin', name: 'Administrator', role: 'admin' };
// pliki NetworkMakera konta: klucz pliku i spis (dla kont sprzed spisu – sam dawny projekt jako plik „0”)
const tmKey = (id, f) => (!f || f === '0') ? 'tm:' + id : 'tm:' + id + ':' + f;
async function tmList(env, id) {
  const L = await env.KONTA.get('tmf:' + id, 'json'); if (Array.isArray(L)) return L;
  const v = await env.KONTA.get('tm:' + id); if (!v) return [];
  let t = 0; try { t = JSON.parse(v).t || 0; } catch (e) {}
  return [{ f: '0', name: 'Projekt', t, size: v.length }];
}
// wszystkie pliki konta {f: zawartość} (eksport, przeniesienie) i ich usunięcie
async function tmAll(env, id) { const o = {}; for (const x of await tmList(env, id)) { const v = await env.KONTA.get(tmKey(id, x.f)); if (v) o[x.f] = v; } return o; }
async function tmDelAll(env, id) { for (const x of await tmList(env, id)) await env.KONTA.delete(tmKey(id, x.f)); await Promise.all([env.KONTA.delete('tm:' + id), env.KONTA.delete('tmf:' + id)]); }
async function sessNew(env, id) { const sid = newTok(40), sh = await sha(sid);
  await env.KONTA.put('s:' + sh, JSON.stringify({ id, at: new Date().toISOString() }), { expirationTtl: SESS_TTL });
  const L = ((await env.KONTA.get('ss:' + id, 'json')) || []).filter(Boolean); L.unshift(sh); for (const x of L.splice(30)) await env.KONTA.delete('s:' + x);
  await env.KONTA.put('ss:' + id, JSON.stringify(L)); return sid; }
async function sessEndAll(env, id) { const L = (await env.KONTA.get('ss:' + id, 'json')) || []; await Promise.all([...L.map(x => env.KONTA.delete('s:' + x)), env.KONTA.delete('ss:' + id)]); }
async function who(req, env, viaCode) {
  const m = (req.headers.get('Authorization') || '').match(/^Bearer\s+([A-Za-z0-9_\-+/=]{8,200})$/);
  if (!m) return null;
  {const se = await env.KONTA.get('s:' + await sha(m[1]), 'json'); if (se && se.id) { if (viaCode) return null; if (se.id === 'admin') return env.ADMIN_TOKEN ? ADMIN0 : null; const a = await env.KONTA.get('u:' + se.id, 'json'); if (a) a._sid = m[1]; return a; }}
  if (env.ADMIN_TOKEN && same(m[1], env.ADMIN_TOKEN)) return ADMIN0;
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
// właściciel konta: administrator, który je utworzył (konta sprzed tego podziału – główny administrator)
const ownerOf = a => (a && a.own) || 'admin';
async function ownIds(env, oid) { const out = new Set(); let cur; do { const l = await env.KONTA.list({ prefix: 'u:', cursor: cur }); for (const k of l.keys) { const md = k.metadata || {}; let o = md.own; if (o === undefined) { const a = await env.KONTA.get(k.name, 'json'); o = ownerOf(a); } if ((o || 'admin') === oid) out.add(k.name.slice(2)); } cur = l.list_complete ? null : l.cursor; } while (cur); return out; }
async function konta(req, env, cors) {
  const h = new Headers(cors); h.set('Content-Type', 'application/json; charset=utf-8'); h.set('Cache-Control', 'no-store');
  const J = (o, st) => new Response(JSON.stringify(o), { status: st || 200, headers: h });
  if (!env.KONTA) return J({ error: 'accounts not set up' }, 503);
  const p = new URL(req.url).pathname.replace(/\/+$/, '');
  // logowanie kodem: wymiana na sesję (kod nie jest potem przechowywany w przeglądarce); wylogowanie kończy sesję
  if (p === '/konto/login' && req.method === 'POST') { const a = await who(req, env, true); if (!a) return J({ error: 'unauthorized' }, 401); return J({ session: await sessNew(env, a.id) }); }
  const u = await who(req, env);
  if (p === '/konto/logout' && req.method === 'POST') { const m2 = (req.headers.get('Authorization') || '').match(/^Bearer\s+(\S+)$/); if (m2) { const sh = await sha(m2[1]); if (await env.KONTA.get('s:' + sh)) { await env.KONTA.delete('s:' + sh); if (u) { const L = ((await env.KONTA.get('ss:' + u.id, 'json')) || []).filter(x => x !== sh); await env.KONTA.put('ss:' + u.id, JSON.stringify(L)); } } } return J({ ok: true }); }
  // the settings every visitor's page needs, logged in or not: which sections and options each role gets (comp), and the
  // proposals the administrator approved (ok: e.g. the transfer to replacement lines shown in a line's timetable)
  if (p === '/konto/konfig' && req.method === 'GET') { const c = (await env.KONTA.get('cfg:mk', 'json')) || {}; return J({ comp: c.comp || null, ok: c.ok || [] }); }
  if (!u) return J({ error: 'unauthorized' }, 401);
  // konto zawieszone przez swojego administratora: odpowiada tylko /konto (z susp: true – strona pokazuje komunikat), reszta odmawia
  if (u.susp && !(p === '/konto' && req.method === 'GET')) return J({ error: 'suspended' }, 423);
  if (u.susp) return J({ id: u.id, name: u.name, role: u.role, susp: true });
  // (with the administrator's settings for mKomputer: voice, language, gong – or null, the driver's own choice)
  // the account: its service number, and the sections or options given to it alone (ucomp; the whole list only for an administrator)
  if (p === '/konto' && req.method === 'GET') { const mk = (await env.KONTA.get('cfg:mk', 'json')) || null, grant = mk && mk.ucomp && Array.isArray(mk.ucomp[u.id]) ? mk.ucomp[u.id] : [];
    if (mk && u.role !== 'admin') delete mk.ucomp; else if (mk && mk.ucomp) { const own = await ownIds(env, u.id); for (const k of Object.keys(mk.ucomp)) if (!own.has(k)) delete mk.ucomp[k]; } return J({ id: u.id, name: u.name, role: u.role, emp: u.emp || null, grant, mk }); }
  // the administrator's messages: those for this account, newest first; fetching marks them delivered, opening read
  // ("every driver": the administrators too, who can use the drivers' mode)
  const forMe = x => x.to === '*' ? (u.role === 'driver' || u.role === 'admin') && (ownerOf(u) === (x.fid || 'admin') || u.id === (x.fid || 'admin')) : Array.isArray(x.to) && x.to.includes(u.id);
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
  // what the account is doing now (mKomputer): "run" (a trip: the line, the stops, the times, the place), "break" (a duty, no trip
  // now), "off"; kept 6 hours at most (a driver who just closed the page is not shown working for ever)
  if (p === '/konto/status' && req.method === 'POST') {
    if (u.role !== 'driver' && u.role !== 'admin') return J({ error: 'forbidden' }, 403);
    const t = await req.text(); if (t.length > 40000) return J({ error: 'too large' }, 413);
    let b; try { b = JSON.parse(t); } catch (e) { return J({ error: 'bad json' }, 400); }
    if (b.s === 'off') { await env.KONTA.delete('st:' + u.id); return J({ ok: true }); }
    b.at = new Date().toISOString(); b.s = b.s === 'run' ? 'run' : 'break';
    await env.KONTA.put('st:' + u.id, JSON.stringify(b), { expirationTtl: 6 * 3600 }); return J({ ok: true });
  }
  // NetworkMaker: pliki projektów konta (cała sieć, zapisywana z menu Plik). Spis w tmf:<id> ([{f, name, t, size}]); plik „0” to
  // dawny jedyny projekt (tm:<id>), pozostałe w tm:<id>:<f>. Bez ?f= – plik „0” (zgodność ze starszymi wersjami strony).
  if (p === '/konto/tm/pliki' && req.method === 'GET') return J({ files: await tmList(env, u.id) });
  if (p === '/konto/tm') {
    const f = new URL(req.url).searchParams.get('f') || '0'; if (!/^[a-z0-9]{1,16}$/.test(f)) return J({ error: 'bad file' }, 400);
    if (req.method === 'GET') return new Response((await env.KONTA.get(tmKey(u.id, f))) || '{}', { headers: h });
    if (req.method === 'PUT') {
      const t = await req.text(); if (t.length > 20000000) return J({ error: 'too large' }, 413);
      let o; try { o = JSON.parse(t); if (!o || typeof o !== 'object' || !o.net || typeof o.net !== 'object') throw 0; } catch (e) { return J({ error: 'bad json' }, 400); }
      const L = await tmList(env, u.id), e = L.find(x => x.f === f);
      if (!e && L.length >= 50) return J({ error: 'too many files' }, 409);
      await env.KONTA.put(tmKey(u.id, f), t);
      const name = String(o.name || (e && e.name) || 'Projekt').slice(0, 80), ent = { f, name, t: +o.t || Date.now(), size: t.length };
      if (e) Object.assign(e, ent); else L.push(ent);
      await env.KONTA.put('tmf:' + u.id, JSON.stringify(L)); return J({ ok: true, f });
    }
    if (req.method === 'DELETE') {
      const L = (await tmList(env, u.id)).filter(x => x.f !== f);
      await env.KONTA.delete(tmKey(u.id, f)); await env.KONTA.put('tmf:' + u.id, JSON.stringify(L)); return J({ ok: true });
    }
  }
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
    const mine_ = a => a && ownerOf(a) === u.id;
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
      // the components each role may use: {guest|user|driver: [the switched-off sections and options]}
      if ('comp' in b) { const o = {}; if (b.comp && typeof b.comp === 'object') for (const r of ['guest', 'user', 'driver']) o[r] = (Array.isArray(b.comp[r]) ? b.comp[r] : []).map(String).filter(k => /^[a-zA-Z.]{2,24}$/.test(k)).slice(0, 60); c.comp = o; }
      // approved proposals (ids of the proposals from data/propozycje.json, with what was approved): applied for everyone
      if ('ok' in b) c.ok = (Array.isArray(b.ok) ? b.ok : []).filter(x => x && typeof x === 'object' && typeof x.id === 'string' && x.id.length <= 80).slice(0, 300)
        .map(x => ({ id: x.id, at: typeof x.at === 'string' ? x.at.slice(0, 30) : new Date().toISOString(), d: x.d && typeof x.d === 'object' && JSON.stringify(x.d).length <= 4000 ? x.d : null }));
      // sections or options given to single accounts, whatever their group: {account id: [keys]}
      if ('ucomp' in b) { const own = await ownIds(env, u.id), o = {}; for (const [k, v] of Object.entries(c.ucomp || {})) if (!own.has(k)) o[k] = v; if (b.ucomp && typeof b.ucomp === 'object') for (const [id, L] of Object.entries(b.ucomp).slice(0, 300)) { if (!/^[A-Za-z0-9_-]{4,40}$/.test(id) || !Array.isArray(L) || !own.has(id)) continue; const k = L.map(String).filter(x => /^[a-zA-Z.]{2,24}$/.test(x)).slice(0, 60); if (k.length) o[id] = k; } c.ucomp = o; }
      if ('no' in b) c.no = (Array.isArray(b.no) ? b.no : []).map(String).filter(x => x.length <= 80).slice(0, 500);
      await env.KONTA.put('cfg:mk', JSON.stringify(c)); { const own = await ownIds(env, u.id), out = Object.assign({}, c); out.ucomp = Object.fromEntries(Object.entries(c.ucomp || {}).filter(([k]) => own.has(k))); return J(out); }
    }
    const myMsg = x => (x.fid || 'admin') === u.id;
    if (p === '/admin/komunikaty' && req.method === 'GET') return J(((await env.KONTA.get('msg:list', 'json')) || []).filter(myMsg));
    if (p === '/admin/komunikat' && req.method === 'POST') {
      let b; try { b = await req.json(); } catch (e) { return J({ error: 'bad json' }, 400); }
      const text = String(b.text || '').trim().slice(0, 500); if (!text) return J({ error: 'text' }, 400);
      const to = b.to === '*' ? '*' : Array.isArray(b.to) ? [...new Set(b.to.filter(x => typeof x === 'string' && /^[a-z0-9]{3,32}$/.test(x)))].slice(0, 200) : null;
      if (!to || (Array.isArray(to) && !to.length)) return J({ error: 'to' }, 400);
      if (Array.isArray(to)) { const own = await ownIds(env, u.id); if (to.some(x => !own.has(x))) return J({ error: 'to' }, 403); }
      const L = (await env.KONTA.get('msg:list', 'json')) || []; L.unshift({ id: newTok(8), t: new Date().toISOString(), text, from: u.name, fid: u.id, to, ack: !!b.ack, st: {} }); L.splice(300);
      await env.KONTA.put('msg:list', JSON.stringify(L)); return J(L.filter(myMsg));
    }
    {const mm = p.match(/^\/admin\/komunikat(?:\/([a-z0-9]{6,16}))?$/);
    if (mm && req.method === 'DELETE') { const L = ((await env.KONTA.get('msg:list', 'json')) || []).filter(x => !(myMsg(x) && (!mm[1] || x.id === mm[1]))); await env.KONTA.put('msg:list', JSON.stringify(L)); return J(L.filter(myMsg)); }}
    if (p === '/admin/statusy' && req.method === 'GET') {
      const keys = []; let cur;
      do { const l = await env.KONTA.list({ prefix: 'st:', cursor: cur }); keys.push(...l.keys); cur = l.list_complete ? null : l.cursor; } while (cur);
      const own = await ownIds(env, u.id); own.add(u.id);
      const out = {}; await Promise.all(keys.filter(k => own.has(k.name.slice(3))).map(async k => { const v = await env.KONTA.get(k.name, 'json'); if (v) out[k.name.slice(3)] = v; })); return J(out);
    }
    // import kont wyeksportowanych wcześniej (np. przy usuwaniu administratora): wracają pod tego administratora
    if (p === '/admin/import' && req.method === 'POST') {
      const t = await req.text(); if (t.length > 25000000) return J({ error: 'too large' }, 413);
      let X; try { X = JSON.parse(t); } catch (e) { return J({ error: 'bad json' }, 400); }
      if (!X || X.app !== 'zbiorkominfo-konta' || !Array.isArray(X.accounts)) return J({ error: 'format' }, 400);
      const ids = new Set(X.accounts.map(a => a && a.id)), done = [], skip = [];
      for (const a of X.accounts) {
        if (!a || !/^[a-z0-9]{8,32}$/.test(a.id || '') || !ROLES.includes(a.role)) continue;
        if (await env.KONTA.get('u:' + a.id)) { skip.push(a.id); continue; }
        if (!ids.has(a.own) || a.id === X.root) a.own = u.id;   // (najwyższe konto eksportu – i każde bez opiekuna w pliku – trafia do importującego)
        if (a.th && await env.KONTA.get('t:' + a.th)) { delete a.th; delete a.tk; }   // (kod zajęty przez inne konto: trzeba nadać nowy)
        await env.KONTA.put('u:' + a.id, JSON.stringify(a), { metadata: { name: a.name, role: a.role, created: a.created, emp: a.emp || null, fn: (a.fn || '').slice(0, 60), ln: (a.ln || '').slice(0, 60), own: a.own } });
        if (a.th) await env.KONTA.put('t:' + a.th, a.id);
        const D = (X.data || {})[a.id] || {}; if (typeof D.d === 'string') await env.KONTA.put('d:' + a.id, D.d); if (typeof D.tm === 'string') await env.KONTA.put('tm:' + a.id, D.tm);
        if (D.tmx && typeof D.tmx === 'object' && Array.isArray(D.tmf)) { for (const [f, v] of Object.entries(D.tmx)) if (/^[a-z0-9]{1,16}$/.test(f) && typeof v === 'string') await env.KONTA.put(tmKey(a.id, f), v); await env.KONTA.put('tmf:' + a.id, JSON.stringify(D.tmf)); }
        done.push(a.id);
      }
      if (Array.isArray(X.msgs) && X.msgs.length) { const L = (await env.KONTA.get('msg:list', 'json')) || [], have = new Set(L.map(x => x.id)); for (const x of X.msgs) if (x && x.id && !have.has(x.id) && done.includes(x.fid)) L.push(x); L.sort((a, b) => (b.t || '').localeCompare(a.t || '')); L.splice(300); await env.KONTA.put('msg:list', JSON.stringify(L)); }
      return J({ ok: true, imported: done.length, skipped: skip });
    }
    const m = p.match(/^\/admin\/konta(?:\/([a-z0-9]{8,32})(\/token|\/eksport|\/przenies)?)?$/); if (!m) return J({ error: 'not found' }, 404);
    // (the account's list entry carries its name, role and date as the key's metadata: the list needs no read per account)
    const putU = a => env.KONTA.put('u:' + a.id, JSON.stringify(a), { metadata: { name: a.name, role: a.role, created: a.created, emp: a.emp || null, fn: (a.fn || '').slice(0, 60), ln: (a.ln || '').slice(0, 60), own: ownerOf(a) } });
    const nextEmp = async () => { const n = (+(await env.KONTA.get('cnt:emp')) || 1000) + 1; await env.KONTA.put('cnt:emp', String(n)); return n; };
    const PROF = ['fn', 'ln', 'phone', 'email', 'note'];
    const pub = a => ({ id: a.id, name: a.name, role: a.role, created: a.created, emp: a.emp || null, fn: a.fn || '', ln: a.ln || '', phone: a.phone || '', email: a.email || '', note: a.note || '', susp: !!a.susp });
    const newToken = async a => { const t = newTok(), th = await sha(t), old = a.th; a.th = th; a.tk = await tokSeal(env, t);
      await Promise.all([env.KONTA.put('t:' + th, a.id), putU(a), old ? env.KONTA.delete('t:' + old) : null, sessEndAll(env, a.id)]); return t; };
    if (!m[1] && req.method === 'GET') {
      const keys = []; let cur;
      do { const l = await env.KONTA.list({ prefix: 'u:', cursor: cur }); keys.push(...l.keys); cur = l.list_complete ? null : l.cursor; } while (cur);
      // (the whole record for each account: the profile's fields; accounts from before the numbers get theirs now, in the order made)
      const all = (await Promise.all(keys.map(k => env.KONTA.get(k.name, 'json')))).filter(Boolean).sort((a, b) => (a.created || '').localeCompare(b.created || ''));
      for (const a of all) if (!a.emp) { a.emp = await nextEmp(); await putU(a); }
      return J(all.filter(mine_).map(pub));
    }
    if (!m[1] && req.method === 'POST') {
      let b; try { b = await req.json(); } catch (e) { return J({ error: 'bad json' }, 400); }
      const name = String(b.name || '').trim().slice(0, 60), role = ROLES.includes(b.role) ? b.role : 'user';
      if (!name) return J({ error: 'name' }, 400);
      const id = newTok(10), a = { id, name, role, created: new Date().toISOString(), emp: await nextEmp(), own: u.id };
      for (const k of PROF) if (b[k]) a[k] = String(b[k]).trim().slice(0, k === 'note' ? 500 : 80);
      const token = await newToken(a);
      return J(Object.assign(pub(a), { token }));
    }
    const a = m[1] && await env.KONTA.get('u:' + m[1], 'json'); if (!a || !mine_(a)) return J({ error: 'not found' }, 404);   // (konto innego administratora: jakby go nie było)
    // wszystkie konta pod administratorem: jego własne i – rekurencyjnie – konta jego administratorów
    const tree = async root => { const out = [], seen = new Set([root]); const q = [root]; while (q.length) { const o = q.shift(); for (const id of await ownIds(env, o)) { if (seen.has(id)) continue; seen.add(id); const x = await env.KONTA.get('u:' + id, 'json'); if (!x) continue; out.push(x); if (x.role === 'admin') q.push(id); } } return out; };
    // eksport administratora z jego kontami i ich danymi (do ponownego wczytania przez POST /admin/import)
    if (m[2] === '/eksport' && req.method === 'GET') {
      const accs = [a, ...await tree(a.id)], data = {};
      for (const x of accs) { const [d, tmf, tmx] = await Promise.all([env.KONTA.get('d:' + x.id), tmList(env, x.id), tmAll(env, x.id)]); if (d || tmf.length) data[x.id] = Object.assign({}, d ? { d } : {}, tmf.length ? { tmf, tmx } : {}); }
      const fids = new Set(accs.map(x => x.id)), msgs = ((await env.KONTA.get('msg:list', 'json')) || []).filter(x => fids.has(x.fid));
      return J({ app: 'zbiorkominfo-konta', v: 1, at: new Date().toISOString(), root: a.id, accounts: accs, data, msgs });
    }
    // konta i dane administratora przekazane innemu administratorowi (sobie albo administratorowi, którego się utworzyło)
    if (m[2] === '/przenies' && req.method === 'POST') {
      if (a.role !== 'admin') return J({ error: 'not admin' }, 400);
      let b = {}; try { b = await req.json(); } catch (e) {}
      const to = String(b.to || ''); if (!to || to === a.id) return J({ error: 'to' }, 400);
      if (to !== u.id) { const t = await env.KONTA.get('u:' + to, 'json'); if (!t || !mine_(t) || t.role !== 'admin') return J({ error: 'to' }, 403); }
      const own = await ownIds(env, a.id); let n = 0;
      for (const id of own) { const x = await env.KONTA.get('u:' + id, 'json'); if (!x) continue; x.own = to; await putU(x); n++; }
      const L = (await env.KONTA.get('msg:list', 'json')) || []; let ch = false; for (const x of L) if (x.fid === a.id) { x.fid = to; ch = true; } if (ch) await env.KONTA.put('msg:list', JSON.stringify(L));
      // (projekt NetworkMakera i dane konta przenoszonego administratora – tylko jeśli docelowy nie ma własnych)
      { const v = await env.KONTA.get('d:' + a.id); if (v && !(await env.KONTA.get('d:' + to))) await env.KONTA.put('d:' + to, v); }
      // (pliki NetworkMakera dopisywane do plików docelowego administratora pod nowymi identyfikatorami)
      { const src = await tmList(env, a.id), dst = await tmList(env, to);
        for (const x of src) { const v = await env.KONTA.get(tmKey(a.id, x.f)); if (!v || dst.length >= 50) continue; let f; do f = Math.random().toString(36).slice(2, 10); while (dst.some(y => y.f === f));
          await env.KONTA.put(tmKey(to, f), v); dst.push(Object.assign({}, x, { f, name: x.name + ' (' + (a.name || a.id) + ')' })); }
        if (src.length) await env.KONTA.put('tmf:' + to, JSON.stringify(dst)); }
      return J({ ok: true, moved: n });
    }
    // a new token: drawn, or the administrator's own code ({token}: 8–40 letters and digits, not in use by another account);
    // the profile and the data stay
    if (m[2] && req.method === 'POST') {
      let b = {}; try { b = await req.json(); } catch (e) {}
      if (b && b.token) {
        const t = String(b.token).trim(); if (!/^[A-Za-z0-9]{8,40}$/.test(t)) return J({ error: 'format' }, 400);
        const th = await sha(t), other = await env.KONTA.get('t:' + th); if (other && other !== a.id) return J({ error: 'taken' }, 409);
        if (env.ADMIN_TOKEN && same(t, env.ADMIN_TOKEN)) return J({ error: 'taken' }, 409);
        const old = a.th; a.th = th; a.tk = await tokSeal(env, t); await Promise.all([env.KONTA.put('t:' + th, a.id), putU(a), old && old !== th ? env.KONTA.delete('t:' + old) : null, sessEndAll(env, a.id)]);
        return J({ id: a.id, token: t });
      }
      return J({ id: a.id, token: await newToken(a) });
    }
    // the profile changed: the name shown, the role, first and last name, phone, e-mail, note
    if (!m[2] && req.method === 'PUT') {
      let b; try { b = await req.json(); } catch (e) { return J({ error: 'bad json' }, 400); }
      if ('name' in b) { const n = String(b.name || '').trim().slice(0, 60); if (n) a.name = n; }
      if ('role' in b && ROLES.includes(b.role)) a.role = b.role;
      if ('susp' in b) { if (b.susp) a.susp = true; else delete a.susp; }
      for (const k of PROF) if (k in b) a[k] = String(b[k] || '').trim().slice(0, k === 'note' ? 500 : 80);
      await putU(a); return J(pub(a));
    }
    // the token now in use, for the administrator (null: made before tokens were kept – a new one is needed)
    if (m[2] && req.method === 'GET') return J({ id: a.id, token: await tokOpen(env, a.tk) });
    if (!m[2] && req.method === 'DELETE') {
      // (administrator z własnymi kontami: najpierw trzeba je usunąć – inaczej zostałyby bez opiekuna albo przeszły do kogoś innego)
      // (?wszystko=1: razem ze wszystkimi kontami pod nim i ich danymi; bez tego administrator z kontami nie jest usuwany)
      if (a.role === 'admin' && (await ownIds(env, a.id)).size) {
        if (new URL(req.url).searchParams.get('wszystko') !== '1') return J({ error: 'has accounts' }, 409);
        for (const x of await tree(a.id)) { await sessEndAll(env, x.id); await Promise.all([x.th ? env.KONTA.delete('t:' + x.th) : null, env.KONTA.delete('u:' + x.id), env.KONTA.delete('d:' + x.id), tmDelAll(env, x.id), env.KONTA.delete('st:' + x.id)]); }
        const L = (await env.KONTA.get('msg:list', 'json')) || []; await env.KONTA.put('msg:list', JSON.stringify(L.filter(x => x.fid !== a.id)));
      }
      await sessEndAll(env, a.id); await Promise.all([a.th ? env.KONTA.delete('t:' + a.th) : null, env.KONTA.delete('u:' + a.id), env.KONTA.delete('d:' + a.id), tmDelAll(env, a.id), env.KONTA.delete('st:' + a.id)]); return J({ ok: true }); }
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
