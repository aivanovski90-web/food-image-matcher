import streamlit as st
import google.generativeai as genai
from PIL import Image

# --- PAGE CONFIG ---
st.set_page_config(page_title="Gemini Vision Chat", layout="wide")
st.title("👁️ Gemini Vision Assistant")

# --- 1. SECURE API KEY SETUP ---
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

if not api_key:
    st.info("Please add your Gemini API key to continue.", icon="🔑")
    st.stop()

genai.configure(api_key=api_key)

# --- 2. INITIALIZE SESSION STATE ---
# This keeps the chat history alive even when the app reruns
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- 3. SIDEBAR: IMAGE UPLOAD ---
with st.sidebar:
    st.header("Upload Image")
    uploaded_file = st.file_uploader("Choose a picture...", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Preview", use_container_width=True)
    
    if st.button("Clear Chat"):
        st.session_state.chat_history = []
        st.rerun()

# --- 4. MODEL SETUP ---
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 5. CHAT INTERFACE ---
# Display existing chat messages
for role, text in st.session_state.chat_history:
    with st.chat_message(role):
        st.markdown(text)

# Input for new message
if user_input := st.chat_input("Ask something about the image..."):
    if not uploaded_file:
        st.error("Please upload an image first!")
    else:
        # Display user message
        st.chat_message("user").markdown(user_input)
        st.session_state.chat_history.append(("user", user_input))

        # Generate Gemini response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                try:
                    # Pass both the text prompt and the image object
                    response = model.generate_content([user_input, img])
                    st.markdown(response.text)
                    st.session_state.chat_history.append(("assistant", response.text))
                except Exception as e:
                    st.error(f"Error: {e}")
