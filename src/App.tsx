import { FormEvent, useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  GraduationCap,
  Home,
  Lightbulb,
  LockKeyhole,
  Menu,
  MessageCircle,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserRound,
  WalletCards,
  X,
} from "lucide-react";

type Screen = "home" | "consult" | "education" | "auth" | "profile" | "quiz";
type Message = { role: "ai" | "user"; text: string };

const navItems = [
  { id: "home" as Screen, label: "홈", icon: Home },
  { id: "consult" as Screen, label: "맞춤상담", icon: MessageCircle },
  { id: "education" as Screen, label: "금융교육", icon: GraduationCap },
  { id: "profile" as Screen, label: "프로필", icon: UserRound },
];

const lessons = [
  ["처음 시작하는 금융 생활", "12:45", "금융 기초"],
  ["예금과 적금, 무엇이 다를까?", "08:30", "저축"],
  ["신용점수 쉽게 이해하기", "10:15", "신용 관리"],
  ["대출 전 꼭 확인할 것", "14:20", "대출"],
  ["나에게 맞는 금융상품 찾기", "09:40", "금융상품"],
  ["보이스피싱 예방하기", "07:55", "금융 안전"],
  ["월급 관리 첫걸음", "11:10", "자산 관리"],
];

const quiz = [
  ["예금자보호제도로 보호받을 수 있는 금융회사별 최대 원리금은 얼마일까요?", ["3,000만 원", "5,000만 원", "1억 원", "제한 없음"]],
  ["신용점수를 건강하게 관리하는 방법은 무엇일까요?", ["연체 없이 제때 납부하기", "대출을 자주 받기", "한도를 모두 사용하기", "금융 거래를 하지 않기"]],
  ["변동금리 대출을 받을 때 가장 먼저 살펴볼 것은?", ["금리 상승 가능성과 상환 여력", "은행 건물의 크기", "광고 모델", "통장 색상"]],
  ["급하게 돈이 필요할 때 가장 안전한 선택은?", ["등록 금융회사와 정책상품 확인", "SNS 개인 대출", "선입금 요구 업체", "문자 속 링크"]],
  ["월 예산을 세울 때 먼저 구분하면 좋은 것은?", ["고정지출과 변동지출", "좋아하는 숫자", "친구의 소비액", "카드 디자인"]],
];

function Brand() {
  return (
    <div className="brand">
      <span><WalletCards size={19} /></span>
      <strong>머니로그</strong>
    </div>
  );
}

function TopBar({ title, back, action }: { title?: string; back?: () => void; action?: React.ReactNode }) {
  return (
    <header className="top-bar">
      {back ? <button className="icon-button" onClick={back} aria-label="뒤로가기"><ArrowLeft /></button> : <Brand />}
      {title && <strong className="top-title">{title}</strong>}
      <div className="top-action">{action}</div>
    </header>
  );
}

function BottomNav({
  screen,
  loggedIn,
  onNavigate,
}: {
  screen: Screen;
  loggedIn: boolean;
  onNavigate: (screen: Screen) => void;
}) {
  return (
    <nav className="bottom-nav" aria-label="하단 메뉴">
      {navItems.map((item) => {
        const Icon = item.icon;
        const destination = item.id === "profile" && !loggedIn ? "auth" : item.id;
        const active = screen === item.id || (screen === "auth" && item.id === "profile");
        return (
          <button className={active ? "active" : ""} onClick={() => onNavigate(destination)} key={item.id}>
            <span><Icon size={21} strokeWidth={active ? 2.5 : 2} /></span>
            {item.id === "profile" && !loggedIn ? "로그인" : item.label}
          </button>
        );
      })}
    </nav>
  );
}

