![version](https://img.shields.io/badge/version-18%2B-EB8E5F)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-kana)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-kana/total)

**Note**: for v17 and earlier, move `manifest.json` to `Contents`

# 4d-plugin-kana

Convert Japanese text between Hiragana and Katakana, and between fullwidth and halfwidth forms, in one call. The plugin has a single command, [Convert kana](#convert-kana). It takes a `Text` and a mode built from the plugin's [constants](#constants), and returns the converted `Text`. On macOS it uses [`CFStringTransform`](https://developer.apple.com/documentation/corefoundation/1542411-cfstringtransform?language=objc) with ICU transliteration rules. On Windows it calls [`LCMapStringEx`](https://docs.microsoft.com/en-us/windows/win32/api/winnls/nf-winnls-lcmapstringex) with the user's default locale.

| Command | Returns | Purpose |
|---|---|---|
| [Convert kana](#convert-kana) | `Text` | Convert kana (Hiragana / Katakana) and character width (fullwidth / halfwidth) |

**Platforms:** macOS (Apple silicon and Intel), Windows (64-bit)

[Releases](https://github.com/miyako/4d-plugin-kana/releases) · [Original article (Japanese)](https://miyako.github.io/2020/06/01/4d-plugin-kana.html)

---

## Requirements & platform notes

- **Every call does two conversions.** The mode always selects a kana direction (Hiragana *or* Katakana) and a width direction (fullwidth *or* halfwidth). Neither can be left as is. A mode of `0` means `LCMAP_HIRAGANA | LCMAP_FULLWIDTH`.
- **Width conversion is not limited to kana.** On macOS, fullwidth mode also turns ASCII letters, digits, punctuation and the space into their fullwidth forms (`"ABC 123"` → `"ＡＢＣ　１２３"`), and halfwidth mode turns them back (observed). `LCMAP_FULLWIDTH` / `LCMAP_HALFWIDTH` on Windows are expected to behave the same way, but this was not checked.
- **Both parameters are mandatory.** The manifest declares `Convert kana(&T;&L):T`, with no optional form.
- **Thread safe.** The command is declared `threadSafe`, so you can call it from preemptive processes.
- **The two platforms use different engines** (ICU rules on macOS, the Windows NLS tables on Windows), so edge cases can differ. The macOS results quoted below were observed with `CFStringTransform` on macOS 26. The Windows results were not checked for this document.
- **On macOS**, the kana rules are `[:^Modifier Letter:];Hiragana-Katakana` and `[:^Modifier Letter:];Katakana-Hiragana` rather than the built-in `kCFStringTransformHiraganaKatakana`. The filter leaves the prolonged sound mark `ー` (a modifier letter) alone; according to the author's original notes, the built-in rule turns `だーん` into `だあん`. The width step is `kCFStringTransformFullwidthHalfwidth` (applied in reverse for fullwidth).
- **On Windows**, the mode is mapped to `LCMAP_HIRAGANA` or `LCMAP_KATAKANA`, combined with `LCMAP_FULLWIDTH` or `LCMAP_HALFWIDTH`, and passed to `LCMapStringEx(LOCALE_NAME_USER_DEFAULT, …)`.

---

## Constants

Theme **Kana Conversion Mode**. Combine one kana constant and one width constant with the bitwise OR operator `|`.

| Constant | Value | Meaning |
|---|---|---|
| `LCMAP_HIRAGANA` | `0` | Convert Katakana to Hiragana (the default) |
| `LCMAP_KATAKANA` | `2` | Convert Hiragana to Katakana |
| `LCMAP_FULLWIDTH` | `0` | Convert halfwidth characters to fullwidth (the default) |
| `LCMAP_HALFWIDTH` | `1` | Convert fullwidth characters to halfwidth |

The names match the Windows API flags, but the **values are the plugin's own**. Use the constants, not the Windows SDK numbers. Only these two bits are read; any other bits in the mode are ignored.

---

## Convert kana

### Syntax

```
Convert kana ( text ; mode ) -> Text
```

| Parameter | Type | Description |
|---|---|---|
| `text` | Text | The text to convert |
| `mode` | Longint | `LCMAP_HIRAGANA` or `LCMAP_KATAKANA`, combined with `LCMAP_FULLWIDTH` or `LCMAP_HALFWIDTH` |
| Result | Text | The converted text |

### Description

`Convert kana` converts the kana direction first, then the width, and returns the result. Kanji and characters with no Hiragana, Katakana or width counterpart are returned unchanged.

| `mode` | Kana | Width | `"ダダダダーン"` becomes (macOS) |
|---|---|---|---|
| `LCMAP_HIRAGANA` (`0`) | Hiragana | fullwidth | `だだだだーん` |
| `LCMAP_HIRAGANA \| LCMAP_HALFWIDTH` (`1`) | Hiragana | halfwidth | `だだだだｰん` |
| `LCMAP_KATAKANA` (`2`) | Katakana | fullwidth | `ダダダダーン` |
| `LCMAP_KATAKANA \| LCMAP_HALFWIDTH` (`3`) | Katakana | halfwidth | `ﾀﾞﾀﾞﾀﾞﾀﾞｰﾝ` |

Halfwidth forms exist only for Katakana. With `LCMAP_HIRAGANA | LCMAP_HALFWIDTH` the Hiragana stays fullwidth; only characters that have a halfwidth form, such as `ー` and ASCII, change width.

**On macOS**, because the kana step runs before the width step, halfwidth Katakana given to `LCMAP_HIRAGANA | LCMAP_HALFWIDTH` comes back as Hiragana followed by separate halfwidth voiced marks (`ﾀﾞﾀﾞｰﾝ` → `たﾞたﾞｰん`). The small Katakana `ヵ` and `ヶ` become the full-size `か` and `け` in Hiragana mode, and `ゐ` becomes `ヰ` in Katakana mode (observed).

An empty `text` returns an empty string.

### Example

From the plugin's own test method (`test/Project/Sources/Methods/test.4dm`):

```4d
$KANA:="ダダダダーン"

$KANA:=Convert kana ($KANA;LCMAP_HIRAGANA)

$KANA:=Convert kana ($KANA;LCMAP_KATAKANA | LCMAP_HALFWIDTH)

$KANA:=Convert kana ($KANA;LCMAP_KATAKANA | LCMAP_FULLWIDTH)
```

On macOS the three calls produce `だだだだーん`, `ﾀﾞﾀﾞﾀﾞﾀﾞｰﾝ` and `ダダダダーン`.

Normalise a search key so that `かな`, `カナ` and `ｶﾅ` all match. This also makes any ASCII in the key fullwidth, so normalise the stored values the same way:

```4d
$key:=Convert kana($input;LCMAP_KATAKANA | LCMAP_FULLWIDTH)
```

Convert every element of a text array:

```4d
For ($i;1;Size of array($names))
	$names{$i}:=Convert kana($names{$i};LCMAP_HIRAGANA)
End for
```

---

## Error handling & troubleshooting

- **Failures are silent, not 4D errors.** On Windows, if `LCMapStringEx` fails, the result is an empty string. On macOS, the status of `CFStringTransform` is not checked, so a step that fails leaves the text as it was before that step.
- **Unexpected fullwidth ASCII.** The default width is fullwidth, so `Convert kana("abc";LCMAP_KATAKANA)` returns `ａｂｃ` on macOS. Use `LCMAP_HALFWIDTH` to keep ASCII narrow, but then Katakana becomes halfwidth too: one call can't mix widths.
- **Results differ between Mac and Windows.** The engines are different. If both platforms must agree exactly, test your own data on both.
- **Wrong numbers for the mode.** Windows SDK values such as `0x00100000` don't work: the plugin reads only bit `1` (halfwidth) and bit `2` (Katakana). Use the plugin constants.
- **Internal exceptions.** From this revision on, an unexpected internal exception returns an empty string instead of leaving the call without a result. This was added during the code review and is not in release 1.1.0.

---

## Quick reference

```4d
$hira:=Convert kana($text;LCMAP_HIRAGANA)  // Hiragana, fullwidth
$kata:=Convert kana($text;LCMAP_KATAKANA)  // Katakana, fullwidth
$hankaku:=Convert kana($text;LCMAP_KATAKANA | LCMAP_HALFWIDTH)  // halfwidth Katakana
```
