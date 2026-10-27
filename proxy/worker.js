// ZbiorkomInfo – pass-through for live departures (Cloudflare Worker, free plan).
// The ZTM Gdańsk API sends no CORS header, so a page on another site (e.g. GitHub Pages) cannot read it directly.
// This worker fetches it and adds the header. Only the listed hosts are passed through.
// Set up: dash.cloudflare.com → Workers & Pages → Create → Worker → paste this file → Deploy;
// then put the worker's address (https://….workers.dev) into RT_PROXY in index.html.
const ALLOWED = ['ckan2.multimediagdansk.pl'];
export default {
  async fetch(req) {
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS' };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    const target = new URL(req.url).searchParams.get('url');
    let u; try { u = new URL(target); } catch (e) { return new Response('url?', { status: 400, headers: cors }); }
    if (u.protocol !== 'https:' || !ALLOWED.includes(u.hostname)) return new Response('host not allowed', { status: 403, headers: cors });
    const r = await fetch(u.toString(), { headers: { 'User-Agent': 'ZbiorkomInfo/1.0' }, cf: { cacheTtl: 15 } });
    const h = new Headers(r.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v); h.set('Cache-Control', 'max-age=15');
    return new Response(r.body, { status: r.status, headers: h });
  }
};
