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
// Set up: dash.cloudflare.com → Workers & Pages → Create → Worker → paste this file → Deploy; then put the worker's
// address (https://….workers.dev) into RT_PROXY in index.html.
// For the voices, Azure: in the worker's Settings → Variables and Secrets add AZURE_KEY (type Secret: the key of an Azure
// "Speech service" resource, pricing tier Free F0) and AZURE_REGION (type Text: the resource's region, e.g. westeurope).
const ALLOWED = ['ckan2.multimediagdansk.pl', 'cdn.zbiorkom.live', 'www.ztm.poznan.pl', 'gtfs.ztp.krakow.pl', 'api.golemio.cz'];
const VOICES = { 'pl-PL-ZofiaNeural': 'pl-PL', 'pl-PL-MarekNeural': 'pl-PL', 'cs-CZ-VlastaNeural': 'cs-CZ', 'cs-CZ-AntoninNeural': 'cs-CZ',
  'sk-SK-ViktoriaNeural': 'sk-SK', 'sk-SK-LukasNeural': 'sk-SK', 'de-DE-SeraphinaMultilingualNeural': 'de-DE', 'de-DE-FlorianMultilingualNeural': 'de-DE',
  'en-GB-AdaMultilingualNeural': 'en-GB', 'en-GB-OllieMultilingualNeural': 'en-GB' };
// stop names the voices say wrongly: their sounds (IPA)
const SAY = { Munketoft: { ipa: 'ˈmʊŋkəˌtɔft' } };
const SAY_RE = new RegExp('\\b(' + Object.keys(SAY).join('|') + ')\\b', 'g');
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
  SAY_RE.lastIndex = 0; const said = SAY_RE.test(text);   // (a text with such a name: kept apart in the cache, so a new way to say it is heard)
  const key = new Request('https://tts.cache/az2/' + (said ? 'say1/' : '') + encodeURIComponent(voice) + '/' + encodeURIComponent(text));
  const cache = caches.default;
  let res = await cache.match(key), err = '';
  const keep = (buf, by) => { const r = new Response(buf, { headers: { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'public, max-age=31536000', 'X-Voice-By': by } }); ctx.waitUntil(cache.put(key, r.clone())); return r; };
  // Microsoft Azure: the voice itself (the same neural voices as Microsoft Edge reads with), free tier F0; at 48 kHz, 96 kbit/s
  //    (at 24 kHz and 48 kbit/s it sounds muffled on a phone's speaker)
  if (!res) {
    const ssml = `<speak version="1.0" xml:lang="${VOICES[voice]}"><voice name="${voice}"><prosody rate="-5%">${xml(text).replace(SAY_RE, w => `<phoneme alphabet="ipa" ph="${SAY[w].ipa}">${w}</phoneme>`)}</prosody></voice></speak>`;
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

export default {
  async fetch(req, env, ctx) {
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS' };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (new URL(req.url).pathname === '/tts') return tts(req, env, ctx, cors);
    if (new URL(req.url).pathname === '/byd') return byd(req, cors);
    if (new URL(req.url).pathname === '/alerts') return alerts(cors);
    const target = new URL(req.url).searchParams.get('url');
    let u; try { u = new URL(target); } catch (e) { return new Response('url?', { status: 400, headers: cors }); }
    if (u.protocol !== 'https:' || !ALLOWED.includes(u.hostname)) return new Response('host not allowed', { status: 403, headers: cors });
    const r = await fetch(u.toString(), { headers: { 'User-Agent': 'ZbiorkomInfo/1.0' }, cf: { cacheTtl: 15 } });
    const h = new Headers(r.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v); h.set('Cache-Control', 'max-age=15');
    return new Response(r.body, { status: r.status, headers: h });
  }
};
