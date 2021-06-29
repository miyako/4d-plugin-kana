![version](https://img.shields.io/badge/version-18%2B-EB8E5F)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-kana)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-kana/total)

**Note**: for v17 and earlier, move `manifest.json` to `Contents`

# 4d-plugin-kana
Convert Hiragana / Katakana, Fullwidth / Halfwidth

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
