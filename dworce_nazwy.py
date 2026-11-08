#!/usr/bin/env python3
"""Stops named with the word "Dworzec" in full ("Dworzec Centralny", "Dworzec Łódź Kaliska", "Aleja Batorego - Dworzec PKP"),
not "Dw." as in the operators' data; also inside other texts (headsigns, "Kurs do: …").
Done on the data written by build.py, like krynica_nazwy.py.
Usage: python3 dworce_nazwy.py [data folder]   (build.py calls apply())"""
import json, os, re, sys
from krynica_nazwy import _apply

DW = re.compile(r'(?<![\w.])Dw\.\s*(?=\w)')


def apply(out, log=print):
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    mp = {s[0]: DW.sub('Dworzec ', s[0]) for s in idx['stops'].values() if DW.search(s[0])}
    # (also: a bracket after a name parted from it, "Krusau(DK)" -> "Krusau (DK)")
    for s_ in idx['stops'].values():
        n0 = mp.get(s_[0], s_[0]); n1 = re.sub(r'(?<=\w)\(', ' (', n0)
        if n1 != s_[0]: mp[s_[0]] = n1
    if mp:
        rx = re.compile(r'(?<![\w.])(' + '|'.join(re.escape(k) for k in sorted(mp, key=len, reverse=True)) + r')(?![\w])')
        n = _apply(out, lambda v: rx.sub(lambda m: mp[m.group(1)], v) if 'Dw.' in v or '(' in v else v, ('Dw.', '('))
        log('„Dworzec” zamiast „Dw.”: %d nazw (%d plików)' % (len(mp), n))
    return mp


if __name__ == '__main__':
    apply(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
