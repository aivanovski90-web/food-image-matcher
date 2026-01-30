import streamlit as st
import os, re, zipfile, shutil, json, time, base64
from openai import OpenAI
from playwright.sync_api import sync_playwright

# --- 1. SETUP & AUTH ---
st.set_page_config(page_title="Grok Menu Matcher", page_icon="🚀")

if "zip_buffer" not in st.session_state: st.session_state.zip_buffer = None
if "preview_list" not in st.session_state: st.session_state.preview_list = []

try:
    # Uses the GROK_API_KEY from your Streamlit Secrets
    client = OpenAI(
        api_key=st.secrets["GROK_API_KEY"],
        base_url="https://api.x.ai/v1" 
    )
except Exception as e:
    st.error("Please add 'GROK_API_KEY' to your Streamlit Secrets.")
    st.stop()

# Using Grok 4.1 Fast for high-speed, low-cost processing
MODEL_NAME = "grok-4.1-fast"

# --- 2. BATCH HANDLER ---
def process_grok_batch(chunk_files, menu_items):
    """Groups images into one request to save API quota."""
    user_content = [{"type": "text", "text": f"Identify these {len(chunk_files)} images from this menu: {menu_items}. Return ONLY a JSON object: {{\"names\": [\"Name1\", \"Name2\"]}} in exact order."}]
    
    for f in chunk_files:
        b64_img = base64.b64encode(f.getvalue()).decode("utf-8")
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}})
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": user_content}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content).get("names", [])
    except:
        return ["Unmatched"] * len(chunk_files)

# --- 3. UI & LOGIC ---
st.title("🚀 Grok-Powered Menu Matcher")
with st.sidebar:
    st.header("1. Settings")
    uploaded_files = st.file_uploader("Upload Batch (Up to 500)", accept_multiple_files=True, type=['jpg', 'jpeg', 'png'])
    url = st.text_input("Restaurant Website URL")
    st.markdown("---")
    st.header("2. Live Preview")
    preview = st.empty()
    if st.session_state.preview_list:
        preview.info("\n".join(st.session_state.preview_list))

if st.button("Start Fast Batch Processing"):
    if not uploaded_files or not url:
        st.warning("Please provide both a URL and images.")
    else:
        # A. SCRAPE
        st.info("Scraping menu data...")
        with sync_playwright() as p:
            # Install browser on first run
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url)
            menu_html = page.inner_html("body")
            browser.close()

        # B. EXTRACT DISHES
        extract = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": f"Extract all dish names from this HTML. Return ONLY a JSON list of strings. HTML: {menu_html[:25000]}"}]
        )
        menu_items = json.loads(extract.choices[0].message.content)

        # C. BATCH PROCESSING
        brand_name = url.split("//")[-1].split(".")[0].capitalize()
        temp_dir = os.path.abspath(f"./{brand_name}")
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        name_tracker = {}
        batch_size = 10 # Efficiency: 10 images per request
        
        for i in range(0, len(uploaded_files), batch_size):
            chunk = uploaded_files[i : i + batch_size]
            matches = process_grok_batch(chunk, menu_items)
            
            for idx, file in enumerate(chunk):
                name = matches[idx] if idx < len(matches) else "Unmatched"
                clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name).strip("_")
                
                # Handling Duplicates
                count = name_tracker.get(clean_name, 0)
                name_tracker[clean_name] = count + 1
                final_filename = f"{clean_name}_{count}.jpg"
                
                with open(os.path.join(temp_dir, final_filename), "wb") as f:
                    f.write(file.getvalue())
                
                st.session_state.preview_list.append(f"✅ {final_filename}")
                preview.info("\n".join(st.session_state.preview_list[-10:]))
            
            st.progress((i + len(chunk)) / len(uploaded_files))
            time.sleep(1) # Safety delay

        # D. ZIP & FINISH
        zip_fn = f"{brand_name}_Results.zip"
        with zipfile.ZipFile(zip_fn, 'w') as z:
            for f in os.listdir(temp_dir): z.write(os.path.join(temp_dir, f), f)
        
        with open(zip_fn, "rb") as f: st.session_state.zip_buffer = f.read()
        shutil.rmtree(temp_dir)
        st.rerun()

if st.session_state.zip_buffer:
    st.download_button("💾 Download Results", st.session_state.zip_buffer, "Photos.zip")
