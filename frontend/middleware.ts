import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const password = process.env.ATG_APP_PASSWORD;
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
      // Fall through to the authentication challenge for malformed headers.
    }
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Academic Tour Guide"',
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
