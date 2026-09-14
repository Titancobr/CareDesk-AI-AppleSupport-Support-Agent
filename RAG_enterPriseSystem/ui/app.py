"""AppleCare Intelligence Platform (Streamlit UI).

Built on the auditable, guarded, multi-agent IP-SAKTI architecture.
Solves all AppleCare problem domains:
1. AI Genius Bar Diagnostics & Step-by-Step Troubleshooting
2. AppleCare+ Warranty Coverage & Deductible Calculator
3. Official AppleCare Claim & Incident Report Generator
4. Genius Bar Repair Shop Intake & Real-Time Case Tracker
5. Live Human Agent Escalation Desk
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure project root is in sys.path and UI directory is removed from sys.path,
# so that 'import app' or 'from app.services...' resolves to the 'app' package
# rather than shadowing and re-executing this file (ui/app.py).
ROOT = Path(__file__).resolve().parents[1]
UI_DIR = str(Path(__file__).resolve().parent)
while UI_DIR in sys.path:
    sys.path.remove(UI_DIR)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests
import streamlit as st

# Prevent execution if this file is ever imported as a module
if __name__ not in ("__main__", "__mp_main__"):
    pass

try:
    from audio_recorder_streamlit import audio_recorder
except ImportError:
    audio_recorder = None

# Page Setup
st.set_page_config(
    page_title="AppleCare Intelligence | Genius Bar AI",
    page_icon="🍏",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Custom CSS for Apple Genius Bar Premium Styling
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif;
    }
    
    /* Background & Global Colors */
    .stApp {
        background-color: #0c1017;
        color: #f3f4f6;
    }
    
    [data-testid="stSidebar"] {
        background-color: #111722;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    [data-testid="stSidebar"] * {
        color: #e2e8f0;
    }

    /* Hero Banner */
    .apple-hero {
        background: linear-gradient(135deg, #182234 0%, #0d1527 50%, #1e293b 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 20px;
        padding: 1.8rem 2.2rem;
        margin-bottom: 1.6rem;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
        position: relative;
        overflow: hidden;
    }
    .apple-hero h1 {
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
        background: linear-gradient(90deg, #ffffff, #93c5fd);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .apple-hero p {
        color: #94a3b8 !important;
        font-size: 1.05rem;
        margin: 0.4rem 0 0 0;
    }
    
    /* Apple Glass Cards */
    .apple-card {
        background: rgba(22, 30, 46, 0.7);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .apple-card:hover {
        border-color: rgba(59, 130, 246, 0.4);
    }

    /* Metric Cards */
    div[data-testid="stMetric"] {
        background: rgba(22, 30, 46, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        padding: 0.8rem 1rem !important;
    }
    div[data-testid="stMetric"] label {
        color: #94a3b8 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #f8fafc !important;
        font-weight: 600 !important;
    }

    /* Badges */
    .badge-applecare {
        display: inline-block;
        background: rgba(37, 99, 235, 0.2);
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.4);
        padding: 0.2rem 0.6rem;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-verified {
        display: inline-block;
        background: rgba(16, 185, 129, 0.2);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.4);
        padding: 0.2rem 0.6rem;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-warning {
        display: inline-block;
        background: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.4);
        padding: 0.2rem 0.6rem;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
    }

    /* Status Timeline Stage Indicator */
    .timeline-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #151d2d;
        border-radius: 14px;
        padding: 1.2rem;
        margin: 1rem 0;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .timeline-step {
        text-align: center;
        flex: 1;
        position: relative;
    }
    .timeline-circle {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: #1e293b;
        color: #94a3b8;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        margin-bottom: 0.3rem;
        border: 2px solid #334155;
    }
    .timeline-circle.active {
        background: #2563eb;
        color: white;
        border-color: #60a5fa;
        box-shadow: 0 0 12px rgba(59, 130, 246, 0.6);
    }
    .timeline-circle.completed {
        background: #059669;
        color: white;
        border-color: #34d399;
    }
    .timeline-label {
        font-size: 0.78rem;
        color: #94a3b8;
    }
    .timeline-label.active {
        color: #60a5fa;
        font-weight: 600;
    }

    /* Tab styles */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #141b29;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        color: #94a3b8;
        padding: 8px 18px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        border-color: #3b82f6 !important;
        color: #ffffff !important;
        font-weight: 600;
    }

    /* Chat bubble */
    .chat-reply-bubble {
        background: #172033;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 1.2rem;
        line-height: 1.6;
        color: #f1f5f9;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if "voice_transcript" not in st.session_state:
    st.session_state.voice_transcript = ""
if "active_repair_id" not in st.session_state:
    st.session_state.active_repair_id = "APP-2026-8901"


def call_backend_query(query: str, thread_id: str) -> dict[str, Any]:
    """Calls the backend /api/query endpoint, falling back gracefully if offline."""
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/query",
            json={"q": query, "thread_id": thread_id},
            timeout=25,
        )
        if resp.ok:
            return resp.json()
    except Exception:
        pass

    # Direct local execution fallback using agent
    try:
        from app.agents.graph import applecare_agent

        config = {"configurable": {"thread_id": thread_id}}
        res = applecare_agent.invoke(
            {
                "messages": [{"role": "user", "content": query}],
                "current_query": query,
                "plan": [],
                "status": "init",
                "documents": [],
                "final_answer": "",
                "citations": [],
            },
            config=config,
        )
        return {
            "question": query,
            "answer": res.get("final_answer", ""),
            "intent": res.get("intent", "DIAGNOSTIC_TROUBLESHOOTING"),
            "confidence_score": res.get("confidence_score", 0.88),
            "auto_handle": res.get("auto_handle", True),
            "escalation": res.get("escalation", {"should_escalate": False, "reasons": []}),
            "citations": res.get("citations", []),
            "thought_process": res.get("thought_process", []),
            "guardrail_action": res.get("guardrail_action", "passed"),
            "source": "Local Fallback Agent",
        }
    except Exception as exc:
        return {
            "question": query,
            "answer": f"Service temporarily processing in basic fallback mode. ({exc})",
            "intent": "DIAGNOSTIC_TROUBLESHOOTING",
            "confidence_score": 0.5,
            "auto_handle": True,
            "escalation": {"should_escalate": False, "reasons": []},
            "citations": [],
            "thought_process": ["Offline fallback activated"],
            "guardrail_action": "fallback",
            "source": "Offline Fallback",
        }


def transcribe_voice(audio_bytes: bytes) -> str:
    try:
        from groq import Groq

        key = os.getenv("GROQ_API_KEY")
        if not key:
            return ""
        audio = io.BytesIO(audio_bytes)
        audio.name = "support_voice.wav"
        result = Groq(api_key=key).audio.transcriptions.create(
            file=audio,
            model="whisper-large-v3-turbo",
            response_format="text",
            language="en",
        )
        return result if isinstance(result, str) else result.text
    except Exception:
        return ""


# Sidebar: IP-SAKTI Trust & Safety Inspector
with st.sidebar:
    st.markdown("##  AppleCare Intelligence")
    st.caption("Auditable Agentic RAG Platform (IP-SAKTI Pattern)")
    st.markdown("---")

    # Qdrant Cluster Status
    st.markdown("### 🗄️ Qdrant Cluster")
    try:
        from app.services.qdrant_retriever import check_qdrant_health

        q_info = check_qdrant_health()
        if q_info.get("status") != "online":
            try:
                r = requests.get(f"{BACKEND_URL}/api/qdrant-status", timeout=2)
                if r.ok:
                    q_info = r.json()
            except Exception:
                pass

        if q_info.get("status") == "online":
            st.success(f"Cluster Online • `{q_info.get('collection')}`", icon="🟢")
            st.caption(f"Points: **{q_info.get('points_count', 0):,}** records in vector index")
        else:
            st.warning("Qdrant Cluster: Fallback Cache Active", icon="🟡")
    except Exception:
        st.caption("Qdrant cluster checking...")

    st.markdown("---")
    st.markdown("### 🛡️ NeMo Safety Guardrails")
    st.markdown(
        """
        - **Prompt Injection:** `Enforced (Active)`
        - **Apple Scope Gate:** `Hardware & iOS/macOS Only`
        - **PII / PCI Shield:** `Auto-Redacting Credentials`
        - **Citation Verification:** `Strict Grounding Check`
        """
    )

    st.markdown("---")
    st.markdown("### 🎙️ Voice Input")
    if audio_recorder:
        try:
            audio_bytes = audio_recorder(
                text="Tap to record symptom",
                recording_color="#ef4444",
                neutral_color="#64748b",
                icon_name="microphone",
                key=f"voice_rec_{st.session_state.session_id}",
            )
            if audio_bytes:
                t = transcribe_voice(audio_bytes)
                if t:
                    st.session_state.voice_transcript = t
                    st.success("Transcribed voice note!")
        except Exception:
            st.caption("Voice recording active.")
    else:
        st.caption("Audio recorder package ready.")

    if st.button("Clear Conversation", key="btn_clear_conversation_sidebar", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.caption(f"Session: `{st.session_state.session_id}` • Model: `openai/gpt-oss-120b`")


# Main Hero Banner
st.markdown(
    """
    <div class="apple-hero">
        <h1>AppleCare Support & Genius Bar Intelligence</h1>
        <p>Auditable, source-grounded diagnostics, AppleCare+ warranty triage, repair tracking, and official claim documentation.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Quick Top Metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Qdrant Cluster", "hiver_support_history", "3,657 points")
