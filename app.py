import streamlit as st
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from PIL import Image
import io
import zipfile

# --- PAGE SETUP ---
st.set_page_config(page_title="AI Food Matcher", layout="wide")
st.title("🤖 AI Restaurant Matcher")

# --- SECRETS & AI CONFIG ---
# We will set the API_KEY in Streamlit's dashboard later
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    st.error("Please add your GEMINI_API_KEY to Streamlit Secrets.")

# --- SIDEBAR: WEBSITE SCRAPER ---
st.sidebar.header("1. Get Menu from Website")
url = st.sidebar.text_input("Paste Restaurant URL:")
menu_items = []

if url:
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Scrapes headers and bold text which usually contain dish names
        found_text = soup.find_all(['h2', 'h3', 'strong', 'b'])
        menu_items = sorted(list(set([t.get_text().strip() for t in found_text if len(t.get_text().strip()) > 3])))
        st.sidebar.success(f"Found {len(menu_items)} items!")
    except:
        st.sidebar.error("Could not read menu. Check the URL.")

# --- MAIN: IMAGE UPLOAD ---
st.header("2. Upload & Auto-Match")
uploaded_files = st.file_uploader("Drop images here", accept_multiple_files=True, type=['jpg', 'png', 'jpeg'])

if uploaded_files and menu_items:
    if st.button("🚀 Start AI Matching"):
        results = {}
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            # The AI Logic
            img = Image.open(file)
            prompt = f"Identify this food. Pick the closest match from this list: {menu_items}. Return ONLY the name."
            
            try:
                response = model.generate_content([prompt, img])
                match_name = response.text.strip()
                results[file.name] = {"match": match_name, "bytes": file.getvalue()}
                st.write(f"✅ {file.name} matched to **{match_name}**")
            except:
                st.write(f"❌ Error matching {file.name}")
            
            progress_bar.progress((i + 1) / len(uploaded_files))

        # --- STEP 3: ZIP DOWNLOAD ---
        if results:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a") as zip_file:
                for original_name, data in results.items():
                    # Clean filename to remove invalid characters
                    clean_name = "".join([c for c in data['match'] if c.isalnum() or c in (' ', '_')]).strip()
                    zip_file.writestr(f"{clean_name}.jpg", data['bytes'])
            
            st.download_button(
                label="📥 Download Renamed Zip",
                data=zip_buffer.getvalue(),
                file_name="matched_images.zip",
                mime="application/zip"
            )
