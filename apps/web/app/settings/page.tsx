"use client";

/**
 * 設定（docs/ui/screens/10-settings.md）。
 *
 * 方向色は最初の項目。ライブプレビューで切替結果を見てから画面を離れる。
 * クライアント側の表示設定は即時反映し、サーバ側設定は失敗したら元に戻す。
 */

import { Suspense, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { formatUsd, NULL_PLACEHOLDER } from "@ai-stock/ui";

import { useOnlineStatus } from "../../components/app-shell";
import { ConfirmDialog, Field } from "../../components/dialog";
import { PageHeader } from "../../components/page-header";
import { usePrefs } from "../../components/prefs";
import {
  LoadingRegion,
  QuerySection,
  Skeleton,
  SkeletonCards,
  SkeletonTable,
} from "../../components/states";
import { Badge, Button, Notice, SectionCard, Toggle } from "../../components/ui";
import { DirectionValue, NullableText } from "../../components/values";
import type { DefaultMarket, DirectionColors, Horizon, Settings, ThemeMode } from "../../lib/api-types";
import { resolveMarket } from "../../lib/market";
import {
  useAgentCost,
  useRebuildVectors,
  useRunBackup,
  useRunDiagnostics,
  useSettingsQuery,
  useSystemFreshness,
  useSystemHealth,
  useUpdateSettings,
} from "../../lib/queries";
import { useQueryParamState } from "../../lib/use-tab";

const SECTIONS = ["display", "cost", "data", "analysis", "notifications", "system"] as const;
type Section = (typeof SECTIONS)[number];
const SECTION_LABEL: Record<Section, string> = {
  display: "表示",
  cost: "コスト",
  data: "データ",
  analysis: "分析",
  notifications: "通知",
  system: "システム",
};

const SCHEDULE: Array<{ job: string; when: string }> = [
  { job: "日本株の収集", when: "平日 06:00 / 15:30 (JST)" },
  { job: "米国株の収集", when: "平日 06:30 (JST)" },
  { job: "分析", when: "平日 06:15 / 16:00 (JST)" },
  { job: "資料読解", when: "平日 06:25 (JST)" },
  { job: "推奨生成", when: "平日 06:35 (JST)" },
  { job: "レビュー", when: "平日 06:42 (JST)" },
  { job: "実績評価", when: "平日 06:47 (JST)" },
  { job: "週次の深掘り", when: "土曜 09:00 (JST)" },
  { job: "ranker 再学習", when: "第1土曜 10:00 (JST)" },
  { job: "GARCH 再推定", when: "月曜 07:00 (JST)" },
];

function DirectionPreview() {
  return (
    <div className="card-inset p-3 space-y-1" data-testid="direction-preview">
      <p className="text-body-sm">
        7203 トヨタ自動車 <DirectionValue value={0.0124} format="percent" />
      </p>
      <p className="text-body-sm">
        6758 ソニーグループ <DirectionValue value={-0.0082} format="percent" />
      </p>
    </div>
  );
}

function DisplaySection({ settings }: { settings: Settings }) {
  const prefs = usePrefs();
  const update = useUpdateSettings();
  const online = useOnlineStatus();

  const applyDirection = (next: DirectionColors) => {
    prefs.setPrefs({ directionColors: next });
    if (online) update.mutate({ "ui.direction_colors": next });
  };

  return (
    <SectionCard title="表示" id="display">
      <p className="text-h4 mb-2">上昇・下落の色</p>
      <p className="text-body-sm text-fg-secondary prose-block">
        日本と米国では上昇・下落の色が逆です。取り違えると保有状況を正反対に読み取る危険があるため、必ず自分が慣れている方式を選んでください。
      </p>
      <p className="text-caption text-fg-tertiary mt-1">
        どちらを選んでも、符号（+ / -）と矢印を併記します。色だけで方向を判断する必要はありません。
      </p>
      <div className="mt-3 grid gap-3 tablet:grid-cols-2">
        <button
          type="button"
          className="card p-4 text-left tap-target"
          aria-pressed={prefs.directionColors === "jp"}
          onClick={() => applyDirection("jp")}
        >
          <p className="text-h4">日本式</p>
          <p className="text-caption text-fg-tertiary">上昇 = 赤 / 下落 = 青</p>
          <div className="mt-2" data-direction-colors="jp">
            {/* プレビューはグローバル設定に従う。選択中のカードであることが分かるようにする */}
            <DirectionPreview />
          </div>
        </button>
        <button
          type="button"
          className="card p-4 text-left tap-target"
          aria-pressed={prefs.directionColors === "us"}
          onClick={() => applyDirection("us")}
        >
          <p className="text-h4">米国式</p>
          <p className="text-caption text-fg-tertiary">上昇 = 緑 / 下落 = 赤</p>
          <DirectionPreview />
        </button>
      </div>
      <div className="mt-4 desktop:hidden">
        <p className="text-caption text-fg-tertiary mb-1">プレビュー</p>
        <DirectionPreview />
      </div>

      <Field label="テーマ" className="mt-4">
        <select
          className="input"
          value={prefs.theme}
          onChange={(e) => {
            const theme = e.target.value as ThemeMode;
            prefs.setPrefs({ theme });
            if (online) update.mutate({ "ui.theme": theme });
          }}
        >
          <option value="dark">ダーク</option>
          <option value="light">ライト</option>
        </select>
        <span className="text-caption text-fg-muted">既定はダークです。システムに合わせるはOS設定の反映を次版で追加します。</span>
      </Field>
      <Field label="既定の市場" className="mt-3">
        <select
          className="input"
          value={settings["ui.default_market"]}
          disabled={!online}
          onChange={(e) => {
            const next = e.target.value as DefaultMarket;
            prefs.setPrefs({ market: resolveMarket(next) });
            update.mutate({ "ui.default_market": next });
          }}
        >
          <option value="JP">日本株</option>
          <option value="US">米国株</option>
          <option value="auto">時刻で自動切替</option>
        </select>
        <span className="text-caption text-fg-muted">
          「時刻で自動切替」は日本時間15時までを日本株、それ以降を米国株として開きます。
        </span>
      </Field>
      <Field label="大きい数値の表記" className="mt-3">
        <select
          className="input"
          value={settings["ui.number_format"]}
          onChange={(e) => update.mutate({ "ui.number_format": e.target.value as Settings["ui.number_format"] })}
          disabled={!online}
        >
          <option value="jp">日本式（1兆2,340億円）</option>
          <option value="intl">国際式（12.34兆 / 1.234e12）</option>
        </select>
      </Field>
      <Field label="情報密度" className="mt-3">
        <select
          className="input"
          value={prefs.density}
          onChange={(e) => {
            const density = e.target.value as "standard" | "dense";
            prefs.setPrefs({ density });
            if (online) update.mutate({ "ui.density": density });
          }}
        >
          <option value="standard">標準</option>
          <option value="dense">高密度</option>
        </select>
        <span className="text-caption text-fg-muted">高密度は表の行の高さを詰めます。モバイルでは常に標準が使われます。</span>
      </Field>
      <p className="text-caption text-fg-tertiary mt-3">アニメーションの抑制: OSの設定に従います</p>
    </SectionCard>
  );
}

function CostSection({ settings }: { settings: Settings }) {
  const online = useOnlineStatus();
  const costQ = useAgentCost();
  const update = useUpdateSettings();
  const [daily, setDaily] = useState(String(settings["llm.daily_cap_usd"]));
  const [monthly, setMonthly] = useState(String(settings["llm.monthly_cap_usd"]));
  const [confirmKill, setConfirmKill] = useState<"on" | "off" | null>(null);
  const spent = costQ.data?.data.spent_today_usd ?? null;
  const kill = settings["llm.kill_switch"];

  const saveDaily = () => {
    const n = Number(daily);
    if (!Number.isFinite(n) || n < 0 || n > 100) {
      return;
    }
    update.mutate({ "llm.daily_cap_usd": n });
  };

  return (
    <SectionCard title="コスト" id="cost">
      <QuerySection
        label="現在の利用額"
        query={costQ}
        skeleton={<Skeleton className="h-12 w-full" />}
      >
        {(c) => (
          <p className="text-body-sm">
            現在の利用額 本日 {formatUsd(c.spent_today_usd)} / 当月 {formatUsd(c.spent_month_usd)} · 当月見込み{" "}
            <NullableText value={c.projected_month_usd !== null ? formatUsd(c.projected_month_usd) : null} />
          </p>
        )}
      </QuerySection>
      {costQ.error ? <p className="text-caption text-status-warning">利用額を取得できませんでした</p> : null}
      <Field label="日次上限 (USD)" className="mt-3">
        <input
          className="input input-numeric"
          value={daily}
          disabled={!online}
          onChange={(e) => setDaily(e.target.value)}
          onBlur={saveDaily}
        />
        <span className="text-caption text-fg-muted">上限に達するとその日のLLM呼び出しを停止します。定量スコアと推奨の生成は継続します。</span>
        {spent !== null && Number(daily) < spent ? (
          <Notice tone="warning" className="mt-2">
            本日すでに {formatUsd(spent)} 使用しています。上限を {formatUsd(Number(daily))} に設定すると、本日はこれ以上LLMを使用できません。
          </Notice>
        ) : null}
      </Field>
      <Field label="月次上限 (USD)" className="mt-3">
        <input
          className="input input-numeric"
          value={monthly}
          disabled={!online}
          onChange={(e) => setMonthly(e.target.value)}
          onBlur={() => {
            const n = Number(monthly);
            if (Number.isFinite(n)) update.mutate({ "llm.monthly_cap_usd": n });
          }}
        />
      </Field>
      <Toggle
        checked={kill}
        disabled={!online}
        onChange={(next) => setConfirmKill(next ? "on" : "off")}
        label="LLMの停止スイッチ"
        description="有効にすると、資料の要約・定性評価・論拠生成をすべて停止します。この状態でも推奨は定量スコアのみで生成されます。"
      />
      {!online ? <p className="text-caption text-status-warning">オフラインでは変更できません</p> : null}
      <div className="mt-4">
        <p className="text-h4">モデルの割り当て</p>
        <table className="data-table data-table--dense mt-2">
          <thead>
            <tr>
              <th>用途</th>
              <th>モデル</th>
              <th>単価</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>一括処理</td>
              <td>Gemini 3.7 Flash</td>
              <td className="num">$0.75 / $3.75</td>
            </tr>
            <tr>
              <td>推論</td>
              <td>Claude Sonnet 5</td>
              <td className="num">$3.00 / $15.00</td>
            </tr>
            <tr>
              <td>詳細分析</td>
              <td>Claude Opus 5</td>
              <td className="num">$5.00 / $25.00</td>
            </tr>
            <tr>
              <td>埋め込み</td>
              <td>gemini-embedding</td>
              <td className="num">$0.15 / —</td>
            </tr>
          </tbody>
        </table>
        <p className="text-caption text-fg-tertiary mt-2 prose-block">
          モデル名と単価は models.yaml で管理しています。この画面からは変更できません。表示している単価は 2026年8月 時点の確認値です。
        </p>
      </div>
      <ConfirmDialog
        open={confirmKill === "on"}
        onClose={() => setConfirmKill(null)}
        title="LLMを停止しますか"
        confirmLabel="停止する"
        danger
        onConfirm={() => {
          update.mutate({ "llm.kill_switch": true });
          setConfirmKill(null);
        }}
      >
        要約と論拠生成が停止します。
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmKill === "off"}
        onClose={() => setConfirmKill(null)}
        title="停止を解除しますか"
        confirmLabel="解除する"
        onConfirm={() => {
          update.mutate({ "llm.kill_switch": false });
          setConfirmKill(null);
        }}
      >
        本日の残予算は {spent !== null ? formatUsd(Math.max(0, settings["llm.daily_cap_usd"] - spent)) : NULL_PLACEHOLDER} です。
      </ConfirmDialog>
    </SectionCard>
  );
}

