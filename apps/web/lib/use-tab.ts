"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** URL のタブ・フィルタを `?key=` と同期する。仕様のルートパラメータ用。 */
export function useQueryParamState<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T,
): [T, (next: T) => void] {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = search.get(key);
  const value = (raw && (allowed as readonly string[]).includes(raw) ? raw : fallback) as T;

  const setValue = useCallback(
    (next: T) => {
      const sp = new URLSearchParams(search.toString());
      if (next === fallback) sp.delete(key);
      else sp.set(key, next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [fallback, key, pathname, router, search],
  );

  return [value, setValue];
}

export function useOptionalQueryParam(key: string): [string | null, (next: string | null) => void] {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = search.get(key);

  const setValue = useCallback(
    (next: string | null) => {
      const sp = new URLSearchParams(search.toString());
      if (!next) sp.delete(key);
      else sp.set(key, next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [key, pathname, router, search],
  );

  return [value, setValue];
}
