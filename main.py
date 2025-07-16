import fitz  # PyMuPDF for PDF reading
import pyttsx3
import pygame
import threading
import os
import time
import speech_recognition as sr
from tkinter import *
from tkinter import ttk, messagebox, simpledialog
from tkinter import END
from tkinter.filedialog import askopenfilename, asksaveasfilename
import logging
from concurrent.futures import ThreadPoolExecutor
import requests
import json
# Initialize logging first
logging.basicConfig(
    filename='error_log.txt',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# Global variables
pdf = None
current_page_num = 0
tts_thread = None
executor = ThreadPoolExecutor(max_workers=3)
text_to_read = ""
is_playing = False
should_stop = False
is_paused = False
current_sentence_index = 0
recognizer = sr.Recognizer()


bookmarks = {}

def add_bookmark():
    """Add bookmark for current page."""
    if not pdf:
        messagebox.showinfo("Info", "Please load a PDF first.")
        return
        
    name = simpledialog.askstring("Bookmark", "Enter bookmark name:")
    if name:
        if name in bookmarks:
            if not messagebox.askyesno("Confirm", "Bookmark already exists. Update it?"):
                return
        bookmarks[name] = current_page_num
        save_bookmarks()  # Save immediately after adding
        update_bookmark_menu()

def goto_bookmark(page_num):
    """Go to bookmarked page."""
    global current_page_num
    current_page_num = page_num
    update_current_page_display()
    display_pdf_content(current_page_num)
# Add after global variables
current_pdf_path = None

def save_bookmarks():
    """Save bookmarks to file."""
    try:
        with open("bookmarks.json", "w") as f:
            json.dump({
                "bookmarks": {
                    name: {
                        "page": page,
                        "pdf_path": current_pdf_path
                    } for name, page in bookmarks.items()
                }
            }, f)
    except Exception as e:
        logging.error(f"Error saving bookmarks: {str(e)}")
        messagebox.showerror("Error", "Failed to save bookmarks")    

def load_bookmarks():
    """Load bookmarks from file."""
    global bookmarks
    try:
        if os.path.exists("bookmarks.json"):
            with open("bookmarks.json", "r") as f:
                data = json.load(f)
                if pdf:
                    bookmarks = {name: data[name]["page"] 
                               for name in data 
                               if data[name]["pdf"] == pdf.name}
                update_bookmark_menu()
    except Exception as e:
        logging.error(f"Error loading bookmarks: {str(e)}")
def update_bookmark_menu():
    """Update the bookmarks menu."""
    # Clear existing bookmarks
    for i in range(bookmark_menu.index("END"), 1, -1):
        bookmark_menu.delete(i)
    
    # Add current bookmarks
    if bookmarks:
        for name, page in bookmarks.items():
            bookmark_menu.add_command(
                label=f"{name} (Page {page + 1})",
                command=lambda p=page: goto_bookmark(p)
            )  
                      

def show_statistics():
    """Show text statistics."""
    if not pdf:
        return
        
    text = text_display.get("1.0", END)
    words = len(text.split())
    chars = len(text)
    lines = len(text.splitlines())
    
    stats = f"""Text Statistics:
    Words: {words}
    Characters: {chars}
    Lines: {lines}
    Current Page: {current_page_num + 1}
    Total Pages: {pdf.page_count}
    """
    messagebox.showinfo("Statistics", stats)    
# Add after global variables
MAX_RECENT_FILES = 5
recent_files = []

def update_recent_files(file_path):
    """Update recent files list."""
    global recent_files
    if file_path in recent_files:
        recent_files.remove(file_path)
    recent_files.insert(0, file_path)
    if len(recent_files) > MAX_RECENT_FILES:
        recent_files.pop()
    update_recent_menu()

try:
    player = pyttsx3.init()
    tts_available = True
except Exception as e:
    logging.error(f"TTS initialization error: {str(e)}")

try:
    pygame.mixer.init()
    music_available = True
except Exception as e:
    logging.error(f"Music initialization error: {str(e)}")
# Check internet connection
def check_internet():
    """Check if there is an active internet connection."""
    try:
        requests.get("http://www.google.com", timeout=3)
        return True
    except requests.ConnectionError:
        try:
            # Try an alternative URL as backup
            requests.get("http://www.bing.com", timeout=3)
            return True
        except requests.ConnectionError:
            return False

# Alternative to googletrans - using a more stable solution
try:
    from deep_translator import GoogleTranslator
    has_translator = True
except ImportError:
    has_translator = False
    messagebox.showwarning("Translation Feature", "Translation libraries not found. Translation features will be disabled.")

# ... rest of the code ...

# In the translate_text function, replace the translation part:
def translate_text():
    """Translate displayed text to the selected language."""
    if not has_translator:
        messagebox.showwarning("Warning", "Translation library not available.")
        return
        
    if not check_internet():
        messagebox.showwarning("Warning", "Internet connection required for translation.")
        return
        
    try:
        # Get current language from dropdown if not already selected
        if not lang_var.get():
            lang_var.set("en")  # Default to English
            
        translator = GoogleTranslator(source='auto', target=lang_var.get())
        
        # Get text from display or selection
        try:
            selected_text = text_display.get(SEL_FIRST, SEL_LAST)
            if selected_text.strip():
                text_to_translate = selected_text
            else:
                text_to_translate = text_display.get("1.0", END)
        except TclError:
            text_to_translate = text_display.get("1.0", END)
        
        if not text_to_translate.strip():
            messagebox.showinfo("Info", "No text to translate.")
            return
            
        status_label.config(text=f"Translating to {lang_dict[lang_var.get()]}...")
        root.update()
        
        def _translate_task():
            try:
                translation = translator.translate(text_to_translate)
                return translation
            except Exception as e:
                logging.error("Translation Error: %s", str(e))
                return None
                
        # Run in background thread
        translated_text = executor.submit(_translate_task).result()
        
        if translated_text:
            text_display.config(state=NORMAL)
            text_display.delete("1.0", END)
            text_display.insert(END, translated_text)
            text_display.config(state=DISABLED)
            status_label.config(text=f"Translated to {lang_dict[lang_var.get()]}")
            
            # Store the translated text for TTS
            global text_to_read
            text_to_read = translated_text
        else:
            messagebox.showerror("Error", "Translation failed")
            status_label.config(text="Translation failed")
            
    except Exception as e:
        logging.error("Error in translate_text: %s", str(e))
        messagebox.showerror("Error", "An error occurred during translation")


# ----- PDF Reading Functions -----
def load_pdf() -> None:
    """Load and display PDF file."""
    global pdf, text_to_read, current_page_num, current_pdf_path
    
    try:
        # Close existing PDF if open
        if pdf:
            try:
                pdf.close()
            except Exception:
                pass
            pdf = None
        
        file_path = askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not file_path:
            return  # User canceled

        status_label.config(text="Loading PDF...")
        root.update()
        
        current_pdf_path = file_path  # Set the current PDF path
        
        def _load_pdf_task():
            try:
                pdf_doc = fitz.open(file_path)
                if not pdf_doc or pdf_doc.page_count == 0:
                    if pdf_doc:
                        pdf_doc.close()
                    return None, "PDF file is empty or invalid"
                first_page_text = pdf_doc[0].get_text()
                return pdf_doc, first_page_text
            except Exception as e:
                return None, f"Failed to read PDF: {str(e)}"

        # Run in background thread
        pdf_result, result_text = executor.submit(_load_pdf_task).result()

        if pdf_result:
            pdf = pdf_result
            current_page_num = 0
            status_label.config(text=f"Loaded: {os.path.basename(file_path)} ({pdf.page_count} pages)")
            root.update()
            
            # Clear and update display
            text_display.config(state=NORMAL)
            text_display.delete("1.0", END)
            display_pdf_content(current_page_num, result_text)
            update_current_page_display()
            
            # Load bookmarks for this PDF
            load_bookmarks()
            update_bookmark_menu()
        else:
            status_label.config(text="Failed to load PDF")
            messagebox.showerror("Error", result_text)
            
    except Exception as e:
        logging.error(f"Error in load_pdf: {str(e)}")
        messagebox.showerror("Error", f"Failed to load PDF: {str(e)}")
        status_label.config(text="Error loading PDF")

def display_pdf_content(page_num, text=None):
    """Display PDF content in the text area."""
    if not pdf:
        return
    
    try:
        # Enable widget before modifications
        text_display.config(state=NORMAL)
        text_display.delete("1.0", END)
        
        if text is None:
            # Load text for the current page
            if 0 <= page_num < pdf.page_count:
                page = pdf[page_num]
                text = page.get_text()
            else:
                text = "Invalid page number"
        
        if text:  # Only insert if there's text to display
            text_display.insert("1.0", text)
        
        # Disable widget after modifications
        text_display.config(state=DISABLED)
        
        # Update page entry
        page_entry.delete(0, END)
        page_entry.insert(0, str(page_num + 1))
        
    except Exception as e:
        logging.error(f"Error displaying PDF content: {str(e)}")
        text_display.config(state=NORMAL)
        text_display.delete("1.0", END)
        text_display.insert(END, f"Error displaying content: {str(e)}")
        text_display.config(state=DISABLED)

def update_current_page_display():
    """Update the current page display and read status."""
    if pdf:
        page_status.config(text=f"Page {current_page_num + 1} of {pdf.page_count}")
    else:
        page_status.config(text="No PDF loaded")

# ----- Navigation Functions -----
def next_page():
    """Go to the next page."""
    global current_page_num
    if pdf and current_page_num < pdf.page_count - 1:
        current_page_num += 1
        update_current_page_display()
        display_pdf_content(current_page_num)

def prev_page():
    """Go to the previous page."""
    global current_page_num
    if pdf and current_page_num > 0:
        current_page_num -= 1
        update_current_page_display()
        display_pdf_content(current_page_num)

def go_to_page():
    """Navigate to a specific PDF page."""
    global current_page_num
    if not pdf:
        messagebox.showinfo("Info", "Please load a PDF first.")
        return
    
    try:
        requested_page = int(page_entry.get()) - 1  # Convert to 0-based index
        if 0 <= requested_page < pdf.page_count:
            current_page_num = requested_page
            update_current_page_display()
            display_pdf_content(current_page_num)
        else:
            messagebox.showwarning("Warning", f"Page number must be between 1 and {pdf.page_count}.")
    except ValueError:
        messagebox.showwarning("Warning", "Please enter a valid page number.")

# ----- TTS Functions -----
def prepare_text_for_reading():
    """Prepare text from current page or selection for reading."""
    global text_to_read
    
    # Check if there's a text selection
    try:
        selected_text = text_display.get(SEL_FIRST, SEL_LAST)
        if selected_text.strip():
            text_to_read = selected_text
            return True
    except TclError:
        # No selection, read all text
        text_to_read = text_display.get("1.0", END)
        if text_to_read.strip():
            return True
    
    return False

def highlight_text(start_index, end_index):
    """Highlight the text being read."""
    text_display.tag_remove("highlight", "1.0", END)
    text_display.tag_add("highlight", start_index, end_index)
    text_display.see(start_index)  # Auto-scroll to the highlighted text
    text_display.tag_config("highlight", background="yellow", foreground="black")

def start_tts(resume=False):
    """Start TTS from the beginning or resume from last position."""
    global tts_thread, is_playing, should_stop, current_sentence_index, is_paused
    
    if not tts_available:
        messagebox.showwarning("Warning", "Text-to-speech is not available.")
        return
        
    if is_playing and not resume:
        stop_audio()  # Stop current playback before starting new one
        time.sleep(0.5)  # Give time for the previous playback to stop
    
    if prepare_text_for_reading() or resume:
        should_stop = False
        is_playing = True
        status_label.config(text="Reading text...")
        
        def run_tts():
            try:
                # Declare globals inside the function
                global is_playing, is_paused, current_sentence_index
                
                # Apply speed setting
                player.setProperty('rate', int(speed_slider.get()))
                
                # Get selected voice if available
                if hasattr(player, 'getProperty') and hasattr(player, 'setProperty'):
                    voices = player.getProperty('voices')
                    if voices and voice_var.get() < len(voices):
                        player.setProperty('voice', voices[voice_var.get()].id)
                
                # Split text into sentences for highlighting
                sentences = text_to_read.split('.')
                current_pos = "1.0"
                
                # Start from the saved position if resuming
                start_index = current_sentence_index if resume else 0
                
                # If resuming, find the correct starting position in text
                if resume and start_index > 0:
                    for i in range(start_index):
                        if sentences[i].strip():
                            pos = text_display.search(sentences[i].strip(), current_pos, END)
                            if pos:
                                current_pos = f"{pos}+{len(sentences[i])}c"
                
                for i in range(start_index, len(sentences)):
                    if should_stop:
                        current_sentence_index = i  # Save position for resume
                        break
                        
                    sentence = sentences[i]
                    if sentence.strip():
                        # Find the sentence in the text display
                        start_pos = text_display.search(sentence.strip(), current_pos, END)
                        if start_pos:
                            end_pos = f"{start_pos}+{len(sentence)}c"
                            # Highlight current sentence
                            root.after(0, lambda s=start_pos, e=end_pos: highlight_text(s, e))
                            root.update()  # Force update the display
                            # Read the sentence
                            player.say(sentence)
                            player.runAndWait()
                            current_pos = end_pos
                
                if not should_stop:
                    # Clear highlight when done
                    root.after(0, lambda: text_display.tag_remove("highlight", "1.0", END))
                    current_sentence_index = 0
                    is_paused = False
                
            except Exception as e:
                logging.error(f"TTS error: {str(e)}")
            finally:
                # Reset playing state only if not paused
                if not is_paused:
                    is_playing = False
                    status_label.config(text="Ready")
        
        # Run in a new thread
        tts_thread = threading.Thread(target=run_tts)
        tts_thread.daemon = True
        tts_thread.start()
    else:
        messagebox.showinfo("Info", "No text to read.")

def stop_audio():
    """Stop TTS."""
    global is_playing, should_stop
    
    if is_playing and tts_available:
        should_stop = True
        try:
            player.stop()
        except Exception as e:
            logging.error(f"Error stopping TTS: {str(e)}")
        
        is_playing = False
        status_label.config(text="Reading stopped")

def pause_resume_audio():
    """Pause or resume audio playback."""
    global is_playing, is_paused, should_stop
    
    if not tts_available:
        messagebox.showwarning("Warning", "Text-to-speech is not available.")
        return
        
    if is_playing and not is_paused:
        # Pause
        is_paused = True
        should_stop = True
        try:
            player.stop()
        except Exception as e:
            logging.error(f"Error pausing TTS: {str(e)}")
        status_label.config(text="Reading paused")
    elif is_paused:
        # Resume
        is_paused = False
        should_stop = False
        start_tts(resume=True)

# ----- Audio Export Functions -----
def save_audio():
    """Save the PDF text as an audio file."""
    if not pdf:
        messagebox.showinfo("Info", "Please load a PDF first.")
        return
    
    if not tts_available:
        messagebox.showwarning("Warning", "Text-to-speech is not available.")
        return
    
    try:
        if prepare_text_for_reading():
            save_path = asksaveasfilename(
                defaultextension=".mp3",
                filetypes=[("MP3 Files", "*.mp3"), ("WAV Files", "*.wav")]
            )
            
            if not save_path:
                return  # User canceled
                
            status_label.config(text="Saving audio...")
            root.update()
            
            # Check if the selected TTS engine supports direct saving
            try:
                if hasattr(player, 'save_to_file'):
                    player.save_to_file(text_to_read, save_path)
                    player.runAndWait()
                    messagebox.showinfo("Success", f"Audio saved to {save_path}")
                else:
                    messagebox.showwarning("Warning", "Current TTS engine doesn't support direct file saving.")
            except Exception as e:
                logging.error(f"Error saving audio: {str(e)}")
                messagebox.showerror("Error", f"Failed to save audio: {str(e)}")
                
            status_label.config(text="Ready")
        else:
            messagebox.showinfo("Info", "No text to save as audio.")
    except Exception as e:
        logging.error(f"Error in save_audio: {str(e)}")
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

# ----- Music Controls -----
def play_music():
    """Play background music."""
    if not music_available:
        messagebox.showwarning("Warning", "Audio playback is not available.")
        return
        
    try:
        music_file = askopenfilename(filetypes=[
            ("Audio Files", "*.mp3 *.wav *.ogg")
        ])
        
        if not music_file:
            return  # User canceled
            
        pygame.mixer.music.load(music_file)
        pygame.mixer.music.set_volume(music_volume.get() / 100)
        pygame.mixer.music.play(-1)  # Loop indefinitely
        
        status_label.config(text=f"Playing music: {os.path.basename(music_file)}")
    except Exception as e:
        logging.error(f"Error playing music: {str(e)}")
        messagebox.showerror("Error", f"Failed to play music: {str(e)}")

def stop_music():
    """Stop background music."""
    if music_available:
        try:
            pygame.mixer.music.stop()
            status_label.config(text="Music stopped")
        except Exception as e:
            logging.error(f"Error stopping music: {str(e)}")

def adjust_music_volume(val):
    """Adjust the music volume."""
    if music_available and pygame.mixer.music.get_busy():
        try:
            pygame.mixer.music.set_volume(float(val) / 100)
        except Exception as e:
            logging.error(f"Error adjusting volume: {str(e)}")

# ----- Export PDF Text -----
def export_text():
    """Export PDF text to a .txt file."""
    if not pdf:
        messagebox.showinfo("Info", "Please load a PDF first.")
        return
        
    try:
        export_file = asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")]
        )
        
        if not export_file:
            return  # User canceled
            
        status_label.config(text="Exporting text...")
        root.update()
        
        def _export_task():
            try:
                with open(export_file, "w", encoding="utf-8") as f:
                    for page_num in range(pdf.page_count):
                        page = pdf[page_num]
                        text = page.get_text()
                        f.write(f"Page {page_num + 1}\n{text}\n\n")
                return True
            except Exception as e:
                logging.error(f"Error exporting text: {str(e)}")
                return str(e)
        
        # Run in background thread
        result = executor.submit(_export_task).result()
        
        if result is True:
            messagebox.showinfo("Success", f"PDF text saved to {export_file}")
        else:
            messagebox.showerror("Error", f"Failed to export text: {result}")
            
        status_label.config(text="Ready")
    except Exception as e:
        logging.error(f"Error in export_text: {str(e)}")
        messagebox.showerror("Error", f"An error occurred: {str(e)}")


