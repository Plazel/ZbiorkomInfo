"""Lines P1–P6 of Gmina Podegrodzie (operator Renata Małek EKO-trans), from komunikacjapodegrodzie.pl/rozklad-jazdy/:
informacje/rozklad_P1_od260926.pdf … rozklad_P6_od260926.pdf (valid from 26.09.2026). The PDFs have a text layer:
each timetable is read by the position of its words (pdftotext -bbox), a column of times being one run.
Days: S school days -> w, F weekdays without school -> f, W Saturdays, Sundays and holidays -> sh.
Stops: those of MPK Nowy Sącz (data/index.json) where the name matches (the pole nearest to the previous stop of the
run, odd poles outwards and even ones back when two are as near); the others placed by OpenStreetMap or on the road
between their neighbours ('est'). Writes the lines PG1–PG6 (area 'ns') into ../km_dodatkowe.json.
Usage: python3 podegrodzie.py DIR_WITH_PDFS"""
import json, os, re, subprocess, sys, math

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'km_dodatkowe.json')
IX = json.load(open(os.path.join(HERE, '..', '..', 'data', 'index.json'), encoding='utf-8'))['stops']
TM = re.compile(r'^\d{1,2}:\d\d$')
DAYS = {'S': 'w', 'F': 'f', 'W': 'sh'}
# PDF name -> MPK Nowy Sącz stop name, where they differ
ALIAS = {'Nowy Sącz Dworzec MPK': 'Dworzec Aut. MPK', 'Nowy Sącz ul. Batorego': 'Aleja Batorego', 'Nowy Sącz Batorego': 'Aleja Batorego',
         'Chełmiec - Mała Wieś': 'Chełmiec Mała Wieś', 'Świnarsko': 'Świniarsko', 'Stadła (Szkoła)': 'Stadła I',
         'Naszacowice Granica': 'Naszacowice Granica I', 'Brzezna Skrzyżowanie': 'Brzezna - Skrzyżowanie',
         'Brzezna Instytut': 'Brzezna - Instytut', 'Brzezna - Litacz pętla': 'Brzezna - Strzyganiec pętla',
         'Brzezna Litacz pętla (Szkoła)': 'Brzezna Litacz pętla'}
# stops MPK does not have: OpenStreetMap / village centre; the rest are put between their neighbours
OSM = {'Olszanka': (49.55563, 20.54701), 'Gostwica Szkoła': (49.59506, 20.59017), 'Długołęka Świerkla': (49.61319, 20.55933),
       'Długołęka Świerkla Wieś': (49.62365, 20.54856), 'Przyszowa Centrum': (49.64123, 20.50417),
       'Podegrodzie Osowie Sklep': (49.58342, 20.56100), 'Juraszowa Centrum': (49.57428, 20.56328)}
# P6: two small timetables side by side on one page (school days)
P6 = [(['Stadła CPN', 'Stadła (Szkoła)', 'Stadła Skrzyżowanie', 'Stadła', 'Gostwica Sklep', 'Gostwica Szkoła'], [(0, 7 * 60 + 40)]),
      (['Gostwica Szkoła', 'Gostwica Sklep', 'Stadła', 'Stadła Skrzyżowanie', 'Stadła (Szkoła)', 'Stadła CPN'],
       [(0, 11 * 60 + 37), (0, 12 * 60 + 47), (0, 13 * 60 + 28), (0, 14 * 60 + 18)])]
LINES = {'PG1': ('P1', '#2e7d32', 'Nowy Sącz – Podrzecze – Olszana – Szczereż'),
         'PG2': ('P2', '#1565c0', 'Nowy Sącz – Podrzecze – Mokra Wieś – Stronie'),
         'PG3': ('P3', '#8d6e63', 'Nowy Sącz – Podrzecze – Długołęka-Świerkla – Przyszowa'),
         'PG4': ('P4', '#c62828', 'Nowy Sącz – Podrzecze – Chochorowice – Brzezna – Podrzecze – Nowy Sącz'),
         'PG5': ('P5', '#ef6c00', 'Nowy Sącz – Podrzecze – Rogi – Juraszowa'),
         'PG6': ('P6', '#6a1b9a', 'Stadła – Gostwica')}


