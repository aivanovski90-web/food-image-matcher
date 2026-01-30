import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json, time
from playwright.sync_api import sync_playwright
from google.api_core.exceptions import ResourceExhausted

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

# Optimized for 1,000 requests/day on Free Tier
MODEL_NAME = 'gemini-2.5-flash-lite'
model = genai.GenerativeModel(MODEL_NAME)

# --- 3. HELPER: RETRY LOGIC ---
def call_gemini_with_retry(prompt_data, max_retries=3):
    """Handles 429 errors by backing off as suggested by the API."""
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt_data, generation_config={"temperature": 0.2})
        except ResourceExhausted as e:
            # Extract suggested wait time or default to 35s
            wait_seconds = 35 
            st.warning(f"Quota reached. Sleeping {wait_seconds}s before retry {attempt+1}/{max_retries}...")
            time.sleep(wait_seconds)
        except Exception as e:
            st.error(f"AI Error: {e}")
            return None
    return None

# --- 4. UI SETUP ---
st.set_page_config(page_title="High-Quota Matcher", page_icon="📸")
st.title("📸 High-Quota Menu Matcher")
st.info(f"Using {MODEL_NAME} (Higher Daily Limits)")

with st.sidebar:
    st.header("Upload Settings")
    uploaded_files = st.file_uploader("Upload Images (Max 500)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant Website URL")

if st.button("Start Processing Batch"):
    if not uploaded_files or not url:
        st.warning("Please provide a URL and upload images.")
    else:
        status_text = st.empty()
        
        # A. SCRAPING PHASE
        status_text.text("Extracting menu data...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            # Extraction with Retry
            extract_prompt = f"Identify all menu items and descriptions from this HTML. Return ONLY a JSON list of objects: [{{'item': 'Name', 'info': 'Desc'}}] HTML: {raw_html[:20000]}"
            extraction = call_gemini_with_retry(extract_prompt)
            if not extraction: st.stop()
            
            clean_json = extraction.text.replace('```json', '').replace('```', '').strip()
            structured_menu = json.loads(clean_json)
        except Exception as e:
            st.error(f"Extraction failed: {e}")
            st.stop()

        # B. VISION MATCHING
        brand_match = re.search(r'https?://(?:www\.)?([^./]+)', url)
        brand_name = brand_match.group(1).capitalize() if brand_match else "Restaurant"
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        progress_bar = st.progress(0)
        name_tracker = {}
        total_files = len(uploaded_files)

        for i in range(0, total_files, 5):
            batch = uploaded_files[i : i + 5]
            for file in batch:
                file_bytes = file.getvalue()
                matched_name = "Unmatched"
                
                # Match attempt with Retry
                match_resp = call_gemini_with_retry([
                    f"Match this image to an item from: {structured_menu}. Return ONLY the 'item' name.",
                    {"mime_type": "image/jpeg", "data": file_bytes}
                ])
                
                if match_resp and match_resp.text:
                    matched_name = match_resp.text.strip()
                
                # Sanitize & Save EVERY file
                clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                count = name_tracker.get(clean_name, 0)
                name_tracker[clean_name] = count + 1
                suffix = f"_{count}" if count > 0 else ""
                
                with open(os.path.join(temp_dir, f"{clean_name}{suffix}.jpg"), "wb") as f:
                    f.write(file_bytes)
            
            progress_bar.progress(min(100, int((i + 5) / total_files * 100)))

        # C. ZIP & DOWNLOAD
        zip_name = f"{brand_name}_Photos.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in os.listdir(temp_dir):
                z.write(os.path.join(temp_dir, f), f)
        
        st.success(f"Processed {total_files} images.")
        with open(zip_name, "rb") as f:
            st.download_button("💾 Download ZIP", data=f, file_name=zip_name)
        shutil.rmtree(temp_dir)
