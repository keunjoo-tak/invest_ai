const qs = (s) => document.querySelector(s);

async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}\n${JSON.stringify(data, null, 2)}`);
  }
  return data;
}

function print(target, obj) {
  target.textContent = JSON.stringify(obj, null, 2);
}

async function refreshHealth() {
  const box = qs("#health-status");
  try {
    const data = await request("GET", "/api/v1/health");
    box.innerHTML = `<span class="ok">정상</span> · ${data.time_utc}`;
  } catch (e) {
    box.innerHTML = `<span class="err">오류</span> · ${e.message}`;
  }
}

qs("#refresh-health").addEventListener("click", refreshHealth);

qs("#analyze-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = qs("#analyze-output");
  out.textContent = "실행 중...";
  const f = new FormData(e.currentTarget);
  const body = {
    ticker_or_name: f.get("ticker_or_name"),
    analysis_mode: "full",
    notify: f.get("notify") === "on",
    force_send: f.get("force_send") === "on",
    channels: ["telegram"],
    response_language: f.get("response_language"),
  };
  try {
    print(out, await request("POST", "/api/v1/analyze/ticker", body));
  } catch (err) {
    out.textContent = err.message;
  }
});

qs("#insight-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = qs("#insight-output");
  out.textContent = "조회 중...";
  const f = new FormData(e.currentTarget);
  try {
    print(out, await request("GET", `/api/v1/stock-insight/${encodeURIComponent(f.get("ticker"))}`));
  } catch (err) {
    out.textContent = err.message;
  }
});

qs("#trade-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = qs("#trade-output");
  out.textContent = "생성 중...";
  const f = new FormData(e.currentTarget);
  const body = {
    ticker_or_name: f.get("ticker_or_name"),
    risk_profile: f.get("risk_profile"),
  };
  try {
    print(out, await request("POST", "/api/v1/trade-compass/analyze", body));
  } catch (err) {
    out.textContent = err.message;
  }
});

qs("#pulse-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = qs("#pulse-output");
  out.textContent = "조회 중...";
  try {
    print(out, await request("GET", "/api/v1/market-pulse/overview"));
  } catch (err) {
    out.textContent = err.message;
  }
});

qs("#preview-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = qs("#preview-output");
  out.textContent = "수집 중...";
  const f = new FormData(e.currentTarget);
  const body = { source_id: f.get("source_id"), max_chars: 6000 };
  try {
    print(out, await request("POST", "/api/v1/ingestion/crawl/preview", body));
  } catch (err) {
    out.textContent = err.message;
  }
});

async function runBatch(url, body) {
  const out = qs("#batch-output");
  out.textContent = "배치 실행 중...";
  try {
    print(out, await request("POST", url, body));
  } catch (err) {
    out.textContent = err.message;
  }
}

qs("#run-kind").addEventListener("click", () => runBatch("/api/v1/batch/kind/disclosures", { ticker_or_name: "005930", max_items: 3 }));
qs("#run-policy").addEventListener("click", () => runBatch("/api/v1/batch/policy-briefing", { max_items: 3 }));
qs("#run-bok").addEventListener("click", () => runBatch("/api/v1/batch/bok/publications", { max_items: 3 }));

refreshHealth();

