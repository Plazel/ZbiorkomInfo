#!/usr/bin/env python3
"""Courses of the lines laid exactly onto the OpenStreetMap roads and tram tracks (map matching).

The timetable data's shapes often cut corners or run a few metres beside the street. Each shape is followed piece by
piece (about 1.5 km at a time) through the road graph of drogi.py (OpenFreeMap vector tiles, zoom 14): the cheapest way
from the start to the end of the piece, where every road is dearer the farther it lies from the shape. A piece whose
result strays from the shape (a different street, a detour) keeps its original course.
build.py calls match_all(); results are kept in reczne/dopasowanie_cache.json, so a shape is matched only once.
"""
import collections, hashlib, heapq, json, math, os
import drogi, basemap

Z = drogi.Z
PX = 2 ** Z * 4096                       # tile-pixel grid of drogi.TileRouter (its node coordinates)
COSTS = dict(drogi.COST, transit=1.0, minor=1.05, service=1.3, track=2.5)   # trams (transit) along their tracks too
CHUNK = 1500.0                           # metres of shape per routed piece
CORR = 70.0                              # metres: roads farther from the shape are not used
SOFT = 14.0                              # metres: the cost grows with (distance / SOFT)^2


def to_px(lat, lon):
    return ((lon + 180) / 360 * PX, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * PX)


def to_ll(x, y):
    lon = x / PX * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / PX))))
    return [round(lat, 6), round(lon, 6)]


RAIL = {'rail': 1.0, 'transit': 1.1}   # trains: along the railway tracks only


class Matcher:
    def __init__(self, bbox, log=print, rail=False):
        # trains: a wider corridor (the railway shapes in the data are often coarse; tracks are few, so no other line is near)
        self.corr, self.soft = (450.0, 90.0) if rail else (CORR, SOFT)
        self.r = drogi.TileRouter(bbox, log=log, costs=RAIL if rail else COSTS)
        adj = self.r.adj   # the shape gives the direction: one-way restrictions are not needed (and bus lanes run against them)
        for a in list(adj):
            for b, cm in list(adj[a].items()):
                if a not in adj[b]: adj[b][a] = cm
        lat = (bbox[0] + bbox[1]) / 2
        self.mpp = 40075016.686 * math.cos(math.radians(lat)) / PX   # metres per grid unit here

    def match(self, latlon, stops=()):
        """the shape [[lat, lon], …] along the roads, or the shape itself where that fails; stops ([lat, lon]): pieces
        end at them (a train reversing at a station then visits the station instead of cutting the corner)"""
        P = [to_px(*p) for p in latlon]
        if len(P) < 2: return latlon
        # cut into pieces of about CHUNK metres (at shape points)
        cum = [0.0]
        for a, b in zip(P, P[1:]): cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]) * self.mpp)
        if cum[-1] < 30: return latlon
        n = max(1, round(cum[-1] / CHUNK)); cuts = [0]
        for k in range(1, n):
            t = cum[-1] * k / n; i = min(range(len(cum)), key=lambda j: abs(cum[j] - t))
            if i > cuts[-1] and i < len(P) - 1: cuts.append(i)
        cuts.append(len(P) - 1)
        if stops:   # the shape points nearest to the stops, in order along the shape
            j0 = 0; sc = set(cuts)
            for la, lo in stops:
                q = to_px(la, lo); best = None
                for j in range(j0, len(P)):
                    d = math.hypot(P[j][0] - q[0], P[j][1] - q[1])
                    if best is None or d < best[0]: best = (d, j)
                if best and best[0] * self.mpp < 400: sc.add(best[1]); j0 = best[1]
            cuts = sorted(sc)
        out = []
        for i0, i1 in zip(cuts, cuts[1:]):
            seg = P[i0:i1 + 1]
            got = self._piece(seg, out[-1] if out else None)
            pts = got if got else seg
            out += pts if not out else pts[1:]
        res = [to_ll(x, y) for x, y in out]
        return [[round(a, 5), round(b, 5)] for a, b in drogi.simplify(res, 1.5)]

    def _piece(self, seg, start_at):
        mpp = self.mpp; G = 64; CORR, SOFT = self.corr, self.soft
        grid = collections.defaultdict(list)
        for i, (a, b) in enumerate(zip(seg, seg[1:])):
            for gx in range(int(min(a[0], b[0]) - CORR / mpp) // G, int(max(a[0], b[0]) + CORR / mpp) // G + 1):
                for gy in range(int(min(a[1], b[1]) - CORR / mpp) // G, int(max(a[1], b[1]) + CORR / mpp) // G + 1):
                    grid[(gx, gy)].append(i)
        dc = {}

        def dist(q):   # metres from the piece of shape
            v = dc.get(q)
            if v is not None: return v
            best = 1e9
            for i in grid.get((int(q[0]) // G, int(q[1]) // G), ()):
                a, b = seg[i], seg[i + 1]; dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
                t = max(0, min(1, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / l2)) if l2 else 0
                d = math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)
                if d < best: best = d
            v = dc[q] = best * mpp; return v

        adj = self.r.adj
        def ends(p, back):
            """graph nodes to begin (or finish) at near point p, with the cost of getting there"""
            ll = to_ll(*p); out = {}
            for d, i, q, t in self.r.nearest(ll, 16):
                a, b, c, ow = self.r.segs[i]
                dm = math.hypot(q[0] - p[0], q[1] - p[1]) * mpp
                if dm > max(35, CORR / 3): continue
                for nd in (a, b):
                    cost = dm * 4 + math.hypot(nd[0] - q[0], nd[1] - q[1]) * mpp * c
                    if nd in adj and cost < out.get(nd, (1e18,))[0]: out[nd] = (cost, q)
            return out
        A = ends(start_at or seg[0], False); B = ends(seg[-1], True)
        if not A or not B: return None
        best = {nd: v[0] for nd, v in A.items()}; prev = {}
        h = [(v[0], nd) for nd, v in A.items()]; heapq.heapify(h); done = set(); found = None
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(seg, seg[1:])) * mpp
        while h:
            c0, nd = heapq.heappop(h)
            if nd in done: continue
            done.add(nd)
            if nd in B:
                tot = c0 + B[nd][0]
                if found is None or tot < found[0]: found = (tot, nd)
            if found and c0 > found[0]: break
            if c0 > length * 8 + 2000: break
            for m, (cost, metres) in adj[nd].items():
                mid = ((nd[0] + m[0]) / 2, (nd[1] + m[1]) / 2)
                dmid = max(dist(m), dist(mid))
                if dmid > CORR: continue
                nc = c0 + cost * (1 + (dmid / SOFT) ** 2)
                if nc < best.get(m, 1e18): best[m] = nc; prev[m] = nd; heapq.heappush(h, (nc, m))
        if not found: return None
        nd = found[1]; path = [nd]
        while nd in prev: nd = prev[nd]; path.append(nd)
        path.reverse()
        pts = [start_at or A[path[0]][1]] + [tuple(x) for x in path] + [B[path[-1]][1]]
        if start_at: pts[0] = start_at
        # sanity: about as long as the shape, and close to it all the way
        ml = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])) * mpp
        if not (0.75 * length - 40 <= ml <= 1.3 * length + 60): return None
        dens = []
        for a, b in zip(pts, pts[1:]):
            k = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) * mpp / 15))
            dens += [(a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k) for j in range(k)]
        far = [dist(q) for q in dens]
        if far and (max(far) > CORR or sum(far) / len(far) > max(22, SOFT * 1.5)): return None
        return pts