# ----- Dark Mode Toggle -----
def toggle_mode():
    """Toggle between light and dark mode."""
    current_bg = text_display.cget("bg")
    
    if current_bg == "white":
        # Dark mode
        text_display.config(bg="#1e1e1e", fg="#ffffff")
        content_frame.config(bg="#2d2d2d")
        controls_frame.config(bg="#2d2d2d")
        status_frame.config(bg="#2d2d2d")
        for label in all_labels:
            label.config(bg="#2d2d2d", fg="#ffffff")
        root.config(bg="#2d2d2d")
        mode_button.config(text="Light Mode")
    else:
        # Light mode
        text_display.config(bg="white", fg="black")
        content_frame.config(bg="#f0f0f0")
        controls_frame.config(bg="#f0f0f0")
        status_frame.config(bg="#f0f0f0")
        for label in all_labels:
            label.config(bg="#f0f0f0", fg="black")
        root.config(bg="#f0f0f0")
        mode_button.config(text="Dark Mode")

# ----- Voice Commands -----
def voice_commands():
    """Recognize and execute voice commands."""
    if not check_internet():
        messagebox.showwarning("Warning", "Internet connection required for voice recognition.")
        return
        
    try:
        status_label.config(text="Listening for commands...")
        root.update()
        
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
            
        try:
            command = recognizer.recognize_google(audio).lower()
            status_label.config(text=f"Command recognized: {command}")
            
            # Process commands
            if "start" in command or "read" in command or "play" in command:
                start_tts()
            elif "stop" in command or "pause" in command:
                stop_audio()
            elif "next" in command or "forward" in command:
                next_page()
            elif "back" in command or "previous" in command:
                prev_page()
            elif "music" in command and "stop" not in command:
                play_music()
            elif "stop music" in command:
                stop_music()
            elif "dark" in command or "night" in command:
                toggle_mode()
            elif "translate" in command:
                translate_text()
            elif "exit" in command or "quit" in command:
                if messagebox.askyesno("Confirmation", "Do you want to exit the application?"):
                    root.quit()
            else:
                status_label.config(text=f"Unknown command: {command}")
                
        except sr.UnknownValueError:
            status_label.config(text="Could not understand command")
        except sr.RequestError as e:
            status_label.config(text="Could not request results from speech service")
            logging.error(f"Speech recognition request error: {str(e)}")
            
    except Exception as e:
        logging.error(f"Voice command error: {str(e)}")
        status_label.config(text="Voice command error")