function HomeScreen({ onNavigate, openTerms, loggedIn }: { onNavigate: (s: Screen) => void; openTerms: () => void; loggedIn: boolean }) {
  return (
    <>
      <TopBar action={<button className="avatar-button" onClick={() => onNavigate(loggedIn ? "profile" : "auth")}><UserRound size={18} /></button>} />
      <main className="screen home-screen">
        <section className="welcome">
          <span className="hello">{loggedIn ? "안녕하세요, 임종원 님" : "금융이 쉬워지는 첫걸음"}</span>
          <h1>오늘은 어떤 금융 고민을<br />함께 해결해 볼까요?</h1>
        </section>

        <button className="consult-banner" onClick={() => onNavigate("consult")}>
          <div className="banner-copy">
            <span><Sparkles size={14} /> AI 맞춤 금융상담</span>
            <h2>내 상황에 꼭 맞는<br />금융 정보를 찾아드려요</h2>
            <p>소득과 자산을 바탕으로 쉽게 설명해 드릴게요.</p>
            <strong>상담 시작하기 <ArrowRight size={16} /></strong>
          </div>
          <div className="banner-art">
            <span className="bot-orb"><Bot size={35} /></span>
            <i className="bubble one" />
            <i className="bubble two" />
          </div>
        </button>

        <section className="daily-term">
          <div className="section-heading">
            <div><span className="heading-icon"><Lightbulb size={17} /></span><div><small>오늘의 금융 용어</small><h2>하루 하나, 쉽게 알아봐요</h2></div></div>
            <span className="display-label">매일 새로운 용어</span>
          </div>
          <div className="term-card">
            <span className="term-index">오늘</span>
            <div><strong>DSR</strong><h3>내 소득에서 빚 갚는 돈의 비율</h3><p>연간 갚아야 하는 대출 원리금이 소득에서 얼마나 차지하는지 보여주는 숫자예요.</p></div>
          </div>
        </section>

        <section className="continue-learning">
          <div className="section-heading">
            <div><span className="heading-icon mint"><Play size={16} /></span><div><small>이어서 학습하기</small><h2>10분 금융 교실</h2></div></div>
            <button onClick={() => onNavigate("education")}>전체보기 <ChevronRight size={15} /></button>
          </div>
          <button className="continue-card" onClick={() => onNavigate("education")}>
            <span className="lesson-thumb"><Play fill="currentColor" size={19} /></span>
            <div><small>금융 기초 · 1강</small><strong>처음 시작하는 금융 생활</strong><div className="progress"><i /></div><span>68% 학습 완료</span></div>
          </button>
        </section>

        <div className="trust-note"><ShieldCheck size={17} /><span>공공기관 금융정보를 바탕으로<br /><strong>안전하고 신뢰할 수 있는 정보</strong>를 안내해요.</span></div>
      </main>
      <button className="term-side-toggle" onClick={openTerms} aria-label="용어 AI 챗봇 열기">
        <Sparkles size={23} />
      </button>
    </>
  );
}

