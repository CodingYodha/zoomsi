# recorder.py

import cv2
import dxcam
import json
import time
import threading
from pynput import mouse, keyboard

# --- Configuration ---
FPS = 30
OUTPUT_VIDEO_FILE = "raw_recording.mp4"
OUTPUT_METADATA_FILE = "mouse_metadata.json"

# --- Global State ---
is_recording = False
mouse_events = []

def get_screen_resolution():
    """Gets the primary screen resolution using a temporary DXCAM instance."""
    try:
        temp_cam = dxcam.create()
        if temp_cam:
            width, height = temp_cam.get_resolution()
            del temp_cam
            return width, height
    except Exception as e:
        print(f"Could not initialize DXCAM to get resolution: {e}")
    # Fallback resolution if DXCAM fails
    return 1920, 1080

# Set screen resolution dynamically
SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_resolution()
print(f"Using screen resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")


class MouseLogger:
    """A class to listen for and record mouse events in a separate thread."""
    def __init__(self):
        self.recording_start_time = None
        self._listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click
        )

    def _on_move(self, x, y):
        if is_recording and self.recording_start_time is not None:
            elapsed_time = time.time() - self.recording_start_time
            mouse_events.append({'time': elapsed_time, 'type': 'move', 'x': x, 'y': y})

    def _on_click(self, x, y, button, pressed):
        if is_recording and self.recording_start_time is not None:
            event_type = 'click_press' if pressed else 'click_release'
            elapsed_time = time.time() - self.recording_start_time
            mouse_events.append({'time': elapsed_time, 'type': event_type, 'x': x, 'y': y, 'button': str(button)})

    def start(self):
        print("Starting mouse listener...")
        self.recording_start_time = time.time()
        self._listener.start()

    def stop(self):
        print("Stopping mouse listener...")
        if self._listener.is_alive():
            self._listener.stop()

def record_screen(camera, video_writer):
    """The main screen recording loop."""
    global is_recording
    frame_time = 1.0 / FPS
    print("Screen recording started. Press 'ESC' to stop.")
    
    while is_recording:
        start_time = time.time()
        frame = camera.get_latest_frame()
        if frame is not None:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            video_writer.write(frame_bgr)
        
        elapsed = time.time() - start_time
        sleep_time = frame_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    print("Screen recording loop finished.")

def on_press(key):
    """Keyboard listener callback to stop recording."""
    global is_recording
    if key == keyboard.Key.esc:
        print("Escape key pressed. Stopping recording...")
        is_recording = False
        return False # Stops the keyboard listener

def main():
    global is_recording
    
    camera = dxcam.create(output_color="BGRA")
    if not camera:
        print("Failed to create DXCAM instance. Check if your DirectX/graphics drivers are okay.")
        return

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(OUTPUT_VIDEO_FILE, fourcc, FPS, (SCREEN_WIDTH, SCREEN_HEIGHT))

    mouse_logger = MouseLogger()
    keyboard_listener = keyboard.Listener(on_press=on_press)

    is_recording = True
    
    recording_thread = threading.Thread(target=record_screen, args=(camera, video_writer))
    
    recording_thread.start()
    mouse_logger.start()
    keyboard_listener.start() # This is a blocking call
    
    keyboard_listener.join()
    recording_thread.join()
    mouse_logger.stop()

    print("Releasing resources...")
    camera.stop()
    video_writer.release()

    with open(OUTPUT_METADATA_FILE, 'w') as f:
        json.dump(mouse_events, f, indent=4)
        
    print(f"\n✅ Recording saved successfully!")
    print(f"   Video file: {OUTPUT_VIDEO_FILE}")
    print(f"   Metadata file: {OUTPUT_METADATA_FILE}")
    print("\nNext step: Run 'editor.py' to process the video.")


if __name__ == "__main__":
    main()