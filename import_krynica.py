#!/usr/bin/env python3
"""Positions of the Krynica-Zdrój and Muszyna stops placed by hand (narzedzia/przystanki-krynica.html, "Pobierz plik")
taken into reczne/krynica_muszyna.json.

A stop with one platform gets the new position (and number). A stop with two platforms (01 and 02, on the two sides of the
street) gets a second stop id (<id>b); each trip then calls at the platform on the right-hand side of its direction of travel
(traffic keeps right), judged from the previous and the next stop of the trip. The notes are printed.
Usage: python3 import_krynica.py przystanki-krynica.json
"""
import json, math, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, 'reczne', 'krynica_muszyna.json')


def street_dir(legs, a, sid, b, cx, cy):
    """direction of travel at a place (x = lon*cos(lat), y = lat): the nearest piece (within ~60 m) of the trip's course
    from the stop before through this one to the stop after"""
    pts = (legs.get('%s %s' % (a, sid)) or []) + (legs.get('%s %s' % (sid, b)) or [])
    best, bd = None, 60 / 110540
    for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]):
        ax, ay = lo1 * math.cos(math.radians(la1)) - cx, la1 - cy
        bx, by = lo2 * math.cos(math.radians(la2)) - cx, la2 - cy
        dx, dy = bx - ax, by - ay; l2 = dx * dx + dy * dy
        if not l2: continue
        u = max(0, min(1, -(ax * dx + ay * dy) / l2)); d = math.hypot(ax + u * dx, ay + u * dy)
        if d < bd: bd, best = d, (dx, dy)
    return best


def main(src):
    D = json.load(open(PATH, encoding='utf-8'))
    U = json.load(open(src, encoding='utf-8'))['stops']
    S = D['stops']
    two = {}
    for sid, u in U.items():
        if sid not in S: print('nieznany przystanek', sid); continue
        ps = u.get('poles') or []
        if u.get('note'): print('UWAGA %s (%s): %s' % (sid, S[sid][0], u['note']))
        if not ps: continue
        p0 = ps[0]
        S[sid][1] = p0.get('p') or (S[sid][1] if len(ps) == 1 else '01')
        S[sid][2], S[sid][3], S[sid][4] = round(p0['lat'], 5), round(p0['lon'], 5), 'user'
        if len(ps) > 1:
            nid = sid + 'b'; p1 = ps[1]
            S[nid] = [S[sid][0], p1.get('p') or '02', round(p1['lat'], 5), round(p1['lon'], 5), 'user']
            two[sid] = nid
    # trips: the platform on the right of the direction of travel
    pos = lambda i: (S[i][3] * math.cos(math.radians(S[i][2])), S[i][2])
    moved = 0
    for t in D['trips']:
        st = t['st']
        for k, x in enumerate(st):
            sid = x[0]
            if sid not in two: continue
            a = st[k - 1][0] if k > 0 else None
            b = st[k + 1][0] if k + 1 < len(st) else None
            pa = pos(a) if a in S else pos(sid); pb = pos(b) if b in S else pos(sid)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            if dx == 0 and dy == 0: continue
            cx = (pos(sid)[0] + pos(two[sid])[0]) / 2; cy = (pos(sid)[1] + pos(two[sid])[1]) / 2
            # the way the street goes there (the trip's course in and out of the stop), so that only the platforms'
            # distance across the street counts, not how far apart along it they are (as in the tool)
            sd = street_dir(D.get('legs') or {}, a, sid, b, cx, cy)
            if sd: dx, dy = sd
            side = lambda i: dx * (pos(i)[1] - cy) - dy * (pos(i)[0] - cx)   # < 0: right of the direction
            if side(two[sid]) < side(sid): x[0] = two[sid]; moved += 1
    # shapes between stops: the same course for the new platform ids
    legs = D.get('legs') or {}
    for key in list(legs):
        a, b = key.split(' ')
        for na in [a, two.get(a)]:
            for nb in [b, two.get(b)]:
                if na and nb and (na, nb) != (a, b): legs.setdefault(na + ' ' + nb, legs[key])
    json.dump(D, open(PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('przystanki: %d, z dwoma peronami: %d, przypisań do drugiego peronu: %d' % (len(U), len(two), moved))


if __name__ == '__main__':
    main(sys.argv[1])
