"""2688 TOPIGEON proxy. No server-side persistent user data."""
from flask import Flask, request, jsonify, send_from_directory
import requests, re
from bs4 import BeautifulSoup
from datetime import datetime

app = Flask(__name__, static_folder='.')
TOP = 'https://www.topigeon.com.tw/index.asp'
HEAD = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1', 'Referer': TOP}


def decode(response):
    encoding = response.encoding
    if not encoding or encoding.lower() in ('iso-8859-1', 'ascii'):
        encoding = response.apparent_encoding or 'big5'
    try:
        return response.content.decode(encoding, errors='replace')
    except LookupError:
        return response.content.decode('big5', errors='replace')


def seconds(t):
    h, m, s = t.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_rows(html, eligible=None):
    """Keep earliest observed return for each eligible ring, regardless of hour.

    Eligibility must come from an external-training participant list. Without
    it, an afternoon-only home flight cannot reliably be distinguished from a
    late external-training return; return such records for manual review.
    """
    by_ring = {}
    for tr in BeautifulSoup(html, 'html.parser').select('tr'):
        cells = [td.get_text(' ', strip=True) for td in tr.select('td')]
        for i, cell in enumerate(cells):
            if cell != '2688' or i < 2 or i + 2 >= len(cells):
                continue
            s1, s2, ring, t = cells[i-2:i] + cells[i+1:i+3]
            if not (re.fullmatch(r'\d{1,4}', s1) and re.fullmatch(r'\d{1,4}', s2)
                    and re.fullmatch(r'\d{1,4}', ring)
                    and re.fullmatch(r'\d{1,2}:\d{2}:\d{2}(?:\.\d+)?', t)):
                continue
            ring = ring.zfill(2)
            if eligible is not None and ring not in eligible:
                continue
            stamp = seconds(t)
            if ring not in by_ring or stamp < by_ring[ring]['_seconds']:
                by_ring[ring] = {'ring': ring, 'return_time': t, '_seconds': stamp,
                                 'loft': '2688', 'source_serial1': int(s1), 'source_serial2': int(s2)}
    rows = sorted(by_ring.values(), key=lambda row: row['_seconds'])
    for rank, row in enumerate(rows, 1):
        row['serial1'] = rank
        row['serial2'] = rank
        del row['_seconds']
    return rows


def extract_meta(html):
    body = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
    place = re.search(r'施放(?:地點|地)\s*[:：]?\s*([^\s　]+)', body)
    time = re.search(r'施放時間\s*[:：]?\s*(\d{1,2}:\d{2}(?::\d{2})?)', body)
    return place.group(1) if place else '', time.group(1) if time else ''


@app.get('/')
def home():
    return send_from_directory('.', 'index.html')


@app.get('/health')
def health():
    return {'ok': True}


@app.get('/api/topigeon')
def topigeon():
    date = request.args.get('date', '').strip().replace('-', '/')
    password = request.args.get('pass', '').strip()
    try:
        datetime.strptime(date, '%Y/%m/%d')
    except ValueError:
        return jsonify(error='日期格式需為 YYYY/MM/DD'), 400
    # Optional comma-separated participant list; UI supplies this from roster.
    participants = request.args.get('participants', '').strip()
    eligible = None
    if participants:
        eligible = {x.zfill(2) for x in participants.split(',') if re.fullmatch(r'\d{1,4}', x)}
        if not eligible:
            return jsonify(error='參訓名單格式不正確'), 400
    payload = {'QSysid': '1606', 'QMode': 'train', 'QRaceDate': date,
               'QSite': '2688', 'QSiteCode': '2688', 'QSort': '1',
               'qsize': '1000', 'QPass': password, 'p': 'N'}
    try:
        with requests.Session() as session:
            session.headers.update(HEAD)
            session.get(TOP, timeout=20)
            response = session.post(TOP, data=payload, timeout=30)
            response.raise_for_status()
            html = decode(response)
        rows = parse_rows(html, eligible)
        place, release_time = extract_meta(html)
        if not rows:
            diagnostic = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)[:500]
            return jsonify(error='TOPIGEON 有回應，但沒有符合條件的 2688 紀錄', diagnostic=diagnostic), 404
        raw = '\n'.join(f"{r['serial1']} {r['serial2']} 2688 {r['ring']} {r['return_time']}" for r in rows)
        return jsonify(date=date, count=len(rows), rows=rows, raw_text=raw,
                       release_place=place, release_time=release_time,
                       filter='first_return_per_eligible_ring_any_hour',
                       warning=('未提供參訓名單，下午首次出現的家飛鴿可能混入，請人工核對。'
                                if eligible is None else '依參訓名單篩選；請確認參訓勾選正確。'))
    except requests.RequestException as exc:
        return jsonify(error='連線 TOPIGEON 失敗', detail=str(exc)), 502


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

@app.get('/history.json')
def history_file():
    return send_from_directory('.', 'history.json')
