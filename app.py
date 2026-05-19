"""
노인복지관 사업계획서 AI 어시스턴트 v2
- 대화형 채팅 인터페이스
- 업로드 문서 기억 (세션 내)
- 웹 검색으로 최신 노인복지 트렌드 반영
"""

import streamlit as st
import pdfplumber
import io
import hashlib
import google.generativeai as genai

st.set_page_config(
    page_title="복지관 AI 어시스턴트",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #f8f9fa; }
.doc-badge {
    display:inline-block; background:#e8f4fd; color:#1a6fa5;
    border-radius:20px; padding:3px 10px; font-size:0.8rem; margin:2px;
}
.search-badge {
    display:inline-block; background:#e8f5e9; color:#2e7d32;
    border-radius:20px; padding:2px 8px; font-size:0.75rem; margin-left:6px;
}
</style>
""", unsafe_allow_html=True)

# ── 인증 ──────────────────────────────────────────────────
def load_users():
    try:
        return {u: h for u, h in st.secrets["users"].items()}
    except Exception:
        return {"admin": hashlib.sha256("admin1234".encode()).hexdigest()}

def check_login(u, p):
    return load_users().get(u) == hashlib.sha256(p.encode()).hexdigest()

# ── PDF 추출 ───────────────────────────────────────────────
def extract_pdf(file_bytes: bytes, filename: str) -> str:
    pages = []
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                t = page.extract_text()
                if t:
                    pages.append(f"[페이지 {i}]\n{t}")
        return "\n\n".join(pages) or "(텍스트 추출 불가)"
    except Exception as e:
        return f"({filename} 오류: {e})"

# ── 시스템 프롬프트 생성 ───────────────────────────────────
def build_system(docs: dict) -> str:
    if not docs:
        doc_section = "(아직 업로드된 문서 없음)"
    else:
        parts = []
        for name, text in docs.items():
            # 문서당 최대 20,000자 (Gemini 1M 토큰 컨텍스트 활용)
            parts.append(f"{'='*60}\n📄 문서명: {name}\n{'='*60}\n{text[:20000]}")
        doc_section = "\n\n".join(parts)

    return f"""당신은 노인복지관 사업 전문 AI 어시스턴트입니다.
담당자와 대화하며 사업계획서 작성을 도와드립니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
업로드된 문서 ({len(docs)}개)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{doc_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[역할]
1. 연도별 데이터 조회
   - "2023년 예산 알려줘" → 해당 문서에서 정확한 수치 인용
   - 출처 문서명과 연도를 반드시 명시

2. 연도 간 비교 분석
   - "2022년 vs 2024년 참여자 수 비교" → 표 형태로 비교
   - 변화 추이와 원인 분석

3. 내년 사업계획서 초안 작성
   - 과거 데이터 추이 분석
   - 웹 검색으로 최신 노인복지 정책·트렌드 반영
   - 실제 사용 가능한 수준으로 구체적 작성

4. 자유 질문
   - 프로그램 기획, 예산 편성, 성과지표 등 모든 질문

[답변 원칙]
- 항상 한국어로 답변
- 수치는 반드시 출처 명시: "(2023년 결과보고서 기준)"
- 문서에 없는 내용은 솔직히 없다고 하고 대안 제시
- 표나 목록을 적극 활용하여 가독성 높이기
- 사업계획서 작성 시 섹션별로 완성도 있게 작성"""

# ── 웹 검색 필요 여부 판단 ─────────────────────────────────
SEARCH_KEYWORDS = [
    '동향', '트렌드', '최근', '최신', '요즘', '내년', '2026', '2027',
    '정책', '지침', '변화', '새로운', '추진', '계획서 작성', '초안'
]

def needs_web_search(text: str) -> bool:
    return any(kw in text for kw in SEARCH_KEYWORDS)

# ── AI 응답 생성 ───────────────────────────────────────────
def get_response(user_msg: str, api_key: str, docs: dict, history: list) -> tuple[str, bool]:
    """
    Returns: (response_text, used_search)
    """
    genai.configure(api_key=api_key)

    system = build_system(docs)
    use_search = needs_web_search(user_msg)

    # Gemini용 히스토리 변환 (role: user/model)
    gemini_history = []
    for h in history[:-1]:  # 마지막 user 메시지 제외 (send_message로 전송)
        role = "model" if h["role"] == "assistant" else "user"
        gemini_history.append({"role": role, "parts": [h["content"]]})

    try:
        if use_search:
            # Google Search grounding 활성화
            from google.generativeai import protos
            search_tool = protos.Tool(
                google_search_retrieval=protos.GoogleSearchRetrieval(
                    dynamic_retrieval_config=protos.DynamicRetrievalConfig(
                        mode=protos.DynamicRetrievalConfig.Mode.MODE_DYNAMIC,
                        dynamic_threshold=0.3,
                    )
                )
            )
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system,
                tools=[search_tool],
            )
        else:
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system,
            )

        chat = model.start_chat(history=gemini_history)
        response = chat.send_message(user_msg)
        return response.text, use_search

    except Exception as e:
        # 검색 실패 시 일반 모드로 재시도
        if use_search:
            try:
                model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    system_instruction=system,
                )
                chat = model.start_chat(history=gemini_history)
                response = chat.send_message(user_msg)
                return response.text, False
            except Exception as e2:
                return f"오류가 발생했습니다: {str(e2)[:200]}", False
        return f"오류가 발생했습니다: {str(e)[:200]}", False

# ── 빠른 질문 버튼 ─────────────────────────────────────────
QUICK_QUESTIONS = [
    "📊 업로드된 문서 전체 요약해줘",
    "📅 연도별 주요 사업 목록 정리해줘",
    "💰 연도별 예산 변화 비교해줘",
    "📈 참여자 수 추이 분석해줘",
    "✍️ 내년 사업계획서 초안 작성해줘",
    "🔍 최신 노인복지 트렌드 알려줘",
]

# ══════════════════════════════════════════════════════════
#  로그인
# ══════════════════════════════════════════════════════════
def show_login():
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 🏥 복지관 AI 어시스턴트")
        st.markdown("사업계획서·결과보고서를 학습하고 대화로 분석합니다")
        st.markdown("---")
        with st.form("login"):
            u = st.text_input("아이디")
            p = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                if check_login(u, p):
                    st.session_state.update({"logged_in": True, "username": u})
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호를 확인하세요.")

# ══════════════════════════════════════════════════════════
#  메인 앱
# ══════════════════════════════════════════════════════════
def show_app():
    # ── 세션 초기화 ──────────────────────────────────────
    if "documents" not in st.session_state:
        st.session_state.documents = {}
    if "messages" not in st.session_state:
        st.session_state.messages = []

    docs: dict = st.session_state.documents
    messages: list = st.session_state.messages

    # ── 사이드바 ──────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"**👤 {st.session_state['username']}** 님")
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear(); st.rerun()

        st.markdown("---")

        # API 키
        api_key = ""
        try:
            api_key = st.secrets["GEMINI_API_KEY"]
            st.success("🟢 Gemini API 연결됨")
        except Exception:
            api_key = st.text_input("Gemini API 키", type="password", placeholder="AIza...")
            if not api_key:
                st.info("👉 [무료 키 발급](https://aistudio.google.com/apikey)")

        st.markdown("---")
        st.markdown("### 📁 문서 업로드")

        uploaded = st.file_uploader(
            "PDF 파일 선택 (여러 개 가능)",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded:
            added = 0
            for f in uploaded:
                if f.name not in docs:
                    docs[f.name] = extract_pdf(f.read(), f.name)
                    added += 1
            if added:
                st.success(f"✅ {added}개 추가됨")
                # 문서 추가되면 대화 맥락 리셋
                st.session_state.messages = []
                st.rerun()

        # 문서 목록
        if docs:
            st.markdown(f"**{len(docs)}개 문서 학습됨:**")
            for name in list(docs.keys()):
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(
                        f"<span class='doc-badge'>📄 {name[:16]}{'…' if len(name)>16 else ''}</span>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button("✕", key=f"d_{name}", help="삭제"):
                        del st.session_state.documents[name]
                        st.session_state.messages = []
                        st.rerun()
        else:
            st.caption("문서를 업로드하면 AI가 학습합니다")

        st.markdown("---")

        # 대화 초기화
        if st.button("🗑️ 대화 초기화", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        if docs and st.button("📂 문서 전체 삭제", use_container_width=True):
            st.session_state.documents = {}
            st.session_state.messages = []
            st.rerun()

    # ── 메인 채팅 영역 ─────────────────────────────────────
    st.markdown("# 🏥 복지관 AI 어시스턴트")

    if docs:
        doc_names = " · ".join(docs.keys())
        st.caption(f"📚 학습된 문서: {doc_names}")
    else:
        st.info("👈 왼쪽 사이드바에서 PDF 파일을 업로드하면 AI가 문서를 학습합니다.")

    # 빠른 질문 버튼 (대화 없을 때만 표시)
    if not messages and docs:
        st.markdown("**자주 쓰는 질문:**")
        cols = st.columns(3)
        for i, q in enumerate(QUICK_QUESTIONS):
            with cols[i % 3]:
                if st.button(q, use_container_width=True, key=f"q{i}"):
                    st.session_state._quick_input = q
                    st.rerun()

    # 채팅 메시지 표시
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("searched"):
                st.markdown(
                    "<span class='search-badge'>🔍 웹 검색 반영</span>",
                    unsafe_allow_html=True,
                )

    # 빠른 질문 처리
    quick = st.session_state.pop("_quick_input", None)

    # 사용자 입력
    user_input = st.chat_input(
        "질문하세요 — '2023년 예산 알려줘', '내년 사업계획서 써줘' 등",
        disabled=not api_key,
    )

    prompt = quick or user_input

    if prompt:
        if not api_key:
            st.warning("API 키를 사이드바에 입력해주세요.")
            st.stop()

        # 사용자 메시지 추가
        messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 응답
        with st.chat_message("assistant"):
            with st.spinner("분석 중..."):
                reply, searched = get_response(prompt, api_key, docs, messages)

            st.markdown(reply)
            if searched:
                st.markdown(
                    "<span class='search-badge'>🔍 웹 검색 반영</span>",
                    unsafe_allow_html=True,
                )

        messages.append({"role": "assistant", "content": reply, "searched": searched})
        st.rerun()

# ── 진입점 ────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    show_login()
else:
    show_app()
