#!/usr/bin/env python3
"""Notices of changes and disruptions for the cities whose operators publish no GTFS-RT alerts, taken from their own public
pages and feeds (the build, hourly). Each city: data/alerts_<city>.json, as bvg_utrudnienia.py writes Berlin's:
{"t", "url", "alerts": [{"id", "lines", "title", "text" (plain, one paragraph a line, "• " items), "start", "end", "url"}]}.
Sources (all open, no key, nothing behind a check):
  prg – PID, RSS "Operativní mimořádnosti" and "Plánované výluky" (pid.cz/rss-kanal, CC BY 4.0): their lines and periods given;
        only notices touching Prague's own lines, in force now or within three days
  poz – ZTM Poznań, RSS of its notices (www.ztm.poznan.pl/feed/?post_type=komunikaty), the last two weeks'
  byd – ZDMiKP Bydgoszcz, RSS of "Aktualności komunikacyjne", the last two weeks'
  ns  – MPK Nowy Sącz, the notices its home page shows in its bar of notices (each read from its page)
  wej – MZK Wejherowo, "Wiadomości i komunikaty": the notices (komunikaty) of the last month
A source that does not answer leaves its old file. Usage: python3 utrudnienia_miast.py [data folder]"""
import datetime, email.utils, html, json, os, re, sys, urllib.request

UA = {'User-Agent': 'ZbiorkomInfo/1.0 (rozklady; github.com/Plazel/ZbiorkomInfo)'}
NOW = datetime.datetime.now(datetime.timezone.utc)
PL_MONTHS = ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia', 'września', 'października', 'listopada', 'grudnia']


def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read().decode('utf-8', 'replace')


def marks(h):
    """bold and links kept through the plain text: **bold**, [text](https://…) – the page draws them again"""
    h = re.sub(r'(?is)<a\b[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', lambda m: (lambda t: '[%s](%s)' % (t, m.group(1)) if t else '')(re.sub(r'<[^>]+>', '', m.group(2)).strip()), h)
    h = re.sub(r'(?is)<(strong|b)\b[^>]*>(.*?)</\1>', lambda m: (lambda t: ' **%s** ' % t.strip() if t.strip() else ' ')(re.sub(r'<[^>]+>', '', m.group(2))), h)
    return h


def plain(h):
    """HTML as plain text: a paragraph, heading or list item a line"""
    h = re.sub(r'(?is)<(script|style|table|img|figure)\b.*?(</\1>|/?>)', ' ', h)
    h = re.sub(r'(?i)<li[^>]*>', '\n• ', h); h = re.sub(r'(?i)</p>|<br\s*/?>|</li>|</h\d>|</div>|</tr>', '\n', h)
    h = marks(h)
    h = html.unescape(re.sub(r'<[^>]+>', '', h))
    L = [re.sub(r'\s+([.,;:)])', r'\1', re.sub(r'\*\*\s*\*\*', ' ', re.sub(r'[ \t\u00a0]+', ' ', x))).strip() for x in h.split('\n')]
    L = [x for x in L if x and x != '•' and not re.match(r'^(Artykuł .* pochodzi z serwisu|Przeczytaj więcej|Czytaj dalej)', x)]
    return '\n'.join(L)[:3000]


def iso(dt): return dt.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if dt else None


def rss_items(x):
    out = []
    for it in re.findall(r'(?s)<item>(.*?)</item>', x):
        f = lambda t: (re.search(r'(?s)<%s[^>]*>(.*?)</%s>' % (t, t), it) or [None, ''])[1]
        cd = lambda v: re.sub(r'(?s)^\s*<!\[CDATA\[(.*)\]\]>\s*$', r'\1', v or '')
        out.append({'title': html.unescape(cd(f('title'))).strip(), 'link': cd(f('link')).strip(), 'pub': cd(f('pubDate')).strip(),
                    'desc': cd(f('description')), 'content': cd(f('content:encoded')), 'raw': it})
    return out


def pub_dt(s):
    try: return email.utils.parsedate_to_datetime(s)
    except Exception: return None


def prague(data):
    try: names = {r['n'] for r in json.load(open(os.path.join(data, 'index.json'), encoding='utf-8'))['routes'] if 'prg' in r.get('c', [])}
    except Exception: names = set()
    res = []
    for feed in ('rss-mimoradnosti', 'rss-vyluky'):
        for it in rss_items(get('https://pid.cz/feed/%s/' % feed)):
            lines = re.findall(r'<line>\s*([^<\s]+)\s*</line>', it['raw'])
            if names and not (set(lines) & names): continue   # (regional lines only: not Prague's)
            a = re.search(r'<dateFrom>(\d+)</dateFrom>', it['raw']); b = re.search(r'<dateTo>(\d+)</dateTo>', it['raw'])
            s0 = datetime.datetime.fromtimestamp(int(a.group(1)), datetime.timezone.utc) if a else None
            e0 = datetime.datetime.fromtimestamp(int(b.group(1)), datetime.timezone.utc) if b else None
            if (e0 and e0 < NOW) or (s0 and s0 > NOW + datetime.timedelta(days=3)): continue
            text = plain(it['content']) or plain(it['desc'])
            text = '\n'.join(re.sub(r';?\s*Dotčené linky:.*$', '', x) for x in text.split('\n') if not re.match(r'^(Linky:|Dotčené linky:)', x) and 'přímo do vašeho e' not in x)
            text = '\n'.join(x for x in text.split('\n') if x.strip() and not re.match(r'^[\d.: ]+-\s*([\d.: ]+|do odvolání)$', x.strip()))   # (the period alone: shown from start and end)
            if feed == 'rss-vyluky' and s0 and s0 > NOW: continue   # (planned closures: only those already in force)
            res.append({'id': feed[4:] + ':' + re.sub(r'\D', '', it['link'])[-9:], 'lines': [l for l in lines if l in names] or lines,
                        'title': it['title'], 'text': text, 'start': iso(s0), 'end': iso(e0), 'url': it['link']})
    return 'https://pid.cz/zmeny/', res


