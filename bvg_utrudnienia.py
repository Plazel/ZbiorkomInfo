#!/usr/bin/env python3
"""BVG's disruption notices (www.bvg.de/de/verbindungen/stoerungsmeldungen: U-Bahn, tram, bus, ferry) for Berlin, taken from
the data that page shows (disruption-reports-service, a few pages of 50 notices), as the user asked. Only traffic notices (not
lifts) in force now or within the next two weeks. Written as data/alerts_ber.json:
[{"id", "lines": ["M17", …], "title", "text" (German, plain, one item per line), "start", "end"}]; the page translates the
recurring phrases itself. build.py calls fetch(); with no answer the old file stays.
Usage: python3 bvg_utrudnienia.py [data folder]"""
import datetime, html, json, os, re, sys, urllib.request

URL = 'https://www.bvg.de/disruption-reports-service/disruptions/v1/de?page=%d'
PAGE = 'https://www.bvg.de/de/verbindungen/stoerungsmeldungen'


def plain(h):
    """BVG's HTML with its own tags (line signs, arrows, labels) as plain text: one paragraph or list item per line"""
    h = re.sub(r"<bds-signet-line\b.*?line-id='([^']+)'.*?</bds-signet-line>", r' \1 ', h, flags=re.S)   # (its as='<span>' holds a ">")
    h = re.sub(r"<bds-icon[^>]*icon-name='bds-arrow-triangle-expand-solid'[^>]*>\s*(</bds-icon>)?", ' ↔ ', h)
    h = re.sub(r"<bds-icon[^>]*icon-name='bds-moon-line'[^>]*>\s*(</bds-icon>)?", '(nachts) ', h)
    h = re.sub(r"<bds-signet-transport[^>]*transport-id='(\w+)'[^>]*>\s*</bds-signet-transport>", lambda m: {'bus': ' Bus ', 'tram': ' Tram ', 'subway': ' U-Bahn ', 'ferry': ' Fähre '}.get(m.group(1), ' '), h)
    h = re.sub(r'<bds-tag[^>]*>(.*?)</bds-tag>', r'[\1]', h, flags=re.S)
    h = re.sub(r'(?is)<a\b[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', lambda m: '[%s](%s)' % (re.sub(r'<[^>]+>', '', m.group(2)).strip(), m.group(1)), h)
    h = re.sub(r'(?is)<(strong|b)\b[^>]*>(.*?)</\1>', lambda m: (lambda t: ' **%s** ' % t.strip() if t.strip() else ' ')(re.sub(r'<[^>]+>', '', m.group(2))), h)   # (bold and links kept: **…**, [text](url))
    h = re.sub(r'<li[^>]*>', '\n• ', h); h = re.sub(r'</p>|<br\s*/?>|</li>|</ul>', '\n', h)
    h = re.sub(r'<[^>]+>', '', h); h = html.unescape(h)
    lines = [re.sub(r'\s+([.,;:)])', r'\1', re.sub(r'\*\*\s*\*\*', ' ', re.sub(r'\s+', ' ', x))).replace('( ', '(').strip() for x in h.split('\n')]
    lines = [re.sub(r'\b(Tram|Bus|U-Bahn)\s+\1\b', r'\1', x) for x in lines]
    return '\n'.join(x for x in lines if x)


def fetch(out, log=print):
    els = []; page = 1
    while page <= 20:
        req = urllib.request.Request(URL % page, headers={'User-Agent': 'Mozilla/5.0 (ZbiorkomInfo; rozklady-trojmiasto)', 'Accept': 'application/json'})
        j = json.load(urllib.request.urlopen(req, timeout=60))
        els += j.get('elements') or []
        if page >= (j.get('numPages') or 1): break
        page += 1
    now = datetime.datetime.now(datetime.timezone.utc); soon = now + datetime.timedelta(days=14)
    dt = lambda s: datetime.datetime.fromisoformat(s) if s else None
    res = []
    for e in els:
        if e.get('messageType') != 'TRAFFIC': continue
        a, b = dt(e.get('startDate')), dt(e.get('endDate'))
        if (b and b < now) or (a and a > soon): continue
        lines = list(dict.fromkeys(x['name'] for l in e.get('lines') or [] for v in l.values() for x in v))
        body = '\n'.join(plain(c.get('content') or '') for c in e.get('content') or [])
        title = next((c.get('headline') for c in e.get('content') or [] if c.get('headline')), '') or (e.get('disruptionTypes') or [{}])[0].get('displayName', '')
        res.append({'id': e['id'], 'lines': lines, 'title': html.unescape(title or ''), 'text': body, 'start': e.get('startDate'), 'end': e.get('endDate'),
                    'station': (e.get('stationOne') or {}).get('displayName', ''),
                    # the stretch and the kind, as BVG heads its notice ("21 Holteistr. ↔ Marktstr. · Unterbrechung"), and its map
                    'stretch': ' ↔ '.join(x for x in ((e.get('stationOne') or {}).get('displayName', ''), (e.get('stationTwo') or {}).get('displayName', '')) if x),
                    'kind': ', '.join(t.get('displayName', '') for t in e.get('disruptionTypes') or [] if t.get('displayName')),
                    'img': [{'url': 'https://www.bvg.de' + (i.get('rawImage') or {}).get('link', ''), 'alt': i.get('subText') or ((i.get('rawImage') or {}).get('metadata') or {}).get('alt', '')}
                            for i in e.get('images') or [] if (i.get('rawImage') or {}).get('link')]})
    f = os.path.join(out, 'alerts_ber.json')
    try: same = json.load(open(f, encoding='utf-8')).get('alerts') == res
    except Exception: same = False
    if not same:   # (unchanged notices: the file left as it was, so that the hourly run commits nothing)
        json.dump({'t': now.strftime('%Y-%m-%dT%H:%MZ'), 'url': PAGE, 'alerts': res}, open(f, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    log('BVG: %d komunikatów o utrudnieniach (%d stron)' % (len(res), page))


if __name__ == '__main__':
    fetch(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
