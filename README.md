# 4d-plugin-kana
Convert Hiragana&lt;->Katakana, Fullwidth&lt;->Halfwidth


#### Examples

```
$KANA:="ダダダダーン"

$KANA:=Convert kana ($KANA;LCMAP_HIRAGANA)

$KANA:=Convert kana ($KANA;LCMAP_KATAKANA | LCMAP_HALFWIDTH)

$KANA:=Convert kana ($KANA;LCMAP_KATAKANA | LCMAP_FULLWIDTH)
```

#### Remarks

Windowsでは[``LCMapStringEx``](https://docs.microsoft.com/en-us/windows/win32/api/winnls/nf-winnls-lcmapstringex)を使用しています。

Macでは，[``CFStringTransform``](https://developer.apple.com/documentation/corefoundation/1542411-cfstringtransform?language=objc)を使用しています。デフォルトのルール（``kCFStringTransformHiraganaKatakana``）では「だーん」が「だあん」になるので，ICU式（``CFSTR("[:^Modifier Letter:];Hiragana-Katakana")``）でルールを記述しています。
