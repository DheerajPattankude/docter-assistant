import os
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI   # <-- using only OpenAI client

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
# STREAMLIT CONFIG
# =========================
st.set_page_config(page_title="Virtual Doctor Assistant", page_icon="🩺", layout="wide")
st.title("🩺 Virtual Doctor Assistant")
st.caption(DISCLAIMER)

# =========================
# USER INPUT
# =========================
symptoms = st.text_area("✍️ Write your symptoms", placeholder="Example: headache, dizziness, shortness of breath")

prev_conditions = st.multiselect(
    "📋 Previous conditions (if any)",
    ["Hypertension", "Diabetes", "Asthma", "Heart Disease", "Kidney Disease"]
)

use_ai = st.checkbox("🤖 Use Hugging Face Medical AI", value=True)

# =========================
# HUGGING FACE VIA OPENAI CLIENT
# =========================
def call_hf_chat(prompt: str, model: str = "meta-llama/Llama-3.1-8B-Instruct:cerebras") -> str:
    """
    Calls Hugging Face model through OpenAI-compatible API.
    Adds request to include references/sources.
    """
    if not HF_API_KEY:
        return "❌ Hugging Face API Key missing. Please set HF_API_KEY in your .env file."

    try:
        client = OpenAI(
            base_url="https://router.huggingface.co/v1",  # Hugging Face OpenAI-compatible endpoint
            api_key=HF_API_KEY,
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a medical assistant AI. Use docter varified site to answer."
                        "multipal doctors each doctor give answers : name and qualification, saparetly give result as prescription guidance, Prescribe drugs and some some guidance to patients for fast recovery,Always include reliable medical references each doctor saparetly. Minimum 10 doctors."
                        "In answer each doctor head line will be in bold leter" 
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=700,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[HF Chat Error] {e}"

# =========================
# ACTION
# =========================
if st.button("Get Advice"):
    if not symptoms.strip():
        st.warning("⚠️ Please enter your symptoms.")
    else:
        user_prompt = f"""
        Patient Symptoms: {symptoms}.
        Check against known diseases and specialists from database.
        Provide safe guidance only.
        """
        ai_response = call_hf_chat(user_prompt)
        st.write("### 🧑‍⚕️ Virtual Doctor Assistant Suggestion")
        st.write(ai_response)
        response = call_hf_chat(ai_response)
        st.markdown(response)

        st.subheader("🚨 Emergency Red Flags")
        for rf in RED_FLAGS:
            st.write(f"- {rf}")

        st.caption("Generated on " + datetime.now().strftime("%Y-%m-%d %H:%M"))










