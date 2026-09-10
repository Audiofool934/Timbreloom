export class JobConnectionError extends Error {}

export async function readJob(url) {
  let response;
  try {
    response = await fetch(url, { cache: "no-store" });
  } catch (error) {
    throw new JobConnectionError("The local service disconnected. Progress will return when the connection resumes.", { cause: error });
  }
  if (response.status >= 500) {
    throw new JobConnectionError("The local service is recovering. Reconnecting automatically.");
  }
  if (!response.ok) {
    let detail = "The job is missing or cannot be read.";
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}
