#!/usr/bin/env python3
"""Lokalny serwer strony ZbiorkomInfo: udostępnia folder ze stroną pod http://localhost:8765/
i przekazuje zapytania tablicy odjazdów do API ZTM Gdańsk (/rt?stopId=…), które samo nie pozwala
na odczyt z przeglądarki (brak nagłówka CORS). Dzięki temu tablica pokazuje odjazdy na żywo.
Użycie: python serwer.py [port]"""
import http.server, os, sys, urllib.parse, urllib.request, webbrowser, threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
RT = 'https://ckan2.multimediagdansk.pl/departures?'
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/rtdep?'):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:
                body = json.dumps(rt_departures(q.get('area', [''])[0], q.get('stops', [''])[0].split(','))).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(body)
            except Exception as e: self.send_error(502, str(e)[:200])
            return
        if self.path.startswith('/gps') or self.path.startswith('/rtveh?'):
            try:
                if self.path.startswith('/gps'): body = _get(GPS, 15)
                else: body = json.dumps(rt_vehicles(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('area', [''])[0])).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(body)
            except Exception as e: self.send_error(502, str(e)[:200])
            return
        if self.path.startswith('/rt?'):
            q = urllib.parse.urlsplit(self.path).query
            stop = urllib.parse.parse_qs(q).get('stopId', [''])[0]
            if not stop.isdigit():
                self.send_error(400); return
            try:
                req = urllib.request.Request(RT + 'stopId=' + stop, headers={'User-Agent': 'iRozklad/1.0'})
                with urllib.request.urlopen(req, timeout=10) as r: body = r.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(body)
            except Exception as e:
                self.send_error(502, str(e))
            return
        return super().do_GET()
    def log_message(self, *a): pass


# ---- live departures from GTFS-Realtime (Poznań, Kraków, Warszawa, Łódź, Praga): trip updates joined to the static timetable ----
import csv, io, json, time, zipfile, datetime, threading as _th
RT_AREAS = {   # area -> [(stop id prefix on the page, static GTFS, trip updates)]
    'poz': [('P', 'https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile', 'https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile?file=trip_updates.pb')],
    'krk': [('KA', 'https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip', 'https://gtfs.ztp.krakow.pl/TripUpdates_A.pb'),
            ('KT', 'https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip', 'https://gtfs.ztp.krakow.pl/TripUpdates_T.pb')],
    # Warszawa and Łódź: trip updates published by zbiorkom.live (Warszawa: joined to its own GTFS, whose stop ids are the
    # same ZTM ids as on the page; Łódź: the city's own GTFS)
    'waw': [('W', 'https://cdn.zbiorkom.live/gtfs/warsaw.zip', 'https://cdn.zbiorkom.live/gtfs-rt/warsaw.pb')],
    'ldz': [('L', 'https://otwarte.miasto.lodz.pl/wp-content/uploads/2025/06/GTFS.zip', 'https://cdn.zbiorkom.live/gtfs-rt/lodz.pb')],
    # Praga: PID open data (Golemio), public GTFS-Realtime
    'prg': [('G', 'https://data.pid.cz/PID_GTFS.zip', 'https://api.golemio.cz/v2/vehiclepositions/gtfsrt/trip_updates.pb')],
}
_STATIC, _LOCK = {}, _th.Lock()
def _get(u, t=60):
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'iRozklad/1.0'}), timeout=t) as r: return r.read()
def _static(url):
    """trip_id -> (line, headsign, [(stop_sequence, stop_id, seconds)]) from a GTFS file, kept for a day.
    Stored compactly (big feeds such as Warszawa or Praga have millions of stop times): per trip three int arrays."""
    with _LOCK:
        c = _STATIC.get(url)
        if c and time.time() - c[0] < 86400: return c[1]
        from array import array
        z = zipfile.ZipFile(io.BytesIO(_get(url, 600)))
        rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), 'utf-8-sig'))
        routes = {r['route_id']: r['route_short_name'] for r in rd('routes.txt')}
        trips = {r['trip_id']: [routes.get(r['route_id'], r['route_id']), r.get('trip_headsign', ''), array('i'), array('i'), array('i')] for r in rd('trips.txt')}
        sidx, snames = {}, []
        with z.open('stop_times.txt') as fh:
            rdr = csv.reader(io.TextIOWrapper(fh, 'utf-8-sig')); hdr = next(rdr)
            it, idp, isd, isq = hdr.index('trip_id'), hdr.index('departure_time'), hdr.index('stop_id'), hdr.index('stop_sequence')
            for row in rdr:
                t = trips.get(row[it])
                if t is None or not row[idp]: continue
                h, m, sec = row[idp].split(':'); k = sidx.get(row[isd])
                if k is None: k = sidx[row[isd]] = len(snames); snames.append(row[isd])
                t[2].append(int(row[isq])); t[3].append(k); t[4].append(int(h) * 3600 + int(m) * 60 + int(sec))
        out = {}
        for tid, t in trips.items():
            if not t[2]: continue
            order = sorted(range(len(t[2])), key=t[2].__getitem__)
            out[tid] = (t[0], t[1], _Seq(array('i', (t[2][i] for i in order)), array('i', (t[3][i] for i in order)), array('i', (t[4][i] for i in order)), snames))
        _STATIC[url] = (time.time(), out); return out
