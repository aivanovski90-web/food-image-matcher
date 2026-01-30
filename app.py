import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json, time
from playwright.sync_api import sync_playwright

# --- 1. SESSION STATE INITIALIZATION ---
# This keeps your results visible even after the app reruns
if "zip_buffer" not in st.session_state:
    st.session_state.zip_buffer = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = ""
if "processed_msg" not in st.session_state:
    st.session_state.processed_msg = ""

# --- 2. CLOUD INSTALLATION ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

# --- 3. CONFIGURATION ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Add it to Streamlit Secrets.")
    st.stop()

model = genai.GenerativeModel('gemini-3-flash-preview')

# --- 4. UI SETUP ---
st.set_page_config(page_title="Menu Matcher Pro", page_icon="📸")
st.title("📸 Restaurant Menu Photo Matcher")

with st.sidebar:
    st.header("Upload Settings")
    uploaded_files = st.file_uploader("Upload Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant Website URL")
    
    # Add a reset button to clear session state if needed
    if st.button("Clear Results"):
        st.session_state.zip_buffer = None
        st.rerun()

# --- 5. PROCESSING LOGIC ---
if st.button("Start Processing Batch"):
    if not uploaded_files or not url:
        st.warning("Please provide a URL and images.")
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

            status_text.text("Extracting menu items...")
            extract_prompt = f"Identify all menu items. Return ONLY a JSON list: ['Dish 1']. HTML: {raw_html[:20000]}"
            extraction = model.generate_content(extract_prompt)
            structured_menu = json.loads(extraction.text.replace('```json', '').replace('```', '').strip())
        except Exception as e:
            st.error(f"Failed: {e}")
            st.stop()

        # B. VISION & MATCHING
        brand_name = url.split("//")[-1].split(".")[0].capitalize()
        temp_dir = f"./{brand_name}_output"
        os.makedirs(temp_dir, exist_ok=True)
        
        total = len(uploaded_files)
        prog = st.progress(0)
        
        for i in range(0, total, 5):
            batch = uploaded_files[i : i+5]
            for file in batch:
                file_bytes = file.getvalue()
                try:
                    resp = model.generate_content([
                        f"Match to this menu: {structured_menu}. Return ONLY dish name.",
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ])
                    name = re.sub(r'\W+', '_', resp.text).strip("_") if resp.text else "Unmatched"
                    with open(os.path.join(temp_dir, f"{name}_{i}.jpg"), "wb") as f:
                        f.write(file_bytes)
                except: continue
            prog.progress(min(100, int((i + 5) / total * 100)))

        # C. SAVING TO SESSION STATE
        zip_name = f"{brand_name}_Photos.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in os.listdir(temp_dir):
                z.write(os.path.join(temp_dir, f), f)
        
        # READ ZIP INTO MEMORY AND STORE
        with open(zip_name, "rb") as f:
            st.session_state.zip_buffer = f.read()
        
        st.session_state.zip_filename = zip_name
        st.session_state.processed_msg = f"Successfully matched {total} images!"
        shutil.rmtree(temp_dir)
        os.remove(zip_name)
        st.rerun() # Refresh to show the persistent download button

# --- 6. PERSISTENT DOWNLOAD SECTION ---
# This part stays on screen even if the app reruns
if st.session_state.zip_buffer is not None:
    st.success(st.session_state.processed_msg)
    st.download_button(
        label="💾 Download ZIP archive",
        data=st.session_state.zip_buffer,
        file_name=st.session_state.zip_filename,
        mime="application/zip",
        on_click="ignore" # PREVENTS RERUN UPON CLICK
    )
