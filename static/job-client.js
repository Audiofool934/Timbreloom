export class JobConnectionError extends Error {}

export async function readJob(url) {
  let response;
  try {
    response = await fetch(url, { cache: "no-store" });
  } catch (error) {
    throw new JobConnectionError("本地服务暂时断开，连接恢复后会继续显示进度。", { cause: error });
  }
  if (response.status >= 500) {
    throw new JobConnectionError("本地服务正在恢复，稍后会自动重新连接。");
  }
  if (!response.ok) {
    let detail = "任务不存在或无法读取。";
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}
