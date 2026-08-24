import { redirect } from "next/navigation";

/**
 * `/stocks/7203` のような市場を省いたパスの受け口。
 *
 * docs/01-architecture.md §3 は `/stocks/[ticker]`、docs/ui と 09-api-spec.md は
 * `/stocks/[market]/[ticker]` を使っている。App Router は同一階層に別名の動的セグメントを
 * 置けないため、`[market]/[ticker]` を正とし、1セグメントだけの場合はここで補完して飛ばす。
 */
export default async function StockRedirectPage({
  params,
}: {
  params: Promise<{ market: string }>;
}) {
  const { market } = await params;

  if (market === "JP" || market === "US") {
    // 市場だけ指定された場合は探す場所（スクリーナー）へ
    redirect(`/screener?market=${market}`);
  }

  // 日本株は4桁の数字コード、それ以外は米国株のティッカーとして扱う
  const inferred = /^\d{4}$/.test(market) ? "JP" : "US";
  redirect(`/stocks/${inferred}/${market}`);
}
