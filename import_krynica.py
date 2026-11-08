#!/usr/bin/env python3
"""Positions of the Krynica-Zdrój and Muszyna stops placed by hand (narzedzia/przystanki-krynica.html, "Pobierz plik")
taken into reczne/krynica_muszyna.json (MPGK, Muszyna) and reczne/km_dodatkowe.json (RAFATEX, the Bardejov bus).

Only the stops in the file change; the others keep their position, number and state.
- A stop of the tool may stand for several ids (data from several sources, one stop in reality): every id gets the position,
  and the ids other than the first are merged into it (their runs call at the first id).
- MERGE below: stops that are the same as another one (from the notes in the file): removed, their runs moved to the other.
- A stop with two platforms gets a second id (<id>b). Which runs call at which platform is decided by build.py when it builds
  the runs (the one on the right of the street in the direction of travel, or by the destinations given in PLATFORM_TOK).
- ONE_WAY: stops served in one direction only.
The notes of the file are printed; those not handled here need handling by hand.
Then the road routes of the moved stops: python3 reczne/narzedzia/legs_odswiez.py
Usage: python3 import_krynica.py przystanki-krynica.json
"""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
PATHS = [os.path.join(HERE, 'reczne', 'krynica_muszyna.json'), os.path.join(HERE, 'reczne', 'km_dodatkowe.json')]

# the same stop under two names / from two sources: removed id -> the id kept (notes of 2026-11-01)
MERGE = {
    'km108': 'km76',   # Krynica-Zdrój CPN (line 6) = Piłsudskiego Szkoła
    'kmr3': 'km76',    # Słotwiny CPN (RAFATEX) = Piłsudskiego Szkoła
    'kmr2': 'km74',    # "Krynica-Zdrój" (RAFATEX) = Piłsudskiego Hawana
    'km93': 'km128',   # Pułaskiego Raj = Pułaskiego Szpital Wojskowy
    'km107': 'km91',   # Muszyna Folwark Szkoła = Muszyna Kościuszki Szkoła
    'km32': 'km23',    # Muszyna Rynek Obwodnica = Muszyna Obwodnica
    # notes of 2026-11-08
    'km96': 'km135',   # Pomnik Pułaskiego = Pułaskiego Kopiec
    'km94': 'km129',   # Pułaskiego (lines RX11, 8) = Pułaskiego Mielec
}
# stops of the file left out for now (their note says so)
SKIP = {'km100'}   # Tylicz Skrzyżowanie
# platforms given by the destinations: the platform (0 = first, 1 = second) whose word comes first among the stops still ahead
PLATFORM_TOK = {
    'km75': {0: ['Piłsudskiego Szkoła', 'Jastrzębia ZAiKS', 'Stara Droga', 'Nowy Sącz', 'Słotwin'],
             1: ['Piłsudskiego Hawana', 'Zdrojowa Bank', 'Muszyna', 'Szpital']},
    'km23': {0: ['Powroźnik', 'Wojkowa', 'Krynica', 'Nowy Sącz'],
             1: ['Dubne', 'Złockie', 'Szczawnik', 'Kościuszki']},
    # Nowy Sącz Nawojowska - Grunwaldzka: 01 towards the bus station, 02 towards Szczawnik (2026-11-08)
    'kmr18': {0: ['Graniczna', 'Traugutta', 'Dworzec', 'Batorego'],
              1: ['Zawada', 'Nawojowa', 'Łabowa', 'Krynica', 'Muszyna', 'Szczawnik']},
}
# served in one direction only: stop -> the stop the runs that call there go on to (later in the run)
ONE_WAY = {'km126': 'km127',   # Stara Droga Ziarenko: only towards Stara Droga Gazownia
           'kmx9': 'kmx11'}   # Nowy Sącz Dworzec PKP: only towards the bus station (not towards Krynica)


