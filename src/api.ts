// 로그인/프로필 저장이 아직 없어서 임시 고정값. 나중에 실제 프로필로 교체
export const TEST_PROFILE = {
  age: 28, job: "취업준비생",
  monthly_income: 150, total_assets: 3000, household_size: 1, score: 50,
};

async function post(url: string, body: object): Promise<string> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.answer ?? "";
}

export const askConsult = (question: string, profile: typeof TEST_PROFILE) =>
  post("/chat", { question, ...profile });

export const askTerm = (question: string) =>
  post("/side_chat", { question });