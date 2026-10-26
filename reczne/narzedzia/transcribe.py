"""Transcribe Krynica-Zdrój (MPGK) and Muszyna (Zapopradzie) timetable PDFs into one JSON file of trips."""
import json, re, sys, os, collections
import pdfplumber
sys.path.insert(0, os.path.dirname(__file__))
KM = sys.argv[1]           # folder with the PDFs and OCR results
OUT = sys.argv[2]
TIME = re.compile(r'^\d{1,2}[:;]\d{2}$')


def rows_of(path):
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            rows = []
            for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
                yc = (w['top'] + w['bottom']) / 2
                for r in rows:
                    if abs(r['y'] - yc) < 3.0: r['w'].append(w); break
                else: rows.append({'y': yc, 'w': [w]})
            for r in sorted(rows, key=lambda r: r['y']):
                r['w'].sort(key=lambda w: w['x0'])
                out.append({'p': pi, 'y': r['y'], 'w': [((w['x0'] + w['x1']) / 2, w['x0'], w['text']) for w in r['w']]})
    return out


def tmin(t):
    h, m = t.replace(';', ':').split(':'); return int(h) * 60 + int(m)


def cluster(xs, tol=9):
    cs = []
    for x in sorted(xs):
        if cs and x - cs[-1][-1] <= tol: cs[-1].append(x)
        else: cs.append([x])
    return [sum(c) / len(c) for c in cs]


def trips_from_table(rows, colx=None):
    """rows: [(name, [(x, 'HH:MM')])] in table order -> trips [[(row index, name, minute)]]"""
    xs = [x for _, ts in rows for x, _ in ts]
    if not xs: return []
    cols = colx or cluster(xs)
    bycol = collections.defaultdict(list)
    for ri, (name, ts) in enumerate(rows):
        for x, t in ts:
            ci = min(range(len(cols)), key=lambda i: abs(cols[i] - x))
            bycol[ci].append((ri, name, tmin(t)))
    trips = []
    for ci in sorted(bycol):
        pts = bycol[ci]
        if len(pts) < 2: continue
        # does the column run down the table or up (some tables list a return trip bottom-up)?
        up = sum(1 for a, b in zip(pts, pts[1:]) if b[2] < a[2]) > sum(1 for a, b in zip(pts, pts[1:]) if b[2] > a[2])
        pts = sorted(pts, key=lambda p: (p[2], -p[0] if up else p[0]))
        cur = [pts[0]]
        for p in pts[1:]:
            if p[2] - cur[-1][2] > 45: trips.append((ci, cur)); cur = [p]
            else: cur.append(p)
        trips.append((ci, cur))
    # a few times are printed off their column (e.g. the last stops of a trip): join a short piece to the trip it continues
    trips = [list(x) for x in trips]
    changed = True
    while changed:
        changed = False
        for A in trips:
            for B in trips:
                if A is B or not A[1] or not B[1]: continue
                a, b = A[1][-1], B[1][0]
                if 0 <= b[2] - a[2] <= 3 and min(len(A[1]), len(B[1])) <= 4 and A[0] != B[0] and not set(r[0] for r in A[1]) & set(r[0] for r in B[1]):
                    A[1] = A[1] + B[1]; B[1] = []; changed = True
    return [(ci, t) for ci, t in trips if len(t) >= 2]


# ---------------- names ----------------
def tc(s):
    """SZPITAL WOJSKOWY -> Szpital Wojskowy (words in capitals only)"""
    return ' '.join(w if not (w.isupper() and len(w) > 2) else w[0] + w[1:].lower() for w in s.split())