function DataSection({ settings }: { settings: Settings }) {
  const online = useOnlineStatus();
  const update = useUpdateSettings();
  const freshnessQ = useSystemFreshness();
  const [confirmPlan, setConfirmPlan] = useState(false);
  const [confirmTdnet, setConfirmTdnet] = useState(false);

  return (
    <SectionCard title="データ" id="data">
      <Field label="J-Quantsのプラン">
        <select
          className="input"
          value={settings["data.jquants_plan"]}
          disabled={!online}
          onChange={(e) => {
            if (e.target.value !== settings["data.jquants_plan"]) setConfirmPlan(true);
          }}
        >
          <option value="free">無料プラン</option>
          <option value="light">Lightプラン</option>
        </select>
      </Field>
      <p className="text-caption text-fg-secondary mt-2 prose-block">
        無料プラン: 費用 ¥0 · 過去2年 · 12週間の遅延 · 5リクエスト/分。Lightプラン: 月額 ¥1,650 · 過去5年 · 遅延なし · 60リクエスト/分。
      </p>
      <p className="text-caption text-fg-tertiary mt-1">
        変更されるもの: 価格データの遅延、取得可能な履歴の長さ、リクエスト間隔。変更されないもの: スキーマ、分析ロジック、参考現在値の取得元（yfinance）。
      </p>
      <Toggle
        checked={settings["data.tdnet_enabled"]}
        disabled={!online}
        onChange={(next) => {
          if (next) setConfirmTdnet(true);
          else update.mutate({ "data.tdnet_enabled": false });
        }}
        label="適時開示 (TDnet)"
        description="TDnetには公開APIがないため、取得は低頻度に制限しています。利用規約を確認したうえで有効にしてください。"
      />
      <QuerySection label="データソース" query={freshnessQ} skeleton={<SkeletonTable rows={6} cols={3} />}>
        {(f) => (
          <table className="data-table data-table--dense mt-3">
            <thead>
              <tr>
                <th>ソース</th>
                <th>状態</th>
                <th>最新</th>
                <th>APIキー</th>
              </tr>
            </thead>
            <tbody>
              {f.sources.map((s) => (
                <tr key={s.source}>
                  <td>{s.label_ja}</td>
                  <td>
                    <Badge tone={s.status === "ok" ? "success" : s.status === "failed" ? "danger" : "warning"}>
                      {s.status === "ok" ? "正常" : s.status === "failed" ? "失敗" : "遅延"}
                    </Badge>
                  </td>
                  <td className="num">{s.latest_as_of}</td>
                  <td>{s.api_key_ja ?? NULL_PLACEHOLDER}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </QuerySection>
      <p className="text-h4 mt-4">収集スケジュール</p>
      <table className="data-table data-table--dense mt-2">
        <tbody>
          {SCHEDULE.map((row) => (
            <tr key={row.job}>
              <td>{row.job}</td>
              <td className="num">{row.when}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-caption text-fg-tertiary mt-2">
        スケジュールはアプリ内のスケジューラで管理しています。OSのタスクスケジューラやcronは使用していません。PCがスリープしていた場合、復帰後にまとめて1回だけ実行されます。
      </p>
      <ConfirmDialog
        open={confirmPlan}
        onClose={() => setConfirmPlan(false)}
        title="プランを切り替えますか"
        confirmLabel="切り替える"
        onConfirm={() => {
          update.mutate({ "data.jquants_plan": settings["data.jquants_plan"] === "free" ? "light" : "free" });
          setConfirmPlan(false);
        }}
      >
        遅延と履歴の長さが変わります。スキーマと分析ロジックは変わりません。次のデータ収集で遅延分が埋まります。
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmTdnet}
        onClose={() => setConfirmTdnet(false)}
        title="TDnetを有効にしますか"
        confirmLabel="有効にする"
        onConfirm={() => {
          update.mutate({ "data.tdnet_enabled": true });
          setConfirmTdnet(false);
        }}
      >
        公開APIがないため取得は低頻度です。利用規約を確認したうえで有効にしてください。
      </ConfirmDialog>
    </SectionCard>
  );
}

function AnalysisSection({ settings }: { settings: Settings }) {
  const online = useOnlineStatus();
  const update = useUpdateSettings();
  const [confirmAuto, setConfirmAuto] = useState(false);
  return (
    <SectionCard title="分析" id="analysis">
      <Field label="既定の予測期間">
        <select
          className="input"
          value={settings["analysis.default_horizon"]}
          disabled={!online}
          onChange={(e) => update.mutate({ "analysis.default_horizon": e.target.value as Horizon })}
        >
          <option value="H5">5営業日</option>
          <option value="H20">20営業日</option>
        </select>
      </Field>
      <Field label="1日の推奨件数の上限" className="mt-3">
        <input
          className="input input-numeric"
          defaultValue={settings["analysis.max_recommendations"]}
          disabled={!online}
          onBlur={(e) => {
            const n = Number(e.target.value);
            if (n >= 1 && n <= 50) update.mutate({ "analysis.max_recommendations": n });
          }}
        />
        <span className="text-caption text-fg-muted">件数を増やすとLLMコストが比例して増えます。</span>
      </Field>
      <p className="text-caption text-fg-secondary mt-3">定性スコアの調整幅 ±12点（変更不可）</p>
      <p className="text-caption text-fg-muted">定性評価が定量スコアの序列を覆さないよう、調整幅を固定しています。</p>
      <Field label="ファクター重みの更新" className="mt-3">
        <select
          className="input"
          value={settings["analysis.weight_approval_mode"]}
          disabled={!online}
          onChange={(e) => {
            if (e.target.value === "auto") setConfirmAuto(true);
            else update.mutate({ "analysis.weight_approval_mode": "manual" });
          }}
        >
          <option value="manual">承認制（既定）</option>
          <option value="auto">自動適用</option>
        </select>
        <span className="text-caption text-fg-muted">
          自動適用は推奨しません。Evaluatorが提案した重みは、モデルラボで内容を確認してから適用してください。
        </span>
      </Field>
      <p className="text-caption text-fg-tertiary mt-3">特徴量バージョン v3 (2026年6月1日以降)</p>
      <ConfirmDialog
        open={confirmAuto}
        onClose={() => setConfirmAuto(false)}
        title="自動適用にしますか"
        confirmLabel="自動適用にする"
        danger
        onConfirm={() => {
          update.mutate({ "analysis.weight_approval_mode": "auto" });
          setConfirmAuto(false);
        }}
      >
        Evaluatorの提案が確認なしで翌日の推奨に入ります。意図しない偏りが固定されるリスクがあります。
      </ConfirmDialog>
    </SectionCard>
  );
}

function NotificationsSection({ settings }: { settings: Settings }) {
  const online = useOnlineStatus();
  const update = useUpdateSettings();
  return (
    <SectionCard title="通知" id="notifications">
      <Toggle checked disabled={!online} onChange={() => undefined} label="バッチの失敗" />
      <Toggle checked disabled={!online} onChange={() => undefined} label="データの陳腐化" />
      <Toggle checked disabled={!online} onChange={() => undefined} label="コストのしきい値到達" />
      <Toggle
        checked={settings["notify.web_push_enabled"]}
        disabled={!online}
        onChange={(next) => update.mutate({ "notify.web_push_enabled": next })}
        label="Webプッシュ通知"
        description="iOSではホーム画面に追加したPWAでのみプッシュ通知を受け取れます。"
      />
      <Field label="Webhook URL" className="mt-3">
        <input
          className="input"
          defaultValue={settings["notify.webhook_url"]}
          disabled={!online}
          placeholder="未設定"
          onBlur={(e) => update.mutate({ "notify.webhook_url": e.target.value })}
        />
        <span className="text-caption text-fg-muted">
          確実に通知を受け取りたい場合はWebhookを推奨します。SlackやDiscordのIncoming Webhook URLを設定してください。
        </span>
      </Field>
      <p className="text-caption text-fg-tertiary mt-3">
        通知しない時間帯 {settings["notify.quiet_hours"].from} - {settings["notify.quiet_hours"].to}
      </p>
    </SectionCard>
  );
}

function SystemSection() {
  const healthQ = useSystemHealth();
  const diag = useRunDiagnostics();
  const backup = useRunBackup();
  const rebuild = useRebuildVectors();
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const [typed, setTyped] = useState("");

  return (
    <SectionCard title="システム" id="system">
      <QuerySection label="システム情報" query={healthQ} skeleton={<SkeletonTable rows={8} cols={2} />}>
        {(h) => (
          <dl className="grid grid-cols-2 gap-3 text-body-sm">
            <div>
              <dt className="text-caption text-fg-tertiary">バージョン</dt>
              <dd className="num">
                {h.version} (commit {h.commit})
              </dd>
            </div>
            <div>
              <dt className="text-caption text-fg-tertiary">Python</dt>
              <dd className="num">{h.python_version}</dd>
            </div>
            <div>
              <dt className="text-caption text-fg-tertiary">Node.js</dt>
              <dd className="num">{h.node_version}</dd>
            </div>
            <div>
              <dt className="text-caption text-fg-tertiary">実行環境</dt>
              <dd>{h.os_ja}</dd>
            </div>
            <div>
              <dt className="text-caption text-fg-tertiary">ストレージ</dt>
              <dd>{h.db_sizes_ja}</dd>
            </div>
            <div>
              <dt className="text-caption text-fg-tertiary">最終バックアップ</dt>
              <dd>{h.last_backup_ja}</dd>
            </div>
          </dl>
        )}
      </QuerySection>
      {healthQ.error ? <p className="text-caption text-status-warning">システム情報を取得できませんでした</p> : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => backup.mutate()} className="hidden desktop:inline-flex">
          いますぐバックアップ
        </Button>
        <Button variant="secondary" onClick={() => setConfirmRebuild(true)} className="hidden desktop:inline-flex">
          ベクトルストアを再構築
        </Button>
        <Button variant="secondary" onClick={() => diag.mutate()}>
          診断を実行
        </Button>
      </div>
      <p className="text-caption text-fg-tertiary desktop:hidden mt-2">この操作はデスクトップから実行してください</p>
      {diag.data?.data.report_ja ? (
        <pre className="mt-3 whitespace-pre-wrap text-caption text-fg-secondary">{diag.data.data.report_ja}</pre>
      ) : null}
      <ConfirmDialog
        open={confirmRebuild}
        onClose={() => setConfirmRebuild(false)}
        title="ベクトルストアを再構築しますか"
        confirmLabel="再構築"
        danger
        disabled={typed !== "再構築"}
        onConfirm={() => {
          rebuild.mutate();
          setConfirmRebuild(false);
        }}
      >
        推定 18分 · 推定コスト $0.42。確認のため「再構築」と入力してください。
        <input className="input mt-2" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </ConfirmDialog>
    </SectionCard>
  );
}

function SettingsInner() {
  const qc = useQueryClient();
  const [section, setSection] = useQueryParamState<Section>("section", SECTIONS, "display");
  const settingsQ = useSettingsQuery();
  const update = useUpdateSettings();
  const online = useOnlineStatus();
  const prefs = usePrefs();

  useEffect(() => {
    const data = settingsQ.data?.data;
    if (!data) return;
    prefs.setPrefs({
      directionColors: data["ui.direction_colors"],
      theme: data["ui.theme"],
      density: data["ui.density"],
      market: resolveMarket(data["ui.default_market"]),
    });
    // 初回のサーバ値だけ取り込む
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settingsQ.data]);

  return (
    <>
      <PageHeader
        title="設定"
        asOf={settingsQ.data?.meta.as_of}
        computedAt={settingsQ.data?.meta.computed_at}
        refreshing={update.isPending}
        onRefresh={() => void qc.invalidateQueries({ queryKey: ["settings"] })}
        description={update.isPending ? "保存中…" : update.isSuccess ? "保存しました" : "変更は自動保存されます"}
      />
      <div className="grid gap-4 desktop:grid-cols-12">
        <nav className="desktop:col-span-3 card p-2" aria-label="設定セクション">
          <ul className="desktop:sticky desktop:top-0">
            {SECTIONS.map((id) => (
              <li key={id}>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 rounded-md tap-target text-body-sm"
                  aria-current={section === id ? "page" : undefined}
                  onClick={() => setSection(id)}
                >
                  {SECTION_LABEL[id]}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="desktop:col-span-6 space-y-4 max-w-xl">
          <QuerySection label="設定" query={settingsQ} skeleton={<SkeletonCards count={3} />}>
            {(s) => (
              <>
                {section === "display" ? <DisplaySection settings={s} /> : null}
                {section === "cost" ? <CostSection settings={s} /> : null}
                {section === "data" ? <DataSection settings={s} /> : null}
                {section === "analysis" ? <AnalysisSection settings={s} /> : null}
                {section === "notifications" ? <NotificationsSection settings={s} /> : null}
                {section === "system" ? <SystemSection /> : null}
              </>
            )}
          </QuerySection>
          {update.isError ? (
            <Notice tone="danger">
              設定を保存できませんでした。変更は適用されていません。
              <Button variant="secondary" className="mt-2" onClick={() => update.reset()}>
                再試行
              </Button>
            </Notice>
          ) : null}
          {!online ? <Notice tone="warning">オフラインではサーバ側の設定を変更できません。方向色とテーマは端末に保存されます。</Notice> : null}
        </div>
        <aside className="hidden desktop:block desktop:col-span-3">
          <SectionCard title="プレビュー">
            <p className="text-caption text-fg-tertiary mb-2">現在の方向色での表示</p>
            <DirectionPreview />
            <p className="text-caption text-fg-secondary mt-3">注目 · 7203 トヨタ自動車</p>
          </SectionCard>
        </aside>
      </div>
    </>
  );
}

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <LoadingRegion label="設定">
          <Skeleton className="h-10 w-32" />
          <SkeletonCards count={3} className="mt-4" />
        </LoadingRegion>
      }
    >
      <SettingsInner />
    </Suspense>
  );
}