class _Seq:
    """a trip's stops as (stop_sequence, stop_id, seconds), read from compact arrays"""
    __slots__ = ('q', 's', 't', 'n')
    def __init__(self, q, s, t, n): self.q, self.s, self.t, self.n = q, s, t, n
    def __iter__(self): return ((self.q[i], self.n[self.s[i]], self.t[i]) for i in range(len(self.q)))
    def __len__(self): return len(self.q)
    def __getitem__(self, i): return (self.q[i], self.n[self.s[i]], self.t[i])
def _varint(b, i):
    v = s = 0
    while True:
        x = b[i]; i += 1; v |= (x & 127) << s; s += 7
        if x < 128: return v, i
def _pb(b):
    """protobuf message -> {field: [values]} (varints as int, length-delimited as bytes)"""
    i, out = 0, {}
    while i < len(b):
        k, i = _varint(b, i); f, w = k >> 3, k & 7
        if w == 0: v, i = _varint(b, i)
        elif w == 2: n, i = _varint(b, i); v = b[i:i + n]; i += n
        elif w == 1: v = b[i:i + 8]; i += 8
        elif w == 5: v = b[i:i + 4]; i += 4
        else: break
        out.setdefault(f, []).append(v)
    return out
_s64 = lambda v: v - (1 << 64) if v >= 1 << 63 else v
_RT = {}
try:
    from zoneinfo import ZoneInfo; _TZ = ZoneInfo('Europe/Warsaw')
