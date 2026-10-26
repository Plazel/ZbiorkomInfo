"""Schematic (octilinear) network diagram, made with LOOM (https://github.com/ad-freiburg/loom).

Steps:
 1. build a line graph from the route files in data/ (stations = stops of one name close together,
    edges = runs between consecutive stations, with their street geometry) -> GeoJSON
 2. LOOM: topo (merges shared track/street sections) | loom (orders lines on shared sections) |
    octi (lays the graph out on an octilinear grid)
 3. the result is turned into data/schema_<area>.json: for every edge its octilinear polyline and the ordered
    lines on it; for every station its position and name.

LOOM is a separate program (C++). When its tools are not found, the previous schema files are kept.
"""
import json, math, os, subprocess, collections

COS = math.cos(math.radians(54.45))


def PJ(lat, lon):
    return (lon * COS * 1000.0, -lat * 1000.0)


def proj_on(path, p):
    """position of point p along polyline path: (segment index, t, distance, point)"""
    best = (1e18, 0, 0.0, path[0])
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]; dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) if l2 else 0.0
        q = (a[0] + t * dx, a[1] + t * dy); d = math.hypot(p[0] - q[0], p[1] - q[1])
        if d < best[0]: best = (d, i, t, q)
    return best


def cut_by_stops(path, pts, tol=0.12):
    """split a route polyline at its stops, walking forward so places passed twice are told apart.
    Returns one polyline per pair of consecutive stops (straight lines where the shape does not fit)."""
    if not path or len(path) < 2:
        return [[pts[i], pts[i + 1]] for i in range(len(pts) - 1)]
    pos = []; start = 0
    for p in pts:
        best = None
        for i in range(start, len(path) - 1):
            a, b = path[i], path[i + 1]; dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) if l2 else 0.0
            q = (a[0] + t * dx, a[1] + t * dy); d = math.hypot(p[0] - q[0], p[1] - q[1])
            if best is None or d < best[0] - 1e-9: best = (d, i, t, q)
            if best[0] < tol and d > best[0] * 3 + tol: break     # first good match, stop at the local minimum
        pos.append(best); start = best[1] if best else start
    out = []
    for k in range(len(pts) - 1):
        a, b = pos[k], pos[k + 1]
        if a is None or b is None or a[0] > 0.5 or b[0] > 0.5 or (b[1], b[2]) < (a[1], a[2]):
            out.append([pts[k], pts[k + 1]]); continue
        seg = [pts[k], a[3]] + [tuple(path[i]) for i in range(a[1] + 1, b[1] + 1)] + [b[3], pts[k + 1]]
        out.append(seg)
    return out


def stations(stops, used):
    """stop poles -> stations: same name and within 600 m of each other"""
    by_name = collections.defaultdict(list)
    for sid in used:
        S = stops[sid]; by_name[S[0]].append((sid, PJ(S[2], S[3])))
    st_of, st_pos, st_name = {}, {}, {}
    for name, poles in by_name.items():
        groups = []
        for sid, p in poles:
            for g in groups:
                if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 8.0 for _, q in g): g.append((sid, p)); break   # 8 units ≈ 600 m
            else: groups.append([(sid, p)])
        for gi, g in enumerate(groups):
            key = '%s#%d' % (name, gi)
            st_pos[key] = (sum(p[0] for _, p in g) / len(g), sum(p[1] for _, p in g) / len(g)); st_name[key] = name
            for sid, _ in g: st_of[sid] = key
    return st_of, st_pos, st_name


_PACKS = {}


