import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const isProduction = process.env.ROADSHOW_ENV === "production";
  const password = process.env.ROADSHOW_APP_PASSWORD ?? process.env.ATG_APP_PASSWORD;
  if (isProduction && !password) {
    return new NextResponse("Roadshow access protection is not configured.", { status: 503 });
  }
  if (!password) {
    return NextResponse.next();
  }

  const authorization = request.headers.get("authorization");
  if (authorization?.startsWith("Basic ")) {
    try {
      const encoded = authorization.slice("Basic ".length);
      const [, providedPassword] = atob(encoded).split(":");
      if (providedPassword === password) {
        return NextResponse.next();
      }
    } catch {
    }
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Roadshow"',
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