# ----- About Dialog -----
def show_about():
    """Show the about dialog."""
    about_text = """
    PDF to Audio App
    
    A tool for converting PDF documents to speech.
    
    Features:
    - PDF text extraction
    - Text-to-speech conversion
    - Background music
    - Voice commands
    - Text translation
    - Dark mode
    
    Created with Python 3.13
    """
    messagebox.showinfo("About", about_text)

# ----- Help Dialog -----
def show_help():
    """Show the help dialog."""
    help_text = """
    Quick Guide:
    
    1. File Menu:
       - Open PDF: Load a PDF document
       - Save Audio: Save current text as audio file
       - Export Text: Save PDF text to a file
    
    2. Navigation:
       - Previous/Next buttons: Move between pages
       - Go to Page: Enter a page number and click Go
    
    3. Reading:
       - Start: Begin reading current page
       - Stop: Stop reading
       - Speed: Adjust reading speed with slider
    
    4. Voice Commands:
       - "Start/Read/Play": Begin reading
       - "Stop/Pause": Stop reading
       - "Next/Forward": Next page
       - "Back/Previous": Previous page
       - "Music": Play background music
       - "Stop Music": Stop music
       - "Dark/Night": Toggle dark mode
       - "Translate": Translate current text
       - "Exit/Quit": Exit application
    """
    messagebox.showinfo("Help", help_text)

