#!/usr/bin/env python3
"""Flensburg (Aktiv Bus Flensburg) cut out of the Schleswig-Holstein timetable data (opendata.schleswig-holstein.de,
dataset "Fahrplandaten", GTFS, CC BY 4.0). Only the operator's routes, their trips, stop times, shapes, stops and calendars
are kept, written as a small GTFS folder.
Usage: python flensburg_gtfs.py <zip path or URL> <output folder>   (build.py calls build())"""
import csv, io, os, sys, urllib.request, zipfile, shutil

URL = 'https://opendata.schleswig-holstein.de/dataset/5e0652d8-7f59-42fc-92ab-a6358f800e1d/resource/d26a3f87-b8a9-4c02-ab2e-13ea4755ebc3/download/fahrplandaten'
AGENCY = 'Aktiv Bus Flensburg GmbH'


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


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else URL, sys.argv[2] if len(sys.argv) > 2 else 'fl')
