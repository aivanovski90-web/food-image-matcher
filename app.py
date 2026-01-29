import streamlit as st
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from PIL import Image
import io
import zipfile
import time  # New: To handle rate limits

# --- PAGE SETUP ---
st.set_page_config(page_title="AI Food Matcher Pro", layout="wide")
st.title("🤖 AI Restaurant Matcher (Updated)")

# --- AI CONFIGURATION ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    # Updated: Added Safety Settings to prevent the AI from blocking food images
    # Threshold "BLOCK_NONE" ensures the AI doesn't accidentally trigger on harmless photos
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=safety_settings)
else:
    st.error("Missing API Key. Add 'GEMINI_API_KEY' to Streamlit Secrets.")

# --- SIDEBAR: MENU SCRAPER ---
st.sidebar.header("1. Menu Source")
url = st.sidebar.text_input("Paste Restaurant URL:")
menu_items = []

if url:
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Improved Scraping: Looking for common menu tags
        tags = soup.find_all(['h2', 'h3', 'h4', 'strong', 'b', 'span'])
        menu_items = sorted(list(set([t.get_text().strip() for t in tags if 3 < len(t.get_text().strip()) < 50])))
        st.sidebar.success(f"Found {len(menu_items)} potential menu items!")
    except Exception as e:
        st.sidebar.error(f"Error reading website: {e}")

# Manual Backup: In case scraping fails
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
                # 1. Process Image
                img = Image.open(file)
                if img.mode != 'RGB':
                    img = img.convert('RGB') # Fix for certain PNG/WebP files
                
                # 2. AI Prompt
                prompt = f"From this list: {menu_items}, identify which dish is in this photo. Return ONLY the exact name from the list."
                
                # 3. Call AI
                response = model.generate_content([prompt, img])
                match_name = response.text.strip()
                
                # 4. Save results
                results[file.name] = {"match": match_name, "bytes": file.getvalue()}
                st.write(f"✅ **{file.name}** matched to: {match_name}")
                
                # 5. Rate Limit Protection (Crucial for Free Tier)
                # Pauses for 2 seconds every image to stay under the 15 requests per minute limit
                time.sleep(2) 
                
            except Exception as e:
                # Specific error handling for the "429" rate limit error
                if "429" in str(e):
                    st.warning(f"⚠️ API Busy (Rate Limit). Waiting 10 seconds to retry {file.name}...")
                    time.sleep(10)
                else:
                    st.error(f"❌ Could not match {file.name}: {e}")
            
            progress_bar.progress((i + 1) / len(uploaded_files))

        # --- STEP 3: DOWNLOAD ---
        if results:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a") as zip_file:
                for original_name, data in results.items():
                    # Sanitize the new filename
                    safe_name = "".join([c for c in data['match'] if c.isalnum() or c in (' ', '_')]).strip()
                    zip_file.writestr(f"{safe_name}.jpg", data['bytes'])
            
            st.download_button(
                label="📥 Download Renamed Zip",
                data=zip_buffer.getvalue(),
                file_name="matched_images.zip",
                mime="application/zip"
            )
