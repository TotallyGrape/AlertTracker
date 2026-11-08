import { useRef, useState, type KeyboardEvent } from 'react';
import { ResidentScreen } from './screens/ResidentScreen';
import { CoordinatorScreen } from './screens/CoordinatorScreen';
import { ResponderScreen } from './screens/ResponderScreen';
import { DallasMap } from './components/DallasMap';
import { LiveMap } from './components/LiveMap';
import './styles.css';

const tabs = [
  { id: 'resident', label: 'Resident', screen: ResidentScreen },
  { id: 'coordinator', label: 'Coordinator', screen: CoordinatorScreen },
  { id: 'responder', label: 'Responder', screen: ResponderScreen },
] as const;

export default function App() {
  const [active, setActive] = useState(0);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const Screen = tabs[active].screen;

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    setActive(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="brand"><span className="brand-symbol" aria-hidden="true">✳</span><span>Texas<span className="brand-light">Response</span></span></div>
        <span className="preview-badge"><span /> Workspace preview</span>
      </header>
      <main className="workspace">
        <div className="workspace-heading"><span className="eyebrow">DALLAS, TEXAS</span><span className="workspace-label">Community response workspace</span></div>
        <nav className="tab-bar" role="tablist" aria-label="Workspace views">
          {tabs.map((tab, index) => (
            <button key={tab.id} ref={element => { tabRefs.current[index] = element; }}
              id={`tab-${tab.id}`} role="tab" type="button" aria-selected={active === index}
              aria-controls={`panel-${tab.id}`} tabIndex={active === index ? 0 : -1}
              onClick={() => setActive(index)} onKeyDown={event => handleKeyDown(event, index)}>
              <span className="tab-number">0{index + 1}</span>{tab.label}
            </button>
          ))}
        </nav>
        {import.meta.env.VITE_SPACETIMEDB_ENABLED === 'true' ? <LiveMap /> : <DallasMap />}
        {tabs.map((tab, index) => (
          <section key={tab.id} id={`panel-${tab.id}`} role="tabpanel" aria-labelledby={`tab-${tab.id}`} hidden={active !== index} tabIndex={0}>
            {active === index && <Screen />}
          </section>
        ))}
      </main>
      <footer className="site-footer"><span>Built around people. Ready for what comes next.</span><span>Texas Response <span className="footer-dot">/</span> Dallas pilot</span></footer>
    </div>
  );
}
