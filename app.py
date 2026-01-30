import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json, time
from playwright.sync_api import sync_playwright
from google.api_core.exceptions import ResourceExhausted

# --- 1. CLOUD INSTALLATION ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

# --- 2. CONFIGURATION & STATE ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY in Streamlit Secrets.")
    st.stop()

# Initialize Session State trackers for the monitor
if "requests_used" not in st.session_state:
    st.session_state.requests_used = 0
if "quota_limit" not in st.session_state:
    st.session_state.quota_limit = 1000 # Default for Flash-Lite

MODEL_NAME = 'gemini-2.5-flash-lite'
model = genai.GenerativeModel(MODEL_NAME)

# --- 3. HELPER: RETRY & MONITOR ---
def call_gemini_with_retry(prompt_data, max_retries=3):
    """Tracks usage and handles 429 errors with backoff."""
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt_data, generation_config={"temperature": 0.2})
            # Increment successful request count
            st.session_state.requests_used += 1 
            return response
        except ResourceExhausted:
            wait_seconds = 35 
            st.warning(f"Quota reached. Sleeping {wait_seconds}s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(wait_seconds)
        except Exception as e:
            st.error(f"AI Error: {e}")
            return None
    return None

# --- 4. UI SETUP ---
st.set_page_config(page_title="Quota Monitor Pro", page_icon="📸")
st.title("📸 Menu Matcher with Quota Monitor")

# Display the Monitor in the Sidebar
with st.sidebar:
    st.header("📊 Quota Monitor")
    remaining = max(0, st.session_state.quota_limit - st.session_state.requests_used)
    
    # Visual Progress Bar for daily quota
    progress_val = min(1.0, st.session_state.requests_used / st.session_state.quota_limit)
    st.progress(progress_val)
    
    col1, col2 = st.columns(2)
    col1.metric("Used", st.session_state.requests_used)
    col2.metric("Remaining", remaining)
    st.caption("RPD resets at midnight Pacific Time")
    
    st.markdown("---")
    st.header("Settings")
    uploaded_files = st.file_uploader("Upload Images (Max 500)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant Website URL")

# --- 5. MAIN LOGIC ---
if st.button("Start Processing"):
    if not uploaded_files or not url:
        st.warning("Please provide a URL and upload images.")
    else:
        status_text = st.empty()
        
        # A. SCRAPING
        status_text.text("Connecting to website...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            status_text.text("Parsing menu structure...")
            extract_prompt = f"Extract dish items. Return ONLY JSON list: ['Dish 1', 'Dish 2']. HTML: {raw_html[:20000]}"
            extraction = call_gemini_with_retry(extract_prompt)
            if not extraction: st.stop()
            
            clean_json = extraction.text.replace('```json', '').replace('```', '').strip()
            structured_menu = json.loads(clean_json)
        except Exception as e:
            st.error(f"Scraping failed: {e}")
            st.stop()

        # B. VISION & MATCHING
        brand_name = url.split("//")[-1].split(".")[0].capitalize() if url else "Restaurant"
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        main_progress = st.progress(0)
        total_files = len(uploaded_files)

        for i in range(0, total_files, 5):
            batch = uploaded_files[i : i + 5]
            for file in batch:
                file_bytes = file.getvalue()
                matched_name = "Unmatched"
                
                match_resp = call_gemini_with_retry([
                    f"Match this to an item from: {structured_menu}. Return ONLY the name.",
                    {"mime_type": "image/jpeg", "data": file_bytes}
                ])
                
                if match_resp and match_resp.text:
                    matched_name = match_resp.text.strip()
                
                # Sanitize & Save
                clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                dest_path = os.path.join(temp_dir, f"{clean_name}_{i}.jpg")
                with open(dest_path, "wb") as f:
                    f.write(file_bytes)
            
            main_progress.progress(min(100, int((i + 5) / total_files * 100)))

        # C. ZIP & CLEANUP
        zip_name = f"{brand_name}_Photos.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in os.listdir(temp_dir):
                z.write(os.path.join(temp_dir, f), f)
        
        st.success(f"Processed {total_files} images.")
        with open(zip_name, "rb") as f:
            st.download_button("💾 Download ZIP", data=f, file_name=zip_name)
        shutil.rmtree(temp_dir)
        st.rerun() # Refresh UI to update the Quota Monitor counts
