#!/usr/bin/env python3
"""日文研 IIIF から指定した頁の画像をダウンロードする（並列・黒ブロック検出と分割再取得つき）。

日文研 IIIF 的 full 大图偶尔会整块变黑（服务器渲染不完整）。
检测到黑块时，改为按 tile 分块请求，再在本地拼合。

页码按图像文件名里的编号（例如 tenb_1_0012.tif → 12，与山田正解的 P 12 对应）；
目録（moku）、奥付（oku）等不带纯数字编号的图像会跳过。

用法:
    python fetch_iiif_pages.py --manifest https://iiif.nichibun.ac.jp/IIIF/manifest/KJZ/jinb_1.json \
        --start 1 --end 100 --out /workspace/test_images_all [--workers 6]
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

TILE = 512
BLACK_LEVEL = 16        # 灰度 <= 此值视为黑
BLACK_BLOCK_RATIO = 0.6  # 某个格子里黑像素占比超过此值视为黑块（纸面不会这么黑）
GRID = 8
UA = {'User-Agent': 'Mozilla/5.0 (kojiruien-tagger research)'}  # 日文研会拒绝 Python 默认 UA（403）


def fetch(url, retries=4):
    req = urllib.request.Request(url, headers=UA)
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            print(f'    retry {i + 1}: {e}', file=sys.stderr)
            time.sleep(2 * (i + 1))


def has_black_block(img):
    g = img.convert('L')
    w, h = g.size
    for gy in range(GRID):
        for gx in range(GRID):
            box = (gx * w // GRID, gy * h // GRID, (gx + 1) * w // GRID, (gy + 1) * h // GRID)
            hist = g.crop(box).histogram()
            if sum(hist[:BLACK_LEVEL + 1]) / max(1, sum(hist)) > BLACK_BLOCK_RATIO:
                return True
    return False


def fetch_tiled(service, w, h):
    canvas = Image.new('RGB', (w, h), 'white')
    for y in range(0, h, TILE):
        for x in range(0, w, TILE):
            tw, th = min(TILE, w - x), min(TILE, h - y)
            data = fetch(f'{service}/{x},{y},{tw},{th}/full/0/default.jpg')
            canvas.paste(Image.open(io.BytesIO(data)).convert('RGB'), (x, y))
    return canvas


def page_number(canvas):
    """图像文件名里的页码；目録・奥付等返回 None。"""
    rid = canvas['images'][0]['resource']['@id']
    m = re.search(r'/([a-z]+_\d+)_(\d+)\.tif', rid)
    return int(m.group(2)) if m else None


def download(c, n, out):
    res = c['images'][0]['resource']
    service = res['service']['@id'] if 'service' in res else res['@id'].split('/full/')[0]
    w, h = int(c['width']), int(c['height'])
    name = os.path.join(out, f'{n:04d}.jpg')
    if os.path.exists(name):
        return None
    img = Image.open(io.BytesIO(fetch(f'{service}/full/full/0/default.jpg'))).convert('RGB')
    note = ''
    if img.size != (w, h) or has_black_block(img):
        img = fetch_tiled(service, w, h)
        note = '  （黒ブロック／サイズ異常 → 分割して再取得）'
    img.save(name, quality=95)
    return f'{n:04d} {img.size}{note}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--start', type=int, required=True, help='页码（图像文件名编号）起')
    ap.add_argument('--end', type=int, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=6, help='并发数（别太大，避免给日文研服务器添负担）')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    m = json.loads(fetch(args.manifest))
    todo = [(c, n) for c in m['sequences'][0]['canvases']
            if (n := page_number(c)) is not None and args.start <= n <= args.end]
    print(f'{len(todo)} 頁をダウンロード → {args.out}', flush=True)
    done = 0
    with ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(download, c, n, args.out) for c, n in todo]
        for f in as_completed(futs):
            msg = f.result()
            done += 1
            if msg and ('黒ブロック' in msg or done % 50 == 0):
                print(f'[{done}/{len(todo)}] {msg}', flush=True)
    print(f'✅ {done} 頁 完了', flush=True)


if __name__ == '__main__':
    main()