function ConsultScreen() {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState("");
  const [histories, setHistories] = useState<string[]>([]);
  const [currentStarted, setCurrentStarted] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { role: "ai", text: "안녕하세요, 임종원 님. 소득과 자산에 맞는 금융 정보를 찾아드릴게요. 무엇이 궁금하세요?" },
  ]);

  const send = (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim() || historyOpen) return;
    const question = input.trim();
    if (!currentStarted) {
      const title = question.length > 18 ? `${question.slice(0, 18)}…` : question;
      setHistories((items) => [title, ...items]);
      setCurrentStarted(true);
    }
    setMessages((items) => [...items, { role: "user", text: question }, { role: "ai", text: "질문을 확인했어요. 등록된 프로필을 기준으로 필요한 금융 정보를 차근차근 안내해 드릴게요." }]);
    setInput("");
  };

  return (
    <>
      <TopBar
        title="맞춤형 AI 금융상담"
        action={<span className="secure-badge"><LockKeyhole size={12} /> 안전한 상담</span>}
      />
      <main className="screen chat-screen">
        <div className="chat-tools">
          <button onClick={() => setHistoryOpen(true)}><Menu size={18} /><span>상담 기록</span></button>
          {/*<span><i /> 상담 가능</span>*/}
        </div>
        <div className="chat-day">2026년 11월 5일 목요일</div>
        <div className="messages">
          {messages.map((message, index) => (
            <div className={`message ${message.role}`} key={`${message.text}-${index}`}>
              {message.role === "ai" && <span className="ai-avatar"><Bot size={17} /></span>}
              <div>
                {message.role === "ai" && <small>금빛 AI</small>}
                <p>{message.text}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="question-chips">
          {["필요 서류는?", "내가 받을 수 있어?", "신청 방법 알려줘"].map((item) => <button onClick={() => setInput(item)} key={item}>{item}</button>)}
        </div>
        <form className={`message-form ${historyOpen ? "disabled" : ""}`} onSubmit={send}>
          <input disabled={historyOpen} value={input} onChange={(event) => setInput(event.target.value)} placeholder="질문을 입력해 주세요" />
          <button disabled={historyOpen} aria-label="질문 전송"><Send size={18} /></button>
        </form>
      </main>

      <aside className={`history-drawer ${historyOpen ? "open" : ""}`}>
        <div className="drawer-head"><div><Clock3 size={18} /><strong>상담 기록</strong></div><button onClick={() => setHistoryOpen(false)}><X size={20} /></button></div>
        <button className="new-chat" onClick={() => { setMessages([{ role: "ai", text: "새로운 상담을 시작할게요. 무엇이 궁금하세요?" }]); setCurrentStarted(false); setHistoryOpen(false); }}><Plus size={17} /> 새로운 대화</button>
        <small>최근 상담</small>
        {histories.length === 0 ? (
          <div className="empty-history">
            <MessageCircle size={24} />
            <strong>아직 상담 기록이 없어요</strong>
            <p>새로운 대화를 시작하고 질문을 보내면<br />상담 기록이 여기에 표시돼요.</p>
          </div>
        ) : (
          <div className="history-list">
            {histories.map((history, index) => (
              <button className={index === 0 ? "selected" : ""} key={`${history}-${index}`}>
                <MessageCircle size={15} /><span>{history}</span>
                <i onClick={(event) => { event.stopPropagation(); setHistories((items) => items.filter((_, itemIndex) => itemIndex !== index)); }}><Trash2 size={14} /></i>
              </button>
            ))}
          </div>
        )}
      </aside>
      {historyOpen && <button className="drawer-scrim" onClick={() => setHistoryOpen(false)} aria-label="상담 기록 닫기" />}
    </>
  );
}

function EducationScreen({ openTerms }: { openTerms: () => void }) {
  const [selected, setSelected] = useState(0);
  return (
    <>
      <TopBar title="금융 교육" action={<button className="search-button"><Search size={19} /></button>} />
      <main className="screen education-screen">
        <section className="video-card">
          <div className="video">
            <span className="video-lines" />
            <button><Play fill="currentColor" /></button>
            <small>{lessons[selected][1]}</small>
          </div>
          <div className="video-info"><span>{lessons[selected][2]}</span><h1>{lessons[selected][0]}</h1><p>생활 속 사례로 꼭 필요한 금융 개념을 쉽게 배워요.</p></div>
        </section>

        <div className="course-title"><div><small>기초 금융 과정</small><h2>강의 목록</h2></div><span>{selected + 1} / {lessons.length}</span></div>
        <div className="lesson-list">
          {lessons.map((lesson, index) => (
            <button className={selected === index ? "active" : ""} onClick={() => setSelected(index)} key={lesson[0]}>
              <span className="lesson-number">{selected === index ? <Play size={12} fill="currentColor" /> : index + 1}</span>
              <span><strong>{lesson[0]}</strong><small>{lesson[2]} · {lesson[1]}</small></span>
              {index === 0 && <CheckCircle2 size={18} />}
            </button>
          ))}
        </div>
        <button className="term-fab" onClick={openTerms}><BookOpen size={20} /><span>모르는 용어 물어보기</span></button>
      </main>
    </>
  );
}

function AuthScreen({ onLogin, onSignup }: { onLogin: () => void; onSignup: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [checked, setChecked] = useState(false);
  const [notice, setNotice] = useState("");
  const fields = ["이름", "나이", "아이디", "비밀번호", "직업", "월 소득", "총 자산", "가구원 수"];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const missing = mode === "signup" ? fields.find((field) => !String(form.get(field) ?? "").trim()) : undefined;
    if (missing) return setNotice(`${missing} 항목을 입력해 주세요.`);
    if (mode === "signup" && !checked) return setNotice("아이디 중복 확인은 필수입니다.");
    mode === "login" ? onLogin() : onSignup();
  };

  return (
    <>
      <TopBar title={mode === "login" ? "로그인" : "회원가입"} />
      <main className="screen auth-screen">
        <div className="auth-intro"><span><UserRound size={25} /></span><h1>{mode === "login" ? "다시 만나서 반가워요" : "머니로그를 시작해 볼까요?"}</h1><p>{mode === "login" ? "로그인하고 맞춤 금융 정보를 확인하세요." : "꼭 필요한 정보만 입력하면 맞춤 상담을 시작할 수 있어요."}</p></div>
        <div className="mode-tabs"><button className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setNotice(""); }}>로그인</button><button className={mode === "signup" ? "active" : ""} onClick={() => { setMode("signup"); setNotice(""); }}>회원가입</button></div>
        <form className="auth-form" onSubmit={submit}>
          {(mode === "login" ? ["아이디", "비밀번호"] : fields).map((field) => (
            <label key={field}>{field}
              <div className="field-row">
                <input name={field} type={field === "비밀번호" ? "password" : "text"} placeholder={`${field} 입력`} />
                {mode === "signup" && field === "아이디" && <button type="button" onClick={() => setChecked(true)}>{checked ? "확인 완료" : "중복 확인"}</button>}
              </div>
            </label>
          ))}
          {checked && mode === "signup" && <span className="valid"><Check size={14} /> 사용할 수 있는 아이디예요.</span>}
          {notice && <div className="form-notice"><CircleHelp size={17} /><span><strong>필수 입력 항목 누락</strong>{notice}</span></div>}
          <button className="primary-button">{mode === "login" ? "로그인" : "가입하고 퀴즈 시작"} <ArrowRight size={17} /></button>
        </form>
      </main>
    </>
  );
}

