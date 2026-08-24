export type Session = {
  authenticated: boolean;
  username: string;
  ai_id: string;
};

export type QuickEntry = {
  key: string;
  name: string;
  description: string;
  url: string;
};

export type Personality = {
  ai_id: string;
  name: string;
  identity: string;
  traits: string[];
  speaking_style: string;
  catchphrases: string[];
  taboos: string[];
  version: number;
  fingerprint: string;
};

export type MemoryDocument = {
  markdown: string;
  version: number;
  updated_at: string;
};

export type SelfMemory = {
  ai_id: string;
  memory: MemoryDocument | null;
};

export type PersonSummary = {
  person_id: string;
  display_name: string;
  qq: string;
  version: number;
  updated_at: string;
};

export type People = {
  ai_id: string;
  people: PersonSummary[];
};

export type PersonMemory = {
  ai_id: string;
  person: PersonSummary;
  memory: MemoryDocument;
};

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const AUTH_EXPIRED_EVENT = "ai-love:auth-expired";

export function onAuthExpired(listener: () => void): () => void {
  window.addEventListener(AUTH_EXPIRED_EVENT, listener);
  return () => window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(`/ai-love-api${path}`, {
    method: options.method ?? "GET",
    credentials: "same-origin",
    headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const payload = await response.json();
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    throw new ApiError(response.status, String(payload.detail));
  }
  return payload as T;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function qqAvatarUrl(qq: string): string {
  const query = new URLSearchParams({ b: "qq", nk: qq, s: "100" });
  return `https://q1.qlogo.cn/g?${query.toString()}`;
}
