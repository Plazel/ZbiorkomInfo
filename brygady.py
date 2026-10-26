#!/usr/bin/env python3
"""Rozkłady brygad (zadania przewozowe) z plików GTFS.

Dla każdego przewoźnika, który podaje w GTFS numer brygady (block_id / brigade),
zapisuje data/bg/<źródło>.json (daty -> plan) i data/bg/<źródło>_<n>.json (plan dnia:
brygady z listą kursów). Uruchamiane na końcu build.py albo osobno:
    python brygady.py [folder_danych] [--zips folder_z_plikami_zip]
"""
import csv, datetime, hashlib, io, json, os, sys, urllib.request, zipfile, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = {
    'ztm':  ['https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/30e783e4-2bec-4a7d-bb22-ee3e3b26ca96/download/gtfsgoogle.zip'],
    'waw':  ['https://mkuran.pl/gtfs/warsaw.zip'],
    'poz':  ['https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile'],
    'krk':  ['https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip', 'https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip'],
    'byd':  ['https://mkuran.pl/gtfs/bydgoszcz.zip'],
}
ZIPNAME = {'ztm': ['ztm'], 'waw': ['waw'], 'poz': ['poz'], 'krk': ['krkA', 'krkT'], 'byd': ['byd']}
DAYS_N = 21


def tmin(t):
    h, m, *_ = t.strip().split(':')
    return int(h) * 60 + int(m)


def open_zip(src, i, zdir):
    if zdir:
        p = os.path.join(zdir, ZIPNAME[src][i] + '.zip')
        if os.path.exists(p): return zipfile.ZipFile(p)
    req = urllib.request.Request(SRC[src][i], headers={'User-Agent': 'rozklady-trojmiasto/1.0'})
    with urllib.request.urlopen(req, timeout=300) as r: return zipfile.ZipFile(io.BytesIO(r.read()))


def rows(z, name):
    if name not in z.namelist(): return iter(())
    return csv.DictReader(io.TextIOWrapper(z.open(name), encoding='utf-8-sig'))