function ProfileScreen({ onSaved }: { onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const fields = [["이름", "임종원"], ["나이", "28"], ["아이디", "user123"], ["비밀번호", "••••••••"], ["직업", "취업준비생"], ["월 소득", "150만 원"], ["총 자산", "3,000만 원"], ["가구원 수", "1인 가구"]];
  return (
    <>
      <TopBar title="프로필" action={<button className="edit-button" onClick={() => setEditing(!editing)}>{editing ? <Check size={16} /> : <Pencil size={16} />}{editing ? "완료" : "수정"}</button>} />
      <main className="screen profile-screen">
        <section className="profile-hero">
          <span><UserRound size={34} /></span><h1>임종원</h1><p>취업준비생 · 1인 가구</p><small><ShieldCheck size={13} /> 본인 인증 완료</small>
        </section>
        <section className="profile-form">
          <div className="profile-form-title"><div><h2>내 정보</h2><p>맞춤 상담에 활용되는 정보예요.</p></div><span className={editing ? "editing" : ""}>{editing ? "수정 중" : "확인 모드"}</span></div>
          {fields.map(([label, value]) => <label key={label}>{label}<input disabled={!editing || label === "아이디"} defaultValue={value} /></label>)}
          <button className="primary-button" onClick={() => { setEditing(false); onSaved(); }}>확인 및 저장 <Check size={17} /></button>
        </section>
      </main>
    </>
  );
}

function QuizScreen({ onDone, onExit }: { onDone: () => void; onExit: () => void }) {
  const [step, setStep] = useState(0);
  const [answer, setAnswer] = useState<number | null>(null);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);
  const next = () => {
    if (answer === null) return;
    if (step === quiz.length - 1) onDone();
    else { setStep(step + 1); setAnswer(null); }
  };
  return (
    <>
      <TopBar title="금융 이해도 퀴즈" back={onExit} />
      <main className="screen quiz-screen">
        <div className="quiz-progress-head"><span>STEP {String(step + 1).padStart(2, "0")}</span><strong>{step + 1} / {quiz.length}</strong></div>
        <div className="quiz-progress"><i style={{ width: `${((step + 1) / quiz.length) * 100}%` }} /></div>
        <section className="quiz-content">
          <span className="quiz-bulb"><Lightbulb size={23} /></span>
          <p>정답보다 현재 금융 이해도를 알아보는 과정이에요.</p>
          <h1>{quiz[step][0] as string}</h1>
          <div className="answers">
            {(quiz[step][1] as string[]).map((option, index) => <button className={answer === index ? "selected" : ""} onClick={() => setAnswer(index)} key={option}><span>{index + 1}</span>{option}{answer === index && <CheckCircle2 size={19} />}</button>)}
          </div>
          <button className="primary-button" disabled={answer === null} onClick={next}>{step === quiz.length - 1 ? "결과 확인" : "다음 질문"} <ArrowRight size={17} /></button>
        </section>
      </main>
    </>
  );
}

