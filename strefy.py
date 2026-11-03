#!/usr/bin/env python3
"""The fare zones of the stops, for the guide's "Uwaga! Zmiana strefy taryfowej" (data/strefy.json):
- "b": stops on a zone border, where the operator marks them: ZTM Gdańsk (ticketZoneBorder in its stop list), Warszawa
  (zone "1+2" in the GTFS);
- "z": the zone of each stop where the GTFS gives one per stop (Poznań A–D, Kraków 1–3, Łódź 1–3): the guide announces the
  change at the first stop of the run in another zone.
The GTFS stops are matched to the page's stops by name and place (the nearest of the same name within 80 m).
Usage: python3 strefy.py [data folder]   (build.py calls build())"""
import csv, io, json, math, os, sys, urllib.request, zipfile, tempfile

ZTM_STOPS = 'https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json'
GTFS = {'waw': 'https://mkuran.pl/gtfs/warsaw.zip', 'poz': 'https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile',
        'krk': ['https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip', 'https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip'],
        'ldz': 'https://otwarte.miasto.lodz.pl/wp-content/uploads/2025/06/GTFS.zip'}
UA = {'User-Agent': 'Mozilla/5.0 (rozklady-trojmiasto)'}


def get(url, path=None):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600)
    if path is None: return r.read()
    with open(path, 'wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b)


def dist(a, b, c, d):
    return math.hypot((d - b) * math.cos(math.radians(a)) * 111320, (c - a) * 110540)


def build(out, log=print, cache=None):
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    by = {}
    for sid, s in idx['stops'].items(): by.setdefault((s[4], s[0]), []).append((sid, s[2], s[3]))
    res = {'b': [], 'z': {}}
    # ZTM Gdańsk: its own border flag, stop ids as on the page
    try:
        j = json.loads(get(ZTM_STOPS))   # (a list for each day ahead; the last days may come without the flags: all days together)
        res['b'] += sorted({str(x['stopId']) for day in j.values() if isinstance(day, dict) for x in day.get('stops', []) if x.get('ticketZoneBorder') and str(x['stopId']) in idx['stops']})
    except Exception as e: log('Strefy, ZTM Gdańsk: pominięto (%s)' % e)
    tmp = cache or tempfile.mkdtemp(prefix='strefy-')
    for area, urls in GTFS.items():
        n0 = len(res['b']) + len(res['z'])
        for i, url in enumerate(urls if isinstance(urls, list) else [urls]):
            try:
                p = os.path.join(tmp, '%s_%d.zip' % (area, i))
                if not os.path.exists(p): get(url, p)
                rows = csv.DictReader(io.TextIOWrapper(zipfile.ZipFile(p).open('stops.txt'), encoding='utf-8-sig'))
                for r in rows:
                    z = (r.get('zone_id') or '').strip(); nm = (r.get('stop_name') or '').strip()
                    if not z or not nm or not r.get('stop_lat'): continue
                    la, lo = float(r['stop_lat']), float(r['stop_lon'])
                    best = min(by.get((area, nm), []), key=lambda x: dist(la, lo, x[1], x[2]), default=None)
                    if not best or dist(la, lo, best[1], best[2]) > 80: continue
                    if area == 'waw':
                        if '+' in z: res['b'].append(best[0])
                    else: res['z'][best[0]] = z
            except Exception as e: log('Strefy, %s: pominięto (%s)' % (area, e))
        log('Strefy, %s: %d przystanków' % (area, len(res['b']) + len(res['z']) - n0))
    res['b'] = sorted(set(res['b']))
    json.dump(res, open(os.path.join(out, 'strefy.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    log('Strefy taryfowe: %d przystanków na granicy, %d ze strefą' % (len(res['b']), len(res['z'])))


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'),
          cache=sys.argv[2] if len(sys.argv) > 2 else None)
