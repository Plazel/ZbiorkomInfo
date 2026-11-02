#!/usr/bin/env python3
"""Bydgoszcz: the numbers of the stops in ZDMiKP's live departures service (odjazdy.zdmikp.bydgoszcz.pl, the system behind
the electronic boards at the stops) for the stops of the timetable. The service numbers its stops in its own way
(iIdParada); each also has the stop's code (sIdParada, "6018"), which is the timetable's stop id ("06018"). The stops are
read line by line (one request per line), so this takes about a minute. Result: data/byd_live.json {stop code: number}.
Usage: python3 byd_live.py [data folder]   (build.py calls it once a month, or when the file is missing)"""
import json, os, sys, urllib.request, concurrent.futures

URL = 'http://odjazdy.zdmikp.bydgoszcz.pl/PresenterService.asmx/'
UA = {'User-Agent': 'ZbiorkomInfo/1.0 (timetable site)', 'Content-Type': 'application/json; charset=utf-8'}


def call(method, args):
    req = urllib.request.Request(URL + method, data=json.dumps(args).encode(), headers=UA, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r: return json.load(r).get('d')


def build(lines, out_path):
    """lines: line numbers to read (the service's line number is the line's own number)"""
    codes = {}
    def one(n):
        try: return call('GetParadas', {'iIdLinea': n, 'bTodas': True}) or []
        except Exception: return []
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        for ps in ex.map(one, lines):
            for p in ps:
                try: codes[str(int(p['sIdParada']))] = p['iIdParada']
                except (ValueError, KeyError, TypeError): pass
    if codes:
        json.dump(codes, open(out_path, 'w', encoding='utf-8'), separators=(',', ':'))
    return len(codes)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    ls = sorted({int(str(r['n']).rstrip('N')) for r in idx['routes'] if r['id'].startswith('b') and str(r['n']).rstrip('N').isdigit()})   # (night lines: 31N is the service's 31)
    print('Bydgoszcz, odjazdy na żywo: %d przystanków' % build(ls, os.path.join(out, 'byd_live.json')))
