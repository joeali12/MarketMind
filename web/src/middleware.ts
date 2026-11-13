import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Exact Stitch export screens — same HTML as static/stitch and the Downloads pack. */
const STITCH: Record<string, string> = {
  "/": "/stitch/welcome_upload_pipeline.html",
  "/upload": "/stitch/welcome_upload_pipeline.html",
  "/file-understanding": "/stitch/file_understanding_setup.html",
  "/cleaning": "/stitch/data_cleaning_review.html",
  "/store": "/stitch/store_dashboard.html",
};

export function middleware(request: NextRequest) {
  const dest = STITCH[request.nextUrl.pathname];
  if (!dest) return NextResponse.next();
  return NextResponse.rewrite(new URL(dest, request.url));
}

export const config = {
  matcher: ["/", "/upload", "/file-understanding", "/cleaning", "/store"],
};
