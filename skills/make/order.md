# order.json の書き方

写真・動画・曲のパスは、order.json からの相対パスでよい。書いていない項目はおすすめの値になる。

```json
{
  "type": "style",                 // style / brand / talk
  "kind": "ba",                    // 下の「種類」
  "photos": {"before": "src/before.jpg", "after": "src/after.jpg", "more": ["src/a2.jpg"]},
  "copy": "春だけの、透けるベージュ。",      // 動画の一言（15文字前後・改行は \n）
  "words": ["艶", "新"],              // 強調する言葉（1〜2文字が強い）
  "lines": ["3月だけの特別価格", "¥8,800"], // 補足の文・手順・お客様の声
  "salon": "hair salon ○○",
  "cta": "ご予約はプロフィールから",
  "music": "src/song.mp3",          // 任意（爆速カットは拍に合わせる）
  "tempo": "normal",               // slow / normal / fast / bakusoku
  "length": 15,                    // 15 / 30 / 60（Talk は話した長さで決まる）
  "textfx": ["up", "big"],         // 文字の出方（3つまで・順番に使う）
  "trans": ["slider", "mono"],     // 場面の切り替え（3つまで）
  "texture": "none",               // none / film / riso
  "fonts": {"head": "mincho", "sub": "anton"},
  "colors": {"bg": "#ffffff", "fg": "#0b0b0b", "accent": "#0b0b0b"},
  "sizes": ["9:16", "4:5", "1:1"],
  "name": "spring-beige",          // ファイル名
  "out": "out"
}
```

## 種類と素材
| type | kind | 中身 | 素材（photos の形） | 言葉 |
|---|---|---|---|---|
| style | `ba` | ビフォーアフター（スライダーで切り替え→左右比較→寄り） | `{"before", "after", "more":[...]}` | copy |
| style | `turn` | スタイル紹介（前→横→後ろ→3枚並び→連打） | `{"front", "side", "back"}` | copy |
| style | `process` | 施術の流れ（番号つきで工程→仕上がり） | `[工程1, 工程2, …, 仕上がり]` | copy・lines＝工程名 |
| brand | `menu` | 新メニュー告知（フラッシュ→特大の字→連打→詳細） | `[写真 3〜10枚]` | copy・words・lines＝期間や価格 |
| brand | `recruit` | 求人（前半モノクロ→後半いきなりカラー） | `[写真 4〜10枚]` | copy・lines＝こんな人・message＝締め |
| brand | `review` | お客様の声（言葉を大きくゆっくり） | `[写真 1〜5枚]` | copy・lines＝`"声|30代・会社員"` |
| brand | `bakusoku` | 爆速カット（1〜3コマの連打・特大の字・4面/16面・万華鏡） | `[写真 6〜15枚]`＋music | words |
| talk | `katari` | 語り（強調語で暗転の文字場面・フィルム質感） | `"video": "src/me.mp4"` | script・words・copy |
| talk | `tele3d` | 立体テロップ（強調語が顔の横でくるっと回る） | 同上 | script・words・copy |
| talk | `howto` | ノウハウ解説（`# 見出し` で番号つきの章カード） | 同上 | script（`# ` 行が章） |

Talk の `script` は話した内容の文章。**1行＝1テロップ**（16〜24文字が読みやすい）。間（無音）は自動で削る。うまく削れない時は `"noise_db": -28`（大きめの雑音の部屋）〜 `-38`（静かな部屋）。

## 選べる演出
- **textfx（文字の出方）**：`up` スッと出る／`pop` 弾む／`type` 1文字ずつ／`big` 特大はみ出し／`spin` 立体で回る／`scene` 明朝の文字場面（暗転）／`number` 番号つき／`marker` マーカー
- **trans（切り替え）**：`black` 暗転／`wipe` ワイプ／`slider` スライダー／`zoom` 寄り／`turn` 回り込み／`flash` 赤黒フラッシュ／`mono` モノクロ反転／`kaleido` 万華鏡／`trail` 残像／`cut` そのまま
- **fonts**：`mincho` 明朝（上品・語り）／`gothic` ゴシック（読みやすい）／`maru` 丸ゴ（やわらか）／`anton` 英字（日本語は自動でゴシック）
- **配色の見本**：モノクロ `#0b0b0b/#ffffff/#9a9a9a`／黒×赤 `#0b0b0b/#ffffff/#e2261a`／白×黒 `#ffffff/#0b0b0b/#0b0b0b`／ベージュ `#ece5da/#1a1714/#8a6a4a`／紺×桃 `#151b3c/#ffffff/#f2a7c3`／黒×金 `#0e0d0b/#f4efe6/#c9a45c`（bg/fg/accent の順）

## おすすめ表（「おすすめで」の時はこれをそのまま）
| kind | tempo | textfx | trans | texture | 長さ | fonts | 配色 |
|---|---|---|---|---|---|---|---|
| ba | normal | up, big | slider, mono | none | 15 | mincho / anton | 白×黒 |
| turn | slow | up | turn, trail | none | 15 | mincho / anton | ベージュ |
| process | normal | number, up | wipe | none | 30 | gothic / gothic | モノクロ |
| menu | fast | big, pop | flash, zoom | none | 15 | mincho / anton | 黒×赤 |
| recruit | normal | pop, type | mono, wipe | film | 30 | gothic / maru | 紺×桃 |
| review | slow | spin, type | black | none | 15 | maru / maru | ベージュ |
| bakusoku | bakusoku | big, type | kaleido, flash, trail | riso | 15 | mincho / anton | 黒×赤 |
| katari | slow | scene, up | black, trail | film | — | mincho / mincho | モノクロ |
| tele3d | normal | spin, marker | zoom, flash | none | — | gothic / gothic | 黒×赤 |
| howto | normal | number, marker | wipe, zoom | none | — | gothic / maru | 白×黒 |

## よくある直し
- 文字が変な所で折れる → copy に `\n` を入れる
- 写真の寄る位置がずれる → 写真を先にトリミングしておく（髪が画面の上半分に来るように）
- 曲の合わせる位置を変えたい → `"music_start": 秒`（爆速カットはサビを自動で探す）
- もっと速く／ゆっくり → tempo を1段変える
