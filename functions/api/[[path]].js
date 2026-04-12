export async function onRequest(context) {
  const { request, env, params } = context;
  const backendUrl = env.BACKEND_URL;

  if (!backendUrl) {
    return new Response("BACKEND_URL not configured", { status: 502 });
  }

  const path = params.path ? params.path.join("/") : "";
  const url = new URL(request.url);
  const target = `${backendUrl}/${path}${url.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");

  const res = await fetch(target, {
    method: request.method,
    headers,
    body: request.body,
  });

  const responseHeaders = new Headers(res.headers);
  responseHeaders.set("Access-Control-Allow-Origin", url.origin);

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}