def mpgk_name(raw):
    s = raw.replace('Czany', 'Czarny').replace('mochnaczka', 'Mochnaczka').strip()
    pole = ''
    m = re.search(r'/\s*(\w+)(\s*/\s*\w+)?\s*$', s)
    if m: pole = m.group(1); s = s[:m.start()].strip()
    s = s.rstrip('/ ').strip()
    s = re.sub(r'^Krynica-Zdrój\s*ul\.?\s*', '', s)
    s = re.sub(r'^Krynica-Zdrój\s+', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return tc(s), pole


def zap_name(raw):
    s = re.sub(r'\s+', ' ', raw).strip()
    fixes = {'StacjaNarciarska': 'Stacja Narciarska', 'DomOciemniałych': 'Dom Ociemniałych', 'ZdrójSkrzyżowanie': 'Zdrój Skrzyżowanie',
             'WyżnaKopciowa': 'Wyżna Kopciowa', 'WyżnaTARTAK': 'Wyżna TARTAK', 'WyżnaSZKOŁA': 'Wyżna SZKOŁA',
             'KazimierzaWielkiego': 'Kazimierza Wielkiego', 'Powrożnik': 'Powroźnik', 'Muszyna I Dom': 'Muszyna Dom'}
    for a, b in fixes.items(): s = s.replace(a, b)
    return tc(s), ''


# ---------------- Zapopradzie (Muszyna) ----------------
DAYS = {'D': 'w', 'R': 'w', '0': 'w', 'F': 'sh', 'SN': 'sh'}


def parse_zap(path, line, split=False):
    rows = rows_of(path)
    hdr = next(r for r in rows if any(t == 'Lp.' for _, _, t in r['w']))
    lps = [x0 for _, x0, t in hdr['w'] if t == 'Lp.']
    parts = [(lps[0] - 5, lps[1] - 5), (lps[1] - 5, 1e9)] if split and len(lps) > 1 else [(-1, 1e9)]
    out = []
    for lo, hi in parts:
        H = [(xc, t) for xc, x0, t in hdr['w'] if lo <= x0 < hi and t in DAYS]
        trows = []
        for r in rows:
            if r['y'] <= hdr['y'] + 2: continue
            ws = [(xc, x0, t) for xc, x0, t in r['w'] if lo <= x0 < hi]
            if not ws: continue
            txt = [t for xc, x0, t in ws if not TIME.match(t) and t not in ('-', '‐', '_', '–')]
            if txt and txt[0] in ('LEGENDA:', 'R', 'D', 'F', 'SN') and len(txt) > 1 and txt[1] in ('–', '-', 'kursuje', 'kurs', '‐'): break
            if txt and txt[0].rstrip(':') == 'LEGENDA': break
            ts = [(xc, t) for xc, x0, t in ws if TIME.match(t)]
            lp = txt[0] if txt and txt[0].isdigit() else None
            name = ' '.join(txt[1:] if lp else txt)
            if not lp and not ts:   # second line of a stop name written on two lines
                if trows and name and not name[0].isdigit(): trows[-1][2].append(name)
                continue
            trows.append([lp, ts, [name] if name else []])
        rows2 = [(zap_name(' '.join(n))[0], ts) for lp, ts, n in trows]
        for ci, t in trips_from_table(rows2):
            # day type of the column: the header letter nearest to it
            xs = [x for _, ts in rows2 for x, _ in ts]
            cols = cluster(xs)
            d = DAYS[min(H, key=lambda h: abs(h[0] - cols[ci]))[1]] if H else 'w'
            out.append({'line': line, 'days': d, 'stops': [[n, '', m] for _, n, m in t], 'src': os.path.basename(path)})
    return out


def parse_ocr(json_path, line, names, codes):
    d = json.load(open(json_path))
    rows = [r for r in d['rows'] if any(re.match(r'^\d{1,2}:\d{2}$', c) for c in r)]
    assert len(rows) == len(names), (json_path, len(rows), len(names))
    out = []
    for ci, code in enumerate(codes):
        pts = [(i, names[i], tmin(r[ci])) for i, r in enumerate(rows) if re.match(r'^\d{1,2}:\d{2}$', r[ci])]
        out.append({'line': line, 'days': DAYS[code], 'stops': [[n, '', m] for _, n, m in pts], 'src': os.path.basename(json_path)})
    return out


# ---------------- MPGK (Krynica-Zdrój) ----------------
STOPLIKE = re.compile(r'^(Krynica|Tylicz|Muszynka|Mochnaczka|mochnaczka|Berest|Polany|Czyrna|Piorunka)')


def parse_mpgk(path, line, days):
    rows = rows_of(path)
    tables, cur, last = [], [], None
    for r in rows:
        txt = ' '.join(t for _, _, t in r['w'] if not TIME.match(t))
        ts = [(xc, t) for xc, x0, t in r['w'] if TIME.match(t)]
        if txt.startswith('Strona'): continue
        is_stop = bool(STOPLIKE.match(txt)) and (ts or '/' in txt or 'ul' in txt)
        if not is_stop:
            if re.search(r'[A-Za-zĄ-Ż]', txt) and cur: tables.append(cur); cur = []
            continue
        if last and last['p'] == r['p'] and r['y'] - last['y'] > 25 and cur: tables.append(cur); cur = []
        last = r
        cur.append((mpgk_name(txt), ts))
    if cur: tables.append(cur)
    out = []
    for tb in tables:
        rows2 = [(n, ts) for n, ts in tb]
        for ci, t in trips_from_table(rows2):
            out.append({'line': line, 'days': days, 'stops': [[n[0], n[1], m] for _, n, m in t], 'src': os.path.basename(path)})
    return out


if __name__ == '__main__':
    P = lambda f: os.path.join(KM, f)
    trips = []
    for f, ln in [('z1z', 'Z1'), ('z1s', 'Z1'), ('z2d', 'Z2'), ('z2s', 'Z2'), ('z4w', 'Z4'), ('z4m', 'Z4'), ('z5', 'Z5'),
                  ('z7a', 'Z7'), ('z7b', 'Z7'), ('z8a', 'Z8'), ('z8b', 'Z8'), ('z9a', 'Z9'), ('z9b', 'Z9')]:
        trips += parse_zap(P(f + '.pdf'), ln)
    trips += parse_zap(P('z3.pdf'), 'Z3', split=True)
    N6a = ['Żegiestów Zdrój Palenica', 'Żegiestów Ćmielówka', 'Żegiestów Zdrój Chmielówka', 'Żegiestów Zdrój Leśniczówka', 'Żegiestów Zdrój Wieś',
           'Żegiestów Zdrój GS', 'Żegiestów Zdrój Skrzyżowanie', 'Żegiestów Zdrój', 'Żegiestów Zdrój Wiktor', 'Andrzejówka Ługi', 'Andrzejówka RPGK',
           'Andrzejówka', 'Milik PKP', 'Milik Niżny', 'Milik OSP', 'Milik Cmentarz', 'Milik Wyżny', 'Milik Pętla', 'Milik Wyżny', 'Milik Cmentarz',
           'Milik OSP', 'Milik Niżny', 'Milik PKP', 'Milik', 'Muszyna Dom Ociemniałych', 'Muszyna Obwodnica', 'Muszyna Kościół', 'Muszyna Grunwaldzka',
           'Muszyna Polna', 'Muszyna Granica', 'Powroźnik PKP', 'Powroźnik Skrzyżowanie', 'Powroźnik MPGK', 'Krynica Zdrój Dolna', 'Krynica Lecznica Zwierząt',
           'Krynica Zdrój II', 'Krynica Szpital', 'Krynica Zdrój Graniczna', 'Krynica Zdrój Ośrodek Zdrowia', 'Krynica Zdrój UM', 'Krynica Bank',
           'Krynica Hawana', 'Krynica Jastrzębia', 'Krynica Zdrój CPN', 'Krynica Sielanka', 'Krynica Zdrój Słotwińska Kościół', 'Krynica Słotwiny Arena',
           'Krynica Zdrój Słotwiny Pętla']
    trips += parse_ocr(P('z6a_ocr.json'), 'Z6', N6a, 'R SN R R SN R SN R R SN R SN R SN R'.split())
    N6b = ['Krynica Zdrój Słotwiny Pętla', 'Krynica Słotwiny Arena', 'Krynica Zdrój Słotwińska Kościół', 'Krynica Sielanka', 'Krynica Zdrój CPN',
           'Krynica Jastrzębia', 'Krynica Hawana', 'Krynica Bank', 'Krynica Zdrój UM', 'Krynica Zdrój Ośrodek Zdrowia', 'Krynica Zdrój Graniczna',
           'Krynica Szpital', 'Krynica Zdrój II', 'Krynica Lecznica Zwierząt', 'Krynica Zdrój Dolna', 'Powroźnik MPGK', 'Powroźnik Skrzyżowanie',
           'Powroźnik PKP', 'Muszyna Granica', 'Muszyna Polna', 'Muszyna Grunwaldzka', 'Muszyna Kościół', 'Muszyna Obwodnica', 'Muszyna Dom Ociemniałych',
           'Milik', 'Milik PKP', 'Milik Niżny', 'Milik OSP', 'Milik Cmentarz', 'Milik Wyżny', 'Milik Pętla', 'Milik Wyżny', 'Milik Cmentarz', 'Milik OSP',
           'Milik Niżny', 'Milik PKP', 'Andrzejówka', 'Andrzejówka RPGK', 'Andrzejówka Ługi', 'Żegiestów Zdrój Wiktor', 'Żegiestów Zdrój',
           'Żegiestów Zdrój Skrzyżowanie', 'Żegiestów Zdrój GS', 'Żegiestów Zdrój Wieś', 'Żegiestów Zdrój Leśniczówka', 'Żegiestów Zdrój Chmielówka',
           'Żegiestów Ćmielówka', 'Żegiestów Zdrój Palenica']
    trips += parse_ocr(P('z6b_ocr.json'), 'Z6', N6b, 'R SN R SN R R SN R R SN R SN R SN R'.split())
    for f, ln, d in [('k1', 'K1', 'w'), ('k2', 'K1', 'w'), ('k3', 'K1', 'w'), ('kwe', 'K1', 'sh'), ('k5z', 'K3', 'w'), ('ksd', 'K3', 'w'),
                     ('k4a', 'K4', 'w'), ('k5', 'K5', 'w'), ('k8', 'KM', 'w'), ('k9', 'KM', 'w')]:
        trips += parse_mpgk(P(f + '.pdf'), ln, d)
    json.dump({'trips': trips}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    c = collections.Counter((t['line'], t['days'], t['src']) for t in trips)
    for k in sorted(c): print(k, c[k])