except Exception: _TZ = None   # without time zone data the computer's own (Polish) time is used
def rt_departures(area, stops):
    """next departures (2 h) at the given page stop ids: [{r, h, t (epoch s), st (scheduled), s (stop id)}]"""
    now = time.time(); out = []
    for pre, st_url, tu_url in RT_AREAS.get(area, []):
        want = {x[len(pre):] for x in stops if x.startswith(pre)}
        if not want: continue
        trips = _static(st_url)
        c = _RT.get(tu_url)
        if not c or now - c[0] > 20: c = _RT[tu_url] = (now, _pb(_get(tu_url, 20)))
        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for ent in c[1].get(2, []):
            e = _pb(ent); tu = e.get(3)
            if not tu: continue
            tu = _pb(tu[0]); td = _pb(tu.get(1, [b''])[0])
            tid = td.get(1, [b''])[0].decode('utf-8', 'replace'); trip = trips.get(tid)
            if not trip: continue
            sd = td.get(3, [b''])[0].decode()
            base = datetime.datetime.strptime(sd, '%Y%m%d') if sd else today
            if _TZ: base = base.replace(tzinfo=_TZ)   # timetable times are Polish local time
            if not sd and trip[2] and trip[2][0][2] > 20 * 3600 and datetime.datetime.now().hour < 6: base -= datetime.timedelta(days=1)
            b0 = base.timestamp()
            upd = {}
            for su in tu.get(2, []):
                u = _pb(su); seq = u.get(1, [None])[0]; sid = u.get(4, [b''])[0].decode()
                ev = _pb((u.get(3) or u.get(2) or [b''])[0])
                upd[seq if seq is not None else sid] = (_s64(ev[1][0]) if 1 in ev else None, _s64(ev[2][0]) if ev.get(2) and ev[2][0] else None)
            delay = _s64(tu[5][0]) if 5 in tu else 0
            seqs = {q for q, _, _ in trip[2]}; sids = {x for _, x, _ in trip[2]}
            for k, (d, t) in upd.items():   # an update for a stop the timetable does not list (e.g. sequence 0): from the start
                if k not in seqs and k not in sids and d is not None: delay = d
            for seq, sid, secs in trip[2]:
                if seq in upd or sid in upd:
                    d, t = upd.get(seq) or upd.get(sid)
                    if d is not None: delay = d
                    if t: delay = t - (b0 + secs)
                if sid in want:
                    t = b0 + secs + delay
                    if delay < -900: continue   # far ahead of time: an update meant for another run of the trip
                    if now - 60 <= t <= now + 7200: out.append({'r': trip[0], 'h': trip[1], 't': int(t), 'st': int(b0 + secs), 's': pre + sid})
    return sorted(out, key=lambda x: x['t'])

# ---- vehicles on brigades (Rozkłady brygad): which vehicle runs which brigade right now ----
GPS = 'https://ckan2.multimediagdansk.pl/gpsPositions?v=2'
VP = {'poz': [(None, 'https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile?file=vehicle_positions.pb')],
      'krk': [('https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip', 'https://gtfs.ztp.krakow.pl/VehiclePositions_A.pb'),
              ('https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip', 'https://gtfs.ztp.krakow.pl/VehiclePositions_T.pb')]}
_BLK = {}
def _blocks(url):
    """trip_id -> block_id, kept for a day"""
    with _LOCK:
        c = _BLK.get(url)
        if c and time.time() - c[0] < 86400: return c[1]
        z = zipfile.ZipFile(io.BytesIO(_get(url, 300)))
        m = {r['trip_id']: r.get('block_id', '') for r in csv.DictReader(io.TextIOWrapper(z.open('trips.txt'), 'utf-8-sig'))}
        _BLK[url] = (time.time(), m); return m
def rt_vehicles(area):
    """{brigade key as in data/bg: vehicle number} from GTFS-Realtime vehicle positions"""
    out = {}
    for i, (st_url, vp_url) in enumerate(VP.get(area, [])):
        blk = _blocks(st_url) if st_url else None
        for ent in _pb(_get(vp_url, 20)).get(2, []):
            e = _pb(ent)
            if 4 not in e: continue
            v = _pb(e[4][0]); td = _pb(v[1][0]) if 1 in v else {}; vd = _pb(v[8][0]) if 8 in v else {}
            g = lambda d, k: d[k][0].decode('utf-8', 'replace') if k in d else ''
            veh = g(vd, 3) or g(vd, 1); tid = g(td, 1)
            if area == 'poz': key = g(vd, 2)   # label "linia/brygada"
            else:
                b = blk.get(tid, '') if blk else ''
                if not b and tid.startswith('block_'): b = '_'.join(tid.split('_')[:2])
                key = '%d:%s' % (i, b) if b else ''
            if key and veh: out[key] = veh
    return out

srv = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H)
url = 'http://localhost:%d/index.html' % PORT
print('ZbiorkomInfo działa pod adresem', url)
print('Zostaw to okno otwarte; zamknij je, aby wyłączyć serwer.')
threading.Timer(1, lambda: webbrowser.open(url)).start()
try: srv.serve_forever()
except KeyboardInterrupt: pass