def main(src):
    F = [json.load(open(p, encoding='utf-8')) for p in PATHS]
    K = F[0]
    U = {k: v for k, v in json.load(open(src, encoding='utf-8'))['stops'].items() if k not in SKIP}
    stop_of = lambda sid: next((D['stops'] for D in F if sid in D['stops']), None)
    merge = dict(MERGE)
    for e in U.values():   # the ids the tool showed as one stop
        ids = [i for i in e.get('ids') or [] if i not in merge and stop_of(i) is not None]
        ids.sort(key=lambda i: i not in K['stops'])   # the id of the main file is kept (MPGK, with its stop numbers)
        for i in ids[1:]: merge[i] = ids[0]
        if ids: e['ids'] = ids[:1]
    for a, b in list(merge.items()):
        while b in merge: b = merge[b]
        merge[a] = b
    # runs: merged stops, one-way stops; the same stop twice in a row once
    moved = cut = 0
    for D in F:
        for t in D['trips']:
            st = []
            for x in t['st']:
                if x[0] in merge: x = [merge[x[0]]] + x[1:]; moved += 1
                if st and st[-1][0] == x[0]: continue
                st.append(x)
            for sid, nxt in ONE_WAY.items():
                ids = [x[0] for x in st]
                if sid in ids and nxt not in ids[ids.index(sid) + 1:]:
                    i = ids.index(sid)
                    if 0 < i < len(st) - 1:
                        a, b = st[i - 1][0], st[i + 1][0]; L = D.setdefault('legs', {})
                        if '%s %s' % (a, b) not in L and '%s %s' % (a, sid) in L and '%s %s' % (sid, b) in L:
                            L['%s %s' % (a, b)] = L['%s %s' % (a, sid)] + L['%s %s' % (sid, b)][1:]
                        del st[i]; cut += 1
            t['st'] = st
        L = D.get('legs') or {}
        for key in list(L):
            a, b = key.split(' '); na, nb = merge.get(a, a), merge.get(b, b)
            if (na, nb) != (a, b):
                if na != nb: L.setdefault(na + ' ' + nb, L[key])
                del L[key]
    gone = [s for s in merge if any(s in D['stops'] for D in F)]
    for D in F:
        for s in merge: D['stops'].pop(s, None)
    # positions, numbers, second platforms
    plat = K.setdefault('platforms', {})
    n1 = n2 = 0
    for key, u in U.items():
        if u.get('note'): print('UWAGA %s (%s): %s' % (key, u.get('name', ''), u['note']))
        ps = u.get('poles') or []
        ids = [i for i in (u.get('ids') or [key]) if i not in merge]
        if not ps or not ids: continue
        for sid in ids:
            S = stop_of(sid)
            if S is None: print('nieznany przystanek', sid); continue
            p0 = ps[0]
            S[sid][1] = p0.get('p') or S[sid][1]
            S[sid][2], S[sid][3] = round(p0['lat'], 6), round(p0['lon'], 6)
            S[sid][4:5] = ['user']; n1 += 1
            nid = sid + 'b'
            for D in F: D['stops'].pop(nid, None)
            plat.pop(sid, None)
            if len(ps) > 1:
                p1 = ps[1]
                K['stops'][nid] = [S[sid][0], p1.get('p') or '02', round(p1['lat'], 6), round(p1['lon'], 6), 'user']
                plat[sid] = {'b': nid}
                if sid in PLATFORM_TOK: plat[sid]['tok'] = PLATFORM_TOK[sid]
                for D in F: D['stops'].pop(sid + 'c', None)
                if len(ps) > 2:   # a third platform (e.g. Tylicz Skrzyżowanie): used by the runs PLATFORM_TOK sends there (index 2)
                    p2 = ps[2]; K['stops'][sid + 'c'] = [S[sid][0], p2.get('p') or '03', round(p2['lat'], 6), round(p2['lon'], 6), 'user']; plat[sid]['c'] = sid + 'c'
                n2 += 1
    for i, p in enumerate(PATHS):
        json.dump(F[i], open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('przystanki z pliku: %d; ustawione id: %d, z dwoma peronami: %d; usunięte (połączone z innymi): %s; przeniesione postoje: %d, usunięte postoje (jeden kierunek): %d'
          % (len(U), n1, n2, ', '.join('%s→%s' % (s, merge[s]) for s in gone) or '–', moved, cut))
    print('teraz przebieg po ulicach dla przesuniętych przystanków: python3 reczne/narzedzia/legs_odswiez.py')


if __name__ == '__main__':
    main(sys.argv[1])
