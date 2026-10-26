#!/usr/bin/env python3
"""Walking network for the journey planner: streets, footways, paths, steps and squares from OpenStreetMap
(OpenFreeMap vector tiles, zoom 14), around the stops of an area -> data/walk/<area>.json (list of parts) and
data/walk/<area>_<x>_<y>.json (one part per zoom-10 tile, loaded only where a walk is drawn).

The page builds a graph from it and draws each walk (to a stop, between stops, to the destination) along it.
Format: {"q": Q, "c": [[x0, y0, dx, dy, …], …]} – polylines in the map's own projection (basemap.PJ), times Q,
delta-encoded like the background map.
Usage: python walknet.py [data folder]   (or from build.py)"""
import json, math, os, sys, concurrent.futures
import basemap

Z = 14
Q = 10
RADIUS = 600   # metres around each stop
WALK = {'primary', 'secondary', 'tertiary', 'minor', 'service', 'path', 'pedestrian'}
PART_Z = 10


def tiles_near(stops):
    """z14 tiles within RADIUS of any stop"""
    out = set()
    for lat, lon in stops:
        dlat = RADIUS / 111320; dlon = RADIUS / (111320 * math.cos(math.radians(lat)))
        x0, y1 = basemap.tile_of(lat - dlat, lon - dlon, Z); x1, y0 = basemap.tile_of(lat + dlat, lon + dlon, Z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1): out.add((x, y))
    return sorted(out)


def build(out, area, stops, log=print):
    tj = json.loads(basemap.fetch(basemap.TILEJSON)); url = tj['tiles'][0]
    jobs = tiles_near(stops)
    log('Sieć piesza %s: %d kafelków' % (area, len(jobs)))

    def one(j):
        for _ in range(3):
            try: return j, basemap.decode_tile(basemap.fetch(url.replace('{z}', str(Z)).replace('{x}', str(j[0])).replace('{y}', str(j[1]))), {'transportation'})
            except Exception as e: err = e
        log('  kafelek %s pominięty: %s' % (j, err)); return j, {}
    lines = []
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        for (tx, ty), L in ex.map(one, jobs):
            for props, typ, parts, ext in L.get('transportation', []):
                if typ != 2: continue
                c = props.get('class')
                if c not in WALK and props.get('subclass') not in WALK: continue
                for part in parts:
                    pts = [basemap.PJ(*basemap.to_latlon(Z, tx, ty, px, py, ext)) for px, py in part]
                    pts = basemap.rdp(pts, 0.03)
                    if len(pts) >= 2:
                        lat, lon = basemap.to_latlon(Z, tx, ty, part[0][0], part[0][1], ext)
                        lines.append((basemap.tile_of(lat, lon, PART_Z), pts))

    def enc(c):
        o = []; px = py = 0
        for x, y in c:
            ix, iy = int(round(x * Q)), int(round(y * Q))
            if o and ix == px and iy == py: continue
            o += [ix - px, iy - py]; px, py = ix, iy
        return o
    parts = {}
    for t, pts in lines:
        e = enc(pts)
        if len(e) >= 4: parts.setdefault(t, []).append((e, pts))
    os.makedirs(os.path.join(out, 'walk'), exist_ok=True)
    idx = []; tot = 0
    for (x, y), L in sorted(parts.items()):
        f = '%s_%d_%d' % (area, x, y)
        xs = [p[0] for _, pts in L for p in pts]; ys = [p[1] for _, pts in L for p in pts]
        json.dump({'q': Q, 'c': [e for e, _ in L]}, open(os.path.join(out, 'walk', f + '.json'), 'w', encoding='utf-8'), separators=(',', ':'))
        tot += os.path.getsize(os.path.join(out, 'walk', f + '.json'))
        idx.append([f, round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)])
    json.dump(idx, open(os.path.join(out, 'walk', area + '.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    log('Sieć piesza %s: %d odcinków w %d częściach (%d KB)' % (area, len(lines), len(idx), tot // 1024))


AREAS = {'tri': lambda a: a in ('gda', 'sop', 'gdy'), 'km': lambda a: a in ('km', 'kmx'), 'byd': lambda a: a == 'byd', 'ns': lambda a: a == 'ns',
         'poz': lambda a: a == 'poz', 'krk': lambda a: a == 'krk', 'waw': lambda a: a == 'waw', 'wej': lambda a: a == 'wej', 'ldz': lambda a: a == 'ldz', 'fl': lambda a: a == 'fl', 'prg': lambda a: a == 'prg'}


def build_all(out, areas=None, log=print):
    st = list(json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))['stops'].values())
    for a, sel in AREAS.items():
        if areas and a not in areas: continue
        pts = [(v[2], v[3]) for v in st if sel(v[4])]
        if pts:
            try:
                for f in os.listdir(os.path.join(out, 'walk')) if os.path.isdir(os.path.join(out, 'walk')) else []:
                    if f == a + '.json' or f.startswith(a + '_'): os.remove(os.path.join(out, 'walk', f))
                build(out, a, pts, log)
            except Exception as e: log('Sieć piesza %s: nie udało się (%s)' % (a, e))


if __name__ == '__main__':
    build_all(sys.argv[1] if len(sys.argv) > 1 else 'data', sys.argv[2].split(',') if len(sys.argv) > 2 else None)
