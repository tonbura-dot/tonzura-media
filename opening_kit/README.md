# 4角女神 オープニング キット
キャラの絵・仕草クリップは入っていません（Mac miniの手元の素材を使う）。

```
python3 compose_op.py --clips <仕草フォルダ> --stills <透過PNGフォルダ> --bgm <01_opening_jingle.wav> --out <出力先>
```
- 仕草クリップ: ソラ_髪をくるくる / ララン_ヘッドホンをつける / ミレイ_コインをいじる / ロゼ_メモを取る（CHARS の clip で変更可）
- 背景抜きは rembg(isnet-anime)。結果は frames/ にキャッシュ。
- 出力: opening_yoko_16x9.mp4（1920x1080）と opening_tate_9x16.mp4（1080x1920）、約7.5秒、30fps
- 声: voice/（VOICEVOX、いつもの4人の声。voice_op.py で再生成）
- フォント: Dela Gothic One / Shippori Mincho B1（使う文字だけのサブセット）/ Cinzel（いずれもSIL OFL）
