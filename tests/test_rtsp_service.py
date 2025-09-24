#!/usr/bin/env python3
"""
Test script to validate RTSP audio service functionality
This test connects to the RTSP service and validates it's working correctly
"""
import os
import subprocess
import sys
import time
from pathlib import Path

# Configuration
RTSP_URL = "rtsp://127.0.0.1:554/mic"
OUTPUT_DIR = f"/tmp/twin_test_{os.getenv('USER', 'user')}"
TEST_DURATION = 3  # seconds

def run_command(cmd, timeout=10):
    """Run a command and return success status and output"""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"

def test_rtsp_probe():
    """Test if RTSP stream can be probed"""
    print("1. Testing RTSP stream probe...")
    cmd = f'ffprobe -v error -rtsp_transport tcp -select_streams a:0 -show_streams "{RTSP_URL}"'
    success, stdout, stderr = run_command(cmd)
    
    if success and "codec_name=aac" in stdout:
        print("   ✓ RTSP probe: SUCCESS")
        print(f"   ✓ Stream format: AAC audio detected")
        return True
    else:
        print("   ✗ RTSP probe: FAILED")
        print(f"   Error: {stderr}")
        return False

def test_rtsp_record():
    """Test if RTSP stream can be recorded"""
    print("2. Testing RTSP stream recording...")
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = f"{OUTPUT_DIR}/rtsp_service_test.aac"
    
    cmd = f'ffmpeg -hide_banner -loglevel error -rtsp_transport tcp -t {TEST_DURATION} -i "{RTSP_URL}" -vn -acodec copy "{output_file}" -y'
    success, stdout, stderr = run_command(cmd, timeout=TEST_DURATION + 5)
    
    if success and os.path.exists(output_file):
        file_size = os.path.getsize(output_file)
        if file_size > 1000:  # Expect at least 1KB for 3 seconds of audio
            print("   ✓ RTSP recording: SUCCESS")
            print(f"   ✓ File created: {file_size} bytes")
            return True, output_file
        else:
            print("   ✗ RTSP recording: FAILED (file too small)")
            return False, None
    else:
        print("   ✗ RTSP recording: FAILED")
        print(f"   Error: {stderr}")
        return False, None

def test_rtsp_stream_info():
    """Get detailed RTSP stream information"""
    print("3. Getting RTSP stream details...")
    cmd = f'ffprobe -v quiet -show_format -show_streams "{RTSP_URL}"'
    success, stdout, stderr = run_command(cmd)
    
    if success:
        print("   ✓ Stream information retrieved:")
        # Extract key information
        lines = stdout.split('\n')
        for line in lines:
            if any(key in line for key in ['codec_name', 'sample_rate', 'channels', 'bit_rate']):
                print(f"     {line}")
        return True
    else:
        print("   ✗ Could not retrieve stream information")
        return False

def test_service_status():
    """Check if RTSP service is running"""
    print("0. Checking RTSP service status...")
    cmd = "systemctl is-active rtsp-server.service"
    success, stdout, stderr = run_command(cmd)
    
    if success and "active" in stdout:
        print("   ✓ RTSP service: RUNNING")
        return True
    else:
        print("   ✗ RTSP service: NOT RUNNING")
        print("   Please start the service: sudo systemctl start rtsp-server.service")
        return False

def validate_recorded_file(file_path):
    """Validate the recorded file has proper audio content"""
    print("4. Validating recorded audio file...")
    if not file_path or not os.path.exists(file_path):
        print("   ✗ No file to validate")
        return False
    
    cmd = f'ffprobe -v quiet -show_format "{file_path}"'
    success, stdout, stderr = run_command(cmd)
    
    if success:
        # Check duration
        for line in stdout.split('\n'):
            if line.startswith('duration='):
                duration = float(line.split('=')[1])
                if 2.5 <= duration <= 3.5:  # Allow some tolerance
                    print(f"   ✓ File duration: {duration:.2f}s (expected ~{TEST_DURATION}s)")
                    return True
                else:
                    print(f"   ✗ Unexpected duration: {duration:.2f}s")
                    return False
    
    print("   ✗ Could not validate file")
    return False

def main():
    """Main test function"""
    print("=== RTSP Service Test ===")
    print(f"Testing RTSP URL: {RTSP_URL}")
    print()
    
    # Test sequence
    tests_passed = 0
    total_tests = 5
    
    # Check service status
    if test_service_status():
        tests_passed += 1
    
    print()
    
    # Test RTSP probe
    if test_rtsp_probe():
        tests_passed += 1
    
    print()
    
    # Test RTSP recording
    record_success, output_file = test_rtsp_record()
    if record_success:
        tests_passed += 1
    
    print()
    
    # Get stream info
    if test_rtsp_stream_info():
        tests_passed += 1
    
    print()
    
    # Validate recorded file
    if validate_recorded_file(output_file):
        tests_passed += 1
    
    print()
    print("=== TEST RESULTS ===")
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("🎉 ALL TESTS PASSED - RTSP service is working correctly!")
        if output_file:
            print(f"📁 Test recording saved to: {output_file}")
        return True
    else:
        print("❌ SOME TESTS FAILED - Please check the RTSP service configuration")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