def match_all(shapes, keys, area_of, cache_path, log=print):
    """shapes: {key: [[lat, lon], …]}; matches those in keys, one road graph per area (area_of(key)); in place"""
    cache = json.load(open(cache_path, encoding='utf-8')) if os.path.exists(cache_path) else {}
    h = lambda pts: hashlib.md5(json.dumps(pts).encode()).hexdigest()[:16]
    todo = collections.defaultdict(list); done = 0
    for k in keys:
        pts = shapes.get(k)
        if not pts or len(pts) < 2: continue
        c = cache.get(h(pts))
        if c: shapes[k] = c; done += 1
        else: todo[area_of(k)].append(k)
    for area, ks in todo.items():
        lats = [p[0] for k in ks for p in shapes[k]]; lons = [p[1] for k in ks for p in shapes[k]]
        try: M = Matcher((min(lats) - .01, max(lats) + .01, min(lons) - .015, max(lons) + .015), log=lambda m: log(area + ', ' + m))
        except Exception as e: log('%s: dopasowanie pominięte (%s)' % (area, e)); continue
        for j, k in enumerate(ks):
            src = shapes[k]
            try: res = M.match(src)
            except Exception as e: log('  %s: %s' % (k, e)); res = src
            cache[h(src)] = res; shapes[k] = res
            if j % 200 == 199: log('%s: %d / %d kształtów' % (area, j + 1, len(ks)))
        json.dump(cache, open(cache_path, 'w', encoding='utf-8'), separators=(',', ':'))
        log('%s: dopasowano %d kształtów do dróg' % (area, len(ks)))
    log('Dopasowanie do dróg: %d z pamięci, %d nowych' % (done, sum(len(v) for v in todo.values())))
