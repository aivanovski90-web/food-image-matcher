import streamlit as st
import google.generativeai as genai
import os, re, zipfile, shutil
from playwright.sync_api import sync_playwright

# --- CONFIGURATION & SECURITY ---
# This pulls your key from Streamlit's "Secrets" panel instead of hardcoding it
try:
    API_KEY = st.secrets["AIzaSyDVU6VlLM---rbWvRIX66xaVehKzcLXJNY"]
    genai.configure(api_key=AIzaSyDVU6VlLM---rbWvRIX66xaVehKzcLXJNY)
except KeyError:
    st.error("Missing GEMINI_API_KEY. Please add it to Streamlit Secrets.")
    st.stop()

model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Menu Photo Packager", page_icon="📸")
st.title("📸 Restaurant Menu Photo Packager")
st.write("Upload your photos and provide a menu URL to automatically rename and zip them.")

# --- INPUT PHASE ---
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

        # 1. SCRAPING PHASE (Playwright Engine)
        status_text.text("Connecting to restaurant website...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                menu_text = page.inner_text("body")
                browser.close()
        except Exception as e:
            st.error(f"Scraping failed: {e}")
            st.stop()

        # 2. ANALYSIS & PROCESSING PHASE
        # Extract Brand Name from URL
        brand_match = re.search(r'https?://(?:www\.)?([^./]+)', url)
        brand_name = brand_match.group(1).capitalize() if brand_match else "Restaurant"
        
        temp_dir = f"./{brand_name}_output"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        valid_count = 0
        name_tracker = {}

        # Memory Fix: Process in batches of 5 to avoid RAM crashes
        batch_size = 5
        total_files = len(uploaded_files)
        
        for i in range(0, total_files, batch_size):
            batch = uploaded_files[i : i + batch_size]
            
            for file in batch:
                file_bytes = file.getvalue()
                
                # Match Image via Gemini Vision (Classifier Mode)
                # This explicitly prevents image generation
                try:
                    response = model.generate_content([
                        f"Identify this food item from the following menu list: {menu_text}. Return ONLY the name of the dish. No description.",
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ])
                    
                    # Sanitize filename
                    matched_name = response.text.strip()
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                    
                    # Deduplication
                    count = name_tracker.get(clean_name, 0)
                    name_tracker[clean_name] = count + 1
                    suffix = f"_{count}" if count > 0 else ""
                    
                    # 1KB Fix: Binary Write directly to disk
                    dest_path = os.path.join(temp_dir, f"{clean_name}{suffix}.jpg")
                    with open(dest_path, "wb") as f:
                        f.write(file_bytes)
                    
                    if os.path.getsize(dest_path) > 2000:
                        valid_count += 1
                except:
                    continue
            
            # Update Progress
            percent_complete = min(100, int((i + batch_size) / total_files * 100))
            progress_bar.progress(percent_complete)
            status_text.text(f"Processed {min(i + batch_size, total_files)} of {total_files} images...")

        # 3. ZIPPING PHASE
        if valid_count > 0:
            status_text.text("Packaging ZIP archive...")
            zip_path = f"{brand_name}_Photos.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
                for f in os.listdir(temp_dir):
                    z.write(os.path.join(temp_dir, f), f)
            
            # 4. OUTPUT PHASE (Direct Download Button)
            status_text.success(f"Processing Complete! Successfully matched {valid_count} images.")
            with open(zip_path, "rb") as f:
                st.download_button(
                    label="💾 Download Finished Zip",
                    data=f,
                    file_name=zip_path,
                    mime="application/zip",
                    use_container_width=True
                )
            
            # Cleanup
            shutil.rmtree(temp_dir)
        else:
            st.error("No images could be processed. Check the menu URL or image quality.")
