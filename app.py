import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json, time
from playwright.sync_api import sync_playwright
from google.api_core.exceptions import ResourceExhausted

# --- 1. PERSISTENCE ---
if "zip_buffer" not in st.session_state:
    st.session_state.zip_buffer = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = ""
if "preview_list" not in st.session_state:
    st.session_state.preview_list = []

# --- 2. SETUP ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Add it to Streamlit Secrets.")
    st.stop()

# HYBRID MODELS: High quota for text, high intelligence for vision
text_model = genai.GenerativeModel('gemini-2.5-flash-lite') 
vision_model = genai.GenerativeModel('gemini-3-flash-preview')

# --- 3. HELPER: QUOTA-AWARE CALLS ---
def safe_gemini_call(target_model, prompt_data, retries=3):
    """Handles 429 errors and directs calls to the chosen model."""
    for i in range(retries):
        try:
            return target_model.generate_content(prompt_data, generation_config={"temperature": 0.1})
        except ResourceExhausted:
            st.warning(f"Quota reached. Pausing for 55 seconds... (Attempt {i+1})")
            time.sleep(55)
        except Exception as e:
            st.error(f"AI Error: {e}")
            return None
    return None

# --- 4. UI ---
st.set_page_config(page_title="Hybrid Precision Matcher", page_icon="📸")
st.title("📸 Hybrid Precision Menu Matcher")
st.info("Using Hybrid Logic: Smart Vision for matches, High-Quota for extraction.")

with st.sidebar:
    st.header("1. Settings")
    uploaded_files = st.file_uploader("Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant URL")
    st.markdown("---")
    st.header("2. Live Preview")
    preview_container = st.empty()
    if st.session_state.preview_list:
        preview_container.info("\n".join(st.session_state.preview_list))

# --- 5. LOGIC ---
if st.button("Start Processing Batch"):
    if not uploaded_files or not url:
        st.warning("Provide both images and a URL.")
    else:
        st.session_state.preview_list = []
        status_text = st.empty()
        
        # A. SCRAPING
        status_text.text("Extracting menu data with descriptions...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            extract_prompt = f"Extract dish items and descriptions. Return ONLY JSON list: [{{'name': 'Dish', 'info': 'Desc'}}] HTML: {raw_html[:20000]}"
            extraction = safe_gemini_call(text_model, extract_prompt)
            if not extraction: st.stop()
            
            structured_menu = json.loads(extraction.text.replace('```json', '').replace('```', '').strip())
        except Exception as e:
            st.error(f"Extraction failed: {e}")
            st.stop()

        # B. DIRECTORY SETUP (OSError Fix)
        brand_match = re.search(r'https?://(?:www\.)?([^./]+)', url)
        brand_name = brand_match.group(1).capitalize() if brand_match else "Restaurant"
        
        # Use absolute path to ensure Streamlit Cloud finds it
        temp_dir = os.path.abspath(f"./{brand_name}_output")
        if os.path.exists(temp_dir): 
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        name_tracker = {} 
        total = len(uploaded_files)
        prog = st.progress(0)
        
        # C. VISION MATCHING
        for idx, file in enumerate(uploaded_files):
            file_bytes = file.getvalue()
            matched_name = "Unmatched"
            
            match_resp = safe_gemini_call(vision_model, [
                f"Analyze image. Match to: {structured_menu}. Return ONLY the exact 'name'.",
                {"mime_type": "image/jpeg", "data": file_bytes}
            ])
            
            if match_resp and match_resp.text:
                matched_name = match_resp.text.strip()
            
            # FILENAME FIX: Remove all non-alphanumeric to prevent OSErrors
            clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
            count = name_tracker.get(clean_name, 0)
            name_tracker[clean_name] = count + 1
            final_filename = f"{clean_name}_{count}.jpg"
            
            # WRITING DATA (Full Return Fix)
            file_path = os.path.join(temp_dir, final_filename)
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            
            st.session_state.preview_list.append(f"✅ {final_filename}")
            preview_container.info("\n".join(st.session_state.preview_list[-15:]))
            prog.progress(int((idx + 1) / total * 100))

        # D. PACKAGING
        zip_name = f"{brand_name}_Photos.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in os.listdir(temp_dir):
                z.write(os.path.join(temp_dir, f), f)
        
        with open(zip_name, "rb") as f:
            st.session_state.zip_buffer = f.read()
        st.session_state.zip_filename = zip_name
        
        shutil.rmtree(temp_dir)
        os.remove(zip_name)
        st.rerun()

# --- 6. PERSISTENT DOWNLOAD ---
if st.session_state.zip_buffer:
    st.success(f"Success! Processed {len(st.session_state.preview_list)} images.")
    st.download_button(
        label="💾 Download ZIP archive",
        data=st.session_state.zip_buffer,
        file_name=st.session_state.zip_filename,
        mime="application/zip",
        on_click="ignore" 
    )
