"""Background map for the network map window, made from OpenStreetMap data.

Vector tiles (OpenMapTiles schema, served by OpenFreeMap) are read with a tiny decoder written here, so nothing
beyond the Python standard library is needed. Only what a calm, minimal map needs is kept: water, green areas,
built-up areas, roads by importance and railways. The result goes to data/base.json in the same coordinates as
the network map (see PJ in build.py), as delta-encoded integers in units of 1/q (q is stored in the file).

Map data © OpenStreetMap contributors (ODbL), tiles from OpenFreeMap / OpenMapTiles.
"""
import gzip, json, math, os, struct, urllib.request, concurrent.futures

TILEJSON = 'https://tiles.openfreemap.org/planet'
UA = {'User-Agent': 'rozklady-trojmiasto/1.0 (timetable site; basemap build)'}
COS = math.cos(math.radians(54.45))


def PJ(lat, lon):
    return (lon * COS * 1000.0, -lat * 1000.0)


# ---------------- minimal Mapbox Vector Tile (protobuf) decoder ----------------
def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s; s += 7
        if c < 0x80: return r, i


def _fields(b):
    i, n = 0, len(b)
    while i < n:
        key, i = _varint(b, i); f, wt = key >> 3, key & 7
        if wt == 0: v, i = _varint(b, i)
        elif wt == 2:
            ln, i = _varint(b, i); v = b[i:i + ln]; i += ln
        elif wt == 1: v = b[i:i + 8]; i += 8
        elif wt == 5: v = b[i:i + 4]; i += 4
        else: raise ValueError('wire type %d' % wt)
        yield f, wt, v


def _packed(b):
    out, i = [], 0
    while i < len(b):
        v, i = _varint(b, i); out.append(v)
    return out


def _value(b):
    for f, wt, v in _fields(b):
        if f == 1: return v.decode('utf-8', 'replace')
        if f == 2: return struct.unpack('<f', v)[0]
        if f == 3: return struct.unpack('<d', v)[0]
        if f in (4, 5): return v
        if f == 6: return (v >> 1) ^ -(v & 1)
        if f == 7: return bool(v)
    return None


def decode_tile(data, want):
    """-> {layer: [(props, type, [[(x, y), ...], ...], extent)]} for the layers in `want`"""
    out = {}
    for f, wt, lb in _fields(data):
        if f != 3: continue
        name, feats, keys, vals, ext = None, [], [], [], 4096
        for g, wt2, v in _fields(lb):
            if g == 1: name = v.decode()
            elif g == 2: feats.append(v)
            elif g == 3: keys.append(v.decode())
            elif g == 4: vals.append(_value(v))
            elif g == 5: ext = v
        if name not in want: continue
        res = out.setdefault(name, [])
        for fb in feats:
            tags, typ, geom = [], 0, []
            for g, wt2, v in _fields(fb):
                if g == 2: tags = _packed(v)
                elif g == 3: typ = v
                elif g == 4: geom = _packed(v)
            props = {keys[tags[k]]: vals[tags[k + 1]] for k in range(0, len(tags) - 1, 2)}
            parts, cur, x, y, i = [], None, 0, 0, 0
            while i < len(geom):
                cmd, cnt = geom[i] & 7, geom[i] >> 3; i += 1
                if cmd == 7:
                    if cur: cur.append(cur[0])
                    continue
                for _ in range(cnt):
                    dx, dy = geom[i], geom[i + 1]; i += 2
                    x += (dx >> 1) ^ -(dx & 1); y += (dy >> 1) ^ -(dy & 1)
                    if cmd == 1:
                        cur = [(x, y)]; parts.append(cur)
                    else: cur.append((x, y))
            res.append((props, typ, parts, ext))
    return out


# ---------------- tiles ----------------
def tile_of(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def to_latlon(z, tx, ty, px, py, ext):
    n = 2 ** z
    lon = (tx + px / ext) / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + py / ext) / n))))
    return lat, lon


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r: data = r.read()
    return gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data


def rdp(pts, eps):
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
    return [p for p, k in zip(pts, keep) if k]


