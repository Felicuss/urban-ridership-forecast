# TiRex-2 в Docker с GPU: бэктест на 4 фолдах и прогноз на ноябрь-декабрь.
# Запуск из любой папки:
#   powershell -ExecutionPolicy Bypass -File D:\projects_2\hakaton_moskovskogo_transporta_2026\analysis\docker\run_tirex2.ps1
# Нужны Docker Desktop с поддержкой GPU (WSL2) и uv. Образ ghcr.io/nx-ai/tirex2-gpu весит около 10 ГБ.

$ErrorActionPreference = 'Stop'
$Image = 'ghcr.io/nx-ai/tirex2-gpu:latest'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Analysis = Join-Path $Root 'analysis'
$Io = Join-Path $Root 'data\fm_io'
$Code = Join-Path $Root 'analysis\docker'
$env:PYTHONIOENCODING = 'utf-8'

function Step([string]$Text) { Write-Host "`n== $Text" -ForegroundColor Cyan }
function Check([string]$What) { if ($LASTEXITCODE -ne 0) { throw "$What завершился с кодом $LASTEXITCODE" } }

$started = Get-Date

Step '1/5 Входные данные для модели (data\fm_io\inputs)'
if (Test-Path (Join-Path $Io 'inputs\final.npz')) {
    Write-Host 'Уже выгружены, пропускаю.'
} else {
    Push-Location $Analysis
    uv run python s13_tirex2_docker.py export; Check 'export'
    Pop-Location
}

Step '2/5 Скачивание образа (прогресс по слоям ниже)'
docker pull $Image; Check 'docker pull'

Step '3/5 Проверка GPU внутри контейнера'
$probe = "import torch; a = torch.cuda.get_arch_list(); " +
         "print('torch', torch.__version__, 'cuda', torch.version.cuda, 'gpu available', torch.cuda.is_available()); " +
         "print('device', torch.cuda.get_device_name(0), 'capability', torch.cuda.get_device_capability(0)); " +
         "print('arch list', a); print('OK: sm_120 (Blackwell) supported' if 'sm_120' in a else 'WARNING: no sm_120 in this torch build')"
docker run --rm --gpus all $Image python -c $probe; Check 'проверка GPU'

Step '4/5 Прогноз TiRex-2 на GPU (3 варианта x 5 окон)'
docker run --rm --gpus all `
    -e HF_HOME=/work/hf-cache `
    -v "${Io}:/work" `
    -v "${Code}:/code:ro" `
    $Image python /code/tirex2_forecast.py
Check 'прогноз TiRex-2'

Step '5/5 Оценка на фолдах и сводка с остальными моделями'
Push-Location $Analysis
uv run python s13_tirex2_docker.py collect; Check 'collect'
uv run python s11_ensembles.py; Check 'ансамбли'
Pop-Location

$minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
Write-Host "`nГотово за $minutes мин. Таблицы: docs\analysis\tables\backtest_fm_tirex2.csv и backtest_ensembles.csv" -ForegroundColor Green
