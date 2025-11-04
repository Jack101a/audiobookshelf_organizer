# 🎧 AudiobookShelf Folder Organizer

A Python + Streamlit tool that automatically organises audiobook files for **[AudiobookShelf](https://www.audiobookshelf.org/)** by fetching metadata from **Audible**.

The app scans your folder for audio files, reads embedded ID3 tags, fetches accurate metadata from Audible, lets you review and edit matches visually, and finally renames + moves the files into a clean library structure — including `.opf`, `.metadata.json`, and cover image files.

---

## ⭐ What it does

✅ Scans a folder for new audiobook files  
✅ Reads ID3 metadata (title, author, ASIN, cover)  
✅ Fetches missing metadata directly from Audible  
✅ Displays *Local vs Audible* info side-by-side  
✅ Allows manual edits before finalizing  
✅ Renames + moves files into an organized library  
✅ Downloads high-quality cover art  
✅ Generates `.opf` and `.metadata.json` files  
✅ Keeps a log to skip already processed files  

---

## 🖥 How to Use --

### 🔹 1) Streamlit UI (Recommended)

```bash
chmod +x start_app.sh
./start_app.sh
```


Then open the browser when Streamlit launches (usually at http://localhost:8501).

---

### 🔹 2) CLI (Automation / Headless Mode)

```
python main.py --input "/path/to/input" --output "/path/to/output"
```
---

### 📦 Installation --
```
git clone https://github.com/Jack101a/audiobookshelf_organizer.git
cd audiobookshelf_organizer
pip install -r requirements.txt
```

---

## ⚙️ Basic Workflow

1️⃣ Drop new audiobook files into your input folder  
2️⃣ Open the Streamlit app or run the CLI  
3️⃣ The app scans and reads local tags  
4️⃣ Fetches metadata from Audible automatically  
5️⃣ You review and approve/edit matches  
6️⃣ Files are renamed, moved, and tagged properly  

---

### 📁 Folder Structure 
```
audiobookshelf_organizer/
├─ app.py                → Streamlit UI
├─ main.py               → CLI entry point
├─ utils.py              → File scanning & logging
├─ tag_reader.py         → Reads ID3 metadata
├─ audible_client.py     → Audible metadata fetcher
├─ metadata_writer.py    → Generates .opf & metadata files
├─ file_manager.py       → Rename / move / copy logic
├─ config_loader.py      → Loads & validates config.json
└─ logger.py             → Logging setup
```
