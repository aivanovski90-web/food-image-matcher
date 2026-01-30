import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json
from playwright.sync_api import sync_playwright

# --- 1. CLOUD INSTALLATION FIX ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

# --- 2. SECURE CONFIGURATION ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Add it to Streamlit Secrets.")
    st.stop()

# --- MODEL FIX: Using the newer, supported models ---
# Use 'gemini-3-flash-preview' for maximum intelligence and speed
# Use 'gemini-2.5-flash' for stable production
MODEL_NAME = 'gemini-3-flash-preview' 
model = genai.GenerativeModel(MODEL_NAME)

# --- 3. UI SETUP ---
st.set_page_config(page_title="Menu Matcher Pro", page_icon="📸")
st.title("📸 Restaurant Menu Photo Matcher")
st.info(f"Currently using Model: {MODEL_NAME}")

with st.sidebar:
    st.header("Upload Files")
    uploaded_files = st.file_uploader("Upload Images (Max 500)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant Website URL")

if st.button("Start Processing Batch"):
    if not uploaded_files or not url:
        st.warning("Please provide a URL and upload your images.")
    else:
        status_text = st.empty()
        structured_menu = []

        # --- 4. OPAL-STYLE DATA EXTRACTION ---
        status_text.text("Connecting to website and grabbing HTML...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                # Wait for 'commit' to get the structure as fast as possible
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            # Using Gemini 3 Flash to convert messy HTML into a clean list
            status_text.text(f"Model {MODEL_NAME} is parsing the menu...")
            extract_prompt = (
                "Identify every menu item in this HTML content. "
                "Return ONLY a clean JSON list of strings like ['Dish 1', 'Dish 2']. "
                f"HTML: {raw_html[:25000]}"
            )
            extraction = model.generate_content(extract_prompt)
            # Clean JSON formatting
            clean_json = extraction.text.replace('```json', '').replace('```', '').strip()
            structured_menu = json.loads(clean_json)
        except Exception as e:
            st.error(f"Menu parsing failed with {MODEL_NAME}: {e}")
            st.stop()

        # --- 5. VISION MATCHING & BINARY COPY ---
        brand_name = url.split("//")[-1].split(".")[0].capitalize()
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        progress_bar = st.progress(0)
        valid_count = 0
        name_tracker = {}
        total_files = len(uploaded_files)

        # Memory Fix: Batching at 5 to prevent RAM spikes
        for i in range(0, total_files, 5):
            batch = uploaded_files[i : i + 5]
            for file in batch:
                file_bytes = file.getvalue()
                try:
                    # Match photo to the structured menu items
                    match_resp = model.generate_content([
                        f"From this list: {structured_menu}, which dish is this image? Return ONLY the name.",
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ])
                    
                    matched_name = match_resp.text.strip()
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                    
                    # 1KB Fix: Binary write to ensure full quality
                    count = name_tracker.get(clean_name, 0)
                    name_tracker[clean_name] = count + 1
                    suffix = f"_{count}" if count > 0 else ""
                    
                    dest_path = os.path.join(temp_dir, f"{clean_name}{suffix}.jpg")
                    with open(dest_path, "wb") as f:
                        f.write(file_bytes)
                    valid_count += 1
                except: continue
            
            # Progress Math Fix
            progress_bar.progress(min(100, int((i + 5) / total_files * 100)))

        # --- 6. PACKAGING & DOWNLOAD ---
        if valid_count > 0:
            zip_name = f"{brand_name}_Photos.zip"
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        z.write(os.path.join(root, f), f)
            
            st.success(f"Successfully matched {valid_count} images!")
            with open(zip_name, "rb") as f:
                st.download_button("💾 Download ZIP archive", data=f, file_name=zip_name)
            shutil.rmtree(temp_dir)
