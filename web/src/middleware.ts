import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Product UI is the Next.js App Router (upload → clean → dashboard).
 * Stitch HTML shells live under static/stitch for Streamlit (?stitch=1) and
 * the FastAPI /stitch mount — not under web/public.
 * Do not rewrite product routes to static Stitch shells.
 */
export function middleware(_request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [],
};
