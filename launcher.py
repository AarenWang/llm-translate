"""Simple GUI launcher for translation system."""

import sys
from pathlib import Path

def launch_desktop_gui():
    """Launch desktop GUI application."""
    print("Starting Desktop GUI...")
    try:
        from llm_translate.gui.main import TranslationGUI
        from llm_translate.config import Settings

        settings = Settings.from_env()
        app = TranslationGUI(settings)
        app.run()
    except Exception as e:
        print(f"Error starting GUI: {e}")


def launch_web_api():
    """Launch web API server."""
    print("Starting Web API...")
    try:
        from llm_translate.web.app import run_web_server

        print("Web server starting on http://localhost:8000")
        print("API docs available at http://localhost:8000/docs")
        print("Press Ctrl+C to stop the server")

        run_web_server()
    except Exception as e:
        print(f"Error starting web server: {e}")


def main():
    """Main launcher."""
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

        if mode in ["gui", "desktop"]:
            launch_desktop_gui()
        elif mode in ["web", "api"]:
            launch_web_api()
        else:
            print(f"Unknown mode: {mode}")
            print("Usage: python launcher.py [gui|web]")
    else:
        print("LLM Translate Launcher")
        print("Usage:")
        print("  python launcher.py gui   # Launch desktop GUI")
        print("  python launcher.py web   # Launch web API")
        print("\nOr directly:")
        print("  python -m llm_translate.gui.main")
        print("  python -m llm_translate.web.app")


if __name__ == "__main__":
    main()