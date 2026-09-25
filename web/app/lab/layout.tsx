import { LabHeader } from "@/components/lab/LabNav";
import s from "@/components/lab/lab.module.css";

export default function LabLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={s.page}>
      <LabHeader />
      <main className={s.main}>{children}</main>
    </div>
  );
}
