#!/usr/bin/env python3
"""Berlin and Hamburg: their city lines cut out of the regional GTFS files (build.py calls cut()).
Berlin: VBB (Verkehrsverbund Berlin-Brandenburg, www.vbb.de/vbbgtfs, CC BY 4.0) – BVG's buses, trams, U-Bahn and ferries
and S-Bahn Berlin's trains (its replacement buses too).
Hamburg: hvv (Hamburger Verkehrsverbund, Transparenzportal Hamburg, dl-de/by-2.0) – the lines of HOCHBAHN (U-Bahn, buses),
VHH, S-Bahn Hamburg and HADAG's ferries that stop in Hamburg itself (stop ids de:02000:…); the hvv file names no operators,
only its agency numbers, so those are listed here.
Only the files a timetable needs are written (the stop times and shapes of the lines kept)."""
import csv, io, json, os, re, sys, urllib.request, zipfile

CITIES = {
    'ber': {'agencies': {'1', '796'}, 'stop_prefix': None},
    'ham': {'agencies': {'61', '66', '73', '76', '361'}, 'stop_prefix': 'de:02000:'},
}
HVV_SEARCH = ('https://suche.transparenz.hamburg.de/api/3/action/package_search?q=hvv%20Rohdaten%20GTFS'
              '&sort=metadata_modified%20desc&rows=5')


def hvv_url():
    """the newest hvv GTFS file on the Transparenzportal (its address changes with each timetable)"""
    req = urllib.request.Request(HVV_SEARCH, headers={'User-Agent': 'rozklady-trojmiasto/1.0'})
    j = json.load(urllib.request.urlopen(req, timeout=60))
    for p in j['result']['results']:
        for r in p.get('resources', []):
            u = r.get('url') or ''
            if re.search(r'GTFS.*\.zip$', u, re.I): return u
    raise RuntimeError('hvv: brak pliku GTFS w Transparenzportal')


def cut(src_zip, out, area, log=print):
    C = CITIES[area]; os.makedirs(out, exist_ok=True)
    z = zipfile.ZipFile(src_zip)
    rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))

    def write(name, rows, fields=None):
        rows = list(rows)
        if not rows: return
        with open(os.path.join(out, name), 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields or list(rows[0].keys()), extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    routes = [r for r in rd('routes.txt') if r['agency_id'] in C['agencies']]
    rids = {r['route_id'] for r in routes}
    trips = [t for t in rd('trips.txt') if t['route_id'] in rids]
    tids = {t['trip_id'] for t in trips}
    # the stop times of those trips (read once: the file is big)
    st_path = os.path.join(out, 'stop_times.txt'); used = set(); trip_stops = {}
    with z.open('stop_times.txt') as fh:
        r_ = csv.reader(io.TextIOWrapper(fh, encoding='utf-8-sig')); hdr = next(r_); it = hdr.index('trip_id'); isd = hdr.index('stop_id')
        rows = [row for row in r_ if row[it] in tids]
    if C['stop_prefix']:   # Hamburg: only the lines with a stop in the city
        inside = set()
        for row in rows:
            if row[isd].startswith(C['stop_prefix']): inside.add(row[it])
        keep_r = {t['route_id'] for t in trips if t['trip_id'] in inside}
        routes = [r for r in routes if r['route_id'] in keep_r]; rids = keep_r
        trips = [t for t in trips if t['route_id'] in rids]; tids = {t['trip_id'] for t in trips}
        rows = [row for row in rows if row[it] in tids]
    with open(st_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(rows)
    used = {row[isd] for row in rows}; del rows
    stops = [s for s in rd('stops.txt') if s['stop_id'] in used]
    sids = {t['service_id'] for t in trips}; shp = {t.get('shape_id') for t in trips if t.get('shape_id')}
    agencies = [a for a in rd('agency.txt') if a['agency_id'] in C['agencies']]
    write('agency.txt', agencies); write('routes.txt', routes); write('trips.txt', trips); write('stops.txt', stops)
    for n in ('calendar.txt', 'calendar_dates.txt'):
        if n in z.namelist(): write(n, (r for r in rd(n) if r['service_id'] in sids))
    if 'feed_info.txt' in z.namelist(): write('feed_info.txt', rd('feed_info.txt'))
    if 'shapes.txt' in z.namelist():
        with z.open('shapes.txt') as fh, open(os.path.join(out, 'shapes.txt'), 'w', encoding='utf-8', newline='') as fo:
            r_ = csv.reader(io.TextIOWrapper(fh, encoding='utf-8-sig')); hdr = next(r_); i = hdr.index('shape_id')
            w = csv.writer(fo); w.writerow(hdr)
            for row in r_:
                if row[i] in shp: w.writerow(row)
    log('%s: %d linii, %d kursów, %d przystanków' % (area, len(routes), len(trips), len(stops)))


if __name__ == '__main__':
    cut(sys.argv[1], sys.argv[2], sys.argv[3])