def classify(layer, p, typ):
    """class key of a feature, or None to leave it out"""
    c = p.get('class')
    if layer == 'water' and typ == 3: return 'w'
    if layer == 'waterway' and typ == 2 and c in ('river', 'canal'): return 'ww'
    if layer == 'landcover' and typ == 3:
        if c == 'wood': return 'f'
        if c == 'grass' or p.get('subclass') in ('park', 'garden', 'recreation_ground', 'meadow'): return 'g'
        if c == 'sand' and p.get('subclass') == 'beach': return 'b'
        return None
    if layer == 'park' and typ == 3: return 'g'
    if layer == 'landuse' and typ == 3:
        if c in ('residential', 'suburb', 'neighbourhood', 'commercial', 'retail'): return 'u'
        if c in ('industrial', 'railway', 'garages'): return 'i'
        if c == 'cemetery': return 'g'
        return None
    if layer == 'transportation' and typ == 2:
        if p.get('brunnel') == 'tunnel': return None
        if c in ('motorway', 'trunk'): return 'r1'
        if c in ('primary', 'secondary'): return 'r2'
        if c == 'tertiary': return 'r3'
        if c == 'minor': return 'r4'
        if c == 'rail' and p.get('subclass', 'rail') == 'rail' and p.get('service') not in ('yard', 'siding', 'spur'): return 'rl'
        return None
    return None


LAYERS = {'water', 'waterway', 'landcover', 'park', 'landuse', 'transportation'}


def build(out_path, bbox=None, core=None, log=print, regions=None):
    """bbox, core: (lat_min, lat_max, lon_min, lon_max). Core areas get detailed tiles (z13), the rest z11.
    regions: several (bbox, core) pairs for areas far apart (e.g. the Tricity and Krynica-Zdrój)."""
    tj = json.loads(fetch(TILEJSON)); url = tj['tiles'][0]
    jobs = []
    for bbox, core in (regions or [(bbox, core)]):
        x0, y1 = tile_of(bbox[0], bbox[2], 11); x1, y0 = tile_of(bbox[1], bbox[3], 11)
        cx0, cy1 = tile_of(core[0], core[2], 11); cx1, cy0 = tile_of(core[1], core[3], 11)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if cx0 <= x <= cx1 and cy0 <= y <= cy1:
                    jobs += [(13, x * 4 + i, y * 4 + j) for i in range(4) for j in range(4)]
                else: jobs.append((11, x, y))
    jobs = list(dict.fromkeys(jobs))
    log('Podkład mapy: pobieranie %d kafelków OpenStreetMap…' % len(jobs))

    def one(job):
        z, x, y = job
        for _ in range(3):
            try: return job, decode_tile(fetch(url.replace('{z}', str(z)).replace('{x}', str(x)).replace('{y}', str(y))), LAYERS)
            except Exception as e: err = e
        log('  kafelek %s pominięty: %s' % (job, err)); return job, {}
    out = {}
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        for (z, tx, ty), layers in ex.map(one, jobs):
            eps = 0.04 if z == 13 else 0.1
            for lname, feats in layers.items():
                for props, typ, parts, ext in feats:
                    k = classify(lname, props, typ)
                    if not k: continue
                    if k == 'r4' and z < 13: continue
                    for part in parts:
                        pts = [PJ(*to_latlon(z, tx, ty, px, py, ext)) for px, py in part]
                        if typ == 3:
                            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                            tiny = 0.15 if k in ('u', 'i') else 0.08
                            if max(xs) - min(xs) < tiny and max(ys) - min(ys) < tiny: continue   # tiny areas
                        pts = rdp(pts, eps)
                        if len(pts) >= (4 if typ == 3 else 2): out.setdefault(k, []).append(pts)

    Q = 20   # coordinates in units of 1/Q (about 3–5 m), plenty for a background
    def enc(c):
        o = []; px = py = 0
        for x, y in c:
            ix, iy = int(round(x * Q)), int(round(y * Q))
            if o and ix == px and iy == py: continue
            o += [ix - px, iy - py]; px, py = ix, iy
        return o
    res = {'attr': '© OpenStreetMap', 'q': Q, 'c': {k: [e for e in (enc(c) for c in v) if len(e) >= 4] for k, v in out.items()}}
    json.dump(res, open(out_path, 'w', encoding='utf-8'), separators=(',', ':'))
    log('Podkład mapy: %s (%d KB)' % (', '.join('%s=%d' % (k, len(v)) for k, v in sorted(out.items())), os.path.getsize(out_path) // 1024))
    return res


if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else 'data/base.json', (54.20, 54.67, 17.70, 19.00), (54.30, 54.62, 18.35, 18.85))
