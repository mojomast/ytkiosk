#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
import importlib.util
import time
import tempfile

APP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simple-video-player.py")

spec = importlib.util.spec_from_file_location("svp", APP_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SimpleVideoPlayer = mod.SimpleVideoPlayer


def stub_playback(app):
    def fake_play_keyword(keyword, session_id):
        time.sleep(1)

    app._play_keyword = fake_play_keyword


def find_keyword_buttons(widget):
    """Recursively find keyword buttons in the scrollable frame."""
    buttons = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            text = child.cget("text")
            if text and text.startswith("http"):
                continue
            if text and text not in (
                mod.FR["add_keyword"], mod.FR["edit"], mod.FR["exit"],
                mod.FR["help"], mod.FR["debug"], mod.FR["options"],
                "×",
            ) and text not in (
                mod.FR["control_play"], mod.FR["control_pause"],
                mod.FR["control_next"], mod.FR["control_prev"],
                mod.FR["control_stop"], mod.FR["control_keywords"],
            ):
                buttons.append(child)
        if hasattr(child, 'winfo_children'):
            try:
                buttons.extend(find_keyword_buttons(child))
            except Exception:
                pass
    return buttons


def test_button_command_bound():
    root = tk.Tk()
    root.withdraw()
    app = SimpleVideoPlayer(root)
    root.update_idletasks()

    kw_buttons = find_keyword_buttons(app.kw_scrollable)
    actual_texts = [b.cget("text") for b in kw_buttons]
    print(f"Keyword buttons found: {actual_texts}")

    if not kw_buttons:
        print("ERROR: No keyword buttons found!")
        root.destroy()
        return False

    expected = [
        "Voitures classiques",
        "Compilations d'animaux",
        "Course automobile",
        "Chasse et pêche",
    ]
    for kw in expected:
        found = any(b.cget("text") == kw for b in kw_buttons)
        print(f"  Button '{kw}': {'found' if found else 'MISSING!'}")

    import threading
    before = threading.active_count()
    stub_playback(app)
    app._on_keyword_click(expected[0])
    time.sleep(0.3)
    after = threading.active_count()

    keyword_view_visible = app.keyword_frame.winfo_ismapped()
    loading_visible = app.loading_label.winfo_ismapped()
    print(f"Keyword frame visible: {keyword_view_visible}")
    print(f"Loading label visible: {loading_visible}")

    if after > before:
        print("Button click spawns a thread (good)")
    else:
        print("No new thread detected")

    app._cleanup()
    root.destroy()
    return True


def test_button_click_simulation():
    root = tk.Tk()
    root.withdraw()
    app = SimpleVideoPlayer(root)
    root.update_idletasks()

    import threading
    original = threading.active_count()
    print(f"Threads before click: {original}")

    keyword = mod.INITIAL_KEYWORDS[0]
    try:
        stub_playback(app)
        app._on_keyword_click(keyword)
        print("_on_keyword_click returned")
        time.sleep(0.5)
        current = threading.active_count()
        print(f"Threads after click: {current}")
        if current > original:
            print("New thread was spawned (good)")
        else:
            print("No new thread detected (check daemon)")
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    finally:
        app._cleanup()
        root.destroy()


def test_edit_button_bound():
    root = tk.Tk()
    root.withdraw()
    app = SimpleVideoPlayer(root)
    root.update_idletasks()

    edits = []
    deletes = []
    for child in app.kw_scrollable.winfo_children():
        if isinstance(child, tk.Frame):
            for c in child.winfo_children():
                if isinstance(c, tk.Button) and c.cget("text") == mod.FR["edit"]:
                    edits.append(c)
                if isinstance(c, tk.Button) and c.cget("text") == "×":
                    deletes.append(c)

    print(f"Edit buttons found: {len(edits)} (expected 4)")
    print(f"Delete buttons found: {len(deletes)} (expected 4)")
    if len(edits) < 4:
        print("ERROR: Not all keywords have edit buttons!")
        root.destroy()
        return False
    if len(deletes) < 4:
        print("ERROR: Not all keywords have delete buttons!")
        root.destroy()
        return False

    keyword_rows = 0
    for child in app.kw_scrollable.winfo_children():
        if isinstance(child, tk.Frame):
            btns = [c for c in child.winfo_children() if isinstance(c, tk.Button)]
            text_btns = [c for c in btns if c.cget("text") != mod.FR["edit"] and
                         c.cget("text") != ""]
            if any(c.cget("text") == mod.FR["edit"] for c in btns) and text_btns:
                keyword_rows += 1

    print(f"Keyword rows with edit buttons: {keyword_rows}")
    if keyword_rows == 4:
        print("All 4 keywords have edit buttons (good)")
    else:
        print(f"Expected 4 keyword rows, found {keyword_rows}")

    app._cleanup()
    root.destroy()
    return True


def test_kiosk_mode():
    root = tk.Tk()
    root.withdraw()
    app = SimpleVideoPlayer(root)
    root.update_idletasks()

    is_fullscreen = root.attributes("-fullscreen")
    print(f"Fullscreen mode: {is_fullscreen}")

    root.destroy()
    return True


def test_help_button():
    """Verify help button exists and can be invoked."""
    root = tk.Tk()
    root.withdraw()
    app = SimpleVideoPlayer(root)
    root.update_idletasks()

    help_btn = None
    for child in app.top_bar.winfo_children():
        if isinstance(child, tk.Button) and child.cget("text") == mod.FR["help"]:
            help_btn = child
            break

    if help_btn:
        print("Help button found in top bar (good)")
    else:
        print("ERROR: Help button not found!")

    app._cleanup()
    root.destroy()
    return help_btn is not None


def test_debug_button_hidden_by_default():
    old_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.environ["HOME"] = tmp
            sys.modules.pop("ytkiosk.legacy", None)
            pkg = sys.modules.get("ytkiosk")
            if pkg is not None and hasattr(pkg, "legacy"):
                delattr(pkg, "legacy")
            spec2 = importlib.util.spec_from_file_location("svp_debug_default", APP_PATH)
            mod2 = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(mod2)
            root = tk.Tk()
            root.withdraw()
            app = mod2.SimpleVideoPlayer(root)
            root.update_idletasks()

            debug_btn = None
            for child in app.top_bar.winfo_children():
                if isinstance(child, tk.Button) and child.cget("text") == mod2.FR["debug"]:
                    debug_btn = child
                    break

            hidden = debug_btn is None or not debug_btn.winfo_ismapped()
            if hidden:
                print("Debug button hidden by default (good)")
            else:
                print("ERROR: Debug button should be hidden by default!")

            app._cleanup()
            root.destroy()
            return hidden
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


def test_options_button():
    root = tk.Tk()
    root.withdraw()
    app = SimpleVideoPlayer(root)
    root.update_idletasks()

    options_btn = None
    exit_btn = None
    for child in app.top_bar.winfo_children():
        if isinstance(child, tk.Button) and child.cget("text") == mod.FR["options"]:
            options_btn = child
        if isinstance(child, tk.Button) and child.cget("text") == mod.FR["exit"]:
            exit_btn = child

    if options_btn and exit_btn is None:
        print("Options button found and direct Exit hidden (good)")
    else:
        print("ERROR: Options button missing or direct Exit visible!")

    app._cleanup()
    root.destroy()
    return options_btn is not None and exit_btn is None


if __name__ == "__main__":
    print("=== Integration Test Suite ===\n")

    print("--- Test 1: Button commands are bound ---")
    test_button_command_bound()

    print("\n--- Test 2: _on_keyword_click spawns thread ---")
    test_button_click_simulation()

    print("\n--- Test 3: Edit buttons are bound ---")
    test_edit_button_bound()

    print("\n--- Test 4: Kiosk mode enabled ---")
    test_kiosk_mode()

    print("\n--- Test 5: Help button present ---")
    test_help_button()

    print("\n--- Test 6: Options button present ---")
    test_options_button()

    print("\n--- Test 7: Debug button hidden by default ---")
    test_debug_button_hidden_by_default()

    print("\n=== Integration tests complete ===")
