type IntroProps = { eyebrow: string; title: string; description: string };

export function ScreenIntro({ eyebrow, title, description }: IntroProps) {
  return <div className="screen-intro"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="intro-description">{description}</p></div>;
}

export function EmptyPanel({ title, description, label }: { title: string; description: string; label: string }) {
  return (
    <article className="panel">
      <div className="panel-heading"><h2>{label}</h2><span className="empty-count">—</span></div>
      <div className="empty-state">
        <span className="empty-icon" aria-hidden="true"><svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="5" y="4" width="14" height="17" rx="3" /><path d="M9 4V2h6v2M9 10h6M9 14h6" /></svg></span>
        <h3>{title}</h3><p>{description}</p>
      </div>
    </article>
  );
}
