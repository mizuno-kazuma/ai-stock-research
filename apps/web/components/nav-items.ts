/** ナビゲーションの定義。docs/ui/components.md §1.4 / §1.5 の表がそのまま仕様 */

import {
  Bot,
  Briefcase,
  FileText,
  Filter,
  FlaskConical,
  LayoutDashboard,
  Search,
  Settings,
  Star,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  labelJa: string;
  icon: LucideIcon;
}

export const SIDEBAR_ITEMS: NavItem[] = [
  { href: "/", labelJa: "ダッシュボード", icon: LayoutDashboard },
  { href: "/recommendations", labelJa: "推奨銘柄", icon: Star },
  { href: "/screener", labelJa: "スクリーナー", icon: Filter },
  { href: "/filings", labelJa: "決算資料", icon: FileText },
  { href: "/macro", labelJa: "為替・マクロ", icon: TrendingUp },
  { href: "/model-lab", labelJa: "モデルラボ", icon: FlaskConical },
  { href: "/agent", labelJa: "エージェント", icon: Bot },
  { href: "/portfolio", labelJa: "ポートフォリオ", icon: Briefcase },
  { href: "/settings", labelJa: "設定", icon: Settings },
];

export const BOTTOM_NAV_ITEMS: NavItem[] = [
  { href: "/", labelJa: "ホーム", icon: LayoutDashboard },
  { href: "/recommendations", labelJa: "推奨", icon: Star },
  { href: "/screener", labelJa: "検索", icon: Search },
  { href: "/filings", labelJa: "資料", icon: FileText },
  { href: "/portfolio", labelJa: "保有", icon: Briefcase },
];

/** ルートから画面名を引く。ページ遷移の読み上げに使う */
export function routeTitle(pathname: string): string {
  if (pathname.startsWith("/stocks")) return "銘柄詳細";
  const hit = SIDEBAR_ITEMS.find((item) =>
    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  );
  return hit?.labelJa ?? "AIリサーチ";
}
