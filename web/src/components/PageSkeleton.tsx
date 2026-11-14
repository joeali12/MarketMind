/** Reserved-space loading placeholders — avoid content jump (ui-ux-pro-max). */

type PageSkeletonProps = {
  variant?: "dashboard" | "list" | "form";
  label?: string;
};

export function PageSkeleton({
  variant = "dashboard",
  label = "Loading",
}: PageSkeletonProps) {
  if (variant === "list") {
    return (
      <div className="skeleton-stack" role="status" aria-live="polite" aria-busy="true">
        <span className="sr-only">{label}</span>
        <div className="skeleton skeleton-title" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line short" />
        <div className="skeleton skeleton-table" />
      </div>
    );
  }
  if (variant === "form") {
    return (
      <div className="skeleton-stack" role="status" aria-live="polite" aria-busy="true">
        <span className="sr-only">{label}</span>
        <div className="skeleton skeleton-title" />
        <div className="skeleton skeleton-block" />
        <div className="skeleton skeleton-line" />
      </div>
    );
  }
  return (
    <div className="skeleton-stack" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <div className="skeleton-kpi-row" aria-hidden>
        <div className="skeleton skeleton-kpi" />
        <div className="skeleton skeleton-kpi" />
        <div className="skeleton skeleton-kpi" />
        <div className="skeleton skeleton-kpi" />
      </div>
      <div className="skeleton skeleton-chart" />
      <div className="skeleton skeleton-line" />
      <div className="skeleton skeleton-line short" />
    </div>
  );
}
