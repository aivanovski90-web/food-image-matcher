import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil
from playwright.sync_api import sync_playwright

# --- 1. CLOUD INSTALLATION FIX ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

# --- 2. CONFIGURATION ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Add it to Streamlit Settings > Secrets.")
    st.stop()

model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. APP UI ---
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

        # --- 4. SCRAPING PHASE (STUCK FIX) ---
        status_text.text("Connecting to restaurant website...")
        menu_text = ""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True, 
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
                )
                page = browser.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                menu_text = page.inner_text("body")
                browser.close()
        except Exception as e:
            st.error(f"Scraping failed: {e}")
            st.stop()

        # --- 5. VISION & PROCESSING ---
        brand_match = re.search(r'https?://(?:www\.)?([^./]+)', url)
        brand_name = brand_match.group(1).capitalize() if brand_match else "Restaurant"
        
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        valid_count = 0
        name_tracker = {}
        batch_size = 5 
        total_files = len(uploaded_files)
        
        for i in range(0, total_files, batch_size):
            batch = uploaded_files[i : i + batch_size]
            for file in batch:
                file_bytes = file.getvalue()
                try:
                    response = model.generate_content([
                        f"Identify this dish from the menu: {menu_text}. Return ONLY the name.",
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ])
                    
                    matched_name = response.text.strip()
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                    
                    count = name_tracker.get(clean_name, 0)
                    name_tracker[clean_name] = count + 1
                    suffix = f"_{count}" if count > 0 else ""
                    
                    dest_path = os.path.join(temp_dir, f"{clean_name}{suffix}.jpg")
                    with open(dest_path, "wb") as f:
                        f.write(file_bytes)
                    valid_count += 1
                except: continue
            
            # MATH FIX: Added min(100, ...) to prevent out-of-range error
            progress_bar.progress(min(100, int((i + batch_size) / total_files * 100)))

        # --- 6. ZIP & DOWNLOAD ---
        if valid_count > 0:
            zip_name = f"{brand_name}_Photos.zip"
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
                for f in os.listdir(temp_dir):
                    z.write(os.path.join(temp_dir, f), f)
            
            st.success(f"Processed {valid_count} images!")
            with open(zip_name, "rb") as f:
                st.download_button("💾 Download ZIP", data=f, file_name=zip_name)
            shutil.rmtree(temp_dir)
