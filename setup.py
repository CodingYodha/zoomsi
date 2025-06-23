#!/usr/bin/env python3
"""
Setup script for the AI Screen Recorder project.
This script helps install dependencies and check the environment.
"""

import subprocess
import sys
import os

def install_package(package):
    """Install a package using pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        return False

def check_package(package):
    """Check if a package is installed"""
    try:
        __import__(package)
        return True
    except ImportError:
        return False

def main():
    print("🎬 AI Screen Recorder Setup")
    print("=" * 40)
    
    # List of required packages with their import names
    packages = [
        ("opencv-python", "cv2"),
        ("dxcam", "dxcam"),
        ("pynput", "pynput"),
        ("moviepy", "moviepy"),
        ("Pillow", "PIL"),
        ("numpy", "numpy")
    ]
    
    missing_packages = []
    
    print("Checking dependencies...")
    for pip_name, import_name in packages:
        if check_package(import_name):
            print(f"✅ {pip_name} - OK")
        else:
            print(f"❌ {pip_name} - Missing")
            missing_packages.append(pip_name)
    
    if missing_packages:
        print(f"\n📦 Installing {len(missing_packages)} missing packages...")
        for package in missing_packages:
            print(f"Installing {package}...")
            if install_package(package):
                print(f"✅ {package} installed successfully")
            else:
                print(f"❌ Failed to install {package}")
                print("Please try installing manually:")
                print(f"pip install {package}")
    else:
        print("\n🎉 All dependencies are already installed!")
    
    print("\n" + "=" * 40)
    print("Setup complete!")
    print("\nTo use the application:")
    print("1. Run 'python main_app.py' to start recording")
    print("2. Run 'python editor.py' to edit your recordings")
    
    # Check if we're on Windows (required for dxcam)
    if os.name != 'nt':
        print("\n⚠️  WARNING: This application is designed for Windows.")
        print("DXCam requires DirectX which is only available on Windows.")

if __name__ == "__main__":
    main()