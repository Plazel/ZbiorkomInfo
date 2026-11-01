// ZbiorkomInfo – pass-through for live departures and the guide's announcements (Cloudflare Worker, free plan).
//
// 1. Live data: the ZTM Gdańsk API and the GTFS-Realtime feeds of Warszawa, Łódź, Poznań, Kraków and Praga send no CORS
//    header, so a page on another site (e.g. GitHub Pages) cannot read them directly. ?url=… fetches one of the listed
//    hosts and adds the header; the feeds are passed through unchanged (the page reads them itself).
// 2. Announcements: /tts?v=<voice>&t=<text> returns the text spoken by a Microsoft Azure neural voice (MP3). Every text is
//    synthesised once and then kept in Cloudflare's cache for a year, so each stop name costs the Azure quota only once.
//    Azure's free tier (F0, 0.5 million characters a month) is never billed: past the limit it only stops answering
//    until the next month (the page then uses the device's own voice).
//
// Set up: dash.cloudflare.com → Workers & Pages → Create → Worker → paste this file → Deploy; then put the worker's
// address (https://….workers.dev) into RT_PROXY in index.html.
// For the voices: in the worker's Settings → Variables and Secrets add AZURE_KEY (type Secret: the key of an Azure
// "Speech service" resource, pricing tier Free F0) and AZURE_REGION (type Text: the resource's region, e.g. westeurope).
const ALLOWED = ['ckan2.multimediagdansk.pl', 'cdn.zbiorkom.live', 'www.ztm.poznan.pl', 'gtfs.ztp.krakow.pl', 'api.golemio.cz'];
const VOICES = { 'pl-PL-ZofiaNeural': 'pl-PL', 'pl-PL-MarekNeural': 'pl-PL', 'cs-CZ-VlastaNeural': 'cs-CZ', 'cs-CZ-AntoninNeural': 'cs-CZ',
  'sk-SK-ViktoriaNeural': 'sk-SK', 'sk-SK-LukasNeural': 'sk-SK', 'de-DE-SeraphinaMultilingualNeural': 'de-DE', 'de-DE-FlorianMultilingualNeural': 'de-DE',
  'en-GB-AdaMultilingualNeural': 'en-GB', 'en-GB-OllieMultilingualNeural': 'en-GB' };
const xml = s => s.replace(/[<>&'"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[c]));

async function tts(req, env, ctx, cors) {
  const u = new URL(req.url), voice = u.searchParams.get('v') || '', text = (u.searchParams.get('t') || '').trim();
  if (!VOICES[voice] || !text || text.length > 160) return new Response('bad request', { status: 400, headers: cors });
  if (!env.AZURE_KEY || !env.AZURE_REGION) return new Response('voice not set up', { status: 503, headers: cors });
  const key = new Request('https://tts.cache/' + encodeURIComponent(voice) + '/' + encodeURIComponent(text));
  const cache = caches.default;
  let res = await cache.match(key);
  if (!res) {
    const ssml = `<speak version="1.0" xml:lang="${VOICES[voice]}"><voice name="${voice}"><prosody rate="-5%">${xml(text)}</prosody></voice></speak>`;
    const r = await fetch(`https://${env.AZURE_REGION}.tts.speech.microsoft.com/cognitiveservices/v1`, {
      method: 'POST', body: ssml,
      headers: { 'Ocp-Apim-Subscription-Key': env.AZURE_KEY, 'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': 'audio-24khz-48kbitrate-mono-mp3', 'User-Agent': 'ZbiorkomInfo' } });
    if (!r.ok) return new Response('voice error ' + r.status, { status: 502, headers: cors });
    res = new Response(await r.arrayBuffer(), { headers: { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'public, max-age=31536000' } });
    ctx.waitUntil(cache.put(key, res.clone()));
  }
  const h = new Headers(res.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v);
  return new Response(res.body, { status: 200, headers: h });
}

export default {
  async fetch(req, env, ctx) {
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS' };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (new URL(req.url).pathname === '/tts') return tts(req, env, ctx, cors);
    const target = new URL(req.url).searchParams.get('url');
    let u; try { u = new URL(target); } catch (e) { return new Response('url?', { status: 400, headers: cors }); }
    if (u.protocol !== 'https:' || !ALLOWED.includes(u.hostname)) return new Response('host not allowed', { status: 403, headers: cors });
    const r = await fetch(u.toString(), { headers: { 'User-Agent': 'ZbiorkomInfo/1.0' }, cf: { cacheTtl: 15 } });
    const h = new Headers(r.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v); h.set('Cache-Control', 'max-age=15');
    return new Response(r.body, { status: r.status, headers: h });
  }
};
