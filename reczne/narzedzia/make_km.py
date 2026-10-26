"""Transcribed trips -> site/reczne/krynica_muszyna.json: stops (one name per place, positions from OpenStreetMap
where a stop is mapped there, otherwise estimated along the route) and trips."""
import json, math, re, sys, collections
SP = sys.argv[1]; OUT = sys.argv[2]
T = json.load(open(SP + '/trips_raw.json'))['trips']
# MPGK's weekend timetables are spreadsheets (sheets.py): Saturday and Sunday
try: T += json.load(open(SP + '/trips_sheets.json'))['trips']
except FileNotFoundError: pass
OSM = [s for s in json.load(open(SP + '/osm_stops.json'))]
PLACES = json.load(open(SP + '/places.json'))

ACR = {'Pkp': 'PKP', 'Osp': 'OSP', 'Rpgk': 'RPGK', 'Mpgk': 'MPGK', 'Rsp': 'RSP', 'Gs': 'GS', 'Um': 'UM', 'Cpn': 'CPN', 'Zaiks': 'ZAiKS'}
KZ = 'Krynica-Zdrój '
CANON = {   # Zapopradzie names (Muszyna) -> the same stop as named here
    'Muszyna DomO ciemniałych': 'Muszyna Dom Ociemniałych', 'Żegiestów ZdrójS krzyżowanie': 'Żegiestów Zdrój Skrzyżowanie',
    'Żegiestów Szkoła Zdrój Wieś': 'Żegiestów Zdrój Wieś', 'Muszyna źródełko Wapienne': 'Muszyna Źródełko Wapienne', 'Wapienne': 'Muszyna Źródełko Wapienne',
    'Krynica Szpital': KZ + 'Kraszewskiego Szpital', 'Krynica Graniczna': KZ + 'Kraszewskiego Graniczna', 'Krynica Zdrój Graniczna': KZ + 'Kraszewskiego Graniczna',
    'Krynica Ośrodek Zdrowia': KZ + 'Kraszewskiego Ośrodek Zdrowia', 'Krynica Zdrój Ośrodek Zdrowia': KZ + 'Kraszewskiego Ośrodek Zdrowia',
    'Krynica Urząd Miasta': KZ + 'Kraszewskiego Urząd Miasta', 'Krynica Zdrój UM': KZ + 'Kraszewskiego Urząd Miasta', 'Krynica Bank': KZ + 'Zdrojowa Bank',
    'Krynica Hawana': KZ + 'Piłsudskiego Hawana', 'Krynica Jastrzębia': KZ + 'Piłsudskiego Jastrzębia', 'Krynica Zdrój Jastrzębie': KZ + 'Piłsudskiego Jastrzębia',
    'Krynica Szkoła': KZ + 'Piłsudskiego Szkoła', 'Krynica Sielanka': KZ + 'Słotwińska Sielanka', 'Krynica Zdrój Słotwińska Kościół': KZ + 'Słotwińska Kościół',
    'Krynica Zdrój Słotwiny Pętla': KZ + 'Słotwińska Pętla', 'Krynica Lecznica Zwierząt': KZ + 'Kraszewskiego Lecznica', 'Krynica Zdrój II': KZ + 'Kraszewskiego Cerkiew',
    'Krynica Zdrój Dolna': KZ + 'Dolna', 'Krynica Zdrój CPN': KZ + 'CPN', 'Krynica Słotwiny Arena': KZ + 'Słotwiny Arena',
    'Krynica ul. PułaskiegoH ajduczek': KZ + 'Pułaskiego Hajduczek', 'Krynica ul. Pułaskiego Hajduczek': KZ + 'Pułaskiego Hajduczek',
    'Krynica ul. Pułaskiego': KZ + 'Pułaskiego', 'Krynica ul. Pułaskiego Raj': KZ + 'Pułaskiego Raj', 'Krynica Pomnik Pułaskiego': KZ + 'Pomnik Pułaskiego',
    'Tylicz Kazimierza Wielkiego I': 'Tylicz Kazimierza Wielkiego',
}
# stops placed exactly where OpenStreetMap has them (name in OSM)
OSMNAME = {
    'Czarny Potok Gondola': 'Czarny Potok - Gondola', 'Czarny Potok Akademia Rolnicza': 'Czarny Potok - Akademia Rolnicza', 'Czarny Potok Azoty': 'Czarny Potok - Azoty',
    'Czarny Potok Osiedle 1': 'Czarny Potok - Osiedle 1', 'Czarny Potok Pętla': 'Czarny Potok - Pętla', 'Czarny Potok Osiedle': 'Czarny Potok - Osiedle',
    'Kraszewskiego Graniczna': 'Kraszewskiego - Graniczna', 'Kraszewskiego Ośrodek Zdrowia': 'Kraszewskiego - Ośrodek Zdrowia', 'Kraszewskiego Szpital': 'Kraszewskiego - Szpital',
    'Kraszewskiego Urząd Miasta': 'Kraszewskiego - Urząd Miasta', 'Kraszewskiego Cerkiew': 'Kraszewskiego - cerkiew', 'Kraszewskiego Lecznica': 'Kraszewskiego - lecznica',
    'Piłsudskiego Hawana': 'Piłsudskiego - Hawana', 'Piłsudskiego Jastrzębia': 'Piłsudskiego - Jastrzębia', 'Piłsudskiego Szkoła': 'Piłsudskiego - Szkoła',
    'Pułaskiego Hajduczek': 'Pułaskiego - Hajduczek', 'Pułaskiego Mielec': 'Pułaskiego - Mielec', 'Pułaskiego Szpital Wojskowy': 'Pułaskiego - Szpital Wojskowy',
    'Słotwińska Kościół': 'Słotwińska - Kościół', 'Słotwińska Pętla': 'Słotwińska - Pętla', 'Słotwińska Sielanka': 'Słotwińska - Sielanka',
    'Zdrojowa Bank': 'Zdrojowa - Bank', 'Źródlana Szczyt': 'Źródlana Szczyt', 'Dolna': 'Krynica Dolna',
}
OSMNAME = {KZ + k: v for k, v in OSMNAME.items()}
OSMNAME.update({'Muszyna Granica': 'Muszyna Granica', 'Muszyna Kościół': 'Muszyna Kościół', 'Muszyna Rynek Obwodnica': 'Muszyna Rynek Obwodnica',
    'Muszyna Grunwaldzka': 'Muszyna ul. Grunwaldzka', 'Muszyna Piłsudskiego': 'Muszyna ul. Piłsudskiego', 'Muszyna PKP': 'Muszyna ul. Piłsudskiego PKP',
    'Muszyna Polna': 'Muszyna ul. Polna', 'Muszyna Zazamcze': 'Muszyna ul. Zazamcze', 'Powroźnik PKP': 'Powroźnik PKP', 'Powroźnik Skrzyżowanie': 'Powroźnik Skrzyżowanie',
    'Mochnaczka Wyżna Kopciowa': 'Mochnaczka Wyżna Kopciowa', 'Muszynka Osiedle': 'Muszynka osiedle', 'Tylicz Roma': 'Tylicz Roma / 34a',
    'Złockie Skrzyżowanie': 'Złockie Skrzyżowanie', 'Żegiestów Zdrój Palenica': 'Żegiestów Palenica', 'Żegiestów PKP': 'Żegiestów',
    KZ + 'Stara Droga Kościół': 'Krynica Stara Droga'})
