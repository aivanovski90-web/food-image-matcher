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

# Use Gemini 3 Flash for speed and large context processing
model = genai.GenerativeModel('gemini-3-flash-preview')

# --- 3. UI SETUP ---
st.set_page_config(page_title="Advanced Menu Matcher", page_icon="📸")
st.title("📸 Advanced Restaurant Menu Matcher")
st.markdown("Improving matching by extracting dish descriptions and using expert personas.")

with st.sidebar:
    st.header("Settings")
    uploaded_files = st.file_uploader("Upload Images (Max 500)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    url = st.text_input("Restaurant Website URL")

if st.button("Start High-Accuracy Match"):
    if not uploaded_files or not url:
        st.warning("Please provide a URL and upload images.")
    else:
        status_text = st.empty()
        
        # --- 4. DATA EXTRACTION (ENHANCED) ---
        status_text.text("Extracting menu with descriptions...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(3000) 
                raw_html = page.inner_html("body")
                browser.close()

            # PTCF Framework: Define Persona and Task clearly
            extract_prompt = f"""
            <PERSONA> You are a meticulous data extractor specializing in restaurant menus. </PERSONA>
            <TASK> Extract every dish name AND its description/ingredients from this HTML. </TASK>
            <FORMAT> Return ONLY a JSON list of objects: [{{"item": "Name", "info": "Description"}}] </FORMAT>
            <CONTEXT> HTML: {raw_html[:25000]} </CONTEXT>
            """
            extraction = model.generate_content(extract_prompt)
            clean_json = extraction.text.replace('```json', '').replace('```', '').strip()
            structured_menu = json.loads(clean_json)
        except Exception as e:
            st.error(f"Extraction failed: {e}")
            st.stop()

        # --- 5. VISION & MATCHING (EXPERT MODE) ---
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
                
                try:
                    # Advanced Prompting: Explicitly reference modality and use anchoring
                    match_resp = model.generate_content([
                        f"""
                        <PERSONA> You are an expert culinary judge. </PERSONA>
                        <TASK> Based on the image provided, identify which item from the menu below is most likely shown. </TASK>
                        <RULES>
                        1. Look for visual matches in the 'item' names AND 'info' ingredients.
                        2. If a dish is described as having 'green sauce' and the photo has green sauce, prioritize that.
                        3. Only return 'Unmatched' if there is NO possible connection.
                        4. Return ONLY the 'item' name.
                        </RULES>
                        <MENU_CONTEXT> {structured_menu} </MENU_CONTEXT>
                        """,
                        {"mime_type": "image/jpeg", "data": file_bytes}
                    ], generation_config={"temperature": 0.2}) # Lower temperature for precision
                    
                    if match_resp and match_resp.text:
                        matched_name = match_resp.text.strip()
                except: pass
                
                # Sanitize & Save
                clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
                count = name_tracker.get(clean_name, 0)
                name_tracker[clean_name] = count + 1
                suffix = f"_{count}" if count > 0 else ""
                
                dest_path = os.path.join(temp_dir, f"{clean_name}{suffix}.jpg")
                with open(dest_path, "wb") as f:
                    f.write(file_bytes)
            
            progress_bar.progress(min(100, int((i + 5) / total_files * 100)))

        # --- 6. ZIP & DOWNLOAD ---
        zip_name = f"{brand_name}_Photos.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in os.listdir(temp_dir):
                z.write(os.path.join(temp_dir, f), f)
        
        st.success(f"Processed {total_files} images.")
        with open(zip_name, "rb") as f:
            st.download_button("💾 Download Results", data=f, file_name=zip_name)
        shutil.rmtree(temp_dir)