def active(z, dates):
    """service_id -> set of dates (YYYYMMDD) within the window"""
    out = collections.defaultdict(set); ds = set(dates)
    for c in rows(z, 'calendar.txt'):
        a, b = c['start_date'], c['end_date']
        for d in dates:
            if a <= d <= b and c[['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday()]] == '1':
                out[c['service_id']].add(d)
    for c in rows(z, 'calendar_dates.txt'):
        d = c['date']
        if d not in ds: continue
        if c['exception_type'] == '1': out[c['service_id']].add(d)
        else: out[c['service_id']].discard(d)
    return out


def load(src, zdir, dates):
    """-> {date: {key: {'lab':…, 'fl':…, 'trips':[(line, dep, from, arr, to)]}}}"""
    per = collections.defaultdict(lambda: collections.defaultdict(lambda: {'lab': '', 'fl': '', 'trips': []}))
    for i in range(len(SRC[src])):
        z = open_zip(src, i, zdir)
        R = {r['route_id']: (r.get('route_short_name') or r['route_id']).strip() for r in rows(z, 'routes.txt')}
        S = {s['stop_id']: s['stop_name'].strip() for s in rows(z, 'stops.txt')}
        svc = active(z, dates)
        T = {}
        for t in rows(z, 'trips.txt'):
            if not svc.get(t['service_id']): continue
            line = R.get(t['route_id'], '?')
            if src == 'ztm':
                b = t['trip_id'].rsplit('_', 1)[-1]; key, lab = b, b
            elif src == 'poz':
                b = t.get('brigade', ''); key, lab = line + '/' + b, line + '/' + b
            elif src == 'krk':
                b = t.get('block_id', ''); key = str(i) + ':' + b
                lab = b if i == 0 else 'T/' + b.replace('block_', '')
            else:   # waw, byd
                b = t.get('block_id', ''); key = b; lab = t.get('block_short_name') or b
            if not b: continue
            T[t['trip_id']] = (line, key, lab, t.get('fleet_type', ''), t['service_id'])
        first, last = {}, {}
        for st in rows(z, 'stop_times.txt'):
            tid = st['trip_id']
            if tid not in T: continue
            q = int(st['stop_sequence'])
            if tid not in first or q < first[tid][0]: first[tid] = (q, st['departure_time'] or st['arrival_time'], st['stop_id'])
            if tid not in last or q > last[tid][0]: last[tid] = (q, st['arrival_time'] or st['departure_time'], st['stop_id'])
        for tid, (line, key, lab, fl, sid) in T.items():
            if tid not in first: continue
            tr = (line, tmin(first[tid][1]), S.get(first[tid][2], '?'), tmin(last[tid][1]), S.get(last[tid][2], '?'))
            for d in svc[sid]:
                B = per[d][key]; B['lab'] = lab; B['trips'].append(tr)
                if fl and not B['fl']: B['fl'] = fl
    return per


def plan_of(blocks, src):
    """one day: compact JSON plan (deterministic, so equal days give equal files)"""
    raw = []
    for key, B in blocks.items():
        tr = sorted(set(B['trips']), key=lambda x: (x[1], x[0], x[3]))
        main = collections.Counter(t[0] for t in tr).most_common(1)[0][0]
        lab = B['lab']
        if src in ('waw', 'byd') or (src == 'krk' and lab.startswith('T/')):
            lab = main + '/' + lab.replace('T/', '')
        raw.append((lab, B['fl'], tr, key))
    def sk(b):
        l = b[0].split('/')[0].split('-')[0]
        return (0 if l[:1].isalpha() else 1, int(''.join(c for c in l if c.isdigit()) or 0), l, b[0], b[2][0][1] if b[2] else 0)
    raw.sort(key=sk)
    names = sorted({t[2] for b in raw for t in b[2]} | {t[4] for b in raw for t in b[2]})
    lines = sorted({t[0] for b in raw for t in b[2]})
    ni = {n: i for i, n in enumerate(names)}; li = {n: i for i, n in enumerate(lines)}
    out = [[lab, fl, [[li[t[0]], t[1], ni[t[2]], t[3], ni[t[4]]] for t in tr], key if src in ('ztm', 'poz', 'krk') else ''] for lab, fl, tr, key in raw]
    return {'S': names, 'L': lines, 'B': out}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    out = args[0] if args else os.path.join(HERE, 'data')
    zdir = sys.argv[sys.argv.index('--zips') + 1] if '--zips' in sys.argv else None
    if zdir in args: args.remove(zdir); out = args[0] if args else os.path.join(HERE, 'data')
    bg = os.path.join(out, 'bg'); os.makedirs(bg, exist_ok=True)
    for f in os.listdir(bg): os.remove(os.path.join(bg, f))
    today = datetime.date.today()
    dates = [(today + datetime.timedelta(days=i)).strftime('%Y%m%d') for i in range(DAYS_N)]
    for src in SRC:
        try:
            per = load(src, zdir, dates)
        except Exception as e:
            print('Brygady', src, 'pominięte:', e); continue
        seen, idx = {}, {}
        for d in dates:
            if d not in per: continue
            P = plan_of(per[d], src)
            s = json.dumps(P, ensure_ascii=False, separators=(',', ':'))
            h = hashlib.md5(s.encode()).hexdigest()
            if h not in seen:
                seen[h] = len(seen)
                open(os.path.join(bg, '%s_%d.json' % (src, seen[h])), 'w', encoding='utf-8').write(s)
            idx[d] = seen[h]
        json.dump({'dates': idx}, open(os.path.join(bg, src + '.json'), 'w', encoding='utf-8'), separators=(',', ':'))
        print('Brygady %s: %d dni, %d różnych planów' % (src, len(idx), len(seen)))


if __name__ == '__main__':
    main()
