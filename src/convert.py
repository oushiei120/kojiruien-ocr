#!/usr/bin/env python3
"""NDLOCR 2.1 sorted.xml → 山田格式（shikibetsu_raw）规则转换器 v1。

用法:
    python src/convert.py data/eval_jinbu1/v4.sorted.xml -o output/jinbu1_v4.txt [--page-offset 0]

每页的处理顺序：
  1. 去掉柱、页码、版心外的行；同一列里重叠的重复行框去重
  2. 按 x 坐标把 本文 / 割注 聚成列（右→左），列内按 y 排序
     割注按左右两小列配对：先右后左
  3. 版框上方的頭注 → C（插在它正下方那一列之前）
  4. 解析：〔書名 + 割注(編目) + 〕本文
       〔 顶格 → V/N/H；低一格 → W/M/X
     大字行 → A（…部…）/ B；A/B 之后不带〔的正文 → G
     页首在任何新记录之前的内容 → 无标签续行
"""
import argparse
import collections
import json
import os
import re
import statistics
import sys

from rapidfuzz.distance import Levenshtein

sys.path.insert(0, os.path.dirname(__file__))
import ndlxml  # noqa: E402

TEXT_TYPES = {'本文', '割注'}
OPEN, CLOSE = '〔', '〕'
A_PAT = re.compile(r'^.{1,4}部[一二三四五六七八九十]*$')
SKIP_TITLES = {'古事類苑'}


# ---------------------------------------------------------------- 预处理

def overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def dedupe(lines):
    """同一小列里纵向重叠的行：被其他行覆盖 ≥80% 且置信度不更高的删掉；
    剩下仍重叠的，把下面那行开头重叠部分的字去掉。"""
    keep = sorted(lines, key=lambda b: b.conf)
    removed = set()
    for i, b in enumerate(keep):
        others = [o for j, o in enumerate(keep) if j != i and j not in removed and abs(o.cx - b.cx) < b.w * 0.6]
        ivs = sorted((max(o.y, b.y), min(o.y1, b.y1)) for o in others if overlap(o.y, o.y1, b.y, b.y1) > 0)
        cov, cur = 0, b.y
        for s, e in ivs:
            s = max(s, cur)
            if e > s:
                cov += e - s
                cur = e
        if b.h and cov / b.h >= 0.8 and all(o.conf >= b.conf for o in others
                                            if overlap(o.y, o.y1, b.y, b.y1) > 0):
            removed.add(i)
    out = sorted((b for i, b in enumerate(keep) if i not in removed), key=lambda b: b.y)
    res = []
    for b in out:
        if res and abs(res[-1].cx - b.cx) < b.w * 0.6:
            ov = overlap(res[-1].y, res[-1].y1, b.y, b.y1)
            if ov > 0 and b.text:
                pitch = b.h / max(1, len(b.text))
                k = int(round(ov / pitch))
                if k >= len(b.text):
                    continue
                b = ndlxml.Box(b.kind, b.type, b.x, b.y + ov, b.w, b.h - ov, b.conf, b.text[k:])
        res.append(b)
    return res


def cluster_columns(boxes, gap):
    """按中心 x 单链聚类；返回从右到左的列（每列是 box 列表）。"""
    boxes = sorted(boxes, key=lambda b: -b.cx)
    cols, cur, last = [], [], None
    for b in boxes:
        if last is not None and last - b.cx > gap:
            cols.append(cur)
            cur = []
        cur.append(b)
        last = b.cx
    if cur:
        cols.append(cur)
    return cols


# ---------------------------------------------------------------- 一页 → 列 → 条目

class Item:
    """列内的一个条目：本文行 或 割注段（右小列文字, 左小列文字）。"""

    def __init__(self, kind, y0, y1, text='', right='', left='', w=0):
        self.kind, self.y0, self.y1, self.w = kind, y0, y1, w
        self.text, self.right, self.left = text, right, left

    def wari_text(self, sep=''):
        return self.right + (sep if self.right and self.left else '') + self.left


def column_items(col):
    mains = dedupe([b for b in col if b.type == '本文'])
    waris = [b for b in col if b.type == '割注']
    if mains:
        center = statistics.median(b.cx for b in mains)
    elif waris:
        center = statistics.mean(b.cx for b in waris)
    else:
        center = 0
    right = dedupe([b for b in waris if b.cx >= center])
    left = dedupe([b for b in waris if b.cx < center])
    items = [Item('main', b.y, b.y1, text=b.text, w=b.w) for b in mains if b.text]

    # 割注段：左右小列的行按 y 区间合并（中间被本文行隔开的就是不同的段）
    segs = []
    for side, bs in (('r', right), ('l', left)):
        for b in bs:
            segs.append([b.y, b.y1, [(side, b)]])
    segs.sort(key=lambda s: s[0])
    merged = []
    for s in segs:
        if merged and s[0] <= merged[-1][1] + 20:
            merged[-1][1] = max(merged[-1][1], s[1])
            merged[-1][2].extend(s[2])
        else:
            merged.append(s)
    for y0, y1, parts in merged:
        r = ''.join(b.text for side, b in sorted(parts, key=lambda p: p[1].y) if side == 'r')
        l = ''.join(b.text for side, b in sorted(parts, key=lambda p: p[1].y) if side == 'l')
        if r or l:
            items.append(Item('wari', y0, y1, right=r, left=l))
    items.sort(key=lambda it: it.y0)
    return items, center


