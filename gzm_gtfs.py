"""Górnośląsko-Zagłębiowska Metropolia (ZTM GZM): oficjalne otwarte dane GTFS z portalu otwartedane.metropoliagzm.pl.

ZTM publikuje rozkład podzielony na kilka plików ZIP, każdy na kilka kolejnych dni (np. pon–śr, czw–pt, sob–nd). Wybieramy
najwcześniejsze pliki obejmujące dzień powszedni, sobotę i niedzielę i łączymy je w jeden katalog GTFS: identyfikatory kursów
i kalendarzy dostają przedrostek pliku (te same kursy w różnych plikach to różne dni), przystanki, linie i kształty są wspólne.
Kategoria linii z routes_ext.txt (route_type_1: Normalna, Nocna, Linia metropolitalna, Autobusowa komunikacja zastępcza)
trafia do routes.txt jako dodatkowa kolumna route_type_1.
"""
import csv, io, json, os, urllib.request, zipfile, datetime

PKG = 'https://otwartedane.metropoliagzm.pl/api/3/action/package_show?id=317435cc-0075-4d10-b8ef-6e9b0010e90a'
# wersja tymczasowa (jeden plik, publikowana dla Google'a) – do indeksu kursów GTFS-RT, gdyby dane na żywo odnosiły się do niej
PKG_TMP = 'https://otwartedane.metropoliagzm.pl/api/3/action/package_show?id=5d8d7145-1be1-4ed2-9c18-5535e056a56d'
RT_FILES = ('routes.txt', 'trips.txt', 'stop_times.txt', 'calendar.txt', 'calendar_dates.txt')
UA = {'User-Agent': 'ZbiorkomInfo (rozklady; github.com/Plazel/ZbiorkomInfo)'}


def _get(url, timeout=180, tries=3):
    # (portal GZM czasem nie odpowiada – kilka prób z przerwą)
    import time
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if k == tries - 1: raise
            time.sleep(20 * (k + 1))


def resources():
    """adresy plików ZIP z rozkładem (najnowsze wydanie), w kolejności nazw"""
    j = json.loads(_get(PKG, 60))
    rs = [r for r in j['result']['resources'] if (r.get('format') or '').upper() == 'ZIP' and r.get('url')]
    rs.sort(key=lambda r: r.get('name') or r['url'])
    return [r['url'] for r in rs]


def _rows(z, name):
    if name not in z.namelist(): return []
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), 'utf-8-sig')))


def _days(z):
    """rodzaje dni (0–6, pon–nd) i daty, które obejmuje plik"""
    out = set()
    for r in _rows(z, 'calendar.txt'):
        a = datetime.datetime.strptime(r['start_date'], '%Y%m%d').date(); b = datetime.datetime.strptime(r['end_date'], '%Y%m%d').date()
        d = a
        while d <= b:
            if r[('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')[d.weekday()]] == '1': out.add(d)
            d += datetime.timedelta(days=1)
    for r in _rows(z, 'calendar_dates.txt'):
        if r.get('exception_type') == '1': out.add(datetime.datetime.strptime(r['date'], '%Y%m%d').date())
    return out


