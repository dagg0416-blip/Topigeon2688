from flask import Flask, request, jsonify, send_from_directory
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime

app = Flask(__name__, static_folder='.')

TOP = 'https://www.topigeon.com.tw/index.asp'

HEAD = {
    'User-Agent': (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) '
        'Version/18.0 Mobile/15E148 Safari/604.1'
    ),
    'Referer': 'https://www.topigeon.com.tw/index.asp'
}


def txt(resp):
    """處理 TOPIGEON 舊網站中文字編碼"""
    enc = resp.encoding

    if not enc or enc.lower() in ('iso-8859-1', 'ascii'):
        enc = resp.apparent_encoding or 'big5'

    try:
        return resp.content.decode(enc, errors='replace')
    except Exception:
        return resp.content.decode('big5', errors='replace')


def time_seconds(t):
    """把 HH:MM:SS.xxx 轉成秒數"""
    try:
        p = t.split(':')
        return (
            int(p[0]) * 3600
            + int(p[1]) * 60
            + float(p[2])
        )
    except Exception:
        return None


def parse_rows(html):
    """
    解析 2688 歸返資料。

    重點：
    TOPIGEON 同一天可能同時出現：
    - 早上外訓 / 自訓
    - 下午家飛

    2688 分析只保留早上的自訓資料。
    """

    soup = BeautifulSoup(html, 'html.parser')
    rows = []

    # 格式：
    # 序號1 / 序號2 / 鴿舍 / 環號 / 飛返時間
    pattern = re.compile(
        r'^\d{1,4}$'
    )

    for tr in soup.select('tr'):
        cells = [
            x.get_text(' ', strip=True)
            for x in tr.select('td')
        ]

        if len(cells) < 5:
            continue

        # 嘗試在這一列中找 2688
        try:
            loft_index = cells.index('2688')
        except ValueError:
            continue

        # 2688 前面至少需要兩個序號
        # 後面需要環號與時間
        if loft_index < 2 or loft_index + 2 >= len(cells):
            continue

        serial1 = cells[loft_index - 2].strip()
        serial2 = cells[loft_index - 1].strip()
        ring = cells[loft_index + 1].strip()
        return_time = cells[loft_index + 2].strip()

        if not pattern.match(serial1):
            continue

        if not pattern.match(serial2):
            continue

        if not re.match(
            r'^\d{1,2}:\d{2}:\d{2}(?:\.\d+)?$',
            return_time
        ):
            continue

        seconds = time_seconds(return_time)

        if seconds is None:
            continue

        rows.append({
            'serial1': int(serial1),
            'serial2': int(serial2),
            'loft': '2688',
            'ring': ring.zfill(2),
            'return_time': return_time,
            '_seconds': seconds
        })

    # -----------------------------
    # 去除完全重複紀錄
    # -----------------------------

    unique = {}

    for row in rows:
        key = (
            row['ring'],
            row['return_time']
        )

        if key not in unique:
            unique[key] = row

    rows = list(unique.values())

    # -----------------------------
    # 排除下午家飛
    #
    # 目前 2688 的使用需求：
    # 下午家飛不納入分析。
    #
    # 12:00 後的歸返紀錄先排除。
    # -----------------------------

    morning_rows = [
        r for r in rows
        if r['_seconds'] < 12 * 3600
    ]

    # 如果確實有早上紀錄，就採用早上這一批。
    # 若某天完全沒有早上資料，不硬刪，
    # 讓 API 回傳原始資料供診斷。
    if morning_rows:
        rows = morning_rows

    # 同一羽若出現多次，只保留最早歸返
    by_ring = {}

    for row in rows:
        ring = row['ring']

        if (
            ring not in by_ring
            or row['_seconds'] < by_ring[ring]['_seconds']
        ):
            by_ring[ring] = row

    rows = list(by_ring.values())

    # 依歸返時間，由早到晚
    rows.sort(key=lambda x: x['_seconds'])

    # 重新建立名次
    for i, row in enumerate(rows, start=1):
        row['serial1'] = i
        row['serial2'] = i
        row.pop('_seconds', None)

    return rows


def extract_meta(html):
    """嘗試取得施放地點與施放時間"""

    soup = BeautifulSoup(html, 'html.parser')
    body = soup.get_text(' ', strip=True)

    release_place = ''
    release_time = ''

    place_patterns = [
        r'施放地點\s*[:：]?\s*([^\s　]+)',
        r'施放地\s*[:：]?\s*([^\s　]+)',
    ]

    for pat in place_patterns:
        m = re.search(pat, body)
        if m:
            release_place = m.group(1).strip()
            break

    m = re.search(
        r'施放時間\s*[:：]?\s*(\d{1,2}:\d{2}(?::\d{2})?)',
        body
    )

    if m:
        release_time = m.group(1)

    return release_place, release_time


@app.get('/')
def home():
    return send_from_directory('.', 'index.html')


@app.get('/health')
def health():
    return {'ok': True}


@app.get('/api/topigeon')
def topigeon():

    date = (
        request.args.get('date', '')
        .strip()
        .replace('-', '/')
    )

    passwd = request.args.get('pass', '').strip()

    try:
        datetime.strptime(date, '%Y/%m/%d')
    except Exception:
        return jsonify(
            error='日期格式需為 YYYY/MM/DD'
        ), 400

    # TOPIGEON 查詢條件
    data = {
        'QSysid': '1606',
        'QMode': 'train',
        'QRaceDate': date,
        'QSite': '2688',
        'QSiteCode': '2688',
        'QSort': '1',
        'qsize': '1000',
        'QPass': passwd,
        'p': 'N'
    }

    try:

        with requests.Session() as s:

            s.headers.update(HEAD)

            # 先進首頁取得 Cookie / Session
            s.get(
                TOP,
                timeout=20
            )

            # 再送查詢
            r = s.post(
                TOP,
                data=data,
                timeout=30
            )

            r.raise_for_status()

            html = txt(r)

        rows = parse_rows(html)

        place, rtime = extract_meta(html)

        if not rows:

            soup = BeautifulSoup(
                html,
                'html.parser'
            )

            page = soup.get_text(
                ' ',
                strip=True
            )[:800]

            return jsonify(
                error=(
                    'TOPIGEON 有回應，但沒有解析到 '
                    '2688 的早上自訓紀錄。'
                ),
                diagnostic=page
            ), 404

        raw = '\n'.join(
            f"{x['serial1']} "
            f"{x['serial2']} "
            f"2688 "
            f"{x['ring']} "
            f"{x['return_time']}"
            for x in rows
        )

        return jsonify(
            date=date,
            count=len(rows),
            rows=rows,
            raw_text=raw,
            release_place=place,
            release_time=rtime,
            filter='morning_training_only'
        )

    except requests.RequestException as e:

        return jsonify(
            error='連線 TOPIGEON 失敗',
            detail=str(e)
        ), 502


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=8080
    )
