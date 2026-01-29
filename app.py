import streamlit as st
import google.generativeai as genai
from PIL import Image
import requests
from bs4 import BeautifulSoup

# --- CONFIG ---
st.set_page_config(page_title="Multi-Modal Gemini", layout="wide")
st.title("🌐 Multi-Image & Website Analyzer")

# API Setup
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

if not api_key:
    st.info("Please add your API key.")
    st.stop()

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- SIDEBAR: INPUTS ---
with st.sidebar:
    st.header("Inputs")
    # Multiple file uploader
    uploaded_files = st.file_uploader("Upload Images", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    # URL input
    url_input = st.text_input("Website Link (optional)", placeholder="https://example.com")

# --- UTILITY: WEB SCRAPER ---
def get_site_text(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Get text and clean it up
        return f"\n\nContent from {url}:\n" + soup.get_text()[:5000] # Limit to 5k chars
    except Exception as e:
        return f"\n(Could not read website: {e})"

# --- MAIN CHAT ---
user_prompt = st.chat_input("Ask a question about the images and the website...")

if user_prompt:
    # 1. Start the prompt list with the user's text
    content_payload = [user_prompt]
    
    # 2. Add Website Text if URL exists
    if url_input:
        with st.status("Reading website..."):
            site_context = get_site_text(url_input)
            content_payload.append(site_context)
    
    # 3. Add All Uploaded Images
    if uploaded_files:
        for uploaded_file in uploaded_files:
            img = Image.open(uploaded_file)
            content_payload.append(img)
            st.image(img, caption=uploaded_file.name, width=200)

    # 4. Generate Response
    with st.chat_message("assistant"):
        with st.spinner("Processing everything..."):
            try:
                # content_payload is now a list: [text_prompt, site_text, img1, img2, ...]
                response = model.generate_content(content_payload)
                st.markdown(response.text)
            except Exception as e:
                st.error(f"Error: {e}")