# weaker anchors: village centres for the stop that carries the village's name
PLACE = {'Milik': 'Milik', 'Andrzejówka': 'Andrzejówka', 'Szczawnik': 'Szczawnik', 'Dubne': 'Dubne', 'Leluchów': 'Leluchów', 'Wojkowa I': 'Wojkowa',
         'Tylicz Rynek': 'Tylicz', 'Berest': 'Berest', 'Polany': 'Polany', 'Czyrna': 'Czyrna', 'Piorunka': 'Piorunka', 'Muszynka': 'Muszynka',
         'Jastrzębik Centrum': 'Jastrzębik', 'Złockie Kościół': 'Złockie', 'Żegiestów Zdrój': 'Żegiestów-Zdrój', 'Mochnaczka Niżna Szkoła': 'Mochnaczka Niżna',
         'Mochnaczka Wyżna': 'Mochnaczka Wyżna', 'Krynica-Zdrój Zieleniewskiego Jakubik': 'Jakubik', 'Tylicz Bradowiec': 'Bradów',
         'Krynica-Zdrój Słotwiny Arena': 'Słotwiny', 'Andrzejówka Ługi': 'Ługi'}


MPGK_STOP = lambda n: bool(re.match(r'^(Tylicz|Muszynka|Mochnaczka|Berest|Polany|Czyrna|Piorunka)', n))


def norm(name, line):
    s = ' '.join(ACR.get(w, w) for w in name.split())
    if line.startswith('K') and not re.match(r'^(Tylicz|Muszynka|Mochnaczka|Berest|Polany|Czyrna|Piorunka)', s): s = KZ + s
    return CANON.get(s, s)


