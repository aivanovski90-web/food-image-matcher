import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil, json, time
from playwright.sync_api import sync_playwright

# --- 1. SESSION STATE FOR PERSISTENCE ---
# This ensures data lives across reruns
if "zip_buffer" not in st.session_state:
    st.session_state.zip_buffer = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = ""
if "preview_list" not in st.session_state:
    st.session_state.preview_list = []

# --- 2. INSTALLATION & SETUP ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Add it to Streamlit Secrets.")
    st.stop()

model = genai.GenerativeModel('gemini-3-flash-preview')

# --- 3. UI SETUP ---
st.set_page_config(page_title="Menu Matcher Pro", page_icon="📸")
st.title("📸 Advanced Menu Matcher")

with st.sidebar:
    st.header("1. Upload & Settings")
    uploaded_files = st.file_uploader("Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant URL")
    
    st.markdown("---")
    st.header("2. Live Preview")
    # This container updates live during the loop
    preview_container = st.empty()
    if st.session_state.preview_list:
        preview_container.info("\n".join(st.session_state.preview_list))

# --- 4. CORE LOGIC ---
if st.button("Start Processing Batch"):
    if not uploaded_files or not url:
        st.warning("Provide both images and a URL.")
    else:
        # Reset previous session data
        st.session_state.preview_list = []
        status_text = st.empty()
        
        # A. SCRAPING
        status_text.text("Connecting to restaurant...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            status_text.text("AI is parsing menu structure...")
            extract_prompt = f"Extract all dish items. Return ONLY JSON list: ['Dish 1']. HTML: {raw_html[:20000]}"
            extraction = model.generate_content(extract_prompt)
            structured_menu = json.loads(extraction.text.replace('```json', '').replace('```', '').strip())
        except Exception as e:
            st.error(f"Failed during extraction: {e}")
            st.stop()

        # B. VISION & AUTO-NUMBERING
        brand_name = url.split("//")[-1].split(".")[0].capitalize()
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        name_tracker = {} # Track duplicates for numbering
        total = len(uploaded_files)
        prog = st.progress(0)
        
        for i in range(0, total, 5):
            batch = uploaded_files[i : i+5]
            for file in batch:
                file_bytes = file.getvalue()
                try:
                    resp = model.generate_content([
                        f"Match this photo to an item: {structured_menu}. Return ONLY the name.",
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ])
                    
                    raw_name = resp.text.strip() if resp.text else "Unmatched"
                    clean_name = re.sub(r'\W+', '_', raw_name).strip("_")
                    
                    # DUPLICATE HANDLING: Add numbering suffix
                    count = name_tracker.get(clean_name, 0)
                    name_tracker[clean_name] = count + 1
                    # Only add suffix if it's the 2nd image or more
                    final_filename = f"{clean_name}_{count}.jpg" if count > 0 else f"{clean_name}.jpg"
                    
                    # Save to disk
                    with open(os.path.join(temp_dir, final_filename), "wb") as f:
                        f.write(file_bytes)
                    
                    # Update Live Preview in Sidebar
                    st.session_state.preview_list.append(f"✅ {final_filename}")
                    preview_container.info("\n".join(st.session_state.preview_list[-15:])) # Show last 15
                except: continue
            prog.progress(min(100, int((i + 5) / total * 100)))

        # C. ZIP & STORE
        zip_name = f"{brand_name}_Photos.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in os.listdir(temp_dir):
                z.write(os.path.join(temp_dir, f), f)
        
        # PERSIST RESULTS
        with open(zip_name, "rb") as f:
            st.session_state.zip_buffer = f.read()
        st.session_state.zip_filename = zip_name
        
        shutil.rmtree(temp_dir)
        os.remove(zip_name)
        st.rerun() # Refresh to show final download button

# --- 5. PERSISTENT DOWNLOAD ---
if st.session_state.zip_buffer:
    st.success(f"Successfully processed images!")
    st.download_button(
        label="💾 Download ZIP archive",
        data=st.session_state.zip_buffer,
        file_name=st.session_state.zip_filename,
        mime="application/zip",
        on_click="ignore" # Keeps the screen state after download
    )
