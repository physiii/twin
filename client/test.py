#!/usr/bin/env python3
"""
Simple RTSP service test - works for any user
"""
import os
import subprocess
import sys
import shutil

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

def main():
    """Main test function"""
    print("=== RTSP Service Quick Test ===")
    
    # Setup test directory
    user = os.getenv('USER', 'user')
    test_dir = f"/tmp/rtsp_test_{user}"
    cleanup_needed = False
    
    try:
        # Test 1: Check service status
        print("1. Checking service status...")
        success, stdout, stderr = run_command("systemctl is-active rtsp-server.service")
        if success and "active" in stdout:
            print("   ✓ RTSP service is running")
        else:
            print("   ✗ RTSP service is not running")
            return False
        
        # Test 2: Probe RTSP stream
        print("2. Testing RTSP stream...")
        cmd = 'ffprobe -v error -rtsp_transport tcp -select_streams a:0 -show_streams "rtsp://127.0.0.1:554/mic"'
        success, stdout, stderr = run_command(cmd)
        if success and "codec_name=aac" in stdout:
            print("   ✓ RTSP stream is accessible and contains AAC audio")
        else:
            print("   ✗ RTSP stream test failed")
            print(f"   Error: {stderr}")
            return False
        
        # Test 3: Quick recording test
        print("3. Testing recording capability...")
        os.makedirs(test_dir, exist_ok=True)
        cleanup_needed = True
        output_file = f"{test_dir}/quick_test.aac"
        
        cmd = f'ffmpeg -hide_banner -loglevel error -rtsp_transport tcp -t 2 -i "rtsp://127.0.0.1:554/mic" -vn -acodec copy "{output_file}" -y'
        success, stdout, stderr = run_command(cmd, timeout=10)
        
        if success and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            if file_size > 500:  # Expect at least 500 bytes for 2 seconds
                print(f"   ✓ Recording successful ({file_size} bytes)")
            else:
                print("   ✗ Recording file too small")
                return False
        else:
            print("   ✗ Recording failed")
            print(f"   Error: {stderr}")
            return False
        
        print("\n🎉 ALL TESTS PASSED - RTSP service is working!")
        return True
        
    finally:
        # Cleanup test files
        if cleanup_needed:
            print("\n4. Cleaning up test files...")
            try:
                if os.path.exists(test_dir):
                    shutil.rmtree(test_dir)
                    print("   ✓ Test files cleaned up")
            except Exception as e:
                print(f"   ⚠ Warning: Could not clean up test files: {e}")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
