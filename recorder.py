# recorder.py

import cv2
import dxcam
import json
import time
import threading
from pynput import mouse

class ScreenRecorder:
    """A robust, thread-safe screen recorder."""
    def __init__(self, video_file, metadata_file, fps=30):
        self.video_file = video_file
        self.metadata_file = metadata_file
        self.fps = fps
        
        # State
        self.is_recording = False
        self.is_paused = False
        self.start_time = 0

        # Threading control
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set() # Set means not paused
        self._write_lock = threading.Lock()  # Protect video writer access

        # Resources
        self.camera = None
        self.video_writer = None
        self.mouse_listener = None
        self.mouse_events = []
        self._threads = []

    def _get_screen_resolution(self):
        """Gets screen resolution using dxcam correctly."""
        try:
            # Create temporary camera instance to get resolution
            temp_cam = dxcam.create()
            if temp_cam:
                width, height = temp_cam.width, temp_cam.height
                del temp_cam
                return (width, height)
        except Exception as e:
            print(f"DXCam resolution check failed: {e}. Falling back to 1920x1080.")
        return (1920, 1080)

    def _record_screen_thread(self):
        """Thread target for capturing the screen with DXCam."""
        frame_time = 1.0 / self.fps
        print("Screen recording thread started")
        
        try:
            while not self._stop_event.is_set():
                # Check if we should pause - but with shorter timeout
                if not self._pause_event.is_set():
                    # We're paused, check stop event more frequently
                    if self._stop_event.wait(timeout=0.1):
                        break
                    continue
                
                start = time.time()
                
                try:
                    frame = self.camera.get_latest_frame()
                    if frame is not None:
                        with self._write_lock:
                            if self.video_writer and self.video_writer.isOpened():
                                bgr_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                                self.video_writer.write(bgr_frame)
                except Exception as e:
                    print(f"Frame capture error: {e}")
                    break
                
                # Maintain frame rate with responsive stop checking
                elapsed = time.time() - start
                sleep_time = frame_time - elapsed
                if sleep_time > 0:
                    # Break sleep into smaller chunks to be more responsive
                    chunks = max(1, int(sleep_time / 0.01))  # 10ms chunks
                    chunk_time = sleep_time / chunks
                    for _ in range(chunks):
                        if self._stop_event.is_set():
                            break
                        time.sleep(chunk_time)
                        
        except Exception as e:
            print(f"Screen recording thread error: {e}")
        finally:
            # Ensure video writer is flushed from this thread
            with self._write_lock:
                if self.video_writer and self.video_writer.isOpened():
                    try:
                        print("Flushing video writer...")
                        self.video_writer.release()
                    except Exception as e:
                        print(f"Error flushing video writer: {e}")
                    finally:
                        self.video_writer = None
            print("Screen recording thread finished")

    def _mouse_listener_thread(self):
        """Thread target for capturing mouse events with pynput."""
        print("Mouse listener thread started")
        
        def on_event(event_type, x, y, button=None, pressed=None):
            if self.is_recording and not self.is_paused and not self._stop_event.is_set():
                elapsed = time.time() - self.start_time
                self.mouse_events.append({
                    'time': elapsed, 'type': event_type, 
                    'x': int(x), 'y': int(y), 
                    'button': str(button) if button else None
                })

        def on_move(x, y): 
            on_event('move', x, y)
            
        def on_click(x, y, button, pressed): 
            on_event('click_press' if pressed else 'click_release', x, y, button)
        
        try:
            with mouse.Listener(on_move=on_move, on_click=on_click) as listener:
                self.mouse_listener = listener
                # Keep listener running until stop is requested
                while not self._stop_event.is_set():
                    if not listener.running:
                        break
                    time.sleep(0.1)
        except Exception as e:
            print(f"Mouse listener error: {e}")
        finally:
            print("Mouse listener thread finished")

    def start(self):
        """Initializes resources and starts all recording threads."""
        if self.is_recording: 
            print("Already recording")
            return False
            
        try:
            print("Initializing recording...")
            width, height = self._get_screen_resolution()
            
            # Initialize camera
            self.camera = dxcam.create(output_color="BGRA")
            if not self.camera:
                raise Exception("Failed to create DXCam instance")
            
            # Initialize video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(self.video_file, fourcc, self.fps, (width, height))

            if not self.video_writer.isOpened():
                raise IOError("Could not open video writer. Check permissions or codecs.")

            # Reset state
            self.is_recording = True
            self.is_paused = False
            self.start_time = time.time()
            self.mouse_events = []
            self._stop_event.clear()
            self._pause_event.set()

            # Start threads
            self._threads = [
                threading.Thread(target=self._record_screen_thread, daemon=False),
                threading.Thread(target=self._mouse_listener_thread, daemon=False)
            ]
            
            for t in self._threads:
                t.start()
            
            print("Recording started successfully.")
            return True
            
        except Exception as e:
            print(f"ERROR starting recording: {e}")
            self._cleanup_resources()
            self.is_recording = False
            return False

    def stop(self):
        """Signals all threads to stop, waits for them, and cleans up resources."""
        if not self.is_recording: 
            print("Not currently recording")
            return False
        
        print("Stopping recording...")
        
        # Signal all threads to stop
        self._stop_event.set()
        
        # If paused, resume to let threads exit cleanly
        if self.is_paused:
            self._pause_event.set()
            self.is_paused = False
        
        # Stop mouse listener explicitly
        if self.mouse_listener:
            try:
                self.mouse_listener.stop()
            except:
                pass
        
        # Wait for threads to finish with timeout
        print("Waiting for threads to finish...")
        for i, t in enumerate(self._threads):
            print(f"Waiting for thread {i+1}...")
            t.join(timeout=3.0)  # Reduced to 3 seconds since we're more responsive
            if t.is_alive():
                print(f"Warning: Thread {i+1} did not finish cleanly")
        
        # Additional cleanup - ensure video writer is closed
        print("Finalizing video file...")
        with self._write_lock:
            if self.video_writer is not None:
                print("Video writer cleanup in main thread")
                try:
                    if self.video_writer.isOpened():
                        self.video_writer.release()
                except Exception as e:
                    print(f"Error in final video writer cleanup: {e}")
                finally:
                    self.video_writer = None
        
        # Clean up camera
        if self.camera:
            try:
                self.camera.stop()
                print("Camera stopped successfully")
            except Exception as e:
                print(f"Error stopping camera: {e}")
            finally:
                self.camera = None
        
        # Save metadata
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.mouse_events, f, indent=4)
            print(f"Metadata saved to {self.metadata_file}")
        except Exception as e:
            print(f"Error saving metadata: {e}")
        
        # Reset state
        self.is_recording = False
        self.is_paused = False
        self.mouse_events = []
        self._threads = []
        self.mouse_listener = None
        
        print("Recording stopped and all files saved.")
        return True

    def _cleanup_resources(self):
        """Safely releases camera and video writer."""
        with self._write_lock:
            if self.video_writer:
                try:
                    self.video_writer.release()
                except:
                    pass
                self.video_writer = None
                
        if self.camera:
            try:
                self.camera.stop()
            except:
                pass
            self.camera = None

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