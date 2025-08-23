# app.py
import os
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from deep_translator import GoogleTranslator
from gtts import gTTS

# =========================
# ENVIRONMENT
# =========================
load_dotenv()
HF_API_KEY = os.getenv("HF_API_KEY", "")

# =========================
# SAFETY
# =========================
DISCLAIMER = (
    "⚠️ This is **not a diagnosis**. It provides general health guidance. "
    "Always consult a qualified doctor for treatment. In case of severe or urgent symptoms, "
    "seek emergency care immediately."
)
RED_FLAGS = [
    "Severe chest pain",
    "Sudden difficulty breathing",
    "Confusion or fainting",
    "Seizure",
    "Very high blood pressure (≥ 180/120 mmHg)",
    "High fever with stiff neck",
]

# =========================
# HUGGING FACE VIA OPENAI CLIENT
# =========================
def call_hf_chat(prompt: str, model: str = "meta-llama/Llama-3.1-8B-Instruct:cerebras") -> str:
    if not HF_API_KEY:
        return "❌ Hugging Face API Key missing. Please set HF_API_KEY in your .env file."
    try:
        client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=HF_API_KEY,
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You are a medical assistant AI. Use doctor-verified sites to answer. "
                    "Multiple doctors each give answers: name and qualification, separately give result as prescription guidance. "
                    "Prescribe drugs and provide guidance for fast recovery. Always include reliable medical references for each doctor. "
                    "Minimum 5 doctors. Each doctor suggestion must be prefixed with **Doctor Name (Qualification):**"
                )},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=700,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[HF Chat Error] {e}"

# =========================
# AI-DRIVEN RELATED SYMPTOMS
# =========================
def get_ai_related_symptoms(symptoms, prev_conditions):
    if not symptoms.strip():
        return []
    prompt = f""" 
    The patient problem: {symptoms}. Previous conditions: {', '.join(prev_conditions) if prev_conditions else 'None'}.
    Based on the patient problem and previous conditions, suggest 5 related possible symptoms/questions the patient may consider. 
    Only related symptoms, no headlines needed. They are independent of advice output.
    """
    response = call_hf_chat(prompt)
    suggestions = [s.strip() for s in response.replace("\n", ",").split(",") if s.strip()]
    return suggestions[:5]

# =========================
# TRANSLATION UTILITIES
# =========================
def translate_text(text, target_lang):
    if not text.strip():
        return ""
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception as e:
        st.error(f"[Translation Error] {e}")
        return text

# =========================
# ADVICE FUNCTIONS
# =========================
def generate_advice(symptoms_input, prev_conditions, selected_lang):
    languages = {
        "English": "en","Hindi": "hi","Marathi": "mr","Tamil": "ta","Telugu": "te",
        "Kannada": "kn","Gujarati": "gu","Punjabi": "pa","Bengali": "bn",
        "Malayalam": "ml","Urdu": "ur"
    }
    user_prompt = f"""
    Patient Symptoms: {symptoms_input}.
    Previous Conditions: {', '.join(prev_conditions) if prev_conditions else 'None'}.
    Provide safe guidance only with correct grammar.
    """
    ai_response = call_hf_chat(user_prompt)
    translated_text = translate_text(ai_response, languages[selected_lang])
    st.session_state["advice_text"] = translated_text

def generate_audio(selected_lang):
    languages = {
        "English": "en","Hindi": "hi","Marathi": "mr","Tamil": "ta","Telugu": "te",
        "Kannada": "kn","Gujarati": "gu","Punjabi": "pa","Bengali": "bn",
        "Malayalam": "ml","Urdu": "ur"
    }
    if "advice_text" not in st.session_state:
        return
    try:
        tts = gTTS(st.session_state["advice_text"], lang=languages[selected_lang])
        audio_file = "output.mp3"
        tts.save(audio_file)
        st.session_state["advice_audio_file"] = audio_file
    except Exception as e:
        st.error(f"Audio generation failed: {e}")

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="Virtual Doctor Assistant", page_icon="🩺", layout="wide")
st.markdown(
    """
    <style>
    textarea, .stMultiSelect, .stSelectbox { background-color: #f0f9ff !important; border: 2px solid #0284c7 !important; border-radius: 10px !important; padding: 8px !important; }
    .stButton>button { background-color: #0284c7; color: white; border-radius: 8px; padding: 10px 20px; border: none; font-weight: bold; }
    .stButton>button:hover { background-color: #0369a1; color: white; }
    .suggestion-box { background-color: #e0f7fa; border: 2px solid #0284c7; border-radius: 8px; padding: 10px; max-height: 500px; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 8px; }
    .suggestion-item { background-color: #ffffff; padding: 6px 10px; border-radius: 20px; border: 1px solid #0284c7; font-size: 14px; flex: 0 0 auto; }
    .suggestion-item:hover { background-color: #b2ebf2; cursor: pointer; }
    </style>
    """, unsafe_allow_html=True
)
st.title("🩺 Virtual Medi Assistant")
st.caption(DISCLAIMER)

