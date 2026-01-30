import os

# Auto-install Playwright browsers if they are missing
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")
import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil
from playwright.sync_api import sync_playwright

# --- SECURE CONFIGURATION ---
try:
    # Pulls key from Streamlit Cloud Secrets dashboard
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Please add it to your Streamlit Secrets dashboard.")
    st.stop()

model = genai.GenerativeModel('gemini-1.5-flash')

# --- APP UI ---
st.set_page_config(page_title="Menu Photo Packager", page_icon="📸")
st.title("📸 Restaurant Menu Photo Packager")

with st.sidebar:
    st.header("Upload Settings")
    uploaded_files = st.file_uploader("Upload Menu Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant Website URL")

if st.button("Start Processing Batch"):
    if not uploaded_files or not url:
        st.warning("Please upload images and provide a URL.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 1. SCRAPING PHASE (Playwright Engine)
        status_text.text("Connecting to restaurant website...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                menu_text = page.inner_text("body")
                browser.close()
        except Exception as e:
            st.error(f"Scraping failed: {e}")
            st.stop()

        # 2. ANALYSIS & PROCESSING PHASE
        brand_match = re.search(r'https?://(?:www\.)?([^./]+)', url)
        brand_name = brand_match.group(1).capitalize() if brand_match else "Restaurant"
        
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        valid_count = 0
        name_tracker = {}
        batch_size = 5 # Memory Fix
        total_files = len(uploaded_files)
        
        for i in range(0, total_files, batch_size):
            batch = uploaded_files[i : i + batch_size]
            for file in batch:
                file_bytes = file.getvalue()
                try:
                    # Match Image via Gemini Vision (Classifier Mode)
                    response = model.generate_content([
                        f"Identify this food item from the following menu: {menu_text}. Return ONLY the dish name.",
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ])
                    
                    matched_name = response.text.strip()
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                    
                    count = name_tracker.get(clean_name, 0)
                    name_tracker[clean_name] = count + 1
                    suffix = f"_{count}" if count > 0 else ""
                    
                    # Binary Write (1KB Fix)
                    dest_path = os.path.join(temp_dir, f"{clean_name}{suffix}.jpg")
                    with open(dest_path, "wb") as f:
                        f.write(file_bytes)
                    
                    if os.path.getsize(dest_path) > 2000:
                        valid_count += 1
                except:
                    continue
            
            progress_bar.progress(min(100, int((i + batch_size) / total_files * 100)))

        # 3. ZIPPING & DOWNLOAD
        if valid_count > 0:
            zip_path = f"{brand_name}_Photos.zip"
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
                for f in os.listdir(temp_dir):
                    z.write(os.path.join(temp_dir, f), f)
            
            with open(zip_path, "rb") as f:
                st.download_button("💾 Download ZIP", data=f, file_name=zip_path, use_container_width=True)
            shutil.rmtree(temp_dir)
