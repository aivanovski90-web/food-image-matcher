import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json
from playwright.sync_api import sync_playwright

# --- 1. CLOUD INSTALLATION ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

# --- 2. CONFIGURATION ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Add it to Streamlit Secrets.")
    st.stop()

# Using Gemini 1.5 Flash for speed and high context
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. UI SETUP ---
st.set_page_config(page_title="Menu Matcher Pro", page_icon="📸")
st.title("📸 Restaurant Menu Photo Matcher")

with st.sidebar:
    st.header("Upload Files")
    uploaded_files = st.file_uploader("Upload Images (Max 500)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant Website URL")

if st.button("Start Processing"):
    if not uploaded_files or not url:
        st.warning("Provide both images and a valid URL.")
    else:
        status_text = st.empty()
        
        # --- 4. DATA EXTRACTION (OPAL LOGIC) ---
        status_text.text("Connecting and extracting HTML data...")
        structured_menu = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                # commit strategy stops as soon as raw data is available
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            # MIMIC OPAL: Use Gemini to clean the HTML into a structured JSON list
            status_text.text("Gemini is parsing the menu structure...")
            extract_prompt = f"Extract all menu items and their short descriptions from this HTML. Return ONLY a valid JSON list of strings like ['Dish Name', 'Dish Name']. HTML: {raw_html[:20000]}"
            extraction = model.generate_content(extract_prompt)
            # Basic cleanup of the response to ensure valid JSON
            menu_list_raw = extraction.text.replace('```json', '').replace('```', '').strip()
            structured_menu = json.loads(menu_list_raw)
        except Exception as e:
            st.error(f"Failed to parse menu: {e}. Try pasting the menu text manually.")
            st.stop()

        # --- 5. VISION & MATCHING ---
        brand_name = url.split("//")[-1].split(".")[0].capitalize()
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        progress_bar = st.progress(0)
        valid_count = 0
        name_tracker = {}
        total_files = len(uploaded_files)

        # Memory Fix: Process in batches of 5
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
            
            # MATH FIX: min(100, ...) ensures progress bar stays in range
            progress_bar.progress(min(100, int((i + 5) / total_files * 100)))

        # --- 6. ZIP & DOWNLOAD ---
        if valid_count > 0:
            zip_name = f"{brand_name}_Photos.zip"
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
                for f in os.listdir(temp_dir):
                    z.write(os.path.join(temp_dir, f), f)
            
            st.success(f"Matched {valid_count} photos!")
            with open(zip_name, "rb") as f:
                st.download_button("💾 Download Results", data=f, file_name=zip_name)
            shutil.rmtree(temp_dir)
