import { PageSkeleton } from "@/components/PageSkeleton";

export default function UploadLoading() {
  return (
    <main className="main page-enter">
      <PageSkeleton variant="form" label="Loading upload" />
    </main>
  );
}
