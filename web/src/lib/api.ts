const BASE = "";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => getJson<Record<string, unknown>>("/api/meta"),
  overview: () => getJson<Record<string, unknown>>("/api/overview"),
  segments: () => getJson<Record<string, unknown>>("/api/segments"),
  segmentCustomers: (id: number) =>
    getJson<Record<string, unknown>>(`/api/segments/${id}/customers?limit=40`),
  customers: (q?: string) =>
    getJson<Record<string, unknown>>(
      q ? `/api/customers?q=${encodeURIComponent(q)}&limit=50` : "/api/customers?limit=50"
    ),
  customer: (id: number) => getJson<Record<string, unknown>>(`/api/customers/${id}`),
  products: () => getJson<Record<string, unknown>>("/api/products"),
  project: () => getJson<Record<string, unknown>>("/api/project"),
  uploadPolicy: () => getJson<Record<string, unknown>>("/api/upload/policy"),
  uploadOverview: (sid: string) =>
    getJson<Record<string, unknown>>(`/api/upload/${sid}/overview`),
  uploadSegments: (sid: string) =>
    getJson<Record<string, unknown>>(`/api/upload/${sid}/segments`),
  uploadSegmentCustomers: (sid: string, id: number) =>
    getJson<Record<string, unknown>>(
      `/api/upload/${sid}/segments/${id}/customers?limit=40`
    ),
  uploadCustomers: (sid: string, q?: string) =>
    getJson<Record<string, unknown>>(
      q
        ? `/api/upload/${sid}/customers?q=${encodeURIComponent(q)}&limit=50`
        : `/api/upload/${sid}/customers?limit=50`
    ),
  uploadCustomer: (sid: string, id: number) =>
    getJson<Record<string, unknown>>(`/api/upload/${sid}/customers/${id}`),
  uploadProducts: (sid: string) =>
    getJson<Record<string, unknown>>(`/api/upload/${sid}/products`),
};

export function formatMoney(
  amount: number,
  lang: string,
  currencyCode: string | null | undefined
): string {
  const locale = lang === "ar" ? "ar-EG" : "en-GB";
  const n = new Intl.NumberFormat(locale, {
    numberingSystem: "latn",
    maximumFractionDigits: 0,
  }).format(Number.isFinite(amount) ? amount : 0);
  if (!currencyCode || currencyCode === "UNSPECIFIED") {
    return `${n} (source)`;
  }
  return `${currencyCode} ${n}`;
}
