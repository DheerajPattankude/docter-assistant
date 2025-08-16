# 🩺 Virtual Doctor Assistant

A **Streamlit-based AI-powered Virtual Doctor Assistant** that provides general health guidance using Hugging Face medical AI models via the OpenAI-compatible API.

⚠️ **Disclaimer:**  
This application is **not a diagnosis tool**. It only provides **general health guidance**.  
Always consult a qualified doctor for treatment.  
In case of severe or urgent symptoms, **seek emergency care immediately**.

---

## 🚀 Features
- Write your **symptoms** and get AI-powered medical guidance.
- Option to select **previous health conditions**.
- Uses **Hugging Face medical models** via OpenAI client.
- Highlights **emergency red flags**.
- Secure API key management using `.env`.

---

## 🛠️ Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/your-username/virtual-doctor-assistant.git
cd virtual-doctor-assistant
# Create venv
python -m venv venv

# Activate venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
pip install -r requirements.txt

