//%attributes = {}
$KANA:="ダダダダーン"

$KANA:=Convert kana ($KANA;LCMAP_HIRAGANA)

$KANA:=Convert kana ($KANA;LCMAP_KATAKANA | LCMAP_HALFWIDTH)

$KANA:=Convert kana ($KANA;LCMAP_KATAKANA | LCMAP_FULLWIDTH)