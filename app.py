import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil
from playwright.sync_api import sync_playwright

# --- 1. CLOUD INSTALLATION FIX ---
# Automatically install Playwright browser binaries on the first run
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

# --- 2. CONFIGURATION & SECRETS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Add it to Streamlit Cloud Settings > Secrets.")
    st.stop()

model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. APP INTERFACE ---
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

        # --- 4. SCRAPING PHASE (With Stealth Fixes) ---
        status_text.text("Connecting to restaurant website...")
        menu_text = ""
        try:
            with sync_playwright() as p:
                # Launch with arguments to prevent bot detection from hanging
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                
                # Faster loading strategy (domcontentloaded) and longer timeout
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Give the site 5 seconds to finish any JS rendering
                page.wait_for_timeout(5000) 
                menu_text = page.inner_text("body")
                browser.close()
        except Exception as e:
            st.error(f"The website did not respond in time. Try a direct menu link. Error: {e}")
            st.stop()

        # --- 5. VISION & PROCESSING PHASE ---
        # Extract Brand Name
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
                    # Match Image via Gemini (Analysis mode only)
                    response = model.generate_content([
                        f"Identify this dish from the menu text provided: {menu_text}. Return ONLY the name.",
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ])
                    
                    matched_name = response.text.strip()
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                    
                    # Deduplication
                    count = name_tracker.get(clean_name, 0)
                    name_tracker[clean_name] = count + 1
                    suffix = f"_{count}" if count > 0 else ""
                    
                    # 1KB Binary Write Fix
                    dest_path = os.path.join(temp_dir, f"{clean_name}{suffix}.jpg")
                    with open(dest_path, "wb") as f:
                        f.write(file_bytes)
                    
                    if os.path.getsize(dest_path) > 2000:
                        valid_count += 1
                except: continue
            
            progress_bar.progress(min(100, int((i + batch_size) / total_files * 100)))

        # --- 6. ZIPPING & AUTO-DOWNLOAD ---
        if valid_count > 0:
            zip_file_name = f"{brand_name}_Photos.zip"
            with zipfile.ZipFile(zip_file_name, 'w', zipfile.ZIP_DEFLATED) as z:
                for f in os.listdir(temp_dir):
                    z.write(os.path.join(temp_dir, f), f)
            
            status_text.success(f"Success! Processed {valid_count} images.")
            with open(zip_file_name, "rb") as f:
                st.download_button("💾 Download ZIP archive", data=f, file_name=zip_file_name, use_container_width=True)
            
            shutil.rmtree(temp_dir)
