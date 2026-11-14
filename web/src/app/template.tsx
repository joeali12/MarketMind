/**
 * App Router template remounts on navigation — drives the page-enter transition
 * (transform/opacity only, ~220ms, respects prefers-reduced-motion via CSS).
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <div className="page-enter" data-motion="route">
      {children}
    </div>
  );
}
