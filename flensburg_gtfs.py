#!/usr/bin/env python3
"""Flensburg (Aktiv Bus Flensburg) cut out of the Schleswig-Holstein timetable data (opendata.schleswig-holstein.de,
dataset "Fahrplandaten", GTFS, CC BY 4.0). Only the operator's routes, their trips, stop times, shapes, stops and calendars
are kept, written as a small GTFS folder.
Usage: python flensburg_gtfs.py <zip path or URL> <output folder>   (build.py calls build())"""
import csv, io, os, re, sys, urllib.request, zipfile, shutil

URL = 'https://opendata.schleswig-holstein.de/dataset/5e0652d8-7f59-42fc-92ab-a6358f800e1d/resource/d26a3f87-b8a9-4c02-ab2e-13ea4755ebc3/download/fahrplandaten'
AGENCY = 'Aktiv Bus Flensburg GmbH'
DATASET = '5e0652d8-7f59-42fc-92ab-a6358f800e1d'


def current_url():
    """the dataset's GTFS file as listed now (its resource id changes when the data is renewed)"""
    try:
        import json
        req = urllib.request.Request('https://opendata.schleswig-holstein.de/api/3/action/package_show?id=' + DATASET, headers={'User-Agent': 'Mozilla/5.0 (rozklady-trojmiasto)'})
        res = json.load(urllib.request.urlopen(req, timeout=60))['result']['resources']
        for r in res:
            if 'GTFS' in (r.get('format') or '').upper() or 'fahrplan' in (r.get('name') or '').lower(): return r['url']
    except Exception: pass
    return URL


def build(src, out, log=print):
    if src.startswith('http'):
        tmp = out.rstrip('/') + '.zip'
        req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0 (rozklady-trojmiasto)'})
        with urllib.request.urlopen(req, timeout=900) as r, open(tmp, 'wb') as f: shutil.copyfileobj(r, f)
        src = tmp
    z = zipfile.ZipFile(src)
    rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))
    os.makedirs(out, exist_ok=True)

    def write(name, rows, fields):
        with open(os.path.join(out, name), 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    ag = [a for a in rd('agency.txt') if a['agency_name'] == AGENCY]
    aids = {a['agency_id'] for a in ag}
    write('agency.txt', ag, list(ag[0].keys()))
    routes = [r for r in rd('routes.txt') if r['agency_id'] in aids]
    rids = {r['route_id'] for r in routes}
    write('routes.txt', routes, list(routes[0].keys()))
    trips = [t for t in rd('trips.txt') if t['route_id'] in rids]
    tids = {t['trip_id'] for t in trips}; sids = {t['service_id'] for t in trips}
    write('trips.txt', trips, list(trips[0].keys()))
    for n in ('calendar.txt', 'calendar_dates.txt'):
        if n in z.namelist():
            rows = [r for r in rd(n) if r['service_id'] in sids]
            if rows: write(n, rows, list(rows[0].keys()))
    # stop times: streamed (the file is too big to hold)
    used = set(); n = 0
    with z.open('stop_times.txt') as fh, open(os.path.join(out, 'stop_times.txt'), 'w', encoding='utf-8', newline='') as fo:
        rdr = csv.reader(io.TextIOWrapper(fh, encoding='utf-8-sig')); hdr = next(rdr); it = hdr.index('trip_id'); isd = hdr.index('stop_id')
        w = csv.writer(fo); w.writerow(hdr)
        for row in rdr:
            if row[it] in tids: w.writerow(row); used.add(row[isd]); n += 1
    shp = {t.get('shape_id') for t in trips if t.get('shape_id')}
    if shp and 'shapes.txt' in z.namelist():
        with z.open('shapes.txt') as fh, open(os.path.join(out, 'shapes.txt'), 'w', encoding='utf-8', newline='') as fo:
            rdr = csv.reader(io.TextIOWrapper(fh, encoding='utf-8-sig')); hdr = next(rdr); ish = hdr.index('shape_id')
            w = csv.writer(fo); w.writerow(hdr)
            for row in rdr:
                if row[ish] in shp: w.writerow(row)
    stops = [s for s in rd('stops.txt') if s['stop_id'] in used]
    write('stops.txt', stops, list(stops[0].keys()))
    log('Flensburg: %d linii, %d kursów, %d przystanków, %d odjazdów' % (len(routes), len(trips), len(stops), n))
    if src.endswith('.zip') and os.path.dirname(src) == os.path.dirname(out.rstrip('/')) and os.path.basename(src) == os.path.basename(out.rstrip('/')) + '.zip':
        os.remove(src)


# gtfs.de (DELFI data, CC BY 4.0): the same timetable with every stop's platforms ("Angelburger Str. B1 > Südermarkt",
# "Stuhrsallee > ZOB"), which the Schleswig-Holstein file merges into one point per stop; read from the zip on the server
# (HTTP ranges), so that only the small files and the stop times of Flensburg are taken from its 2 GB of stop times
DE_URL = 'https://download.gtfs.de/germany/nv_free/latest.zip'
DE_AGENCY = 'Aktiv Bus Flensburg'


def build_de(out, log=print, url=DE_URL):
    from remotezip import RemoteZip
    os.makedirs(out, exist_ok=True)
    with RemoteZip(url, headers={'User-Agent': 'Mozilla/5.0 (rozklady-trojmiasto)'}) as z:
        rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))

        def write(name, rows, fields):
            with open(os.path.join(out, name + '.tmp'), 'w', encoding='utf-8', newline='') as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
        ag = [a for a in rd('agency.txt') if a['agency_name'] == DE_AGENCY]
        aids = {a['agency_id'] for a in ag}
        routes = [r for r in rd('routes.txt') if r['agency_id'] in aids]
        rids = {r['route_id'] for r in routes}
        trips = [t for t in rd('trips.txt') if t['route_id'] in rids]
        tids = {t['trip_id'] for t in trips}; sids = {t['service_id'] for t in trips}
        if not trips: raise RuntimeError('gtfs.de: brak kursów ' + DE_AGENCY)
        cal = {n: [r for r in rd(n) if r['service_id'] in sids] for n in ('calendar.txt', 'calendar_dates.txt')}
        used = set(); n = 0
        with z.open('stop_times.txt') as fh, open(os.path.join(out, 'stop_times.txt.tmp'), 'w', encoding='utf-8', newline='') as fo:
            rdr = csv.reader(io.TextIOWrapper(fh, encoding='utf-8-sig')); hdr = next(rdr); it = hdr.index('trip_id'); isd = hdr.index('stop_id')
            w = csv.writer(fo); w.writerow(hdr)
            for row in rdr:
                if row[it] in tids: w.writerow(row); used.add(row[isd]); n += 1
        allst = list(rd('stops.txt'))
        stops = [s for s in allst if s['stop_id'] in used]
        par = {s['parent_station'] for s in stops if s.get('parent_station')}
        pname = {s['stop_id']: s['stop_name'] for s in allst if s['stop_id'] in par}
        for s in stops:   # the stop's own name from its parent ("Flensburg Stuhrsallee"), the platform's ("B1", the way) after it
            pn = pname.get(s.get('parent_station'))
            if pn and not s['stop_name'].startswith(pn):
                m = re.search(r'\bB(\d)\b', s['stop_name'])
                s['stop_name'] = pn + (' B' + m.group(1) if m else '')
    write('agency.txt', ag, list(ag[0].keys())); write('routes.txt', routes, list(routes[0].keys()))
    write('trips.txt', trips, list(trips[0].keys()))
    for k, rows in cal.items():
        if rows: write(k, rows, list(rows[0].keys()))
    write('stops.txt', stops, list(stops[0].keys()))
    # the new files take the old ones' place only now, when all of them are there; no shapes here: build.py draws the
    # routes along the streets of the map itself
    new = {f[:-4] for f in os.listdir(out) if f.endswith('.tmp')}
    for f in os.listdir(out):
        if f.endswith('.txt') and f not in new: os.remove(os.path.join(out, f))
    for f in new: os.replace(os.path.join(out, f + '.tmp'), os.path.join(out, f))
    log('Flensburg (gtfs.de): %d linii, %d kursów, %d przystanków (perony), %d odjazdów' % (len(routes), len(trips), len(stops), n))



