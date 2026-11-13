"""The index of lines and stops cut into one file per area (data/ix/<area>.json), so the page loads only its city's
part (the whole index.json: all cities, several MB) and joins another area's when its city is opened.
Each file: the index's header fields, 'cities' (every city code the whole data has stops for), the area's lines and the
stops of the area – those with its code and every stop its lines call at.
    python ixsplit.py [data]"""
import collections, json, os, sys

SEP = ('km', 'byd', 'ns', 'poz', 'krk', 'waw', 'wej', 'ldz', 'fl', 'prg', 'ber', 'ham', 'wro', 'lub', 'bts')   # as SEP_AREAS in index.html


def area_of(r):
    c = r.get('c') or []
    return next((a for a in SEP if c and all(x == a for x in c)), 'tri')


def build(out):
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    stops = idx['stops']; routes = idx['routes']
    if not isinstance(routes, list): return 0
    by = collections.defaultdict(list)
    for r in routes: by[area_of(r)].append(r)
    used = collections.defaultdict(set)   # area -> stop ids its lines call at
    packs = {}
    for r in routes:
        a = area_of(r); L = None
        if r.get('rp'):
            if r['rp'] not in packs:
                try: packs[r['rp']] = json.load(open(os.path.join(out, 'rp', r['rp'] + '.json'), encoding='utf-8'))
                except Exception: packs[r['rp']] = {}
            L = packs[r['rp']].get(r['id'])
        else:
            try: L = json.load(open(os.path.join(out, 'r', r['id'] + '.json'), encoding='utf-8'))
            except Exception: L = None
        for d in (L or {}).get('dirs', []):
            for s in d.get('stops', []): used[a].add(s[0])
    cities = sorted({v[4] for v in stops.values() if len(v) > 4 and v[4]})
    head = {k: v for k, v in idx.items() if k not in ('stops', 'routes')}
    dest = os.path.join(out, 'ix'); os.makedirs(dest, exist_ok=True)
    for f in os.listdir(dest): os.remove(os.path.join(dest, f))
    for a, rs in by.items():
        st = {k: v for k, v in stops.items() if k in used[a] or ((v[4] if len(v) > 4 else '') == a if a != 'tri' else (v[4] if len(v) > 4 else '') not in SEP)}
        json.dump({**head, 'area': a, 'cities': cities, 'stops': st, 'routes': rs},
                  open(os.path.join(dest, a + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return len(by)


if __name__ == '__main__':
    print('Indeks wg obszarów:', build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')), 'plików')