def reline(line, st):
    """MPGK publishes routes, not lines, and many trips mix them; sort the trips into lines that each keep to one route"""
    if not line.startswith('K'): return line
    names = [n for n, p, m in st]
    has = lambda k: any(k in n for n in names)
    centre = has('Kraszewskiego Szpital') or has('Zdrojowa Bank')
    if has('Berest') or has('Polany') or has('Piorunka') or has('Czyrna'):
        if not centre: return 'K7'                       # Tylicz – Muszynka – Mochnaczka – Berest – Piorunka (no Krynica centre)
        if has('Polany'): return 'K5'                    # Krynica – Berest – Polany
        return 'K8'                                      # Krynica – Pułaskiego – Mochnaczka Niżna – Czyrna – Piorunka
    if (has('Muszynka') or has('Mochnaczka')) and not centre: return 'K7'
    if has('Muszynka') or has('Mochnaczka'): return 'K6'  # Krynica – Mochnaczka – Muszynka – Tylicz
    if has('Tylicz'): return 'K4'                         # Krynica – Pułaskiego – Tylicz
    if has('Stara Droga') or has('Źródlana'): return 'K3' # Zawodzie – Źródlana – Stara Droga
    if not centre or has('Zawodzie'): return 'K2'         # Zawodzie – Czarny Potok / Słotwiny
    if has('Pułaskiego'): return 'K9'                     # Czarny Potok Gondola – Pułaskiego – Słotwiny
    return 'K1'                                           # Czarny Potok Gondola – Słotwiny
trips = []
seen_src = collections.Counter()
for t in T:
    t['no'] = seen_src[t['src']]; seen_src[t['src']] += 1   # trip's place in its PDF (column order, table by table)
# misprints in the PDFs: (PDF, trip, stop index) -> minutes after midnight
TIME_FIX = {('k3.pdf', 8, 0): 13 * 60 + 30}   # 3sg.pdf: "13:20" at Słotwińska Pętla, 13:31 at the next stop
for t in T:
    for i, x in enumerate(t['stops']):
        if (t['src'], t['no'], i) in TIME_FIX: x[2] = TIME_FIX[(t['src'], t['no'], i)]
    st = [[norm(n, t['line']), p, m] for n, p, m in t['stops']]
    trips.append({'line': reline(t['line'], st), 'days': t['days'], 'src': t['src'], 'no': t['no'], 'stops': st})
# MPGK Krynica-Zdrój lines are added one by one, together with the user; only those listed here are kept
print(collections.Counter(t['line'] for t in trips))

# poles: the PDFs sometimes leave the pole out (a cut-off "/ 11a") or give the opposite one for the same direction;
# take the pole most often used for that stop with the same next stop (or, at the end of a trip, the same previous stop)
def side_key(st, i):
    return (st[i][0], '>' + st[i + 1][0]) if i + 1 < len(st) else (st[i][0], '<' + st[i - 1][0])
votes = collections.defaultdict(collections.Counter)
for t in trips:
    if not t['line'].startswith('K'): continue
    for i, (n, p, m) in enumerate(t['stops']):
        if p: votes[side_key(t['stops'], i)][p] += 1
fixed_poles = 0
for t in trips:
    if not t['line'].startswith('K'): continue
    for i, (n, p, m) in enumerate(t['stops']):
        c = votes.get(side_key(t['stops'], i))
        if not c: continue
        best, k = c.most_common(1)[0]
        if p != best and (not p or k >= 2 * c.get(p, 0)): t['stops'][i][1] = best; fixed_poles += 1
print('poles set or corrected:', fixed_poles)
# MPGK Krynica-Zdrój: one line per timetable on mpgk-krynica.pl (the route it is published under), numbered as in the PDF
# headings (1, 3, 4, 5) or the file names (8, 9); the weekend spreadsheets are lines 6 (Saturday) and 7 (Sunday).
# Every trip of a timetable stays in its line, the ones off the main route as its variants. The holiday timetable
# (ferie.pdf) is left out.
MPGK_LINES = {'K1': ['k1.pdf', 'k2.pdf', 'k3.pdf', 'kwe.pdf'],   # Gondola – Słotwińska Pętla (weekdays: 1s, 2gs, 3sg; weekends: Rozklad)
              'K3': ['k5z.pdf', 'ksd.pdf'],                       # Zawodzie – Stara Droga Gazownia przez Źródlaną, both ways
              'K4': ['k4a.pdf'],                                  # Gondola przez Pułaskiego – Tylicz
              'K5': ['k5.pdf'],                                   # Krynica-Zdrój – Sołectwa
              'K8': ['k8.pdf'],                                   # Gondola przez Mochnaczkę – Muszynka
              'K9': ['k9.pdf'],                                   # Muszynka przez Tylicz, Pułaskiego – Gondola / Czarny Potok / Zawodzie
              'K6': ['ksob.xlsx'],                                # Saturday
              'K7': ['knie.xls']}                                 # Sunday