def norm(n):
    n = n.lower().replace('sacz', 'sącz')
    n = re.sub(r'^nowy sącz\s+', '', n); n = re.sub(r'\bul\.?\s*', '', n)
    return re.sub(r'[\s\-–.()]+', '', n)


BYNAME = {}
for sid, v in IX.items():
    if sid.startswith('ns'): BYNAME.setdefault(norm(v[0]), []).append(sid)


def words(page):
    return [dict(x0=float(a), y0=float(b), x1=float(c), t=t.replace('&amp;', '&')) for a, b, c, d, t in
            re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', page)]


def parse(pdf):
    """the timetables of a PDF: [(stop names, [(days, [(stop index, minutes)])])]"""
    h = subprocess.run(['pdftotext', '-bbox', pdf, '-'], capture_output=True, text=True).stdout
    out = []
    for pg in h.split('<page')[1:]:
        R = []
        for w in sorted(words(pg), key=lambda w: (w['y0'], w['x0'])):
            if R and abs(R[-1][0] - w['y0']) < 2.5: R[-1][1].append(w)
            else: R.append([w['y0'], [w]])
        heads = [k for k, (y, r) in enumerate(R) if any(w['t'] == 'przystanek' for w in r)]
        if len(heads) == 1 and sum(w['t'] == 'przystanek' for w in R[heads[0]][1]) > 1: continue   # P6: side by side
        for hi, k in enumerate(heads):
            px = [w for w in R[k][1] if w['t'] == 'przystanek'][0]['x0']
            body = []
            for y, r in R[k + 1:heads[hi + 1] if hi + 1 < len(heads) else len(R)]:
                nm = [w for w in r if px - 2 <= w['x0'] < px + 190 and not TM.match(w['t']) and w['t'] != '|']
                cells = [w for w in r if TM.match(w['t']) or w['t'] == '|']
                if not cells:
                    if body: break
                    continue
                body.append((' '.join(w['t'] for w in sorted(nm, key=lambda w: w['x0'])), cells))
            xs = sorted((c['x0'] + c['x1']) / 2 for _, cs in body for c in cs)
            cl = []
            for x in xs:
                if cl and x - cl[-1][-1] < 6: cl[-1].append(x)
                else: cl.append([x])
            cols = [sum(c) / len(c) for c in cl if len(c) >= 2]
            hdr = {}   # the day headers, each centred over its columns
            for y, r in R[max(0, k - 4):k]:
                ph = []
                for w in sorted(r, key=lambda w: w['x0']):
                    if ph and w['x0'] - ph[-1][-1]['x1'] < 8: ph[-1].append(w)
                    else: ph.append([w])
                for p in ph:
                    m = re.search(r'\(([SFW])\)', ' '.join(w['t'] for w in p))
                    if m: hdr[m.group(1)] = (p[0]['x0'] + p[-1]['x1']) / 2
            sec = [None] * len(cols); start = 0
            for key in [c for c in 'SFW' if c in hdr]:
                tgt = 2 * hdr[key] - cols[start]
                e = min(range(start, len(cols)), key=lambda j: abs(cols[j] - tgt))
                for j in range(start, e + 1): sec[j] = key
                start = e + 1
            runs = [[] for _ in cols]
            for i, (nm, cs) in enumerate(body):
                for c in cs:
                    if not TM.match(c['t']): continue
                    j = min(range(len(cols)), key=lambda j: abs(cols[j] - (c['x0'] + c['x1']) / 2))
                    hh, mm = c['t'].split(':'); runs[j].append((i, int(hh) * 60 + int(mm)))
            out.append(([n for n, _ in body], [(DAYS[sec[j]], runs[j]) for j in range(len(cols)) if len(runs[j]) > 1]))
    return out


def dist(a, b): return math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(49.6)))


