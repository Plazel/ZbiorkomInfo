"""Road routes between stops, for lines whose data has no street geometry (Krynica-Zdrój, Muszyna, Nowy Sącz).

The roads come from OpenStreetMap, as the OpenFreeMap vector tiles at zoom 14 (the same source as the map background),
and are turned into a graph here; a route is the shortest by distance, main roads preferred, one-way streets respected.
"""
import json, math, heapq, collections, concurrent.futures
import basemap   # tile download and decoding

Z = 14
K = math.cos(math.radians(49.5))   # southern Poland; distances only need to be roughly right
# cost per metre by road class (paths, railways and the like are left out)
COST = {'motorway': 1.0, 'trunk': 1.0, 'primary': 1.0, 'secondary': 1.0, 'tertiary': 1.05, 'busway': 1.0, 'bus_guideway': 1.0,
        'minor': 1.25, 'service': 1.8, 'track': 4.0, 'raceway': 6.0}
# where that finds only a long detour: field and forest roads too (some village roads are mapped as tracks)
COST_RELAXED = dict(COST, track=1.3, path=2.5)


def dist(a, b):   # metres between [lat, lon] points
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * K)


def simplify(pts, eps=4.0):
    """Douglas–Peucker in metres"""
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True; st = [(0, len(pts) - 1)]
    while st:
        i0, i1 = st.pop(); a, b = pts[i0], pts[i1]
        ax, ay, bx, by = a[1] * K * 111320, a[0] * 111320, b[1] * K * 111320, b[0] * 111320
        dx, dy = bx - ax, by - ay; l2 = dx * dx + dy * dy; dm, im = 0, None
        for i in range(i0 + 1, i1):
            px, py = pts[i][1] * K * 111320 - ax, pts[i][0] * 111320 - ay
            t = max(0, min(1, (px * dx + py * dy) / l2)) if l2 else 0
            d = math.hypot(px - t * dx, py - t * dy)
            if d > dm: dm, im = d, i
        if im is not None and dm > eps: keep[im] = True; st += [(i0, im), (im, i1)]
    return [p for p, k in zip(pts, keep) if k]


