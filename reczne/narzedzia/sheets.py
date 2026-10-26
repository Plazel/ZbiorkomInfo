"""MPGK Krynica-Zdrój weekend timetables published as spreadsheets ("minutówki"): one row per stop, each column
one bus; a column may run down the sheet or up it, and may hold several trips one after another.
Usage: python3 sheets.py <dir with ksob.xlsx and knie.xls> -> <dir>/trips_sheets.json"""
import json, os, re, sys, collections


def tc(s):   # as in transcribe.py
    return ' '.join(w if not (w.isupper() and len(w) > 2) else w[0] + w[1:].lower() for w in s.split())


def mpgk_name(raw):   # as in transcribe.py
    s = raw.replace('Czany', 'Czarny').replace('mochnaczka', 'Mochnaczka').strip()
    pole = ''
    m = re.search(r'/\s*(\w+)(\s*/\s*\w+)?\s*$', s)
    if m: pole = m.group(1); s = s[:m.start()].strip()
    s = s.rstrip('/ ').strip()
    s = re.sub(r'^Krynica-Zdrój\s*ul\.?\s*', '', s)
    s = re.sub(r'^Krynica-Zdrój\s+', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return tc(s), pole


def cells_xlsx(path):
    import openpyxl, datetime
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    out = []
    for row in ws.iter_rows(values_only=True):
        r = []
        for v in row:
            if isinstance(v, datetime.time): v = v.hour * 60 + v.minute
            elif isinstance(v, datetime.datetime): v = v.hour * 60 + v.minute
            elif isinstance(v, float) and 0 < v < 1: v = round(v * 1440)
            elif isinstance(v, str) and re.fullmatch(r'\s*\d{1,2}:\d{2}\s*', v): h, m = v.strip().split(':'); v = int(h) * 60 + int(m)
            r.append(v)
        out.append(r)
    return out


def cells_xls(path):
    import xlrd
    sh = xlrd.open_workbook(path).sheets()[0]; out = []
    for i in range(sh.nrows):
        r = []
        for j in range(sh.ncols):
            v, t = sh.cell_value(i, j), sh.cell_type(i, j)
            if t == xlrd.XL_CELL_NUMBER and 0 < v < 1: v = round(v * 1440)
            elif isinstance(v, str) and re.fullmatch(r'\s*\d{1,2}:\d{2}\s*', v): h, m = v.strip().split(':'); v = int(h) * 60 + int(m)
            r.append(v)
        out.append(r)
    return out


def trips_of(rows, line, days, src):
    cols = collections.defaultdict(list)
    for i, r in enumerate(rows):
        if not r or not isinstance(r[0], str) or not r[0].strip(): continue
        n, p = mpgk_name(r[0])
        for j, v in enumerate(r[1:], 1):
            if isinstance(v, int) and not isinstance(v, bool): cols[j].append((v, i, n, p))
    out = []
    for j in sorted(cols):
        pts = sorted(cols[j])
        # equal minutes at neighbouring stops: order them the way the column runs at that place
        res = []; k = 0
        while k < len(pts):
            g = [x for x in pts[k:] if x[0] == pts[k][0]]
            if len(g) > 1:
                prev = res[-1][1] if res else None
                nxt = pts[k + len(g)][1] if k + len(g) < len(pts) else None
                down = (nxt is not None and prev is not None and nxt > prev) or (prev is None and nxt is not None and nxt > g[0][1]) or \
                       (nxt is None and prev is not None and g[0][1] > prev)
                g.sort(key=lambda x: x[1] if down else -x[1])
            res += g; k += len(g)
        cur = [res[0]]
        for x in res[1:]:
            if x[0] - cur[-1][0] > 45: out.append(cur); cur = [x]
            else: cur.append(x)
        out.append(cur)
    return [{'line': line, 'days': days, 'src': src, 'stops': [[n, p, m] for m, i, n, p in t]} for t in out if len(t) >= 2]


if __name__ == '__main__':
    D = sys.argv[1]
    trips = trips_of(cells_xlsx(os.path.join(D, 'ksob.xlsx')), 'K6', 's', 'ksob.xlsx') + \
            trips_of(cells_xls(os.path.join(D, 'knie.xls')), 'K7', 'h', 'knie.xls')
    json.dump({'trips': trips}, open(os.path.join(D, 'trips_sheets.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    for t in trips: print(t['src'], t['stops'][0][0], '%02d:%02d' % divmod(t['stops'][0][2], 60), '->', t['stops'][-1][0], '%02d:%02d' % divmod(t['stops'][-1][2], 60), len(t['stops']))
