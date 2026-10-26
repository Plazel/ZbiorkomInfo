import cv2, numpy as np, pytesseract, sys, json, re
def runs(mask, minlen):
    """start/end of runs of True"""
    out=[];i=0;n=len(mask)
    while i<n:
        if mask[i]:
            j=i
            while j<n and mask[j]: j+=1
            out.append((i,j));i=j
        else: i+=1
    return out
def grid(path):
    img=cv2.imread(path,cv2.IMREAD_GRAYSCALE);bw=(img<160).astype(np.uint8)
    H,W=bw.shape
    # long horizontal / vertical lines
    hk=cv2.morphologyEx(bw,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(W//6,1)))
    vk=cv2.morphologyEx(bw,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,H//12)))
    hy=[ (a+b)//2 for a,b in runs(hk.sum(1)>W//6,1)]
    vx=[ (a+b)//2 for a,b in runs(vk.sum(0)>H//12,1)]
    return img,hy,vx
def ocr_cell(img,x0,x1,y0,y1):
    c=img[y0+4:y1-3,x0+4:x1-3]
    if c.size==0 or (c<160).sum()<15: return ''
    c=cv2.copyMakeBorder(c,15,15,15,15,cv2.BORDER_CONSTANT,value=255)
    c=cv2.resize(c,None,fx=1.6,fy=1.6,interpolation=cv2.INTER_CUBIC)
    t=pytesseract.image_to_string(c,config='--psm 7 -c tessedit_char_whitelist=0123456789:-').strip()
    return t
if __name__=='__main__':
    img,hy,vx=grid(sys.argv[1])
    print('rows',len(hy),'cols',len(vx),file=sys.stderr)
    first=int(sys.argv[2]); 
    rows=[]
    for i in range(len(hy)-1):
        y0,y1=hy[i],hy[i+1]
        if y1-y0<15: continue
        cells=[ocr_cell(img,vx[j],vx[j+1],y0,y1) for j in range(first,len(vx)-1)]
        rows.append(cells)
    json.dump({'hy':hy,'vx':vx,'rows':rows},open(sys.argv[3],'w'))
