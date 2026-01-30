# --- 5. VISION & PROCESSING (FULL-RETURN FIX) ---
brand_name = url.split("//")[-1].split(".")[0].capitalize() if url else "Custom_Restaurant"
temp_dir = f"./{brand_name}_output"
if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
os.makedirs(temp_dir, exist_ok=True)

progress_bar = st.progress(0)
processed_count = 0
name_tracker = {}
total_files = len(uploaded_files)

# Batch size of 5 for memory safety
for i in range(0, total_files, 5):
    batch = uploaded_files[i : i + 5]
    for file in batch:
        file_bytes = file.getvalue()
        matched_name = "Unmatched" # DEFAULT FALLBACK NAME
        
        try:
            # AI Matching Attempt
            match_resp = model.generate_content([
                f"From this menu list: {structured_menu}, which dish is this image? Return ONLY the exact name. If you are not sure, return 'Unmatched'.",
                {"mime_type": "image/jpeg", "data": file_bytes}
            ])
            
            # Use the AI result if it successfully returned text
            if match_resp and match_resp.text:
                matched_name = match_resp.text.strip()
        except Exception:
            # If the API fails or times out, matched_name remains "Unmatched"
            pass
            
        # SANITIZE & SAVE EVERY FILE
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', matched_name).strip("_")
        
        # Deduplication tracker
        count = name_tracker.get(clean_name, 0)
        name_tracker[clean_name] = count + 1
        suffix = f"_{count}" if count > 0 else ""
        
        # Save to temp directory (1KB Binary Fix)
        dest_path = os.path.join(temp_dir, f"{clean_name}{suffix}.jpg")
        with open(dest_path, "wb") as f:
            f.write(file_bytes)
        processed_count += 1
            
    progress_bar.progress(min(100, int((i + 5) / total_files * 100))) # Progress Math Fix

# --- 6. ZIP & DOWNLOAD (WILL NOW CONTAIN ALL FILES) ---
if processed_count > 0:
    zip_name = f"{brand_name}_Photos.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(temp_dir):
            z.write(os.path.join(temp_dir, f), f)
    
    st.success(f"Complete! All {processed_count} images are ready in the ZIP.")
    with open(zip_name, "rb") as f:
        st.download_button("💾 Download Results", data=f, file_name=zip_name)
    shutil.rmtree(temp_dir)
