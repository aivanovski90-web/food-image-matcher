import streamlit as st
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from PIL import Image
import io
import zipfile
import time

# --- PAGE SETUP ---
st.set_page_config(page_title="AI Food Matcher Pro", layout="wide")
st.title("🤖 AI Restaurant Matcher")

# --- AI CONFIGURATION ---
# Improved: More robust key checking
if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Configure the model with safety settings
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=safety_settings)
    except Exception as e:
        st.error(f"Failed to configure AI: {e}")
else:
    st.error("Missing API Key! Please go to App Settings > Secrets and add: GEMINI_API_KEY = 'your_key'")

# --- SIDEBAR: MENU SOURCE ---
st.sidebar.header("1. Menu Source")
url = st.sidebar.text_input("Paste Restaurant URL:")
menu_items = []

if url:
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Scrapes common header and bold tags for dish names
        tags = soup.find_all(['h2', 'h3', 'h4', 'strong', 'b', 'span'])
        menu_items = sorted(list(set([t.get_text().strip() for t in tags if 3 < len(t.get_text().strip()) < 50])))
        if menu_items:
            st.sidebar.success(f"Found {len(menu_items)} potential menu items!")
        else:
            st.sidebar.warning("No items found. Try pasting the menu manually below.")
    except Exception as e:
        st.sidebar.error(f"Link Error: {e}")

# Manual Backup Box
manual_menu = st.sidebar.text_area("Or paste menu items here (one per line):")
if manual_menu:
    menu_items = [item.strip() for item in manual_menu.split('\n') if item.strip()]

# --- MAIN: UPLOAD & MATCH ---
st.header("2. Upload & Auto-Match")
uploaded_files = st.file_uploader("Drop images here", accept_multiple_files=True, type=['jpg', 'png', 'jpeg'])

if uploaded_files and menu_items:
    if st.button("🚀 Start AI Matching"):
        results = {}
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            try:
                # Prepare image
                img = Image.open(file)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Ask AI
                prompt = f"Which item from this list is in the photo? List: {menu_items}. Return ONLY the exact name."
                response = model.generate_content([prompt, img])
                
                # Check for valid AI response
                if response and response.text:
                    match_name = response.text.strip()
                    results[file.name] = {"match": match_name, "bytes": file.getvalue()}
                    st.write(f"✅ **{file.name}** matched to: {match_name}")
                
                # Respect rate limits (Free tier: 15 RPM)
                time.sleep(4) 
                
            except Exception as e:
                st.error(f"❌ Error with {file.name}: {e}")
            
            progress_bar.progress((i + 1) / len(uploaded_files))

        # --- STEP 3: DOWNLOAD ---
        if results:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a") as zip_file:
                for original_name, data in results.items():
                    safe_name = "".join([c for c in data['match'] if c.isalnum() or c in (' ', '_')]).strip()
                    zip_file.writestr(f"{safe_name}.jpg", data['bytes'])
            
            st.download_button(
                label="📥 Download Renamed Zip",
                data=zip_buffer.getvalue(),
                file_name="matched_images.zip",
                mime="application/zip"
            )
