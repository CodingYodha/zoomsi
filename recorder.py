# recorder.py

import cv2
import dxcam
import json
import time
import threading
from pynput import mouse  # Missing import fixed

class ScreenRecorder:
    def __init__(self, video_file, metadata_file, fps=30):
        self.video_file = video_file
        self.metadata_file = metadata_file
        self.fps = fps
        
        # State management
        self.is_recording = False
        self.is_paused = False
        
        # Threading events
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Initially not paused

        # Resources to be managed
        self.camera = None
        self.video_writer = None
        self.mouse_listener = None
        self.mouse_events = []
        self._threads = []
        self.start_time = None

    def _get_screen_resolution(self):
        try:
            import tkinter as tk
            root = tk.Tk()
            width = root.winfo_screenwidth()
            height = root.winfo_screenheight()
            root.destroy()
            return (width, height)
        except Exception as e:
            print(f"Warning: Could not get screen resolution: {e}")
            return (1920, 1080)  # Fallback

    def _record_screen_thread(self):
        frame_time = 1.0 / self.fps
        consecutive_none_frames = 0
        max_none_frames = 30  # Allow up to 1 second of None frames
        
        while not self._stop_event.is_set():
            try:
                self._pause_event.wait()  # This will block if paused
                if self._stop_event.is_set():
                    break
                
                start_time = time.time()
                frame = self.camera.get_latest_frame()
                
                if frame is not None:
                    consecutive_none_frames = 0
                    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    self.video_writer.write(bgr_frame)
                else:
                    consecutive_none_frames += 1
                    if consecutive_none_frames > max_none_frames:
                        print("Warning: Too many consecutive None frames, continuing...")
                        consecutive_none_frames = 0
                
                elapsed = time.time() - start_time
                sleep_time = frame_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                print(f"Error in screen recording thread: {e}")
                if self._stop_event.is_set():
                    break

    def _mouse_listener_thread(self):
        def on_move(x, y):
            if self.is_recording and not self.is_paused and self.start_time:
                try:
                    elapsed = time.time() - self.start_time
                    self.mouse_events.append({
                        'time': elapsed, 
                        'type': 'move', 
                        'x': x, 
                        'y': y
                    })
                except Exception as e:
                    print(f"Error recording mouse move: {e}")

        def on_click(x, y, button, pressed):
            if self.is_recording and not self.is_paused and self.start_time:
                try:
                    event_type = 'click_press' if pressed else 'click_release'
                    elapsed = time.time() - self.start_time
                    self.mouse_events.append({
                        'time': elapsed, 
                        'type': event_type, 
                        'x': x, 
                        'y': y, 
                        'button': str(button)
                    })
                except Exception as e:
                    print(f"Error recording mouse click: {e}")

        try:
            self.mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click)
            self.mouse_listener.start()
            self.mouse_listener.join()
        except Exception as e:
            print(f"Error in mouse listener thread: {e}")

    def start(self):
        if self.is_recording:
            print("Already recording!")
            return False
        
        try:
            self.is_recording = True
            self.is_paused = False
            self._stop_event.clear()
            self._pause_event.set()
            self.mouse_events = []
            self.start_time = time.time()

            # Get screen resolution and create camera
            width, height = self._get_screen_resolution()
            self.camera = dxcam.create(output_color="BGRA")
            if self.camera is None:
                raise Exception("Failed to create DXCam instance")

            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(self.video_file, fourcc, self.fps, (width, height))
            if not self.video_writer.isOpened():
                raise Exception("Failed to create video writer")
            
            # Start threads
            screen_thread = threading.Thread(target=self._record_screen_thread, daemon=True)
            mouse_thread = threading.Thread(target=self._mouse_listener_thread, daemon=True)
            
            self._threads = [screen_thread, mouse_thread]
            for t in self._threads:
                t.start()
            
            print("Recording started successfully.")
            return True
            
        except Exception as e:
            print(f"Error starting recording: {e}")
            self._cleanup_resources()
            self.is_recording = False
            return False

    def stop(self):
        if not self.is_recording:
            print("Not currently recording!")
            return False

        try:
            print("Stopping recording...")
            self._stop_event.set()
            
            # If paused, unpause to allow threads to exit
            if self.is_paused:
                self.resume()
            
            # Stop the mouse listener gracefully
            if self.mouse_listener:
                self.mouse_listener.stop()

            # Wait for threads to finish
            for t in self._threads:
                if t.is_alive():
                    t.join(timeout=5.0)  # 5 second timeout
                    if t.is_alive():
                        print(f"Warning: Thread {t.name} did not finish cleanly")

            # Clean up resources
            self._cleanup_resources()
            
            # Save mouse events
            try:
                with open(self.metadata_file, 'w') as f:
                    json.dump(self.mouse_events, f, indent=4)
                print(f"Mouse metadata saved to {self.metadata_file}")
            except Exception as e:
                print(f"Error saving metadata: {e}")
                return False
            
            self.is_recording = False
            self._threads = []
            print("Recording stopped and saved successfully.")
            return True
            
        except Exception as e:
            print(f"Error stopping recording: {e}")
            return False

    def _cleanup_resources(self):
        """Safely clean up all resources"""
        try:
            if self.camera:
                self.camera.stop()
                self.camera = None
        except Exception as e:
            print(f"Error stopping camera: {e}")
        
        try:
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
        except Exception as e:
            print(f"Error releasing video writer: {e}")

    def pause(self):
        if self.is_recording and not self.is_paused:
            self.is_paused = True
            self._pause_event.clear()
            print("Recording paused.")
            return True
        return False
            
    def resume(self):
        if self.is_recording and self.is_paused:
            self.is_paused = False
            self._pause_event.set()
            print("Recording resumed.")
            return True
        return False