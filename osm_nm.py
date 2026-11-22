"""NetworkMaker: kopie danych OSM (przystanki, tory tramwajowe) dla miast NetworkMakera, zapisywane przy budowaniu rozkładów
do data/nm/. Aplikacja bierze przystanki najpierw z tej kopii (szybko i bez zależności od publicznych serwerów Overpass, które
często odmawiają lub nie odpowiadają), a gdy Overpass nie odpowiada – także tory.
Zapytania są takie same jak w tm.html (stopQuery, loadTram)."""
import json, os, time, urllib.parse, urllib.request

OVS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter', 'https://overpass.private.coffee/api/interpreter']
BOX = {'trojmiasto': '54.27,18.40,54.58,19.02', 'bydgoszcz': '53.06,17.85,53.21,18.20', 'krynica': '49.395,20.92,49.445,21.00'}


def stop_query(B):
    u = ['node["highway"="bus_stop"](%s)' % B, 'node["railway"="tram_stop"](%s)' % B, 'node["railway"~"^(station|halt)$"]["station"!="subway"](%s)' % B,
         'way["railway"~"^(station|halt)$"]["station"!="subway"](%s)' % B]
    for k in ('bus', 'trolleybus', 'tram'):
        u += ['node["public_transport"="platform"]["%s"="yes"](%s)' % (k, B), 'way["public_transport"="platform"]["%s"="yes"](%s)' % (k, B), 'way["highway"="platform"]["%s"="yes"](%s)' % (k, B)]
    for k in ('bus', 'trolleybus', 'tram'):
        u.append('node["public_transport"="stop_position"]["%s"="yes"]["name"](%s)' % (k, B))
    u += ['node["railway"="platform"]["tram"="yes"](%s)' % B, 'way["railway"="platform"]["tram"="yes"](%s)' % B]
    return '[out:json][timeout:180];(%s;);out body center;' % ';'.join(u)


def tram_query(B):
    return '[out:json][timeout:180];(way["railway"~"^(tram|light_rail|construction|proposed|disused)$"](%s);way["disused:railway"~"^(tram|light_rail)$"](%s););out body;>;out skel qt;' % (B, B)


def ov(q):
    last = None
    for u in OVS:
        try:
            req = urllib.request.Request(u, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': 'ZbiorkomInfo NetworkMaker (github.com/Plazel/ZbiorkomInfo)'})
            with urllib.request.urlopen(req, timeout=240) as r:
                j = json.loads(r.read())
            if j.get('remark') and any(w in j['remark'].lower() for w in ('error', 'timed out', 'out of memory')): raise RuntimeError(j['remark'])
            return j
        except Exception as e:
            last = e; time.sleep(5)
    raise last


def build(out, log=print):
    d = os.path.join(out, 'nm'); os.makedirs(d, exist_ok=True)
    for key, B in BOX.items():
        for kind, q in (('stops', stop_query(B)), ('tram', tram_query(B))):
            f = os.path.join(d, '%s_%s.json' % (kind, key))
            try:
                j = ov(q)
                if not j.get('elements'): raise RuntimeError('pusta odpowiedź')
                json.dump({'t': int(time.time()), 'bb': B, 'elements': j['elements']}, open(f, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
                log('NetworkMaker OSM %s %s: %d elementów' % (kind, key, len(j['elements'])))
            except Exception as e:
                log('NetworkMaker OSM %s %s: bez zmian (%s)' % (kind, key, e))


if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else 'data')
