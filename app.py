"""
노인복지관 사업계획서 분석 에이전트
- 테스트: Google Gemini API (무료)
- 운영:   Anthropic Claude API (유료)
"""

import streamlit as st
import pdfplumber
import io
import hashlib
from datetime import datetime

st.set_page_config(
    page_title="복지관 사업계획서 분석",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #f8f9fa; }
.file-badge {
    display: inline-block;
    background: #e8f4fd;
    color: #1a6fa5;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.82rem;
    margin: 3px;
}
.mode-free  { background:#e8f5e9; color:#2e7d32; padding:4px 12px; border-radius:20px; font-size:0.82rem; }
.mode-paid  { background:#fff3e0; color:#e65100; padding:4px 12px; border-radius:20px; font-size:0.82rem; }
</style>
""", unsafe_allow_html=True)

# ── 사용자 계정 ────────────────────────────────────────────
def load_users() -> dict:
    try:
        return {u: h for u, h in st.secrets["users"].items()}
    except Exception:
        return {"admin": hashlib.sha256("admin1234".encode()).hexdigest()}

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def check_login(username: str, password: str) -> bool:
    return load_users().get(username) == hash_pw(password)

# ── PDF 텍스트 추출 ────────────────────────────────────────
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

# ── 시스템 프롬프트 ────────────────────────────────────────
SYSTEM_PROMPT = """당신은 노인복지관 사업 전문 분석가입니다.
업로드된 사업계획서·결과보고서를 분석하여 아래 형식으로 보고서를 작성하세요.

## 1. 📋 문서 개요
- 파일별 종류(계획서/보고서), 연도, 주요 사업 영역 식별

## 2. 🎯 사업 목표 분석
- 주요 목표와 추진 방향 요약

## 3. 📊 프로그램별 성과 분석
- 프로그램명, 계획 대비 실적, 참여자 수, 만족도

## 4. 💰 예산 분석
- 편성·집행 현황, 주요 절감·초과 항목

## 5. ✅ 성과 및 개선 필요 사항
- 잘된 점 / 개선이 필요한 점

## 6. 🔮 신규 사업계획서 작성을 위한 제언
- 반영 권고사항, 신규 프로그램 아이디어, 예산 조정 방향

## 7. 📝 종합 평가

실무 담당자가 바로 활용할 수 있도록 구체적이고 수치 중심으로 작성하세요."""

# ── Gemini 분석 (무료) ─────────────────────────────────────
def analyze_gemini(docs: dict, api_key: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    combined = _build_prompt(docs)
    response = model.generate_content(combined)
    return response.text

# ── Claude 분석 (유료) ─────────────────────────────────────
def analyze_claude(docs: dict, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_prompt(docs)}],
    )
    return response.content[0].text

def _build_prompt(docs: dict) -> str:
    combined, total = [], 0
    for name, text in docs.items():
        chunk = f"{'='*60}\n📄 {name}\n{'='*60}\n{text}"
        if total + len(chunk) > 80000:
            combined.append(f"\n⚠️ [{name}]: 분량 초과로 생략")
            break
        combined.append(chunk)
        total += len(chunk)
    return (
        f"아래 {len(docs)}개 노인복지관 문서를 분석하고 보고서를 작성해주세요.\n\n"
        + "\n\n".join(combined)
    )

# ══════════════════════════════════════════════════════════
#  로그인 화면
# ══════════════════════════════════════════════════════════
def show_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 🏥 복지관 사업계획서 분석 시스템")
        st.markdown("---")
        with st.form("login"):
            username = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                if check_login(username, password):
                    st.session_state.update({"logged_in": True, "username": username})
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호를 확인하세요.")

# ══════════════════════════════════════════════════════════
#  메인 앱
# ══════════════════════════════════════════════════════════
def show_app():
    # ── 사이드바 ──────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"**👤 {st.session_state['username']}** 님")
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear(); st.rerun()

        st.markdown("---")
        st.markdown("### ⚙️ AI 엔진 선택")

        engine = st.radio(
            "사용할 AI",
            ["🆓 Gemini (무료 테스트)", "💛 Claude (정식 운영)"],
            help="처음엔 Gemini로 성능 확인 후 Claude로 전환하세요.",
        )
        is_gemini = engine.startswith("🆓")

        # API 키 입력
        api_key = ""
        if is_gemini:
            st.markdown('<span class="mode-free">무료 테스트 모드</span>', unsafe_allow_html=True)
            try:
                api_key = st.secrets["GEMINI_API_KEY"]
                st.success("Gemini API 키 연결됨 ✓")
            except Exception:
                api_key = st.text_input(
                    "Gemini API 키",
                    type="password",
                    placeholder="AIza...",
                    help="aistudio.google.com에서 무료 발급",
                )
            if not api_key:
                st.info("👉 [Gemini API 키 발급](https://aistudio.google.com/apikey)")
        else:
            st.markdown('<span class="mode-paid">정식 운영 모드</span>', unsafe_allow_html=True)
            try:
                api_key = st.secrets["ANTHROPIC_API_KEY"]
                st.success("Claude API 키 연결됨 ✓")
            except Exception:
                api_key = st.text_input(
                    "Anthropic API 키",
                    type="password",
                    placeholder="sk-ant-...",
                    help="console.anthropic.com에서 발급",
                )

        st.markdown("---")
        st.markdown("### 📁 업로드된 문서")
        if "documents" not in st.session_state:
            st.session_state["documents"] = {}
        docs: dict = st.session_state["documents"]

        if docs:
            for fname in list(docs.keys()):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(
                        f"<span class='file-badge'>📄 {fname[:18]}{'…' if len(fname)>18 else ''}</span>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button("✕", key=f"del_{fname}"):
                        del st.session_state["documents"][fname]; st.rerun()
            if st.button("🗑️ 전체 삭제", use_container_width=True):
                st.session_state["documents"] = {}; st.rerun()
        else:
            st.caption("없음")

    # ── 메인 ──────────────────────────────────────────────
    st.markdown("# 🏥 노인복지관 사업계획서 분석")

    mode_label = "Gemini 무료 테스트" if is_gemini else "Claude 정식 운영"
    st.caption(f"현재 모드: {mode_label}")

    tab1, tab2 = st.tabs(["📂 문서 업로드 & 분석", "📊 분석 결과"])

    with tab1:
        uploaded = st.file_uploader(
            "PDF 파일을 드래그하거나 선택하세요 (여러 개 가능)",
            type=["pdf"],
            accept_multiple_files=True,
        )
        if uploaded:
            added = 0
            for f in uploaded:
                if f.name not in st.session_state["documents"]:
                    st.session_state["documents"][f.name] = extract_pdf(f.read(), f.name)
                    added += 1
            if added:
                st.success(f"✅ {added}개 파일 추가됨"); st.rerun()

        docs = st.session_state["documents"]
        if docs:
            st.markdown(f"**{len(docs)}개 문서 준비됨:**")
            for name in docs:
                st.markdown(
                    f"<span class='file-badge'>📄 {name} ({len(docs[name]):,}자)</span>",
                    unsafe_allow_html=True,
                )
            st.markdown("")

            if not api_key:
                st.warning("⚠️ 사이드바에 API 키를 입력해주세요.")
            else:
                if st.button("🔍 분석 시작", type="primary"):
                    with st.spinner(f"{mode_label} 분석 중... (1~2분 소요)"):
                        try:
                            if is_gemini:
                                report = analyze_gemini(docs, api_key)
                            else:
                                report = analyze_claude(docs, api_key)

                            st.session_state.update({
                                "report": report,
                                "report_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "report_engine": mode_label,
                                "report_docs": len(docs),
                            })
                            st.success("✅ 분석 완료! '분석 결과' 탭을 확인하세요.")
                        except Exception as e:
                            err = str(e)
                            if "API_KEY" in err or "api_key" in err.lower() or "auth" in err.lower():
                                st.error("❌ API 키가 올바르지 않습니다.")
                            elif "quota" in err.lower() or "rate" in err.lower() or "429" in err:
                                st.error("❌ API 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
                            else:
                                st.error(f"❌ 오류: {err[:300]}")
        else:
            st.info("💡 PDF 파일을 업로드하면 분석을 시작할 수 있습니다.")
            with st.expander("📖 사용법"):
                st.markdown("""
**권장 순서**
1. 전년도 결과보고서 PDF 업로드
2. 올해 사업계획서 초안 업로드 (있으면)
3. 분석 시작 → 결과 확인

**AI 엔진 선택 기준**
- 처음 → Gemini (무료, 성능 확인용)
- 만족스러우면 → Claude로 전환 (더 정확, 소량 유료)
""")

    with tab2:
        if "report" in st.session_state:
            r = st.session_state
            c1, c2 = st.columns([3, 1])
            with c1:
                st.caption(f"분석: {r['report_time']} | {r['report_engine']} | 문서 {r['report_docs']}개")
            with c2:
                st.download_button(
                    "⬇️ 다운로드",
                    data=r["report"],
                    file_name=f"분석보고서_{r['report_time'][:10]}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown("---")
            st.markdown(r["report"])
        else:
            st.info("아직 결과가 없습니다. 문서를 업로드하고 분석을 시작하세요.")

# ── 진입점 ────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    show_login()
else:
    show_app()
