#!/usr/bin/env python3
"""Rozkłady Trójmiasta – generator danych dla strony.

Pobiera aktualne otwarte dane (GTFS) ZTM w Gdańsku, ZKM w Gdyni, rozkład kolei
(S1 SKM, S2 i S22 PKM/POLREGIO), ZDMiKP Bydgoszcz oraz rozkład MPK Nowy Sącz (z jego strony),
dołącza spisane ręcznie rozkłady Krynicy-Zdroju i Muszyny, przelicza trasy, warianty,
rozkłady i kolory linii i zapisuje je jako pliki JSON w katalogu data/ obok index.html.

Użycie:  python3 build.py              (zapisuje do ./data)
         python3 build.py inny/katalog
         python3 build.py --embed      (dodatkowo tworzy rozklady.html z wbudowanymi danymi,
                                        który działa po otwarciu prosto z dysku)
         python3 build.py --podklad    (wymusza ponowne pobranie podkładu mapy z OpenStreetMap;
                                        normalnie odświeżany raz w miesiącu)
Wymaga tylko Pythona 3.9+ (bez dodatkowych pakietów).
"""
import csv, json, os, re, sys, time, collections, datetime, io, shutil, tempfile, urllib.request, zipfile, concurrent.futures

SOURCES = {
    'ztm':   'https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/30e783e4-2bec-4a7d-bb22-ee3e3b26ca96/download/gtfsgoogle.zip',
    'ztrips': 'https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/b15bb11c-7e06-4685-964e-3db7775f912f/download/trips.json',
    'zkm':   'https://api.zdiz.gdynia.pl/pt/gtfs.zip',
    'rail':  'https://mkuran.pl/gtfs/polish_trains.zip',
    # ZDMiKP Bydgoszcz does not publish GTFS itself: this feed is converted from its official timetables (CC0)
    'byd':   'https://mkuran.pl/gtfs/bydgoszcz.zip',
    # Poznań (ZTM Poznań), Kraków (ZTP Kraków: buses A, trams T) and Warszawa (ZTM/WTP, converted to GTFS by mkuran.pl)
    'poz':   'https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile',
    'krkA':  'https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip',
    'krkT':  'https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip',
    'waw':   'https://mkuran.pl/gtfs/warsaw.zip',
    'wej':   'https://mkuran.pl/gtfs/wejherowo.zip',   # MZK Wejherowo
    'ldz':   'https://otwarte.miasto.lodz.pl/wp-content/uploads/2025/06/GTFS.zip',   # Łódź (ZDiT Łódź, MPK-Łódź), official open data
    'prg':   'https://data.pid.cz/PID_GTFS.zip',   # Praha (PID, ROPID open data; the city lines are kept)
}
HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
EMBED = '--embed' in sys.argv
OUT = ARGS[0] if ARGS else os.path.join(HERE, 'data')
SCR = tempfile.mkdtemp(prefix='rozklady-')

def fetch(url, dest):
    req = urllib.request.Request(url, headers={'User-Agent': 'rozklady-trojmiasto/1.0'})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, 'wb') as f: shutil.copyfileobj(r, f)

print('Pobieranie danych…')
for key, sub in (('ztm', 'gtfs/x'), ('zkm', 'gdy'), ('rail', 'tr'), ('byd', 'byd'), ('poz', 'poz'), ('krkA', 'krkA'), ('krkT', 'krkT'), ('waw', 'waw'), ('wej', 'wej'), ('ldz', 'ldz'), ('prg', 'prg')):
    z = os.path.join(SCR, key + '.zip'); fetch(SOURCES[key], z)
    zipfile.ZipFile(z).extractall(os.path.join(SCR, sub)); os.remove(z)
# Flensburg (Aktiv Bus Flensburg): cut out of the Schleswig-Holstein GTFS (opendata.schleswig-holstein.de), kept a week in cache/fl
try:
    import flensburg_gtfs
    _fc = os.path.join(HERE, 'cache', 'fl')
    if not os.path.exists(_fc + '/stop_times.txt') or (datetime.datetime.now().timestamp() - os.path.getmtime(_fc + '/stop_times.txt')) > 6 * 86400:
        os.makedirs(os.path.dirname(_fc), exist_ok=True); flensburg_gtfs.build(flensburg_gtfs.URL, _fc)
    shutil.copytree(_fc, os.path.join(SCR, 'fl'))
except Exception as e: print('Flensburg: bez danych (%s)' % e)
fetch(SOURCES['ztrips'], os.path.join(SCR, 'ztrips.json'))

# representative days: the nearest Wednesday (or Tuesday/Thursday), Saturday and Sunday from today
TODAY = datetime.date.today()
def nearest(wds):
    for i in range(14):
        d = TODAY + datetime.timedelta(days=i)
        if d.weekday() in wds: return d.strftime('%Y%m%d')
# the timetable shows the nearest weekday, Saturday and Sunday counting from today (like the ZTM website)
WEEKS_N = 3
WINDOW_DAYS = 7 * WEEKS_N
# weeks counted from today; in each: the first weekday, the Saturday and the Sunday -> keys w0 s0 h0, w1 s1 h1, ...
WEEKS = []; DAYS = {}
for wi in range(WEEKS_N):
    days = [TODAY + datetime.timedelta(days=7 * wi + i) for i in range(7)]
    rep = {'w': next(d for d in days if d.weekday() < 5), 's': next(d for d in days if d.weekday() == 5), 'h': next(d for d in days if d.weekday() == 6)}
    WEEKS.append({'from': days[0].strftime('%Y%m%d'), 'to': days[-1].strftime('%Y%m%d'), **{k: v.strftime('%Y%m%d') for k, v in rep.items()}})
    for k, v in rep.items(): DAYS[k + str(wi)] = v.strftime('%Y%m%d')
OPEND = {}
os.makedirs(OUT + '/r', exist_ok=True)
for f in os.listdir(OUT + '/r'): os.remove(OUT + '/r/' + f)

def rd(path): return csv.DictReader(open(path, encoding='utf-8-sig'))
def tmin(t):
    h, m, s = map(int, t.split(':')); return h * 60 + m + (1 if s >= 30 else 0)
def dtype(d):
    wd = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday()
    return 'w' if wd < 5 else ('s' if wd == 5 else 'h')
def plans_of(trips_out):
    """identical departure lists (e.g. the same weekday in two weeks) are stored once"""
    plans = []; tp = {}
    for k, lst in trips_out.items():
        if not lst: continue
        if lst not in plans: plans.append(lst)
        tp[k] = plans.index(lst)
    return {'plans': plans, 'tp': tp}

STOPS = {}           # sid -> [name, num, lat, lon, city]
TSHAPE = {}; SHAPE_OF = {}   # trip -> shape id; (route, stop ids of a pattern) -> shape id
ROUTES_OUT = []

TOWNS_OTHER = ('Pruszcz', 'Kowale', 'Banino', 'Borkowo', 'Czaple', 'Jankowo', 'Otomin', 'Straszyn', 'Rotmanka',
               'Juszkowo', 'Rusocin', 'Lędowo', 'Bąkowo', 'Cieplewo', 'Żukowo', 'Kolbudy', 'Rumia', 'Reda', 'Wejherowo',
               'Kosakowo', 'Szemud', 'Koleczkowo', 'Chwaszczyno', 'Rewa', 'Mechelinki', 'Dębogórze', 'Pogórze', 'Suchy Dwór',
               'Pierwoszyno', 'Kazimierz', 'Mosty', 'Sopot')

def split_name(n):
    n = n.strip().replace('""', '"')
    m = re.match(r'^(.*?)\s+(\d{2})$', n)
    return (m.group(1), m.group(2)) if m else (n, '')

def ztm_city(name):
    if name.startswith('Sopot'): return 'sop'
    if name.startswith('Gdynia'): return 'gdy'
    if name.startswith(TOWNS_OTHER): return 'oth'
    return 'gda'

def zkm_city(zone):
    return {'Gdańsk': 'gda', 'Gdynia': 'gdy', 'Sopot': 'sop'}.get(zone, 'oth')

def rail_city(name):
    for pre, c in (('Gdańsk', 'gda'), ('Sopot', 'sop'), ('Gdynia', 'gdy')):
        if name.startswith(pre): return c
    return 'oth'

