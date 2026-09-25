#!/usr/bin/env bash
# Замер для README: k6 в контейнере против nginx, параллельно раз в 2 секунды пишется загрузка
# процессора и память реплик api. Итог: deploy/k6/results/summary.json и stats.csv.
#   docker compose up -d --scale api=N    (стек должен быть уже запущен, k6 его не трогает)
#   RATES=100,300,500 ./deploy/k6/run-load.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p deploy/k6/results
stats=deploy/k6/results/stats.csv
echo "ts;container;cpu;mem" > "$stats"
(
  while true; do
    docker stats --no-stream --format "{{.Name}};{{.CPUPerc}};{{.MemUsage}}" \
      | grep -- '-api-' | sed "s/^/$(date +%s);/" >> "$stats" || true
    sleep 2
  done
) &
sampler=$!
trap 'kill $sampler 2>/dev/null || true' EXIT
start=$(date +%s)
K6_RATES="${RATES:-100,300,500}" docker compose --profile load run --rm --no-deps k6
echo "start=$start" > deploy/k6/results/started_at.txt
