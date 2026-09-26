import { LabFrame } from "@/components/lab/LabFrame";
import { TopBar } from "@/components/shell/TopBar";

export default function LabLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <TopBar overAt="/lab" />
      <LabFrame>{children}</LabFrame>
    </>
  );
}
