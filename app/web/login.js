const form = document.querySelector("#login-form");
const errorBox = document.querySelector("#login-error");

function nextPath() {
  const params = new URLSearchParams(window.location.search);
  return params.get("next") || "/app";
}

async function requestJson(method, url, body) {
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "로그인 중 오류가 발생했습니다.");
  }
  return payload;
}

async function checkSession() {
  try {
    const response = await fetch("/api/v1/auth/me", { credentials: "same-origin" });
    if (response.ok) {
      window.location.replace(nextPath());
    }
  } catch {
    // ignore
  }
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox?.classList.add("hidden");
  const formData = new FormData(form);
  try {
    await requestJson("POST", "/api/v1/auth/login", {
      username: String(formData.get("username") || "").trim(),
      password: String(formData.get("password") || ""),
    });
    window.location.replace(nextPath());
  } catch (error) {
    if (errorBox) {
      errorBox.textContent = error instanceof Error ? error.message : String(error);
      errorBox.classList.remove("hidden");
    }
  }
});

checkSession();