def line_graph(data_dir, pick, color_of, clip_by=None, box_stop=None, all_pats=False):
    """GeoJSON line graph for LOOM's topo; pick(route) -> bool, color_of(route) -> 'rrggbb'.
    clip_by(route) -> bool: the diagram covers the area of these lines; other lines (trains) are cut at its edge
    and the cut is noted on the last station shown ("→ Lębork").
    box_stop(stop) -> bool: instead, the diagram covers the area of these stops (e.g. the stops in Gdańsk);
    every line is cut at its edge."""
    idx = json.load(open(os.path.join(data_dir, 'index.json'), encoding='utf-8'))
    stops = idx['stops']; routes = [r for r in idx['routes'] if pick(r)]
    runs = []   # (route, [pole ids], polyline in map units)
    for r in routes:
        if r.get('rp'):   # a big city's routes are packed several to a file (data/rp/)
            if r['rp'] not in _PACKS: _PACKS[r['rp']] = json.load(open(os.path.join(data_dir, 'rp', r['rp'] + '.json'), encoding='utf-8'))
            d = _PACKS[r['rp']][r['id']]
        else: d = json.load(open(os.path.join(data_dir, 'r', r['id'] + '.json'), encoding='utf-8'))
        for dd in d['dirs']:
            pat = [dd['stops'][i][0] for i in dd['pats'][0]]
            shape = [PJ(a, b) for a, b in dd.get('shape') or []]
            runs.append((r, pat, shape))
            if all_pats:   # small networks (Krynica-Zdrój): the variants too, so that every stop and detour is drawn
                for q in dd['pats'][1:]:
                    runs.append((r, [dd['stops'][i][0] for i in q], []))
    used = {sid for _, pat, _ in runs for sid in pat}
    st_of, st_pos, st_name = stations(stops, used)
    box = None
    if clip_by or box_stop:
        ps = [st_pos[st_of[s]] for r, pat, _ in runs if (box_stop is None and clip_by(r)) for s in pat] \
            + [st_pos[st_of[s]] for r, pat, _ in runs if box_stop is not None for s in pat if box_stop(stops[s])]
        if ps:
            m = 20.0   # about 1.3–2 km of margin
            box = (min(p[0] for p in ps) - m, min(p[1] for p in ps) - m * .7, max(p[0] for p in ps) + m, max(p[1] for p in ps) + m * .7)
    inside = lambda k: box is None or (box[0] <= st_pos[k][0] <= box[2] and box[1] <= st_pos[k][1] <= box[3])
    cuts = collections.defaultdict(list)
    feats, nodes = [], {}
    def node(key):
        if key not in nodes:
            x, y = st_pos[key]
            nodes[key] = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [x / COS / 1000.0, -y / 1000.0]},
                          'properties': {'id': key, 'station_id': key, 'station_label': st_name[key]}}
        return key
    eid = 0
    for r, pat, shape in runs:
        keys = [st_of[s] for s in pat]
        # one point per station visit (several poles of one stop in a row count once)
        seq = [k for i, k in enumerate(keys) if i == 0 or k != keys[i - 1]]
        pts = [st_pos[k] for k in seq]
        segs = cut_by_stops(shape, pts)
        ins = [inside(k) for k in seq]
        if not all(ins) and any(ins):
            # the line leaves the diagram: note where it goes on the last station inside
            for i in range(len(seq) - 1):
                if ins[i] and not ins[i + 1] and not any(ins[i + 1:]):
                    if [r['id'], st_name[seq[-1]]] not in cuts[seq[i]]: cuts[seq[i]].append([r['id'], st_name[seq[-1]]])
                if not ins[i] and ins[i + 1] and not any(ins[:i + 1]):
                    if [r['id'], st_name[seq[0]]] not in cuts[seq[i + 1]]: cuts[seq[i + 1]].append([r['id'], st_name[seq[0]]])
        for k in range(len(seq) - 1):
            a, b = seq[k], seq[k + 1]
            if a == b or not (ins[k] and ins[k + 1]): continue
            g = segs[k]; g[0] = st_pos[a]; g[-1] = st_pos[b]
            eid += 1
            feats.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [[x / COS / 1000.0, -y / 1000.0] for x, y in g]},
                          'properties': {'id': 'e%d' % eid, 'from': node(a), 'to': node(b),
                                         'lines': [{'id': r['id'], 'label': r['n'], 'color': color_of(r)}]}})
    return {'type': 'FeatureCollection', 'features': list(nodes.values()) + feats}, dict(cuts)


