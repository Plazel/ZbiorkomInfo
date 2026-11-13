"""Schematic network diagram laid out as a mixed-integer programme (the newer way; schematic.py's LOOM is the older one).

Steps:
 1. stations (stops of one name; the two directions' stops named differently and the two stops of a terminal loop are
    one station) and the lines' runs over them, from the route files in data/
 2. corridors: chains of stations between nodes (junctions, line ends, real bends of the street)
 3. octilinear layout (after Nöllenburg & Wolff): every corridor one straight piece at 0°/45°/90°, the order of the
    corridors around a node kept, as few bends of the lines as possible, corridors apart from each other; the centre
    (around the busiest node) drawn larger
 4. the result in the form of data/schema_<area>.json (as schematic.to_schema): nodes [x, y, name, cuts], edges
    [from, to, points, strokes, grey lines, night lines]

Needs numpy and scipy (HiGHS). When they are missing or no layout is found in time, schematic.py's LOOM is used.
"""
import json, math, os, collections, itertools, functools
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix
import schematic

M_PER = 111.0      # metres in one unit of schematic.PJ

DIR = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]   # screen coordinates (y down), 45° steps
SP = 0.17          # distance between two lines of a bundle, in units (one unit = the usual distance between stations)


class Model:
    def __init__(self): self.n = 0; self.lb = []; self.ub = []; self.int = []; self.c = []; self.rows = []
    def var(self, lo, hi, integer=False, cost=0.0):
        self.lb.append(lo); self.ub.append(hi); self.int.append(1 if integer else 0); self.c.append(cost); self.n += 1; return self.n - 1
    def add(self, terms, lo, hi): self.rows.append((terms, lo, hi))
    def solve(self, time_limit=60, gap=0.03):
        A = lil_matrix((len(self.rows), self.n)); lo = np.empty(len(self.rows)); hi = np.empty(len(self.rows))
        for i, (terms, l, h) in enumerate(self.rows):
            acc = collections.defaultdict(float)
            for j, v in terms: acc[j] += v
            for j, v in acc.items(): A[i, j] = v
            lo[i] = l; hi[i] = h
        res = milp(np.array(self.c), constraints=LinearConstraint(A.tocsr(), lo, hi), integrality=np.array(self.int),
                   bounds=Bounds(np.array(self.lb), np.array(self.ub)), options={'time_limit': time_limit, 'mip_rel_gap': gap, 'disp': False})
        return res


def seg_dist(a, b, c, d):
    """smallest distance between segments ab and cd"""
    def pt(p, a, b):
        v = b - a; l2 = float(v @ v); t = max(0.0, min(1.0, float((p - a) @ v) / l2)) if l2 else 0.0
        return float(np.hypot(*(p - a - t * v)))
    def ccw(p, q, r): return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if ccw(a, b, c) * ccw(a, b, d) < 0 and ccw(c, d, a) * ccw(c, d, b) < 0: return 0.0
    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def layout(nodes, cors, G, w_bend=3.0, w_dir=2.0, w_len=1.0, w_geo=0.0, lmin_of=None, sep=0.9, time_limit=60, log=print, wide=1):
    """G: {node: (x, y)} real positions in units. Sets c['dir'] and returns {node: np.array([x, y])}."""
    ix = {n: i for i, n in enumerate(nodes)}; N = len(nodes)
    span = max(max(p[0] for p in G.values()) - min(p[0] for p in G.values()), max(p[1] for p in G.values()) - min(p[1] for p in G.values()))
    need = [max(1.0, (lmin_of(c) if lmin_of else len(c['ch']) - 1)) for c in cors]
    B = max(span * 2.5, sum(need) * 0.6) + 10; M = 2 * B
    md = Model()
    X = [md.var(0, B) for _ in nodes]; Y = [md.var(0, B) for _ in nodes]
    lam = []; alpha = []; dexpr = []
    for ci, c in enumerate(cors):
        u, v = ix[c['ch'][0]], ix[c['ch'][-1]]
        a = np.array(G[c['ch'][0]]); b = np.array(G[c['ch'][-1]])
        ang = math.atan2(b[1] - a[1], b[0] - a[0]); s = round(ang / (math.pi / 4)) % 8
        c['sec'] = s
        cand = [(s + d) % 8 for d in range(-wide, wide + 1)]
        L = md.var(need[ci] * 0.7, B, cost=w_len * (1 + 0.15 * len(c['lines']))); lam.append(L)
        al = {}
        for k in cand:
            off = min((k - s) % 8, (s - k) % 8)
            al[k] = md.var(0, 1, True, cost=w_dir * off * (1 + 0.1 * (len(c['ch']) - 1)))
            dx, dy = DIR[k]
            md.add([(X[v], 1), (X[u], -1), (L, -dx), (al[k], M)], -np.inf, M)
            md.add([(X[v], -1), (X[u], 1), (L, dx), (al[k], M)], -np.inf, M)
            md.add([(Y[v], 1), (Y[u], -1), (L, -dy), (al[k], M)], -np.inf, M)
            md.add([(Y[v], -1), (Y[u], 1), (L, dy), (al[k], M)], -np.inf, M)
        md.add([(j, 1) for j in al.values()], 1, 1)
        # as long as its stations need; a diagonal's length is counted along an axis (×√2 on paper)
        md.add([(L, 1)] + [(al[k], -need[ci] * (0.72 if k % 2 else 1.0)) for k in cand], 0, np.inf)
        alpha.append(al)
        dexpr.append(([(al[k], k) for k in cand], [(al[k], (k + 4) % 8) for k in cand]))   # running u→v, v→u
    # the corridors around a node keep their order (so they also all leave it in different directions)
    inc = collections.defaultdict(list)
    for ci, c in enumerate(cors):
        a = np.array(G[c['ch'][0]]); b = np.array(G[c['ch'][-1]])
        # the bearing a corridor leaves a node with: towards its first station there
        inc[c['ch'][0]].append((ci, 0)); inc[c['ch'][-1]].append((ci, 1))
    def bearing(ci, end, st_pos):
        ch = cors[ci]['ch']; a, b = (ch[0], ch[1]) if end == 0 else (ch[-1], ch[-2])
        pa, pb = st_pos[a], st_pos[b]; return math.atan2(pb[1] - pa[1], pb[0] - pa[0])
    return md, X, Y, lam, alpha, dexpr, inc, ix, need, B, M, bearing


