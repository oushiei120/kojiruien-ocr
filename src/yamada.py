"""山田格式（shikibetsu_raw）的读取与字符级展开。

把一份山田格式文本拆成「页 → 字符序列」，每个字符带上：
  tag  : 所属记录的行标签（A/B/C/G/V/N/H/W/M/X…）。页首无标签的续行继承前一条记录的标签
  wari : 是否在 <wari>…</wari> 里

评测时比较的「文字」规则：
  - 去掉 <ruby> 的 <rt>（注音），保留 <rb>
  - 去掉返り点【K…】、<br />、空白
  - 外字 <tmc …/> 统一成 〓（OCR 也输出 〓）
"""
import re
from dataclasses import dataclass, field

LINE_TAG = re.compile(r'^([A-Z]) (.*)$')
PAGE = re.compile(r'^P (\d+)\s*$')
INLINE = re.compile(r'(<wari>|</wari>|<ruby>|</ruby>|<rb>|</rb>|<rt>|</rt>|<br\s*/>|<tmc[^>]*/>|【K[^】]*】|<[^>]+>)')


@dataclass
class Record:
    tag: str          # 行标签；页首续行为 ''
    raw: str          # 去掉标签后的原始内容（含行内标记）


@dataclass
class Page:
    number: int
    records: list = field(default_factory=list)
    chars: list = field(default_factory=list)   # [(ch, tag, wari)]

    @property
    def text(self):
        return ''.join(c for c, _, _ in self.chars)


def parse(text):
    """山田格式文本 → {页码: Page}。跨页的 <wari> 状态、续行标签都会延续。"""
    pages = {}
    page = None
    last_tag = ''
    in_wari = False
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        m = PAGE.match(line)
        if m:
            page = pages.setdefault(int(m.group(1)), Page(int(m.group(1))))
            continue
        if page is None:
            continue
        m = LINE_TAG.match(line)
        if m:
            tag, body = m.group(1), m.group(2)
            last_tag = tag
            # 新记录开始时，上一条没闭合的 <wari> 视为结束
            in_wari = False
        else:
            tag, body = '', line
        page.records.append(Record(tag, body))
        eff = tag or last_tag
        in_rt = False
        for tok in INLINE.split(body):
            if not tok:
                continue
            if tok == '<wari>':
                in_wari = True
            elif tok == '</wari>':
                in_wari = False
            elif tok == '<rt>':
                in_rt = True
            elif tok == '</rt>':
                in_rt = False
            elif tok.startswith('<tmc'):
                page.chars.append(('〓', eff, in_wari))
            elif INLINE.fullmatch(tok):
                continue
            elif not in_rt:
                for ch in tok:
                    if not ch.isspace():
                        page.chars.append((ch, eff, in_wari))
    return pages


def read(path):
    with open(path, encoding='utf-8') as f:
        return parse(f.read())
