#!/usr/bin/env python3
"""NDLOCR ver.2.1 で 1 つのフォルダ（中に img/ がある）を OCR する。

    python ocr_one.py <入力フォルダ> <出力フォルダ> --ckpt <レイアウトモデル.pth> [--thr 0.3]
結果：<出力フォルダ>/<入力フォルダ名>/xml/<入力フォルダ名>.sorted.xml
"""
import argparse
import os
import shutil
import sys

ap = argparse.ArgumentParser()
ap.add_argument('in_dir')
ap.add_argument('out_dir')
ap.add_argument('--ckpt', required=True)
ap.add_argument('--thr', type=float, default=0.3)
ap.add_argument('--ndlocr', default='/workspace/full_package/ndlocr_cli')
a = ap.parse_args()

sys.path.insert(0, a.ndlocr)
os.chdir(a.ndlocr)
from cli.core.utils import parse_cfg  # noqa: E402
from cli.core.inference import OcrInferrer  # noqa: E402

shutil.rmtree(a.out_dir, ignore_errors=True)
os.makedirs(a.out_dir)
cfg = parse_cfg({'config_file': f'{a.ndlocr}/config.yml', 'input_root': a.in_dir, 'output_root': a.out_dir,
                 'proc_range': '0..3', 'save_image': False, 'save_xml': True, 'input_structure': 's',
                 'dump': False, 'ruby_only': False, 'ruby_read': False, 'partial_infer': False, 'line_order': True})
cfg['layout_extraction']['checkpoint_path'] = a.ckpt
cfg['layout_extraction']['config_path'] = (f'{a.ndlocr}/submodules/ndl_layout/models/'
                                           'cascade_mask_rcnn_convnext-t_p4_w7_fpn_giou_4conv1f_fp16_ms-crop_3x_coco.py')
cfg['layout_extraction']['device'] = 'cuda:0'
cfg['layout_extraction']['score_thr'] = a.thr
OcrInferrer(cfg).run()
print('DONE', a.in_dir, flush=True)
