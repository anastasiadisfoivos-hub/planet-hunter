import { TopBar } from "@/components/shell/TopBar";

export default function FinderLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <TopBar />
      <main className="wrap" style={{ paddingBottom: "var(--section-app)" }}>
        {children}
      </main>
    </>
  );
}
