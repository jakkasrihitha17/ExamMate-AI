from google import genai
from google.genai import types
import streamlit as st
import json
import time

from twilio.rest import Client as TwilioClient
from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE, SUMMARY_PROMPT

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = st.secrets["TWILIO_WHATSAPP_FROM"]
TWILIO_CONTENT_SID = st.secrets["TWILIO_CONTENT_SID"]

@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)

@st.cache_resource
def get_twilio_client():
    return TwilioClient(
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN
    )

MODEL_NAME = "gemini-3.8-flash"
gemini_client = get_gemini_client()
twilio_client = get_twilio_client()


def render_message(message):
    with st.chat_message(message["role"]):

        if message["kind"] == "text":
            st.write(message["content"])

        elif message["kind"] == "image":
            st.image(message["content"])

        if message.get("answer_type"):
            st.caption(f"Answer Type: {message['answer_type']}")
 
 
def add_message(role, kind, content, answer_type=None):
    message = {
        "role": role,
        "kind": kind,
        "content": content
    }

    if answer_type:
        message["answer_type"] = answer_type

    st.session_state.messages.append(message)
    render_message(st.session_state.messages[-1])

def ask_gemini(parts):
    for attempt in range(3):
        try:
            if len(parts) == 1 and isinstance(parts[0], str):
                contents = parts[0]
            else:
                contents = parts

            response = gemini_client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT
                )
            )

            return response.text

        except Exception as error:
            if "503" in str(error) and attempt < 2:
                time.sleep(2 ** attempt)
            else:
                return f"Sorry, something went wrong: {error}"

def clean_whatsapp_text(text):
    if not text:
        return ""

    text = " ".join(text.split())

    if len(text) > 1500:
        return text[:1497] + "..."

    return text


def send_whatsapp(to_number, user_name, summary):
    try:
        content_variables = json.dumps(
            {
                "1": user_name,
                "2": clean_whatsapp_text(summary)
            },
            ensure_ascii=False
        )

        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{to_number}",
            content_sid=TWILIO_CONTENT_SID,
            content_variables=content_variables
        )

        return True, message.sid

    except Exception as error:
        return False, str(error)


if 'onboarded' not in st.session_state:
    st.title("📚 ExamMate AI")
    st.caption("I can turn your study material into exam-ready preparation."
    "Upload your material and let's start preparing!")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        whatsapp_number = st.text_input(
            "WhatsApp number along with country code",
            placeholder = "+91XXXXXXXXXX",
            help ="We'll use this number to send your study preparation via WhatsApp."
        )

        submitted = st.form_submit_button("Let's start")
    if submitted:
        if not name.strip() or not whatsapp_number.strip():
            st.warning("Please kindly fill both the name and whatsapp number")
        else:
            st.session_state.name = name.strip()
            st.session_state.whatsapp_number = whatsapp_number.strip()
            #activate my AI
            st.session_state.chat = gemini_client.chats.create(model = MODEL_NAME,config = types.GenerateContentConfig(system_instruction = SYSTEM_PROMPT),
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()
    st.stop()


#chat interface
header_col, button_col = st.columns([5, 2], vertical_alignment="center")

with header_col:
    st.title("📚 ExamMate AI")

with button_col:
    has_ai_answer = any(
    message["role"] == "assistant"
    and message["kind"] == "text"
    for message in st.session_state.messages
    )

    if st.button(
        "📤 Send to WhatsApp",
        disabled=not has_ai_answer,
        use_container_width=True
    ):
   
        with st.spinner("Preparing your WhatsApp message..."):

            # Get the latest AI response
            ai_messages = [
                message
                for message in st.session_state.messages
                if message["role"] == "assistant"
                and message["kind"] == "text"
            ]

            if ai_messages:
                latest_answer = ai_messages[-1]["content"]

                success, info = send_whatsapp(
                    st.session_state.whatsapp_number,
                    st.session_state.name,
                    latest_answer
                )

                if success:
                    st.success("Sent to your WhatsApp! 📲")
                else:
                    st.error(f"Couldn't send: {info}")

 
if not st.session_state.messages:
    add_message("assistant", "text", WELCOME_MESSAGE.format(name=st.session_state.name))
else:
    for message in st.session_state.messages:
        render_message(message)

answer_type = st.selectbox(
    "Choose your preparation type:",
    ["Quick Revision", "2 Marks", "5 Marks", "10 Marks", "Deep Study"]
)

user_input = st.chat_input(
    "Enter your study material or attach an image",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)
 
if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text.strip()

    parts = []

    # Handle uploaded image
    if photo is not None:
        photo_bytes = photo.getvalue()

        add_message("user", "image", photo_bytes,answer_type)

        parts.append(
            types.Part.from_bytes(
                data=photo_bytes,
                mime_type=photo.type
            )
        )

    # Handle typed text
    if text:
        add_message("user", "text", text,answer_type)
        material = text

    elif photo is not None:
        material = "The study material is provided in the uploaded image."

    else:
        material = ""

    # Create the complete prompt
    prompt = SUMMARY_PROMPT.format(
        answer_type=answer_type,
        material=material
    )

    # Add the prompt to Gemini request
    parts.append(prompt)

    with st.spinner("🔄 Analyzing your study material..."):
        answer = ask_gemini(parts)

    add_message("assistant", "text", answer)











    