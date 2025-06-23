# main_app.py

import tkinter as tk
from tkinter import messagebox
import threading
import time
import os
from recorder import ScreenRecorder

OUTPUT_VIDEO_FILE = "raw_recording.mp4"
OUTPUT_METADATA_FILE = "mouse_metadata.json"

class ControlPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.recorder = ScreenRecorder(OUTPUT_VIDEO_FILE, OUTPUT_METADATA_FILE)
        self.is_recording = False
        self.elapsed_time = 0
        self.timer_after_id = None
        self.recording_start_time = None

        self.title("Screen Recorder Controls")
        self.geometry("350x150")
        self.resizable(False, False)
        self.attributes('-topmost', True)

        # Status label
        self.lbl_status = tk.Label(self, text="Ready to record", font=("Helvetica", 10))
        self.lbl_status.pack(pady=(10, 0))

        # Timer display
        self.lbl_timer = tk.Label(self, text="00:00:00", font=("Helvetica", 24, "bold"))
        self.lbl_timer.pack(pady=10)

        # Button frame
        button_frame = tk.Frame(self)
        button_frame.pack(pady=5)
        
        self.btn_start = tk.Button(
            button_frame, text="Start", command=self.start_recording, 
            font=("Helvetica", 10), width=10, bg="#4CAF50", fg="white"
        )
        self.btn_start.pack(side=tk.LEFT, padx=5)
        
        self.btn_pause = tk.Button(
            button_frame, text="Pause", command=self.toggle_pause, 
            font=("Helvetica", 10), width=10, state=tk.DISABLED
        )
        self.btn_pause.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(
            button_frame, text="Stop", command=self.stop_recording, 
            font=("Helvetica", 10), width=10, state=tk.DISABLED, 
            bg="#FF4500", fg="white"
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start_recording(self):
        """Start the recording process"""
        if self.is_recording:
            return

        self.lbl_status.config(text="Starting recording...", fg="orange")
        self.update()

        # Start recording in a separate thread
        def start_thread():
            success = self.recorder.start()
            self.after(0, lambda: self._on_recording_started(success))

        threading.Thread(target=start_thread, daemon=True).start()

    def _on_recording_started(self, success):
        """Called when recording start attempt completes"""
        if success:
            self.is_recording = True
            self.elapsed_time = 0
            self.recording_start_time = time.time()
            
            self.btn_start.config(state=tk.DISABLED)
            self.btn_pause.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)
            
            self.lbl_status.config(text="Recording...", fg="red")
            self.update_timer()
        else:
            self.lbl_status.config(text="Failed to start recording!", fg="red")
            messagebox.showerror("Error", "Failed to start recording. Please check your system permissions and try again.")

    def stop_recording(self):
        """Stop the recording process"""
        if not self.is_recording:
            return

        self.lbl_status.config(text="Stopping recording...", fg="orange")
        self._set_buttons_disabled()
        
        # Cancel timer
        if self.timer_after_id:
            self.after_cancel(self.timer_after_id)
            self.timer_after_id = None

        # Stop recording in a separate thread
        def stop_thread():
            success = self.recorder.stop()
            self.after(0, lambda: self._on_recording_stopped(success))

        threading.Thread(target=stop_thread, daemon=True).start()
        
    def _on_recording_stopped(self, success):
        """Called when recording stop attempt completes"""
        self.is_recording = False
        
        if success:
            self.lbl_status.config(text="Recording saved successfully!", fg="green")
            # Check if files exist
            video_exists = os.path.exists(OUTPUT_VIDEO_FILE)
            metadata_exists = os.path.exists(OUTPUT_METADATA_FILE)
            
            if video_exists and metadata_exists:
                messagebox.showinfo("Success", 
                    f"Recording saved successfully!\n\n"
                    f"Video: {OUTPUT_VIDEO_FILE}\n"
                    f"Metadata: {OUTPUT_METADATA_FILE}\n\n"
                    f"You can now run the editor to process your recording.")
            else:
                missing = []
                if not video_exists: missing.append("video file")
                if not metadata_exists: missing.append("metadata file")
                messagebox.showwarning("Partial Success", 
                    f"Recording completed but {', '.join(missing)} missing.")
        else:
            self.lbl_status.config(text="Error stopping recording!", fg="red")
            messagebox.showerror("Error", "There was an error stopping the recording.")

        # Reset UI
        self._reset_ui()

    def toggle_pause(self):
        """Toggle pause/resume recording"""
        if not self.is_recording:
            return

        if self.recorder.is_paused:
            success = self.recorder.resume()
            if success:
                self.btn_pause.config(text="Pause")
                self.lbl_status.config(text="Recording...", fg="red")
                self.update_timer()  # Resume timer
        else:
            success = self.recorder.pause()
            if success:
                self.btn_pause.config(text="Resume")
                self.lbl_status.config(text="Paused", fg="orange")
                if self.timer_after_id:
                    self.after_cancel(self.timer_after_id)
                    self.timer_after_id = None

    def update_timer(self):
        """Update the timer display"""
        if not self.is_recording or self.recorder.is_paused:
            return
        
        if self.recording_start_time:
            self.elapsed_time = int(time.time() - self.recording_start_time)
        
        hours, rem = divmod(self.elapsed_time, 3600)
        minutes, seconds = divmod(rem, 60)
        self.lbl_timer.config(text=f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}")
        
        self.timer_after_id = self.after(1000, self.update_timer)

    def _set_buttons_disabled(self):
        """Disable all buttons"""
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)

    def _reset_ui(self):
        """Reset UI to initial state"""
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED, text="Pause")
        self.btn_stop.config(state=tk.DISABLED)
        self.elapsed_time = 0
        self.recording_start_time = None
        self.lbl_timer.config(text="00:00:00")
        
        # After 3 seconds, reset status to ready
        self.after(3000, lambda: self.lbl_status.config(text="Ready to record", fg="black"))

    def on_closing(self):
        """Handle window close event"""
        if self.is_recording:
            result = messagebox.askyesnocancel(
                "Recording in Progress", 
                "Recording is still in progress. Do you want to stop recording and exit?"
            )
            if result is True:  # Yes - stop and exit
                self.stop_recording()
                # Wait a bit for the stop process, then force close
                self.after(2000, self.destroy)
            elif result is False:  # No - just exit without stopping
                self.destroy()
            # Cancel - do nothing, keep window open
        else:
            self.destroy()

if __name__ == "__main__":
    # Check for required dependencies
    try:
        import dxcam
        import pynput
    except ImportError as e:
        tk.messagebox.showerror("Missing Dependencies", 
            f"Required package not found: {e}\n\n"
            "Please install required packages:\n"
            "pip install dxcam pynput opencv-python")
        exit(1)
    
    app = ControlPanel()
    app.mainloop()