import { EmptyPanel, ScreenIntro } from '../components/WorkspaceParts';
import { ResidentReports } from '../components/ResidentReports';

export function ResidentScreen() {
  return <>
    <ScreenIntro eyebrow="YOUR COMMUNITY, CONNECTED" title="Support starts here." description="A place to ask for assistance and stay informed about your community." />
    {import.meta.env.VITE_SPACETIMEDB_ENABLED === 'true' && <ResidentReports />}
    <div className="panel-grid">
      {import.meta.env.VITE_SPACETIMEDB_ENABLED !== 'true' && <EmptyPanel label="Your requests" title="A little support goes a long way." description="Your assistance requests and their progress will appear here." />}
      <EmptyPanel label="Community updates" title="Room for what matters." description="Local alerts and helpful information will appear here." />
    </div>
    <p className="screen-note">If you are in immediate danger, call 911.</p>
  </>;
}
