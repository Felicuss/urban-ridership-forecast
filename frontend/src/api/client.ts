import createClient from 'openapi-fetch';
import type { components, paths } from './schema';

// Клиент по схеме OpenAPI сервиса (/api/v1/openapi, типы: npm run api:types).
export const api = createClient<paths>({ baseUrl: '' });

export type Schemas = components['schemas'];

/** Ошибка API в формате Problem Details (RFC 9457). */
export class ApiError extends Error {
  readonly status: number;
  readonly errors: { field: string; message: string }[];

  constructor(status: number, detail: string, errors: { field: string; message: string }[] = []) {
    super(detail);
    this.status = status;
    this.errors = errors;
  }
}

interface Problem {
  detail?: string;
  title?: string;
  errors?: { field: string; message: string }[];
}

export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined) return result.data;
  const problem = (result.error ?? {}) as Problem;
  throw new ApiError(result.response.status, problem.detail ?? problem.title ?? 'Сервис не ответил',
    problem.errors ?? []);
}

/** Статичные JSON сервиса (сеть, факторы) отдаются байтами с ETag, openapi-fetch их не типизирует. */
export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new ApiError(res.status, `${url}: ${res.status}`);
  return (await res.json()) as T;
}
