import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json, time
from playwright.sync_api import sync_playwright

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

# Using Gemini 3 Flash for the largest context window and best reasoning
model = genai.GenerativeModel('gemini-3-flash-preview')

# --- 3. UI ---
st.set_page_config(page_title="High-Accuracy Matcher", page_icon="📸")
st.title("📸 High-Accuracy Menu Matcher")

with st.sidebar:
    st.header("1. Upload & Settings")
    uploaded_files = st.file_uploader("Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant URL")
    
    st.markdown("---")
    st.header("2. Live Preview")
    preview_container = st.empty()
    if st.session_state.preview_list:
        preview_container.info("\n".join(st.session_state.preview_list))

# --- 4. LOGIC ---
if st.button("Start High-Accuracy Match"):
    if not uploaded_files or not url:
        st.warning("Provide both images and a URL.")
    else:
        st.session_state.preview_list = []
        status_text = st.empty()
        
        # A. SCRAPING (Enhanced with Descriptions)
        status_text.text("Extracting menu titles & ingredients...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            # PTCF Framework: Persona-Task-Context-Format
            extract_prompt = f"""
            Identify all menu items in this HTML. Include the name and its short description or ingredients.
            Return ONLY a valid JSON list: [{{"name": "Dish", "info": "Description"}}]
            HTML: {raw_html[:25000]}
            """
            extraction = model.generate_content(extract_prompt)
            clean_json = extraction.text.replace('```json', '').replace('```', '').strip()
            structured_menu = json.loads(clean_json)
        except Exception as e:
            st.error(f"Failed during extraction: {e}")
            st.stop()

        # B. VISION MATCHING (Expert Mode)
        brand_name = url.split("//")[-1].split(".")[0].capitalize()
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        name_tracker = {} 
        total = len(uploaded_files)
        prog = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            file_bytes = file.getvalue()
            matched_name = "Unmatched"
            
            try:
                # Expert Persona + Low Temperature (0.2) for precise matching
                match_resp = model.generate_content([
                    f"""
                    You are a culinary expert. Match this image to the most likely item from this list: {structured_menu}.
                    Consider the visual ingredients and compare them to the 'name' and 'info' descriptions.
                    If unsure, return 'Unmatched'. Return ONLY the dish name string.
                    """,
                    {"mime_type": "image/jpeg", "data": file_bytes}
                ], generation_config={"temperature": 0.2})
                
                if match_resp and match_resp.text:
                    matched_name = match_resp.text.strip()
            except: 
                pass # Falls back to "Unmatched"
            
            # Sanitize and Numbering
            clean_name = re.sub(r'\W+', '_', matched_name).strip("_")
            count = name_tracker.get(clean_name, 0)
            name_tracker[clean_name] = count + 1
            final_filename = f"{clean_name}_{count}.jpg"
            
            with open(os.path.join(temp_dir, final_filename), "wb") as f:
                f.write(file_bytes)
            
            st.session_state.preview_list.append(f"✅ {final_filename}")
            preview_container.info("\n".join(st.session_state.preview_list[-15:]))
            prog.progress(int((idx + 1) / total * 100))

        # C. PACKAGING
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

# --- 5. PERSISTENT DOWNLOAD ---
if st.session_state.zip_buffer:
    st.success(f"Success! All {len(st.session_state.preview_list)} images processed.")
    st.download_button(
        label="💾 Download ZIP archive",
        data=st.session_state.zip_buffer,
        file_name=st.session_state.zip_filename,
        mime="application/zip",
        on_click="ignore" 
    )
