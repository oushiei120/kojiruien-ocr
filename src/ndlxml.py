"""NDLOCR 2.1 的 sorted.xml 读取。

结构是扁平的：<OCRDATASET><PAGE …> 下面直接是 <LINE …/> 和 <BLOCK …/>。
LINE 的 TYPE：本文 / 割注 / 頭注 …；BLOCK 的 TYPE：柱 / ノンブル / ルビ / 図版 …
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class Box:
    kind: str      # 'LINE' or 'BLOCK'
    type: str
    x: int
    y: int
    w: int
    h: int
    conf: float
    text: str

    @property
    def x1(self):
        return self.x + self.w

    @property
    def y1(self):
        return self.y + self.h

    @property
    def cx(self):
        return self.x + self.w / 2


@dataclass
class OcrPage:
    image: str      # 例如 0001_L.jpg
    width: int
    height: int
    boxes: list

    @property
    def index(self):
        """图像序号（文件名开头的数字）。"""
        m = re.match(r'(\d+)', self.image)
        return int(m.group(1)) if m else None


def read(path):
    root = ET.parse(path).getroot()
    pages = []
    for p in root.iter('PAGE'):
        boxes = []
        for el in p.iter():  # base 模型的输出会把部分 LINE 包在 TEXTBLOCK 里
            if el.tag not in ('LINE', 'BLOCK'):
                continue
            a = el.attrib
            try:
                boxes.append(Box(el.tag, a.get('TYPE', ''), int(a['X']), int(a['Y']), int(a['WIDTH']),
                                 int(a['HEIGHT']), float(a.get('CONF', 1) or 1), a.get('STRING', '')))
            except (KeyError, ValueError):
                continue
        pages.append(OcrPage(p.get('IMAGENAME', ''), int(p.get('WIDTH', 0)), int(p.get('HEIGHT', 0)), boxes))
    return pages
