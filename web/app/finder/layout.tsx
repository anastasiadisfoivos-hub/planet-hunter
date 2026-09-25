import { FinderHeader } from "@/components/finder/FinderNav";
import s from "@/components/lab/lab.module.css";

export default function FinderLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={s.page}>
      <FinderHeader />
      <main className={s.main}>{children}</main>
    </div>
  );
}