def past(title, text):
    """a notice all of whose dates are gone ("1 listopada", "31.10-01.11.2026") is over"""
    t = title + ' ' + text[:1500]; ds = []; y = NOW.year
    for d, m, yy in re.findall(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})?', t):
        try: ds.append(datetime.date(int(yy or y), int(m), int(d)))
        except ValueError: pass
    for d, mo, yy in re.findall(r'\b(\d{1,2})\s+(%s)(?:\s+(\d{4}))?' % '|'.join(PL_MONTHS), t):
        try: ds.append(datetime.date(int(yy or y), PL_MONTHS.index(mo) + 1, int(d)))
        except ValueError: pass
    ds = [d for d in ds if abs((d - NOW.date()).days) < 200]
    if re.search(r'do odwołania|do odwolania', t): return False
    # (a change "od 26 października" with no end given goes on)
    since = re.search(r'\bod(?: dnia)?\s+(\d{1,2})(?:\.(\d{1,2})\.|\s+(%s))' % '|'.join(PL_MONTHS), t)
    if since and not re.search(r'\bdo(?: dnia)?\s+\d{1,2}(?:\.\d{1,2}|\s+(?:%s))' % '|'.join(PL_MONTHS), t): return False
    return bool(ds) and max(ds) < NOW.date()


def recent_rss(url, page, days=14, n=8):
    res = []
    for it in rss_items(get(url))[:n]:
        d = pub_dt(it['pub'])
        if d and d < NOW - datetime.timedelta(days=days): continue
        if past(it['title'], plain(it['content'] or it['desc'])): continue
        res.append({'id': it['link'], 'lines': [], 'title': it['title'], 'text': plain(it['content'] or it['desc']), 'start': None, 'end': None, 'url': it['link']})
    return page, res


def nowy_sacz(data):
    home = get('https://www.mpk.nowysacz.pl/')
    res = []
    for u, t in re.findall(r'<div[^>]*class="hcb_item[^"]*"[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', home)[:6]:
        try: a = get(u)
        except Exception: continue
        i = a.find('class="gp_content'); body = a[i:a.find('</section>', i)] if i >= 0 else ''
        d = re.search(r'class="gp_date">(\d{1,2})\.(\d{2})\.(\d{4})<', a)
        tt = html.unescape(re.sub(r'<[^>]+>', '', t)).strip(); tx = plain(body[body.find('>') + 1:])
        if past(tt, tx): continue
        res.append({'id': u, 'lines': [], 'title': tt, 'text': tx,
                    'start': None, 'end': None, 'url': u})
    return 'https://www.mpk.nowysacz.pl/komunikaty/', res


def wejherowo(data):
    page = get('https://mzkwejherowo.pl/wiadomosci-i-komunikaty')
    res = []
    for h, inner in re.findall(r'(?s)<a[^>]+href="(/komunikaty/[^"]+)"[^>]*>(.*?)</a>', page)[:6]:
        t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', inner)).strip()
        m = re.search(r'(\d{1,2}) (%s) (\d{4})' % '|'.join(PL_MONTHS), t)
        if m:
            d = datetime.datetime(int(m.group(3)), PL_MONTHS.index(m.group(2)) + 1, int(m.group(1)), tzinfo=datetime.timezone.utc)
            if d < NOW - datetime.timedelta(days=31): continue
            t = t[:m.start()].strip()
        u = 'https://mzkwejherowo.pl' + h
        try: a = get(u)
        except Exception: continue
        m2 = re.search(r'<(div|article)[^>]*class="[^"]*\bprose\b[^"]*"[^>]*>', a); body = a[m2.end():] if m2 else ''
        body = body[:body.find('</article>')] if '</article>' in body else body[:20000]
        tx = plain(body)
        if past(t, tx): continue
        res.append({'id': u, 'lines': [], 'title': t, 'text': tx, 'start': None, 'end': None, 'url': u})
    return 'https://mzkwejherowo.pl/wiadomosci-i-komunikaty', res


SOURCES = {
    'prg': prague,
    'poz': lambda d: recent_rss('https://www.ztm.poznan.pl/feed/?post_type=komunikaty', 'https://www.ztm.poznan.pl/pl/komunikaty/'),
    'byd': lambda d: recent_rss('https://zdmikp.bydgoszcz.pl/pl/transport/aktualnosci-komunikacyjne?format=feed&type=rss',
                                'https://zdmikp.bydgoszcz.pl/pl/transport/aktualnosci-komunikacyjne'),
    'ns': nowy_sacz,
    'wej': wejherowo,
}


def fetch(data, log=print, only=None):
    for city, f in SOURCES.items():
        if only and city not in only: continue
        try: page, res = f(data)
        except Exception as e:
            log('utrudnienia %s: brak odpowiedzi (%s)' % (city, e)); continue
        out = os.path.join(data, 'alerts_%s.json' % city)
        try: same = json.load(open(out, encoding='utf-8')).get('alerts') == res
        except Exception: same = False
        if not same:   # (unchanged: the file left as it was, so that the hourly run commits nothing)
            json.dump({'t': NOW.strftime('%Y-%m-%dT%H:%MZ'), 'url': page, 'alerts': res}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        log('utrudnienia %s: %d komunikatów' % (city, len(res)))


if __name__ == '__main__':
    fetch(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
