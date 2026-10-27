#!/usr/bin/env python3
"""Trip index for the live departures read by the page itself (GTFS-Realtime of Warszawa, Łódź, Poznań, Kraków, Praga).

The realtime feeds name each run only by its trip_id (and the stop sequence or stop id it has reached). The page knows
the timetables as lines, directions and runs by start time, so it needs, for every trip_id of today and tomorrow,
the line number, the start time (minutes after midnight) and the stop_sequence of the first stop. build.py calls build()
at the end; the result is data/rt/<area>.json: {"days": [...], "f": {feed: {trip_id: [line, start, first seq]}}}.
Warszawa's realtime feed (zbiorkom.live) refers to its own static GTFS, so that one is downloaded here.
"""
import collections, csv, datetime, io, json, os, shutil, urllib.request, zipfile

AREAS = {   # area -> [(feed key used by the page, static GTFS: folder in the build's scratch directory or a URL)]
    'waw': [('W', 'https://cdn.zbiorkom.live/gtfs/warsaw.zip')],
    'ldz': [('L', 'ldz')],
    'poz': [('P', 'poz')],
    'krk': [('KA', 'krkA'), ('KT', 'krkT')],
    'prg': [('G', 'prg')],
}


def rd(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def tmin(t):
    h, m, s = (int(x) for x in t.strip().split(':'))
    return h * 60 + m + s / 60


def active(folder, dates):
    """service_id -> True for services running on any of the dates (YYYYMMDD)"""
    on = collections.defaultdict(set)
    if os.path.exists(folder + '/calendar.txt'):
        for r in rd(folder + '/calendar.txt'):
            a = datetime.datetime.strptime(r['start_date'], '%Y%m%d').date(); b = datetime.datetime.strptime(r['end_date'], '%Y%m%d').date()
            for ds in dates:
                d = datetime.datetime.strptime(ds, '%Y%m%d').date()
                if a <= d <= b and r[('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')[d.weekday()]] == '1': on[r['service_id']].add(ds)
    if os.path.exists(folder + '/calendar_dates.txt'):
        for r in rd(folder + '/calendar_dates.txt'):
            if r['date'] not in dates: continue
            if r['exception_type'] == '1': on[r['service_id']].add(r['date'])
            else: on[r['service_id']].discard(r['date'])
    return {s for s, v in on.items() if v}


def build(scr, out, names_of_area=None, log=print):
    today = datetime.date.today()
    # yesterday too: its runs after midnight are still under way in the morning
    dates = [(today + datetime.timedelta(days=i)).strftime('%Y%m%d') for i in (-1, 0, 1)]
    os.makedirs(out + '/rt', exist_ok=True)
    for area, feeds in AREAS.items():
        res = {'days': dates, 'f': {}}
        names = (names_of_area or {}).get(area)
        for key, src in feeds:
            folder = src if os.path.isabs(src) else os.path.join(scr, src)
            try:
                if src.startswith('http'):
                    folder = os.path.join(scr, 'rt_' + key); z = folder + '.zip'
                    req = urllib.request.Request(src, headers={'User-Agent': 'ZbiorkomInfo/1.0'})
                    with urllib.request.urlopen(req, timeout=300) as r, open(z, 'wb') as f: shutil.copyfileobj(r, f)
                    with zipfile.ZipFile(z) as zf:
                        for n in ('routes.txt', 'trips.txt', 'stop_times.txt', 'calendar.txt', 'calendar_dates.txt'):
                            if n in zf.namelist(): zf.extract(n, folder)
                    os.remove(z)
                svc = active(folder, set(dates))
                short = {r['route_id']: r['route_short_name'] or r['route_id'] for r in rd(folder + '/routes.txt')}
                trips = {}
                for r in rd(folder + '/trips.txt'):
                    if r['service_id'] not in svc: continue
                    n = short.get(r['route_id'], '')
                    if names is not None and n not in names: continue
                    trips[r['trip_id']] = n
                first = {}
                for r in rd(folder + '/stop_times.txt'):
                    t = r['trip_id']
                    if t not in trips: continue
                    q = int(r['stop_sequence']); f = first.get(t)
                    if f is None or q < f[0]: first[t] = (q, r['departure_time'] or r['arrival_time'])
                res['f'][key] = {t: [trips[t], round(tmin(f[1])), f[0]] for t, f in first.items()}
                log('Indeks kursów na żywo %s/%s: %d kursów' % (area, key, len(res['f'][key])))
            except Exception as e:
                log('Indeks kursów na żywo %s/%s: pominięty (%s)' % (area, key, e))
        if res['f']:
            json.dump(res, open(out + '/rt/' + area + '.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
