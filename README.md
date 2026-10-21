# 古事類苑 OCR（v5b モデル）実行手順

日文研 IIIF の『古事類苑』画像を OCR し、**山田形式**（識別タグ付きテキスト）に変換します。RunPod（クラウド GPU）でノートブックを実行するだけです。

- 目安：1 冊 約 1 時間、約 1 ドル（RTX 4090）
- 対照ビューア：https://oushiei120.github.io/kojiruien-ocr-viewer/

---

## 1. テンプレートを作る（初回のみ）

https://www.runpod.io でアカウントを作り、**Billing** でクレジット（10 ドル程度）を追加します。
**Templates → New Template** で次のように入力して保存します。

| 項目 | 値 |
|---|---|
| Container image | `runpod/pytorch:2.1.1-py3.10-cuda12.1.1-devel-ubuntu22.04` |
| Container disk / Volume disk | 50 GB / 50 GB |
| HTTP Port | `8888` |
| Environment variables | `JUPYTER_PASSWORD` ＝ 任意のパスワード |

## 2. Pod を起動する

1. **Pods → Deploy** で GPU を選ぶ：**RTX 4090 または 3090**（50 シリーズは不可）
2. **Change Template** で 1 のテンプレートを選び、**Deploy On-Demand**
3. 1〜2 分後、**Connect → JupyterLab** を開き、パスワードを入力

## 3. 実行する

1. JupyterLab で **File → New → Terminal** を開き、次の 1 行を貼り付けて Enter：

```bash
cd /workspace && curl -L -o kojiruien_ocr_runpod.ipynb https://raw.githubusercontent.com/oushiei120/kojiruien-ocr/main/kojiruien_ocr_runpod.ipynb
```

2. 左のファイル一覧から `kojiruien_ocr_runpod.ipynb` を開く
3. 「設定」のセルで冊名を指定する（冊名は下の一覧を参照）

```python
VOLUMES = ['bung_2', 'bung_3']
```

4. **Run → Run All Cells** を押して待つ

警告が出ても、**❌** が出なければ問題ありません。❌ が出たら、そのメッセージを開発者に送ってください。

## 4. 結果を受け取り、Pod を削除する

1. 最後のセルに **✅ 完了** と出たら、`results.zip` を右クリック → **Download**
2. **RunPod で Pod を Terminate する**（削除しないと課金が続きます）

`results.zip` の中身：

- `<冊名>_v5b.txt`：山田形式のテキスト（`P n` は画像の番号）
- `<冊名>_v5b.sorted.xml`：OCR 結果（行の座標つき）

---

## 冊名の一覧

| 部 | 冊名 | 部 | 冊名 | 部 | 冊名 |
|---|---|---|---|---|---|
| 天部 | tenb_1 | 歳時部 | saij_1 | 地部 | chib_1〜3 |
| 神祇部 | jing_1〜4 | 帝王部 | teio_1 | 官位部 | kani_1〜3 |
| 封禄部 | horo_1 | 政治部 | seij_1〜4 | 法律部 | hori_1〜3 |
| 泉貨部 | senk_1 | 称量部 | syor_1 | 外交部 | gaik_1 |
| 兵事部 | heij_1 | 武技部 | bugi_1 | 方技部 | hogi_1 |
| 宗教部 | syuk_1〜4 | 文学部 | bung_1〜3 | 礼式部 | reis_1〜2 |
| 楽舞部 | gaku_1〜2 | 人部 | jinb_1〜2 | 姓名部 | seim_1 |
| 産業部 | sang_1〜2 | 服飾部 | huku_1 | 飲食部 | insi_1 |
| 居処部 | kyos_1 | 器用部 | kiyo_1〜2 | 遊戯部 | yugi_1 |
| 動物部 | dobu_1 | 植物部 | syok_1〜2 | 金石部 | kins_1 |

## うまくいかないとき

| 症状 | 対処 |
|---|---|
| GPU が「Instance not available」 | 別の GPU を選ぶ |
| Google Drive 関連のエラー | 混雑による一時的な制限。しばらく待ってそのセルを再実行 |
| `CUDA out of memory` | 設定の `PARALLEL` を 2 にして再実行 |

---

OCR エンジン：国立国会図書館 [NDLOCR](https://github.com/ndl-lab/ndlocr_cli)（CC BY 4.0）／ 正解データ・書名辞書：[識別タグ付き古事類苑データ](https://github.com/yamadashoji18/kojiruien)（CC0）／ 画像：国際日本文化研究センター（実行時に取得し、本リポジトリには含みません）
