import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
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
  const [active, setActive] = useState(() => Math.max(0, tabs.findIndex(tab => `#${tab.id}` === window.location.hash)));
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const Screen = tabs[active].screen;
  function selectTab(index: number) {
    setActive(index);
    window.history.replaceState(null, '', `#${tabs[index].id}`);
  }
  useEffect(() => {
    const syncHash = () => setActive(Math.max(0, tabs.findIndex(tab => `#${tab.id}` === window.location.hash)));
    window.addEventListener('hashchange', syncHash);
    return () => window.removeEventListener('hashchange', syncHash);
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    selectTab(next);
    tabRefs.current[next]?.focus();
  }
  const map = <div key="map">{import.meta.env.VITE_SPACETIMEDB_ENABLED === 'true' ? <LiveMap /> : <DallasMap />}</div>;
  const panels = <div key="panels">{tabs.map((tab, index) => (
    <section key={tab.id} id={`panel-${tab.id}`} role="tabpanel" aria-labelledby={`tab-${tab.id}`} hidden={active !== index} tabIndex={0}>
      {active === index && <div className="glass-pop-in" key={tab.id}><Screen /></div>}
    </section>
  ))}</div>;

  return (
    <div className="app-shell">
      <div className="aurora" aria-hidden="true" />
      <header className="site-header glass--strong">
        <div className="brand"><span className="brand-symbol" aria-hidden="true">✳</span><span>Rally <span className="brand-light">Point</span></span></div>
        <span className="preview-badge glass-badge"><span className="glass-dot glass-dot--live" /> Workspace preview</span>
      </header>
      <main className="workspace">
        <div className="workspace-heading"><span className="eyebrow">Dallas, Texas</span><span className="workspace-label">Community response workspace</span></div>
        <nav className="tab-bar glass-segmented" role="tablist" aria-label="Workspace views"
          style={{ '--count': tabs.length, '--index': active } as CSSProperties}>
          {tabs.map((tab, index) => (
            <button key={tab.id} ref={element => { tabRefs.current[index] = element; }}
              id={`tab-${tab.id}`} role="tab" type="button" aria-selected={active === index}
              aria-controls={`panel-${tab.id}`} tabIndex={active === index ? 0 : -1}
              onClick={() => selectTab(index)} onKeyDown={event => handleKeyDown(event, index)}>
              <span className="tab-number">0{index + 1}</span>{tab.label}
            </button>
          ))}
        </nav>
        {active === 2 ? [panels, map] : [map, panels]}
      </main>
      <footer className="site-footer glass--subtle"><span>Built around people. Ready for what comes next.</span><span>Rally Point <span className="footer-dot">/</span> Dallas pilot</span></footer>
    </div>
  );
}
