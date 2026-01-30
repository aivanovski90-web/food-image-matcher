import streamlit as st
import os, re, zipfile, shutil, json, time, base64
from openai import OpenAI
from playwright.sync_api import sync_playwright

# --- 1. SESSION STATE & AUTH ---
if "zip_buffer" not in st.session_state: st.session_state.zip_buffer = None
if "preview_list" not in st.session_state: st.session_state.preview_list = []

try:
    client = OpenAI(
        api_key=st.secrets["GROK_API_KEY"],
        base_url="https://api.x.ai/v1" # Compatible with OpenAI SDK
    )
except:
    st.error("Add GROK_API_KEY to Streamlit Secrets.")
    st.stop()

# Grok 4.1 Fast is the best intelligence-to-cost ratio in 2026
MODEL_NAME = "grok-4.1-fast"

# --- 2. BATCH HANDLER ---
def process_grok_batch(chunk_files, menu_items):
    """Processes images in groups of 10 to maximize token efficiency."""
    messages = [
        {"role": "system", "content": f"Match these {len(chunk_files)} images to items in: {menu_items}. Return ONLY a JSON list of names in exact order."},
    ]
    
    user_content = []
    for f in chunk_files:
        # Encode image to Base64 for the API
        b64_img = base64.b64encode(f.getvalue()).decode("utf-8")
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}})
    
    messages.append({"role": "user", "content": user_content})
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            response_format={"type": "json_object"} # Force structured data
        )
        return json.loads(response.choices[0].message.content).get("names", [])
    except:
        return ["Unmatched"] * len(chunk_files)

# --- 3. MAIN UI & LOGIC ---
st.title("🚀 Grok-Powered Menu Matcher")
with st.sidebar:
    uploaded_files = st.file_uploader("Upload Batch (Up to 500)", accept_multiple_files=True)
    url = st.text_input("Restaurant Website URL")
    preview = st.empty()

if st.button("Start Fast Batch Processing"):
    if uploaded_files and url:
        # A. SCRAPE
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            menu_html = page.inner_html("body")
            browser.close()

        # B. EXTRACT MENU
        extract = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": f"Extract all dish names from this HTML. Return JSON list ['Name']. HTML: {menu_html[:25000]}"}]
        )
        menu_items = json.loads(extract.choices[0].message.content)

        # C. BATCH IMAGE PROCESSING
        brand_name = url.split("//")[-1].split(".")[0].capitalize()
        temp_dir = os.path.abspath(f"./{brand_name}")
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        name_tracker = {}
        batch_size = 10 # Grok handles up to 10 images smoothly
        
        for i in range(0, len(uploaded_files), batch_size):
            chunk = uploaded_files[i : i + batch_size]
            matches = process_grok_batch(chunk, menu_items)
            
            for idx, file in enumerate(chunk):
                name = matches[idx] if idx < len(matches) else "Unmatched"
                clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name).strip("_")
                
                # Handling Duplicates
                count = name_tracker.get(clean_name, 0)
                name_tracker[clean_name] = count + 1
                fname = f"{clean_name}_{count}.jpg"
                
                with open(os.path.join(temp_dir, fname), "wb") as f:
                    f.write(file.getvalue())
                
                st.session_state.preview_list.append(f"✅ {fname}")
                preview.info("\n".join(st.session_state.preview_list[-10:]))
            
            st.progress((i + len(chunk)) / len(uploaded_files))
            time.sleep(0.5) # Short rest for stability

        # D. ZIP & DOWNLOAD
        zip_fn = f"{brand_name}_Results.zip"
        with zipfile.ZipFile(zip_fn, 'w') as z:
            for f in os.listdir(temp_dir): z.write(os.path.join(temp_dir, f), f)
        
        with open(zip_fn, "rb") as f: st.session_state.zip_buffer = f.read()
        shutil.rmtree(temp_dir)
        st.rerun()

if st.session_state.zip_buffer:
    st.download_button("💾 Download Results", st.session_state.zip_buffer, "Photos.zip")
