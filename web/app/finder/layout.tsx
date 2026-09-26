import { TopBar } from "@/components/shell/TopBar";
import s from "@/components/lab/lab.module.css";

export default function FinderLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={s.page}>
      <TopBar />
      <main className={s.main}>{children}</main>
    </div>
  );
}
