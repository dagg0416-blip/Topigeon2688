from flask import Flask, request, jsonify, send_from_directory
import requests, re
from bs4 import BeautifulSoup
from datetime import datetime

app=Flask(__name__, static_folder='.')
TOP='https://www.topigeon.com.tw/index.asp'
HEAD={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'}

def txt(resp):
    # TOPIGEON is an older ASP site; respect declared encoding, then Big5 fallback.
    enc=resp.encoding
    if not enc or enc.lower() in ('iso-8859-1','ascii'):
        enc=resp.apparent_encoding or 'big5'
    try:return resp.content.decode(enc, errors='replace')
    except:return resp.content.decode('big5', errors='replace')

def parse_rows(html):
    soup=BeautifulSoup(html,'html.parser')
    rows=[]
    for tr in soup.select('tr'):
        c=[x.get_text(' ',strip=True) for x in tr.select('td')]
        if len(c)>=5 and c[0].isdigit() and c[1].isdigit() and c[2]=='2688' and re.match(r'^\d{1,2}:\d{2}:\d{2}(?:\.\d+)?$',c[4]):
            rows.append({'serial1':int(c[0]),'serial2':int(c[1]),'loft':c[2],'ring':c[3].zfill(2),'return_time':c[4]})
    return rows

def extract_meta(html):
    soup=BeautifulSoup(html,'html.parser')
    body=soup.get_text(' ',strip=True)
    release_place=release_time=None
    for pat in [r'施放地(?:點)?\s*[:：]?\s*([^\s]+)',r'放鴿地(?:點)?\s*[:：]?\s*([^\s]+)']:
        m=re.search(pat,body)
        if m: release_place=m.group(1); break
    m=re.search(r'施放時間\s*[:：]?\s*(\d{1,2}:\d{2}(?::\d{2})?)',body)
    if m: release_time=m.group(1)
    return release_place,release_time

@app.get('/')
def home(): return send_from_directory('.', 'index.html')

@app.get('/health')
def health(): return {'ok':True}

@app.get('/api/topigeon')
def topigeon():
    date=request.args.get('date','').strip().replace('-','/')
    passwd=request.args.get('pass','')
    try: datetime.strptime(date,'%Y/%m/%d')
    except: return jsonify(error='日期格式需為 YYYY/MM/DD'),400
    data={'QSysid':'1606','QMode':'train','QRaceDate':date,'QSite':'2688','QSiteCode':'2688','qsize':'1000','QSort':'0','QPass':passwd,'p':'N','btnSubmit':'查詢'}
    try:
        with requests.Session() as s:
            s.headers.update(HEAD)
            s.get(TOP,timeout=20)
            r=s.post(TOP,data=data,timeout=30)
            r.raise_for_status(); html=txt(r)
        rows=parse_rows(html)
        place,rtime=extract_meta(html)
        if not rows:
            # Return diagnostic without leaking full upstream HTML.
            soup=BeautifulSoup(html,'html.parser')
            page=soup.get_text(' ',strip=True)[:500]
            return jsonify(error='TOPIGEON 有回應，但沒有解析到 2688 紀錄。可能需要自訓密碼、當日無資料，或網站格式已變更。',diagnostic=page),422
        raw='\n'.join(f"{x['serial1']} {x['serial2']} 2688 {x['ring']} {x['return_time']}" for x in rows)
        return jsonify(date=date,count=len(rows),rows=rows,raw_text=raw,release_place=place,release_time=rtime)
    except requests.RequestException as e:
        return jsonify(error='連線 TOPIGEON 失敗',detail=str(e)),502

if __name__=='__main__': app.run(host='0.0.0.0',port=8080)
