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

## Maintainer release workflow

The two Actions workflows are separate, manual operations:

1. Run **Bump version**, select the source branch in **Use workflow from**, and choose
   `patch`, `minor`, or `major`. It validates source metadata and commits only the
   version changes directly onto that branch. It does not create a tag, dispatch
   Build, build binaries, or publish a release.
2. Run **Build** (`release.yml`) on the resulting branch/commit. There are **zero
   inputs** beyond GitHub's branch selector. Every job checks out the same immutable
   dispatch SHA. The source version supplies `vX.Y.Z`, `Kana-X.Y.Z.zip`, and
   `Kana-X.Y.Z.dmg`; a tag or free-form input never supplies the version.

Bump requires a clean checkout and the selected branch's exact remote SHA, both
before preparation and immediately before pushing. Its mandatory executable
pre-push guard checks the server-advertised old SHA, literal new commit SHA,
exact target, exactly one update, and one direct parent. Advance, rewind,
deletion, and same-result races fail closed. Pushes are non-force and disable
following tags even if Git is configured otherwise. Generated bump commits include
the Copilot App co-author trailer and must change only the three source metadata
paths listed below.

Build retains Windows x64 (`Release`, VS2022/v143 and Windows SDK 10.0) followed by
macOS (`Default`, arm64 + x86_64, deployment target 11.5). It preserves the native
project, dependencies, Cocoa framework, resource copying, `windows-binaries`
artifact, committed bundle resources, and Windows payload during Mac cleanup.
It requires fresh exact output paths, universal architecture and source bundle
metadata verification, Developer ID signing and strict signature verification,
successful **Accepted** notarization of both ZIP and DMG, and DMG stapling.
Certificate/keychain/notary secret names and the `notarytool-profile` are unchanged.
There is no new branch restriction; neither original workflow restricted branches.
Do not use a production Build run merely to validate workflow changes.

Publication is serialized repository-wide across branches, without cancellation.
Before building and again **after all native/sign/notary/staple gates**, authenticated
requests check the exact remote tag and every releases page, including drafts.
Authentication failures, 404s, network errors, malformed data, and later-page
failures are errors, never evidence of absence. Publication then performs three
create-only operations: `POST git/refs` at the selected SHA (and remote verification),
`POST releases` for a new public, non-prerelease release, and asset POSTs to that
new release ID. The original release title remains the tag; the body remains empty,
without generated notes. Existing tags/releases/assets are never reused, updated,
clobbered, deleted, retried, or rolled back, even for the same SHA.

**Partial publication recovery:** a failed request may already have succeeded
remotely. Inspect the Actions log, exact tag SHA, draft/public releases, release
IDs, and uploaded asset names/sizes manually before taking any action. Tags,
releases, and earlier uploaded assets are retained on every later failure. A
rerun intentionally refuses any occupied version. A maintainer must separately
decide how to complete or remove partial state, or bump to a new version and run
Build; these workflows never perform recovery automatically.

### Source-version authority and migration evidence

`master` was verified through both the repository API and symbolic remote HEAD.
The original workflows were introduced in
[`78355b59`](https://github.com/miyako/4d-plugin-kana/commit/78355b59fa3a9bad46f136b98d7d8c35d3fb8d5a).
Full rename-follow history contains no earlier bump workflow or later authority
change. Its **header explicitly promises coordinated**
`MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` **and**
`CFBundleShortVersionString` / `CFBundleVersion`. That promise takes precedence
over the buggy marketing-first/current-only-fallback body, which only updated the
selected Xcode key and skipped the plist when it contained a reference. This is
not an inference from initially equal values.

The actual source inputs are:

| Source path | Contract |
|---|---|
| `Kana.xcodeproj/project.pbxproj` | Six marketing settings and three current-project settings; all resolve to one strict `X.Y.Z`. The current settings may reference marketing, never themselves or an unknown setting. |
| `Info.plist` | The actual `INFOPLIST_FILE` for all three target configurations. Short version is `$(MARKETING_VERSION)`; optional `CFBundleVersion` is absent and stays absent. Valid references remain byte-for-byte unchanged; present literals co-bump. |
| `English.lproj/InfoPlist.strings` | The actual localized resource input. Both display strings co-bump; the original CR-only endings and `Copyright 2021 miyako.` remain unchanged. Quoted/unquoted and inline assignments are tokenized, with duplicate keys rejected. |

All these inputs already agree on **1.1.0**, so this migration performs **no
intake increment and no drift repair**. The existing remote `v1.1.0` is left
untouched; Build on this unchanged version intentionally refuses publication.
Use Bump first when preparing a subsequent release. Future Bumps validate all inputs before
writing anything and preserve BOM, per-line CR/CRLF/LF endings (including mixed
endings), modes, absent optional fields, references, copyright, and unrelated
bytes. Prebuilt bundle plists/localizations/binaries, dependencies, 4D data/schema
and counters, manifests, and localization/schema versions are not version authority.

The helpers and regression suites were adapted from the full, exact pinned prior
art, not from platform assumptions in comments:
[encoding-detection at `c42ca565`](https://github.com/miyako/4d-plugin-native-encoding-detection/tree/c42ca565857f674bde5ea6ed3435c87375eda4a7)
(coordinated metadata, strict localized tokenizer, guard and fail-closed cleanup),
[codec at `72c67486`](https://github.com/miyako/4d-plugin-codec/tree/72c67486d8f8ca88c1d72935137502b3d7ac4465)
(actual copied plist inputs),
[common-string-algorithm at `2606a682`](https://github.com/miyako/4d-plugin-common-string-algorithm/tree/2606a68201866ec9fcbb38b51462d79215f504ef)
and [corrected window-button at `3f14facb`](https://github.com/miyako/4d-plugin-window-button/tree/3f14facb9aaaaff0e22eeb8e07531163680c3a8a)
(independent-build counterexamples and reference safety). Their independent-build
policy and codec's second plist do not apply to Kana's explicit coordinated
header and single copied source plist.

Local regression checks (no real native/signing/notary/4D execution):

```sh
actionlint
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/tests -v
```

The suites use disposable source copies, real bare-Git race fixtures, mocked
GitHub API responses, closed-PATH native command stubs, and PowerShell path tests.
They also support running unchanged in a disposable copy after a source bump.

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
