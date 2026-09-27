# Модели прогнозирования временных рядов для задачи трамвайных посадок: состояние на 25.09.2026

Задача: 10 почасовых рядов (январь-октябрь 2025, около 7300 точек на маршрут), прогноз на 2025-11-01 … 2025-12-31 целиком, то есть 1464 часовых шага без данных внутри горизонта. Метрика WAPE по всей сетке маршрут × дата × час. Известные будущие ковариаты: календарь и фактическая погода. Железо: RTX 5070 12 ГБ, 32 ГБ RAM, Ryzen 5600X, Windows 11, Python 3.13 через uv. Дедлайн CSV по `docs/task.md`: 27.09.2026.

Как проверялось. Версии пакетов взяты из PyPI JSON API, метаданные моделей (дата создания, лицензия, число параметров из safetensors) из Hugging Face API, релизы из GitHub API, всё 25.09.2026. Лидерборды GIFT-Eval и fev-bench я не читал с картинок: скачал сырые CSV из репозиториев Spaces и пересчитал агрегаты сам. Пересчёт сходится с цифрами из карточек моделей: t0-beta CRPS 0.474 / MASE 0.687 против 0.4738 / 0.6865 в [карточке](https://huggingface.co/theforecastingcompany/t0-beta), Toto-2.0-2.5B 0.476 / 0.696 против 0.476 / 0.696 в [карточке](https://huggingface.co/Datadog/Toto-2.0-2.5B). Всё, что подтвердить не удалось, помечено как «не подтверждено» и собрано в разделе 8.

## 1. Короткий ответ

Для нашей задачи я бы собирал ансамбль из прямой LightGBM-модели на календаре, погоде и сезонных профилях и одной-двух foundation-моделей с поддержкой будущих ковариат. Первой из foundation-моделей стоит пробовать Chronos-2: Apache-2.0, нативные прошлые и будущие ковариаты, второе место на fev-bench по WAPE, ставится на Windows без компиляторов и работает и на GPU, и на CPU.

| # | Модель | Чекпойнт / пакет | Почему | Главный риск |
|---|---|---|---|---|
| 1 | Chronos-2 | `amazon/chronos-2` (119.5M), `chronos-forecasting==2.3.2` | fev-bench WAPE skill 39.4 (2-е место), на задачах с ковариатами 40.0 (2-е), hourly 48.4 (3-е); Apache-2.0 | 1024 шага за проход, 1464 только через авторегрессию или смену шага ряда |
| 2 | TimesFM 3.0 | `google/timesfm-3.0-pytorch` (330.7M), `timesfm==3.0.2` | 1-е место на fev-bench во всех срезах, которые я смотрел (WAPE, hourly, mobility, ковариаты), 1-е среди foundation-моделей на GIFT-Eval | веса под некоммерческой лицензией, см. 4.2 |
| 3 | t0-beta | `theforecastingcompany/t0-beta` (255.6M), `tfc-t0==0.5.0` | fev-bench hourly WAPE 49.8 (2-е), будущие ковариаты нативно, Apache-2.0 | релиз 16.09.2026, девять дней от роду |
| 4 | TiRex-2 | `NX-AI/TiRex-2` (38.4M + 44.1M), `tirex-2==0.2.1` | на GIFT-Eval hourly-long MASE 0.623 против 0.635 у TimesFM-3 и 0.701 у Chronos-2; ковариаты нативно, Apache-2.0 | на Windows нужен MSVC даже для CPU, для CUDA ещё и nvcc |
| 5 | LightGBM direct | `lightgbm==4.7.0` | рабочая лошадь без ограничения по горизонту; идёт в сервис 2-4 vCPU через ONNX | на fev-bench в «коробочной» конфигурации заметно слабее TSFM, нужны свои признаки |

Что пробовать первым: окно сентябрь-октябрь 2025 (обучение на январе-августе) ровно 61 день, это готовый бэктест с тем же горизонтом, что и сабмит. На нём сравнить сезонный профиль, LightGBM direct и Chronos-2 в двух постановках (почасово с авторегрессией и в виде дневных рядов, см. раздел 2), затем подобрать веса ансамбля по WAPE.

## 2. Горизонт 1464 шага не проверяет ни один лидерборд

Это главное ограничение, и оно важнее разницы в пару пунктов между моделями. В GIFT-Eval самый длинный горизонт для часовых данных равен 48 × 15 = 720 шагов ([`PRED_LENGTH_MAP` и `Term.LONG.multiplier` в data.py](https://github.com/SalesforceAIResearch/gift-eval/blob/main/src/gift_eval/data.py)). Наш горизонт вдвое длиннее. fev-bench и BOOM тоже меряют более короткие горизонты, так что позиции на лидербордах для нас только ориентир, а решает свой бэктест.

Что умеют модели по горизонту (по коду и карточкам):

| Модель | За один проход | Больше этого | Источник |
|---|---|---|---|
| Chronos-2 | 1024 (64 патча × 16) | авторегрессия по 9 квантилям с предупреждением «quality may degrade»; при fine-tune `max_output_patches` можно поднять | [config.json](https://huggingface.co/amazon/chronos-2/blob/main/config.json), [pipeline.py](https://github.com/amazon-science/chronos-forecasting/blob/main/src/chronos/chronos2/pipeline.py) |
| TimesFM 3.0 | любой, округляется вверх до кратного 64 (1464 → 1472), декодируется через CPM | ограничений в коде не нашёл | [timesfm3_forecaster.py](https://github.com/google-research/timesfm/blob/master/src/timesfm3/torch/timesfm3_forecaster.py) |
| t0-beta | до 1024 | авторегрессия | [карточка, Input Contract](https://huggingface.co/theforecastingcompany/t0-beta) |
| Toto 2.0 | не указано | для горизонтов «≳1000» рекомендуют `decode_block_size=768` | [README](https://github.com/DataDog/toto) |
| TiRex-2 | не документировано | не подтверждено | [docs](https://github.com/NX-AI/tirex-2/tree/main/docs) |
| TimesFM 2.5 | до 1k с квантильной головой | - | [README](https://github.com/google-research/timesfm) |
| FlowState r1.1 | рекомендуют не больше 30 сезонов; для часовых с суточной сезонностью это 720 | качество падает | [карточка](https://huggingface.co/ibm-granite/granite-timeseries-flowstate-r1) |
| Sundial | multi-patch 720, пример с 1440 через KV cache | - | [карточка](https://huggingface.co/thuml/sundial-base-128m) |

Три способа обойти длинный горизонт. Первые два я считаю обязательными к проверке на бэктесте, это моя рекомендация, а не измеренный факт:

1. Прямо прогнозировать 1464 часа моделью, которая это умеет (TimesFM 3.0 за проход, Chronos-2 и t0 с авторегрессией).
2. Сменить шаг ряда. Либо дневной итог по маршруту (горизонт 61, контекст около 304 точек) плюс внутрисуточный профиль по типу дня, либо 24 ряда «час суток» с дневным шагом, которые Chronos-2 умеет прогнозировать совместно (`cross_learning`). Горизонт 61 шаг короче максимального горизонта за проход у всех моделей из таблицы выше и укладывается в горизонты GIFT-Eval (для дневных рядов там 30, 300 и 450 шагов).
3. GBM без лагов короче горизонта: признаки только календарные, погодные и профильные (средний уровень маршрута по dow × hour за последние N недель). Такой модели длина горизонта безразлична.

## 3. Лидерборды на 25.09.2026

### 3.1 fev-bench

Space [autogluon/fev-bench](https://huggingface.co/spaces/autogluon/fev-bench), последний коммит 2026-09-18 «Add t0-beta» (до этого 2026-08-28 «Add TimesFM-3.0», 2026-08-03 «Add TS-ICL», 2026-07-02 «Add TiRex-2 results»). 100 задач, описание в [arXiv:2509.26468](https://arxiv.org/abs/2509.26468). Skill score считается относительно Seasonal Naive и от добавления новых моделей не меняется, win rate меняется ([описание метрик в src/strings.py](https://huggingface.co/spaces/autogluon/fev-bench/blob/main/src/strings.py)).

Для нас это самый полезный лидерборд: в нём есть отдельная таблица по WAPE, то есть по нашей метрике, и срезы по часовой частоте, домену mobility и задачам с ковариатами. Цифры ниже из [tables/full/leaderboard_WAPE.csv](https://huggingface.co/spaces/autogluon/fev-bench/blob/main/tables/full/leaderboard_WAPE.csv) и соседних файлов.

| Модель | WAPE: win rate / skill (все 100 задач) | WAPE skill, hourly | WAPE skill, mobility | WAPE skill, с ковариатами | SQL skill (вероятностный) | Медиана инференса, с (`median_inference_time_s_per100`) |
|---|---|---|---|---|---|---|
| TimesFM-3 | 84.9 / 41.3 | 52.3 | 33.8 | 40.5 | 48.7 | 3.68 |
| Chronos-2 | 76.4 / 39.4 | 48.4 | 31.4 | 40.0 | 47.3 | 0.84 |
| t0-beta | 74.2 / 38.3 | 49.8 | 29.9 | 38.8 | 46.7 | 2.29 |
| TiRex-2 | 71.5 / 37.0 | 46.9 | 28.2 | 36.4 | 45.5 | 0.27 |
| Toto-2.0-2.5B | 77.1 / 36.7 | 44.0 | 29.5 | 31.8 | 44.4 | 5.58 |
| Toto-2.0-1B | 77.1 / 36.5 | 44.0 | 30.0 | 32.1 | 44.4 | 2.48 |
| Toto-2.0-313m | 74.8 / 36.2 | 43.6 | 29.6 | 31.5 | 44.2 | 1.06 |
| TabPFN-TS-3 | 62.5 / 35.9 | 45.7 | 27.0 | 37.2 | 43.1 | 234.6 |
| TS-ICL | 59.8 / 34.3 | 46.4 | 27.9 | 34.9 | 43.1 | 2.49 |
| TimesFM-2.5 | 64.1 / 33.7 | 38.8 | 30.1 | 29.5 | 42.2 | 1.87 |
| TiRex | 64.2 / 33.6 | 38.2 | 28.7 | 30.4 | 42.6 | 0.24 |
| FlowState | 57.8 / 33.1 | 37.6 | 28.5 | 28.9 | 39.9 | 2.29 |
| Moirai-2.0 | 50.2 / 30.6 | 37.0 | 25.2 | 28.8 | 39.3 | 0.35 |
| Chronos-Bolt | 48.3 / 29.8 | 37.3 | 25.2 | 26.2 | 38.9 | 0.26 |
| Sundial-Base | 39.9 / 27.3 | 37.1 | 23.3 | - | 33.4 | 8.01 |
| CatBoost (mlforecast) | 39.6 / 25.5 | - | - | 27.6 | 23.0 | 0.31 |
| LightGBM (mlforecast) | 38.8 / 23.2 | - | - | 28.0 | 21.0 | 0.27 |
| Stat. Ensemble | 35.9 / 19.5 | - | - | - | 20.7 | 146.9 |
| Seasonal Naive | 13.8 / 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.48 |

`-` значит, что модели нет в топ-21 соответствующего среза (я выводил первые 21 строку). Порядок строк по SQL/WAPE skill примерно совпадает, но не полностью: по win rate на WAPE Toto-2.0-2.5B второй, по skill пятый.

Замечание про LightGBM и CatBoost на fev-bench: это универсальная обёртка над mlforecast с автоматическими лагами, дифференцированием и перебором препроцессинга ([models/mlforecast/model.py](https://github.com/autogluon/fev/blob/main/models/mlforecast/model.py)), без доменных признаков. Их 23-28 skill против 36-41 у топовых TSFM говорит о «коробочном» GBM, а не о GBM с календарём и погодой, собранном под конкретную задачу.

### 3.2 GIFT-Eval

Space [Salesforce/GIFT-Eval](https://huggingface.co/spaces/Salesforce/GIFT-Eval), последнее изменение 2026-09-23 (коммит «Add TW3Cast results» в [GitHub-репозитории](https://github.com/SalesforceAIResearch/gift-eval/commits/main)). 97 конфигураций, 133 сабмита с полным набором. Метрики нормализованы на Seasonal Naive и усреднены геометрически, ранг CRPS усреднён по конфигурациям, как в [src/utils.py](https://huggingface.co/spaces/Salesforce/GIFT-Eval/blob/main/src/utils.py). По умолчанию Space сортирует по MASE rank; я сортировал по CRPS rank, обе колонки есть ниже.

Верх общего списка занимают agentic-системы: STRIDE w/ Synapse (Google Cloud AI Research, CRPS rank 14.0), EXAONE-Forecast-Agent (LG AI Research, 20.1), LS-MoE, CastStar, LS-Agent. У первых двух в config.json `replication_code_available: "No"` и нет ссылок на веса, для нас они бесполезны.

Среди foundation-моделей (типы zero-shot / pretrained / fine-tuned, `testdata_leakage: No`, всего 69) картина такая:

| Место среди FM | Место в общем списке | Модель | Тип | MASE | CRPS | CRPS rank | MASE rank | MASE, только H | MASE, H + long | MASE, домен Transport |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 12 | TimesFM-3 | zero-shot | 0.667 | 0.456 | 26.8 | 28.6 | 0.643 | 0.635 | 0.543 |
| 2 | 18 | EXAONE-Forecast (кода и весов нет) | zero-shot | 0.673 | 0.460 | 30.6 | 32.6 | 0.629 | 0.615 | 0.582 |
| 3 | 22 | Toto-2.0-2.5B-FT | fine-tuned | 0.679 | 0.463 | 33.7 | 34.4 | 0.667 | 0.673 | 0.584 |
| 7 | 30 | Granite-PatchTST-FM-r2 | zero-shot | 0.685 | 0.467 | 38.4 | 40.9 | 0.669 | 0.654 | 0.583 |
| 9 | 38 | TiRex-2 (gifteval-pretrain) | pretrained | 0.678 | 0.467 | 43.6 | 45.1 | 0.631 | 0.623 | 0.576 |
| 10 | 41 | t0-beta | pretrained | 0.687 | 0.474 | 45.2 | 48.6 | 0.645 | 0.640 | 0.591 |
| 11 | 42 | Toto-2.0-2.5B | pretrained | 0.696 | 0.476 | 45.6 | 45.2 | 0.682 | 0.695 | 0.594 |
| 14 | 46 | TiRex-2 (gifteval-zs) | zero-shot | 0.697 | 0.478 | 47.5 | 52.8 | 0.632 | 0.627 | 0.580 |
| 15 | 47 | Toto-2.0-313m | pretrained | 0.703 | 0.481 | 47.7 | 49.0 | 0.689 | 0.698 | 0.602 |
| 17 | 49 | Chronos-2 | pretrained | 0.698 | 0.485 | 50.0 | 49.5 | 0.698 | 0.701 | 0.603 |
| 21 | 53 | TiRex | zero-shot | 0.716 | 0.488 | 52.2 | 59.5 | 0.686 | 0.694 | 0.613 |
| 23 | 55 | FlowState-r1.1 | zero-shot | 0.701 | 0.487 | 53.8 | 54.5 | 0.689 | 0.689 | 0.604 |
| 25 | 58 | TimesFM-2.5 | zero-shot | 0.705 | 0.490 | 54.3 | 54.6 | 0.676 | 0.675 | 0.585 |
| 27 | 60 | Timer-S1 | pretrained | 0.693 | 0.485 | 55.2 | 54.1 | 0.646 | 0.624 | 0.596 |
| 30 | 63 | Falcon-X (только API) | pretrained | 0.687 | 0.486 | 57.4 | 57.4 | 0.594 | 0.540 | 0.608 |
| 38 | 72 | Toto-Open-Base-1.0 | zero-shot | 0.750 | 0.517 | 68.1 | 74.7 | 0.726 | 0.746 | 0.632 |
| 39 | 73 | Moirai 2.0 | pretrained | 0.728 | 0.516 | 69.6 | 71.9 | 0.710 | 0.717 | 0.620 |
| 41 | 75 | TTM-R3 (pretrained) | pretrained | 0.724 | 0.520 | 72.6 | 67.7 | 0.704 | 0.702 | 0.612 |
| 48 | 84 | TabPFN-TS (v1) | zero-shot | 0.771 | 0.544 | 80.2 | 87.4 | - | - | - |
| 55 | 92 | Kairos 50m | zero-shot | 0.742 | 0.548 | 84.8 | 69.8 | - | - | - |
| 59 | 96 | Sundial base 128m | zero-shot | 0.750 | 0.559 | 87.6 | 79.9 | - | - | - |
| - | 128 | Seasonal Naive | statistical | 1.000 | 1.000 | 121.9 | 115.6 | 1.000 | 1.000 | 1.000 |

Срез H содержит 31 конфигурацию, H + long 9 (горизонт 720), Transport 15. `-` в последних трёх колонках значит «не считал». Две вещи отсюда важны для нас. На часовых длинных горизонтах TiRex-2 и t0-beta не хуже TimesFM-3, а Chronos-2 уступает им заметно (0.701 против 0.623-0.640). Из открытых моделей рядом с TiRex-2 на H + long ещё Zeus (0.621, [HF](https://huggingface.co/GestaltCog/zeus), Apache-2.0) и Timer-S1 (0.624). Лучший MASE на H + long среди не-агентных сабмитов у Falcon-X (0.540), но в [README falconx](https://github.com/ant-intl/Falcon-TST/tree/main/falconx) описан только клиент `FalconClient` к внешнему сервису, открытых весов Falcon-X на HF я не нашёл (у `ant-intl` там лежит только Falcon-TST_Large), так что данные пришлось бы отправлять на чужой сервер.

Granite-PatchTST-FM-r2 в своей [карточке](https://huggingface.co/ibm-granite/granite-timeseries-patchtst-fm-r2) называет себя моделью номер 2 среди zero-shot с кодом репликации; в моём пересчёте по CRPS rank он второй среди zero-shot с репликацией после TimesFM-3, так что утверждение сходится.

### 3.3 BOOM

Space [Datadog/BOOM](https://huggingface.co/spaces/Datadog/BOOM), последнее обновление 2026-05-12 (все коммиты того дня про Toto 2.0). Бенчмарк про observability-метрики, от наших пассажиропотоков далёк. TimesFM-3, t0 и TiRex-2 на нём не оценивались. Данные из [results/leaderboards/BOOM_leaderboard.csv](https://huggingface.co/spaces/Datadog/BOOM/blob/main/results/leaderboards/BOOM_leaderboard.csv):

| Модель | MASE | CRPS | Rank |
|---|---|---|---|
| toto_2.0_2.5b | 0.581 | 0.349 | 3.88 |
| toto_2.0_1b | 0.582 | 0.349 | 3.96 |
| toto_2.0_313m | 0.585 | 0.351 | 4.26 |
| toto_2.0_22m | 0.601 | 0.363 | 5.53 |
| Toto-Open-Base-1.0 | 0.617 | 0.375 | 6.94 |
| toto_2.0_4m | 0.624 | 0.377 | 7.17 |
| chronos_2 | 0.641 | 0.392 | 7.39 |
| timesfm_2_5_200m | 0.632 | 0.382 | 7.70 |
| moirai_2_small | 0.672 | 0.427 | 11.29 |
| seasonalnaive | 1.000 | 1.000 | 20.42 |

### 3.4 TIME

[README TimesFM](https://github.com/google-research/timesfm) заявляет первое место TimesFM 3.0 на TIME, [карточка Toto 2.0](https://huggingface.co/Datadog/Toto-2.0-2.5B) заявляет топ-3 для размеров Toto 2.0. Сам [TIME-leaderboard](https://huggingface.co/spaces/Real-TSF/TIME-leaderboard) (Space изменён 2026-03-05) я не разбирал, эти заявления не подтверждены.

## 4. Модели по отдельности

### 4.1 Сводная таблица: версии, лицензии, пакеты

Дата «последней версии» здесь это дата создания репозитория весов на HF (или релиза, если он позже). Число параметров взято из safetensors-метаданных HF API, если не сказано иное.

| Модель | Последняя версия, дата | Параметры | Лицензия весов | Коммерция | Пакет PyPI, версия, дата |
|---|---|---|---|---|---|
| TimesFM 3.0 | `google/timesfm-3.0-pytorch`, [HF](https://huggingface.co/google/timesfm-3.0-pytorch) 2026-08-24, [GitHub v3.0.0](https://github.com/google-research/timesfm/releases/tag/v3.0.0) 2026-08-28, [блог](https://research.google/blog/timesfm-3-a-zero-shot-foundation-model-for-multivariate-forecasting/) 2026-08-31 | 330.7M | [TimesFM Non-Commercial License v1.0](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE) | нет | [`timesfm` 3.0.2](https://pypi.org/project/timesfm/3.0.2/), 2026-09-09 (модуль `timesfm3` внутри колеса, проверил) |
| Chronos-2 | `amazon/chronos-2`, [HF](https://huggingface.co/amazon/chronos-2) 2025-10-30, изменён 2026-06-05; `autogluon/chronos-2-small` 28M, [HF](https://huggingface.co/autogluon/chronos-2-small) 2025-12-03 | 119.5M | Apache-2.0 | да | [`chronos-forecasting` 2.3.2](https://pypi.org/project/chronos-forecasting/2.3.2/), 2026-09-08 |
| t0-beta | `theforecastingcompany/t0-beta`, [HF](https://huggingface.co/theforecastingcompany/t0-beta) 2026-09-16, [arXiv:2609.24559](https://arxiv.org/abs/2609.24559) | 255.6M | Apache-2.0 | да | [`tfc-t0` 0.5.0](https://pypi.org/project/tfc-t0/0.5.0/), 2026-09-17 (нужно `>=0.5.0`, иначе молча портится нормализация) |
| TiRex-2 | `NX-AI/TiRex-2`, [HF](https://huggingface.co/NX-AI/TiRex-2) 2026-06-16, изменён 2026-07-21, [arXiv:2607.01204](https://arxiv.org/abs/2607.01204) | 38.4M (uni) + 44.1M (multi), по карточке | Apache-2.0 | да | [`tirex-2` 0.2.1](https://pypi.org/project/tirex-2/0.2.1/), 2026-08-05 |
| Toto 2.0 | `Datadog/Toto-2.0-{4m,22m,313m,1B,2.5B}`, [HF](https://huggingface.co/Datadog/Toto-2.0-313m) 2026-04-14/17, [arXiv:2605.20119](https://arxiv.org/abs/2605.20119) | 4M … 2.45B | Apache-2.0 | да | [`toto-models` 1.0.0](https://pypi.org/project/toto-models/1.0.0/) → `toto-2` 2.0.0, 2026-06-04, Python ≥3.12 |
| Granite PatchTST-FM r2 | `ibm-granite/granite-timeseries-patchtst-fm-r2`, [HF](https://huggingface.co/ibm-granite/granite-timeseries-patchtst-fm-r2) 2026-08-07 | 384.6M | OpenMDW-1.0 или Apache-2.0 на выбор | да | [`granite-tsfm` 0.3.9](https://pypi.org/project/granite-tsfm/0.3.9/), 2026-08-28 |
| Granite TTM r3 | `ibm-granite/granite-timeseries-ttm-r3`, [HF](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r3) 2026-05-21 | 1-35M (семейство, по карточке) | Apache-2.0 | да | `granite-tsfm` 0.3.9 (рецепты «to be released») |
| FlowState r1.1 | `ibm-granite/granite-timeseries-flowstate-r1`, `revision="r1.1"`, [HF](https://huggingface.co/ibm-granite/granite-timeseries-flowstate-r1) изменён 2026-04-29 | 18.5M (r1.1, по карточке) | Apache-2.0 (Granite-версия) | да | `granite-tsfm` 0.3.9 |
| TabPFN-TS | `tabpfn-time-series` по умолчанию на TabPFN-3.5 ([HF](https://huggingface.co/Prior-Labs/tabpfn_3_5), 2026-09-09); чекпойнт TabPFN-TS-3 в [`Prior-Labs/tabpfn_3`](https://huggingface.co/Prior-Labs/tabpfn_3) | не указано | tabpfn-3/3-5-license-v1.0: только исследование и внутренняя оценка, выходы нельзя использовать для «client deliverables» | нет | [`tabpfn-time-series` 1.3.0](https://pypi.org/project/tabpfn-time-series/1.3.0/), 2026-09-17; [`tabpfn` 9.0.0](https://pypi.org/project/tabpfn/9.0.0/), 2026-09-15 |
| Timer-S1 | `bytedance-research/Timer-S1`, [HF](https://huggingface.co/bytedance-research/Timer-S1) 2026-04-09, [arXiv:2603.04791](https://arxiv.org/abs/2603.04791) | 8.3B всего, 0.75B активных (MoE) | Apache-2.0 | да | нет, `transformers~=4.57.1` + `trust_remote_code` |
| Sundial | `thuml/sundial-base-128m`, [HF](https://huggingface.co/thuml/sundial-base-128m) 2025-05-13, изменён 2026-03-09 | 128.3M | Apache-2.0 | да | нет, карточка просит `transformers==4.40.1` |
| Moirai 2.0 | `Salesforce/moirai-2.0-R-small`, [HF](https://huggingface.co/Salesforce/moirai-2.0-R-small) 2025-08-06; MoiraiAgent 2025-12-29 | 11.4M | CC-BY-NC-4.0 | нет | [`uni2ts` 2.0.0](https://pypi.org/project/uni2ts/2.0.0/), 2025-11-04 |
| Moirai-MoE | `Salesforce/moirai-moe-1.0-R-base`, [HF](https://huggingface.co/Salesforce/moirai-moe-1.0-R-base) 2024-11-01 | 935M всего | CC-BY-NC-4.0 | нет | `uni2ts` |
| TiRex (v1) | `NX-AI/TiRex`, [HF](https://huggingface.co/NX-AI/TiRex) 2025-05-26 | 35M | NXAI Community License | не проверял условия | [`tirex-ts` 1.4.2](https://pypi.org/project/tirex-ts/1.4.2/), 2026-06-09 |
| TimesFM 2.5 | `google/timesfm-2.5-200m-pytorch`, [HF](https://huggingface.co/google/timesfm-2.5-200m-pytorch) 2025-09-02 | 231.3M | Apache-2.0 | да | `timesfm` (для 2.5 путь `timesfm.TimesFM_2p5_200M_torch`) |
| Toto 1.0 | `Datadog/Toto-Open-Base-1.0`, [HF](https://huggingface.co/Datadog/Toto-Open-Base-1.0) 2025-04-30 | 151.3M | Apache-2.0 | да | [`toto-ts` 0.2.0](https://pypi.org/project/toto-ts/0.2.0/), 2026-02-26 |
| Kairos | `mldi-lab/Kairos_{10m,23m,50m}`, [HF](https://huggingface.co/mldi-lab/Kairos_50m) 2025-09-30 | 50.1M | Apache-2.0 | да | не нашёл (`kairos-ts` на PyPI нет) |
| Time-MoE | `Maple728/TimeMoE-50M`, [HF](https://huggingface.co/Maple728/TimeMoE-50M) 2024-09-21 | 113.4M всего по safetensors | Apache-2.0 | да | нет |
| Timer-XL | `thuml/timer-base-84m`, [HF](https://huggingface.co/thuml/timer-base-84m) 2024-11-23 | 84.1M | Apache-2.0 | да | нет |
| YingLong | `qcw1314/YingLong_300m`, [HF](https://huggingface.co/qcw1314/YingLong_300m) 2025-05-17 | 310.1M | CC-BY-4.0 | да, с атрибуцией | нет |
| MOMENT | `AutonLab/MOMENT-1-large`, [HF](https://huggingface.co/AutonLab/MOMENT-1-large) 2024-05-09 | 346.4M | MIT | да | [`momentfm` 0.1.4](https://pypi.org/project/momentfm/0.1.4/), 2025-03-19 |
| Lag-Llama | [HF](https://huggingface.co/time-series-foundation-models/Lag-Llama) 2024-02-07, изменён 2024-05-14 | 2.4M | Apache-2.0 | да | на PyPI нет (`lag-llama` отдаёт 404) |
| TimeGPT-2 / 2.1 | только API: `timegpt-2-mini`, `timegpt-2`, `timegpt-2-pro`, `timegpt-2-lab`, `timegpt-2.1` ([docs](https://www.nixtla.io/docs/forecasting/timegpt_2_family)); 2.1 анонсирован 2025-12-10, private preview ([блог](https://www.nixtla.io/blog/timegpt-2-1-announcement)) | - | коммерческий API | платно, доступ через поддержку | [`nixtla` 0.9.0](https://pypi.org/project/nixtla/0.9.0/), 2026-09-21 |
| TS-ICL | [GitHub EDF-Lab/ts-icl](https://github.com/EDF-Lab/ts-icl), 2026-06, [arXiv:2606.05878](https://arxiv.org/abs/2606.05878) | не проверял | некоммерческая (README) | нет | `tsicl` (версию не проверял) |
| citras-fm | [HF](https://huggingface.co/hitachi-nlp/citras-fm) 2026-06-26 | 7.2M | CC-BY-NC-SA-4.0 | нет | - |
| Zeus | [HF](https://huggingface.co/GestaltCog/zeus) 2026-07-13 | 102.1M | Apache-2.0 | да | - |
| Tafsut | [HF](https://huggingface.co/Tafsut-FM/tafsut-univariate-base) 2026-08-12 | 105.3M | MIT | да | - |
| Aurora | [HF](https://huggingface.co/DecisionIntelligence/Aurora) 2026-01-27, ICLR 2026 | не проверял | MIT | да | [`aurora-model` 0.2.0](https://pypi.org/project/aurora-model/0.2.0/), 2026-03-27 |

Новых версий Chronos-3, Moirai 2.1/3, Lag-Llama 2 или MOMENT 2 я не нашёл ни на HF (листинг по авторам amazon, Salesforce, AutonLab), ни поиском. Последний релиз `uni2ts` вышел 2025-11-04.

### 4.2 Возможности и железо

| Модель | Прошлые ковариаты | Будущие известные | Мультивариантность | Контекст | RTX 5070 12 ГБ | CPU (5600X) | fev-bench WAPE skill | GIFT-Eval, место среди FM |
|---|---|---|---|---|---|---|---|---|
| TimesFM 3.0 | да | да | да, 32 вариаты (targets + ковариаты) на проход, больше режется на чанки автоматически ([evaluator.py](https://github.com/google-research/timesfm/blob/master/src/timesfm3/torch/evaluator.py)) | 15 360 (`_MAX_CONTEXT_LENGTH`) | да, веса fp32 1.32 ГБ | да, медленнее | 41.3 (1) | 1 |
| Chronos-2 | да, вещественные и категориальные | да | да, group attention, `cross_learning` | 8192 | да, fp32 около 0.48 ГБ (расчёт) | да, карточка заявляет CPU-инференс | 39.4 (2) | 17 |
| t0-beta | да (как доп. вариаты в `context`) | да, `future_covariates [B, F, T+H]` | да, `group_ids`; не сочетается с `future_covariates` | не документировано | да, fp32 около 1.0 ГБ (расчёт) | да | 38.3 (3) | 10 |
| TiRex-2 | да | да | да | не документировано | да, но CUDA-ядро FlashRNN собирается `nvcc` при первом прогнозе, compute capability ≥8.0 ([README](https://github.com/NX-AI/tirex-2)) | да, но на Windows нужен MSVC `cl` даже на CPU ([FAQ](https://github.com/NX-AI/tirex-2/blob/main/docs/faq.md)) | 37.0 (4) | 9 (pretrain) / 14 (zs) |
| Toto 2.0 | только как вариаты | нет: «exogenous variable support are planned for a future 2.0 release» ([toto2/README](https://github.com/DataDog/toto/blob/main/toto2/README.md)) | да | не указан | 313m и 1B да; 2.5B весит 9.1 ГБ в fp32, впритык | мелкие размеры да | 36.7 (2.5B) | 11 (2.5B) |
| PatchTST-FM r2 | не упомянуты в карточке | не упомянуты | в примере только `target_columns` | 8192 | да, fp32 около 1.5 ГБ (расчёт) | да | нет на лидерборде | 7 |
| TabPFN-TS | нет (отбрасываются) | да, `future_df` | нет, каждый таргет отдельно ([README](https://github.com/PriorLabs/tabpfn-time-series)) | - | да | медленно: медиана 234.6 с на fev-bench против 0.84 с у Chronos-2 | 35.9 (TabPFN-TS-3) | 48 (v1) |
| FlowState r1.1 | нет | нет | нет | 4096 при предобучении | да | да | 33.1 | 23 |
| TTM r3 | «exogenous / control variable integration» по карточке | не уточнено | да | не указан | да | да, до 800 samples/s для Lite по карточке | нет | 41 |
| Timer-S1 | нет | нет | нет | 11 520 | нет: карточка рекомендует ≥40 ГБ VRAM | в bf16 около 16.6 ГБ весов (расчёт), теоретически влезет в 32 ГБ RAM, практически не проверял | нет | 27 |
| Moirai 2.0 | не проверял | не проверял | не проверял | не проверял | `uni2ts` 2.0.0 требует `torch<2.5`, см. раздел 7; закладываться на CPU | да, модель 11M | 30.6 | 39 |
| Toto 1.0 | да, с февраля 2026 через fine-tuning | да, `ev_fields` при fine-tuning | да | - | да | - | 31.5 | 38 |

Моё мнение о кандидатах, которое стоит проверить бэктестом.

TimesFM 3.0 лучшая модель по всем трём лидербордам, которые я проверил, и в карточке прямо сказано, что вес открыт, ковариаты есть, контекст 15 360 покрывает всю историю. Но [лицензия](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE) разрешает только «testing, evaluation, or research not tied to commercial gain», исключая «client deliverables» и «production systems»; README TimesFM это дублирует: «Commercial or production use of the default pretrained weights is not permitted». Потенциальный заказчик — ГУП «Московский метрополитен», и прогноз должен лечь в сервис для диспетчеров. Я бы не включал TimesFM 3.0 в итоговое решение без подтверждения прав на использование, а использовал бы его как эталон на бэктесте: если Chronos-2 или t0 отстают от него на наших данных на доли процента WAPE, спорить не о чем.

Chronos-2 выигрывает у остальных практичностью. Установка из PyPI без компиляции, `predict_df` принимает pandas с `future_df`, есть LoRA fine-tuning (с 2.2.0) и обучение на больших датасетах через `Chronos2Pipeline.fit()` (2.3.0, [релизы](https://github.com/amazon-science/chronos-forecasting/releases)). Слабое место видно в GIFT-Eval: на часовых длинных горизонтах он хуже TiRex-2 и t0-beta (MASE 0.701 против 0.623 и 0.640).

t0-beta появился 16.09.2026, за девять дней до этого отчёта. На fev-bench hourly он второй после TimesFM-3, на GIFT-Eval H + long близок к TiRex-2. Карточка прямо предупреждает: с `tfc-t0<0.5.0` веса загрузятся без ошибки, но нормализация будет от t0-alpha и прогноз молча испортится.

TiRex-2 для нас хорош по цифрам, но его установка на этой машине упирается в инструменты: `nvidia-smi` показывает драйвер 610.74, а `nvcc` и `cl` в PATH нет (проверил 25.09.2026). Реалистичный путь это CPU в WSL2 или Docker-образ `tirex2-cpu`/`tirex2-gpu` из [README](https://github.com/NX-AI/tirex-2).

Toto 2.0 силён на fev-bench по win rate, но будущих ковариат в 2.0 нет, и на задачах с ковариатами он проседает до 31.5-32.1 skill против 40.0 у Chronos-2. Для нас, где календарь и праздники решают, это существенно.

TabPFN-TS по умолчанию работает в режиме `CLIENT`, то есть отправляет ряды в облако Prior Labs ([README](https://github.com/PriorLabs/tabpfn-time-series)), а локальные веса TabPFN-3/3.5 некоммерческие. Для локальной работы с данными метрополитена я бы его не использовал.

## 5. Классический и ML-стек

| Пакет | Версия | Дата | Что важно для нас | Источник |
|---|---|---|---|---|
| LightGBM | 4.7.0 | 2026-07-18 | входы polars через narwhals, CUDA 13, multi-GPU через NCCL; репозиторий переехал в `lightgbm-org`, ветка `main` | [релиз](https://github.com/lightgbm-org/LightGBM/releases/tag/v4.7.0), [PyPI](https://pypi.org/project/lightgbm/4.7.0/) |
| CatBoost | 1.2.10 | 2026-02-18 | Spark 4.x, JVM `predictTransposed`; для Python ничего существенного | [релиз](https://github.com/catboost/catboost/releases/tag/v1.2.10), [PyPI](https://pypi.org/project/catboost/1.2.10/) |
| XGBoost | 3.4.1 | 2026-08-15 | патч-релиз к 3.4.0 (2026-08-04); требует Python ≥3.12 | [релиз](https://github.com/dmlc/xgboost/releases/tag/v3.4.1), [PyPI](https://pypi.org/project/xgboost/3.4.1/) |
| statsforecast | 2.1.1 | 2026-07-16 | в 2.1.0: UCM, conformal-интервалы, `simulate`, Numba объявлена устаревшей | [релиз 2.1.0](https://github.com/Nixtla/statsforecast/releases/tag/v2.1.0), [PyPI](https://pypi.org/project/statsforecast/2.1.1/) |
| mlforecast | 1.1.0 | 2026-07-10 | «Horizon Specific Features» (#585), `date_features_as_dummies`, `LookupLag`, pooled lag transforms | [релиз](https://github.com/Nixtla/mlforecast/releases/tag/v1.1.0), [PyPI](https://pypi.org/project/mlforecast/1.1.0/) |
| neuralforecast | 3.2.2 | 2026-09-08 | в 3.2.0 категориальные экзогенные для univariate-моделей, лосс FreDF; `torch>=2.9.1`, `pytorch-lightning<2.6` | [релиз 3.2.0](https://github.com/Nixtla/neuralforecast/releases/tag/v3.2.0), [PyPI](https://pypi.org/project/neuralforecast/3.2.2/) |
| nixtla (клиент TimeGPT) | 0.9.0 | 2026-09-21 | асинхронные jobs, `simulate()`, `explain()`; исправлены actuals в cross-validation | [релиз](https://github.com/Nixtla/nixtla/releases/tag/v0.9.0) |
| AutoGluon-TimeSeries | 1.6.3 | 2026-09-18 | Chronos-2 и Toto-2 в пресетах, метрика `WAPEB`; ограничения ниже | [релиз 1.6.0](https://github.com/autogluon/autogluon/releases/tag/v1.6.0), [PyPI](https://pypi.org/project/autogluon.timeseries/1.6.3/) |
| Darts | 0.47.0 | 2026-09-04 | обёртки `Chronos2Model`, `TimesFM2p5Model`, `TiRexModel` (TiRex v1), `PatchTSTFMModel`; `TimesFM3Model` пока только в master, в 0.47.0 его нет | [CHANGELOG](https://github.com/unit8co/darts/blob/master/CHANGELOG.md), [PyPI](https://pypi.org/project/darts/0.47.0/) |
| sktime | 1.2.0 | 2026-09-22 | новые обёртки TimesFM3, TiRex-2, TFC-T0, Tafsut; поддержка pandas 3 | [релиз](https://github.com/sktime/sktime/releases/tag/v1.2.0), [PyPI](https://pypi.org/project/sktime/1.2.0/) |
| fev | 0.10.0 | 2026-08-31 | библиотека оценки fev-bench, удобна для своего бэктеста | [PyPI](https://pypi.org/project/fev/0.10.0/) |

### 5.1 AutoGluon-TimeSeries 1.6.3: что внутри пресетов

Из исходников тега v1.6.3 ([hyperparameter_presets.py](https://github.com/autogluon/autogluon/blob/v1.6.3/timeseries/src/autogluon/timeseries/configs/hyperparameter_presets.py), [predictor_presets.py](https://github.com/autogluon/autogluon/blob/v1.6.3/timeseries/src/autogluon/timeseries/configs/predictor_presets.py)):

| Пресет | Гиперпараметры | Модели |
|---|---|---|
| `medium_quality` (`fast_training` теперь его алиас) | `light` | SeasonalNaive, ETS, Theta, RecursiveTabular, DirectTabular, Chronos2 (`autogluon/chronos-2-small`), Toto2 (`Toto-2.0-4m`) |
| `high_quality` | `default` | SeasonalNaive, AutoETS, DynamicOptimizedTheta, RecursiveTabular, DirectTabular, TemporalFusionTransformer, DeepAR, Chronos2 (zero-shot `chronos-2` + fine-tuned `chronos-2-small`), Toto2 (`Toto-2.0-22m`) |
| `best_quality` | `default` + `num_val_windows="auto"`, `refit_every_n_windows="auto"` | то же, что `high_quality`, с несколькими окнами валидации |
| `experimental_quality` | `experimental` | Chronos2 (zero-shot + fine-tuned small), Toto2 (`Toto-2.0-313m`) |
| `chronos2`, `chronos2_small`, `chronos2_ensemble`, `bolt_*` | - | одна модель без выбора или маленький ансамбль Chronos |

Chronos-2 в пресетах есть. По [release notes 1.6.0](https://github.com/autogluon/autogluon/releases/tag/v1.6.0) новые пресеты выигрывают у 1.5 в 65% случаев. Для нас важны зависимости `autogluon.timeseries` 1.6.3: `pandas<2.4.0`, `torch>=2.10,<2.14`, `transformers<5.15`, Python `<3.14` (PyPI requires_dist). В проекте стоит `pandas>=3.0.6` (`pyproject.toml`), значит AutoGluon живёт только в отдельном окружении и с torch 2.13.

### 5.2 Конфликты зависимостей с текущим проектом

Проект: Python 3.13, pandas 3.0.6, scikit-learn 1.9.1. По requires_dist с PyPI:

| Пакет | Ограничение | Совместим с проектом |
|---|---|---|
| `chronos-forecasting` 2.3.2 | `pandas<4,>=2.0`, `torch>=2.2,<3`, `transformers>=4.41,<6` | да |
| `timesfm` 3.0.2 | `torch>=2.0` (extra `torch`) | да |
| `tfc-t0` 0.5.0 | `torch>=2.4` | да |
| `tirex-2` 0.2.1 | `torch>=2.8`, `flashrnn>=1.0.5`, `xlstm~=2.0.3`; extra `gluonts` тянет `pandas~=2.3.3` | ядро да, extra `gluonts` нет |
| `toto-models` 1.0.0 | Python ≥3.12, `toto-2` → `torch>=2.4`, `gluonts[torch]>=0.16` | вероятно да, не ставил |
| `granite-tsfm` 0.3.9 | `torch>=2.10,<2.12`, `scikit-learn<1.8`, Python `<3.14` | нет, отдельное окружение |
| `autogluon.timeseries` 1.6.3 | `pandas<2.4`, `torch<2.14` | нет, отдельное окружение |
| `uni2ts` 2.0.0 | `torch>=2.1,<2.5`, `numpy~=1.26.0` | нет: torch 2.4 не ставится на Python 3.13 |
| `tabpfn-time-series` 1.3.0 | `tabpfn>=9.0.0`, `gluonts>=0.16` | не проверял, и лицензия мешает |

## 6. Сильный бейзлайн для часовых рядов с горизонтом в несколько недель

Прямых измерений на горизонте 1464 часа я не нашёл, поэтому ниже то, что есть, и моё мнение отдельно.

Что измерено. На fev-bench «коробочные» LightGBM и CatBoost из mlforecast дают WAPE skill 23.2 и 25.5 против 33-41 у современных TSFM, но на задачах с ковариатами разрыв меньше: 28.0 и 27.6 против 40.0 у Chronos-2 (раздел 3.1). В M5 LightGBM использовали все 50 лучших команд, победитель усреднял несколько LightGBM-моделей ([Makridakis et al., IJF 2022](https://www.sciencedirect.com/science/article/pii/S0169207021001874)). В свежем сравнении на подсчётах пешеходного потока ([arXiv:2609.16415](https://arxiv.org/abs/2609.16415), 14.09.2026) Seasonal Naive оказался сильным бейзлайном на длинном горизонте для высоконагруженных датчиков, LightGBM и CatBoost конкурентны на малонагруженных, а TimesFM и Chronos-2 лучше при богатой сезонной истории и длинном контексте. В [arXiv:2607.04919](https://arxiv.org/abs/2607.04919) (06.07.2026) foundation-модели выигрывают у классики при любой доле обучающих данных на 15 из 30 датасетов, а LoRA fine-tuning на коротких рядах может ухудшать результат.

Моё мнение: для десяти трамвайных маршрутов с десятью месяцами истории и длинным горизонтом сильный бейзлайн собирается так.

1. Сезонный профиль: медиана или среднее по маршрут × день недели × час за последние 4-8 недель, с отдельным типом дня для праздников и переносов по производственному календарю. Это ноль обучения и нижняя планка, которую любая модель обязана бить.
2. Прямая GBM-модель (LightGBM, при желании CatBoost) на признаках: маршрут, час, день недели, тип дня, праздник и соседние с ним дни, погода по часам, номер недели или тренд, уровень маршрута из профиля. Лаги короче 1464 часов не использовать, иначе на прогнозе придётся рекурсивно подставлять свои же предсказания. Таргет удобно брать как отношение к профилю или в log1p. Если закрывать и продуктовую часть, эта модель без изменений экспортируется в ONNX для сервиса на 2-4 vCPU.
3. Ансамбль GBM с одной-двумя TSFM (Chronos-2, t0-beta) с весами, подобранными по WAPE на окне сентябрь-октябрь.
4. Ночные часы ни одной модели не доверять: нули брать из профиля, прогноз обрезать снизу нулём.

Я бы поменял это мнение, если на бэктесте TSFM без GBM даст WAPE лучше ансамбля; для сезонных рядов с сильным календарным эффектом это возможно, но на ноябрь-декабрь с праздниками я бы на это не ставил.

Оговорка про погоду: в бэктесте и в сабмите мы подаём фактическую погоду за горизонт, в сервисе её заменит прогноз погоды. Эффект погоды на бэктесте поэтому будет немного оптимистичным.

## 7. PyTorch на RTX 5070 (Blackwell, sm_120)

RTX 5070 имеет compute capability 12.0 ([NVIDIA CUDA GPUs](https://developer.nvidia.com/cuda-gpus)). Локально `nvidia-smi` 25.09.2026 показывает драйвер 610.74, CUDA UMD 13.3, 12 227 MiB.

Последний PyTorch 2.14.0 вышел 2026-09-02 ([релиз](https://github.com/pytorch/pytorch/releases/tag/v2.14.0), [PyPI](https://pypi.org/project/torch/2.14.0/)). По [RELEASE.md](https://github.com/pytorch/pytorch/blob/main/RELEASE.md) для 2.14 архитектуры на Windows и Linux x86 такие:

| Сборка | Архитектуры | Blackwell 12.0 |
|---|---|---|
| CUDA 12.6.3 (`cu126`) | Maxwell … Hopper(9.0) | нет |
| CUDA 13.0.3 (`cu130`) | Turing(7.5), Ampere, Hopper, Blackwell(10.0, 12.0+PTX) | да |
| CUDA 13.2.1 (`cu132`) | то же | да |

В [индексе колёс](https://download.pytorch.org/whl/torch/) для 2.14.0 есть `win_amd64` под `cu126`, `cu130`, `cu132` для cp310-cp315; для 2.13.0 тоже `cu130` и `cu132`. CUDA 13.x требует драйвер ветки ≥580 ([CUDA release notes](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)), наш 610.74 подходит. PyPI-колесо torch под Windows идёт без CUDA, поэтому индекс нужно указать явно. Вариант из [документации uv](https://docs.astral.sh/uv/guides/integration/pytorch/) (сверено через Context7):

```toml
[tool.uv.sources]
torch = [{ index = "pytorch-cu130" }]

[[tool.uv.index]]
name = "pytorch-cu130"
url = "https://download.pytorch.org/whl/cu130"
explicit = true
```

Для разовой установки в окружение без pyproject есть `uv pip install torch --torch-backend=cu130` (опция в preview и работает только для `uv pip`). Этот сниппет я не запускал на машине.

Какой torch совместим с какими пакетами:

| Окружение | torch | Почему |
|---|---|---|
| основное (chronos, timesfm, tfc-t0, lightgbm) | 2.14.0 + cu130 | верхних ограничений нет |
| AutoGluon 1.6.3 | 2.13.x + cu130 | `torch<2.14` |
| granite-tsfm 0.3.9 | 2.11.x + cu130 | `torch<2.12`; в 2.11 есть CUDA 12.8 и 13.0 по RELEASE.md |
| uni2ts 2.0.0 (Moirai 2.0) | <2.5 | torch 2.4 по матрице RELEASE.md поддерживает Python ≤3.12 и CUDA не новее 12.4, то есть отдельный Python 3.12; поддержку sm_120 в таких сборках я не подтверждал, реалистично только CPU |
| TiRex-2 на CUDA | ≥2.8 + toolkit с тем же мажором CUDA | нужен `nvcc` и MSVC, на машине их нет |

## 8. Что не удалось подтвердить

- Максимальный контекст и горизонт за проход для t0-beta, TiRex-2 и Toto 2.0: в карточках и README не указаны.
- Как `granite-tsfm` строит 1464 шага для PatchTST-FM r2 при `prediction_length=64` в конфиге; поддержка ковариат у PatchTST-FM r2.
- Параметры, ковариаты и контекст Moirai 2.0 (карточку читал, эти поля там не описаны, код uni2ts не разбирал).
- Число параметров TabPFN-3.5, TS-ICL, Aurora.
- Условия NXAI Community License для TiRex v1 по коммерческому использованию.
- Результаты на TIME-leaderboard (только заявления TimesFM и Datadog).
- Ячейка Sundial в срезе fev-bench с ковариатами (см. примечание под таблицей 3.1).
- Совместимость `toto-models` с pandas 3 и Python 3.13 на практике: по метаданным ограничений нет, но не ставил.
- Допустимы ли для проекта некоммерческие веса (TimesFM 3.0, TabPFN-3/3.5, Moirai, TS-ICL, citras-fm). В `docs/task.md` и `docs/evaluation.md` проекта про лицензии моделей ничего нет; нужно отдельное подтверждение условий использования.
- Точный порядок в интерфейсе Space GIFT-Eval: я пересчитал агрегаты тем же методом по сырым CSV, но интерфейс дополнительно унифицирует частоты, поэтому ранги могут отличаться на единицы.

## 9. Проверка на наших данных

Лидерборды горизонт 1464 часа не меряют, поэтому три лучшие модели мы прогнали zero-shot на своём бэктесте из четырёх фолдов. Подробности и таблицы в [../analysis/README.md](../analysis/README.md), п. 4.4-4.5.

| Модель | Среднее WAPE-score по 4 фолдам | Октябрь (фолд B) | Время на 9 рядов × 1488 ч |
|---|---|---|---|
| медианный профиль 2 нед (без обучения) | 0.845 | 0.901 | меньше секунды |
| Chronos-2 + календарные ковариаты | 0.848 | 0.906 | 1-3 с |
| t0-beta + календарные ковариаты | 0.852 | 0.896 | меньше секунды |
| TimesFM 3.0 + календарные ковариаты | 0.857 | 0.901 | 3-6 с при `per_core_batch_size=1` |
| профиль 2 нед + Chronos-2 + t0-beta (Apache-2.0) | 0.857 | 0.906 | |
| t0-beta на дневных суммах × форма профиля | 0.865 | 0.903 | меньше секунды |
| Chronos-2 на дневных суммах × форма профиля | 0.859 | 0.906 | меньше секунды |
| смесь: профиль × городской уровень data.mos.ru + дневные Chronos-2 и t0-beta | 0.870 | 0.905 | |

Что подтвердилось и что нет:

- ранжирование fev-bench (TimesFM 3.0 > t0-beta ≈ Chronos-2) на наших данных сохраняется, но разрыв с медианным профилем всего 0.3-1.2 п.п.;
- весь выигрыш моделей идёт от уровня: если выровнять их прогноз по недельному уровню профиля, ни одна не лучше профиля. На длинном горизонте они тянут уровень к среднему по истории, и от точки 31.10 прогноз Chronos-2 и t0-beta в будни к концу декабря опускается до 0.85-0.89 октябрьского уровня;
- календарные ковариаты заметно помогают на фолде с праздниками (t0-beta 0.814 → 0.856);
- на дневных суммах (горизонт 31-62 шага вместо 1464) все три модели лучше, чем почасово, на 0.4-1.3 п.п., и почти не уводят уровень; часы берутся долями профиля (подробно в п. 4.7 отчёта);
- TimesFM 3.0 с настройками по умолчанию на RTX 5070 не помещается в 12 ГБ и уходит в системную память, с батчем 1 работает за секунды;
- torch 2.14.0+cu130 на Blackwell (sm_120) работает, как и указано в RELEASE.md.
- TiRex-2 проверен в Docker с GPU и отброшен: за вызов не больше 320 шагов, среднее по фолдам 0.80, лидерство на GIFT-Eval H + long на наших данных не подтвердилось.
