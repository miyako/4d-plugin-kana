# 4d-plugin-kana
Convert Hiragana / Katakana, Fullwidth / Halfwidth

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
||<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|

### Version

<img width="32" height="32" src="https://user-images.githubusercontent.com/1725068/73986501-15964580-4981-11ea-9ac1-73c5cee50aae.png"> <img src="https://user-images.githubusercontent.com/1725068/73987971-db2ea780-4984-11ea-8ada-e25fb9c3cf4e.png" width="32" height="32" />

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

### Syntax

[miyako.github.io](https://miyako.github.io/2020/06/01/4d-plugin-kana.html)
