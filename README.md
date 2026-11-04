# RDL Skills — 美容師のための動画スキル（Claude Code 用）

写真・自撮り動画・曲を渡して、**選ぶだけ**で美容室の動画ができる Claude Code のスキルです。
生成AIの課金はなし。Python と ffmpeg だけで、Windows・Mac・クラウド版の Claude Code で動きます。

## 作れる動画（10種類）
| 種類 | 中身 |
|---|---|
| **Style** ビフォーアフター | スライダーで切り替え → 左右で比べる → 寄り |
| **Style** スタイル紹介 | 前 → 横 → 後ろ → 3枚並び → 連打 |
| **Style** 施術の流れ | 番号つきで工程 → 仕上がり |
| **Brand** 新メニュー告知 | フラッシュ → 特大の文字 → 写真の連打 → 期間・価格 |
| **Brand** 求人 | 前半モノクロ → 後半いきなりカラー |
| **Brand** お客様の声 | 声を大きく、ゆっくり |
| **Brand** 爆速カット | 1〜3コマの連打・はみ出す特大の文字・4面/16面・万華鏡（曲の拍に合わせる） |
| **Talk** 語り | 間を自動で削る・強調語で暗転の文字場面・フィルム質感 |
| **Talk** 立体テロップ | 強調語が顔の横でくるっと回る |
| **Talk** ノウハウ解説 | 章ごとに番号つきのカード |

どれも、**文字の出方・切り替えを組み合わせて**選べます（おすすめ設定あり）。フォント4種・配色6種＋自由な3色。リール（9:16）・投稿（4:5）・Google（1:1）を一度に書き出せます。

美容室向けのおまけ：出す前の**安心チェック**（広告で避けたい言い方・お客様の顔出しの確認）、撮り方のコツ、**投稿文とハッシュタグの下書き**、音声入力で化けやすい美容の言葉の辞書。

## 入れ方（慣れている人向け）
Claude Code で：
```
/plugin marketplace add riliweb3/rdl-skills
/plugin install rdl@rdl-skills
```
入れたら `/rdl:setup`（最初の1回の準備）→ `/rdl:make`（動画をつくる）。

> 画面写真つきの入れ方（Windows・Mac・クラウド）と、うまく頼むコツは note の記事で案内しています。

## スキル
- `/rdl:make` 動画をつくる（入口はここだけ）
- `/rdl:setup` 最初の準備（足りない道具を確かめて入れる）
- `/rdl:check` 監督の確認（コマの一覧・止まり・音量・チェック表）

## コマンドだけで使う
```
python engine/rdl.py env                      # 準備できているか
python engine/rdl.py board samples/style-ba/order.json   # 絵コンテ
python engine/rdl.py make  samples/style-ba/order.json   # 書き出し（--preview で速い試し）
python engine/rdl.py check out/sample-ba_9x16.mp4         # 監督の確認
```

## ライセンス
MIT（`LICENSE`）。同梱フォントは SIL Open Font License（`THIRD_PARTY.md`）。
「RDL」「RiLi. Digital Labo」の名前とロゴはライセンスの対象外です。

by RiLi.（RiLi. Digital Labo）
