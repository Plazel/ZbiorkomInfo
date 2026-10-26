"""Extra lines of the Krynica-Zdrój and Muszyna area -> site/reczne/km_dodatkowe.json (same format as krynica_muszyna.json,
joined to it by build.py; kept apart so that make_km.py does not overwrite it).

* RX – RAFATEX (private carrier): Szczawnik – Muszyna – Krynica-Zdrój – Nowy Sącz, from its PDF timetables
  (rafatex.pl/rozklady/rafatex-krynica-ns.pdf and rafatex-ns-krynica.pdf, read by rafatex.py).
  Day codes: D weekdays, S school days only, 6 Saturdays, 7 Sundays, + holidays. Days in the file: w school days,
  f weekdays without school (a fourth timetable column of this line), s Saturdays, h Sundays and holidays.
* BK – cross-border bus Bardejovské Kúpele – Bardejov – Kurov – Tylicz – Krynica-Zdrój Dworzec PKP, every day
  (SAD Prešov, line 079388, valid from 1.09.2026; all 23 stops).
Stop positions: OpenStreetMap bus stops; stops shared with the MPGK/Muszyna lines use their ids.
A sixth field in a stop gives its area: 'kmx' = outside Krynica-Zdrój and Muszyna (the line still belongs to that area).
Usage: python3 make_dodatkowe.py rafatex-krynica-ns.pdf rafatex-ns-krynica.pdf   (then route_km.py ../km_dodatkowe.json)"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rafatex

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'km_dodatkowe.json')
MAIN = json.load(open(os.path.join(os.path.dirname(OUT), 'krynica_muszyna.json'), encoding='utf-8'))['stops']
SHARED = ['km16', 'km18', 'km19', 'km20', 'km21', 'km22', 'km32', 'km45', 'km46', 'km47', 'km48', 'km49', 'km50', 'km65', 'km66', 'km67',
          'km69', 'km70', 'km71', 'km72', 'km73', 'km75', 'km77']
STOPS = {k: MAIN[k] for k in SHARED}
STOPS.update({
    'kmx1': ['Roztoka Wielka', '', 49.4783, 20.92657, 'osm', 'kmx'],
    'kmx2': ['Nowa Wieś', '', 49.49725, 20.90394, 'osm', 'kmx'],  # PDF: N. Wieś (Kościół) / Nowa Wieś (kapl.)
    'kmx3': ['Łabowa Kotów', '', 49.51694, 20.88223, 'osm', 'kmx'],
    'kmx4': ['Łabowa', '', 49.528, 20.85476, 'osm', 'kmx'],
    'kmx5': ['Maciejowa Szkoła', '', 49.53335, 20.8259, 'osm', 'kmx'],
    'kmx6': ['Frycowa Rybień', '', 49.54005, 20.79975, 'osm', 'kmx'],
    'kmx7': ['Nawojowa Urząd Gminy', '', 49.56011, 20.74454, 'osm', 'kmx'],
    'kmx8': ['Nowy Sącz Zawada Szkoła', '', 49.57907, 20.72944, 'osm', 'kmx'],
    'kmx9': ['Nowy Sącz Dworzec PKP', '', 49.60812, 20.70168, 'osm', 'kmx'],
    'kmx10': ['Nowy Sącz Aleja Batorego', '', 49.61241, 20.69918, 'osm', 'kmx'],
    'kmx11': ['Nowy Sącz Dworzec Autobusowy', '05', 49.61717, 20.69818, 'osm', 'kmx'],
    # line BK (SAD Prešov 079388), from Bardejovské Kúpele to Krynica-Zdrój; 'est' = placed on the road by the timetable
    'kmy1': ['Bardejovské Kúpele parkovisko', '', 49.32692, 21.27419, 'osm', 'kmx'],
    'kmy2': ['Bardejovské Kúpele rázcestie', '', 49.31996, 21.29265, 'osm', 'kmx'],
    'kmy3': ['Bardejov Duklianska-strojárne', '', 49.31557, 21.29343, 'osm?', 'kmx'],
    'kmy4': ['Bardejov Duklianska-JAS', '', 49.30694, 21.29199, 'osm?', 'kmx'],
    'kmy5': ['Bardejov Duklianska-OC', '', 49.3027, 21.28503, 'osm', 'kmx'],
    'kmy6': ['Bardejov AS', '', 49.29773, 21.28208, 'osm', 'kmx'],
    'kmy7': ['Bardejov Dlhý rad', '', 49.29415, 21.27358, 'osm', 'kmx'],
    'kmy8': ['Bardejov Štefánikova-ZŠ', '', 49.29509, 21.26703, 'osm', 'kmx'],
    'kmy9': ['Bardejov Mokrolužský most', '', 49.2962, 21.2545, 'est', 'kmx'],
    'kmy10': ['Mokroluh', '', 49.30861, 21.21192, 'place', 'kmx'],
    'kmy11': ['Rokytov obec', '', 49.31734, 21.18977, 'place', 'kmx'],
    'kmy12': ['Tarnov stred', '', 49.32092, 21.16646, 'place', 'kmx'],
    'kmy13': ['Tarnov rázc. Sveržov', '', 49.3300, 21.1560, 'est', 'kmx'],
    'kmy14': ['Kurov nižný koniec', '', 49.3380, 21.1400, 'est', 'kmx'],
    'kmy15': ['Kurov OcÚ', '', 49.34255, 21.13379, 'place', 'kmx'],
    'kmy16': ['Kurov vyšný koniec', '', 49.3460, 21.1340, 'est', 'kmx'],
    'kmy17': ['Kurov obchvat', '', 49.34936, 21.13483, 'osm', 'kmx'],
    'kmy18': ['Kurov št. hr. CLO', '', 49.3600, 21.1150, 'est', 'kmx'],
    'kmy19': ['Muszynka granica CLO', '', 49.3610, 21.1140, 'est', 'kmx'],
    'kmy20': ['Muszynka', '', 49.38196, 21.07436, 'place', 'kmx'],
    'kmy21': ['Tylicz Skrzyżowanie', '', 49.3955, 21.0300, 'est'],
    'kmb1': ['Krynica-Zdrój Dworzec PKP', '', 49.40989, 20.95659, 'osm'],
})
# RX: every stop, in order towards Nowy Sącz, as e-podroznik.pl lists them (RAFATEX "Szczawnik - Nowy Sącz", October 2026),
# with the running time from the first stop in minutes; the PDF gives only the main stops, the others are timed from this
RX_SEQ = [('km18', 0), ('km19', 1), ('km20', 2), ('km21', 3), ('km22', 5), ('km32', 7), ('km45', 9), ('km46', 10), ('km47', 11), ('km48', 13),
          ('km49', 14), ('km50', 15), ('km65', 17), ('km66', 19), ('km67', 20), ('kmr1', 22), ('km69', 23), ('km70', 25), ('km71', 26),
          ('km72', 28), ('km73', 29), ('kmr2', 31), ('km75', 32), ('kmr3', 33), ('km77', 36), ('kmr4', 38), ('kmr5', 40), ('kmx1', 42),
          ('kmr6', 43), ('kmx2', 44), ('kmr7', 45), ('kmr8', 46), ('kmx3', 48), ('kmr9', 49), ('kmx4', 50), ('kmr10', 52), ('kmx5', 53),
          ('kmr11', 55), ('kmr12', 56), ('kmx6', 58), ('kmr13', 60), ('kmr14', 61), ('kmx7', 63), ('kmr15', 65), ('kmr16', 66), ('kmx8', 67),
          ('kmr17', 68), ('kmr18', 69), ('kmr19', 71), ('kmr20', 74), ('kmx9', 80)]
RX_STOPS = {
    'kmr1': ['Krynica-Zdrój Kraszewskiego Cerkiew', '', 49.39397, 20.95579, 'osm'],   # the MPGK stop's name and place
    'kmr2': ['Krynica-Zdrój', '', 49.4235, 20.9572, 'est'],
    'kmr3': ['Krynica-Zdrój Słotwiny CPN', '', 49.4330, 20.9515, 'est'],
    'kmr4': ['Mochnaczka Wyżna Huta', '', 49.46206, 20.95622, 'osm'],
    'kmr5': ['Krzyżówka', '', 49.47414, 20.94147, 'osm', 'kmx'],
    'kmr6': ['Nowa Wieś Łosie', '', 49.48495, 20.9153, 'osm', 'kmx'],
    'kmr7': ['Nowa Wieś CPN', '', 49.5010, 20.8990, 'est', 'kmx'],
    'kmr8': ['Nowa Wieś Kapliczka', '', 49.50933, 20.88863, 'osm', 'kmx'],
    'kmr9': ['Łabowa Górna', '', 49.52454, 20.87091, 'osm', 'kmx'],
    'kmr10': ['Maciejowa GS', '', 49.53275, 20.83266, 'osm', 'kmx'],
    'kmr11': ['Maciejowa', '', 49.53669, 20.81406, 'osm', 'kmx'],
    'kmr12': ['Frycowa Parking', '', 49.5380, 20.8060, 'est', 'kmx'],
    'kmr13': ['Frycowa Szkoła', '', 49.5493, 20.77213, 'osm', 'kmx'],
    'kmr14': ['Nawojowa Łęg', '', 49.55325, 20.76013, 'osm', 'kmx'],
    'kmr15': ['Nawojowa Podlipie', '', 49.5660, 20.7400, 'est', 'kmx'],
    'kmr16': ['Nowy Sącz Nawojowska - Zawada Podlipie', '', 49.5733, 20.7341, 'osm', 'kmx'],
    'kmr17': ['Nowy Sącz Nawojowska - Zawada Szk. Muzyczna', '', 49.58455, 20.7261, 'osm', 'kmx'],
    'kmr18': ['Nowy Sącz Nawojowska - Grunwaldzka', '', 49.59315, 20.7219, 'osm', 'kmx'],
    'kmr19': ['Nowy Sącz Nawojowska - Graniczna', '', 49.5979, 20.7191, 'osm', 'kmx'],
    'kmr20': ['Nowy Sącz Nawojowska - Traugutta', '', 49.6051, 20.7127, 'osm', 'kmx'],
}
STOPS.update(RX_STOPS)
RAF = {'Szczawnik': 'km16', 'Złockie': 'km19', 'Muszyna Rynek': 'km32', 'Powroźnik PKP': 'km49', 'Krynica Dolna': 'km66', 'Krynica (Dolna)': 'km66',
       'Krynica Szpital': 'km69', 'Krynica (Szpital)': 'km69', 'Krynica (U.M.)': 'km72', 'Krynica Zdrój': 'kmr2', 'Mochnaczka': 'km77',
       'Roztoka': 'kmx1', 'N. Wieś': 'kmx2', 'Nowa Wieś': 'kmx2', 'Kotów': 'kmx3', 'Łabowa': 'kmx4', 'Maciejowa': 'kmx5', 'Frycowa (szkoła)': 'kmr13', 'Frycowa': 'kmx6',
       'Nawojowa': 'kmx7', 'N.S. Zawada': 'kmx8', 'N.S. Dw. PKP': 'kmx9', 'N.S. ul. Batorego': 'kmx10', 'N.S.Dw.PKS': 'kmx11'}


def raf_id(name):
    for k in sorted(RAF, key=len, reverse=True):
        if name.startswith(k): return RAF[k]
    raise KeyError(name)


def fill_rx(st):
    """the PDF trip with every stop of the route between two of its stops, timed in proportion to the running times
    from e-podroznik.pl; stops the PDF has but e-podroznik not (Szczawnik, Nowy Sącz al. Batorego and bus station) stay as they are"""
    seq = [x[0] for x in RX_SEQ]; off = dict(RX_SEQ)
    on = [seq.index(x[0]) for x in st if x[0] in seq]
    back = len(on) > 1 and on[0] > on[-1]
    if back: seq = seq[::-1]; off = {k: -v for k, v in off.items()}
    mins = lambda tm: int(tm[:2]) * 60 + int(tm[3:])
    out = [st[0]]
    for (a, ta), (b, tb) in zip(st, st[1:]):
        if a in seq and b in seq and seq.index(b) > seq.index(a) + 1:
            ma, mb = mins(ta), mins(tb); oa, ob = off[a], off[b]
            for c in seq[seq.index(a) + 1:seq.index(b)]:
                f = (off[c] - oa) / (ob - oa) if ob != oa else 0
                m = round(ma + f * (mb - ma)); out.append([c, '%02d:%02d' % divmod(m, 60)])
        elif a == 'km16' and b == 'km19':   # Szczawnik – Szczawnik Poręba – Złockie Szkoła
            m = mins(ta) + round((mins(tb) - mins(ta)) * 2 / 3); out.append(['km18', '%02d:%02d' % divmod(m, 60)])
        elif a == 'km19' and b == 'km16':
            m = mins(ta) + round((mins(tb) - mins(ta)) / 3); out.append(['km18', '%02d:%02d' % divmod(m, 60)])
        out.append([b, tb])
    return out


def main(pdfs):
    trips = []
    for p in pdfs:
        for t in rafatex.parse(p):
            trips.append({'line': 'RX', 'days': t['days'], 'src': os.path.basename(p), 'st': fill_rx([[raf_id(n), tm] for n, tm in t['st']])})
    # BK: SAD Prešov, line 079388, valid from 1.09.2026 (timetable sent by the user); three runs each way, every day,
    # all with the same running times: from Bardejovské Kúpele at 8:33, 12:33, 16:33, from Krynica-Zdrój at 9:35, 13:35, 17:35
    to_kr = [('kmy1', 0), ('kmy2', 1), ('kmy3', 2), ('kmy4', 3), ('kmy5', 5), ('kmy6', 12), ('kmy7', 15), ('kmy8', 17), ('kmy9', 18),
             ('kmy10', 22), ('kmy11', 24), ('kmy12', 26), ('kmy13', 27), ('kmy14', 30), ('kmy15', 31), ('kmy16', 32), ('kmy17', 33),
             ('kmy18', 37), ('kmy19', 37), ('kmy20', 40), ('kmy21', 44), ('km73', 54), ('kmb1', 57)]   # Bardejov AS: arrives +7, leaves +12
    to_bj = [('kmb1', 0), ('km73', 3), ('kmy21', 13), ('kmy20', 17), ('kmy19', 20), ('kmy18', 20), ('kmy17', 24), ('kmy16', 25),
             ('kmy15', 26), ('kmy14', 27), ('kmy13', 30), ('kmy12', 31), ('kmy11', 33), ('kmy10', 35), ('kmy9', 39), ('kmy8', 40),
             ('kmy7', 42), ('kmy6', 48), ('kmy5', 50), ('kmy4', 51), ('kmy3', 52), ('kmy2', 53), ('kmy1', 55)]   # AS: arrives +45, leaves +48
    hm = lambda m: '%02d:%02d' % divmod(m, 60)
    for seq, starts in ((to_kr, (8 * 60 + 33, 12 * 60 + 33, 16 * 60 + 33)), (to_bj, (9 * 60 + 35, 13 * 60 + 35, 17 * 60 + 35))):
        for t0 in starts:
            trips.append({'line': 'BK', 'days': 'wfsh', 'src': 'SAD Prešov 079388', 'st': [[sid, hm(t0 + m)] for sid, m in seq]})
    # RX11 (Muszyna – Krynica-Zdrój Hajduczek) and RX2 (Nowy Sącz – Gródek nad Dunajcem – Tropie), from rafatex.pl
    # (Muszyna-kz.pdf, Kz-muszyna.pdf, Nowy-sacz-tropie-od-1.10..pdf, Tropie-nowy-sacz-1.10..pdf), read by rafatex2.py
    import rafatex2
    DAYS_OF = {'D': 'wf', 'D,m': 'wf', '6': 's', 'S': 'w', '7': 'h'}
    here = os.path.dirname(os.path.abspath(__file__))
    R11 = {'MUSZYNA PKP': 'km34', 'MUSZYNA PIŁSUDSKIEGO': 'km33', 'MUSZYNA RYNEK OBWODNICA': 'km32', 'MUSZYNA KOŚCIÓŁ': 'km45',
           'MUSZYNA GRUNWALDZKA': 'km46', 'MUSZYNA POLNA': 'km47', 'MUSZYNA GRANICA': 'km48', 'POWROŹNIK PKP': 'km49',
           'POWROŹNIK SKRZYŻOWANIE': 'km50', 'POWROŹNIK MPGK': 'km65', 'KRYNICA ZDRÓJ DOLNA': 'km66', 'KRYNICA LECZNICA ZWIERZĄT': 'km67',
           'KRYNICA ZDRÓJ II': 'kmr1', 'KRYNICA SZPITAL': 'km69', 'KRYNICA GRANICZNA': 'km70', 'KRYNICA OŚRODEK ZDROWIA': 'km71',
           'KRYNICA URZĄD MIASTA': 'km72', 'KRYNICA BANK': 'km73', 'KRYNICA UL. PUŁASKIEGO RAJ': 'km93', 'KRYNICA UL. PUŁASKIEGO': 'km94',
           'KRYNICA UL. PUŁASKIEGO HAJDUCZEK': 'km95', 'KRYNICA POMNIK PUŁASKIEGO': 'km96'}
    for k in ('km33', 'km34', 'km93', 'km94', 'km95', 'km96'): STOPS[k] = MAIN[k]
    src = lambda f: os.path.join(here, 'pdf', f) if os.path.exists(os.path.join(here, 'pdf', f)) else f
    for f in ('Muszyna-kz.pdf', 'Kz-muszyna.pdf'):
        if not os.path.exists(src(f)): continue
        for t in rafatex2.parse(src(f)):
            trips.append({'line': 'R11', 'days': DAYS_OF[t['code']], 'src': f, 'st': [[R11[n], tm] for n, tm in t['st']]})
    R2 = json.load(open(os.path.join(here, 'rx2_stops.json'), encoding='utf-8'))
    IX = json.load(open(os.path.join(here, '..', '..', 'data', 'index.json'), encoding='utf-8'))['stops']
    for n, v in R2.items():
        if isinstance(v, list): STOPS[v[0]] = [v[1], '', v[2][0], v[2][1], v[3], 'ns']
        else: s_ = IX[v]; STOPS[v] = [s_[0], s_[1], s_[2], s_[3], 'osm', 'ns']   # an MPK Nowy Sącz stop
    for f in ('Nowy-sacz-tropie-od-1.10..pdf', 'Tropie-nowy-sacz-1.10..pdf'):
        if not os.path.exists(src(f)): continue
        for t in rafatex2.parse(src(f)):
            trips.append({'line': 'R2', 'days': DAYS_OF[t['code']], 'src': f, 'st': [[R2[n] if isinstance(R2[n], str) else R2[n][0], tm] for n, tm in t['st']]})
    # RX1 in Nowy Sącz too: the same trips, as a line of that city
    trips += [dict(t, line='RXN') for t in trips if t['line'] == 'RX']
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    D = {'lines': {
            'RX': {'op': 'RAFATEX', 'name': 'RX1', 'cat': 'priv', 'color': '#00a651',
                   'desc': 'Szczawnik – Muszyna – Krynica-Zdrój – Nowy Sącz (przewoźnik prywatny)'},
            'RXN': {'op': 'RAFATEX', 'name': 'RX1', 'cat': 'priv', 'color': '#00a651', 'area': 'ns',
                    'desc': 'Nowy Sącz – Krynica-Zdrój – Muszyna – Szczawnik (przewoźnik prywatny)'},
            'R11': {'op': 'RAFATEX', 'name': 'RX11', 'cat': 'priv', 'color': '#2e7d32',
                    'desc': 'Muszyna – Powroźnik – Krynica-Zdrój Hajduczek (przewoźnik prywatny)'},
            'R2': {'op': 'RAFATEX', 'name': 'RX2', 'cat': 'priv', 'color': '#7cb342', 'area': 'ns',
                   'desc': 'Nowy Sącz – Wielogłowy – Gródek nad Dunajcem – Rożnów – Tropie (przewoźnik prywatny)'},
            'BK': {'op': 'SAD Prešov', 'name': 'Krynica-Bardejov', 'cat': 'xb', 'color': '#00838f',
                   'desc': 'Bardejovské Kúpele – Bardejov – Kurov – Tylicz – Krynica-Zdrój (SAD Prešov, linia 079388, ważny od 1.09.2026); na terenie Polski bez przewozów krajowych'}},
         'stops': STOPS, 'trips': trips, 'legs': old.get('legs', {})}
    json.dump(D, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('kursy:', len(trips))


if __name__ == '__main__':
    main(sys.argv[1:])
