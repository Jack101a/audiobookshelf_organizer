import webview
import subprocess
import threading
import sys
import os
import time

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def start_streamlit():
    """Starts the streamlit server in a silent subprocess."""
    
    # Get the path to the bundled app.py
    streamlit_app_path = get_resource_path("app.py")
    
    command = [
        "streamlit", "run", streamlit_app_path,
        "--server.headless=true",      # Runs Streamlit without opening a browser
        "--server.port=8501",          # Sets a fixed port
        "--server.fileWatcherType=none" # Disables the file watcher
    ]

    try:
        # Run the command, hiding all console output
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        # In case of an error, we can't do much, but this helps debugging
        print(f"Failed to start Streamlit: {e}")

if __name__ == '__main__':
    # Start the Streamlit server in a separate daemon thread
    # This means the thread will close when the main app closes
    t = threading.Thread(target=start_streamlit)
    t.daemon = True
    t.start()

    # Give Streamlit a few seconds to start up before opening the window
    time.sleep(5) 

    # Create and start the pywebview window
    webview.create_window(
        "🎧 Audiobook Organizer",
        "http://localhost:8501",
        width=900,
        height=800,
        resizable=True
    )
    webview.start()