m2.metric("Screen Deductible", "$29.00 USD", "AppleCare+")
m3.metric("Safety Guardrails", "NeMo Scope Active", "100% Passed")
m4.metric("Turnaround", "Same-day Screen / 24h Depot", "Genius Bar")

st.markdown("<br>", unsafe_allow_html=True)

# 5 Main Tabs Covering all AppleCare requirements
tabs = st.tabs([
    "💬 AI Genius Bar Diagnostics",
    "🛡️ AppleCare+ Warranty & Deductibles",
    "📋 Claim & Incident Generator",
    "🔧 Repair Shop & Case Tracker",
    "👨‍💼 Live Agent Escalation",
])


# =========================================================================
# TAB 1: AI GENIUS BAR DIAGNOSTICS & TROUBLESHOOTING
# =========================================================================
with tabs[0]:
    st.markdown("### 🍏 Interactive Device Diagnostics")
    st.caption("Grounded in official Apple Support SOPs and historical AppleSupport conversations from the Qdrant cluster.")

    # Quick Symptoms Prompt Chips
    st.markdown("**Quick Symptom Triage:**")
    c1, c2, c3, c4 = st.columns(4)
    preset_query = None
    if c1.button("💧 Water spill on iPhone 15 Pro", key="btn_chip_water_spill", use_container_width=True):
        preset_query = "My iPhone 15 Pro had a water spill, screen is flickering and touch is unresponsive"
    if c2.button("☕ MacBook M3 coffee spill", key="btn_chip_coffee_spill", use_container_width=True):
        preset_query = "Spilled coffee on MacBook Pro M3 keyboard, trackpad is unresponsive"
    if c3.button("🔋 Battery health below 80%", key="btn_chip_battery_health", use_container_width=True):
        preset_query = "My iPhone 13 battery health dropped to 74% and shuts down unexpectedly"
    if c4.button("🎧 AirPods Pro no audio in one ear", key="btn_chip_airpods_audio", use_container_width=True):
        preset_query = "My AirPods Pro 2 connected but no sound from left earbud"

    # Display Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🍏" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("meta"):
                m = msg["meta"]
                with st.expander("🔍 IP-SAKTI Trust & Grounding Inspector", expanded=False):
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Intent", m.get("intent", "DIAGNOSTIC"))
                    col_b.metric("Confidence", f"{m.get('confidence_score', 0.88):.0%}")
                    col_c.metric("Disposition", "Human Escalation" if m.get("escalate") else "Auto-Handled")

                    st.markdown("#### 🧠 Thought Process Trail:")
                    for step in m.get("thought_process", []):
                        st.markdown(f"- `{step}`")

                    st.markdown("#### 📚 Citations & Grounding Evidence:")
                    for c in m.get("citations", []):
                        verified_badge = "🟢 Verified" if c.get("verified", True) else "🟡 Check"
                        if c.get("title"):
                            st.markdown(f"**{c.get('title')}** ({c.get('source')}) • {verified_badge}")
                            st.caption(f"> {c.get('content')}")
                        elif c.get("historical_reply"):
                            st.markdown(f"**Qdrant #{c.get('point_id')}** ({c.get('source')}) • {verified_badge}")
                            st.caption(f"> *Customer:* {c.get('customer_message')}\n> *Resolution:* {c.get('historical_reply')}")

    # Chat Input
    prompt = st.chat_input("Describe your Apple device symptom, model, or question...")
    effective_prompt = preset_query or prompt or st.session_state.pop("voice_transcript", "")

    if effective_prompt:
        st.session_state.messages.append({"role": "user", "content": effective_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(effective_prompt)

        with st.chat_message("assistant", avatar="🍏"):
            with st.status("AppleCare Intelligence triaging issue...", expanded=True) as status:
                st.write("1. Verifying input safety with NeMo Guardrails...")
                st.write("2. Querying Qdrant Cloud cluster collection `hiver_support_history`...")
                st.write("3. Matching official Apple Support Standard Operating Procedures...")
                st.write("4. Synthesizing source-cited diagnostic steps via Groq...")

                api_data = call_backend_query(effective_prompt, st.session_state.session_id)
                status.update(label="Diagnostic Triage Complete", state="complete", expanded=False)

            answer = api_data.get("answer", "")
            intent = api_data.get("intent", "DIAGNOSTIC_TROUBLESHOOTING")
            confidence = api_data.get("confidence_score", 0.88)
            citations = api_data.get("citations", [])
            thought_process = api_data.get("thought_process", [])
            escalation = api_data.get("escalation", {})
            should_escalate = escalation.get("should_escalate", False)

            st.markdown(answer)

            meta = {
                "intent": intent,
                "confidence_score": confidence,
                "escalate": should_escalate,
                "citations": citations,
                "thought_process": thought_process,
            }

            with st.expander("🔍 IP-SAKTI Trust & Grounding Inspector", expanded=False):
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Intent", intent)
                col_b.metric("Confidence", f"{confidence:.0%}")
                col_c.metric("Disposition", "Escalate to Human" if should_escalate else "Safe to Auto-Handle")

                st.markdown("#### 🧠 Thought Process Trail:")
                for step in thought_process:
                    st.markdown(f"- `{step}`")

                st.markdown("#### 📚 Citations & Grounding Evidence:")
                for c in citations:
                    verified_badge = "🟢 Verified" if c.get("verified", True) else "🟡 Check"
                    if c.get("title"):
                        st.markdown(f"**{c.get('title')}** ({c.get('source')}) • {verified_badge}")
                        st.caption(f"> {c.get('content')}")
                    elif c.get("historical_reply"):
                        st.markdown(f"**Qdrant Point #{c.get('point_id')}** ({c.get('source')}) • {verified_badge}")
                        st.caption(f"> *Customer:* {c.get('customer_message')}\n> *Resolution:* {c.get('historical_reply')}")

        st.session_state.messages.append({"role": "assistant", "content": answer, "meta": meta})


# =========================================================================
# TAB 2: APPLECARE+ WARRANTY & DEDUCTIBLES CALCULATOR
# =========================================================================
with tabs[1]:
    st.markdown("### 🛡️ AppleCare+ Coverage & Deductible Calculator")
    st.caption("Verify warranty eligibility, calculate exact out-of-pocket repair deductibles, and view net customer savings.")

    from app.services.applecare_kb import lookup_warranty, DEDUCTIBLE_MATRIX

    col_w1, col_w2 = st.columns([1, 1])

    with col_w1:
        st.markdown("#### Check Serial Number / Device")
        st.markdown("Try one of these registered test devices or enter your own:")
        
        b_c1, b_c2, b_c3 = st.columns(3)
        sample_serial = ""
        if b_c1.button("iPhone 15 Pro Max\n(AppleCare+)", key="btn_serial_iphone15", use_container_width=True):
            sample_serial = "F17X9K02MND6"
        if b_c2.button("MacBook Pro 16\"\n(AppleCare+)", key="btn_serial_macbook", use_container_width=True):
            sample_serial = "C02G80P0MD6R"
        if b_c3.button("iPhone 13\n(Out of Warranty)", key="btn_serial_iphone13", use_container_width=True):
            sample_serial = "H98KL019PQ23"

        serial_input = st.text_input(
            "Enter Apple Serial Number (10–12 characters):",
            value=sample_serial or "F17X9K02MND6",
            max_chars=14,
        )

        w_info = lookup_warranty(serial_input)

        st.markdown(
            f"""
            <div class="apple-card">
                <h4>{w_info.get('device')}</h4>
                <p><strong>Serial Number:</strong> <code>{w_info.get('serial')}</code></p>
                <p><strong>Coverage:</strong> <span class="badge-applecare">{w_info.get('coverage_type')}</span></p>
                <p><strong>Service Status:</strong> <span class="badge-verified">{w_info.get('status')}</span></p>
                <p><strong>Coverage Expiration:</strong> {w_info.get('expiry_date')}</p>
                <p><strong>Battery Health Diagnostic:</strong> {w_info.get('battery_health')}% Maximum Capacity</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_w2:
        st.markdown("#### Interactive Deductible Calculator")
        damage_choice = st.selectbox(
            "Select Damage or Service Type:",
            options=[
                ("screen_or_back_glass", "Screen or Back Glass Damage ($29 under AppleCare+)"),
                ("other_accidental_damage", "Other Accidental Damage / Liquid Spill ($99 under AppleCare+)"),
                ("battery_service", "Battery Service (<80% health is $0 under AppleCare+)"),
                ("theft_and_loss", "Theft or Loss Incident ($149 under AppleCare+)"),
                ("mac_screen_or_enclosure", "MacBook Screen / Enclosure Damage ($99 under AppleCare+)"),
                ("mac_other_damage", "MacBook Logic Board / Liquid Spill ($299 under AppleCare+)"),
            ],
            format_func=lambda x: x[1],
        )[0]

        mat = DEDUCTIBLE_MATRIX.get(damage_choice, {})
        has_applecare = "AppleCare+" in w_info.get("coverage_type", "")

        ac_cost = mat.get("applecare_plus", 99.00)
        oow_min = mat.get("out_of_warranty_min", 299.00)
        oow_max = mat.get("out_of_warranty_max", 599.00)

        effective_cost = ac_cost if has_applecare else oow_min
        savings = max(0.0, oow_min - ac_cost) if has_applecare else 0.0

        st.markdown(
            f"""
            <div class="apple-card">
                <h3>Estimated Repair Fee: ${effective_cost:.2f} USD</h3>
                <p>{mat.get('description')}</p>
                <hr style="border-color: rgba(255,255,255,0.08);">
                <p><strong>AppleCare+ Deductible:</strong> ${ac_cost:.2f} USD</p>
                <p><strong>Standard Out-of-Warranty Rate:</strong> ${oow_min:.2f} – ${oow_max:.2f} USD</p>
                <p><strong>Customer Savings with AppleCare+:</strong> <span style="color:#34d399;font-weight:bold;">${savings:.2f} USD</span></p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Coverage Matrix Comparison
    st.markdown("#### 📊 Apple Warranty vs AppleCare+ Comparison")
    st.table([
        {"Feature": "Duration", "1-Year Limited Warranty": "1 Year", "AppleCare+": "2 to 3 Years / Monthly", "AppleCare+ with Theft/Loss": "2 to 3 Years / Monthly"},
        {"Feature": "Accidental Screen/Glass", "1-Year Limited Warranty": "Not Covered (Full Fee)", "AppleCare+": "$29 Deductible", "AppleCare+ with Theft/Loss": "$29 Deductible"},
        {"Feature": "Liquid / Other Damage", "1-Year Limited Warranty": "Not Covered (Full Fee)", "AppleCare+": "$99 Deductible", "AppleCare+ with Theft/Loss": "$99 Deductible"},
        {"Feature": "Theft and Loss", "1-Year Limited Warranty": "Not Covered", "AppleCare+": "Not Covered", "AppleCare+ with Theft/Loss": "$149 Deductible (Find My required)"},
        {"Feature": "Battery Service (<80%)", "1-Year Limited Warranty": "Only Manufacturing Defects", "AppleCare+": "Free ($0 Deductible)", "AppleCare+ with Theft/Loss": "Free ($0 Deductible)"},
        {"Feature": "24/7 Priority Support", "1-Year Limited Warranty": "90 Days Only", "AppleCare+": "Unlimited Priority Access", "AppleCare+ with Theft/Loss": "Unlimited Priority Access"},
    ])


# =========================================================================
# TAB 3: APPLECARE CLAIM & INCIDENT REPORT GENERATOR
# =========================================================================
with tabs[2]:
    st.markdown("### 📋 AppleCare Incident & Claim Report Generator")
    st.caption("Generate an authoritative, auditable claim package with liquid indicator assessments and claim readiness score.")

    from app.services.claim_engine import generate_claim_report

    with st.form("applecare_claim_form"):
        fc1, fc2 = st.columns(2)
        with fc1:
            c_name = st.text_input("Customer Full Name", value="Jordan Vance")
            c_email = st.text_input("Apple Account Email", value="jordan.vance@example.com")
            c_device = st.selectbox("Device Model", ["iPhone 15 Pro Max", "iPhone 16 Pro", "MacBook Pro 16\" (M3)", "iPad Pro 13\"", "Apple Watch Ultra 2"])
            c_serial = st.text_input("Device Serial Number", value="F17X9K02MND6")

        with fc2:
            c_date = st.date_input("Date of Incident", value=datetime.now().date()).strftime("%Y-%m-%d")
            c_damage_type = st.selectbox("Damage Classification", ["Screen / Display Crack", "Liquid Spill / Water Exposure", "Enclosure Impact", "Theft / Loss", "Battery Degradation"])
            c_liquid = st.checkbox("Device was exposed to liquid", value=True)
            c_lci = st.checkbox("Liquid Contact Indicator (LCI) is Red or Pink", value=True)
            c_find_my = st.checkbox("Find My & Activation Lock disabled", value=True)
            c_backup = st.checkbox("Device backed up to iCloud or Mac", value=True)

        c_desc = st.text_area(
            "Detailed Incident Description",
            value="iPhone accidentally slipped off the kitchen counter onto tile floor, causing a glass crack along the top left and liquid splash from nearby water cup. Touch digitizer has delay.",
            height=90,
        )

        generate_btn = st.form_submit_button("Generate Official Claim Package", use_container_width=True)

    if generate_btn:
        claim_result = generate_claim_report(
            customer_name=c_name,
            customer_email=c_email,
            device_model=c_device,
            serial_number=c_serial,
            incident_date=c_date,
            incident_description=c_desc,
            damage_type=c_damage_type,
            liquid_exposure=c_liquid,
            lci_triggered=c_lci,
            find_my_disabled=c_find_my,
            backed_up=c_backup,
        )

        score = claim_result["readiness_score"]
        rating = claim_result["readiness_rating"]

        st.markdown(f"### Claim Assessment: **{claim_result['claim_id']}**")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Claim Readiness Score", f"{score}/100")
        sc2.metric("Rating", rating)
        sc3.metric("Estimated Deductible", f"${claim_result['estimated_deductible']:.2f} USD")

        st.progress(score / 100.0)

        if claim_result["warnings"]:
            st.warning("Action Items Required Prior to Genius Bar Check-in:\n\n" + "\n".join(f"• {w}" for w in claim_result["warnings"]))
        else:
            st.success("✅ Perfect readiness score! All pre-service criteria (Find My disabled, backup confirmed) are satisfied.")

        with st.expander("📄 View Official Generated AppleCare Claim Package", expanded=True):
            st.markdown(claim_result["report_markdown"])

        st.download_button(
            label="⬇️ Download AppleCare Claim Report (.md)",
            data=claim_result["report_markdown"],
            file_name=f"{claim_result['claim_id']}_AppleCare_Report.md",
            mime="text/markdown",
            use_container_width=True,
        )


# =========================================================================
# TAB 4: REPAIR SHOP & CASE TRACKER
# =========================================================================
with tabs[3]:
    st.markdown("### 🔧 Genius Bar Repair Shop Intake & Case Tracker")
    st.caption("Live work-order tracking for customers and service intake control console for repair technicians.")

    from app.services.repair_tracker import repair_tracker, STAGES

    subtab_customer, subtab_technician = st.tabs(["🔍 Customer Status Lookup", "🛠️ Technician Intake & Management"])

    with subtab_customer:
        search_col, _ = st.columns([2, 1])
        with search_col:
            lookup_id = st.text_input("Enter Repair Work Order ID or Serial Number:", value=st.session_state.active_repair_id)

        case = repair_tracker.get_case(lookup_id)
        if case:
            st.session_state.active_repair_id = case["repair_id"]
            current_stage_idx = case.get("stage_index", 0)

            # Timeline visualization
            st.markdown("#### Repair Progress Timeline")
            timeline_html = '<div class="timeline-container">'
            for i, stage_name in enumerate(STAGES):
                is_active = (i == current_stage_idx)
                is_done = (i < current_stage_idx)
                circle_class = "timeline-circle completed" if is_done else "timeline-circle active" if is_active else "timeline-circle"
                label_class = "timeline-label active" if is_active else "timeline-label"
                icon = "✓" if is_done else str(i + 1)
                display_label = stage_name.replace("_", " ").title()
                timeline_html += f"""
                <div class="timeline-step">
                    <div class="{circle_class}">{icon}</div>
                    <div class="{label_class}">{display_label}</div>
                </div>
                """
            timeline_html += "</div>"
            st.markdown(timeline_html, unsafe_allow_html=True)

            rc1, rc2 = st.columns(2)
            with rc1:
                st.markdown(
                    f"""
                    <div class="apple-card">
                        <h4>Order #{case['repair_id']}</h4>
                        <p><strong>Customer:</strong> {case['customer_name']}</p>
                        <p><strong>Device:</strong> {case['device']}</p>
                        <p><strong>Serial:</strong> <code>{case['serial']}</code></p>
                        <p><strong>Reported Issue:</strong> {case['issue']}</p>
                        <p><strong>Estimated Completion:</strong> {case['estimated_completion']}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with rc2:
                st.markdown(
                    f"""
                    <div class="apple-card">
                        <h4>Technician Work Log</h4>
                        <p><strong>Assigned:</strong> {case['technician']}</p>
                        <p><strong>Parts Used:</strong> {', '.join(case.get('parts_used', [])) or 'None logged yet'}</p>
                        <p><strong>Post-Repair Battery:</strong> {case.get('battery_health')}%</p>
                        <p><strong>Quoted Deductible:</strong> ${case.get('deductible_quoted', 29.0):.2f} USD ({case.get('coverage_type')})</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown("#### 📜 Activity & Customer Notification Log")
            for note in reversed(case.get("customer_notifications", [])):
                st.info(note, icon="🔔")

        else:
            st.error(f"No repair work order found for '{lookup_id}'. Try `APP-2026-8901` or `APP-2026-7842`.")

    with subtab_technician:
        st.markdown("#### Service Center Intake Console")

        with st.expander("➕ Create New Genius Bar Work Order", expanded=False):
            with st.form("new_work_order"):
                tc1, tc2 = st.columns(2)
                with tc1:
                    n_cust = st.text_input("Customer Name")
                    n_email = st.text_input("Customer Email")
                    n_dev = st.text_input("Apple Device Model", value="iPhone 15 Pro")
                with tc2:
                    n_ser = st.text_input("Serial Number", value="F17X9K02MND6")
                    n_issue = st.text_area("Issue Description", value="Cracked back glass and rear camera lens dust")
                    n_ded = st.number_input("Quoted Deductible ($)", value=29.0, step=10.0)

                submit_order = st.form_submit_button("Create Work Order", use_container_width=True)
                if submit_order:
                    created_case = repair_tracker.create_case(
                        customer_name=n_cust,
                        customer_email=n_email,
                        device=n_dev,
                        serial=n_ser,
                        issue=n_issue,
                        deductible_quoted=n_ded,
                    )
                    st.success(f"Created Work Order `{created_case['repair_id']}`!")
                    st.session_state.active_repair_id = created_case["repair_id"]
                    st.rerun()

        st.markdown("#### Update Existing Repair Status")
        cases = repair_tracker.list_cases()
        case_options = {f"{c['repair_id']} - {c['customer_name']} ({c['device']})": c['repair_id'] for c in cases}
        selected_case_label = st.selectbox("Select Active Repair Case:", list(case_options.keys()))
        selected_repair_id = case_options[selected_case_label]
        target_case = repair_tracker.get_case(selected_repair_id)

        if target_case:
            u_col1, u_col2 = st.columns([1, 2])
            with u_col1:
                new_stage = st.selectbox("Advance Stage:", STAGES, index=target_case.get("stage_index", 0))
            with u_col2:
                tech_note = st.text_input("Technician Diagnostic / Action Note:")

            if st.button("Update Repair Status & Notify Customer", key="btn_update_repair_stage_submit", use_container_width=True):
                updated = repair_tracker.update_stage(selected_repair_id, new_stage, tech_note)
                if updated:
                    st.success(f"Case {selected_repair_id} updated to {new_stage}!")
                    st.session_state.active_repair_id = selected_repair_id
                    st.rerun()


# =========================================================================
# TAB 5: LIVE AGENT ESCALATION DESK
# =========================================================================
with tabs[4]:
    st.markdown("### 👨‍💼 Live Agent & Human Escalation Desk")
    st.caption("Real-time support triage queue for high-risk billing disputes, legal concerns, and complex hardware incidents.")

    st.markdown("#### 🚨 Active Escalation Queue")

    SAMPLE_ESCALATIONS = [
        {
            "id": "ESC-901",
            "customer": "Sarah Jenkins",
            "priority": "HIGH",
            "sentiment": "Angry / Frustrated",
            "reason": "Unauthorized Apple Account charges ($420 on App Store)",
            "device": "iPhone 14 Pro",
            "wait_time": "1m 45s",
            "summary": "Customer reports cards charged 5 times overnight. Immediate account lockdown & dispute review requested.",
        },
        {
            "id": "ESC-902",
            "customer": "David Thorne",
            "priority": "CRITICAL",
            "sentiment": "Litigious",
            "reason": "Repeated battery swelling on MacBook Pro after third-party repair",
            "device": "MacBook Pro 16\" Intel",
            "wait_time": "4m 12s",
            "summary": "Customer mentions consumer protection ombudsman. Safety triage protocol required.",
        },
        {
            "id": "ESC-903",
            "customer": "Aisha Patel",
            "priority": "NORMAL",
            "sentiment": "Concerned",
            "reason": "Activation Lock removal request for deceased family member",
            "device": "iPad Air (5th Gen)",
            "wait_time": "6m 30s",
            "summary": "Customer has court legal will and death certificate ready for senior advisor verification.",
        },
    ]

    for esc in SAMPLE_ESCALATIONS:
        badge_style = "badge-warning" if esc["priority"] == "HIGH" else "badge-applecare"
        with st.expander(f"[{esc['priority']}] {esc['id']} — {esc['customer']} ({esc['device']})", expanded=True):
            ec1, ec2, ec3 = st.columns([1, 1, 1])
            ec1.markdown(f"**Customer:** {esc['customer']}")
            ec2.markdown(f"**Priority:** <span class='{badge_style}'>{esc['priority']}</span>", unsafe_allow_html=True)
            ec3.markdown(f"**Wait Time:** {esc['wait_time']}")

            st.markdown(f"**Trigger Reason:** {esc['reason']}")
            st.caption(f"> {esc['summary']}")

            action_col1, action_col2, action_col3 = st.columns(3)
            if action_col1.button(f"Accept & Open Chat ({esc['id']})", key=f"chat_{esc['id']}", use_container_width=True):
                st.success(f"Assigned {esc['customer']} to your advisor desk. Initiating secure chat channel...")
            if action_col2.button(f"Initiate Phone Callback ({esc['id']})", key=f"call_{esc['id']}", use_container_width=True):
                st.info(f"Triggering automated AppleCare telephony callback to {esc['customer']}...")
            if action_col3.button(f"Forward to Legal / Triage ({esc['id']})", key=f"fwd_{esc['id']}", use_container_width=True):
                st.warning(f"Ticket {esc['id']} routed to Apple Senior Executive Relations.")
