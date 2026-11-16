"""Data for the detours read from the operators' notices (the page's "Objazdy z komunikatów", BETA):

data/net_<area>.json – the network of each area: for each kind of vehicle, the pairs of stops that follow each other on any
  route ({"tram": ["a b", …], "bus": […]}) – a detour's path between two stops is looked for on it;
data/ulice_tri.json – the street of each ZTM Gdańsk stop ({stop id: street}), as the operator's line pages give it
  (ztm.gda.pl/rozklady/linia-N.html: every stop row starts with its street) – one request per line, with a pause between."""
import json, os, re, time, html, collections, urllib.request

# the areas of the alerts on the page (alertGrp): the Tricity's route files are gda_*, gdy_*, sop_*, tri_*
GROUP = {'gda': 'tri', 'gdy': 'tri', 'sop': 'tri', 'tri': 'tri'}
# the areas whose notices are in Polish and follow the patterns the page reads (the others are left out)
AREAS = {'tri', 'waw', 'ldz', 'lub', 'wro', 'krk', 'poz', 'byd', 'wej', 'ns'}


def _kind(r):   # (as the page's dtKind: trams, trains, and every other kind on the roads)
    t = r.get('t') or 'bus'
    return t if t in ('tram', 'rail') else 'bus'


def build_net(out):
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    meta = {r['id']: r for r in idx['routes']}
    nets = collections.defaultdict(lambda: collections.defaultdict(set))
    rp = os.path.join(out, 'rp')
    for f in sorted(os.listdir(rp)):
        if not f.endswith('.json'): continue
        g = GROUP.get(f.split('_')[0], f.split('_')[0])
        if g not in AREAS: continue
        pack = json.load(open(os.path.join(rp, f), encoding='utf-8'))
        for rid, r in pack.items():
            k = _kind(meta.get(rid) or r)
            for d in r.get('dirs', []):
                s = [x[0] for x in d.get('stops', [])]
                for a, b in zip(s, s[1:]):
                    if a != b: nets[g][k].add(a + ' ' + b)
    for g, by in nets.items():
        json.dump({k: sorted(v) for k, v in by.items()}, open(os.path.join(out, 'net_%s.json' % g), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('Objazdy: sieci', ', '.join('%s (%d)' % (g, sum(len(v) for v in by.values())) for g, by in nets.items()))


def _norm(k):
    k = re.sub(r'\s*\(n/ż\)\s*', ' ', k)
    k = re.sub(r'\s*[–—-]\s*', ' - ', k)
    k = re.sub(r'\bDw\.\s*', 'Dworzec ', k)
    return re.sub(r'\s+', ' ', k).strip()


def build_streets(out, pause=.5, names=None):
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    lines = sorted({r['n'] for r in idx['routes'] if r.get('op') == 'ZTM Gdańsk'}) if names is None else []
    names = {_norm(k): v for k, v in (names or {}).items()}
    for ln in lines:
        try:
            req = urllib.request.Request('https://ztm.gda.pl/rozklady/linia-%s.html' % ln, headers={'User-Agent': 'ZbiorkomInfo (github.com/Plazel/ZbiorkomInfo)'})
            s = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
        except Exception as e:
            print('Objazdy: ulice linii %s pominięte (%s)' % (ln, e)); continue
        for st, rest in re.findall(r'<div class="route_street"[^>]*>(.*?)</div>(.*?)</td>', s, re.S):
            name = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', rest))).strip(); st = html.unescape(st).strip()
            if name and st: names.setdefault(_norm(name), st)
        time.sleep(pause)
    if not names: print('Objazdy: brak ulic'); return
    by_base = collections.defaultdict(set)
    for k, v in names.items(): by_base[re.sub(r' \d\d$', '', k)].add(v)
    ztm = set()
    rp = os.path.join(out, 'rp')
    ops = {r['id'] for r in idx['routes'] if r.get('op') == 'ZTM Gdańsk'}
    for f in os.listdir(rp):
        if not f.endswith('.json'): continue
        for rid, r in json.load(open(os.path.join(rp, f), encoding='utf-8')).items():
            if rid in ops:
                for d in r.get('dirs', []): ztm.update(x[0] for x in d.get('stops', []))
    res = {}
    for sid in ztm:
        st = idx['stops'].get(sid)
        if not st: continue
        k = _norm(st[0] + ' ' + st[1])
        if k in names: res[sid] = names[k]
        else:
            b = by_base.get(_norm(st[0]))
            if b and len(b) == 1: res[sid] = next(iter(b))   # (another post of the stop, all its posts on one street)
    json.dump(res, open(os.path.join(out, 'ulice_tri.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('Objazdy: ulice dla %d z %d przystanków ZTM' % (len(res), len(ztm)))


def build(out):
    build_net(out)
    try: build_streets(out)
    except Exception as e: print('Objazdy: ulice pominięte (%s)' % e)