def solve(nodes, cors, G, ST, w_bend=3.0, w_dir=2.0, w_len=1.0, w_geo=0.0, lmin_of=None, sep=1.25, time_limit=60, log=print,
          rounds=10, anchors=None):
    """ST: {station: (x, y)} in units, all stations (for the bearings at the nodes)."""
    for wide in (1, 2):
        md, X, Y, lam, alpha, dexpr, inc, ix, need, B, M, bearing = layout(nodes, cors, G, w_bend, w_dir, w_len, w_geo, lmin_of, sep, time_limit, log, wide)
        for n, lst in inc.items():
            if len(lst) < 2: continue
            lst = sorted(lst, key=lambda t: bearing(t[0], t[1], ST))
            beta = [md.var(0, 1, True) for _ in lst]
            md.add([(b, 1) for b in beta], 1, 1)
            for i in range(len(lst)):
                (c1, e1), (c2, e2) = lst[i], lst[(i + 1) % len(lst)]
                md.add([(j, v) for j, v in dexpr[c1][e1]] + [(j, -v) for j, v in dexpr[c2][e2]] + [(beta[i], -8)], -np.inf, -1)
        # bends of the lines at the nodes
        for n, lst in inc.items():
            for (c1, e1), (c2, e2) in itertools.combinations(lst, 2):
                nl = len(cors[c1]['lines'] & cors[c2]['lines'])
                if not nl: continue
                b = md.var(0, 4, cost=w_bend * nl ** 0.6); d1 = md.var(0, 1, True); d2 = md.var(0, 1, True)
                # running into the node along c1 (the opposite of leaving it), out along c2
                t_in = dexpr[c1][1 - e1]; t_out = dexpr[c2][e2]
                terms = [(j, v) for j, v in t_in] + [(j, -v) for j, v in t_out] + [(d1, -8), (d2, 8)]
                md.add(terms + [(b, -1)], -np.inf, 0); md.add([(j, -v) for j, v in terms] + [(b, -1)], -np.inf, 0)
        if w_geo:   # near the real places (up to a shift of the whole map)
            ox = md.var(-1e7, 1e7); oy = md.var(-1e7, 1e7)
            for n in (anchors if anchors is not None else nodes):
                for V, o, g in ((X, ox, G[n][0]), (Y, oy, G[n][1])):
                    t = md.var(0, B, cost=w_geo)
                    md.add([(V[ix[n]], 1), (o, -1), (t, -1)], -np.inf, g); md.add([(V[ix[n]], -1), (o, 1), (t, -1)], -np.inf, -g)
        width = [SP * len(c['lines']) for c in cors]
        # corridors joined by a third one cannot be farther apart than that one is long
        link = {}
        for m, c in enumerate(cors): link[frozenset((c['ch'][0], c['ch'][-1]))] = need[m]
        def dreq_of(i, j):
            d = sep + (width[i] + width[j]) / 2
            for a in (cors[i]['ch'][0], cors[i]['ch'][-1]):
                for b in (cors[j]['ch'][0], cors[j]['ch'][-1]):
                    if frozenset((a, b)) in link: d = min(d, 0.55 * link[frozenset((a, b))])
            return d
        sep_req = {}; res = None; P = None
        # corridors that really cross (tracks crossing with no common stop) may cross on the diagram too
        cross = set()
        def ccw(p, q, r): return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        for i, j in itertools.combinations(range(len(cors)), 2):
            if set(cors[i]['ch']) & set(cors[j]['ch']): continue
            A = [ST[n] for n in cors[i]['ch']]; Bc = [ST[n] for n in cors[j]['ch']]
            if any(ccw(a, b, c) * ccw(a, b, d) < 0 and ccw(c, d, a) * ccw(c, d, b) < 0 for a, b in zip(A, A[1:]) for c, d in zip(Bc, Bc[1:])):
                cross.add((i, j)); log('  krzyżują się w terenie: %s–%s × %s–%s' % (cors[i]['ch'][0], cors[i]['ch'][-1], cors[j]['ch'][0], cors[j]['ch'][-1]))
        def add_sep(i, j, dreq):
            gam = [md.var(0, 1, True) for _ in range(8)]
            md.add([(g, 1) for g in gam], 1, np.inf)
            for k in range(8):
                dx, dy = DIR[k]; s = math.sqrt(2) if k % 2 else 1.0
                for a in (cors[i]['ch'][0], cors[i]['ch'][-1]):
                    for b in (cors[j]['ch'][0], cors[j]['ch'][-1]):
                        md.add([(X[ix[b]], dx), (Y[ix[b]], dy), (X[ix[a]], -dx), (Y[ix[a]], -dy), (gam[k], -2 * M)], dreq * s - 2 * M, np.inf)
        base = (md.n, len(md.rows))
        def rebuild():
            md.n = base[0]; del md.lb[base[0]:], md.ub[base[0]:], md.int[base[0]:], md.c[base[0]:], md.rows[base[1]:]
            for (i, j), d in sep_req.items(): add_sep(i, j, d)
        for rnd in range(rounds):
            r = md.solve(time_limit=time_limit)
            if r.x is None:
                if not sep_req or rnd > rounds - 2: log('  brak rozwiązania (%s)' % r.message); break
                # the last pairs asked too much: half the distance for them
                for key in last: sep_req[key] *= 0.5
                log('  runda %d: nie da się – mniejszy odstęp dla %d par' % (rnd + 1, len(last))); rebuild(); continue
            res = r; P = {n: np.array([r.x[X[ix[n]]], r.x[Y[ix[n]]]]) for n in nodes}
            bad = []
            for i, j in itertools.combinations(range(len(cors)), 2):
                a, b = cors[i]['ch'][0], cors[i]['ch'][-1]; c, d = cors[j]['ch'][0], cors[j]['ch'][-1]
                if {a, b} & {c, d} or (i, j) in sep_req or (i, j) in cross: continue
                dreq = dreq_of(i, j)
                if seg_dist(P[a], P[b], P[c], P[d]) < dreq - 1e-6: bad.append((i, j, dreq))
            log('  runda %d: cel %.1f, za blisko siebie: %d par' % (rnd + 1, r.fun, len(bad)))
            if not bad: break
            last = [(i, j) for i, j, _ in bad]
            for i, j, dreq in bad: sep_req[(i, j)] = dreq; add_sep(i, j, dreq)
        if res is not None: break
        log('  ponownie z szerszym wyborem kierunków')
    if res is None: raise RuntimeError('układ nieznaleziony')
    for ci, c in enumerate(cors):
        c['dir'] = max(alpha[ci], key=lambda k: res.x[alpha[ci][k]])
    return P