# Initialize session states
if "symptoms_list" not in st.session_state:
    st.session_state["symptoms_list"] = []

# =========================
# LAYOUT
# =========================
main_col, suggestion_col = st.columns([1.5, 1.5])

# LEFT COLUMN
with main_col:
    languages = {
        "English": "en","Hindi": "hi","Marathi": "mr","Tamil": "ta","Telugu": "te",
        "Kannada": "kn","Gujarati": "gu","Punjabi": "pa","Bengali": "bn",
        "Malayalam": "ml","Urdu": "ur"
    }
    selected_lang = st.selectbox("🌐 Select output language", list(languages.keys()))

    user_input = st.text_area(
        "✍️ Enter your symptoms",
        value=" with ".join(st.session_state["symptoms_list"]),
        height=150,
        placeholder="Example: headache, dizziness"
    )
    if user_input:
        st.session_state["symptoms_list"] = [s.strip() for s in user_input.split(" with ") if s.strip()]

    prev_conditions = st.multiselect(
        "📋 Previous conditions (if any)",
        ["Hypertension", "Diabetes", "Asthma", "Heart Disease", "Kidney Disease"]
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 Get Advice (Text)"):
            if not st.session_state["symptoms_list"]:
                st.warning("⚠️ Please enter your symptoms.")
            else:
                generate_advice(" with ".join(st.session_state["symptoms_list"]), prev_conditions, selected_lang)
    with col2:
        if st.button("🔊 Get Advice (Audio)"):
            if not st.session_state["symptoms_list"]:
                st.warning("⚠️ Please enter your symptoms.")
            else:
                generate_advice(" with ".join(st.session_state["symptoms_list"]), prev_conditions, selected_lang)
                generate_audio(selected_lang)

# RIGHT COLUMN: AI suggestions
with suggestion_col:
    st.markdown("### 💡 Related Symptoms (AI Suggestions)")
    suggestions = get_ai_related_symptoms(" with ".join(st.session_state["symptoms_list"]), prev_conditions)
    if suggestions:
        st.markdown('<div class="suggestion-box">', unsafe_allow_html=True)
        for s in suggestions:
            if not s.endswith("?"):
                s = s + "?"
            key = f"suggestion_{s}"
            if st.button(s, key=key):
                clean = s.replace("You have", "I have").replace("Have you", "I had").replace("Are you", "I feel").rstrip("?")
                if clean not in st.session_state["symptoms_list"]:
                    st.session_state["symptoms_list"].append(clean)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("AI will suggest related symptoms/questions as you type.")

# =========================
# DISPLAY ADVICE & RED FLAGS
# =========================
if "advice_text" in st.session_state or "advice_audio_file" in st.session_state:
    left, right = st.columns(2)
    with left:
        if "advice_text" in st.session_state:
            st.markdown("### 🧑‍⚕️ Virtual Doctor Assistant Suggestions")

            advice_blocks = st.session_state["advice_text"].split("**Doctor")
            for idx, block in enumerate(advice_blocks):
                if not block.strip():
                    continue
                if idx == 0 and not block.startswith("Doctor"):
                    content = block.strip()
                    header = "General Advice"
                else:
                    content = "**Doctor" + block.strip()
                    header = content.split("**")[1].strip(":") if "**" in content else "Doctor"

                # Doctor Box with header bar
                st.markdown(
                    f"""
                    <div style="border:2px solid #38a169;border-radius:10px;margin:10px 0;">
                        <div style="background:#38a169;color:white;padding:8px;border-radius:8px 8px 0 0;font-weight:bold;">
                            {header}
                        </div>
                        <div style="background:#f0fff4;padding:15px;border-radius:0 0 8px 8px;">
                            {content}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            st.subheader("🚨 Emergency Red Flags")
            for rf in RED_FLAGS:
                st.markdown(
                    f'<div style="background:#fffaf0;border-left:5px solid #dd6b20;'
                    f'padding:8px;margin:5px 0;border-radius:8px;">- {rf}</div>',
                    unsafe_allow_html=True
                )
            st.caption("Generated on " + datetime.now().strftime("%Y-%m-%d %H:%M"))

    with right:
        if "advice_audio_file" in st.session_state:
            st.markdown("### 🔊 Audio Advice")
            st.audio(st.session_state["advice_audio_file"], format="audio/mp3")

            st.subheader("🚨 Emergency Red Flags")
            for rf in RED_FLAGS:
                st.markdown(
                    f'<div style="background:#fffaf0;border-left:5px solid #dd6b20;'
                    f'padding:8px;margin:5px 0;border-radius:8px;">- {rf}</div>',
                    unsafe_allow_html=True
                )
            st.caption("Generated on " + datetime.now().strftime("%Y-%m-%d %H:%M"))



