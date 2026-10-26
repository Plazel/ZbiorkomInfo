import subprocess,re,sys,json
def parse(pdf):
    txt=subprocess.run(['pdftotext','-layout',pdf,'-'],capture_output=True,text=True).stdout.splitlines()
    hdr=next(l for l in txt if l.strip().startswith('Przystanek'))
    cols=[(m.start()+len(m.group(0))/2,m.group(0)) for m in re.finditer(r'(?<=\s)(D,m|D|6|S|7)(?=\s|$)',hdr)]
    trips=[{'code':c,'st':[]} for _,c in cols]
    rows=[l for l in txt[txt.index(hdr)+1:] if re.search(r'\d\d:\d\d',l)]
    ref=next([m.start()+2.5 for m in re.finditer(r'\d\d:\d\d',l)] for l in rows if len(re.findall(r'\d\d:\d\d',l))==len(cols))
    for l in rows:
        name=re.split(r'\s{2,}',l.strip())[0]
        for m in re.finditer(r'\d\d:\d\d',l):
            c=m.start()+2.5;j=min(range(len(cols)),key=lambda i:abs(ref[i]-c))
            trips[j]['st'].append([name,m.group(0)])
    return trips
if __name__=='__main__':
    for p in sys.argv[1:]:
        t=parse(p);print(p,len(t),[(x['code'],len(x['st']),x['st'][0][1]) for x in t])