def unit(v):
    l = float(np.hypot(*v)); return v / l if l else v


def prepare(nodes, cors, P):
    at = collections.defaultdict(list)
    for ci, c in enumerate(cors):
        c['a'] = P[c['ch'][0]]; c['b'] = P[c['ch'][-1]]; c['t'] = unit(c['b'] - c['a']); c['nrm'] = np.array([c['t'][1], -c['t'][0]])
        c['len'] = float(np.hypot(*(c['b'] - c['a']))); n = len(c['ch']) - 1
        c['sp'] = [c['a'] + (c['b'] - c['a']) * i / n for i in range(n + 1)]
        at[c['ch'][0]].append((ci, 0)); at[c['ch'][-1]].append((ci, 1))
    return at


def order_lines(cors, at, P, rank):
    """left-to-right order of the lines on every corridor (seen along it): of two lines the one that turns off to the
    left where they part (looking ahead, else looking back) lies on the left, so bundles part without crossing"""
    def walk(ci, toward, A, B):
        for _ in range(60):
            c = cors[ci]; node = c['ch'][-1] if toward else c['ch'][0]
            tin = c['t'] if toward else -c['t']
            def turn(x):
                cj, e = x; out = cors[cj]['t'] if e == 0 else -cors[cj]['t']
                return math.atan2(tin[0] * out[1] - tin[1] * out[0], tin[0] * out[0] + tin[1] * out[1])
            nA = [x for x in at[node] if x[0] != ci and A in cors[x[0]]['lines']]
            nB = [x for x in at[node] if x[0] != ci and B in cors[x[0]]['lines']]
            common = [x for x in nA if x in nB]
            if common:
                cj, e = min(common, key=lambda x: abs(turn(x))); ci = cj; toward = 1 - e; continue
            ta = sum(turn(x) for x in nA) / len(nA) if nA else None; tb = sum(turn(x) for x in nB) / len(nB) if nB else None
            if ta is not None and tb is not None: return 1 if ta < tb - 1e-6 else -1 if tb < ta - 1e-6 else 0
            if ta is not None: return 1 if ta < -0.1 else -1 if ta > 0.1 else 0
            if tb is not None: return -1 if tb < -0.1 else 1 if tb > 0.1 else 0
            return 0
        return 0
    for ci, c in enumerate(cors):
        def cmp(A, B):
            r = walk(ci, 1, A, B)
            if r: return -r
            r = walk(ci, 0, A, B)
            if r: return r
            return -1 if (rank.get(A, 0), A) < (rank.get(B, 0), B) else 1
        c['ord'] = sorted(c['lines'], key=functools.cmp_to_key(cmp))