def page_layout(page):
    W = page.width or 2150
    text = [b for b in page.boxes if b.kind == 'LINE' and b.type in TEXT_TYPES and b.text.strip()]
    # 版心外（柱、页码一带）的行去掉
    text = [b for b in text if 0.08 * W < b.cx < 0.92 * W]
    if not text:
        return [], None
    mains = [b for b in text if b.type == '本文']
    char_w = statistics.median(b.w for b in mains) if mains else 46
    cols = cluster_columns(text, gap=max(30, char_w * 0.85))
    columns = []
    for col in cols:
        items, center = column_items(col)
        if items:
            widths = [b.w for b in col if b.type == '本文']
            columns.append({'items': items, 'cx': center, 'y0': items[0].y0,
                            'wide': bool(widths) and max(widths) > char_w * 1.3, 'heads': []})
    if not columns:
        return [], None
    starts = sorted(c['y0'] for c in columns)
    top = starts[max(0, len(starts) // 20)]
    # 版框上方的頭注 → C，挂到 x 最近的列
    heads = [b for b in page.boxes if b.kind == 'LINE' and b.type == '頭注' and b.text.strip() and b.y1 < top]
    seen = []
    for h in sorted(heads, key=lambda b: -b.conf):
        if any(overlap(h.x, h.x1, s.x, s.x1) > 0 and overlap(h.y, h.y1, s.y, s.y1) > 0 for s in seen):
            continue
        seen.append(h)
        col = min(columns, key=lambda c: abs(c['cx'] - h.cx))
        col['heads'].append(h)
    return columns, {'top': top, 'char': char_w}


# ---------------------------------------------------------------- 书名词典

CLOSERS = '〕」）)〓]'          # OCR 常把〕认成这些
NOISE = '・、。，,.〓「」『』乙　 '
HEN_ONLY = re.compile(r'^[一二三四五六七八九十百上中下前後編]+$')
EDIT_NOTES = {'○中': '○中略', '○下': '○下略', '○上': '○上略', '○註': '○註略', '○原註': '○原註略'}
MAX_NAME = 12


def clean(t):
    return t.strip(NOISE)


class Lexicon:
    def __init__(self, path):
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        self.books = d['books']
        self.hen = d.get('hen', {})
        self.maxlen = max(map(len, self.books))
        self.by_len = collections.defaultdict(list)
        for b in self.books:
            self.by_len[len(b)].append(b)

    def longest_prefix(self, text, minlen=2):
        for k in range(min(len(text), self.maxlen), minlen - 1, -1):
            if text[:k] in self.books:
                return text[:k], text[k:]
        return None, text

    def fix(self, name):
        """不在词典里、但和某个书名只差 1 个字的，改成那个书名（同距离取出现次数多的）。"""
        if name in self.books or len(name) < 3:
            return name
        best = None
        for L in (len(name), len(name) - 1, len(name) + 1):
            for b in self.by_len.get(L, ()):
                if Levenshtein.distance(name, b, score_cutoff=1) <= 1:
                    if best is None or self.books[b] > self.books[best]:
                        best = b
        return best or name

    def fix_hen(self, name, parts):
        """用「同一本书出现过的編目」补全/纠正：只认出左列时补右列（男女 → 二/男女），差 1 个字的纠正。"""
        hv = self.hen.get(name)
        if not hv or not parts:
            return parts
        joined = '/'.join(parts)
        if joined in hv:
            return parts
        if len(parts) == 1:
            cands = [h for h in hv if h.split('/')[-1] == parts[0]]
        else:
            cands = [h for h in hv if Levenshtein.distance(joined, h, score_cutoff=1) <= 1]
        if not cands:
            return parts
        return max(cands, key=lambda h: hv[h]).split('/')


# ---------------------------------------------------------------- 解析成记录

class Converter:
    def __init__(self, lexicon=None):
        self.lex = lexicon
        self.lines = []          # 输出行
        self.rec = None          # 当前记录 [tag, text]
        self.block = None        # 'V' / 'W' / 'G' / None
        self.state = None        # 'pre' / 'name' / 'hen' / 'body'
        self.name = ''
        self.hen = []

    # 记录操作
    def flush(self):
        if self.rec is not None:
            tag, text = self.rec
            if text:
                self.lines.append(f'{tag} {text}' if tag else text)
            self.rec = None

    def start(self, tag, text=''):
        self.flush()
        self.rec = [tag, text]

    def add(self, text):
        if self.rec is None:
            self.rec = ['', '']          # 页首续行
        self.rec[1] += text

    # 引用
    def open_citation(self, block, text):
        self.flush()
        self.block, self.state, self.name, self.hen = block, 'name', '', []
        self.name_text(text)

    def name_text(self, text):
        """书名状态下来了一段本文。"""
        j = next((k for k, c in enumerate(text) if c in CLOSERS), -1)
        if j != -1 and len(self.name) + j <= MAX_NAME + 3:
            self.name += text[:j]
            self.close_name(text[j + 1:])
            return
        if self.lex and clean(self.name) in self.lex.books:
            self.close_name(text)      # 书名已经完整，这段是正文（〕没认出来）
            return
        room = MAX_NAME - len(self.name)
        if len(text) <= room:
            self.name += text
        else:
            self.name += text
            self.close_name('')

    def close_name(self, carry=''):
        name, hen = clean(self.name), [clean(h) for h in self.hen if clean(h)]
        if self.lex and name not in self.lex.books:
            pre, rest = self.lex.longest_prefix(name)
            if pre and rest:
                if not hen and HEN_ONLY.match(rest):
                    name, hen = pre, [rest]          # 书名后粘上的卷数 → 編目
                elif len(pre) >= 3:
                    name, carry = pre, rest + carry  # 书名后粘上的正文
            name = self.lex.fix(name)
        if self.lex:
            hen = self.lex.fix_hen(name, hen)
        name_tag = self.block if self.block in ('V', 'W') else 'V'
        self.flush()
        self.lines.append(f'{name_tag} {name}')
        if hen:
            self.lines.append(('N ' if name_tag == 'V' else 'M ') + '/'.join(hen))
        self.state, self.name, self.hen = 'body', '', []
        self.rec = ['H' if name_tag == 'V' else 'X', carry]

    # 主流程
    def page(self, number, columns, geo):
        if self.state in ('name', 'hen'):
            self.close_name()
        self.flush()
        self.lines.append(f'P {number}')
        if not columns:
            return
        top, ch = geo['top'], geo['char']
        self.char_w = ch
        for col in columns:
            for h in col['heads']:
                if self.state in ('name', 'hen'):
                    self.close_name()
                self.start('C', h.text)
                self.flush()
                self.block, self.state = None, None
            for k, it in enumerate(col['items']):
                level = ((col['y0'] if k == 0 else it.y0) - top) / ch
                if it.kind == 'main':
                    self.main(it.text, col, level, first=k == 0, w=it.w)
                else:
                    self.wari(it)
        if self.state in ('name', 'hen'):
            self.close_name()
        self.flush()

    def main(self, text, col, level, first, w=0):
        t = text.strip()
        # 部名・門名：这一行本身是大字（宽），而且很短
        if first and w > self.char_w * 1.3 and len(t) <= 8:
            if t in SKIP_TITLES:
                return
            if self.state in ('name', 'hen'):
                self.close_name()
            self.start('A' if A_PAT.match(t) else 'B', t)
            self.flush()
            self.block, self.state = 'G', 'pre'
            return
        i = text.find(OPEN)
        if 0 <= i <= 1:
            if self.state in ('name', 'hen'):
                self.close_name()
            if level > 2.5:
                # 从一列中间开始的引用（如紧接短引用的「〔同」）：位置不是缩进，沿用上一条引用的类型
                blk = getattr(self, 'last_block', None) or 'V'
            else:
                blk = 'V' if level < 0.75 else 'W'
            self.last_block = blk
            self.open_citation(blk, text[i + 1:])
            return
        if self.state == 'name':
            self.name_text(text)
            return
        if self.state == 'hen':
            j = next((k for k, c in enumerate(text[:2]) if c in CLOSERS), -1)
            self.close_name(text[j + 1:] if j != -1 else text)
            return
        if self.block == 'G' and self.state == 'pre':
            self.start('G', text)
            self.state = 'body'
            return
        self.add(text)

    def wari(self, it):
        if self.state == 'name' and self.name:
            self.state = 'hen'
            self.hen.append(it.wari_text('/'))
            return
        if self.state in ('name', 'hen'):
            self.close_name()
        t = it.wari_text()
        t = EDIT_NOTES.get(t, t)
        self.add('<wari>' + t + '</wari>')


def convert(xml_path, page_offset=0, lexicon=None):
    conv = Converter(Lexicon(lexicon) if lexicon else None)
    for page in ndlxml.read(xml_path):
        columns, geo = page_layout(page)
        conv.page(page.index + page_offset, columns, geo)
    if conv.state in ('name', 'hen'):
        conv.close_name()
    conv.flush()
    return '\n'.join(conv.lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xml')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--page-offset', type=int, default=0, help='页码 = 图像序号 + offset')
    ap.add_argument('--lexicon', help='书名词典 JSON（src/lexicon.py 生成；评测时要排除测试集所在文件）')
    args = ap.parse_args()
    out = convert(args.xml, args.page_offset, args.lexicon)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'→ {args.out}')


if __name__ == '__main__':
    main()
