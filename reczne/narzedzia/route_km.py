"""Street geometry for the Krynica-Zdrój / Muszyna lines, which have no shapes of their own.

1. Stops placed from OpenStreetMap stay put; stops whose position was only estimated (or set to the middle of a
   village) are moved onto the road the bus takes, at the point the timetable puts them between their neighbours.
2. Every pair of consecutive stops gets the road route between them ("legs" in krynica_muszyna.json), which
   build.py joins into the drawing of each route on the map.

Roads: OpenStreetMap, from the OpenFreeMap vector tiles (zoom 14, the same source as the map background), turned
into a road graph here; routes are the shortest by distance, main roads preferred, one-way streets respected.
Usage: python3 route_km.py ../krynica_muszyna.json"""
import json, math, os, sys, collections

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import basemap
from drogi import TileRouter, Z, dist, road_legs

FIXED = ('osm', 'osm-near', 'osm?')   # positions taken from OpenStreetMap stops


def along(path, f):
    """point at fraction f of the length of a polyline"""
    L = [dist(path[i], path[i + 1]) for i in range(len(path) - 1)]; tot = sum(L)
    if not tot: return list(path[0])
    t = f * tot
    for i, l in enumerate(L):
        if t <= l and l:
            u = t / l; return [path[i][0] + (path[i + 1][0] - path[i][0]) * u, path[i][1] + (path[i + 1][1] - path[i][1]) * u]
        t -= l
    return list(path[-1])


def main(fn):
    D = json.load(open(fn, encoding='utf-8'))
    S = D['stops']
    lats = [v[2] for v in S.values()]; lons = [v[3] for v in S.values()]
    R = TileRouter((min(lats) - .01, max(lats) + .01, min(lons) - .015, max(lons) + .015))
    fixed = lambda sid: S[sid][4] in FIXED
    mins = lambda tm: int(tm[:2]) * 60 + int(tm[3:5])
    seqs, seen = [], set()   # each distinct trip: [(stop, minute)]
    for t in D['trips']:
        st = [(sid, mins(tm)) for sid, tm in t['st']]
        st = [x for i, x in enumerate(st) if i == 0 or x[0] != st[i - 1][0]]
        k = tuple(s for s, _ in st)
        if k not in seen: seen.add(k); seqs.append(st)
    # 0. ends of routes without a position of their own (the middle of a village, a guess): onto the nearest road
    ends = {st[0][0] for st in seqs} | {st[-1][0] for st in seqs}
    snapped = 0
    for sid in sorted(ends):
        if fixed(sid): continue
        nn = R.nearest(S[sid][2:4], k=1)
        if not nn: continue
        q = basemap.to_latlon(Z, 0, 0, nn[0][2][0], nn[0][2][1], 4096)
        if dist(q, S[sid][2:4]) > 15: S[sid][2], S[sid][3] = round(q[0], 5), round(q[1], 5); snapped += 1
    print('końcowe przystanki przesunięte na najbliższą drogę:', snapped)
    # 1. stops without a position of their own: on the road between their fixed neighbours (or the ends of the
    #    route), by the timetable
    cand = collections.defaultdict(list)
    for st in seqs:
        anchors = [i for i, (s, _) in enumerate(st) if fixed(s) or i in (0, len(st) - 1)]
        for a, b in zip(anchors, anchors[1:]):
            if b - a < 2: continue
            path, _ = R.route(S[st[a][0]][2:4], S[st[b][0]][2:4])
            if not path: continue
            ta, tb = st[a][1], st[b][1]
            for j in range(a + 1, b):
                f = (st[j][1] - ta) / (tb - ta) if tb > ta else (j - a) / (b - a)
                cand[st[j][0]].append(along(path, min(1, max(0, f))))
    moved = 0
    for sid, ps in cand.items():
        best = min(ps, key=lambda p: sum(dist(p, q) for q in ps))   # the one in the middle of the others
        if dist(best, S[sid][2:4]) > 1: moved += 1
        S[sid][2], S[sid][3] = round(best[0], 5), round(best[1], 5)
    print('przystanki przeniesione na drogę:', moved, 'z', sum(1 for v in S.values() if v[4] not in FIXED))
    # 2. road route between every two consecutive stops
    pairs = {(st[i][0], st[i + 1][0]) for st in seqs for i in range(len(st) - 1)}
    found, odd = road_legs(pairs, {k: v[2:4] for k, v in S.items()}, router=R)
    legs = {a + ' ' + b: pts for (a, b), pts in found.items()}
    print('odcinki po drogach:', len(legs), 'z', len(pairs))
    for a, b, st, m in odd: print('  bez trasy (prosta linia):', S[a][0], S[b][0], st, m)
    D['legs'] = legs
    json.dump(D, open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main(sys.argv[1])
