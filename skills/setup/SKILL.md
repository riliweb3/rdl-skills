---
name: setup
description: RDL の動画スキルを使う前の準備（最初の1回）。「RDLスキルの設定」「動画スキルが動かない」「ffmpeg がない」「準備して」で起動。今のパソコン（Windows / Mac / クラウド）を見分け、Python・ffmpeg・必要な部品がそろっているか確かめ、足りない物を本人の許可を取って入れる。
---

# /rdl:setup — 最初の準備

使う人は美容師さん。**1つずつ、何をするかを短く言ってから**進める。入れる前に必ず「入れていいですか？」と聞く。

`ENGINE = <このスキルのフォルダ>/../../engine/rdl.py`

## 手順
1. `python ENGINE env`（Windows 以外は `python3`）を実行し、結果の `where`（windows / mac / cloud / linux）と `missing` を見る
   - `python` が見つからない時は、Windows なら `py ENGINE env` も試す
2. `"ready": true` なら「準備はできています」で終わり。`/rdl:make` へ
3. 足りない物は、結果の `how` に書いてある入れ方を、本人の許可を取ってから実行する
   - **Windows**：`winget` で入れたら、**Claude Code を一度閉じて開き直す**（入れた道具が見えるようになる）
   - **Mac**：Homebrew が無ければ先に入れる（パスワードを聞かれたら、本人に入力してもらう）
   - **クラウド**：`sudo apt-get install -y ffmpeg`。毎回消えるので、**環境の設定スクリプト**に同じ1行を書いておくと楽、と伝える
   - numpy / pillow は `python -m pip install --user numpy pillow`
4. もう一度 `env` を実行して `"ready": true` を確かめる
   - `optional` に出る **文字起こし（faster-whisper）** は任意。Talk の動画を台本なしで作りたい人にだけ「入れますか？（無料・数百MB）」と聞く
5. 試しに1本：`<このスキルのフォルダ>/../../samples/` があれば、その order.json で `board` を作って見せる（動くことの確認）

## つまずいた時
- 「pip が見つからない」→ `python -m ensurepip --upgrade`
- 会社のパソコンで入れられない → クラウド版の Claude Code で使う方法を案内する
- それでも動かない時は、出たメッセージをそのまま見せてもらい、原因を1つずつ確かめる
