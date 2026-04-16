import Sidebar from "@/components/layout/Sidebar";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-auto bg-background">
        <div className="max-w-[1200px] mx-auto px-6 lg:px-10 py-8 page-transition">
          {children}
        </div>
      </main>
    </div>
  );
}