# Initialize language dictionary
lang_dict = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "zh-cn": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "ar": "Arabic",
    "it": "Italian",
    "pt": "Portuguese"
}

# ----- GUI Configuration -----
root = Tk()
root.title("PDF to Audio App")
root.geometry("1000x700")
root.minsize(800, 600)

# Main Frames
content_frame = Frame(root, bg="#f0f0f0")
content_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)

controls_frame = Frame(root, bg="#f0f0f0")
controls_frame.pack(fill=X, padx=10, pady=5)

status_frame = Frame(root, bg="#f0f0f0")
status_frame.pack(fill=X, padx=10, pady=5)

# Menu Bar Configuration
menu_bar = Menu(root)
root.config(menu=menu_bar)

# File Menu
file_menu = Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="Open PDF", command=load_pdf, accelerator="Ctrl+O")
file_menu.add_separator()
file_menu.add_command(label="Save Audio", command=save_audio)
file_menu.add_command(label="Export Text", command=export_text)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit, accelerator="Alt+F4")

# Bookmark Menu
bookmark_menu = Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Bookmarks", menu=bookmark_menu)
bookmark_menu.add_command(label="Add Bookmark", command=add_bookmark)
bookmark_menu.add_separator()

edit_menu = Menu(menu_bar, tearoff=0)
edit_menu.add_command(label="Copy", command=lambda: root.focus_get().event_generate("<<Copy>>"), accelerator="Ctrl+C")
edit_menu.add_command(label="Select All", command=lambda: text_display.tag_add("sel", "1.0", "end"), accelerator="Ctrl+A")
menu_bar.add_cascade(label="Edit", menu=edit_menu)

