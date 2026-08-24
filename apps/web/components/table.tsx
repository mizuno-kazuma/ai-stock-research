"use client";

/**
 * レスポンシブなデータ表。
 *
 * interaction-patterns.md §2.3 に従い、768px 未満では表をカードリストに変換する。
 * 横スクロールはさせない（列が見切れると数字の比較ができない）。
 *
 * キーボード操作は「主要セルのリンク」で担保する。行全体の onClick はマウス操作の
 * 補助でしかないので、リンクのない行は作らない。
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { cx } from "./ui";

export interface Column<T> {
  key: string;
  header: string;
  /** 右寄せ + tabular-nums */
  numeric?: boolean;
  /** カード表示の見出しになる列。1つだけ指定する */
  primary?: boolean;
  /** カード表示では省く列 */
  hideOnCard?: boolean;
  /** 表でのみ省く列（カードにだけ出したい補足） */
  hideOnTable?: boolean;
  render: (row: T) => ReactNode;
  /** 並べ替えに使う値。渡した列だけ並べ替え可能になる */
  sortValue?: (row: T) => number | string | null;
  headerHint?: string;
}

export interface DataTableProps<T> {
  columns: Array<Column<T>>;
  rows: T[];
  getKey: (row: T) => string;
  /** 行の遷移先。指定すると主要セルがリンクになる */
  getHref?: (row: T) => string;
  caption: string;
  dense?: boolean;
  initialSort?: { key: string; dir: "asc" | "desc" };
  /** カード表示のときに主要セルの下に出す補足 */
  cardSubtitle?: (row: T) => ReactNode;
}

type SortState = { key: string; dir: "asc" | "desc" } | null;

export function DataTable<T>({
  columns,
  rows,
  getKey,
  getHref,
  caption,
  dense,
  initialSort,
  cardSubtitle,
}: DataTableProps<T>) {
  const router = useRouter();
  const [sort, setSort] = useState<SortState>(initialSort ?? null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    // 欠損は並べ替えの方向にかかわらず必ず末尾（0 として扱わない）
    return [...rows].sort((a, b) => {
      const av = get(a);
      const bv = get(b);
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv), "ja");
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [rows, sort, columns]);

  const toggleSort = (key: string) => {
    setSort((prev) => {
      if (prev?.key !== key) return { key, dir: "desc" };
      if (prev.dir === "desc") return { key, dir: "asc" };
      return null;
    });
  };

  const primary = columns.find((c) => c.primary) ?? columns[0]!;

  return (
    <>
      {/* 768px 以上: 表 */}
      <div className="hidden tablet:block overflow-hidden rounded-lg border border-divider">
        <table className={cx("data-table", dense && "data-table--dense")}>
          <caption className="visually-hidden">{caption}</caption>
          <thead>
            <tr>
              {columns
                .filter((c) => !c.hideOnTable)
                .map((col) => {
                  const active = sort?.key === col.key;
                  const ariaSort = active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none";
                  return (
                    <th
                      key={col.key}
                      scope="col"
                      className={col.numeric ? "is-numeric" : undefined}
                      aria-sort={col.sortValue ? ariaSort : undefined}
                    >
                      {col.sortValue ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 text-fg-tertiary hover:text-fg-primary"
                          onClick={() => toggleSort(col.key)}
                          title={col.headerHint ?? `${col.header}で並べ替え`}
                        >
                          {col.header}
                          {active ? (
                            sort!.dir === "asc" ? (
                              <ArrowUp size={11} aria-hidden="true" />
                            ) : (
                              <ArrowDown size={11} aria-hidden="true" />
                            )
                          ) : (
                            <ArrowUpDown size={11} aria-hidden="true" className="opacity-50" />
                          )}
                        </button>
                      ) : (
                        <span title={col.headerHint}>{col.header}</span>
                      )}
                    </th>
                  );
                })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const href = getHref?.(row);
              return (
                <tr
                  key={getKey(row)}
                  className={href ? "is-clickable" : undefined}
                  onClick={href ? () => router.push(href) : undefined}
                >
                  {columns
                    .filter((c) => !c.hideOnTable)
                    .map((col) => (
                      <td key={col.key} className={col.numeric ? "is-numeric" : undefined}>
                        {col.key === primary.key && href ? (
                          <Link
                            href={href}
                            className="text-fg-primary hover:text-accent"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {col.render(row)}
                          </Link>
                        ) : (
                          col.render(row)
                        )}
                      </td>
                    ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 768px 未満: カードリスト */}
      <ul className="tablet:hidden space-y-2" aria-label={caption}>
        {sorted.map((row) => {
          const href = getHref?.(row);
          const body = (
            <>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-h4 text-fg-primary min-w-0 truncate">{primary.render(row)}</span>
              </div>
              {cardSubtitle ? <div className="text-caption text-fg-tertiary">{cardSubtitle(row)}</div> : null}
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                {columns
                  .filter((c) => c.key !== primary.key && !c.hideOnCard)
                  .map((col) => (
                    <div key={col.key} className="flex items-baseline justify-between gap-2 min-w-0">
                      <dt className="text-caption text-fg-tertiary truncate">{col.header}</dt>
                      <dd className={cx("text-body-sm", col.numeric && "num")}>{col.render(row)}</dd>
                    </div>
                  ))}
              </dl>
            </>
          );
          return (
            <li key={getKey(row)} className="card p-4">
              {href ? (
                <Link href={href} className="block">
                  {body}
                </Link>
              ) : (
                body
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/**
 * チャートの代替テーブル。アクセシビリティ要件（チャートに同等のデータ表示）を満たす。
 * 既定は閉じているが、これは図の重複表示を避けるためで、内容は常に到達可能。
 */
export function ChartDataTable({
  caption,
  headers,
  rows,
}: {
  caption: string;
  headers: string[];
  rows: Array<Array<ReactNode>>;
}) {
  return (
    <details className="mt-2">
      <summary className="text-caption text-fg-tertiary cursor-pointer tap-target">
        図のデータを表で見る
      </summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-md border border-divider">
        <table className="data-table data-table--dense">
          <caption className="visually-hidden">{caption}</caption>
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={h} scope="col" className={i > 0 ? "is-numeric" : undefined}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((cells, r) => (
              <tr key={r}>
                {cells.map((cell, c) => (
                  <td key={c} className={c > 0 ? "is-numeric" : undefined}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