function TermChat({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim()) return;
    const question = input.trim();
    const answer = question.toUpperCase().includes("LTV")
      ? "LTV는 집값을 기준으로 대출받을 수 있는 금액의 비율이에요. 집값이 1억 원이고 LTV가 70%라면 최대 7천만 원까지 가능하다는 뜻이에요."
      : question.toUpperCase().includes("DSR")
        ? "DSR은 연 소득 중에서 대출 원금과 이자를 갚는 데 쓰는 돈의 비율이에요. 숫자가 낮을수록 상환 부담이 적다는 뜻이에요."
        : "어려운 금융 용어를 생활 속 예시와 함께 쉽게 설명해 드릴게요.";
    setMessages((items) => [...items, { role: "user", text: question }, { role: "ai", text: answer }]);
    setInput("");
  };
  return (
    <aside className="term-drawer" role="dialog" aria-modal="true" aria-label="용어 AI 챗봇">
      <header className="term-drawer-head">
        <div className="term-agent">
          <span><Sparkles size={17} /></span>
          <div><strong>용어 AI</strong><small><i /> 바로 답변해 드려요</small></div>
        </div>
        <div className="term-drawer-actions">
          <button onClick={() => setMessages([])} aria-label="대화 초기화"><RotateCcw size={18} /></button>
          <button onClick={onClose} aria-label="채팅 닫기"><X size={20} /></button>
        </div>
      </header>

      <div className={`term-drawer-body ${messages.length === 0 ? "empty" : ""}`}>
        {messages.length === 0 ? (
          <div className="term-welcome">
            <span className="term-welcome-icon"><Sparkles size={28} /></span>
            <h2>어려운 금융 용어,<br />쉽게 알려드릴게요</h2>
            <p>LTV, DSR, 변동금리처럼 대화 중 모르는<br />금융 용어를 편하게 물어보세요.</p>
            <div className="term-suggestions">
              {["LTV가 뭐야?", "DSR 쉽게 알려줘", "변동금리 뜻"].map((item) => <button onClick={() => setInput(item)} key={item}>{item}</button>)}
            </div>
          </div>
        ) : (
          <div className="term-message-list">
            {messages.map((message, index) => (
              <div className={`term-message ${message.role}`} key={`${message.text}-${index}`}>
                {message.role === "ai" && <span><Sparkles size={15} /></span>}
                <p>{message.text}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <form className="term-drawer-form" onSubmit={submit}>
        <div>
          <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="메시지를 입력해 주세요." />
          <small>금융 용어 질문</small>
        </div>
        <button disabled={!input.trim()} aria-label="메시지 전송"><ArrowRight size={18} /></button>
      </form>
    </aside>
  );
}

function ExitWarning({ onCancel, onExit }: { onCancel: () => void; onExit: () => void }) {
  return (
    <div className="modal-layer">
      <div className="warning-modal">
        <span><CircleHelp size={24} /></span><h2>페이지 이탈 경고</h2><p>퀴즈를 완료하지 않으면 정확한 맞춤 상담이 어려울 수 있어요.<br />그래도 나가시겠어요?</p>
        <button className="primary-button" onClick={onCancel}>계속 풀기</button><button className="text-exit" onClick={onExit}>나가기</button>
      </div>
    </div>
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [loggedIn, setLoggedIn] = useState(false);
  const [termOpen, setTermOpen] = useState(false);
  const [pendingExit, setPendingExit] = useState<Screen | null>(null);
  const inQuiz = screen === "quiz";

  const navigate = (next: Screen) => {
    if (inQuiz && next !== "quiz") return setPendingExit(next);
    setScreen(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="app">
      {screen === "home" && <HomeScreen onNavigate={navigate} openTerms={() => setTermOpen(true)} loggedIn={loggedIn} />}
      {screen === "consult" && <ConsultScreen />}
      {screen === "education" && <EducationScreen openTerms={() => setTermOpen(true)} />}
      {screen === "auth" && <AuthScreen onLogin={() => { setLoggedIn(true); navigate("home"); }} onSignup={() => { setLoggedIn(true); setScreen("quiz"); }} />}
      {screen === "profile" && <ProfileScreen onSaved={() => navigate("home")} />}
      {screen === "quiz" && <QuizScreen onDone={() => setScreen("home")} onExit={() => setPendingExit("home")} />}

      <BottomNav screen={screen} loggedIn={loggedIn} onNavigate={navigate} />
      {termOpen && <><button className="term-drawer-scrim" onClick={() => setTermOpen(false)} aria-label="용어 AI 닫기" /><TermChat onClose={() => setTermOpen(false)} /></>}
      {pendingExit && <ExitWarning onCancel={() => setPendingExit(null)} onExit={() => { setScreen(pendingExit); setPendingExit(null); }} />}
    </div>
  );
}