DAYS_OF = {'kwe.pdf': 'sh', 'ksob.xlsx': 's', 'knie.xls': 'h'}   # Rozklad.pdf is given for Saturdays and Sundays; the rest: weekdays
src_line = {f: ln for ln, fs in MPGK_LINES.items() for f in fs}
for t in trips:
    if t['line'].startswith('K'):
        t['line'] = src_line.get(t['src'], '-'); t['days'] = DAYS_OF.get(t['src'], 'w')
trips = [t for t in trips if t['line'] != '-']
# a trip printed in two timetables (2gs and 3sg share one) is kept once
seen = set(); keep = []
for t in trips:
    k = (t['line'], t['days'], tuple((n, m) for n, p, m in t['stops']))
    if k not in seen: seen.add(k); keep.append(t)
trips = keep
print(collections.Counter(t['line'] for t in trips))

# MPGK's numbers (2a, 6b…) are stop codes, not separate poles to show: one stop per name
for t in trips:
    for x in t['stops']:
        if x[0].startswith(KZ) or MPGK_STOP(x[0]): x[1] = ''
        # "Czarny Potok Osiedle" and "Osiedle 1" are one and the same stop (passed twice by buses turning at the loop)
        if x[0] == KZ + 'Czarny Potok Osiedle 1': x[0] = KZ + 'Czarny Potok Osiedle'
# stop = name + pole; for a stop name seen with poles (MPGK) and without (Muszyna lines), the bare one stays a separate pole ''
keys = collections.OrderedDict()
for t in trips:
    for n, p, m in t['stops']: keys.setdefault((n, p), None)
osm_by = collections.defaultdict(list)
for n, la, lo in OSM: osm_by[n].append((la, lo))
pos = {}
for (n, p) in keys:
    o = OSMNAME.get(n)
    if o and osm_by.get(o):
        pts = osm_by[o]; i = 1 if (p.endswith('b') and len(pts) > 1) else 0
        pos[(n, p)] = (pts[i][0], pts[i][1], 'osm')
    elif n in PLACE and PLACE[n] in PLACES:
        pos[(n, p)] = (PLACES[PLACE[n]][0], PLACES[PLACE[n]][1], 'place')

# the rest: between known neighbours along the trips (by travel time), then onto the nearest unnamed OSM bus stop
def dist(a, b): return math.hypot((a[0] - b[0]) * 111000, (a[1] - b[1]) * 72000)
for it in range(6):
    est = collections.defaultdict(list)
    for t in trips:
        s = t['stops']
        for i, (n, p, m) in enumerate(s):
            if (n, p) in pos: continue
            j = next((k for k in range(i - 1, -1, -1) if (s[k][0], s[k][1]) in pos), None)
            k = next((k for k in range(i + 1, len(s)) if (s[k][0], s[k][1]) in pos), None)
            if j is None or k is None:
                if it < 2: continue
                # an end of a route: carry on in the direction of the last two known stops
                h = j if j is not None else k
                h2 = next((q for q in (range(h - 1, -1, -1) if j is not None else range(h + 1, len(s))) if (s[q][0], s[q][1]) in pos and s[q][2] != s[h][2]), None)
                if h2 is None: continue
                a, b = pos[(s[h][0], s[h][1])], pos[(s[h2][0], s[h2][1])]
                f = min(1.0, abs(m - s[h][2]) / abs(s[h][2] - s[h2][2]))
                est[(n, p)].append((a[0] + (a[0] - b[0]) * f, a[1] + (a[1] - b[1]) * f)); continue
            a, b = pos[(s[j][0], s[j][1])], pos[(s[k][0], s[k][1])]
            if dist(a, b) > 15000: continue
            f = (m - s[j][2]) / (s[k][2] - s[j][2]) if s[k][2] != s[j][2] else (i - j) / (k - j)
            est[(n, p)].append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    for key, l in est.items():
        if key in pos: continue
        la = sum(x[0] for x in l) / len(l); lo = sum(x[1] for x in l) / len(l)
        pos[key] = (la, lo, 'est')
unnamed = [(la, lo) for n, la, lo in OSM if not n]
used = set()
for key, (la, lo, kind) in list(pos.items()):
    if kind != 'est': continue
    best = min(((dist((la, lo), u), u) for u in unnamed if u not in used), default=None)
    if best and best[0] < 350: pos[key] = (best[1][0], best[1][1], 'osm-near'); used.add(best[1])
