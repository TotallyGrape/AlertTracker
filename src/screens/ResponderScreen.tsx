import { EmptyPanel, ScreenIntro } from '../components/WorkspaceParts';

export function ResponderScreen() {
  return <>
    <ScreenIntro eyebrow="READY TO MAKE A DIFFERENCE" title="Your next step, in view." description="A dedicated space for your team, your assignments, and the people you support." />
    <div className="panel-grid">
      <EmptyPanel label="Your assignments" title="Every response starts with a task." description="Assigned requests and their details will appear here." />
      <EmptyPanel label="Your team" title="Better prepared, together." description="Your team profile and availability will appear here." />
    </div>
    <p className="screen-note">Clear information for the people on the ground.</p>
  </>;
}