def build_routes(groups, meta_of):
    """groups: {route_key: [(day, lf, dir, rows)]} rows=[(sid, minute, pickup, drop)]"""
    for key, tl_all in groups.items():
        m = meta_of[key]; rid_key = key
        # special days: of the candidate weekdays of a week (keys X<week>:<date>) the first whose departures differ from
        # the week's weekday timetable becomes column x<week>; the others are dropped
        if any(str(it[0]).startswith('X') for it in tl_all):
            sig = lambda items: sorted((it[2], tuple(x[0] for x in it[3]), it[3][0][1]) for it in items)
            keep = [it for it in tl_all if not str(it[0]).startswith('X')]
            cand = collections.defaultdict(lambda: collections.defaultdict(list))
            for it in tl_all:
                if str(it[0]).startswith('X'): wi, dd = it[0][1:].split(':'); cand[wi][dd].append(it)
            m['dates'] = dict(m.get('dates') or {})
            for wi, by_d in cand.items():
                base = sig([it for it in keep if it[0] == 'w' + wi])
                for dd in sorted(by_d):
                    if sig(by_d[dd]) != base:
                        keep += [('x' + wi,) + tuple(it[1:]) for it in by_d[dd]]; m['dates']['x' + wi] = dd; break
            tl_all = keep
        dirs = collections.defaultdict(list)
        for item in tl_all:
            day, lf, d, rows = item[:4]
            # two poles of one stop in a row (e.g. M32 from Dworzec Główny 07 and then 18) count as one stop:
            # at the start of a trip the last of them (where it really departs), elsewhere the first
            if len(rows) > 2:
                nm = [STOPS[x[0]][0] for x in rows]; keep = []
                for i in range(len(rows)):
                    if i > 0 and nm[i] == nm[i - 1] and not (keep and keep[-1] == i - 1 and i - 1 == 0): continue
                    if i == 1 and nm[0] == nm[1]: keep[-1:] = []
                    keep.append(i)
                if len(keep) >= 2 and len(keep) < len(rows):
                    old = tuple(x[0] for x in rows); rows = [rows[i] for i in keep]
                    if (key, old) in SHAPE_OF: SHAPE_OF.setdefault((key, tuple(x[0] for x in rows)), SHAPE_OF[(key, old)])
            dirs[d].append((day, lf, rows, item[4] if len(item) > 4 else None))
        out_dirs = []; cov24_all = []; dep_all = []; peak_all = []
        lname = lambda sid: STOPS[sid][0]
        for d in sorted(dirs):
            tl = dirs[d]
            pat_count = collections.Counter(tuple(x[0] for x in rows) for _, _, rows, _t in tl)
            wk = collections.Counter(tuple(x[0] for x in rows) for day, _, rows, _t in tl if day[0] == 'w')
            base_c = wk or pat_count
            ends = collections.Counter(); starts = collections.Counter()
            for q, c in base_c.items(): ends[lname(q[-1])] += c; starts[lname(q[0])] += c
            top_end = ends.most_common(1)[0][0]; top_start = starts.most_common(1)[0][0]
            cand = [q for q in base_c if lname(q[-1]) == top_end] or list(base_c)
            cand = [q for q in cand if lname(q[0]) == top_start] or cand
            if m.get('main_ends'):   # forced main route (e.g. S1 Gdańsk Śródmieście – Lębork)
                forced = [q for q in base_c if {lname(q[0]), lname(q[-1])} == set(m['main_ends'])]
                if forced: cand = forced
            if m.get('main_not'):   # stops the main route must not pass (they make a variant instead)
                cand = [q for q in cand if not {lname(x) for x in q} & set(m['main_not'])] or cand
            main = max(cand, key=lambda q: (base_c[q] * len(q), base_c[q]))
            pats = [main] + [p for p, _ in pat_count.most_common() if p != main]
            # variant-only stops go right before the stop where the variant joins the main route
            # (or right after the stop where it leaves it), like on the ZTM website
            merged = list(main)
            for p in pats[1:]:
                pending = []; last = -1
                for sid in p:
                    if sid in merged:
                        idx = merged.index(sid)
                        if pending:
                            if last >= 0 and idx < last: idx = last + 1   # keep order on loops
                            for j, x in enumerate(pending): merged.insert(idx + j, x)
                            idx += len(pending); pending = []
                        last = idx
                    else:
                        pending.append(sid)
                for j, x in enumerate(pending): merged.insert(last + 1 + j, x)
            mpos = {s: i for i, s in enumerate(merged)}; main_set = set(main)
            req = collections.Counter(); tot = collections.Counter()
            for _, _, rows, _t in tl:
                for x in rows:
                    tot[x[0]] += 1
                    if x[2] == '3' or x[3] == '3': req[x[0]] += 1
            sdays = collections.defaultdict(set); regular = set()
            for day, dep, rows, _t in tl:
                for x in rows:
                    sdays[x[0]].add(day[0])
                    if not dep: regular.add(x[0])
            stops_out = [[s, 0 if s in main_set else 1, 1 if req[s] > 0 else 0,
                          '' if (s in main_set or len(sdays[s]) == 3) else ''.join(k for k in 'wsh' if k in sdays[s]),
                          0 if (s in main_set or s in regular) else 1] for s in merged]
            pat_out = []; notes = []
            # a stop visited twice (a turn at a loop, an out-and-back spur): each visit gets its own row
            mall = collections.defaultdict(list)
            for i, s in enumerate(merged): mall[s].append(i)
            def pat_idx(p):   # the first row of that stop after the previous stop's row
                r = []; prev = -1
                for s in p:
                    l = mall[s]; i = next((x for x in l if x > prev), l[-1]); r.append(i); prev = i
                return r
            for p in pats:
                pat_out.append(pat_idx(p))
                if p == main: notes.append(''); continue
                parts = []
                if lname(p[0]) != lname(main[0]): parts.append('kurs rozpoczyna się na przystanku ' + lname(p[0]))
                if lname(p[-1]) != lname(main[-1]): parts.append('kurs kończy bieg na przystanku ' + lname(p[-1]))
                extra = [lname(s) for s in p[1:-1] if s not in main_set and lname(s) not in (lname(p[0]), lname(p[-1]))]
                if extra: parts.append('kurs jedzie przez ' + ', '.join(dict.fromkeys(extra)))
                if not parts:
                    pset = set(p); pn = {lname(s) for s in p}
                    skipped = [lname(s) for s in main if s not in pset and lname(s) not in pn]
                    parts.append('kurs nie zatrzymuje się na: ' + ', '.join(dict.fromkeys(skipped)) if skipped else 'kurs z innego stanowiska przystanku')
                txt = '; '.join(parts); notes.append(txt[:1].upper() + txt[1:])
            pidx = {p: i for i, p in enumerate(pats)}
            profiles = []; prof_idx = {}; trips_out = {k: [] for k in DAYS}; tends = []
            for day, *_r in tl: trips_out.setdefault(day, [])
            for day, lf, rows, tn in tl:
                p = tuple(x[0] for x in rows); t0 = rows[0][1]
                k = (pidx[p], tuple(x[1] - t0 for x in rows))
                if k not in prof_idx: prof_idx[k] = len(profiles); profiles.append([k[0], list(k[1])])
                entry = [t0, prof_idx[k], 1 if lf else 0]
                if tn is not None:
                    if tn not in tends: tends.append(tn)
                    entry.append(tends.index(tn))
                trips_out[day].append(entry)
            for k in trips_out: trips_out[k].sort()
            cnt = collections.Counter()
            # frequency on the first weekday; a line running only on other days (e.g. Warsaw's C lines around
            # 1 November) is judged on its busiest day instead
            dcnt = collections.Counter(day for day, lf, rows, _t in tl)
            dsel = 'w0' if dcnt.get('w0') else (dcnt.most_common(1)[0][0] if dcnt else 'w0')
            for day, lf, rows, _t in tl:
                if day == dsel:
                    for x in rows[:-1]: cnt[x[0]] += 1
            if cnt:
                bs = cnt.most_common(1)[0][0]
                ts = sorted(x[1] for day, lf, rows, _t in tl if day == dsel for x in rows[:-1] if x[0] == bs)
                t24 = sorted(t % 1440 for t in ts)
                c24 = sum(b - a for a, b in zip(t24, t24[1:]) if b - a < 20)
                if t24 and (t24[0] + 1440 - t24[-1]) < 20: c24 += t24[0] + 1440 - t24[-1]
                cov24_all.append(c24); dep_all.append(len([t for t in ts if 420 <= t < 1080]))
                def hw(a, b):
                    w = [t for t in ts if a <= t < b]
                    return (w[-1] - w[0]) / (len(w) - 1) if len(w) >= 4 else 999
                best = lambda lo, hi: min(hw(x, x + 120) for x in range(lo, hi - 119, 5))
                peak_all.append(max(best(300, 600), best(780, 1140)))
            out_dirs.append({'_shape': SHAPE_OF.get((rid_key, main)), '_vshapes': [SHAPE_OF.get((rid_key, q)) for q in pats[1:]], 'd': d, 'head': lname(main[-1]), 'from': lname(main[0]), 'stops': stops_out,
                             'pats': pat_out, 'notes': notes, 'prof': profiles, **plans_of(trips_out), **({'tends': tends} if tends else {})})
        if not out_dirs: continue
        cov24 = min(cov24_all) if cov24_all else 0
        deps = sum(dep_all) / max(1, len(dep_all))
        rid = m['id']
        json.dump({'id': rid, 'n': m['n'], 't': m['t'], 'op': m['op'], 'dates': m['dates'], 'dirs': out_dirs},
                  open(f'{OUT}/r/{rid}.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        main_stops = [dd['stops'][i][0] for dd in out_dirs for i in dd['pats'][0]]
        city_stops = [s[0] for dd in out_dirs for s in dd['stops']]
        cities = sorted({STOPS[s][4] for s in city_stops} - {'oth'})
        ROUTES_OUT.append({'id': rid, 'n': m['n'], 't': m['t'], 'op': m['op'], 'f': cov24 >= 480 or (bool(peak_all) and min(peak_all) <= 15), 'pk': round(min(peak_all), 1) if peak_all and min(peak_all) < 999 else None,
                           'fh': round(cov24 / 60, 1), 'avg': round(660 / deps) if deps else None, 'c': cities,
                           'ends': [out_dirs[0]['from'], out_dirs[0]['head']],
                           'sn': sorted({STOPS[s][0] for s in main_stops})})

def feed_days(path, route_of_trip):
    """returns {(route_key, date): [trip_ids]} for dates in the feed of the needed day types"""
    svc_dates = collections.defaultdict(set)
    if os.path.exists(path + '/calendar.txt'):
        for r in rd(path + '/calendar.txt'):
            d0 = datetime.datetime.strptime(r['start_date'], '%Y%m%d').date(); d1 = datetime.datetime.strptime(r['end_date'], '%Y%m%d').date()
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            x = d0
            while x <= d1:
                if r[days[x.weekday()]] == '1': svc_dates[r['service_id']].add(x.strftime('%Y%m%d'))
                x += datetime.timedelta(days=1)
    for r in rd(path + '/calendar_dates.txt'):
        if r['exception_type'] == '1': svc_dates[r['service_id']].add(r['date'])
        else: svc_dates[r['service_id']].discard(r['date'])
    window = {d for d in (TODAY + datetime.timedelta(days=i) for i in range(WINDOW_DAYS))}
    window = {d.strftime('%Y%m%d') for d in window}
    by = collections.defaultdict(list)
    for tid, (rk, svc) in route_of_trip.items():
        for d in svc_dates.get(svc, ()):
            if d in window: by[(rk, d)].append(tid)
    return by

def choose(by, op=None):
    """pick one date per route & day type -> {tid: (rk, daytype)}, dates"""
    chosen = {}; dates = collections.defaultdict(dict)
    if op and by: OPEND[op] = max(OPEND.get(op, ''), max(d for (_, d) in by))
    rks = {k[0] for k in by}
    for rk in rks:
        # strict: a line that does not run on the chosen day shows no departures for that day type
        strict = any((rk, rep) in by for rep in DAYS.values())
        for k, rep in DAYS.items():
            dates[rk][k] = rep
            if strict:
                d = rep if (rk, rep) in by else None
            else:   # the line runs on none of the three days: show its nearest days of each type instead
                cands = [d for (r2, d) in by if r2 == rk and dtype(d) == k[0]]
                d = min(cands) if cands else None
                if d: dates[rk][k] = d
            if not d: continue
            for tid in by[(rk, d)]: chosen.setdefault(tid, []).append((rk, k))
        # other weekdays of each week whose trips differ from the chosen weekday: candidates for a special day column
        # (build_routes keeps the first one that really has a different timetable, as key x<week>)
        for wi, wk in enumerate(WEEKS):
            rep = DAYS.get('w%d' % wi); reps = set(by.get((rk, rep), ()))
            d0 = datetime.datetime.strptime(wk['from'], '%Y%m%d').date()
            for i in range(7):
                dd = (d0 + datetime.timedelta(days=i)).strftime('%Y%m%d')
                if dd == rep or dtype(dd) != 'w' or (rk, dd) not in by: continue
                if set(by[(rk, dd)]) != reps:
                    for tid in by[(rk, dd)]: chosen.setdefault(tid, []).append((rk, 'X%d:%s' % (wi, dd)))
    return chosen, dates

# ---------------- ZTM Gdańsk ----------------
P = SCR + '/gtfs/x'
for r in rd(P + '/stops.txt'):
    n, num = split_name(r['stop_name'])
    c = ztm_city(n)
    # ZTM prefixes stops in Sopot and Gdynia with the city name; ZKM does not. Drop it so both share names.
    if c in ('sop', 'gdy'): n = re.sub(r'^(Sopot|Gdynia)\s+', '', n)
    STOPS[r['stop_id']] = [n, num, round(float(r['stop_lat']), 5), round(float(r['stop_lon']), 5), c]
ztm_routes = {r['route_id']: r for r in rd(P + '/routes.txt')}
zt = json.load(open(SCR + '/ztrips.json', encoding='utf-8'))
zt = [x for day in zt.values() for x in day['trips']]   # trips are listed per day: take all days
DEPOT = {(str(x['routeId']), str(x['tripId'])) for x in zt if re.search(r'Zajezdnia|Baza', x['tripHeadsign'])}
rot = {}; tmeta = {}
for r in rd(P + '/trips.txt'):
    parts = r['trip_id'].split('_')
    rot[r['trip_id']] = (r['route_id'], r['service_id'])
    tmeta[r['trip_id']] = (r['direction_id'], len(parts) > 1 and (r['route_id'], parts[1]) in DEPOT)
    if r.get('shape_id'): TSHAPE[r['trip_id']] = 'g' + r['shape_id']
chosen, dates = choose(feed_days(P, rot), 'ZTM Gdańsk')
# trips in the ZTM feed that the ZTM website does not show: line -> day types left out (w weekdays, s Saturdays, h Sundays)
# line 7 runs on weekdays only, but the feed of October 2026 also lists weekend trips
ZTM_NO_DAYS = {}   # (line 7 at weekends is shown again, as in the feed)
for tid in list(chosen):
    rk = rot[tid][0]; no = ZTM_NO_DAYS.get(ztm_routes[rk]['route_short_name'], '') if rk in ztm_routes else ''
    if no:
        chosen[tid] = [(r, k) for r, k in chosen[tid] if k[0] not in no]
        if not chosen[tid]: del chosen[tid]
st = collections.defaultdict(list)
for r in rd(P + '/stop_times.txt'):
    if r['trip_id'] in chosen:
        st[r['trip_id']].append((int(r['stop_sequence']), r['stop_id'], tmin(r['departure_time']), r['pickup_type'], r['drop_off_type']))
groups = collections.defaultdict(list); meta_of = {}
for tid, rows in st.items():
    rows.sort(); rows = [(x[1], x[2], x[3], x[4]) for x in rows if not (x[3] == '1' and x[4] == '1')]
    if len(rows) < 2: continue
    for rk, k in chosen[tid]:
        groups[rk].append((k, tmeta[tid][1], tmeta[tid][0], rows))
        if tid in TSHAPE: SHAPE_OF.setdefault((rk, tuple(x[0] for x in rows)), TSHAPE[tid])
for rk in groups:
    rt = ztm_routes[rk]; short = rt['route_short_name']
    t = 'tram' if rt['route_type'] == '900' else 'bus'
    if short.startswith('N'): t = 'night'
    elif short[0] == 'T' or (short[0] == 'M' and short != 'M32'): t = 'repl'   # M32 is an ordinary bus line
    meta_of[rk] = {'id': rk, 'n': short, 't': t, 'op': 'ZTM Gdańsk', 'dates': dates[rk]}
build_routes(groups, meta_of)
ztm_names = {r['n'] for r in ROUTES_OUT}


# ---------------- ZKM Gdynia ----------------
P = SCR + '/gdy'
for r in rd(P + '/stops.txt'):
    n, num = split_name(r['stop_name'])
    STOPS['y' + r['stop_id']] = [n, num, round(float(r['stop_lat']), 5), round(float(r['stop_lon']), 5), zkm_city(r['zone_id'])]
zroutes = {}
for r in rd(P + '/routes.txt'):
    short = r['route_short_name']
    if r['route_long_name'].startswith('...'): continue        # depot runs
    if short in ztm_names: continue                              # joint line already in ZTM feed (171)
    zroutes[r['route_id']] = r
rot = {}; tmeta = {}
for r in rd(P + '/trips.txt'):
    if r['route_id'] not in zroutes: continue
    if r.get('shape_id'): TSHAPE[r['trip_id']] = 'y' + r['shape_id']
    key = 'y' + re.sub(r'\W', '', zroutes[r['route_id']]['route_short_name'])   # merge duplicates of the same number
    rot[r['trip_id']] = (key, r['service_id']); tmeta[r['trip_id']] = (r['direction_id'] or '0', False)
chosen, dates = choose(feed_days(P, rot), 'ZKM Gdynia')
st = collections.defaultdict(list)
for r in rd(P + '/stop_times.txt'):
    if r['trip_id'] in chosen:
        st[r['trip_id']].append((int(r['stop_sequence']), 'y' + r['stop_id'], tmin(r['departure_time']), r['pickup_type'] or '0', r['drop_off_type'] or '0'))
groups = collections.defaultdict(list); meta_of = {}
# ZKM publishes some lines as one round trip; split them at the turning point into two directions
SPLIT_AT = {'y153': 'Wielki Kack Fikakowo', 'y192': 'Płyta Redłowska', 'y203': 'Działki Leśne - Sztumska', 'y144': 'Rynek Non-Stop', 'y114': 'Demptowo',
            'y133': 'Płyta Redłowska', 'y87': 'Janowo SKM', 'y185': 'Rynek Non-Stop'}
for tid, rows in st.items():
    rows.sort(); rows = [(x[1], x[2], x[3], x[4]) for x in rows if not (x[3] == '1' and x[4] == '1')]
    if len(rows) < 2: continue
    for rk, k in chosen[tid]:
        parts = [(tmeta[tid][0], rows)]
        sp = SPLIT_AT.get(rk)
        if sp:
            idx = next((i for i, x in enumerate(rows) if 0 < i < len(rows) - 1 and STOPS[x[0]][0] == sp), None)
            if idx is not None: parts = [('0', rows[:idx + 1]), ('1', rows[idx:])]
            else: parts = [('1' if STOPS[rows[0][0]][0] == sp else '0', rows)]
        for dd_, rr in parts:
            if len(rr) < 2: continue
            groups[rk].append((k, tmeta[tid][1], dd_, rr))
            # a split round trip keeps the shape of the whole loop, marked with the half it needs ("|0" or "|1")
            if tid in TSHAPE: SHAPE_OF.setdefault((rk, tuple(x[0] for x in rr)), TSHAPE[tid] + ('|' + dd_ if len(parts) == 2 else ''))
def fix_dirs(lst):
    """ZKM direction_id is unreliable: orient each trip against the line's most common pattern by stop names."""
    pc = collections.Counter(tuple(x[0] for x in rows) for _, _, _, rows in lst)
    ref = [STOPS[sid][0] for sid in pc.most_common(1)[0][0]]
    pos = {}
    for i, n in enumerate(ref): pos.setdefault(n, i)
    out = []
    for k, lf, d, rows in lst:
        ps = [pos[STOPS[x[0]][0]] for x in rows if STOPS[x[0]][0] in pos]
        up = sum(1 for a, b in zip(ps, ps[1:]) if b > a); down = sum(1 for a, b in zip(ps, ps[1:]) if b < a)
        if up == down and ps: nd = '0' if ps[0] <= len(ref) / 2 else '1'
        else: nd = '0' if up > down else '1'
        if not ps: nd = d
        out.append((k, lf, nd, rows))
    return out
for rk in list(groups):
    if rk not in SPLIT_AT: groups[rk] = fix_dirs(groups[rk])
# trolleybus lines where only some trips are run by buses (the GTFS marks them as bus routes)
TROLLEY_LINES = {'181', 'X'}
first_route = {}
for rid, r in zroutes.items(): first_route.setdefault('y' + re.sub(r'\W', '', r['route_short_name']), r)
for rk in groups:
    r = first_route[rk]; short = r['route_short_name']
    t = 'trol' if (r['route_type'] == '800' or short in TROLLEY_LINES) else 'bus'
    if short.startswith('N'): t = 'night'
    elif re.match(r'^7\d\d$', short): t = 'repl'
    meta_of[rk] = {'id': rk, 'n': short, 't': t, 'op': 'ZKM Gdynia', 'dates': dates[rk]}
n0 = len(ROUTES_OUT); build_routes(groups, meta_of); print('ZKM', len(ROUTES_OUT) - n0)

# ---------------- Rail: S1 (SKM), S2 and S22 (PKM, POLREGIO) ----------------
P = SCR + '/tr'
parent = {}; rstops = {}; plat = {}
for r in rd(P + '/stops.txt'):
    parent[r['stop_id']] = r['parent_station'] or r['stop_id']
    m = re.match(r'\s*(\d+)', r['platform_code'] or ''); plat[r['stop_id']] = m.group(1) if m else ''
    if not r['parent_station']: rstops[r['stop_id']] = r
def station(sid): return parent.get(sid, sid)
rtrips = {}
for r in rd(P + '/trips.txt'):
    if r['route_id'] in ('SKMT_S1', 'PR_REG'): rtrips[r['trip_id']] = r
rst = collections.defaultdict(list)
for r in rd(P + '/stop_times.txt'):
    if r['trip_id'] in rtrips:
        rst[r['trip_id']].append((int(r['stop_sequence']), station(r['stop_id']), tmin(r['departure_time']), r['pickup_type'] or '0', r['drop_off_type'] or '0', plat.get(r['stop_id'], '')))
for v in rst.values(): v.sort()
sname = lambda s: rstops[s]['stop_name']
def corridor(trip_filter, a, b):
    best = None
    for tid, rows in rst.items():
        if not trip_filter(tid): continue
        names = [sname(x[1]) for x in rows]
        if a in names and b in names:
            i, j = sorted((names.index(a), names.index(b)))
            seg = [x[1] for x in rows[i:j + 1]]
            if best is None or len(seg) > len(best): best = seg
    ORDERED.append(list(best or []))
    return set(best or [])
ORDERED = []
AIR = '257530'
names_of = lambda t: [sname(x[1]) for x in rst[t]]
is_pr = lambda t: rtrips[t]['route_id'] == 'PR_REG'
s1_trip = lambda t: rtrips[t]['route_id'] == 'SKMT_S1'
s2_trip = lambda t: is_pr(t) and any(x[1] == AIR for x in rst[t])
s22_trip = lambda t: is_pr(t) and 'Gdańsk Kokoszki' in names_of(t) and 'Gdańsk Wrzeszcz' in names_of(t)
CORR = {
    'kS1': corridor(s1_trip, 'Gdańsk Śródmieście', 'Lębork'),
    'kS2': corridor(s2_trip, 'Gdańsk Wrzeszcz', 'Gdynia Główna') | corridor(s2_trip, 'Gdańsk Główny', 'Gdańsk Osowa'),
    'kS22': corridor(lambda t: s22_trip(t) and not any(x[1] == AIR for x in rst[t]), 'Gdańsk Wrzeszcz', 'Somonino'),
}
ENDS = {'kS1': ('Gdańsk Wrzeszcz', 'Gdynia Główna'), 'kS2': ('Gdańsk Wrzeszcz', 'Gdańsk Osowa'), 'kS22': ('Gdańsk Wrzeszcz', 'Somonino')}
TEST = {'kS1': s1_trip, 'kS2': s2_trip, 'kS22': s22_trip}
ORD = {}
for _rk, _seq in (('kS1', ORDERED[0]), ('kS22', ORDERED[-1])):
    _nm = [sname(x) for x in _seq]
    if _seq and ENDS[_rk][0] in _nm and ENDS[_rk][1] in _nm:
        ORD[_rk] = _seq if _nm.index(ENDS[_rk][0]) < _nm.index(ENDS[_rk][1]) else _seq[::-1]
print('rail corridors', {k: len(v) for k, v in CORR.items()})
for rk, allowed in CORR.items():
    rot = {tid: (rk, r['service_id']) for tid, r in rtrips.items() if TEST[rk](tid)}
    chosen, dates = choose(feed_days(P, rot), 'PKP SKM w Trójmieście' if rk == 'kS1' else 'POLREGIO (Pomorska Kolej Metropolitalna)')
    runs_by = {}
    for tid, k in ((t, kk) for t, lst in chosen.items() for _, kk in lst):
        runs, cur = [], []
        for x in rst[tid]:
            if x[1] in allowed: cur.append(x)
            elif cur: runs.append(cur); cur = []
        if cur: runs.append(cur)
        if not runs: continue
        run = max(runs, key=len)
        if len(run) < 2: continue
        rn = [sname(x[1]) for x in run]; ea, eb = ENDS[rk]
        if ea in rn and eb in rn: d = '0' if rn.index(ea) < rn.index(eb) else '1'
        elif rk in ORD and run[0][1] in ORD[rk] and run[-1][1] in ORD[rk]:
            d = '0' if ORD[rk].index(run[-1][1]) > ORD[rk].index(run[0][1]) else '1'
        else: d = '0' if float(rstops[run[-1][1]]['stop_lat']) > float(rstops[run[0][1]]['stop_lat']) else '1'
        runs_by[(tid, k)] = (k, d, run)
    # one platform per station and direction: the most used one
    pc = collections.defaultdict(collections.Counter)
    for k, d, run in runs_by.values():
        for x in run: pc[(d, x[1])][x[5]] += 1
    groups = collections.defaultdict(list)
    for _key, (k, d, run) in runs_by.items():
        rows2 = []
        for x in run:
            pl = pc[(d, x[1])].most_common(1)[0][0]
            sid = 'k' + x[1] + 'p' + pl
            if sid not in STOPS:
                r = rstops[x[1]]
                STOPS[sid] = [r['stop_name'], pl, round(float(r['stop_lat']), 5), round(float(r['stop_lon']), 5), rail_city(r['stop_name']), 'rail']
            rows2.append((sid, x[2], x[3], x[4]))
        # the track: the trip's shape, cut to the part run inside the corridor ("|c")
        shp = rtrips[_key[0]].get('shape_id')
        if shp: SHAPE_OF.setdefault((rk, tuple(x[0] for x in rows2)), 'r' + shp + '|c')
        full = rst[_key[0]]
        origin = sname(full[0][1]) if full[0][1] in allowed else None
        groups[rk].append((k, False, d, rows2, (origin, sname(full[-1][1]))))
    meta = {'kS1': ('S1', 'PKP SKM w Trójmieście'), 'kS2': ('S2', 'POLREGIO (Pomorska Kolej Metropolitalna)'), 'kS22': ('S22', 'POLREGIO (Pomorska Kolej Metropolitalna)')}[rk]
    n0 = len(ROUTES_OUT)
    build_routes(groups, {rk: {'id': rk, 'n': meta[0], 't': 'rail', 'op': meta[1], 'dates': dates[rk],
                               **({'main_ends': ('Gdańsk Śródmieście', 'Lębork')} if rk == 'kS1' else {})}})
    print('Rail', rk, len(ROUTES_OUT) - n0)


# ---------------- Krynica-Zdrój – Kraków: the trains to and from Krynica-Zdrój, one line per operator ----------------
# PKP Intercity (PKP), POLREGIO (PR) and Koleje Małopolskie (KM), all on the line through Muszyna, Nowy Sącz and Tarnów; each
# train is shown on the part of its run between Krynica-Zdrój and Kraków Główny. The lines belong to the Krynica-Zdrój and
# Muszyna area. Koleje Małopolskie: its trains on that line (K7P), also when they turn back at Nowy Sącz.
KM_BOX = (49.33, 49.47, 20.75, 21.06)   # stations here count as Krynica-Zdrój/Muszyna, the others as outside the area (kmx)
in_km_box = lambda la, lo: KM_BOX[0] <= la <= KM_BOX[1] and KM_BOX[2] <= lo <= KM_BOX[3]
KR_LINES = {   # route_id prefix -> line id, number, operator, colour
    'IC_': ('kIC', 'PKP', 'PKP Intercity', '#f28c00'),
    'PR_': ('kPR', 'PR', 'POLREGIO', '#d7141a'),
}
kr_line = lambda t: next((v for p, v in KR_LINES.items() if t['route_id'].startswith(p)), None)
try:
    kr_station = next(s for s, r in rstops.items() if r['stop_name'] == 'Krynica-Zdrój')
    kr_trips = {}
    for r in rd(P + '/trips.txt'): kr_trips[r['trip_id']] = r
    kr_hit = set()
    for r in rd(P + '/stop_times.txt'):
        if station(r['stop_id']) == kr_station: kr_hit.add(r['trip_id'])
    kml_line = {t for t, r in kr_trips.items() if r['route_id'] in ('KML_K7P', 'KML_K7')}   # Koleje Małopolskie towards Krynica
    krst = collections.defaultdict(list)
    for r in rd(P + '/stop_times.txt'):
        if r['trip_id'] in kr_hit or r['trip_id'] in kml_line:
            krst[r['trip_id']].append((int(r['stop_sequence']), station(r['stop_id']), tmin(r['departure_time']), r['pickup_type'] or '0', r['drop_off_type'] or '0', plat.get(r['stop_id'], '')))
    for v in krst.values(): v.sort()
    # the corridor: the longest run between Krynica-Zdrój and Kraków Główny, in order from Krynica
    kr_seq = []
    for tid, rows in krst.items():
        nm_ = [sname(x[1]) for x in rows]
        if 'Kraków Główny' in nm_ and 'Krynica-Zdrój' in nm_:
            i, j = nm_.index('Krynica-Zdrój'), nm_.index('Kraków Główny')
            seg = [x[1] for x in (rows[i:j + 1] if i < j else rows[j:i + 1][::-1])]
            if len(seg) > len(kr_seq): kr_seq = seg
    kr_allowed = set(kr_seq)
    rot = {}
    for tid in krst:
        if tid not in kr_trips: continue
        ln = kr_line(kr_trips[tid])
        if ln: rot[tid] = (ln[0], kr_trips[tid]['service_id'])
    groups = collections.defaultdict(list); pc = collections.defaultdict(collections.Counter); runs_kr = []; kr_dates = {}
    for pre, (lid, num, op, col) in KR_LINES.items():
        chosen, dates = choose(feed_days(P, {t: v for t, v in rot.items() if v[0] == lid}), op)
        kr_dates[lid] = dates.get(lid)
        for tid, lst in chosen.items():
            run = [x for x in krst[tid] if x[1] in kr_allowed]
            if len(run) < 2: continue
            d = '0' if kr_seq.index(run[-1][1]) > kr_seq.index(run[0][1]) else '1'   # 0: towards Kraków
            for x in run: pc[(d, x[1])][x[5]] += 1
            for _, k in lst: runs_kr.append((tid, lid, k, d, run))
    for tid, lid, k, d, run in runs_kr:
        rows2 = []
        for x in run:
            pl = pc[(d, x[1])].most_common(1)[0][0]
            sid = 'k' + x[1] + 'p' + pl
            if sid not in STOPS:
                r = rstops[x[1]]; la, lo = round(float(r['stop_lat']), 5), round(float(r['stop_lon']), 5)
                STOPS[sid] = [r['stop_name'], pl, la, lo, 'km' if in_km_box(la, lo) else 'kmx', 'rail']
            rows2.append((sid, x[2], x[3], x[4]))
        shp = kr_trips[tid].get('shape_id')
        if shp: SHAPE_OF.setdefault((lid, tuple(x[0] for x in rows2)), 'r' + shp + '|c')
        full = krst[tid]
        groups[lid].append((k, False, d, rows2, (sname(full[0][1]) if full[0][1] in kr_allowed else None, sname(full[-1][1]))))
    for pre, (lid, num, op, col) in KR_LINES.items():
        if not groups.get(lid) or not kr_dates.get(lid): continue
        n0 = len(ROUTES_OUT)
        reaches = any(STOPS[x[0]][0] == 'Krynica-Zdrój' for g in groups[lid] for x in g[3])
        build_routes({lid: groups[lid]}, {lid: {'id': lid, 'n': num, 't': 'rail', 'op': op, 'dates': kr_dates[lid],
                                                **({'main_ends': ('Krynica-Zdrój', 'Kraków Główny')} if reaches else {})}})
        for r in ROUTES_OUT[n0:]: r['c'] = ['km']; r['f'] = True; r['k'] = col; r['cat'] = 'rail'
        print('Kolej Krynica-Zdrój – Kraków,', op + ':', len(groups[lid]), 'kursów')
except StopIteration:
    print('Kolej Krynica-Zdrój – Kraków: brak stacji w danych')


# ---------------- street courses for lines whose feed has no shapes ----------------
KM_SHAPES, KM_KEY = {}, {}
def street_shapes(groups, label, trams=()):
    """routes between consecutive stops on the OpenStreetMap roads (drogi.py; trams also along tram tracks), kept in
    reczne/drogi_cache.json so only new or moved stop pairs are routed again; gives each run of stops its course"""
    pairs = {}
    for rk, tl in groups.items():
        for *_x, rows in tl:
            for a, b in zip(rows, rows[1:]):
                if a[0] != b[0]: pairs.setdefault((a[0], b[0]), rk in trams)
    try:
        import drogi
        _cp = os.path.join(HERE, 'reczne', 'drogi_cache.json')
        _cache = json.load(open(_cp, encoding='utf-8')) if os.path.exists(_cp) else {}
        _key = lambda a, b, t: ('t|' if t else '') + '%s|%s|%s|%s' % (a, b, STOPS[a][2:4], STOPS[b][2:4])
        legs = {pr: _cache[_key(*pr, t)] for pr, t in pairs.items() if _key(*pr, t) in _cache}
        for tram in (False, True):
            miss = {pr for pr, t in pairs.items() if t == tram and _key(*pr, t) not in _cache}
            if not miss: continue
            pos = {sid: STOPS[sid][2:4] for pr in miss for sid in pr}
            router = None
            if tram:
                lats = [q[0] for q in pos.values()]; lons = [q[1] for q in pos.values()]
                router = drogi.TileRouter((min(lats) - .01, max(lats) + .01, min(lons) - .015, max(lons) + .015), log=lambda m: print(label + ',', m), costs=dict(drogi.COST, transit=.9))
            new, odd = drogi.road_legs(miss, pos, log=lambda m: print(label + ',', m), router=router)
            legs.update(new); _cache.update({_key(*pr, tram): v for pr, v in new.items()})
        json.dump(_cache, open(_cp, 'w', encoding='utf-8'), separators=(',', ':'))
        print('%s: przebieg po ulicach dla %d z %d odcinków' % (label, len(legs), len(pairs)))
    except Exception as e:
        print('%s: bez przebiegu po ulicach (%s)' % (label, e)); return
    for rk, tl in groups.items():
        for *_x, rows in tl:
            ids = tuple(x[0] for x in rows)
            if (rk, ids) in SHAPE_OF: continue
            pts = []
            for a, b in zip(ids, ids[1:]):
                if a == b: continue
                seg = legs.get((a, b)) or [STOPS[a][2:4], STOPS[b][2:4]]
                pts += seg if not pts else seg[1:]
            k = KM_KEY.setdefault(json.dumps(pts), 'k%d' % len(KM_KEY)); KM_SHAPES[k] = pts; SHAPE_OF[(rk, ids)] = k


# ---------------- Bydgoszcz: ZDMiKP ----------------
P = SCR + '/byd'
bstops = list(rd(P + '/stops.txt'))
# the feed has no pole numbers: number the poles of each stop name in the order of their ids (01, 02, …)
_poles = collections.defaultdict(list)
bname = lambda r: re.sub(r'\s+-\s+Peron\s+\d+$', '', r['stop_name'].strip())   # "Bielawy - Peron 1" is a pole of Bielawy
for r in sorted(bstops, key=lambda r: r['stop_id']): _poles[bname(r)].append(r['stop_id'])
for r in bstops:
    n = bname(r); l = _poles[n]
    STOPS['b' + r['stop_id']] = [n, '%02d' % (l.index(r['stop_id']) + 1) if len(l) > 1 else '', round(float(r['stop_lat']), 5), round(float(r['stop_lon']), 5), 'byd']
broutes = {r['route_id']: r for r in rd(P + '/routes.txt')}
rot = {}; tmeta = {}
for r in rd(P + '/trips.txt'):
    if r['route_id'] not in broutes: continue
    key = 'b' + re.sub(r'\W', '', broutes[r['route_id']]['route_short_name'])
    rot[r['trip_id']] = (key, r['service_id'])
    # no direction_id in this feed (fix_dirs sorts the trips); runs to or from a depot are marked by the headsign
    tmeta[r['trip_id']] = (r.get('direction_id') or '0', bool(re.search(r'Zajezdnia', r.get('trip_headsign', ''))))
chosen, dates = choose(feed_days(P, rot), 'ZDMiKP Bydgoszcz')
st = collections.defaultdict(list)
for r in rd(P + '/stop_times.txt'):
    if r['trip_id'] in chosen:
        st[r['trip_id']].append((int(r['stop_sequence']), 'b' + r['stop_id'], tmin(r['departure_time']), r.get('pickup_type') or '0', r.get('drop_off_type') or '0'))
groups = collections.defaultdict(list); meta_of = {}
for tid, rows in st.items():
    rows.sort(); rows = [(x[1], x[2], x[3], x[4]) for x in rows if not (x[3] == '1' and x[4] == '1')]
    if len(rows) < 2: continue
    for rk, k in chosen[tid]: groups[rk].append((k, tmeta[tid][1], tmeta[tid][0], rows))
for rk in list(groups): groups[rk] = fix_dirs(groups[rk])
first_b = {}
for rid, r in broutes.items(): first_b.setdefault('b' + re.sub(r'\W', '', r['route_short_name']), r)
for rk in groups:
    r = first_b[rk]; short = r['route_short_name']
    t = 'tram' if r['route_type'] == '0' else 'bus'
    if re.match(r'^\d+N$', short): t = 'night'
    elif short.startswith('Za'): t = 'repl'   # ZaT, ZaT6: buses replacing trams
    meta_of[rk] = {'id': rk, 'n': short, 't': t, 'op': 'ZDMiKP Bydgoszcz', 'dates': dates[rk]}
street_shapes(groups, 'Bydgoszcz', trams={rk for rk, m in meta_of.items() if m['t'] == 'tram'})   # the feed has no shapes
n0 = len(ROUTES_OUT); build_routes(groups, meta_of); print('ZDMiKP Bydgoszcz', len(ROUTES_OUT) - n0)


# ---------------- Krynica-Zdrój and Muszyna: no open data, timetables written down from the PDFs (reczne/) ----------------
def pl_holidays(y):
    a = y % 19; b = y // 100; c = y % 100; d = (19 * a + b - b // 4 - (b - (8 * b + 13) // 25) + 15) % 30
    e = (32 + 2 * (b % 4) + 2 * (c // 4) - d - c % 4) % 7; f = d + e - 7 * ((a + 11 * d + 22 * e) // 451) + 114
    easter = datetime.date(y, f // 31, f % 31 + 1)
    fixed = [(1, 1), (1, 6), (5, 1), (5, 3), (8, 15), (11, 1), (11, 11), (12, 24), (12, 25), (12, 26)]
    return {datetime.date(y, m, d_).strftime('%Y%m%d') for m, d_ in fixed} | {(easter + datetime.timedelta(days=k)).strftime('%Y%m%d') for k in (0, 1, 60)}
MANUAL = os.path.join(HERE, 'reczne', 'krynica_muszyna.json')
if os.path.exists(MANUAL):
    KMD = json.load(open(MANUAL, encoding='utf-8'))
    # more lines of the area, kept in a file of their own (reczne/narzedzia/make_dodatkowe.py): the RAFATEX private
    # line to Nowy Sącz and the cross-border bus to Bardejov; their stops outside the area are marked 'kmx'
    EXTRA = os.path.join(HERE, 'reczne', 'km_dodatkowe.json')
    if os.path.exists(EXTRA):
        _x = json.load(open(EXTRA, encoding='utf-8'))
        for sid, v in _x['stops'].items(): KMD['stops'].setdefault(sid, v)
        KMD['lines'].update(_x['lines']); KMD['trips'] += _x['trips']; KMD.setdefault('legs', {}).update(_x.get('legs', {}))
    for sid, (n, num, la, lo, *_x) in KMD['stops'].items(): STOPS[sid] = [n, num, la, lo, _x[1] if len(_x) > 1 else 'km']
    # MPGK Krynica-Zdrój: its own timetables number lines by days (K6 all Saturday runs, K7 all Sunday runs, K5 every
    # village); here each run is given the line of its route, so that a line keeps one route on every day
    # one route per line; a run that leaves its line's route (via Pułaskiego, Zieleniewskiego, Szkolna, …) gets the
    # line number + 10 (K1 -> K11, K3 -> K13, …)
    # numbering 10–18: mpgk_line() sorts the runs into routes (10A, 10B…); runs with the same number make one line,
    # the routes other than the main one become its variants
    MPGK_LINES = {
        '10': ('#c62828', 'Czarny Potok Gondola – Centrum – Słotwińska Pętla'),
        '11': ('#1565c0', 'Zawodzie – Czarny Potok – Źródlana – Centrum – Stara Droga Gazownia'),
        '12': ('#b7791f', 'Zawodzie – Reymonta – Czarny Potok'),
        '13': ('#2e7d32', 'Czarny Potok – Centrum – Pułaskiego – Tylicz Rynek'),
        '14': ('#ad1457', 'Czarny Potok – Centrum – Tylicz – Muszynka'),
        '15': ('#e65100', 'Czarny Potok – Centrum – Mochnaczka – Tylicz Rynek'),
        '16': ('#6a1b9a', 'Zawodzie – Centrum – Mochnaczka Wyżna – Berest – Polany'),
        '17': ('#00838f', 'Zawodzie – Centrum – Zieleniewskiego – Czyrna – Piorunka – Polany'),
        '18': ('#5d4037', 'Tylicz – Mochnaczka / Muszynka – Czyrna – Piorunka – Polany'),
    }
    MPGK_SRC = {k for k, v in KMD['lines'].items() if 'MPGK' in v.get('op', '')} | {t['line'] for t in KMD['trips'] if re.fullmatch(r'K\d+', t['line'])}
    _KZ = 'Krynica-Zdrój '
    _sid = {v[0]: k for k, v in KMD['stops'].items()}
    _nm = lambda s: KMD['stops'][s][0].replace(_KZ, '')
    _mi = lambda x: int(x[:2]) * 60 + int(x[3:])
    def _mpgk_norm(st):
        """Akademia Rolnicza and Czarny Potok Pętla are served by every run between Czarny Potok and the Gondola"""
        G, AK, AZ, OS, PE = 'Czarny Potok Gondola', 'Czarny Potok Akademia Rolnicza', 'Czarny Potok Azoty', 'Czarny Potok Osiedle', 'Czarny Potok Pętla'
        st = [[_nm(s), _mi(t)] for s, t in st]; out = []
        for x in st:
            if out and {out[-1][0], x[0]} == {G, AZ}: out.append([AK, (out[-1][1] + x[1]) // 2])
            out.append(x)
        st = out; n = [x[0] for x in st]
        for i in range(len(st) - 1, 0, -1):
            if n[i] == AZ and n[i - 1] == OS and not (i >= 3 and n[i - 2] == PE):
                tt = st[i - 1][1]; st[i:i] = [[PE, tt + 1], [OS, tt + 2]]; n = [x[0] for x in st]
        for i in range(len(st) - 2):
            if n[i] == AZ and n[i + 1] == OS and n[i + 2] != PE:
                tt = st[i + 1][1]; st[i + 2:i + 2] = [[PE, tt + 1], [OS, tt + 2]]; n = [x[0] for x in st]
        for i in range(1, len(st)):
            if st[i][1] < st[i - 1][1]: st[i][1] = st[i - 1][1]
        return [[_sid[_KZ + a] if _KZ + a in _sid else _sid[a], '%02d:%02d' % divmod(b, 60)] for a, b in st]
    def mpgk_line(n):
        j = ' | '.join(n); h = lambda w: w in j
        bank = h('Zdrojowa Bank'); zr = h('Źródlana'); zi = h('Zieleniewskiego'); pu = h('Pułaskiego')
        if not bank:
            if h('Tylicz') or h('Polany') or h('Berest') or h('Piorunka'):
                if h('Mochnaczka Wyżna') and h('Berest'): return '18B'
                return '18A' if h('Czyrna') else '18C'
            if h('Reymonta'): return '12'
        if h('Czyrna') or (zi and (h('Piorunka') or h('Polany'))): return '17B' if zr else '17A'
        if h('Berest') or h('Polany') or h('Piorunka'): return '16B' if zr else '16A'
        if h('Muszynka'): return '15B' if h('Mochnaczka') else ('14B' if zr else '14A')
        if h('Tylicz'):
            if h('Mochnaczka'): return '15A'
            return '13C' if zi else '13B' if zr else '13A'
        if h('Stara Droga') or h('Jastrzębia ZAiKS'): return '11B' if zi else '11A' if zr else '11C'
        if h('Słotwińska'): return '10C' if zr else '10B' if pu else '10A'
        return '10A'
    for t in KMD['trips']:
        if t['line'] in MPGK_SRC:
            t['st'] = _mpgk_norm(t['st']); t['line'] = mpgk_line([_nm(s) for s, _ in t['st']])[:2]   # 10A/10B/10C -> one line 10 with variants
    for k in MPGK_SRC: KMD['lines'].pop(k, None)
    # an obvious slip in the timetables: towards Zawodzie the runs from Stara Droga stop at Piłsudskiego Szkoła after Stara Droga Kościół
    def _ins(st, i, name):
        if name not in _sid: return st
        tt = (_mi(st[i - 1][1]) + _mi(st[i][1])) // 2
        return st[:i] + [[_sid[name], '%02d:%02d' % divmod(tt, 60)]] + st[i:]
    for t in KMD['trips']:
        if not t['line'].startswith('11'): continue
        n = [KMD['stops'][x][0] for x, _ in t['st']]
        if n[-1].endswith('Zawodzie Pętla') and 'Krynica-Zdrój Stara Droga Kościół' in n:
            i = n.index('Krynica-Zdrój Stara Droga Kościół') + 1
            if i < len(n) and n[i] != 'Krynica-Zdrój Piłsudskiego Szkoła': t['st'] = _ins(t['st'], i, 'Krynica-Zdrój Piłsudskiego Szkoła')
    for k, (col, desc) in MPGK_LINES.items():
        KMD['lines'][k] = dict(KMD['lines'].get(k, {}), op='MPGK Krynica-Zdrój', name=k, color=col, desc=desc)
    hol = pl_holidays(TODAY.year) | pl_holidays(TODAY.year + 1)
    groups = collections.defaultdict(list)
    legs = KMD.get('legs', {})   # road route between two consecutive stops (reczne/narzedzia/route_km.py)
    # MPGK poles: the stop number of its own timetables (e.g. 9a/9b at Kraszewskiego Szpital, 32b at Stara Droga
    # Gazownia; reczne/mpgk_slupki.json). Where a stop has two poles, a trip takes the one whose timetable lists
    # its destination; the pole becomes a stop of its own (id with "_a"/"_b")
    _sl_p = os.path.join(HERE, 'reczne', 'mpgk_slupki.json')
    SLUP = json.load(open(_sl_p, encoding='utf-8')) if os.path.exists(_sl_p) else {}
    _fold = lambda x: re.sub(r'[^A-Z0-9]', '', __import__('unicodedata').normalize('NFD', x.upper().replace('Ł', 'L')).encode('ascii', 'ignore').decode())
    for sid, P_ in SLUP.items():
        if sid in STOPS and '-' in P_: STOPS[sid][1] = P_['-']['code']
    def _pole(sid, dest):
        P_ = SLUP.get(sid)
        if not P_ or '-' in P_ or sid not in STOPS: return sid
        fd = _fold(dest); fd += 'GONDOLA' if 'CZARNYPOTOK' in fd else ''   # Czarny Potok Pętla/Osiedle: the Gondola side
        side = next((k for k in ('b', 'a') if k in P_ and any(_fold(w) in fd for w in P_[k]['tok'])), 'a' if 'a' in P_ else 'b')
        v = sid + '_' + side
        if v not in STOPS: STOPS[v] = [STOPS[sid][0], P_[side]['code']] + STOPS[sid][2:]
        return v
    _base = lambda x: x.split('_')[0]
    for t in KMD['trips']:
        _dest = STOPS[t['st'][-1][0]][0] if t['st'][-1][0] in STOPS else ''
        t = dict(t, st=[[_pole(sid, _dest), tm] for sid, tm in t['st']]) if SLUP else t
        rows = [(sid, tmin(tm + ':00'), '0', '0') for sid, tm in t['st']]
        ids = tuple(sid for sid, _ in t['st']); rk = KMD['lines'].get(t['line'], {}).get('area', 'km') + t['line']   # a line can belong to Nowy Sącz ('area': 'ns')
        if legs and (rk, ids) not in SHAPE_OF:   # the trip's street geometry: its legs joined (a straight line where none)
            pts = []
            for a, b in zip(ids, ids[1:]):
                if a == b: continue
                seg = legs.get(_base(a) + ' ' + _base(b)) or (legs.get(_base(b) + ' ' + _base(a)) or [])[::-1] or [STOPS[a][2:4], STOPS[b][2:4]]   # the other way round, else straight
                pts += seg if not pts else seg[1:]
            k = KM_KEY.setdefault(json.dumps(pts), 'k%d' % len(KM_KEY)); KM_SHAPES[k] = pts; SHAPE_OF[(rk, ids)] = k
        for k, day in DAYS.items():
            if k[0] in t['days'] and (day not in hol or k[0] == 'h'):   # on a holiday the Sunday timetable runs
                groups[rk].append((k, 0, '0', rows))
            # f: weekdays without school (RAFATEX): a timetable of its own, shown as a fourth column ("Dni robocze wolne od szkoły")
            if k[0] == 'w' and 'f' in t['days'] and day not in hol:
                groups[rk].append(('f' + k[1:], 0, '0', rows))
    meta = {}
    for rk in groups:
        groups[rk] = fix_dirs(groups[rk])
        ln = rk[2:]
        meta[rk] = {'id': rk, 'n': KMD['lines'].get(ln, {}).get('name', ln), 't': 'bus', 'op': KMD['lines'].get(ln, {}).get('op', ''), 'dates': {k: v for k, v in DAYS.items()},
                    **({'cat': KMD['lines'][ln]['cat']} if KMD['lines'].get(ln, {}).get('cat') else {}),
                    **({'main_not': KMD['lines'][ln]['main_not']} if KMD['lines'].get(ln, {}).get('main_not') else {})}
    n0 = len(ROUTES_OUT); build_routes(groups, meta)
    # every line here has a colour of its own (set in the manual file), whatever its frequency
    for r in ROUTES_OUT[n0:]:
        col = KMD['lines'].get(r['id'][2:], {}).get('color')
        if col: r['f'] = True; r['k'] = col
        r['c'] = [KMD['lines'].get(r['id'][2:], {}).get('area', 'km')]   # also the lines that run on beyond the area (Nowy Sącz, Bardejov)
        cat = KMD['lines'].get(r['id'][2:], {}).get('cat')
        if cat: r['cat'] = cat
    print('Krynica-Zdrój i Muszyna (rozkłady spisane z PDF):', len(ROUTES_OUT) - n0, 'linii')

# ---------------- Nowy Sącz: MPK Nowy Sącz with the neighbouring gminas it serves ----------------
# MPK publishes no GTFS; its website's timetable service gives every line with its trips (start time, the days it runs,
# the running time from stop to stop, in seconds) and the stops with their positions. There are no route shapes: the streets
# between stops are found on the OpenStreetMap road network (drogi.py).
NS_API = 'https://www.mpk.nowysacz.pl/wp-json/mpk/v1/timetable'
def ns_get(path):
    err = None
    for i in range(4):
        try:
            req = urllib.request.Request(NS_API + path, headers={'User-Agent': 'rozklady-trojmiasto/1.0'})
            with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)
        except Exception as e: err = e; time.sleep(5 * (i + 1))
    raise err
try: NSA = ns_get('/active')
except Exception as e: NSA = None; print('MPK Nowy Sącz: nie udało się pobrać rozkładu (%s)' % e)
if NSA:
    hol = pl_holidays(TODAY.year) | pl_holidays(TODAY.year + 1)
    WDK = ['is_monday', 'is_tuesday', 'is_wednesday', 'is_thursday', 'is_friday', 'is_saturday', 'is_sunday']
    # "Bulwar Narwiku - Dw. MPK st. 2": the stand is the pole; "Nawojowska-Graniczna" written as "Nawojowska - Graniczna"
    nsname = lambda n: re.sub(r'\s*-$', '', re.sub(r'\s+st\.\s*\d+$', '', re.sub(r'\s*-\s*', ' - ', ' '.join(n.split()))))
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        ns_lines = list(ex.map(lambda L: (L, ns_get('/line/%d' % L['id'])), NSA['lines']))
    groups = collections.defaultdict(list); meta = {}; ns_kind = {}
    for L, D in ns_lines:
        rk = 'ns' + re.sub(r'\W', '', L['name']); ns_kind[rk] = L.get('type')
        for v in D.get('variants', []):
            for run in v.get('runs', []):
                rows = []; cum = 0
                for x in run.get('stops', []):
                    if 'stop_order' not in x: continue   # the first entry repeats the first stop with the start time
                    cum += x.get('stop_time') or 0   # seconds from the previous stop
                    sid = 'ns' + x['number']   # five digits: the stop and, last, its pole
                    if sid not in STOPS:
                        STOPS[sid] = [nsname(x['name']), '0' + x['number'][-1], round(float(x['latitude']), 5), round(float(x['longitude']), 5), 'ns']
                    rows.append((sid, run['start_time'] + round(cum / 60), '0', '0'))
                if len(rows) < 2: continue
                d = '0' if run.get('direction') == 1 else '1'
                for k, day in DAYS.items():
                    wd = 6 if day in hol else datetime.date(int(day[:4]), int(day[4:6]), int(day[6:])).weekday()   # holidays: the Sunday timetable
                    if run.get(WDK[wd]): groups[rk].append((k, 0, d, rows))
        meta[rk] = {'id': rk, 'n': L['name'], 't': 'night' if L.get('type') == 2 else 'bus', 'op': 'MPK Nowy Sącz', 'dates': {k: v for k, v in DAYS.items()}}
    # streets between stops
    pairs = {(a[0], b[0]) for tl in groups.values() for *_x, rows in tl for a, b in zip(rows, rows[1:]) if a[0] != b[0]}
    try:
        import drogi
        # street routes are kept between updates (reczne/drogi_cache.json): only new or moved stop pairs are routed again,
        # so the road tiles are fetched only when something changed
        _cp = os.path.join(HERE, 'reczne', 'drogi_cache.json')
        _cache = json.load(open(_cp, encoding='utf-8')) if os.path.exists(_cp) else {}
        _key = lambda a, b: '%s|%s|%s|%s' % (a, b, STOPS[a][2:4], STOPS[b][2:4])
        legs = {pr: _cache[_key(*pr)] for pr in pairs if _key(*pr) in _cache}
        _miss = {pr for pr in pairs if _key(*pr) not in _cache}
        if _miss:
            _new, odd = drogi.road_legs(_miss, {sid: STOPS[sid][2:4] for pr in _miss for sid in pr}, log=lambda m: print('Nowy Sącz,', m))
            legs.update(_new); _cache.update({_key(*pr): v for pr, v in _new.items()})
            json.dump(_cache, open(_cp, 'w', encoding='utf-8'), separators=(',', ':'))
        print('Nowy Sącz: przebieg po ulicach dla %d z %d odcinków' % (len(legs), len(pairs)))
    except Exception as e:
        legs = {}; print('Nowy Sącz: bez przebiegu po ulicach (%s)' % e)
    if legs:
        for rk, tl in groups.items():
            for *_x, rows in tl:
                ids = tuple(x[0] for x in rows)
                if (rk, ids) in SHAPE_OF: continue
                pts = []
                for a, b in zip(ids, ids[1:]):
                    if a == b: continue
                    seg = legs.get((a, b)) or [STOPS[a][2:4], STOPS[b][2:4]]
                    pts += seg if not pts else seg[1:]
                k = KM_KEY.setdefault(json.dumps(pts), 'k%d' % len(KM_KEY)); KM_SHAPES[k] = pts; SHAPE_OF[(rk, ids)] = k
    n0 = len(ROUTES_OUT); build_routes(groups, meta)
    for r in ROUTES_OUT[n0:]: r['g'] = {0: 'p', 1: 'm', 2: 'n'}.get(ns_kind.get(r['id']), 'p')   # suburban, city, night (sections of the board)
    print('MPK Nowy Sącz (rozkład %s – %s):' % (NSA.get('valid_from'), NSA.get('valid_to')), len(ROUTES_OUT) - n0, 'linii')


# ---------------- Poznań, Kraków, Warszawa: city GTFS feeds ----------------
# Each city is an area of its own (poz, krk, waw). Poles: the stop code's last digits (Poznań, Warszawa) or the pole given
# in the feed (Kraków). Line kinds: trams, buses, night lines (Poznań 2xx, Kraków 6xx, Warszawa N…), replacement lines,
# metro and urban rail (Warszawa: M1, M2, SKM) as trains. The route files of these areas are packed several to a file
# (data/rp/), and their network map has a file of its own (data/map_<area>.json), so that the page loads only what it shows.
NEW_AREAS = {
    'poz': {'op': 'ZTM Poznań', 'feeds': [('poz', 'P')], 'rk': 'pz'},
    'krk': {'op': 'ZTP Kraków', 'feeds': [('krkA', 'KA'), ('krkT', 'KT')], 'rk': 'kr'},
    'waw': {'op': 'ZTM Warszawa', 'feeds': [('waw', 'W')], 'rk': 'wa'},
    'wej': {'op': 'MZK Wejherowo', 'feeds': [('wej', 'J')], 'rk': 'wj'},
    'ldz': {'op': 'MPK Łódź', 'feeds': [('ldz', 'L')], 'rk': 'ld'},
    'fl': {'op': 'Aktiv Bus Flensburg', 'feeds': [('fl', 'F')], 'rk': 'fl'},
    'prg': {'op': 'PID Praha', 'feeds': [('prg', 'G')], 'rk': 'pg'},
}
def wej_name(n):
    """MZK Wejherowo writes the pole and the on-request mark into the name ("Bolszewo Słowackiego 01", "… n/ż")"""
    n = re.sub(r'\s+n/ż$', '', n.strip()); m = re.match(r'^(.*?)\s+(\d{2})$', n)
    return (m.group(1), m.group(2)) if m else (n, '')
def fl_name(n):
    """Aktiv Bus Flensburg writes the platform and the way into the name ("Angelburger Str. B1 > Südermarkt 3,7", "Bahnhof Richtung ZOB")"""
    n = re.sub(r'\s*-?>.*$', '', n.strip()); n = re.sub(r'\s+Richtung\s.*$', '', n); n = re.sub(r'\s+Ring [AB]\b.*$', '', n)
    n = re.sub(r'^Flensburg[ ,]+(?=\S)', '', n)   # the city's own name in front of its stops (Schleswig-Holstein data)
    m = re.match(r'^(.*?)\s+B(\d)$', n)
    return (m.group(1).strip(), '%02d' % int(m.group(2))) if m else (n.strip(), '')
SEQ_POLE = collections.defaultdict(dict)   # Łódź, Flensburg: the poles of a stop numbered 01, 02… in the feed's order
def seq_pole(area, name, sid):
    d = SEQ_POLE[(area, name)]
    if sid not in d: d[sid] = '%02d' % (len(d) + 1)
    return d[sid]
def city_name(area, r):
    if area == 'wej': return wej_name(r['stop_name'])[0]
    if area == 'fl': return fl_name(r['stop_name'])[0]
    return r['stop_name'].strip()
def city_pole(area, r):
    if area == 'wej': return wej_name(r['stop_name'])[1]
    if area == 'fl': return fl_name(r['stop_name'])[1] or seq_pole(area, fl_name(r['stop_name'])[0], r['stop_id'])
    if area == 'ldz': return seq_pole(area, r['stop_name'].strip(), r['stop_id'])
    if area == 'prg': return (r.get('platform_code') or '').strip() or seq_pole(area, r['stop_name'].strip(), r['stop_id'])
    if area == 'krk':
        for v in (r.get('stop_desc'), r.get('platform_code'), (r.get('stop_code') or '').split('-')[-1]):
            if v and re.fullmatch(r'\d{1,2}', v.strip()): return '%02d' % int(v)
        return ''
    m = re.search(r'(\d{2})$', r.get('stop_code') or '')
    return m.group(1) if m else ''
def city_kind(area, short, rtype):
    if area == 'prg' and rtype == '0' and re.fullmatch(r'9\d', short): return 'night'   # Prague night trams 91–99
    if rtype in ('1', '2', '7', '100', '109', '400', '401'): return 'rail'
    if area == 'poz' and re.fullmatch(r'2\d\d', short): return 'night'   # night lines, trams among them
    if area == 'krk' and re.fullmatch(r'6\d\d', short): return 'night'
    if area == 'krk' and rtype in ('0', '900') and re.fullmatch(r'6\d', short): return 'night'   # night trams 62, 64, 69
    if rtype in ('0', '900'): return 'tram' if not short.startswith('N') else 'night'
    if area == 'waw':
        if short.startswith('N'): return 'night'
        if short.startswith('Z'): return 'repl'
    if area == 'poz':
        if re.fullmatch(r'2\d\d', short): return 'night'
        if short.startswith('T'): return 'repl'
    if area == 'krk':
        if re.fullmatch(r'6\d\d', short): return 'night'
        if re.fullmatch(r'7\d\d', short): return 'repl'
    if area in ('ldz', 'fl') and short.startswith('N'): return 'night'
    if area == 'prg':
        if rtype == '11': return 'trol'
        if re.fullmatch(r'9\d\d', short): return 'night'
        if short.startswith('X'): return 'repl'
    if area == 'ldz' and short.startswith('Z'): return 'repl'
    return 'bus'
NEW_ROUTE_IDS = collections.defaultdict(list)
for area, A in NEW_AREAS.items():
    try:
        rot, tmeta, rmeta, tkey = {}, {}, {}, {}
        for fd, pre in A['feeds']:
            P = SCR + '/' + fd
            for r in rd(P + '/stops.txt'):
                if (r.get('location_type') or '0') not in ('0', ''): continue
                STOPS[pre + r['stop_id']] = [city_name(area, r), city_pole(area, r), round(float(r['stop_lat']), 5), round(float(r['stop_lon']), 5), area]
            routes = {r['route_id']: r for r in rd(P + '/routes.txt')}
            for r in rd(P + '/trips.txt'):
                rt = routes.get(r['route_id'])
                if not rt: continue
                short = rt['route_short_name'].strip()
                if area == 'fl': short = short.replace(' ', '')   # Flensburg: 8A, not 8 A
                if area == 'poz' and short == 'PKS': continue   # Poznań: PKS Poznań's regional line (no ZTM fares), not shown
                if area == 'ldz' and re.fullmatch(r'o?[PR]\d+', short): continue   # Łódź: staff and works lines, not for passengers
                if area == 'prg' and not (rt['route_type'] == '2' and re.fullmatch(r'S\d+', short)) and (rt.get('is_regional') == '1' or rt['route_type'] == '2' or re.match(r'(MHD|BB\d|IKEA)', short)): continue   # Prague: the city lines and the Esko (S) trains
                rk = A['rk'] + re.sub(r'\W', '', short)
                tid = pre + ':' + r['trip_id']
                rot[tid] = (rk, pre + ':' + r['service_id']); tmeta[tid] = (r.get('direction_id') or '0',)
                rmeta.setdefault(rk, (short, rt['route_type']))
                if r.get('shape_id'): TSHAPE[tid] = pre + 's' + r['shape_id']
        # the calendars of all feeds of the city, with their service ids prefixed like the trips
        svc = collections.defaultdict(set)
        for fd, pre in A['feeds']:
            P = SCR + '/' + fd
            if os.path.exists(P + '/calendar.txt'):
                for r in rd(P + '/calendar.txt'):
                    d0 = datetime.datetime.strptime(r['start_date'], '%Y%m%d').date(); d1 = datetime.datetime.strptime(r['end_date'], '%Y%m%d').date()
                    wdn = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']; x = d0
                    while x <= d1:
                        if r[wdn[x.weekday()]] == '1': svc[pre + ':' + r['service_id']].add(x.strftime('%Y%m%d'))
                        x += datetime.timedelta(days=1)
            if os.path.exists(P + '/calendar_dates.txt'):
                for r in rd(P + '/calendar_dates.txt'):
                    k = pre + ':' + r['service_id']
                    if r['exception_type'] == '1': svc[k].add(r['date'])
                    else: svc[k].discard(r['date'])
        window = {(TODAY + datetime.timedelta(days=i)).strftime('%Y%m%d') for i in range(WINDOW_DAYS)}
        by = collections.defaultdict(list)
        for tid, (rk, sv) in rot.items():
            for d in svc.get(sv, ()):
                if d in window: by[(rk, d)].append(tid)
        chosen, dates = choose(by, A['op'])
        st = collections.defaultdict(list)
        for fd, pre in A['feeds']:
            P = SCR + '/' + fd
            with open(P + '/stop_times.txt', encoding='utf-8-sig') as fh:
                rdr = csv.reader(fh); hdr = next(rdr); ix = {h: i for i, h in enumerate(hdr)}
                it, iseq, isid, idep = ix['trip_id'], ix['stop_sequence'], ix['stop_id'], ix['departure_time']
                ipu, ido = ix.get('pickup_type'), ix.get('drop_off_type')
                for row in rdr:
                    tid = pre + ':' + row[it]
                    if tid not in chosen: continue
                    st[tid].append((int(row[iseq]), pre + row[isid], tmin(row[idep]), (row[ipu] if ipu is not None else '') or '0', (row[ido] if ido is not None else '') or '0'))
        groups = collections.defaultdict(list); meta_of = {}
        # trips given by frequency (frequencies.txt, e.g. the Warsaw metro): one trip for every headway of each period
        freq = collections.defaultdict(list)
        for fd, pre in A['feeds']:
            fp = SCR + '/' + fd + '/frequencies.txt'
            if os.path.exists(fp):
                for r in rd(fp): freq[pre + ':' + r['trip_id']].append((tmin(r['start_time']), tmin(r['end_time']), int(r['headway_secs']) / 60))
        for tid, rows in st.items():
            rows.sort(); rows = [(x[1], x[2], x[3], x[4]) for x in rows if not (x[3] == '1' and x[4] == '1') and x[1] in STOPS]
            if len(rows) < 2: continue
            runs = [rows]
            if tid in freq:
                runs = []; t0 = rows[0][1]
                for a0, b0, hw in sorted(freq[tid]):
                    t = float(a0)
                    while t < b0 - 1e-6:
                        sh = round(t) - t0; runs.append([(x[0], x[1] + sh, x[2], x[3]) for x in rows]); t += hw
            for rk, k in chosen[tid]:
                for rr in runs: groups[rk].append((k, False, tmeta[tid][0], rr))
                if tid in TSHAPE: SHAPE_OF.setdefault((rk, tuple(x[0] for x in rows)), TSHAPE[tid])
        del st
        for rk in groups:
            short, rtype = rmeta[rk]
            meta_of[rk] = {'id': rk, 'n': short, 't': city_kind(area, short, rtype), 'op': A['op'], 'dates': dates[rk]}
        if area == 'fl' and not os.path.exists(SCR + '/fl/shapes.txt'): street_shapes(groups, 'Flensburg')   # only if the feed has no shapes
        n0 = len(ROUTES_OUT); build_routes(groups, meta_of)
        for r in ROUTES_OUT[n0:]: r['c'] = [area]; NEW_ROUTE_IDS[area].append(r['id'])
        for r in ROUTES_OUT[n0:]:   # night trams (Poznań 2xx, Kraków 62, 64, 69): night lines, drawn round like trams
            if r['t'] == 'night' and r['id'] in rmeta and rmeta[r['id']][1] in ('0', '900'): r['nt'] = True; r['f'] = False
        if area == 'poz':   # Poznań's trams in MPK Poznań's own colours (route_color in the feed), with its text colour
            pc = {}
            for r in rd(SCR + '/poz/routes.txt'):
                if r['route_type'] == '0' and r.get('route_color') and r['route_color'].upper() not in ('FFFFFF', '000000'):
                    pc[r['route_short_name'].strip()] = (r['route_color'], r.get('route_text_color') or 'FFFFFF')
            for r in ROUTES_OUT[n0:]:
                if r['t'] == 'tram' and r['n'] in pc: r['f'] = True; r['k'] = '#' + pc[r['n']][0]; r['kt'] = '#' + pc[r['n']][1]
        # line colours of the operators: MZK Wejherowo (its website), Aktiv Bus Flensburg (its network map), the Prague metro (feed)
        AREA_LINE_COLORS = {
            'wej': {'1': ('#3d86c6', '#fff'), '2': ('#fbd92c', '#222'), '3': ('#e8262f', '#fff'), '4': ('#f39433', '#fff'), '5': ('#7b4f92', '#fff'),
                    '6': ('#b85f25', '#fff'), '7': ('#4b2840', '#fff'), '8': ('#00735e', '#fff'), '9': ('#b9b3d6', '#222'), '10': ('#79c02a', '#fff'),
                    '11': ('#1d3576', '#fff'), '12': ('#8f2743', '#fff'), '13': ('#db3b8a', '#fff'), '16': ('#9a8e83', '#fff'), '17': ('#6f86b6', '#fff'),
                    '18': ('#4fa47c', '#fff'), '19': ('#d8ae5f', '#222'), '701': ('#e4e2dc', '#222')},
            'fl': {'1': ('#00a651', '#fff'), '2': ('#ffcc00', '#222'), '3': ('#a6ce39', '#222'), '4': ('#f4a8c8', '#222'), '5A': ('#ed1c24', '#fff'), '5B': ('#ed1c24', '#fff'),
                   '7': ('#6d8fcb', '#fff'), '8A': ('#485b8c', '#fff'), '8B': ('#485b8c', '#fff'), '10': ('#8dd3f2', '#222'), '11': ('#a5408a', '#fff'),
                   '12': ('#33b89a', '#fff'), '14': ('#f58220', '#fff')},
            'prg': {'A': ('#00a562', '#fff'), 'B': ('#f8b322', '#222'), 'C': ('#cf003d', '#fff')},
            'waw': {'M1': ('#1d58a6', '#fff'), 'M2': ('#e2001a', '#fff')},
        }.get(area, {})
        for r in ROUTES_OUT[n0:]:   # Prague: metro and the funicular in sections of their own
            if area == 'prg' and r['id'] in rmeta: r['cat'] = {'1': 'metro', '7': 'cable', '4': 'ferry'}.get(rmeta[r['id']][1], r.get('cat'))
            if area == 'waw' and r['id'] in rmeta and rmeta[r['id']][1] == '1': r['cat'] = 'metro'   # Warszawa: the metro (M1, M2) apart from the trains (S)
            if area == 'prg': r['f'] = bool(r.get('avg')) and r['avg'] <= 15   # Prague: colour only the lines running every 15 minutes or more often (7–18 h)
        for r in ROUTES_OUT[n0:]:
            if r['n'] in AREA_LINE_COLORS: r['f'] = True; r['k'], r['kt'] = AREA_LINE_COLORS[r['n']]
        print(A['op'] + ':', len(ROUTES_OUT) - n0, 'linii')
    except Exception as e:
        print(A['op'] + ': pominięty (%s)' % e)

used = {s[0] for f in os.listdir(OUT + '/r') for dd in json.load(open(OUT + '/r/' + f, encoding='utf-8'))['dirs'] for s in dd['stops']}
fi = next(rd(SCR + '/gtfs/x/feed_info.txt'), {})
end = fi.get('feed_end_date') or ''
fmt = lambda d: f'{d[6:8]}.{d[4:6]}.{d[:4]}' if len(d) == 8 else ''
json.dump({'valid': TODAY.strftime('%d.%m.%Y'), 'until': fmt(end), 'generated': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'), 'days': DAYS, 'weeks': WEEKS, 'opEnd': OPEND,
           'stops': {k: v for k, v in STOPS.items() if k in used}, 'routes': ROUTES_OUT},
          open(OUT + '/index.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('Gotowe:', len(ROUTES_OUT), 'linii zapisanych w', OUT)

# ---------------- second pass: ZTM-style variant notes ----------------
# "Kurs do: Y", "przez: Z" where Z is the busiest variant-only stop (the origin is not described)
# wording fixed by hand where a stop name needs a declined form: (lines, last stop, stop on the way, note)
NOTE_OVERRIDES = [({'2', '8'}, 'Strzyża PKM', 'Oliwa', 'Kurs do: Strzyża PKM przez: Oliwę')]
if os.path.exists(MANUAL):   # notes written by hand for trips of the Krynica-Zdrój / Muszyna lines
    for ln, last, text in json.load(open(MANUAL, encoding='utf-8')).get('notes', []): NOTE_OVERRIDES.append(({ln}, last, last, text))
files = [OUT + '/r/' + f for f in os.listdir(OUT + '/r')]

# street geometry of each main route (GTFS shapes), simplified to a few metres
def simplify(pts, eps=0.00006):
    if len(pts) < 3: return pts
    # distance to the segment a-b (not to the whole line), so loops that end where they start are not flattened
    a, b = pts[0], pts[-1]; dx, dy = b[0] - a[0], b[1] - a[1]; l2 = dx * dx + dy * dy
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i][0] - a[0], pts[i][1] - a[1]
        t = max(0.0, min(1.0, (px * dx + py * dy) / l2)) if l2 else 0.0
        d = ((px - t * dx) ** 2 + (py - t * dy) ** 2) ** .5
        if d > dmax: dmax, idx = d, i
    if dmax <= eps: return [a, b]
    return simplify(pts[:idx + 1], eps)[:-1] + simplify(pts[idx:], eps)
sys.setrecursionlimit(100000)
need = set(); SH_T = {}   # shape -> kinds of vehicle using it
for f in files:
    _j = json.load(open(f, encoding='utf-8'))
    for dd in _j['dirs']:
        for x in [dd.get('_shape')] + list(dd.get('_vshapes', [])):
            if x: need.add(x.split('|')[0]); SH_T.setdefault(x.split('|')[0], set()).add(_j.get('t'))
SHAPES = collections.defaultdict(list); VSH = {}
for pre, path in (('g', SCR + '/gtfs/x/shapes.txt'), ('y', SCR + '/gdy/shapes.txt'), ('r', SCR + '/tr/shapes.txt'),
                  ('Ps', SCR + '/poz/shapes.txt'), ('KAs', SCR + '/krkA/shapes.txt'), ('KTs', SCR + '/krkT/shapes.txt'), ('Ws', SCR + '/waw/shapes.txt'), ('Js', SCR + '/wej/shapes.txt'), ('Ls', SCR + '/ldz/shapes.txt'), ('Fs', SCR + '/fl/shapes.txt'), ('Gs', SCR + '/prg/shapes.txt')):
    if not os.path.exists(path): continue
    for r in rd(path):
        k = pre + r['shape_id']
        if k in need: SHAPES[k].append((int(r['shape_pt_sequence']), float(r['shape_pt_lat']), float(r['shape_pt_lon'])))
for k, v in SHAPES.items():
    v.sort(); SHAPES[k] = [[round(x[0], 5), round(x[1], 5)] for x in simplify([(x[1], x[2]) for x in v])]
# the courses laid exactly onto the OpenStreetMap streets and tram tracks (dopasuj.py); trains keep their own shapes
MATCH_AREA = {'g': 'Trójmiasto', 'y': 'Trójmiasto', 'Ps': 'Poznań', 'KAs': 'Kraków', 'KTs': 'Kraków', 'Ws': 'Warszawa', 'Js': 'Wejherowo',
              'Ls': 'Łódź', 'Fs': 'Flensburg', 'Gs': 'Praga'}
if '--no-match' not in sys.argv:
    try:
        import dopasuj
        _pre = lambda k: next((p for p in sorted(MATCH_AREA, key=len, reverse=True) if k.startswith(p)), None)
        _keys = [k for k in SHAPES if _pre(k) and not (SH_T.get(k, set()) & {'rail'})]
        dopasuj.match_all(SHAPES, _keys, lambda k: MATCH_AREA[_pre(k)], os.path.join(HERE, 'reczne', 'dopasowanie_cache.json'))
    except Exception as e: print('Dopasowanie do dróg pominięte:', e)
SHAPES.update(KM_SHAPES)
print('Kształty tras:', len(SHAPES))
def cut_shape(pts, stops, back):
    """the part of a round-trip shape that one half of the trip uses: stops are matched one after another along
    the shape (from its start, or from its end for the second half), so places passed twice are told apart"""
    if back: pts = pts[::-1]; stops = stops[::-1]
    import math as _m
    c = _m.cos(_m.radians(54.5))
    def seg_d(p, a, b):
        ax, ay, bx, by, px, py = a[1] * c, a[0], b[1] * c, b[0], p[1] * c, p[0]
        dx, dy = bx - ax, by - ay; l = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l)) if l else 0.0
        return _m.hypot(px - ax - t * dx, py - ay - t * dy) * 111000, [round(a[0] + t * (b[0] - a[0]), 5), round(a[1] + t * (b[1] - a[1]), 5)]
    pos, proj = 0, None
    for sp in stops:
        ds = [seg_d(sp, pts[j], pts[j + 1]) for j in range(pos, len(pts) - 1)]
        if not ds: break
        k = next((i for i, x in enumerate(ds) if x[0] < 80), None)
        if k is None: k = min(range(len(ds)), key=lambda i: ds[i][0])
        else:
            while k + 1 < len(ds) and ds[k + 1][0] <= ds[k][0]: k += 1
        pos, proj = pos + k, ds[k][1]
    out = pts[:pos + 1] + ([proj] if proj else [])
    return out[::-1] if back else out
def shape_for(x, dd, pat):
    if not x: return None
    base, _, half = x.partition('|'); pts = SHAPES.get(base)
    if not pts or not half: return pts
    stops = [STOPS[dd['stops'][i][0]][2:4] for i in pat]
    if half == 'c':   # a train that runs on beyond the line: from its first stop to its last
        return cut_shape(cut_shape(pts, stops, False), stops, True)
    return cut_shape(pts, stops, half == '1')
hub = collections.Counter()
data_all = {f: json.load(open(f, encoding='utf-8')) for f in files}
for d in data_all.values():
    names = set()
    for dd in d['dirs']: names |= {STOPS[dd['stops'][i][0]][0] for i in dd['pats'][0]}
    for n in names: hub[n] += 1
for f, d in data_all.items():
    for dd in d['dirs']:
        nm = lambda i: STOPS[dd['stops'][i][0]][0]
        main = [nm(i) for i in dd['pats'][0]]; mset = set(main)
        pnames = [[nm(i) for i in pat] for pat in dd['pats']]
        inpat = collections.Counter(n for p in pnames[1:] for n in set(p))
        drafts = []
        for pat, p in zip(dd['pats'][1:], pnames[1:]):
            # where the trip started is not described: look only at the part from the first stop on the main route
            first = next((k for k, n in enumerate(p) if n in mset), len(p))
            tail = p[first:]
            extra = [n for n in tail[:-1] if n not in mset and n != p[-1]]
            parts = []
            if p[-1] != main[-1]: parts.append('Kurs do: ' + p[-1])
            via = min(extra, key=lambda n: (inpat[n], -hub[n])) if extra else None
            fixed = next((t for lines, last, through, t in NOTE_OVERRIDES
                          if d['n'] in lines and p[-1] == last and through in tail), None)
            # stops off the main route before the trip joins it (e.g. a run from the depot along other streets)
            pre = [n for n in p[1:min(first, len(p) - 1)] if n not in mset]
            drafts.append([[fixed] if fixed else parts, None if fixed else via, tail, first, p, pre])
        def render(dr, with_via):
            parts, via, tail = dr[:3]
            parts = list(parts)
            if via and (with_via or not parts): parts.append(('przez: ' if parts else 'Kurs przez: ') + via)
            if not parts and tail:
                ts = set(tail)
                i0 = main.index(tail[0]) if tail[0] in main else 0
                lastm = max((main.index(n) for n in tail if n in mset), default=i0)
                skipped = [n for n in main[i0:lastm + 1] if n not in ts]
                if skipped: return 'Nie kursuje przez: ' + ', '.join(dict.fromkeys(skipped))
            if not parts and dr[5]:
                return 'Kurs przez: ' + min(dr[5], key=lambda n: (inpat[n], -hub[n]))
            return ' '.join(parts)
        def skip_limit(dr):
            # a "Nie kursuje przez" note matters only before the skipped stops: the position in the pattern
            # of the first stop past the last skipped one; from there on the note is not shown
            tail, first, p = dr[2], dr[3], dr[4]
            ts = set(tail)
            i0 = main.index(tail[0]) if tail[0] in main else 0
            lastm = max((main.index(n) for n in tail if n in mset), default=i0)
            mk = max(k for k in range(i0, lastm + 1) if main[k] not in ts)
            return next((j for j in range(first, len(p)) if p[j] in mset and main.index(p[j]) > mk), len(p))
        texts = [render(dr, False) for dr in drafts]
        dup = collections.Counter(texts)
        texts = [render(dr, True) if dup[t] > 1 else t for dr, t in zip(drafts, texts)]
        # the main route has no note, unless one is written by hand for it (a line with a single trip)
        main_note = next((t for lines, last, through, t in NOTE_OVERRIDES if d['n'] in lines and main[-1] == last and through in main), '')
        notes = [main_note] + texts
        dd['notes'] = notes
        def limit(dr, t):
            if t.startswith('Nie kursuje przez: '): return skip_limit(dr)
            # a route before joining the main one: the note matters only until the trip reaches the main route
            if dr[5] and not dr[0] and not dr[1] and t.startswith('Kurs przez: '): return dr[3]
            return -1
        nl = [-1] + [limit(dr, t) for dr, t in zip(drafts, texts)]
        if any(x >= 0 for x in nl) and 'tends' not in dd: dd['nl'] = nl
        if 'tends' in dd:   # rail: describe each train by its real origin and destination
            texts = []
            for o, e in dd.pop('tends'):
                parts = []
                if e != main[-1]: parts.append('Kurs do: ' + e)
                texts.append(', '.join(parts[:1] + [q[:1].lower() + q[1:] for q in parts[1:]]))
            dd['notes'] = [''] * len(notes)
            dd['tnotes'] = texts
    # one letter per note for the whole line, used by every timetable of the line and by the network map
    lt = []
    for dd in d['dirs']:
        for t in dd['notes'] + dd.get('tnotes', []):
            if t and t not in lt: lt.append(t)
    d['lt'] = lt
    for di, dd in enumerate(d['dirs']):
        sh = shape_for(dd.pop('_shape', None), dd, dd['pats'][0])
        if sh: dd['shape'] = sh
        VSH[(d['id'], di)] = [shape_for(x, dd, pat) for x, pat in zip(dd.pop('_vshapes', []), dd['pats'][1:])]   # for the network map only
    json.dump(d, open(f, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

# ---------------- network map: drawing geometry and stop positions, computed once here ----------------
import math
COS = math.cos(math.radians(54.45))
def PJ(lat, lon): return (lon * COS * 1000.0, -lat * 1000.0)   # 1 unit ≈ 65 m east-west, 111 m north-south
# where trains take a way the data's shape does not show: between two stations, along the tracks through the given points.
# S22: from Dzierżążno the trains run round the loop east of Kartuzy and enter the station from the north (then go on south
# to Somonino), instead of the shape's reversal at the junction south of the station
RAIL_VIA = {'kS22': [((54.3152, 18.26393), (54.33401, 18.20607), [(54.3394, 18.2226)])]}
_VIA_R = {}
def via_fix(rid, lines):
    if rid not in RAIL_VIA: return lines
    import drogi, dopasuj
    out = [list(c) for c in lines]
    for A, B, via in RAIL_VIA[rid]:
        key = (A, B)
        if key not in _VIA_R:
            pts = [A] + via + [B]; lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
            try:
                R = drogi.TileRouter((min(lats) - .01, max(lats) + .01, min(lons) - .015, max(lons) + .015), costs=dopasuj.RAIL, log=lambda m: None)
                path = []
                for a, b in zip(pts, pts[1:]):
                    pp, m = R.route(a, b)
                    if not pp: path = None; break
                    path += pp if not path else pp[1:]
                _VIA_R[key] = [PJ(*p) for p in path] if path else None
            except Exception as e: print('Przebieg przez punkty pominięty:', e); _VIA_R[key] = None
        P = _VIA_R[key]
        if not P: continue
        pa, pb = PJ(*A), PJ(*B)
        for c in out:
            near = lambda q: min(range(len(c)), key=lambda i: (c[i][0] - q[0]) ** 2 + (c[i][1] - q[1]) ** 2)
            ia, ib = near(pa), near(pb)
            if (c[ia][0] - pa[0]) ** 2 + (c[ia][1] - pa[1]) ** 2 > 9 or (c[ib][0] - pb[0]) ** 2 + (c[ib][1] - pb[1]) ** 2 > 9: continue
            seg = P if ia < ib else P[::-1]
            lo, hi = min(ia, ib), max(ia, ib)
            c[lo:hi + 1] = [tuple(x) for x in seg]
    return out
class SegGrid:
    def __init__(self, polys, cell=1.0):
        self.c = cell; self.g = collections.defaultdict(list); self.all = []
        for poly in polys:
            for i in range(1, len(poly)):
                a, b = poly[i - 1], poly[i]; self.all.append((a, b))
                for cx in range(int(math.floor(min(a[0], b[0]) / cell)), int(math.floor(max(a[0], b[0]) / cell)) + 1):
                    for cy in range(int(math.floor(min(a[1], b[1]) / cell)), int(math.floor(max(a[1], b[1]) / cell)) + 1):
                        self.g[(cx, cy)].append((a, b))
    @staticmethod
    def _proj(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]; l = dx * dx + dy * dy
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l if l else 0
        t = max(0.0, min(1.0, t)); x, y = a[0] + t * dx, a[1] + t * dy
        return math.hypot(p[0] - x, p[1] - y), (x, y), (dx, dy)
    def nearest(self, p, r=1, fallback=False):
        cx, cy = int(math.floor(p[0] / self.c)), int(math.floor(p[1] / self.c))
        best = (1e9, None, None)
        for i in range(-r, r + 1):
            for j in range(-r, r + 1):
                for a, b in self.g.get((cx + i, cy + j), ()):
                    q = self._proj(p, a, b)
                    if q[0] < best[0]: best = q
        if best[1] is None and fallback:
            for a, b in self.all:
                q = self._proj(p, a, b)
                if q[0] < best[0]: best = q
        return best
def rdp(pts, eps=0.05):
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True; stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop(); a, b = pts[i0], pts[i1]; dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy) or 1e-12
        dmax, idx = 0, None
        for i in range(i0 + 1, i1):
            d = abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / n
            if d > dmax: dmax, idx = d, i
        if idx is not None and dmax > eps: keep[idx] = True; stack += [(i0, idx), (idx, i1)]
    return [p for p, k in zip(pts, keep) if k]
def densify(c, step=0.09):
    out = [c[0]]
    for i in range(1, len(c)):
        p, q = c[i - 1], c[i]; n = max(1, int(math.ceil(math.hypot(q[0] - p[0], q[1] - p[1]) / step)))
        out += [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(1, n + 1)]
    return out
def merged_lines(lines, TH=0.6):
    """first direction in full; the second only where it leaves the first (street loops, one-way streets)"""
    if len(lines) < 2 or len(lines[0]) < 2: return lines
    a = lines[0]; G = SegGrid([a]); b = densify(lines[1]); out = [a]; run = None
    for i, p in enumerate(b):
        d, np_, _ = G.nearest(p)
        if d >= TH:
            if run is None:
                prev = G.nearest(b[i - 1])[1] if i > 0 else None
                run = [prev or p]
            run.append(p)
        elif run is not None:
            run.append(np_)
            if len(run) > 3: out.append(rdp(run))
            run = None
    if run is not None and len(run) > 3: out.append(rdp(run))
    return out
def leaving_runs(base, line, TH=0.6):
    """parts of `line` that run away from every polyline in `base` (variant extensions, detours)"""
    if len(line) < 2: return []
    G = SegGrid(base); runs = []; run = None; b = densify(line)
    for i, p in enumerate(b):
        d, np_, _ = G.nearest(p)
        if d >= TH:
            if run is None:
                prev = G.nearest(b[i - 1])[1] if i > 0 else None
                run = [prev or p]
            run.append(p)
        elif run is not None:
            run.append(np_)
            if len(run) > 3: runs.append(rdp(run))
            run = None
    if run is not None and len(run) > 3: runs.append(rdp(run))
    return runs
def trim(path, a, b, tol=0.3):
    """cut a shape to the part between its first and last stop (shapes may include runs to/from the depot)"""
    if len(path) < 3: return path
    da = [math.hypot(p[0] - a[0], p[1] - a[1]) for p in path]; db = [math.hypot(p[0] - b[0], p[1] - b[1]) for p in path]
    ia = next((i for i, d in enumerate(da) if d < tol), min(range(len(path)), key=da.__getitem__))
    ib = next((i for i in range(len(path) - 1, -1, -1) if db[i] < tol), min(range(len(path)), key=db.__getitem__))
    return path[ia:ib + 1] if ib - ia >= 1 else path
MAPD = {}
for f in sorted(os.listdir(OUT + '/r')):
    d = json.load(open(OUT + '/r/' + f, encoding='utf-8'))
    dirs_xy, dirs_st, ve, vstops, var_lines = [], [], set(), set(), []
    vr = {}   # route variants for the map's variant picker: (direction, stop names) -> entry
    for di, dd in enumerate(d['dirs']):
        cnt = collections.Counter()
        for pl in dd.get('plans', []):
            c = collections.Counter(dd['prof'][t[1]][0] for t in pl)
            for k_, v_ in c.items(): cnt[k_] = max(cnt[k_], v_)
        vsh_all = [dd.get('shape')] + VSH.get((d['id'], di), [])
        for k, pat in enumerate(dd['pats']):
            sids = [dd['stops'][i][0] for i in pat]; nm = tuple(STOPS[x][0] for x in sids)
            e = vr.get((di, nm))
            if e is None:
                shp = vsh_all[k] if k < len(vsh_all) else None
                pa, pb = PJ(STOPS[sids[0]][2], STOPS[sids[0]][3]), PJ(STOPS[sids[-1]][2], STOPS[sids[-1]][3])
                path = trim([PJ(q[0], q[1]) for q in shp], pa, pb) if shp else [PJ(STOPS[x][2], STOPS[x][3]) for x in sids if x in STOPS]
                mnames = {STOPS[dd['stops'][i][0]][0] for i in dd['pats'][0]}
                via = next((n for n in nm[1:-1] if n not in mnames), '')
                # the note (and so the letter) of this variant: its own note, or for trains the most common one of its trips
                note = dd['notes'][k] if k < len(dd['notes']) else ''
                if not note and dd.get('tnotes'):
                    tc = collections.Counter(dd['tnotes'][t[3]] for pl in dd.get('plans', []) for t in pl if len(t) > 3 and dd['prof'][t[1]][0] == k)
                    note = tc.most_common(1)[0][0] if tc else ''
                e = vr[(di, nm)] = {'d': di, 'm': 1 if k == 0 else 0, 's': sids, 'g': rdp(path, 0.15), 'n': 0, 'v': via,
                                    'l': d.get('lt', []).index(note) if note and note in d.get('lt', []) else -1}
            e['n'] += cnt.get(k, 0)
        main = [dd['stops'][i][0] for i in dd['pats'][0]]
        dirs_st.append(main)
        if dd.get('shape'): dirs_xy.append(trim([PJ(q[0], q[1]) for q in dd['shape']], PJ(STOPS[main[0]][2], STOPS[main[0]][3]), PJ(STOPS[main[-1]][2], STOPS[main[-1]][3])))
        else: dirs_xy.append([PJ(STOPS[s][2], STOPS[s][3]) for s in main if s in STOPS])
        names = [STOPS[s][0] for s in main]; nset = set(names); ends = {names[0], names[-1]} if names else set()
        vsh = VSH.get((d['id'], di), [])
        for k, pat in enumerate(dd['pats'][1:]):
            sids = [dd['stops'][i][0] for i in pat]
            # a variant's end is a terminus; its start only when off the main route (trips that merely begin
            # part-way along the route, e.g. after leaving the depot, are not short-turn variants)
            if STOPS[sids[-1]][0] not in ends: ve.add(sids[-1])
            if STOPS[sids[0]][0] not in ends and STOPS[sids[0]][0] not in nset: ve.add(sids[0])
            vstops |= {sid for sid in sids if STOPS[sid][0] not in nset}
            shp = vsh[k] if k < len(vsh) else None
            var_lines.append(trim([PJ(q[0], q[1]) for q in shp], PJ(STOPS[sids[0]][2], STOPS[sids[0]][3]), PJ(STOPS[sids[-1]][2], STOPS[sids[-1]][3])) if shp else [PJ(STOPS[s][2], STOPS[s][3]) for s in sids if s in STOPS])
    geo = via_fix(d['id'], merged_lines(dirs_xy))
    var_lines = via_fix(d['id'], var_lines)
    # variant routes (short turns, extensions, depot runs): only the parts that leave the main route
    vgeo = []
    for vl in sorted(var_lines, key=len, reverse=True):
        vgeo += leaving_runs(geo + vgeo, vl)
    G = SegGrid(geo); GV = SegGrid(geo + vgeo)
    sn = {}
    for main in dirs_st:
        for s in main:
            if s in sn or s not in STOPS: continue
            dist, pt, seg = G.nearest(PJ(STOPS[s][2], STOPS[s][3]), r=2, fallback=True)
            if pt: sn[s] = [round(pt[0], 2), round(pt[1], 2), round(seg[0], 2), round(seg[1], 2)]
    for s in sorted(vstops | ve):
        if s in sn or s not in STOPS: continue
        dist, pt, seg = GV.nearest(PJ(STOPS[s][2], STOPS[s][3]), r=2, fallback=True)
        if pt: sn[s] = [round(pt[0], 2), round(pt[1], 2), round(seg[0], 2), round(seg[1], 2)]
    def enc(c):   # polyline as delta-encoded integers in units of 0.01 (about 1 m): [x0, y0, dx1, dy1, ...]
        out = []; px = py = 0
        for x, y in c:
            ix, iy = int(round(x * 100)), int(round(y * 100)); out += [ix - px, iy - py]; px, py = ix, iy
        return out
    rnd = lambda gs: [enc(c) for c in gs if len(c) > 1]
    vlist = []; lt = list(d.get('lt', []))
    for (di, nm), e in vr.items():
        if not e['m'] and e['n'] == 0: continue
        if not e['m'] and e['l'] < 0:
            # a variant that leaves the main route only where it starts (no timetable note, as origins are not
            # described there): it still gets its own letter on the map, after the letters used in timetables
            mn = {STOPS[x][0] for x in dirs_st[di]}
            off = [n for n in nm if n not in mn]
            if off:
                t = ('Kurs od: ' + nm[0]) if nm[0] not in mn else ('Kurs przez: ' + off[0])
                if t not in lt: lt.append(t)
                e['l'] = lt.index(t)
        if len(e['g']) > 1: e['g'] = via_fix(d['id'], [e['g']])[0]
        vlist.append({'d': di, 'm': e['m'], 's': e['s'], 'n': e['n'], 'v': e['v'], 'l': e['l'], 'g': rnd([e['g']])[0] if len(e['g']) > 1 else []})
    vlist.sort(key=lambda e: (e['d'], -e['m'], -e['n']))
    MAPD[d['id']] = {'lt': lt, 'g': rnd(geo), 'v': rnd(vgeo), 'd': dirs_st, 've': sorted(ve), 'vs': sorted(vstops - ve), 'sn': sn, 'vr': vlist}
_new_of = {rid: a for a, ids in NEW_ROUTE_IDS.items() for rid in ids}
json.dump({'routes': {k: v for k, v in MAPD.items() if k not in _new_of}}, open(OUT + '/map.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
for a in NEW_AREAS:   # the network map of each big city in a file of its own
    json.dump({'routes': {k: v for k, v in MAPD.items() if _new_of.get(k) == a}}, open(OUT + '/map_%s.json' % a, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('Schemat sieci:', len(MAPD), 'linii,', os.path.getsize(OUT + '/map.json') // 1024, 'KB')

# ---------------- background map from OpenStreetMap (refreshed once a month, or with --podklad) ----------------
# one file per area: the Tricity (base.json), Krynica-Zdrój with Muszyna (base_km.json), Bydgoszcz (base_byd.json) and Nowy Sącz
# (base_ns.json), each loaded only when shown
BASE = OUT + '/base.json'
_st = list(json.load(open(OUT + '/index.json', encoding='utf-8'))['stops'].values())
for path, sel, core in ((BASE, lambda v: v[4] not in ('km', 'kmx', 'byd', 'ns', 'poz', 'krk', 'waw', 'wej', 'ldz', 'fl', 'prg'), (54.30, 54.62, 18.35, 18.85)),
                        # the big cities: their centres in detail, the suburbs coarser (a whole city in detail would be too big a file)
                        (OUT + '/base_poz.json', lambda v: v[4] == 'poz', (52.37, 52.45, 16.85, 16.99)),
                        (OUT + '/base_krk.json', lambda v: v[4] == 'krk', (50.025, 50.095, 19.88, 20.03)),
                        (OUT + '/base_waw.json', lambda v: v[4] == 'waw', (52.19, 52.27, 20.95, 21.07)), (OUT + '/base_km.json', lambda v: v[4] in ('km', 'kmx'), (49.33, 49.47, 20.75, 21.06)),
                        (OUT + '/base_byd.json', lambda v: v[4] == 'byd', (53.07, 53.18, 17.86, 18.20)),
                        (OUT + '/base_wej.json', lambda v: v[4] == 'wej', (54.58, 54.64, 18.18, 18.30)),
                        (OUT + '/base_ldz.json', lambda v: v[4] == 'ldz', (51.72, 51.81, 19.40, 19.53)),
                        (OUT + '/base_fl.json', lambda v: v[4] == 'fl', (54.76, 54.81, 9.39, 9.48)),
                        (OUT + '/base_prg.json', lambda v: v[4] == 'prg', (50.05, 50.11, 14.38, 14.48)),
                        (OUT + '/base_ns.json', lambda v: v[4] == 'ns', (49.57, 49.67, 20.62, 20.76))):   # Nowy Sącz: the city in detail
    if not ('--podklad' in sys.argv or not os.path.exists(path) or (datetime.datetime.now().timestamp() - os.path.getmtime(path)) > 30 * 86400): continue
    pts = [v for v in _st if sel(v)]
    if not pts: continue
    try:
        import basemap
        lat = sorted(v[2] for v in pts); lon = sorted(v[3] for v in pts)
        box = (lat[0] - .03, lat[-1] + .03, lon[0] - .05, lon[-1] + .05)
        basemap.build(path, box, core or box)   # Krynica-Zdrój and Muszyna: the whole area in detail
    except Exception as e:
        print('Podkład mapy: nie udało się pobrać (%s), zostaje poprzedni' % e)

# walking network for the journey planner (walknet.py): refreshed with the background, or when missing
try:
    import walknet
    _wa = [a for a in walknet.AREAS if '--podklad' in sys.argv or not os.path.exists(OUT + '/walk/' + a + '.json') or (datetime.datetime.now().timestamp() - os.path.getmtime(OUT + '/walk/' + a + '.json')) > 30 * 86400]
    if _wa: walknet.build_all(OUT, _wa)
except Exception as e:
    print('Sieć piesza: nie udało się (%s), zostaje poprzednia' % e)

# ---------------- schematic diagram (needs the LOOM tools, see schematic.py) ----------------
# only the areas whose routes changed are drawn again (a full diagram takes long); the routes each diagram was drawn from
# are remembered as a fingerprint in data/schema_sig.json
try:
    import schematic, hashlib
    _ix = json.load(open(OUT + '/index.json', encoding='utf-8'))
    _sig_path = OUT + '/schema_sig.json'
    _old = json.load(open(_sig_path, encoding='utf-8')) if os.path.exists(_sig_path) else {}
    _new = {}
    for _a, _pred, _ in schematic.AREAS:
        h = hashlib.sha1()
        for r in sorted((r for r in _ix['routes'] if _pred(r)), key=lambda r: r['id']):
            fp = OUT + '/r/' + r['id'] + '.json'
            if not os.path.exists(fp): continue
            d = json.load(open(fp, encoding='utf-8'))
            # the streets a line takes (pairs of consecutive stops), not its trips: a new timetable alone draws nothing again
            edges = sorted({(_ix['stops'][dd['stops'][a][0]][0], _ix['stops'][dd['stops'][b][0]][0]) for dd in d['dirs'] for p in dd['pats'] for a, b in zip(p, p[1:])})
            h.update(json.dumps([r['id'], r['n'], r['t'], bool(r.get('f')), bool(r.get('nt')), edges], ensure_ascii=False).encode())
        _new[_a] = h.hexdigest()
    _todo = [a for a in _new if _old.get(a) != _new[a] or not os.path.exists(OUT + '/schema_' + a + '.json')]
    if '--schematy' in sys.argv: _todo = list(_new)   # force all
    if not _todo: print('Schemat oktylinearny: trasy bez zmian, zostają poprzednie schematy')
    else:
        print('Schemat oktylinearny: do przeliczenia', ', '.join(_todo))
        _done = schematic.build_all(OUT, log=print, areas=_todo) or []
        _old.update({a: _new[a] for a in _done}); json.dump(_old, open(_sig_path, 'w'))
except Exception as e:
    print('Schemat oktylinearny: pominięty (%s)' % e)

# ---------------- the route files of the big cities: several routes to a file (data/rp/<area>_<n>.json) ----------------
PACK = 30
shutil.rmtree(OUT + '/rp', ignore_errors=True); os.makedirs(OUT + '/rp', exist_ok=True)
_idx = json.load(open(OUT + '/index.json', encoding='utf-8'))
_pk = {}
for a, ids in NEW_ROUTE_IDS.items():
    ids = sorted(ids)
    for n in range(0, len(ids), PACK):
        name = '%s_%d' % (a, n // PACK); pack = {}
        for rid in ids[n:n + PACK]:
            f = OUT + '/r/' + rid + '.json'
            if not os.path.exists(f): continue
            pack[rid] = json.load(open(f, encoding='utf-8')); os.remove(f); _pk[rid] = name
        json.dump(pack, open(OUT + '/rp/' + name + '.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
# the other areas too (Tricity, Bydgoszcz, Krynica, Nowy Sącz): fewer files to publish (the site holds at most ~500)
_left = collections.defaultdict(list)
for r in _idx['routes']:
    if r['id'] not in _pk and os.path.exists(OUT + '/r/' + r['id'] + '.json'): _left[(r.get('c') or ['tri'])[0] if r.get('c') else 'tri'].append(r['id'])
for a, ids in _left.items():
    ids = sorted(ids)
    for n in range(0, len(ids), PACK):
        name = '%s_%d' % (a, n // PACK); pack = {}
        for rid in ids[n:n + PACK]:
            f = OUT + '/r/' + rid + '.json'
            pack[rid] = json.load(open(f, encoding='utf-8')); os.remove(f); _pk[rid] = name
        json.dump(pack, open(OUT + '/rp/' + name + '.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
for r in _idx['routes']:
    if r['id'] in _pk: r['rp'] = _pk[r['id']]
json.dump(_idx, open(OUT + '/index.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('Paczki tras:', len(os.listdir(OUT + '/rp')), 'plików')

# ---------------- optional: single-file page with the data built in ----------------
if EMBED:
    page = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
    payload = {'index': json.load(open(OUT + '/index.json', encoding='utf-8')),
               'map': json.load(open(OUT + '/map.json', encoding='utf-8')),
               'base': json.load(open(BASE, encoding='utf-8')) if os.path.exists(BASE) else None,
               'base_km': json.load(open(OUT + '/base_km.json', encoding='utf-8')) if os.path.exists(OUT + '/base_km.json') else None,
               'base_byd': json.load(open(OUT + '/base_byd.json', encoding='utf-8')) if os.path.exists(OUT + '/base_byd.json') else None,
               'base_ns': json.load(open(OUT + '/base_ns.json', encoding='utf-8')) if os.path.exists(OUT + '/base_ns.json') else None,
               **{'base_' + a: json.load(open(OUT + '/base_' + a + '.json', encoding='utf-8')) for a in ('poz', 'krk', 'waw', 'wej', 'ldz', 'fl', 'prg') if os.path.exists(OUT + '/base_' + a + '.json')},
               # Poznań, Kraków, Warszawa: network maps and packed route files
               'maps': {a: json.load(open(OUT + '/map_' + a + '.json', encoding='utf-8')) for a in ('poz', 'krk', 'waw', 'wej', 'ldz', 'fl', 'prg') if os.path.exists(OUT + '/map_' + a + '.json')},
               'rp': {f[:-5]: json.load(open(OUT + '/rp/' + f, encoding='utf-8')) for f in os.listdir(OUT + '/rp')} if os.path.isdir(OUT + '/rp') else {},
               'schema': {f[7:-5]: json.load(open(OUT + '/' + f, encoding='utf-8')) for f in sorted(os.listdir(OUT)) if f.startswith('schema_') and f.endswith('.json')} or None,
               'r': {f[:-5]: json.load(open(OUT + '/r/' + f, encoding='utf-8')) for f in os.listdir(OUT + '/r')},
               # brigade timetables (Rozkłady brygad)
               'bg': {f[:-5]: json.load(open(OUT + '/bg/' + f, encoding='utf-8')) for f in os.listdir(OUT + '/bg')} if os.path.isdir(OUT + '/bg') else {}}
    js = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = page.replace('<script>', '<script>window.EMBEDDED_DATA=' + js + ';</script>\n<script>', 1)
    dest = os.path.join(HERE, 'rozklady.html')
    open(dest, 'w', encoding='utf-8').write(page)
    print('Zapisano', dest, f'({os.path.getsize(dest) // 1024} KB)')

# rozkłady brygad (osobny skrypt: pobiera GTFS przewoźników podających numery brygad)
if '--bez-brygad' not in sys.argv:
    import subprocess
    subprocess.run([sys.executable, os.path.join(HERE, 'brygady.py'), OUT])

shutil.rmtree(SCR, ignore_errors=True)
