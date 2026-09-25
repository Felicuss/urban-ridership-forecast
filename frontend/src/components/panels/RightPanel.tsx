import { Suspense, lazy } from 'react';
import { useStore, type RightTab } from '../../state/store';
import { TramDots } from '../ui/Controls';
import { ForecastTab } from './ForecastTab';
import styles from './RightPanel.module.css';

const ScenarioTab = lazy(() => import('./ScenarioTab'));
const FactorsTab = lazy(() => import('./FactorsTab'));
const ModelTab = lazy(() => import('./ModelTab'));

const TABS: { id: RightTab; label: string; hint: string }[] = [
  { id: 'forecast', label: 'Прогноз', hint: 'Посадки выбранного объекта на сутки, месяц или год' },
  { id: 'scenario', label: 'Сценарий', hint: 'Ползунки факторов и события: перекрытия, стройки' },
  { id: 'factors', label: 'Факторы', hint: 'Погода, календарь, трафик, расписание, события сети' },
  { id: 'model', label: 'Модель', hint: 'Качество прогноза и область применимости' },
];

export default function RightPanel() {
  const tab = useStore((s) => s.tab);
  const setTab = useStore((s) => s.setTab);
  const changes = useStore((s) => Object.keys(s.scenario.coefficients).length + s.scenario.events.length);
  return (
    <div className={styles.panel}>
      <div className={styles.tabs} role="tablist" aria-label="Разделы">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} title={t.hint}
            className={tab === t.id ? styles.tabOn : styles.tab} onClick={() => setTab(t.id)}>
            {t.label}
            {t.id === 'scenario' && changes > 0 && <i className={styles.dot}>{changes}</i>}
          </button>
        ))}
      </div>
      <div className={styles.body} role="tabpanel">
        <Suspense fallback={<TramDots label="Загружаем раздел" />}>
          {tab === 'forecast' && <ForecastTab />}
          {tab === 'scenario' && <ScenarioTab />}
          {tab === 'factors' && <FactorsTab />}
          {tab === 'model' && <ModelTab />}
        </Suspense>
      </div>
    </div>
  );
}