tools_menu = Menu(menu_bar, tearoff=0)
tools_menu.add_command(label="Voice Commands", command=voice_commands)
tools_menu.add_command(label="Translate", command=translate_text)
tools_menu.add_command(label="Toggle Dark Mode", command=toggle_mode)
menu_bar.add_cascade(label="Tools", menu=tools_menu)
tools_menu.add_command(label="Text Statistics", command=show_statistics)


help_menu = Menu(menu_bar, tearoff=0)
help_menu.add_command(label="Help", command=show_help, accelerator="F1")
help_menu.add_command(label="About", command=show_about)
menu_bar.add_cascade(label="Help", menu=help_menu)

root.config(menu=menu_bar)

# Text Display with Scrollbar
text_frame = Frame(content_frame)
text_frame.pack(fill=BOTH, expand=True)

text_display = Text(text_frame, wrap=WORD, font=("Arial", 14), bg="white", fg="black", state=DISABLED)
text_display.pack(side=LEFT, fill=BOTH, expand=True)

scrollbar = Scrollbar(text_frame, command=text_display.yview)
scrollbar.pack(side=RIGHT, fill=Y)
text_display.config(yscrollcommand=scrollbar.set)
# Add after text display creation
search_frame = Frame(content_frame)
search_frame.pack(fill=X, pady=5)