def main(d):
    S = {}; trips = []; newid = {}

    def place(names, back_from):
        """stop ids for the names of one timetable"""
        ids = []; prev = (49.6072, 20.7013)
        for i, n in enumerate(names):
            c = BYNAME.get(norm(ALIAS.get(n, n)), [])
            if c:
                best = min(dist(prev, IX[s][2:4]) for s in c)
                near = [s for s in c if dist(prev, IX[s][2:4]) < best + .0008]
                odd = i < back_from
                near.sort(key=lambda s: (int(IX[s][1] or 0) % 2 != (1 if odd else 0), dist(prev, IX[s][2:4])))
                sid = near[0]; v = IX[sid]; S[sid] = [v[0], v[1], v[2], v[3], 'osm', 'ns']; prev = (v[2], v[3])
            else:
                key = n.replace('Brzezna - Kościół (Strzyganiec)', 'Brzezna Kościół (Strzyganiec)')
                if key not in newid:
                    newid[key] = 'nspg%d' % (len(newid) + 1)
                    S[newid[key]] = [key, '', None, None, 'osm' if key in OSM else 'est', 'ns']
                    if key in OSM: S[newid[key]][2:4] = OSM[key]
                sid = newid[key]
                if S[sid][2] is not None: prev = tuple(S[sid][2:4])
            ids.append(sid)
        return ids

    tables = []
    for i in range(1, 6):
        for names, runs in parse(os.path.join(d, 'rozklad_P%d_od260926.pdf' % i)):
            tables.append(('PG%d' % i, 'rozklad_P%d_od260926.pdf' % i, names, runs))
    for names, runs in P6:
        tables.append(('PG6', 'rozklad_P6_od260926.pdf', names, [('w', [(k, t0 + k) for k in range(len(names))]) for _, t0 in runs]))
    seqs = []
    for line, src, names, runs in tables:
        # odd poles outwards, even ones back (P4: back from its turn in Brzezna Litacz Wola)
        back = names.index('Brzezna Litacz Wola') + 1 if line == 'PG4' else len(names) if names[0].startswith('Nowy Sącz') or line == 'PG6' else 0
        ids = place(names, back); seqs.append(ids)
        for days, run in runs:
            trips.append({'line': line, 'days': days, 'src': src, 'st': [[ids[k], '%02d:%02d' % divmod(t, 60)] for k, t in run]})
    # stops without a position: on the straight line between the nearest placed stops of a timetable
    for ids in seqs:
        for k, sid in enumerate(ids):
            if S[sid][2] is not None: continue
            a = next((j for j in range(k - 1, -1, -1) if S[ids[j]][2] is not None), None)
            b = next((j for j in range(k + 1, len(ids)) if S[ids[j]][2] is not None), None)
            if a is None or b is None: continue
            f = (k - a) / (b - a); pa, pb = S[ids[a]][2:4], S[ids[b]][2:4]
            S[sid][2] = round(pa[0] + f * (pb[0] - pa[0]), 5); S[sid][3] = round(pa[1] + f * (pb[1] - pa[1]), 5)
    assert all(v[2] is not None for v in S.values()), [k for k, v in S.items() if v[2] is None]
    D = json.load(open(OUT, encoding='utf-8'))
    D['trips'] = [t for t in D['trips'] if not t['line'].startswith('PG')] + trips
    for sid, v in S.items(): D['stops'].setdefault(sid, v)
    for k, (n, col, desc) in LINES.items():
        D['lines'][k] = {'op': 'Gmina Podegrodzie', 'name': n, 'cat': 'pg', 'color': col, 'area': 'ns', 'desc': desc}
    json.dump(D, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('Podegrodzie:', len(trips), 'kursów,', len(S), 'przystanków, nowe:', newid)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'pdf'))