def run_loom(graph, bindir, octi_args=(), log=print, timeout=1800):
    exe = lambda n: os.path.join(bindir, n + '.exe') if os.path.exists(os.path.join(bindir, n + '.exe')) else os.path.join(bindir, n)
    p = json.dumps(graph).encode()
    for tool, args in (('topo', []), ('loom', []), ('octi', list(octi_args))):
        log('Schemat: %s…' % tool)
        r = subprocess.run([exe(tool)] + args, input=p, capture_output=True, timeout=timeout)
        if r.returncode != 0: raise RuntimeError('%s: %s' % (tool, r.stderr.decode()[-500:]))
        p = r.stdout
    return json.loads(p)


def simplify(pts, eps):
    """Douglas–Peucker on a polyline (distance to the segment)"""
    pts = [q for i, q in enumerate(pts) if i == 0 or q != pts[i - 1]]
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True; stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop(); a, b = pts[i0], pts[i1]; dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
        dmax, idx = 0, None
        for i in range(i0 + 1, i1):
            px, py = pts[i][0] - a[0], pts[i][1] - a[1]
            t = max(0.0, min(1.0, (px * dx + py * dy) / l2)) if l2 else 0.0
            d = math.hypot(px - t * dx, py - t * dy)
            if d > dmax: dmax, idx = d, i
        if idx is not None and dmax > eps: keep[idx] = True; stack += [(i0, idx), (idx, i1)]
    return [q for q, k in zip(pts, keep) if k]


def merc(lon, lat):
    x = math.radians(lon) * 6378137.0
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137.0
    return x, y


def bundle(ls, kind):
    """lines of one edge in LOOM's order -> drawn strokes: lines with their own colour stay, the grey lines become
    one stroke 'G' and the night lines one stroke 'N' (each placed where its lines were on average);
    returns (strokes, grey line ids, night line ids)"""
    pos = []; mem = {'G': [], 'N': []}; at = {'G': [], 'N': []}
    for i, l in enumerate(ls):
        k = {'g': 'G', 'n': 'N'}.get(kind.get(l, 'c'))
        if k: mem[k].append(l); at[k].append(i)
        else: pos.append((i, 0, l))
    for k in ('G', 'N'):
        if mem[k]: pos.append((sum(at[k]) / len(at[k]), 1, k))
    return [l for _, _, l in sorted(pos)], mem['G'], mem['N']


def to_schema(g, cell=None, cuts=None, kind=None):
    """octi output (GeoJSON) -> compact diagram: nodes [x, y, label] and edges [from, to, [points], [strokes], [grey lines],
    [night lines]], coordinates in grid cells (y pointing down). kind: line id -> 'c' (own colour), 'g' (grey), 'n' (night)"""
    pts = [f for f in g['features'] if f['geometry']['type'] == 'Point']
    eds = [f for f in g['features'] if f['geometry']['type'] == 'LineString']
    idmap, nodes = {}, []
    for f in pts:
        x, y = merc(*f['geometry']['coordinates'][:2]); pr = f['properties']
        idmap[str(pr['id'])] = len(nodes); nodes.append([x, y, pr.get('station_label', '') or '', pr.get('station_id', '') or ''])
    edges = []
    for f in eds:
        pr = f['properties']; c = [merc(*q[:2]) for q in f['geometry']['coordinates']]
        a, b = idmap.get(str(pr['from'])), idmap.get(str(pr['to']))
        if a is None or b is None: continue
        edges.append([a, b, c, [l['id'] for l in pr.get('lines', [])]])
    if cell is None:   # grid cell = the most common distance between connected nodes along x or y
        lens = collections.Counter()
        for a, b, _, _ in edges:
            for d in (abs(nodes[a][0] - nodes[b][0]), abs(nodes[a][1] - nodes[b][1])):
                if d > 50: lens[round(d)] += 1
        cell = float(lens.most_common(1)[0][0]) if lens else 800.0
    x0 = min(n[0] for n in nodes); y1 = max(n[1] for n in nodes)
    T = lambda x, y: [round((x - x0) / cell, 3), round((y1 - y) / cell, 3)]
    out_n = [T(n[0], n[1]) + [n[2]] + ([cuts[n[3]]] if cuts and n[3] in cuts else []) for n in nodes]
    out_e = []
    for a, b, c, ls in edges:
        pl = simplify([T(*q) for q in c], 0.02)
        st, gm, nm = bundle(ls, kind or {})
        out_e.append([a, b, [v for q in pl for v in q], st] + ([gm, nm] if nm else [gm] if gm else []))
    return {'n': out_n, 'e': out_e, 'cell': cell}