search_entry = Entry(search_frame)
search_entry.pack(side=LEFT, fill=X, expand=True)

def search_text():
    """Search text in PDF content."""
    query = search_entry.get().lower()
    if not query:
        return
        
    text_display.tag_remove("search", "1.0", END)
    
    start_pos = "1.0"
    while True:
        start_pos = text_display.search(query, start_pos, END, nocase=True)
        if not start_pos:
            break
        end_pos = f"{start_pos}+{len(query)}c"
        text_display.tag_add("search", start_pos, end_pos)
        start_pos = end_pos
    
    text_display.tag_config("search", background="lightgreen")

search_button = Button(search_frame, text="Search", command=search_text)
search_button.pack(side=LEFT, padx=5)

# Control Panels
control_notebook = ttk.Notebook(controls_frame)
control_notebook.pack(fill=BOTH, expand=True)

# TTS Control Tab
tts_frame = Frame(control_notebook, padx=10, pady=10)
control_notebook.add(tts_frame, text="Reading Controls")

# Speed Control
speed_frame = Frame(tts_frame)
speed_frame.pack(fill=X, pady=5)

speed_label = Label(speed_frame, text="Speed:")
speed_label.pack(side=LEFT)

speed_slider = Scale(speed_frame, from_=100, to=300, orient=HORIZONTAL, length=200)
speed_slider.set(170)
speed_slider.pack(side=LEFT, fill=X, expand=True)

