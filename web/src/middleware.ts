import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Stitch HTML exports live under /stitch/* for reference / Streamlit embeds.
 * The live product UI is the Next.js App Router (upload → clean → dashboard).
 * Do not rewrite product routes to static Stitch shells — that breaks E2E and
 * the React upload journey.
 */
export function middleware(_request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [],
};