# a pole b next to its pole a
for (n, p), v in list(pos.items()):
    if p.endswith('b') and (n, p[:-1] + 'a') in pos and dist(v, pos[(n, p[:-1] + 'a')]) < 1: pos[(n, p)] = (v[0] + 0.00012, v[1] + 0.00012, v[2])
missing = [k for k in keys if k not in pos]
print('stops', len(keys), collections.Counter(v[2] for v in pos.values()), 'missing', missing)

ids = {k: 'km%d' % i for i, k in enumerate(keys)}
city = lambda n: 'kry' if (n.startswith(KZ) or n.startswith(('Tylicz', 'Muszynka', 'Mochnaczka', 'Berest', 'Polany', 'Czyrna', 'Piorunka'))) else 'mus'
# MPGK's numbers (9a, 27a…) are stop codes, not pole numbers: kept apart internally, not shown
stops = {ids[k]: [k[0], '' if k[0].startswith(KZ) or MPGK_STOP(k[0]) else k[1], round(pos[k][0], 5), round(pos[k][1], 5), pos[k][2]] for k in keys if k in pos}
LINES = {
    'K1': ('MPGK Krynica-Zdrój', 'Czarny Potok Gondola – Słotwińska Pętla'), 'K3': ('MPGK Krynica-Zdrój', 'Zawodzie – Źródlana – Stara Droga Gazownia'),
    'K4': ('MPGK Krynica-Zdrój', 'Czarny Potok Gondola – Pułaskiego – Tylicz'), 'K5': ('MPGK Krynica-Zdrój', 'Krynica-Zdrój – sołectwa'),
    'K6': ('MPGK Krynica-Zdrój', 'soboty: Zawodzie – Źródlana – Stara Droga – Czarny Potok – Słotwiny – Mochnaczka – Tylicz – Muszynka'),
    'K7': ('MPGK Krynica-Zdrój', 'niedziele: Zawodzie – Źródlana – Jakubik – Czarny Potok – Słotwiny – Mochnaczka – Tylicz'),
    'K8': ('MPGK Krynica-Zdrój', 'Czarny Potok Gondola – Mochnaczka – Muszynka'), 'K9': ('MPGK Krynica-Zdrój', 'Muszynka – Tylicz – Pułaskiego – Czarny Potok / Zawodzie'),
}
for i in range(1, 10): LINES['Z%d' % i] = ('Zapopradzie (Gmina Muszyna)', '')
NAMES = {('Z%d' % i): str(i) for i in range(1, 10)}
# every line has a colour of its own on the page and the map (Zapopradzie 1–9 and MPGK K…, none alike where they meet)
COLORS = {'K1': '#d32f2f', 'K3': '#1565c0', 'K4': '#2e7d32', 'K5': '#7b1fa2', 'K6': '#e65100', 'K7': '#00838f', 'K8': '#c2185b', 'K9': '#5d4037', 'Z1': '#0277bd', 'Z2': '#00695c', 'Z3': '#ad1457', 'Z4': '#8e24aa', 'Z5': '#827717', 'Z6': '#9e7400', 'Z7': '#283593', 'Z8': '#558b2f', 'Z9': '#4527a0'}
# stops the main route of a line must not pass: there they run as a variant
MAIN_NOT = {'K3': [KZ + 'Jastrzębia ZAiKS']}
# Zapopradzie's own line numbers; MPGK lines keep the letter K
out = {'about': 'Rozkłady spisane z plików przewoźników (PDF, a w MPGK na soboty i niedziele – arkusze): Zapopradzie sp. z o.o. (zapopradzie.pl, linie 1–9) i MPGK Krynica-Zdrój (mpgk-krynica.pl, komunikacja uzdrowiskowa). '
                 'Położenia przystanków: OpenStreetMap, a gdzie przystanku tam brak – oszacowane wzdłuż trasy.',
       'lines': {k: {'op': v[0], 'desc': v[1], 'name': NAMES.get(k, k), 'color': COLORS.get(k), **({'main_not': MAIN_NOT[k]} if k in MAIN_NOT else {})} for k, v in LINES.items()},
       # notes written for particular trips: line name, last stop of the trip -> text
       'notes': [],
       'stops': stops,
       'trips': [{'line': t['line'], 'days': t['days'], 'src': t['src'], 'st': [[ids[(n, p)], '%02d:%02d' % (m // 60, m % 60)] for n, p, m in t['stops']]} for t in trips]}
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('trips', len(out['trips']))
