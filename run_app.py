# run_app.py
import subprocess
import os
import sys

def get_path(relative_path):
    """ Get the absolute path to a resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def main():
    main_script_path = get_path("main_app.py") # Point to your main app file
    command = [sys.executable, "-m", "streamlit", "run", main_script_path]
    print(f"Running command: {' '.join(command)}")
    try:
        process = subprocess.Popen(command)
        process.wait()
    except Exception as e:
        print(f"Failed to launch Streamlit app: {e}")
        import time
        time.sleep(10)

if __name__ == "__main__":
    main()