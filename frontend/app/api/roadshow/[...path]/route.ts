import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DEFAULT_BACKEND_API_BASE_URL = "http://127.0.0.1:8000/api";
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

type ProxyContext = {
  params: Promise<{ path?: string[] }>;
};

function backendApiBaseUrl(): string {
  return (process.env.ROADSHOW_BACKEND_API_BASE_URL || DEFAULT_BACKEND_API_BASE_URL).replace(/\/+$/, "");
}

function backendApiToken(): string | null {
  return process.env.ROADSHOW_API_ACCESS_TOKEN || process.env.ATG_API_ACCESS_TOKEN || null;
}

function targetUrl(request: NextRequest, pathParts: string[]): string {
  const encodedPath = pathParts.map((part) => encodeURIComponent(part)).join("/");
  const url = new URL(`${backendApiBaseUrl()}/${encodedPath}`);
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });
  return url.toString();
}

function proxyRequestHeaders(request: NextRequest, token: string | null): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (HOP_BY_HOP_HEADERS.has(lowerKey) || lowerKey.startsWith("x-forwarded-")) {
      return;
    }
    headers.set(key, value);
  });
  if (token) {
    headers.set("x-roadshow-api-key", token);
    headers.set("x-atg-api-key", token);
  }
  return headers;
}

function proxyResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  response.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (HOP_BY_HOP_HEADERS.has(lowerKey) || lowerKey === "set-cookie") {
      return;
    }
    headers.set(key, value);
  });
  return headers;
}

function copySetCookieHeaders(source: Response, target: NextResponse): void {
  const headersWithCookies = source.headers as Headers & { getSetCookie?: () => string[] };
  const setCookies = headersWithCookies.getSetCookie?.() ?? [];
  if (setCookies.length) {
    for (const cookie of setCookies) {
      target.headers.append("set-cookie", cookie);
    }
    return;
  }
  const combinedCookie = source.headers.get("set-cookie");
  if (combinedCookie) {
    target.headers.append("set-cookie", combinedCookie);
  }
}

async function proxyRoadshowApi(request: NextRequest, context: ProxyContext): Promise<NextResponse> {
  const { path = [] } = await context.params;
  const token = backendApiToken();
  if (process.env.ROADSHOW_ENV === "production" && !token) {
    return NextResponse.json(
      { detail: "Roadshow frontend proxy is missing ROADSHOW_API_ACCESS_TOKEN." },
      { status: 503 },
    );
  }

  const method = request.method.toUpperCase();
  const backendResponse = await fetch(targetUrl(request, path), {
    method,
    headers: proxyRequestHeaders(request, token),
    body: method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer(),
    cache: "no-store",
    redirect: "manual",
  });
  const body = method === "HEAD" || backendResponse.status === 204 || backendResponse.status === 304 ? null : backendResponse.body;
  const response = new NextResponse(body, {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
    headers: proxyResponseHeaders(backendResponse),
  });
  copySetCookieHeaders(backendResponse, response);
  return response;
}

export async function GET(request: NextRequest, context: ProxyContext): Promise<NextResponse> {
  return proxyRoadshowApi(request, context);
}

export async function POST(request: NextRequest, context: ProxyContext): Promise<NextResponse> {
  return proxyRoadshowApi(request, context);
}

export async function PATCH(request: NextRequest, context: ProxyContext): Promise<NextResponse> {
  return proxyRoadshowApi(request, context);
}

export async function DELETE(request: NextRequest, context: ProxyContext): Promise<NextResponse> {
  return proxyRoadshowApi(request, context);
}