def dp_keep(pts, tol):
    """indices kept by Douglas-Peucker"""
    keep = {0, len(pts) - 1}; stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop(); a, b = pts[i0], pts[i1]; dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
        best = (0, None)
        for i in range(i0 + 1, i1):
            px, py = pts[i][0] - a[0], pts[i][1] - a[1]
            t = max(0.0, min(1.0, (px * dx + py * dy) / l2)) if l2 else 0.0
            d = math.hypot(px - t * dx, py - t * dy)
            if d > best[0]: best = (d, i)
        if best[1] is not None and best[0] > tol: keep.add(best[1]); stack += [(i0, best[1]), (best[1], i1)]
    return keep


def graph(st, seqs, bend_tol=300.0):
    """corridors: chains of stations between nodes (junctions, line ends, places where the set of lines changes and
    where the street really turns – by more than bend_tol metres off the straight line)"""
    E = collections.defaultdict(set); fwd = collections.Counter()
    for k, ss in seqs.items():
        for seq in ss:
            for a, b in zip(seq, seq[1:]): E[frozenset((a, b))].add(k); fwd[(a, b)] += 1
    adj = collections.defaultdict(set)
    for e in E:
        a, b = tuple(e); adj[a].add(b); adj[b].add(a)
    ends = {seq[0] for ss in seqs.values() for seq in ss} | {seq[-1] for ss in seqs.values() for seq in ss}
    def is_node(n):
        if len(adj[n]) != 2 or n in ends: return True
        a, b = sorted(adj[n]); return E[frozenset((n, a))] != E[frozenset((n, b))]
    nodes = {n for n in adj if is_node(n)}
    if not nodes: nodes = {sorted(adj)[0]}
    chains = []; seen = set()
    for u in sorted(nodes):
        for v in sorted(adj[u]):
            if frozenset((u, v)) in seen: continue
            ch = [u, v]; seen.add(frozenset((u, v)))
            while ch[-1] not in nodes:
                nx = next(x for x in sorted(adj[ch[-1]]) if x != ch[-2]); seen.add(frozenset((ch[-1], nx))); ch.append(nx)
            chains.append(ch)
    # two chains between the same pair of nodes, or a chain back to its own start: a middle station becomes a node
    count = collections.Counter(frozenset((c[0], c[-1])) for c in chains)
    out = []
    for ch in chains:
        cuts = dp_keep([st[n] for n in ch], bend_tol)
        if (count[frozenset((ch[0], ch[-1]))] > 1 or ch[0] == ch[-1]) and len(ch) > 2 and len(cuts) == 2: cuts.add(len(ch) // 2)
        if ch[0] == ch[-1] and len(ch) > 3 and len(cuts) < 4: cuts |= {len(ch) // 3, 2 * len(ch) // 3}
        cuts = sorted(cuts)
        for i0, i1 in zip(cuts, cuts[1:]):
            part = ch[i0:i1 + 1]
            lines = set(E[frozenset((part[0], part[1]))])
            ow = 0
            if all(fwd[(b, a)] == 0 for a, b in zip(part, part[1:])): ow = 1
            elif all(fwd[(a, b)] == 0 for a, b in zip(part, part[1:])): ow = -1
            out.append({'ch': part, 'lines': lines, 'oneway': ow})
    nodes = sorted({c['ch'][0] for c in out} | {c['ch'][-1] for c in out})
    return nodes, out


# ---------------------------------------------------------------------------------------------------------------------
def main_patterns(d):
    """stop patterns a direction mostly runs (those of at least a quarter of the trips of its commonest one)"""
    tp = d.get('tp') or {}
    k = next((k for k in ('w0', 'w1', 's0', 'h0') if k in tp), None) or next(iter(sorted(tp)), None)
    if k is None or not d.get('plans'): return [d['pats'][0]] if d.get('pats') else []
    use = collections.Counter()
    for t0, pi, *_ in d['plans'][tp[k]]: use[d['prof'][pi][0]] += 1
    if not use: return [d['pats'][0]]
    top = max(use.values())
    return [d['pats'][p] for p, c in sorted(use.items()) if c >= top * 0.25]


def network(data_dir, pick, box_stop=None, clip_by=None, merge_m=350.0):
    """-> st {key: (x, y) metres}, name {key: name}, seqs {route id: [[keys]]}, cuts {key: [[route id, terminus name]]}"""
    idx = json.load(open(os.path.join(data_dir, 'index.json'), encoding='utf-8'))
    stops = idx['stops']; routes = [r for r in idx['routes'] if pick(r)]
    runs = []
    for r in routes:
        if r.get('rp'):
            if r['rp'] not in schematic._PACKS: schematic._PACKS[r['rp']] = json.load(open(os.path.join(data_dir, 'rp', r['rp'] + '.json'), encoding='utf-8'))
            d = schematic._PACKS[r['rp']][r['id']]
        else: d = json.load(open(os.path.join(data_dir, 'r', r['id'] + '.json'), encoding='utf-8'))
        for dd in d['dirs']:
            for pat in main_patterns(dd):
                ids = [dd['stops'][i][0] for i in pat if dd['stops'][i][0] in stops]
                if len(ids) > 1: runs.append((r, ids))
    used = {s for _, ids in runs for s in ids}
    st_of, st_pos, st_name = schematic.stations(stops, used)
    raw = collections.defaultdict(list)
    for r, ids in runs:
        seq = []
        for s in ids:
            k = st_of[s]
            if not seq or seq[-1] != k: seq.append(k)
        if len(seq) > 1: raw[r['id']].append(seq)
    xy = {k: (p[0] * M_PER, p[1] * M_PER) for k, p in st_pos.items()}
    # stops of different names that are one place: close together, never both on one run, and between the same
    # neighbours (the two directions' stops – Urząd Miejski / Nowe Ogrody), or the arriving and the departing stop of a
    # terminal loop, or platforms of one station (the same first word)
    together = set(); cnt = collections.Counter(); nb = collections.defaultdict(set); first = set(); last = set(); inner = set()
    for ss in raw.values():
        for seq in ss:
            first.add(seq[0]); last.add(seq[-1]); inner |= set(seq[1:-1])
            for n in set(seq): cnt[n] += 1
            for a, b in zip(seq, seq[1:]): nb[a].add(b); nb[b].add(a)
            for i, a in enumerate(seq):
                for b in seq[i + 1:]: together.add(frozenset((a, b)))
    def one_place(a, b, dist):
        if nb[a] == nb[b] or (len(nb[a]) >= 2 and nb[a] <= nb[b]) or (len(nb[b]) >= 2 and nb[b] <= nb[a]): return True
        if a not in inner and b not in inner and ((a in last and b in first) or (b in last and a in first)) and not (nb[a] & nb[b]): return True
        return st_name[a].split()[0] == st_name[b].split()[0] and dist < 200
    parent = {n: n for n in xy}
    def find(n):
        while parent[n] != n: n = parent[n]
        return n
    names = sorted(xy); members = {n: {n} for n in names}
    # (a grid so that only near pairs are compared)
    cell = collections.defaultdict(list)
    for n in names: cell[(int(xy[n][0] // merge_m), int(xy[n][1] // merge_m))].append(n)
    pairs = []
    for (cx, cy), ns in cell.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a in ns:
                    for b in cell.get((cx + dx, cy + dy), ()):
                        if a < b:
                            dist = math.hypot(xy[a][0] - xy[b][0], xy[a][1] - xy[b][1])
                            if dist <= merge_m: pairs.append((dist, a, b))
    for dist, a, b in sorted(pairs):
        ra, rb = find(a), find(b)
        if ra == rb: continue
        if any(frozenset((p, q)) in together for p in members[ra] for q in members[rb]): continue
        if not one_place(a, b, dist): continue
        parent[rb] = ra; members[ra] |= members.pop(rb)
    key_of = {}; st = {}; name = {}
    for r, ms in members.items():
        top = sorted(ms, key=lambda n: (-cnt[n], n))[0]; w = sum(cnt[m] for m in ms) or 1
        st[top] = (sum(xy[m][0] * cnt[m] for m in ms) / w, sum(xy[m][1] * cnt[m] for m in ms) / w); name[top] = st_name[top]
        for m in ms: key_of[m] = top
    # the area: of the given stops (the stops in Gdańsk) or of the given lines, with a margin; lines are cut at its edge
    box = None
    if clip_by or box_stop:
        by_id = {r['id']: r for r in routes}
        ps = [st_pos[st_of[s]] for r, ids in runs if (box_stop is None and clip_by(r)) for s in ids] \
            + [st_pos[st_of[s]] for r, ids in runs if box_stop is not None for s in ids if box_stop(stops[s])]
        if ps:
            m = 20.0
            box = ((min(p[0] for p in ps) - m) * M_PER, (min(p[1] for p in ps) - m * .7) * M_PER, (max(p[0] for p in ps) + m) * M_PER, (max(p[1] for p in ps) + m * .7) * M_PER)
    inside = lambda k: box is None or (box[0] <= st[k][0] <= box[2] and box[1] <= st[k][1] <= box[3])
    seqs = collections.defaultdict(list); cuts = collections.defaultdict(list)
    for rid, ss in raw.items():
        for seq0 in ss:
            seq = []
            for n in seq0:
                n = key_of[n]
                if not seq or seq[-1] != n: seq.append(n)
            ins = [inside(n) for n in seq]; run = []
            for i, n in enumerate(seq):
                if ins[i]: run.append(n); continue
                if len(run) > 1: seqs[rid].append(run)
                n_after = sum(ins[i + 1:]); n_before = sum(ins[:i])
                if len(run) > 1 and n_after < 2 and [rid, name[seq[-1]]] not in cuts[run[-1]]: cuts[run[-1]].append([rid, name[seq[-1]]])
                later = next((m for j, m in enumerate(seq[i + 1:]) if ins[i + 1 + j]), None)
                if later and n_before < 2 and n_after > 1 and [rid, name[seq[0]]] not in cuts[later]: cuts[later].append([rid, name[seq[0]]])
                run = []
            if len(run) > 1: seqs[rid].append(run)
    keep = {n for ss in seqs.values() for seq in ss for n in seq}
    return {n: st[n] for n in keep}, name, dict(seqs), {n: v for n, v in cuts.items() if n in keep and v}


def warp_of(geo, lay):
    """geo (metres) -> layout units: scale and shift, then the stations' displacement field (thin-plate spline)"""
    from scipy.interpolate import RBFInterpolator
    names = sorted(set(geo) & set(lay))
    src = np.array([geo[n] for n in names]); dst = np.array([lay[n] for n in names])
    k = float(np.median(np.hypot(*(dst - dst.mean(0)).T)) / max(1.0, np.median(np.hypot(*(src - src.mean(0)).T))))
    s0 = src.mean(0); base = (src - s0) * k + dst.mean(0)
    f = RBFInterpolator(base, dst - base, kernel='thin_plate_spline', smoothing=len(names) * 0.3)
    return lambda pts: (lambda b: b + f(b))((np.array(pts, float) - s0) * k + dst.mean(0))


def octi_path(a, b, mids):
    """a – b as two octilinear pieces (one straight, one at 45°), the bend on the side nearer the stations between them"""
    d = b - a; ax, ay = abs(d[0]), abs(d[1]); sx, sy = np.sign(d[0]) or 1, np.sign(d[1]) or 1
    if min(ax, ay) < 1e-6 or abs(ax - ay) < 1e-6: return [a, b]
    m = min(ax, ay); diag = np.array([sx * m, sy * m])
    c1 = a + diag; c2 = b - diag                    # diagonal first / straight first
    if not len(mids): return [a, c1, b]
    cost = lambda c: sum(min(float(np.hypot(*(p - q))) for q in (a + (c - a) * t for t in np.linspace(0, 1, 9))) +
                         0 for p in mids)
    def near(c):
        tot = 0.0
        for p in mids:
            best = 1e9
            for u, v in ((a, c), (c, b)):
                w = v - u; l2 = float(w @ w); t = max(0.0, min(1.0, float((p - u) @ w) / l2)) if l2 else 0.0
                best = min(best, float(np.hypot(*(p - u - t * w))))
            tot += best
        return tot
    return [a, c1, b] if near(c1) <= near(c2) else [a, c2, b]


def along(poly, n):
    """n + 1 points evenly along a polyline, with the polyline's corners between them: [(point, corners since last)]"""
    L = [0.0]
    for p, q in zip(poly, poly[1:]): L.append(L[-1] + float(np.hypot(*(q - p))))
    pts = []
    for i in range(n + 1):
        t = L[-1] * i / n; j = 0
        while j < len(L) - 2 and L[j + 1] < t: j += 1
        f = (t - L[j]) / ((L[j + 1] - L[j]) or 1); pts.append((poly[j] + (poly[j + 1] - poly[j]) * f, t))
    out = []
    for i in range(n):
        t0, t1 = pts[i][1], pts[i + 1][1]
        mid = [poly[k] for k in range(1, len(poly) - 1) if t0 < L[k] < t1]
        out.append([pts[i][0]] + mid + [pts[i + 1][0]])
    return out


def build(data_dir, pick, box_stop=None, clip_by=None, kind=None, centre=(7.0, 0.9), time_limit=120, max_nodes=160, bg=True, log=print):
    """the diagram of the picked lines: {'n': [[x, y, name(, cuts)]], 'e': [[from, to, [x1, y1, …], strokes(, grey, night)]],
    'bg': the landscape}. The trams, trolleybuses and buses are laid out by the programme; the railway (few long lines
    beside them) is put in afterwards where its stations fall among them, each run between its junctions drawn as two
    octilinear pieces"""
    idx = json.load(open(os.path.join(data_dir, 'index.json'), encoding='utf-8'))
    rail_ids = {r['id'] for r in idx['routes'] if r['t'] == 'rail'}
    st, name, seqs, cuts = network(data_dir, pick, box_stop, clip_by)
    if not seqs: return None
    base = {k: v for k, v in seqs.items() if k not in rail_ids} or seqs
    rail = {k: v for k, v in seqs.items() if k in rail_ids and base is not seqs}
    nodes, cors = graph(st, base)
    if len(nodes) > max_nodes: raise RuntimeError('za duża sieć (%d węzłów)' % len(nodes))
    dd = sorted(math.hypot(st[a][0] - st[b][0], st[a][1] - st[b][1]) for c in cors for a, b in zip(c['ch'], c['ch'][1:]))
    u = dd[len(dd) // 2] or 400.0
    ST = {n: (v[0] / u, v[1] / u) for n, v in st.items()}; G = {n: ST[n] for n in nodes}
    deg = collections.Counter()
    for c in cors:
        for n in (c['ch'][0], c['ch'][-1]): deg[n] += len(c['lines'])
    cx = np.array(G[max(nodes, key=lambda n: (deg[n], n))])
    def lmin(c):
        n = len(c['ch']) - 1; w = SP * len(c['lines'])
        L = max(n * 1.0, 1.0 + 0.9 * w, 1.6 if n == 1 else 0)
        if centre:
            mid = (np.array(ST[c['ch'][0]]) + np.array(ST[c['ch'][-1]])) / 2
            L *= 1 + centre[1] * max(0.0, 1 - float(np.hypot(*(mid - cx))) / centre[0])
        return L
    # parts of the network not joined to each other: two far-apart nodes of each held near their real places
    par = {n: n for n in nodes}
    def fd(n):
        while par[n] != n: n = par[n]
        return n
    for c in cors: par[fd(c['ch'][0])] = fd(c['ch'][-1])
    comp = collections.defaultdict(list)
    for n in nodes: comp[fd(n)].append(n)
    anchors = []
    if len(comp) > 1:
        for ns in comp.values():
            a = max(ns, key=lambda n: (G[n][0] + G[n][1], n)); b = max(ns, key=lambda n: (math.hypot(G[n][0] - G[a][0], G[n][1] - G[a][1]), n))
            anchors += [a] + ([b] if b != a else [])
    P = solve(nodes, cors, G, ST, w_dir=5.0, w_geo=0.5 if anchors else 0.0, anchors=anchors, lmin_of=lmin, time_limit=time_limit, log=log)
    at = prepare(nodes, cors, P)
    rank = {l: i for i, l in enumerate(sorted({l for c in cors for l in c['lines']}, key=lambda x: (len(x), x)))}
    order_lines(cors, at, P, rank)
    S = {}
    pieces = []          # (a, b, points, ordered lines)
    for c in cors:
        for n, p in zip(c['ch'], c['sp']): S.setdefault(n, p)
        for a, b in zip(c['ch'], c['ch'][1:]): pieces.append((a, b, [S[a], S[b]], c['ord']))
    if rail:
        W = warp_of(st, S)
        rn, rc = graph(st, rail, bend_tol=600.0)
        for n in rn:
            if n not in S: S[n] = W([st[n]])[0]
        for c in rc:
            a, b = c['ch'][0], c['ch'][-1]
            mids = W([st[n] for n in c['ch'][1:-1]]) if len(c['ch']) > 2 else []
            poly = octi_path(np.array(S[a], float), np.array(S[b], float), list(mids))
            segs = along(poly, len(c['ch']) - 1)
            for k2, (x, y) in enumerate(zip(c['ch'], c['ch'][1:])):
                if 0 < k2 + 1 < len(c['ch']) - 1 and c['ch'][k2 + 1] not in S: S[c['ch'][k2 + 1]] = segs[k2][-1]
                pieces.append((x, y, segs[k2], sorted(c['lines'])))
    mn = np.min(np.array(list(S.values())), 0)
    ix = {n: i for i, n in enumerate(sorted(S))}
    out_n = [[round(float(S[n][0] - mn[0]), 3), round(float(S[n][1] - mn[1]), 3), name[n]] + ([cuts[n]] if n in cuts else []) for n in sorted(S)]
    out_e = []
    for a, b, pts, ordl in pieces:
        strokes, gm, nm = schematic.bundle(ordl, kind or {})
        flat = []
        for q in pts: flat += [round(float(q[0] - mn[0]), 3), round(float(q[1] - mn[1]), 3)]
        flat[:2] = out_n[ix[a]][:2]; flat[-2:] = out_n[ix[b]][:2]
        out_e.append([ix[a], ix[b], flat, strokes] + ([gm, nm] if nm else [gm] if gm else []))
    res = {'n': out_n, 'e': out_e}
    if bg:
        try: res['bg'] = landscape(st, {n: (float(S[n][0] - mn[0]), float(S[n][1] - mn[1])) for n in S}, log=log)
        except Exception as e: log('  tło schematu: %s' % str(e)[:120])
    return res


def landscape(geo, lay, z=12, log=print):
    """water, woods, parks and beaches around the network, bent onto the layout (so the sea, the rivers and the woods lie
    where the stations beside them are drawn): {'w': [[x1, y1, x2, y2, …]], 'f': …, 'g': …, 'b': …} in layout units.
    geo: {station: (x, y)} metres as in network(); lay: {station: (x, y)} layout units. Tiles: OpenFreeMap (as basemap.py)."""
    import basemap, concurrent.futures
    from scipy.interpolate import RBFInterpolator
    names = sorted(set(geo) & set(lay))
    src = np.array([geo[n] for n in names]); dst = np.array([lay[n] for n in names])
    k = float(np.median(np.hypot(*(dst - dst.mean(0)).T)) / max(1.0, np.median(np.hypot(*(src - src.mean(0)).T))))   # units per metre
    s0 = src.mean(0); base = (src - s0) * k + dst.mean(0)
    f = RBFInterpolator(base, dst - base, kernel='thin_plate_spline', smoothing=len(names) * 0.3)
    warp = lambda pts: (lambda b: b + f(b))((np.array(pts) - s0) * k + dst.mean(0))
    to_ll = lambda x, y: (-y / M_PER / 1000.0, x / M_PER / 1000.0 / schematic.COS)
    la0, lo0 = to_ll(src[:, 0].min() - 4000, src[:, 1].max() + 4000); la1, lo1 = to_ll(src[:, 0].max() + 4000, src[:, 1].min() - 4000)
    tj = json.loads(basemap.fetch(basemap.TILEJSON)); url = tj['tiles'][0]
    x0, y1 = basemap.tile_of(la0, lo0, z); x1, y0 = basemap.tile_of(la1, lo1, z)
    jobs = [(z, x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(min(y0, y1), max(y0, y1) + 1)]
    def one(j):
        try: return j, basemap.decode_tile(basemap.fetch(url.replace('{z}', str(j[0])).replace('{x}', str(j[1])).replace('{y}', str(j[2]))), {'water', 'landcover', 'park'})
        except Exception: return j, {}
    lo = dst.min(0) - 6; hi = dst.max(0) + 6; out = {'w': [], 'f': [], 'g': [], 'b': []}
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for (zz, tx, ty), layers in ex.map(one, jobs):
            for lname, feats in layers.items():
                for props, typ, parts, ext in feats:
                    kd = basemap.classify(lname, props, typ)
                    if kd not in out: continue
                    for part in parts:
                        ll = [basemap.to_latlon(zz, tx, ty, px, py, ext) for px, py in part]
                        pts = [(lon * schematic.COS * 1000.0 * M_PER, -lat * 1000.0 * M_PER) for lat, lon in ll]
                        if len(pts) < 3: continue
                        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                        if (max(xs) - min(xs)) * (max(ys) - min(ys)) < 60000: continue      # (smaller than about 250 × 250 m)
                        q = warp(pts)
                        if q[:, 0].max() < lo[0] or q[:, 0].min() > hi[0] or q[:, 1].max() < lo[1] or q[:, 1].min() > hi[1]: continue
                        q = basemap.rdp([tuple(p) for p in np.clip(q, lo - 4, hi + 4)], 0.06)
                        if len(q) >= 3: out[kd].append([round(float(v), 2) for p in q for v in p])
    log('  tło schematu: %s' % ', '.join('%s %d' % (k2, len(v)) for k2, v in out.items()))
    return out