class TileRouter:
    """road graph of an area from the zoom-14 vector tiles; nodes are points of the global tile-pixel grid"""
    def __init__(self, bbox, log=print, costs=COST):
        self.bbox = bbox
        tj = json.loads(basemap.fetch(basemap.TILEJSON)); url = tj['tiles'][0]
        x0, y1 = basemap.tile_of(bbox[0], bbox[2], Z); x1, y0 = basemap.tile_of(bbox[1], bbox[3], Z)
        jobs = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
        log('drogi: %d kafelków' % len(jobs))
        def one(j):
            for _ in range(4):
                try: return j, basemap.decode_tile(basemap.fetch(url.replace('{z}', str(Z)).replace('{x}', str(j[0])).replace('{y}', str(j[1]))), {'transportation'})
                except Exception as e: err = e
            log('  kafelek %s pominięty: %s' % (j, err)); return j, {}
        self.adj = collections.defaultdict(dict)   # node -> {node: (cost, metres)}
        self.ll = {}
        lines = []
        with concurrent.futures.ThreadPoolExecutor(6) as ex:
            for (tx, ty), L in ex.map(one, jobs):
                for props, typ, parts, ext in L.get('transportation', []):
                    c = costs.get(props.get('class'))
                    if typ != 2 or c is None: continue
                    ow = props.get('oneway') or 0
                    for part in parts:
                        nodes = [(round((tx + px / ext) * 4096), round((ty + py / ext) * 4096)) for px, py in part]
                        nodes = [n for i, n in enumerate(nodes) if i == 0 or n != nodes[i - 1]]
                        if len(nodes) > 1: lines.append((nodes, c, ow, props.get('brunnel')))
        for nodes, c, ow, br in lines:
            for a, b in zip(nodes, nodes[1:]): self._edge(a, b, c, ow)
        # line ends that stop just short of another road (vertices dropped by the tiles' simplification): join them
        grid = collections.defaultdict(list); G = 48
        segs = [(a, b, c, ow) for nodes, c, ow, br in lines for a, b in zip(nodes, nodes[1:])]
        for i, (a, b, c, ow) in enumerate(segs):
            for gx in range(min(a[0], b[0]) // G, max(a[0], b[0]) // G + 1):
                for gy in range(min(a[1], b[1]) // G, max(a[1], b[1]) // G + 1): grid[(gx, gy)].append(i)
        deg = collections.Counter()
        for nodes, *_ in lines:
            deg[nodes[0]] += 1; deg[nodes[-1]] += 1
            for n in nodes[1:-1]: deg[n] += 2
        joined = 0
        for n, k in list(deg.items()):
            if k != 1: continue
            best = None
            for i in grid.get((n[0] // G, n[1] // G), []):
                a, b, c, ow = segs[i]
                if n in (a, b): continue
                dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
                t = max(0, min(1, ((n[0] - a[0]) * dx + (n[1] - a[1]) * dy) / l2)) if l2 else 0
                q = (a[0] + t * dx, a[1] + t * dy); d = math.hypot(n[0] - q[0], n[1] - q[1])
                if d < 14 and (best is None or d < best[0]): best = (d, i, (round(q[0]), round(q[1])))
            if best:
                d, i, q = best; a, b, c, ow = segs[i]
                if q not in (a, b):
                    self._unlink(a, b); self._edge(a, q, c, ow); self._edge(q, b, c, ow)
                    segs[i] = (a, q, c, ow); segs.append((q, b, c, ow))
                    for gx in range(min(q[0], b[0]) // G, max(q[0], b[0]) // G + 1):
                        for gy in range(min(q[1], b[1]) // G, max(q[1], b[1]) // G + 1): grid[(gx, gy)].append(len(segs) - 1)
                self._edge(n, q, 1.25, 0); joined += 1
        self.segs = segs; self.grid = grid; self.G = G
        log('drogi: %d węzłów, %d połączonych końców' % (len(self.adj), joined))

    def pos(self, n):
        if n not in self.ll: self.ll[n] = basemap.to_latlon(Z, 0, 0, n[0], n[1], 4096)
        return self.ll[n]

    def _edge(self, a, b, c, ow):
        m = dist(self.pos(a), self.pos(b))
        if ow != -1: self.adj[a][b] = (m * c, m)
        if ow != 1: self.adj[b][a] = (m * c, m)

    def _unlink(self, a, b):
        self.adj[a].pop(b, None); self.adj[b].pop(a, None)

    def nearest(self, p, k=3):
        """the closest road segments to [lat, lon]: [(metres, segment, point on it)]"""
        n = basemap.tile_of(p[0], p[1], Z)
        lat, lon = p; x = (lon + 180) / 360 * 2 ** Z * 4096
        y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** Z * 4096
        out = []; r = 1
        while not out and r < 40:   # up to about 600 m
            seen = set()
            for gx in range(int(x) // self.G - r, int(x) // self.G + r + 1):
                for gy in range(int(y) // self.G - r, int(y) // self.G + r + 1):
                    for i in self.grid.get((gx, gy), []):
                        if i in seen: continue
                        seen.add(i); a, b, c, ow = self.segs[i]
                        dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
                        t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)) if l2 else 0
                        q = (a[0] + t * dx, a[1] + t * dy)
                        out.append((math.hypot(x - q[0], y - q[1]) * 0.39 * c ** .5, i, q, t))
            r *= 2
        return sorted(out)[:k]

    def route(self, pa, pb):
        """road route from pa to pb ([lat, lon]): (points [[lat, lon]], metres) or (None, None)"""
        # several nearby road pieces to start and end on (a stop between two roads: the one that makes no detour)
        A, B = [x for x in self.nearest(pa, 12) if x[0] < 90], [x for x in self.nearest(pb, 12) if x[0] < 90]
        A, B = A or self.nearest(pa, 1), B or self.nearest(pb, 1)
        if not A or not B: return None, None
        # start: both ends of the nearest segments, at the cost of getting there along the segment
        start, goal = {}, {}
        for d, i, q, t in A:
            a, b, c, ow = self.segs[i]; ql = basemap.to_latlon(Z, 0, 0, q[0], q[1], 4096)
            for n in (a, b):
                if n in self.adj and (ow == 0 or (ow == 1 and n == b) or (ow == -1 and n == a)):
                    cost = d * 3 + dist(ql, self.pos(n)) * c
                    if cost < start.get(n, (1e18,))[0]: start[n] = (cost, ql)
        for d, i, q, t in B:
            a, b, c, ow = self.segs[i]; ql = basemap.to_latlon(Z, 0, 0, q[0], q[1], 4096)
            for n in (a, b):
                if ow == 0 or (ow == 1 and n == a) or (ow == -1 and n == b):
                    cost = d * 3 + dist(ql, self.pos(n)) * c
                    if cost < goal.get(n, (1e18,))[0]: goal[n] = (cost, ql)
            # both on one segment, in order: straight along it
        same = [(d1 + d2, q1) for d1, i1, q1, t1 in A[:1] for d2, i2, q2, t2 in B[:1] if i1 == i2]
        if same and dist(pa, pb) < 400:
            a, b, c, ow = self.segs[A[0][1]]; t1, t2 = A[0][3], B[0][3]
            if ow == 0 or (ow == 1 and t2 >= t1) or (ow == -1 and t2 <= t1):
                q1 = basemap.to_latlon(Z, 0, 0, A[0][2][0], A[0][2][1], 4096); q2 = basemap.to_latlon(Z, 0, 0, B[0][2][0], B[0][2][1], 4096)
                return [list(q1), list(q2)], dist(q1, q2)
        best = {n: v[0] for n, v in start.items()}; prev = {}
        h = [(v[0], n) for n, v in start.items()]; heapq.heapify(h)
        limit = dist(pa, pb) * 6 + 3000; found = None; done = set()
        while h:
            c0, n = heapq.heappop(h)
            if n in done: continue
            done.add(n)
            if n in goal:
                tot = c0 + goal[n][0]
                if found is None or tot < found[0]: found = (tot, n)
            if found and c0 > found[0]: break
            if c0 > limit * 2: break
            for m, (cost, metres) in self.adj[n].items():
                nc = c0 + cost
                if nc < best.get(m, 1e18): best[m] = nc; prev[m] = n; heapq.heappush(h, (nc, m))
        if not found: return None, None
        n = found[1]; path = [n]
        while n in prev: n = prev[n]; path.append(n)
        path.reverse()
        pts = [list(start[path[0]][1])] + [list(self.pos(x)) for x in path] + [list(goal[path[-1]][1])]
        return pts, sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))




def road_legs(pairs, pos, log=print, router=None, margin=(.01, .015)):
    """road route for each (stop a, stop b) in pairs; pos: stop -> [lat, lon].
    Returns ({(a, b): [[lat, lon], …]}, [pairs left as straight lines]). A route much longer than the straight line
    is tried once more with forest and field roads; if still too long, the pair is left out (drawn straight)."""
    if router is None:
        lats = [p[0] for p in pos.values()]; lons = [p[1] for p in pos.values()]
        router = TileRouter((min(lats) - margin[0], max(lats) + margin[0], min(lons) - margin[1], max(lons) + margin[1]), log=log)
    R2 = None; legs, odd = {}, []
    bad = lambda m, straight: m is None or m > max(2.5 * straight, straight + 800)
    for a, b in sorted(pairs):
        pa, pb = pos[a], pos[b]
        straight = dist(pa, pb)
        if straight < 5: continue
        path, m = router.route(pa, pb)
        if bad(m, straight):
            if R2 is None: R2 = TileRouter(router.bbox, costs=COST_RELAXED, log=log)
            p2, m2 = R2.route(pa, pb)
            if not bad(m2, straight): path, m = p2, m2
        if bad(m, straight): odd.append((a, b, round(straight), round(m or 0))); continue
        # from the road point next to one stop to the road point next to the other (the stop itself may stand a little
        # off the road; on the map stops are placed onto the drawn line)
        legs[(a, b)] = [[round(p[0], 5), round(p[1], 5)] for p in simplify(path)]
    return legs, odd