# Voice Selection
voice_frame = Frame(tts_frame)
voice_frame.pack(fill=X, pady=5)

voice_label = Label(voice_frame, text="Voice:")
voice_label.pack(side=LEFT)

voice_var = IntVar(value=0)
voice_options = []

# Try to get available voices
if tts_available:
    try:
        voices = player.getProperty('voices')
        for i, voice in enumerate(voices):
            voice_options.append(f"{voice.name}")
    except:
        voice_options = ["Default Voice"]

voice_dropdown = ttk.Combobox(voice_frame, values=voice_options, state="readonly")
voice_dropdown.current(0)
voice_dropdown.pack(side=LEFT, fill=X, expand=True)
voice_dropdown.bind("<<ComboboxSelected>>", lambda e: voice_var.set(voice_dropdown.current()))

# TTS Control Buttons
tts_buttons_frame = Frame(tts_frame)
tts_buttons_frame.pack(fill=X, pady=10)

start_button = Button(tts_buttons_frame, text="Start Reading", command=start_tts, width=15)
start_button.pack(side=LEFT, padx=5)

pause_button = Button(tts_buttons_frame, text="Pause/Resume", command=pause_resume_audio, width=15)
pause_button.pack(side=LEFT, padx=5)

stop_button = Button(tts_buttons_frame, text="Stop", command=stop_audio, width=10)
stop_button.pack(side=LEFT, padx=5)

# Navigation Tab
nav_frame = Frame(control_notebook, padx=10, pady=10)
control_notebook.add(nav_frame, text="Navigation")

nav_buttons_frame = Frame(nav_frame)
nav_buttons_frame.pack(fill=X, pady=5)

prev_button = Button(nav_buttons_frame, text="← Previous", command=prev_page, width=12)
prev_button.pack(side=LEFT, padx=5)

go_frame = Frame(nav_buttons_frame)
go_frame.pack(side=LEFT, fill=X, expand=True)

page_label = Label(go_frame, text="Go to Page:")
page_label.pack(side=LEFT, padx=5)

page_entry = Entry(go_frame, width=5)
page_entry.pack(side=LEFT, padx=5)

go_button = Button(go_frame, text="Go", command=go_to_page, width=5)
go_button.pack(side=LEFT, padx=5)

next_button = Button(nav_buttons_frame, text="Next →", command=next_page, width=12)
next_button.pack(side=RIGHT, padx=5)

# Music Tab
music_frame = Frame(control_notebook, padx=10, pady=10)
control_notebook.add(music_frame, text="Background Music")

music_buttons_frame = Frame(music_frame)
music_buttons_frame.pack(fill=X, pady=5)

play_music_button = Button(music_buttons_frame, text="Play Music", command=play_music, width=15)
play_music_button.pack(side=LEFT, padx=5)

stop_music_button = Button(music_buttons_frame, text="Stop Music", command=stop_music, width=15)
stop_music_button.pack(side=LEFT, padx=5)

music_volume_frame = Frame(music_frame)
music_volume_frame.pack(fill=X, pady=5)

volume_label = Label(music_volume_frame, text="Volume:")
volume_label.pack(side=LEFT)

music_volume = Scale(music_volume_frame, from_=0, to=100, orient=HORIZONTAL, command=lambda val: adjust_music_volume(val))
music_volume.set(70)
music_volume.pack(side=LEFT, fill=X, expand=True)

