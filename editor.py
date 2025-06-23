# editor.py

import cv2
import json
import numpy as np
from moviepy.editor import VideoFileClip, ImageSequenceClip
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading

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
        self.target_x, self.target_y, self.target_zoom = target_x, target_y, target_zoom

    def process_frame(self, frame):
        """Crops and resizes a frame based on the camera's state."""
        h, w, _ = frame.shape
        crop_w = int(w / self.zoom)
        crop_h = int(h / self.zoom)
        crop_x = int(self.x - crop_w / 2)
        crop_y = int(self.y - crop_h / 2)

        crop_x = max(0, min(crop_x, w - crop_w))
        crop_y = max(0, min(crop_y, h - crop_h))
        
        cropped_frame = frame[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
        return cv2.resize(cropped_frame, (w, h), interpolation=cv2.INTER_LANCZOS4)

class EditorApp(tk.Tk):
    """The main GUI application for the editor."""
    def __init__(self, video_clip, metadata):
        super().__init__()
        self.title("AI-Powered FocuSee-Style Editor")
        
        self.clip, self.metadata, self.zoom_points = video_clip, metadata, []
        self.total_frames = int(self.clip.duration * self.clip.fps)
        self.preview_height = int(PREVIEW_WIDTH * (self.clip.h / self.clip.w))

        self.canvas = tk.Canvas(self, width=PREVIEW_WIDTH, height=self.preview_height, bg="black")
        self.canvas.pack(pady=5)
        
        self.slider = ttk.Scale(self, from_=0, to=self.total_frames - 1, orient=tk.HORIZONTAL, command=self.on_slider_change)
        self.slider.pack(fill=tk.X, padx=10, pady=5)
        
        self.time_label = tk.Label(self, text="Time: 0.00s")
        self.time_label.pack()

        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)

        self.ai_btn = tk.Button(button_frame, text="✨ AI: Suggest Zoom Points", command=self.ai_suggest_zooms, bg="#D1E7DD", activebackground="#A3C4A3")
        self.ai_btn.pack(side=tk.LEFT, padx=5)
        self.add_zoom_btn = tk.Button(button_frame, text="➕ Add Manual Point", command=self.add_zoom_point)
        self.add_zoom_btn.pack(side=tk.LEFT, padx=5)
        self.clear_btn = tk.Button(button_frame, text="❌ Clear All", command=self.clear_zoom_points, fg="red")
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        self.render_btn = tk.Button(button_frame, text="🎬 Render Video", command=self.start_rendering, font=('Helvetica', 10, 'bold'))
        self.render_btn.pack(side=tk.LEFT, padx=10)
        
        self.progress = ttk.Progressbar(self, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        self.progress_label = tk.Label(self, text="Ready")
        self.progress_label.pack()

        self.update_preview(0)

    def on_slider_change(self, val):
        self.update_preview(int(float(val)))

    def add_zoom_point(self):
        current_time = self.slider.get() / self.clip.fps
        if current_time not in self.zoom_points:
            self.zoom_points.append(current_time)
            self.zoom_points.sort()
            self.draw_zoom_markers()

    def clear_zoom_points(self):
        if messagebox.askyesno("Confirm", "Remove all zoom points?"):
            self.zoom_points.clear()
            self.draw_zoom_markers()

    def ai_suggest_zooms(self):
        suggested_points, last_zoom_time = [], -AI_CLICK_COOLDOWN
        for event in self.metadata:
            if event['type'] == 'click_press' and event['time'] >= last_zoom_time + AI_CLICK_COOLDOWN:
                suggested_points.append(event['time'])
                last_zoom_time = event['time']
        
        if not suggested_points:
            messagebox.showinfo("AI Analysis", "No significant click events found.")
            return

        self.zoom_points = sorted(list(set(self.zoom_points + suggested_points)))
        self.draw_zoom_markers()
        messagebox.showinfo("AI Success", f"Added {len(suggested_points)} new zoom points based on mouse clicks!")

    def draw_zoom_markers(self):
        self.canvas.delete("zoom_marker")
        for zoom_time in self.zoom_points:
            x_pos = (zoom_time / self.clip.duration) * PREVIEW_WIDTH
            self.canvas.create_line(x_pos, 0, x_pos, 15, fill="#FFD700", width=2, tags="zoom_marker")

    def update_preview(self, frame_idx):
        current_time = frame_idx / self.clip.fps
        self.time_label.config(text=f"Time: {current_time:.2f}s / {self.clip.duration:.2f}s")
        
        frame = self.clip.get_frame(current_time)
        img = Image.fromarray(frame)
        img.thumbnail((PREVIEW_WIDTH, self.preview_height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image=img)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.draw_zoom_markers()

    def get_mouse_pos_at_time(self, t):
        for event in reversed(self.metadata):
            if event['time'] <= t and event['type'] == 'move':
                return (event['x'], event['y'])
        return None
    
    def start_rendering(self):
        if not self.zoom_points and not messagebox.askyesno("Confirm", "No zoom points are set. Render without any effects?"):
            return
        self.set_ui_state(tk.DISABLED)
        threading.Thread(target=self.render_video).start()

    def set_ui_state(self, state):
        self.ai_btn.config(state=state)
        self.add_zoom_btn.config(state=state)
        self.clear_btn.config(state=state)
        self.render_btn.config(state=state)

    def render_video(self):
        camera = Camera(self.clip.w, self.clip.h)
        processed_frames = []
        total_frames = int(self.clip.duration * self.clip.fps)
        self.progress['maximum'] = total_frames

        for i, frame in enumerate(self.clip.iter_frames()):
            current_time = i / self.clip.fps
            in_zoom = any(zt <= current_time < zt + ZOOM_DURATION for zt in self.zoom_points)
            
            if in_zoom:
                target_pos = self.get_mouse_pos_at_time(current_time) or (self.clip.w/2, self.clip.h/2)
                camera.set_target(target_pos[0], target_pos[1], ZOOM_LEVEL)
            else:
                camera.set_target(self.clip.w / 2, self.clip.h / 2, 1.0)
            
            camera.update()
            processed_frames.append(camera.process_frame(frame))
            
            if i % 5 == 0:
                self.progress['value'] = i + 1
                self.progress_label.config(text=f"Rendering Frame {i+1}/{total_frames}")

        self.progress_label.config(text="Saving video file... This may take a while.")
        final_clip = ImageSequenceClip(processed_frames, fps=self.clip.fps)
        final_clip.write_videofile(FINAL_VIDEO_FILE, codec="libx264", logger='bar')

        messagebox.showinfo("Success!", f"Render complete! Video saved as {FINAL_VIDEO_FILE}")
        self.set_ui_state(tk.NORMAL)
        self.progress['value'] = 0
        self.progress_label.config(text="Ready")

def main():
    try:
        clip = VideoFileClip(RAW_VIDEO_FILE)
        with open(METADATA_FILE, 'r') as f:
            metadata = json.load(f)
    except Exception as e:
        messagebox.showerror("Error", f"Could not load project files: {e}\nPlease run 'recorder.py' first.")
        return
    
    app = EditorApp(clip, metadata)
    app.mainloop()

if __name__ == "__main__":
    main()