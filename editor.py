# editor.py

import cv2
import json
import numpy as np
from moviepy.editor import VideoFileClip, ImageSequenceClip
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import threading
import os
import subprocess

# --- Configuration ---
RAW_VIDEO_FILE = "raw_recording.mp4"
METADATA_FILE = "mouse_metadata.json"
FINAL_VIDEO_FILE = "final_cut_ai.mp4"
PREVIEW_WIDTH = 800

# --- Zoom & Pan Parameters ---
ZOOM_LEVEL = 2.0         # How much to zoom in (e.g., 2.0 = 200%)
SMOOTHING = 0.08         # Camera smoothing factor (lower is smoother, 0.0-1.0)
ZOOM_DURATION = 2.5      # How long the zoom effect lasts in seconds

# --- AI Parameters ---
AI_CLICK_COOLDOWN = ZOOM_DURATION # Prevents frantic zooming on rapid clicks

class Camera:
    """Represents the virtual camera that pans and zooms."""
    def __init__(self, screen_width, screen_height):
        self.screen_width, self.screen_height = screen_width, screen_height
        self.x = self.target_x = screen_width / 2
        self.y = self.target_y = screen_height / 2
        self.zoom = self.target_zoom = 1.0

    def update(self):
        """Smoothly interpolates the camera towards its target."""
        self.x += (self.target_x - self.x) * SMOOTHING
        self.y += (self.target_y - self.y) * SMOOTHING
        self.zoom += (self.target_zoom - self.zoom) * SMOOTHING

    def set_target(self, target_x, target_y, target_zoom):
        """Sets the new target for the camera to move to."""
        self.target_x = max(0, min(target_x, self.screen_width))
        self.target_y = max(0, min(target_y, self.screen_height))
        self.target_zoom = max(1.0, target_zoom)

    def process_frame(self, frame):
        """Crops and resizes a frame based on the camera's state."""
        if frame is None:
            return None
            
        h, w = frame.shape[:2]
        crop_w = int(w / self.zoom)
        crop_h = int(h / self.zoom)
        crop_x = int(self.x - crop_w / 2)
        crop_y = int(self.y - crop_h / 2)

        # Ensure crop bounds are within frame
        crop_x = max(0, min(crop_x, w - crop_w))
        crop_y = max(0, min(crop_y, h - crop_h))
        
        try:
            cropped_frame = frame[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
            if cropped_frame.size == 0:
                return frame  # Return original if crop failed
            return cv2.resize(cropped_frame, (w, h), interpolation=cv2.INTER_LANCZOS4)
        except Exception as e:
            print(f"Error processing frame: {e}")
            return frame

class EditorApp(tk.Tk):
    """The main GUI application for the editor."""
    def __init__(self, video_clip=None, metadata=None):
        super().__init__()
        self.title("AI-Powered FocuSee-Style Editor")
        self.geometry("900x700")
        
        self.clip = video_clip
        self.metadata = metadata or []
        self.zoom_points = []
        self.current_frame_idx = 0
        self.is_rendering = False
        
        if self.clip:
            self.total_frames = int(self.clip.duration * self.clip.fps)
            self.preview_height = int(PREVIEW_WIDTH * (self.clip.h / self.clip.w))
        else:
            self.total_frames = 0
            self.preview_height = 450

        self._setup_ui()
        
        if self.clip:
            self.update_preview(0)

    def _setup_ui(self):
        """Setup the user interface"""
        # File menu
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load Project Files...", command=self.load_files)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # Main frame
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Preview canvas
        self.canvas = tk.Canvas(main_frame, width=PREVIEW_WIDTH, height=self.preview_height, bg="black")
        self.canvas.pack(pady=5)
        
        if not self.clip:
            self.canvas.create_text(PREVIEW_WIDTH//2, self.preview_height//2, 
                                  text="No video loaded\nUse File > Load Project Files", 
                                  fill="white", font=("Helvetica", 16))
        
        # Timeline slider
        self.slider = ttk.Scale(main_frame, from_=0, to=max(1, self.total_frames - 1), 
                               orient=tk.HORIZONTAL, command=self.on_slider_change)
        self.slider.pack(fill=tk.X, padx=10, pady=5)
        if not self.clip: self.slider.config(state=tk.DISABLED)
        
        # Time label
        self.time_label = tk.Label(main_frame, text="Time: 0.00s" if self.clip else "No video loaded")
        self.time_label.pack()

        # Control buttons
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=10)

        self.ai_btn = tk.Button(button_frame, text="✨ AI: Suggest Zoom Points", 
                               command=self.ai_suggest_zooms, bg="#D1E7DD", 
                               activebackground="#A3C4A3")
        self.ai_btn.pack(side=tk.LEFT, padx=5)
        
        self.add_zoom_btn = tk.Button(button_frame, text="➕ Add Manual Point", 
                                     command=self.add_zoom_point)
        self.add_zoom_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = tk.Button(button_frame, text="❌ Clear All", 
                                  command=self.clear_zoom_points, fg="red")
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        self.render_btn = tk.Button(button_frame, text="🎬 Render Video", 
                                   command=self.start_rendering, 
                                   font=('Helvetica', 10, 'bold'), bg="#4CAF50", fg="white")
        self.render_btn.pack(side=tk.LEFT, padx=10)
        
        # Disable buttons if no clip loaded
        if not self.clip:
            for btn in [self.ai_btn, self.add_zoom_btn, self.clear_btn, self.render_btn]:
                btn.config(state=tk.DISABLED)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, orient=tk.HORIZONTAL, 
                                       length=100, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        
        self.progress_label = tk.Label(main_frame, text="Ready" if self.clip else "Load project files to begin")
        self.progress_label.pack()

        # Zoom points info
        self.zoom_info_label = tk.Label(main_frame, text="Zoom points: 0")
        self.zoom_info_label.pack(pady=(10, 0))

    def load_files(self):
        """Load video and metadata files"""
        video_file = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        
        if not video_file:
            return
            
        metadata_file = filedialog.askopenfilename(
            title="Select metadata file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not metadata_file:
            return
            
        try:
            # Use OpenCV to get video properties
            cap = cv2.VideoCapture(video_file)
            if not cap.isOpened():
                raise Exception("Could not open video file")
                
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            # Create VideoFileClip with known parameters
            self.clip = VideoFileClip(video_file)
            self.clip.fps = fps
            
            # Load metadata
            with open(metadata_file, 'r') as f:
                self.metadata = json.load(f)
            
            # Update UI
            self.total_frames = frame_count
            self.preview_height = int(PREVIEW_WIDTH * (height / width))
            
            # Reconfigure canvas
            self.canvas.config(height=self.preview_height)
            
            # Reconfigure slider
            self.slider.config(to=self.total_frames - 1, state=tk.NORMAL)
            
            # Enable buttons
            for btn in [self.ai_btn, self.add_zoom_btn, self.clear_btn, self.render_btn]:
                btn.config(state=tk.NORMAL)
            
            # Clear zoom points
            self.zoom_points = []
            self.update_zoom_info()
            
            # Update preview
            self.update_preview(0)
            self.progress_label.config(text="Ready")
            
            messagebox.showinfo("Success", "Project files loaded successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load project files:\n{e}")

    def on_slider_change(self, val):
        if self.clip and not self.is_rendering:
            self.current_frame_idx = int(float(val))
            self.update_preview(self.current_frame_idx)

    def add_zoom_point(self):
        if not self.clip:
            return
            
        current_time = self.current_frame_idx / self.clip.fps
        if current_time not in self.zoom_points:
            self.zoom_points.append(current_time)
            self.zoom_points.sort()
            self.draw_zoom_markers()
            self.update_zoom_info()

    def clear_zoom_points(self):
        if messagebox.askyesno("Confirm", "Remove all zoom points?"):
            self.zoom_points.clear()
            self.draw_zoom_markers()
            self.update_zoom_info()

    def ai_suggest_zooms(self):
        if not self.clip or not self.metadata:
            messagebox.showinfo("AI Analysis", "No metadata available for analysis.")
            return
            
        suggested_points, last_zoom_time = [], -AI_CLICK_COOLDOWN
        
        for event in self.metadata:
            if (event.get('type') == 'click_press' and 
                event.get('time', 0) >= last_zoom_time + AI_CLICK_COOLDOWN):
                suggested_points.append(event['time'])
                last_zoom_time = event['time']
        
        if not suggested_points:
            messagebox.showinfo("AI Analysis", "No significant click events found for zoom suggestions.")
            return

        # Filter out points beyond video duration
        valid_points = [t for t in suggested_points if t < self.clip.duration]
        
        if not valid_points:
            messagebox.showinfo("AI Analysis", "No valid click events found within video duration.")
            return

        old_count = len(self.zoom_points)
        self.zoom_points = sorted(list(set(self.zoom_points + valid_points)))
        new_count = len(self.zoom_points) - old_count
        
        self.draw_zoom_markers()
        self.update_zoom_info()
        messagebox.showinfo("AI Success", f"Added {new_count} new zoom points based on mouse clicks!")

    def update_zoom_info(self):
        """Update the zoom points info label"""
        self.zoom_info_label.config(text=f"Zoom points: {len(self.zoom_points)}")

    def draw_zoom_markers(self):
        if not self.clip:
            return
            
        self.canvas.delete("zoom_marker")
        for zoom_time in self.zoom_points:
            x_pos = (zoom_time / self.clip.duration) * PREVIEW_WIDTH
            self.canvas.create_line(x_pos, 0, x_pos, 15, fill="#FFD700", width=2, tags="zoom_marker")

    def update_preview(self, frame_idx):
        if not self.clip:
            return
            
        try:
            current_time = frame_idx / self.clip.fps
            self.time_label.config(text=f"Time: {current_time:.2f}s / {self.clip.duration:.2f}s")
            
            frame = self.clip.get_frame(current_time)
            img = Image.fromarray(frame)
            img.thumbnail((PREVIEW_WIDTH, self.preview_height), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(image=img)
            
            self.canvas.delete("preview_image")
            self.canvas.create_image(PREVIEW_WIDTH//2, self.preview_height//2, 
                                   image=self.photo, tags="preview_image")
            self.draw_zoom_markers()
            
        except Exception as e:
            print(f"Error updating preview: {e}")
            self.time_label.config(text="Error loading frame")

    def get_mouse_pos_at_time(self, t):
        """Get the mouse position at a specific time from metadata"""
        if not self.metadata:
            return None
            
        for event in reversed(self.metadata):
            if event.get('time', 0) <= t and event.get('type') == 'move':
                return (event.get('x', 0), event.get('y', 0))
        return None
    
    def start_rendering(self):
        """Start the video rendering process"""
        if not self.clip:
            messagebox.showerror("Error", "No video loaded!")
            return
            
        if self.is_rendering:
            return
            
        if not self.zoom_points and not messagebox.askyesno(
            "Confirm", "No zoom points are set. Render without any effects?"):
            return
            
        # Choose output file
        output_file = filedialog.asksaveasfilename(
            title="Save rendered video as...",
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
            initialvalue=FINAL_VIDEO_FILE
        )
        
        if not output_file:
            return
            
        self.set_ui_state(tk.DISABLED)
        self.is_rendering = True
        threading.Thread(target=self.render_video, args=(output_file,), daemon=True).start()

    def set_ui_state(self, state):
        """Enable or disable UI elements"""
        widgets = [self.ai_btn, self.add_zoom_btn, self.clear_btn, self.render_btn, self.slider]
        for widget in widgets:
            widget.config(state=state)

    def render_video(self, output_file):
        """Render the video with zoom effects"""
        try:
            camera = Camera(self.clip.w, self.clip.h)
            processed_frames = []
            total_frames = int(self.clip.duration * self.clip.fps)
            
            # Update progress bar maximum
            self.after(0, lambda: setattr(self.progress, 'maximum', total_frames))

            for i, frame in enumerate(self.clip.iter_frames()):
                current_time = i / self.clip.fps
                
                # Check if we're in a zoom period
                in_zoom = any(zt <= current_time < zt + ZOOM_DURATION for zt in self.zoom_points)
                
                if in_zoom:
                    # Find the mouse position at this time or use center
                    target_pos = self.get_mouse_pos_at_time(current_time)
                    if target_pos is None:
                        target_pos = (self.clip.w / 2, self.clip.h / 2)
                    camera.set_target(target_pos[0], target_pos[1], ZOOM_LEVEL)
                else:
                    # Return to center and normal zoom
                    camera.set_target(self.clip.w / 2, self.clip.h / 2, 1.0)
                
                camera.update()
                processed_frame = camera.process_frame(frame)
                processed_frames.append(processed_frame)
                
                # Update progress every 10 frames
                if i % 10 == 0:
                    progress_val = i + 1
                    self.after(0, lambda p=progress_val: setattr(self.progress, 'value', p))
                    self.after(0, lambda p=progress_val: 
                             self.progress_label.config(text=f"Rendering frame {p}/{total_frames}"))

            # Save the video
            self.after(0, lambda: self.progress_label.config(text="Saving video file... This may take a while."))
            
            final_clip = ImageSequenceClip(processed_frames, fps=self.clip.fps)
            final_clip.write_videofile(output_file, codec="libx264", logger=None, verbose=False)
            final_clip.close()

            # Success
            self.after(0, lambda: messagebox.showinfo("Success!", 
                      f"Render complete! Video saved as:\n{output_file}"))
            
        except Exception as e:
            print(f"Error during rendering: {e}")
            self.after(0, lambda: messagebox.showerror("Render Error", 
                      f"An error occurred during rendering:\n{e}"))
        finally:
            # Reset UI state
            self.after(0, self._rendering_complete)

    def _rendering_complete(self):
        """Called when rendering is complete"""
        self.is_rendering = False
        self.set_ui_state(tk.NORMAL)
        self.progress['value'] = 0
        self.progress_label.config(text="Ready")

def main():
    """Main function to start the editor"""
    app = EditorApp()
    
    # Try to load default files if they exist
    if os.path.exists(RAW_VIDEO_FILE) and os.path.exists(METADATA_FILE):
        try:
            # Use OpenCV to get video properties
            cap = cv2.VideoCapture(RAW_VIDEO_FILE)
            if not cap.isOpened():
                raise Exception("Could not open video file")
                
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            # Create VideoFileClip with known parameters
            clip = VideoFileClip(RAW_VIDEO_FILE)
            clip.fps = fps
            
            with open(METADATA_FILE, 'r') as f:
                metadata = json.load(f)
            
            app.clip = clip
            app.metadata = metadata
            app.total_frames = frame_count
            app.preview_height = int(PREVIEW_WIDTH * (height / width))
            
            # Update UI for loaded files
            app.canvas.config(height=app.preview_height)
            app.slider.config(to=app.total_frames - 1, state=tk.NORMAL)
            
            for btn in [app.ai_btn, app.add_zoom_btn, app.clear_btn, app.render_btn]:
                btn.config(state=tk.NORMAL)
            
            app.update_preview(0)
            app.progress_label.config(text="Ready")
            print("Default project files loaded successfully.")
            
        except Exception as e:
            print(f"Could not load default project files: {e}")
    
    app.mainloop()

if __name__ == "__main__":
    main()