SETS = [
    ('szyny', 'Tramwaje, trolejbusy i kolej', lambda r: r['t'] in ('tram', 'trol', 'rail')),
    ('czeste', 'Linie częste', lambda r: r['t'] in ('tram', 'trol', 'rail') or (r['t'] == 'bus' and r.get('f'))),
    ('dzienne', 'Wszystkie linie dzienne', lambda r: r['t'] in ('tram', 'trol', 'rail', 'bus', 'repl')),
]
# Krynica-Zdrój and Muszyna: buses and the train to Kraków, every line in its own colour, no night lines – one diagram of all lines
SETS_KM = [('dzienne', 'Wszystkie linie', lambda r: r['t'] in ('bus', 'repl', 'rail'))]
# areas with a diagram (as the area buttons on the page): lines that run there, cut at the edge of the area's stops
TRI = ('gda', 'sop', 'gdy', 'oth')
AREAS = [
    ('gda', lambda r: 'gda' in (r.get('c') or []), lambda S: S[4] == 'gda'),
    ('sop', lambda r: 'sop' in (r.get('c') or []), lambda S: S[4] == 'sop'),
    ('gdy', lambda r: 'gdy' in (r.get('c') or []), lambda S: S[4] == 'gdy'),
    ('all', lambda r: not (r.get('c') and all(c not in TRI for c in r['c'])), None),   # the Tricity, trains cut at its edge
    ('km', lambda r: bool(r.get('c')) and all(c == 'km' for c in r['c']), lambda S: S[4] == 'km'),   # lines to Nowy Sącz, Bardejov, Kraków cut at the edge
    ('ns', lambda r: bool(r.get('c')) and all(c == 'ns' for c in r['c']), None),   # Nowy Sącz with the neighbouring gminas
    ('poz', lambda r: r.get('c') == ['poz'], None),   # Poznań
    ('krk', lambda r: r.get('c') == ['krk'], None),   # Kraków
    ('waw', lambda r: r.get('c') == ['waw'], None),   # Warszawa
    ('byd', lambda r: r.get('c') == ['byd'], None),   # Bydgoszcz
    ('wej', lambda r: r.get('c') == ['wej'], None),   # Wejherowo
]


def kind_of(r):
    """how a line is drawn, as its badge on the page: night lines dark, lines with a colour (frequent lines, trains,
    every line of Krynica-Zdrój and Muszyna) in colour, the rest grey"""
    return 'n' if r['t'] == 'night' else 'c' if (r.get('f') or r['t'] == 'rail') else 'g'


def find_loom():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.environ.get('LOOM_BIN'), os.path.join(here, 'loom-bin'), os.path.join(here, 'loom', 'build')):
        # the .exe programs of loom-bin run only on Windows
        if d and all(os.path.exists(os.path.join(d, t)) or (os.name == 'nt' and os.path.exists(os.path.join(d, t + '.exe'))) for t in ('topo', 'loom', 'octi')):
            return d
    import shutil
    w = shutil.which('octi')
    if w: return os.path.dirname(w)
    return None