def build(dest, cache_dir=None, log=print, rt_dir=None):
    """pobiera, wybiera i łączy pliki; zwraca True, gdy w dest jest gotowy katalog GTFS. rt_dir: katalog na pliki do indeksu kursów
    na żywo (rtindex.py) – każdy plik obejmujący wczoraj, dziś lub jutro osobno i bez zmian identyfikatorów (GTFS-RT podaje oryginalne
    trip_id), oraz wersja tymczasowa"""
    urls = resources()
    if not urls: raise RuntimeError('brak plików ZIP w zbiorze GZM')
    zips = []
    for i, u in enumerate(urls):
        data = _get(u)
        if not data.startswith(b'PK'): raise RuntimeError('plik %d nie jest archiwum ZIP' % i)
        z = zipfile.ZipFile(io.BytesIO(data)); zips.append((u, z, _days(z)))
    # pliki z dniem powszednim, sobotą i niedzielą (najwcześniejsze); gdy któregoś rodzaju brak – wszystkie, jakie są
    pick = []
    for want in ({0, 1, 2, 3, 4}, {5}, {6}):
        for u, z, ds in zips:
            if any(d.weekday() in want for d in ds):
                if not any(p[0] == u for p in pick): pick.append((u, z, ds))
                break
    if not pick: pick = zips
    if rt_dir:
        today = datetime.date.today(); want = {today + datetime.timedelta(days=i) for i in (-1, 0, 1)}
        n = 0
        for i, (u, z, ds) in enumerate(zips):
            if not (ds & want): continue
            d = os.path.join(rt_dir, 'e%d' % i); os.makedirs(d, exist_ok=True)
            for nm in RT_FILES:
                if nm in z.namelist(): z.extract(nm, d)
            n += 1
        try:
            j = json.loads(_get(PKG_TMP, 60)); rs = [r['url'] for r in j['result']['resources'] if (r.get('format') or '').upper() == 'ZIP' and r.get('url')]
            if rs:
                zt = zipfile.ZipFile(io.BytesIO(_get(rs[0]))); d = os.path.join(rt_dir, 'tmp'); os.makedirs(d, exist_ok=True)
                for nm in RT_FILES:
                    if nm in zt.namelist(): zt.extract(nm, d)
                n += 1
        except Exception as e: log('GZM: wersja tymczasowa do GTFS-RT pominięta (%s)' % e)
        log('GZM: %d plików do indeksu kursów na żywo' % n)
    log('GZM: %d z %d plików (%s)' % (len(pick), len(zips), ', '.join(min(p[2]).strftime('%d.%m') + '–' + max(p[2]).strftime('%d.%m') for p in pick if p[2])))
    os.makedirs(dest, exist_ok=True)
    W = {}
    def out(name, fields):
        if name not in W:
            f = open(os.path.join(dest, name), 'w', encoding='utf-8', newline='')
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); W[name] = (f, w)
        return W[name][1]
    seen = {'stops': set(), 'routes': set(), 'shapes': set()}
    for fi, (u, z, ds) in enumerate(pick):
        P = 'f%d_' % fi
        ext = {r['route_id']: r.get('route_type_1', '') for r in _rows(z, 'routes_ext.txt')}
        for name, key in (('stops.txt', 'stops'), ('routes.txt', 'routes')):
            rows = _rows(z, name)
            if not rows: continue
            fields = list(rows[0].keys()) + (['route_type_1'] if name == 'routes.txt' else [])
            w = out(name, fields)
            idk = 'stop_id' if key == 'stops' else 'route_id'
            for r in rows:
                if r[idk] in seen[key]: continue
                seen[key].add(r[idk])
                if name == 'routes.txt': r['route_type_1'] = ext.get(r['route_id'], '')
                w.writerow(r)
        if fi == 0:
            for name in ('agency.txt', 'feed_info.txt'):
                rows = _rows(z, name)
                if rows:
                    w = out(name, list(rows[0].keys()))
                    for r in rows: w.writerow(r)
        for name, cols in (('calendar.txt', ('service_id',)), ('calendar_dates.txt', ('service_id',)), ('trips.txt', ('trip_id', 'service_id')), ('stop_times.txt', ('trip_id',))):
            if name not in z.namelist(): continue
            rd = csv.DictReader(io.TextIOWrapper(z.open(name), 'utf-8-sig'))
            w = out(name, rd.fieldnames)
            for r in rd:
                for c in cols:
                    if r.get(c): r[c] = P + r[c]
                w.writerow(r)
        if 'shapes.txt' in z.namelist():
            rd = csv.DictReader(io.TextIOWrapper(z.open('shapes.txt'), 'utf-8-sig'))
            w = out('shapes.txt', rd.fieldnames); new = set()
            for r in rd:
                s = r['shape_id']
                if s in seen['shapes']: continue
                new.add(s); w.writerow(r)
            seen['shapes'] |= new
    for f, _ in W.values(): f.close()
    for n in ('stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt'):
        if not os.path.exists(os.path.join(dest, n)): raise RuntimeError('GZM: brak ' + n)
    return True


if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else 'gzm_out')