def platforms_de(out, log=print, url=DE_URL):
    """The timetable stays the Schleswig-Holstein one; only the platforms of its stops (B1, B2…) are taken from gtfs.de: each
    platform of the cut-out folder gets the number of the gtfs.de platform at the same place (within 15 m), written into its
    name before the way ("Angelburger Str. B1 > Südermarkt"), where build.py reads it (fl_name)."""
    import math
    from remotezip import RemoteZip
    with RemoteZip(url, headers={'User-Agent': 'Mozilla/5.0 (rozklady-trojmiasto)'}) as z:
        de = []
        for s in csv.DictReader(io.TextIOWrapper(z.open('stops.txt'), encoding='utf-8-sig')):
            try: la, lo = float(s['stop_lat']), float(s['stop_lon'])
            except ValueError: continue
            if not (54.70 < la < 54.88 and 9.25 < lo < 9.60): continue
            m = re.search(r'\bB(\d)\b', s['stop_name']) or re.fullmatch(r'B?(\d)', (s.get('platform_code') or '').strip())
            if m: de.append((la, lo, m.group(1)))
    if not de: raise RuntimeError('gtfs.de: brak peronów we Flensburgu')
    grid = {}
    for p in de: grid.setdefault((round(p[0] * 500), round(p[1] * 300)), []).append(p)
    dist = lambda a, b, c, d: math.hypot((a - c) * 111000, (b - d) * 111000 * math.cos(math.radians(a)))
    path = os.path.join(out, 'stops.txt')
    with open(path, encoding='utf-8-sig', newline='') as f:
        rdr = csv.DictReader(f); fields = rdr.fieldnames; rows = list(rdr)
    n = 0
    for r in rows:
        if re.search(r'\sB\d\b', r['stop_name']) or (r.get('location_type') or '0') not in ('', '0'): continue   # (stations: no platform of their own)
        try: la, lo = float(r['stop_lat']), float(r['stop_lon'])
        except ValueError: continue
        k = (round(la * 500), round(lo * 300)); best = None; bd = 15
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for p in grid.get((k[0] + i, k[1] + j), ()):
                    d = dist(la, lo, p[0], p[1])
                    if d < bd: bd, best = d, p
        if best:
            m = re.search(r'(\s*-?>.*|\s+Richtung\s.*)$', r['stop_name'])
            cut = m.start() if m else len(r['stop_name'])
            r['stop_name'] = r['stop_name'][:cut] + ' B' + best[2] + r['stop_name'][cut:]; n += 1
    with open(path + '.tmp', 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    os.replace(path + '.tmp', path)
    log('Flensburg: perony z gtfs.de dla %d z %d przystanków' % (n, len(rows)))


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else URL, sys.argv[2] if len(sys.argv) > 2 else 'fl')
