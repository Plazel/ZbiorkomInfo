#!/usr/bin/env python3
"""Krynica-Zdrój's stops named without "-Zdrój" ("Krynica Czarny Potok Gondola"): there is only one Krynica in the area, so
the shorter name is enough on the page and in the guide's announcements. The railway station and the stop at it keep the
town's full name ("Krynica-Zdrój", "Krynica-Zdrój Dworzec PKP"), as do the operator (MPGK Krynica-Zdrój) and the area.
Done on the data written by build.py (the names inside the build stay as in the sources).
Usage: python3 krynica_nazwy.py [data folder]   (build.py calls apply())"""
import json, os, re, sys

OLD, NEW = 'Krynica-Zdrój', 'Krynica'
RX = re.compile(r'Krynica-Zdrój (?!Dworzec PKP)(?=\w)')
KEEP_KEYS = {'op'}   # (the operator: its own name)


def fix(v, key=None):
    if isinstance(v, str): return v if key in KEEP_KEYS or OLD not in v else RX.sub(NEW + ' ', v)
    if isinstance(v, list): return [fix(x) for x in v]
    if isinstance(v, dict): return {(RX.sub(NEW + ' ', k) if OLD in k else k): fix(x, k) for k, x in v.items()}
    return v


def apply(out, log=print):
    n = 0
    for root, _, files in os.walk(out):
        for f in files:
            if not f.endswith('.json'): continue
            p = os.path.join(root, f)
            s = open(p, encoding='utf-8').read()
            if OLD not in s: continue
            json.dump(fix(json.loads(s)), open(p, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':')); n += 1
    log('Krynica bez „-Zdrój”: %d plików' % n)
    return n


if __name__ == '__main__':
    apply(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
