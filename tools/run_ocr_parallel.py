#!/usr/bin/env python3
"""1 冊分の画像を分割し、GPU 1 枚あたり N 個の OCR を同時に動かして（GPU が複数あれば全部使う）、結果の XML を 1 つにまとめる。

    python run_ocr_parallel.py <画像フォルダ> <作業フォルダ> <出力XML> --ckpt <モデル.pth> [--per-gpu 3]
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument('img_dir')
ap.add_argument('work_dir')
ap.add_argument('out_xml')
ap.add_argument('--ckpt', required=True)
ap.add_argument('--per-gpu', type=int, default=3, help='GPU 1 枚あたりの同時 OCR 数')
ap.add_argument('--thr', type=float, default=0.3)
ap.add_argument('--poll', type=int, default=30, help='進捗表示の間隔（秒）')
a = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
try:
    ngpu = len(subprocess.run(['nvidia-smi', '-L'], capture_output=True, text=True).stdout.strip().splitlines())
except OSError:
    ngpu = 0
ngpu = max(1, ngpu)
parts = a.per_gpu * ngpu
imgs = sorted(f for f in os.listdir(a.img_dir) if f.lower().endswith('.jpg'))
n = (len(imgs) + parts - 1) // parts
procs = []
for i in range(parts):
    chunk = imgs[i * n:(i + 1) * n]
    if not chunk:
        continue
    part = os.path.join(a.work_dir, f'p{i}')
    os.makedirs(os.path.join(part, 'img'), exist_ok=True)
    for f in chunk:
        dst = os.path.join(part, 'img', f)
        if not os.path.exists(dst):
            os.symlink(os.path.abspath(os.path.join(a.img_dir, f)), dst)
    total = len(os.listdir(os.path.join(part, 'img')))
    log = open(os.path.join(a.work_dir, f'ocr_p{i}.log'), 'w')
    p = subprocess.Popen([sys.executable, '-u', os.path.join(here, 'ocr_one.py'), part,
                          os.path.join(a.work_dir, f'out{i}'), '--ckpt', a.ckpt, '--thr', str(a.thr)],
                         stdout=log, stderr=subprocess.STDOUT,
                         env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(i % ngpu)))
    procs.append((p, log.name, total))
print(f'{len(imgs)} 頁を GPU {ngpu} 枚 × {a.per_gpu} = {len(procs)} 分割して OCR を開始', flush=True)


def done_pages(logname):
    try:
        return open(logname, encoding='utf-8', errors='ignore').read().count('END PAGE INFERENCE')
    except OSError:
        return 0


while True:
    time.sleep(a.poll)
    states = [p.poll() for p, _, _ in procs]
    done = sum(done_pages(l) for _, l, _ in procs)
    print(f'  {time.strftime("%H:%M")}  {done} / {len(imgs)} 頁', flush=True)
    for (p, l, _), s in zip(procs, states):
        if s not in (None, 0):
            print(f'❌ OCR が失敗しました（{l}）。最後の部分：', flush=True)
            print(open(l, encoding='utf-8', errors='ignore').read()[-3000:])
            for q, _, _ in procs:
                q.kill()
            sys.exit(1)
    if all(s == 0 for s in states):
        break

pages = []
for f in sorted(glob.glob(os.path.join(a.work_dir, 'out*', 'p*', 'xml', '*.sorted.xml'))):
    pages += re.findall(r'<PAGE\b.*?</PAGE>', open(f, encoding='utf-8').read(), re.S)
pages.sort(key=lambda p: re.search(r'IMAGENAME="([^"]+)"', p).group(1))
with open(a.out_xml, 'w', encoding='utf-8') as f:
    f.write("<?xml version='1.0' encoding='utf-8'?>\n<OCRDATASET>" + '\n'.join(pages) + '</OCRDATASET>\n')
print(f'✅ {len(pages)} 頁 → {a.out_xml}', flush=True)