def build_all(data_dir, log=print, octi_args=('-g', '60%'), workers=2, areas=None):
    """data/schema_<area>.json for every area (or only the given ones): {'sets': [{id, name, g (day lines), gn (with night lines)}]}"""
    bindir = find_loom()
    if not bindir: raise RuntimeError('brak narzędzi LOOM (topo, loom, octi) – zostają poprzednie schematy')
    import concurrent.futures
    idx = json.load(open(os.path.join(data_dir, 'index.json'), encoding='utf-8'))
    kind = {r['id']: kind_of(r) for r in idx['routes']}
    todo = [a for a in AREAS if areas is None or a[0] in areas]
    # Nowy Sącz: buses only; Warszawa: trams, metro and trains, and the frequent lines (all its bus lines would make an unreadable diagram)
    sets_of = lambda area: SETS_KM if area == 'km' else SETS[1:] if area == 'ns' else SETS[:2] if area == 'waw' else SETS
    jobs = []
    for area, in_area, box_stop in todo:
        for sid, name, pick in sets_of(area):
            for night in ((False,) if area in ('km', 'poz', 'krk', 'waw') else (False, True)):
                p = lambda r, pick=pick, in_area=in_area, night=night: in_area(r) and (pick(r) or (night and r['t'] == 'night'))
                jobs.append((area, sid, night, p, box_stop))

    def one(job):
        area, sid, night, p, box_stop = job
        if box_stop: g, cuts = line_graph(data_dir, p, lambda r: '777777', box_stop=box_stop, all_pats=area == 'km')
        else: g, cuts = line_graph(data_dir, p, lambda r: '777777', clip_by=lambda r: r['t'] != 'rail', all_pats=area == 'km')
        if not any(f['geometry']['type'] == 'LineString' for f in g['features']): return job, None
        # octi now and then gets stuck on a large graph: then once more with a coarser grid and a shorter search;
        # if that fails too, the diagram of the previous build is kept for this set
        for args, tmo in ((octi_args, 900), (('-g', '80%', '--restr-loc-search', '--loc-search-max-iters', '30'), 900)):
            try:
                sch = to_schema(run_loom(g, bindir, args, log=lambda m: None, timeout=tmo), cuts=cuts, kind=kind)
                return job, {'n': sch['n'], 'e': sch['e']}
            except Exception as e:
                log('Schemat %s „%s”%s: %s' % (area, sid, ' (z nocnymi)' if night else '', str(e)[:120]))
        return job, False
    res = {}
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for (area, sid, night, _, _), g in ex.map(one, jobs):
            res[(area, sid, night)] = g
            if g: log('Schemat %s „%s”%s: %d węzłów, %d odcinków' % (area, sid, ' (z nocnymi)' if night else '', len(g['n']), len(g['e'])))
    done = [area for area, _, _ in todo if all(g is not False for (a, _s, _n), g in res.items() if a == area)]
    for area, _, _ in todo:
        dest = os.path.join(data_dir, 'schema_%s.json' % area)
        try: old = {x['id']: x for x in json.load(open(dest, encoding='utf-8'))['sets']}
        except Exception: old = {}
        for (a, sid, night), g in list(res.items()):
            if a == area and g is False:
                o = old.get(sid); res[(a, sid, night)] = (o.get('gn') or o.get('g')) if (o and night) else (o.get('g') if o else None)
        sets = []
        for sid, name, _ in sets_of(area):
            g, gn = res.get((area, sid, False)), res.get((area, sid, True))
            if g: sets.append({'id': sid, 'name': name, 'g': g, **({'gn': gn} if gn and gn != g else {})})   # a set of night lines only is left out
        json.dump({'sets': sets}, open(dest, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        log('Schemat oktylinearny %s: %d KB' % (area, os.path.getsize(dest) // 1024))
    old = os.path.join(data_dir, 'schema.json')
    if os.path.exists(old): os.remove(old)   # the single file of earlier versions
    return done   # the areas drawn without a failed set