# Translation Tab
trans_frame = Frame(control_notebook, padx=10, pady=10)
control_notebook.add(trans_frame, text="Translation")

lang_frame = Frame(trans_frame)
lang_frame.pack(fill=X, pady=5)

lang_label = Label(lang_frame, text="Target Language:")
lang_label.pack(side=LEFT)

lang_var = StringVar(value="en")
lang_dropdown = ttk.Combobox(lang_frame, textvariable=lang_var, values=list(lang_dict.keys()), state="readonly")
lang_dropdown.pack(side=LEFT, fill=X, expand=True)

# Display language names rather than codes
lang_names = Frame(trans_frame)
lang_names.pack(fill=X, pady=5)
lang_name_label = Label(lang_names, text="Selected language:")
lang_name_label.pack(side=LEFT)
selected_lang_label = Label(lang_names, text=lang_dict["en"])
selected_lang_label.pack(side=LEFT)

# Update displayed language name when selection changes
def update_lang_name(event):
    selected_lang_label.config(text=lang_dict[lang_var.get()])
lang_dropdown.bind("<<ComboboxSelected>>", update_lang_name)

translate_button = Button(trans_frame, text="Translate", command=translate_text, width=15)
translate_button.pack(pady=10)

# Status Bar
status_bar_frame = Frame(status_frame)
status_bar_frame.pack(fill=X, expand=True)

status_label = Label(status_bar_frame, text="Ready", bd=1, relief=SUNKEN, anchor=W)
status_label.pack(side=LEFT, fill=X, expand=True)

page_status = Label(status_bar_frame, text="No PDF loaded", bd=1, relief=SUNKEN, anchor=E, width=20)
page_status.pack(side=RIGHT)

# Mode Toggle Button
mode_button = Button(status_bar_frame, text="Dark Mode", command=toggle_mode, width=12)
mode_button.pack(side=RIGHT, padx=10)

# Voice Command Button
voice_cmd_button = Button(status_bar_frame, text="🎤 Voice", command=voice_commands, width=10)
voice_cmd_button.pack(side=RIGHT)

# Store labels for theme toggling
all_labels = [
    speed_label, voice_label, page_label, volume_label, 
    lang_label, lang_name_label, selected_lang_label
]

# Key bindings
def setup_bindings():
    root.bind("<Control-o>", lambda event: load_pdf())
    root.bind("<Control-s>", lambda event: save_audio())
    root.bind("<Control-e>", lambda event: export_text())
    root.bind("<Left>", lambda event: prev_page())
    root.bind("<Right>", lambda event: next_page())
    root.bind("<F1>", lambda event: show_help())
    root.bind("<space>", lambda event: start_tts() if not is_playing else stop_audio())
    text_display.bind("<Control-a>", lambda event: text_display.tag_add("sel", "1.0", "end"))

# Initialize
def init_app():
    """Initialize the application."""
    setup_bindings()
    status_label.config(text="Ready")
    
    # Check for saved settings and apply them
    try:
        if os.path.exists("settings.ini"):
            with open("settings.ini", "r") as f:
                settings = f.readlines()
                for setting in settings:
                    if setting.startswith("speed="):
                        speed_slider.set(int(setting.split("=")[1]))
                    elif setting.startswith("darkmode="):
                        if setting.split("=")[1].strip() == "True":
                            toggle_mode()
    except Exception as e:
        logging.error(f"Error loading settings: {str(e)}")

# Save settings on exit
def on_closing():
    """Save settings when closing the application."""
    try:
        save_bookmarks()
        with open("settings.ini", "w") as f:
            f.write(f"speed={speed_slider.get()}\n")
            f.write(f"darkmode={text_display.cget('bg') != 'white'}\n")
    except Exception as e:
        logging.error(f"Error saving settings: {str(e)}")
    
    # Clean up resources
    if tts_thread and tts_thread.is_alive():
        stop_audio()
    
    if music_available:
        pygame.mixer.quit()
    
    if pdf:
        pdf.close()
    
    executor.shutdown(wait=False)  # Add this line
    root.destroy()

# Bind closing event
root.protocol("WM_DELETE_WINDOW", on_closing)

# Start the application
if __name__ == "__main__":
    init_app()
    root.mainloop()






























