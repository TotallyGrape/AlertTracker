import { EmptyPanel, ScreenIntro } from '../components/WorkspaceParts';

export function CoordinatorScreen() {
  return <>
    <ScreenIntro eyebrow="THE BIGGER PICTURE" title="Bring the response together." description="One shared space for community needs, response teams, and the next steps." />
    <div className="panel-grid glass-stagger">
      <EmptyPanel label="Incident overview" title="The picture starts here." description="Incidents and requests needing attention will appear here." />
      <EmptyPanel label="Response teams" title="A place for your people." description="Team availability and assignments will appear here." />
    </div>
    <p className="screen-note">A shared view. A more coordinated response.</p>
  </>;
}
