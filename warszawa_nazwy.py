#!/usr/bin/env python3
"""Warszawa's stops named with the word "Dworzec" in full ("Dworzec Centralny", not "Dw. Centralny" as in ZTM's data).
Only Warszawa's stops (Łódź keeps its own names); also inside other texts (headsigns, "Kurs do: …").
Done on the data written by build.py, like krynica_nazwy.py.
Usage: python3 warszawa_nazwy.py [data folder]   (build.py calls apply())"""
import json, os, re, sys
from krynica_nazwy import _apply


def apply(out, log=print):
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    mp = {s[0]: 'Dworzec ' + s[0][4:] for s in idx['stops'].values() if s[4] == 'waw' and s[0].startswith('Dw. ')}
    if mp:
        rx = re.compile(r'(?<![\w.])(' + '|'.join(re.escape(k) for k in sorted(mp, key=len, reverse=True)) + r')(?![\w])')
        n = _apply(out, lambda v: rx.sub(lambda m: mp[m.group(1)], v) if 'Dw. ' in v else v, ('Dw. ',))
        log('Warszawa: %d nazw z „Dworzec” (%d plików)' % (len(mp), n))
    return mp


if __name__ == '__main__':
    apply(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
