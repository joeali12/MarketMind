import { PageSkeleton } from "@/components/PageSkeleton";

export default function StoreLoading() {
  return (
    <main className="main page-enter">
      <PageSkeleton variant="dashboard" label="Loading dashboard" />
    </main>
  );
}
