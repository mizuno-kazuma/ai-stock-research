/**
 * PWA のメタデータ用の色。
 *
 * ブラウザのテーマカラーとマニフェストは CSS 変数を解釈しないため、リテラルが必要になる。
 * 値は styles/tokens.css の `--bg-base`（ダーク / ライト）と一致させる。tokens.css を
 * 変更したらここも合わせる。アプリの見た目に使うのはトークン側だけで、ここは
 * ブラウザ UI（アドレスバー・スプラッシュ）にしか使わない。
 */

export const THEME_COLOR_DARK = "#0b0e14";
export const THEME_COLOR_LIGHT = "#f7f8fa";
