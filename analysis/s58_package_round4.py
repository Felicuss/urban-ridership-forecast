"""Package distinct experiments and retain confirmed scores by artifact hash."""
from __future__ import annotations
import hashlib
import json
import shutil
import zipfile
import numpy as np
import pandas as pd
from s52_round4_common import *


def main():
    init();g,_,_,anchor,anchor_grid=assembly_context()
    v3=pd.read_csv(ROOT/'forecasts/submission_future_facts_v3.csv',sep=';',parse_dates=['date'])
    old=g.merge(v3,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    isolated=np.where(g.route==5,old,anchor_grid)
    assert np.array_equal(isolated[g.route!=5],anchor_grid[g.route!=5])
    export('route5_weekly_fact',grid_prediction=isolated,metadata={
        'method':'Only route 5 first-week press-total correction from v3; every other route remains exactly v2',
        'factor':40000/30498,'source':'https://transport.mos.ru/mostrans/all_news/127782',
        'validation':'No route 5 observations in historical labels; effect is unidentified by the v3 score.',
        'caveat_source':'Rounded trip count and assumed reporting window; not proven identical to paid validations.'})
    parts=[]
    for path in TABLES.glob('round4_*.csv'):
        f=pd.read_csv(path)
        if {'candidate','fold','score','gain'}.issubset(f.columns):parts.append(f[['candidate','fold','score','gain']])
    result=pd.concat(parts,ignore_index=True).drop_duplicates(['candidate','fold'])
    summary=result.groupby('candidate').agg(mean_gain=('gain','mean'),worst_gain=('gain','min'),
        wins=('gain',lambda x:int((x>1e-12).sum())),active_folds=('gain',lambda x:int((abs(x)>1e-12).sum())))
    summary['october_gain']=result[result.fold=='B'].set_index('candidate').gain
    summary.to_csv(TABLES/'round4_summary.csv')
    print(summary.sort_values('mean_gain',ascending=False).round(6).to_string(),flush=True)
    for name,row in summary.iterrows():
        path=OUT/f'{name}.json'
        if path.exists():
            meta=json.loads(path.read_text());meta['development_summary']=row.to_dict()
            path.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    names=[('combined_models','Веса по маршрутам + выбор дополнительных моделей',
            'Три улучшения среди четырёх фолдов с изменениями; небольшой минус на октябре.'),
           ('catboost_20','20% CatBoost, 80% ядра v2',
            'Улучшил октябрь; на шести фолдах 3 выигрыша и 3 проигрыша.'),
           ('route5_weekly_fact','Только маршрут 5 по фактическим 40 тыс. поездок',
            'Отдельная проверка источника; локального бэктеста для этого маршрута нет.'),
           ('route_kind_weights','Веса по маршруту и типу дня',
            'Отдельная проверка ансамбля; коррелирует с вариантом 01.'),
           ('daily_optimal_25','25% обучаемой поправки дневного уровня',
            'Повышенный риск: октябрь улучшился, среднее по фолдам ухудшилось.'),
           ('restored_weekends','Только восстановленные выходные 7/50',
            'Малая поправка; историческая проверка не воспроизводит ноябрьское восстановление.')]
    submit=OUT/'submit';submit.mkdir(exist_ok=True)
    manifest=[]
    for i,(name,title,note) in enumerate(names,1):
        src=OUT/f'{name}.csv';dest=submit/f'{i:02}_{name}.csv';shutil.copyfile(src,dest)
        meta=json.loads(src.with_suffix('.json').read_text())
        for result in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()):
            if result['sha256']==meta['sha256'] and result.get('leaderboard_score') is not None:
                meta.update(status='scored',leaderboard_score=result['leaderboard_score'],evidence=result['evidence'])
        src.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
        manifest.append(dict(order=i,file=dest.name,experiment=name,description=title,note=note,
            status=meta['status'],leaderboard_score=meta.get('leaderboard_score'),sha256=meta['sha256'],
            changed_rows=meta['changed_rows'],absolute_difference=meta['absolute_difference'],
            development_summary=meta.get('development_summary')))
    (submit/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    results=json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    best=max((r for r in results if r.get('leaderboard_score') is not None),key=lambda r:r['leaderboard_score'])
    lines=['# Сабмиты после v3','',
        f"Лучший подтверждённый результат: **{best['leaderboard_score']:.5f}** (`{best['file']}`).",
        'Каждый файл — самостоятельная альтернатива v2. Загружать по очереди; предыдущие файлы не нужно смешивать вручную.',
        'Нумерация в имени файла постоянная. Номер строки на платформе меняется после загрузки: сообщайте имя файла и скор.',
        '', '| Порядок | Файл | Скор | Что проверяем | Оговорка |','|---|---|---:|---|---|']
    for item in manifest:
        lb='—' if item['leaderboard_score'] is None else f"{item['leaderboard_score']:.5f}"
        lines.append(f"| {item['order']} | [{item['file']}]({item['file']}) | {lb} | {item['description']} | {item['note']} |")
    lines+=['','## Локальные результаты относительно ядра v2',
        '', 'Это изменения скора в **процентных пунктах**, не прогноз лидерборда. Фолды уже использовались при разработке.',
        'Для весов ансамбля и выбора моделей использованы только завершившиеся предыдущие блоки целевых дат.',
        'На первых фолдах без достаточной истории оставлен v2; нулевой прирост там не считается победой.',
        '', '| Вариант | Средний Δ, п.п. | Октябрь Δ, п.п. | Худший Δ, п.п. | Побед / фолдов с изменениями |',
        '|---|---:|---:|---:|---:|']
    for item in manifest:
        s=item['development_summary']
        if s:
            lines.append(f"| {item['order']:02} | {100*s['mean_gain']:+.4f} | {100*s['october_gain']:+.4f} | {100*s['worst_gain']:+.4f} | {int(s['wins'])}/{int(s['active_folds'])} |")
        else:lines.append(f"| {item['order']:02} | нет проверки | — | — | — |")
    lines+=['','Изначальный порядок проверки: 01–06; полученные скоры приведены выше. 03 отделяет эффект №5 от поправки v3.',
        'Незагруженные варианты не имеют подтверждённого превосходства; локальные оценки отделены от лидерборда.',
        'Общая городская поправка v3 отсутствует во всех файлах. Нули бесплатного проезда сохранены.',
        'Формат, уникальность 14 640 ключей, порядок строк, неотрицательность и SHA-256 проверены.',
        '', 'Остальные исследовательские CSV лежат на уровень выше; усиленные версии CatBoost 40% и дневных поправок 50% в очередь не включены из-за слабого бэктеста.','']
    (submit/'README.md').write_text('\n'.join(lines))
    archive=ROOT/'forecasts/round4_submissions.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(submit.iterdir()):
            if path.is_file():z.write(path,path.name)
    # Verify every experiment, not only the six files in the upload queue.
    for path in OUT.glob('*.csv'):
        frame=pd.read_csv(path,sep=';')
        ref=pd.read_csv(ANCHOR,sep=';')
        assert frame[['route','date','hour']].equals(ref[['route','date','hour']]),path
        assert len(frame)==14640 and not frame.duplicated(['route','date','hour']).any()
        assert frame.prediction.dtype.kind in 'iu' and (frame.prediction>=0).all()
        assert (frame.loc[(frame.date=='2025-12-31')&(frame.hour>=20),'prediction']==0).all()
        m=json.loads(path.with_suffix('.json').read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest()==m['sha256']
    assert hashlib.sha256(ANCHOR.read_bytes()).hexdigest()==ANCHOR_SHA
    print('Packaged',len(manifest),'submissions:',archive,flush=True)


if __name__=='__main__':main()
