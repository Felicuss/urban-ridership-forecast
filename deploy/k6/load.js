// Нагрузочный замер в открытой модели: запросы приходят с постоянной частотой независимо от того,
// как быстро отвечает сервис (constant-arrival-rate), поэтому хвосты задержек не занижаются.
// Разогрев 30 с, дальше по 60 с на каждой частоте из RATES. Смесь запросов как у диспетчера:
// 60 % маршрут на сутки, 25 % остановка, 10 % сценарий с новыми ползунками, 5 % выгрузка CSV.
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const RATES = (__ENV.RATES || '100,300,500').split(',').map(Number);
const WARMUP_S = 30;
const STAGE_S = 60;
const ROUTES = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50];

function stageScenarios() {
  const scenarios = {
    warmup: { executor: 'constant-arrival-rate', rate: 50, timeUnit: '1s', duration: `${WARMUP_S}s`,
      preAllocatedVUs: 20, maxVUs: 200 },
  };
  RATES.forEach((rate, i) => {
    scenarios[`rps${rate}`] = { executor: 'constant-arrival-rate', rate, timeUnit: '1s', duration: `${STAGE_S}s`,
      startTime: `${WARMUP_S + i * STAGE_S}s`, preAllocatedVUs: Math.ceil(rate / 5) + 10, maxVUs: rate * 2 };
  });
  return scenarios;
}

function stageThresholds() {
  const t = {};
  RATES.forEach((rate) => {
    t[`http_req_duration{scenario:rps${rate}}`] = ['p(95)<200'];
    t[`http_req_failed{scenario:rps${rate}}`] = ['rate<0.01'];
    t[`iterations{scenario:rps${rate}}`] = ['count>0'];
    t[`dropped_iterations{scenario:rps${rate}}`] = ['count>=0'];
    ['route', 'stop', 'scenario', 'export'].forEach((type) => {
      t[`http_req_duration{scenario:rps${rate},type:${type}}`] = ['max>=0'];
    });
  });
  return t;
}

export const options = {
  scenarios: stageScenarios(),
  thresholds: stageThresholds(),
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  discardResponseBodies: true,
};

export function setup() {
  const res = http.get(`${BASE}/api/v1/stops`, { responseType: 'text' });
  check(res, { 'stops loaded': (r) => r.status === 200 });
  return { stops: JSON.parse(res.body).map((s) => s.id) };
}

const pick = (list) => list[Math.floor(Math.random() * list.length)];

function randomDate() {
  const day = new Date(Date.UTC(2025, 10, 1) + Math.floor(Math.random() * 61) * 86400000);
  return day.toISOString().slice(0, 10);
}

export default function (data) {
  const r = Math.random();
  let res;
  if (r < 0.6) {
    res = http.get(`${BASE}/api/v1/forecast?level=route&id=${pick(ROUTES)}&horizon=day&from=${randomDate()}`,
      { tags: { type: 'route', name: 'route' } });
  } else if (r < 0.85) {
    res = http.get(`${BASE}/api/v1/forecast?level=stop&id=${pick(data.stops)}&horizon=day&from=${randomDate()}`,
      { tags: { type: 'stop', name: 'stop' } });
  } else if (r < 0.95) {
    // новое значение ползунка почти в каждом запросе: пересчёт всей сетки, кэш почти не помогает
    const body = JSON.stringify({
      query: { level: 'route', id: String(pick(ROUTES)), horizon: 'month', from: randomDate() },
      coefficients: { level_dec: Number((0.95 + Math.random() * 0.15).toFixed(3)) },
    });
    res = http.post(`${BASE}/api/v1/forecast/scenario`, body,
      { headers: { 'Content-Type': 'application/json' }, tags: { type: 'scenario', name: 'scenario' } });
  } else {
    res = http.get(`${BASE}/api/v1/export?format=csv&level=route&ids=${pick(ROUTES)}&horizon=month&from=${randomDate()}`,
      { tags: { type: 'export', name: 'export' } });
  }
  check(res, { 'status 200': (x) => x.status === 200 });
}

function metric(data, name) {
  const m = data.metrics[name];
  return m ? m.values : {};
}

export function handleSummary(data) {
  const rows = RATES.map((rate) => {
    const s = `scenario:rps${rate}`;
    const d = metric(data, `http_req_duration{${s}}`);
    const byType = {};
    ['route', 'stop', 'scenario', 'export'].forEach((type) => {
      const v = metric(data, `http_req_duration{${s},type:${type}}`);
      byType[type] = { p95_ms: v['p(95)'], p99_ms: v['p(99)'] };
    });
    return {
      target_rps: rate,
      achieved_rps: (metric(data, `iterations{${s}}`).count || 0) / STAGE_S,
      dropped: metric(data, `dropped_iterations{${s}}`).count || 0,
      error_rate: metric(data, `http_req_failed{${s}}`).rate,
      median_ms: d.med, p95_ms: d['p(95)'], p99_ms: d['p(99)'], max_ms: d.max,
      by_type: byType,
    };
  });
  const lines = rows.map((x) => `${x.target_rps} rps: факт ${x.achieved_rps.toFixed(1)}, `
    + `p50 ${x.median_ms.toFixed(1)} мс, p95 ${x.p95_ms.toFixed(1)} мс, p99 ${x.p99_ms.toFixed(1)} мс, `
    + `ошибок ${(100 * x.error_rate).toFixed(2)} %, пропущено ${x.dropped}`);
  return {
    stdout: `${lines.join('\n')}\n`,
    '/results/summary.json': JSON.stringify({ base_url: BASE, stages: rows }, null, 2),
  };
}
