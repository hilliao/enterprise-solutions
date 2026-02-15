#!/usr/bin/env python3

# Install required packages:
# pip install opencv-python ollama

# Example usage on Linux Bash shell:
# export RTSP_URL=rtsp://username:password@server-hostname-example.com:554/stream1
# python3 analyze-videos.py -i $RTSP_URL --frame-filename images/saved_frame --model-timeout 600
# Or with virtual environment:
# ~/workspace/ml-ollama/.venv/bin/python3 ~/path/to/analyze-videos.py -i $RTSP_URL --frame-filename images/2/tpe-mucha-1 --model-timeout 600 --output ~/Documents/tw-mucha-stream_analysis.txt

import argparse
import cv2
import ollama
from datetime import datetime
import signal

# Configuration
MODEL_NAME = "minicpm-v"


class TimeoutError(Exception):
    """Custom timeout exception."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutError("Operation timed out")


def capture_frame(rtsp_url, rtsp_timeout):
    """Captures a single frame from the RTSP stream with timeout."""
    # Set RTSP timeout options
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, rtsp_timeout * 1000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, rtsp_timeout * 1000)
    
    if not cap.isOpened():
        print(f"Error: Could not connect to RTSP stream (timeout: {rtsp_timeout}s)")
        return None, None
    
    # Read a single frame
    ret, frame = cap.read()
    cap.release()  # Immediately release to avoid buffering
    
    if not ret:
        print("Error: Could not read frame from stream.")
        return None, None
    
    # Convert to bytes for Ollama
    _, buffer = cv2.imencode('.jpg', frame)
    return frame, buffer.tobytes()


def analyze_frame(frame_bytes, frame_number, prompt, model_timeout):
    """Analyzes a single frame using the Gen AI model with timeout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Analyzing frame {frame_number}...")
    
    # Set timeout alarm
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(model_timeout)
    
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [frame_bytes]
            }]
        )
        signal.alarm(0)  # Cancel the alarm
        return response['message']['content']
    
    except TimeoutError:
        signal.alarm(0)  # Cancel the alarm
        return f"[TIMEOUT] Model did not respond within {model_timeout} seconds. Skipping frame."


def main():
    parser = argparse.ArgumentParser(
        description="Analyze RTSP stream in real-time using generative AI models."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="RTSP stream URL (e.g., rtsp://username:password@server:port/stream1)"
    )
    parser.add_argument(
        "--output", "-o",
        default="stream_analysis.txt",
        help="Output file for analysis log (default: stream_analysis.txt)"
    )
    parser.add_argument(
        "--prompt", "-p",
        default=(
            "This is a picture overlooking a room in a 75+ year old woman's home. She has dementia. Your job is to monitor her activities. "
            "Describe what you see, focusing on people or any activity. Count the number of people in the room. There's often a cat. Tell what the cat is doing. "
            "If the image is black and white, it indicates night mode (low-light). Usually, there's nobody in night mode. "
            "Be verbose and note any significant details. If there are no humans detected, just say 'No humans detected without further details'."
        ),
        help="Custom prompt for the generative AI model."
    )
    parser.add_argument(
        "--rtsp-timeout",
        type=int,
        default=10,
        help="RTSP connection timeout in seconds (default: 10)"
    )
    parser.add_argument(
        "--model-timeout",
        type=int,
        default=120,
        help="AI model processing timeout in seconds (default: 120)"
    )
    parser.add_argument(
        "--frame-filename",
        default="saved_rtsp_frame",
        help="Base filename to save the current RTSP frame without extension (default: saved_rtsp_frame)"
    )
    args = parser.parse_args()

    rtsp_url = args.input
    output_file = args.output
    rtsp_timeout = args.rtsp_timeout
    model_timeout = args.model_timeout
    
    print(f"Starting real-time analysis of RTSP stream...")
    print(f"Stream URL: {rtsp_url}")
    print(f"Output file: {output_file}")
    print(f"RTSP timeout: {rtsp_timeout} seconds")
    print(f"Model timeout: {model_timeout} seconds ({model_timeout // 60} minutes {model_timeout % 60} seconds)")
    print("-" * 60)
    print("Press Ctrl+C to stop.\n")
    
    frame_number = 0
    timeout_count = 0
    
    try:
        with open(output_file, "a") as f:
            while True:
                frame_number += 1
                
                # Step 1: Capture a single frame with timeout
                try:
                    frame, frame_bytes = capture_frame(rtsp_url, rtsp_timeout)
                except Exception as e:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error_msg = f"[{timestamp}] Frame {frame_number}: RTSP capture error - {e}\n"
                    print(error_msg)
                    f.write(error_msg)
                    f.flush()
                    continue
                
                if frame_bytes is None or frame is None:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error_msg = f"[{timestamp}] Frame {frame_number}: Failed to capture frame, skipping...\n"
                    print(error_msg)
                    f.write(error_msg)
                    f.flush()
                    continue
                
                # Save the frame to disk
                frame_filename = f"{args.frame_filename}_{frame_number}.png"
                cv2.imwrite(frame_filename, frame)
                
                # Step 2: Analyze the frame with Gen AI (with timeout)
                analysis = analyze_frame(frame_bytes, frame_number, args.prompt, model_timeout)
                
                # Track timeouts
                if "[TIMEOUT]" in analysis:
                    timeout_count += 1
                    print(f"  (Total timeouts: {timeout_count})")
                
                # Step 3: Summarize and log
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = f"[{timestamp}] Frame {frame_number}:\n{analysis}\n"
                log_entry += "-" * 40 + "\n"
                
                print(log_entry)
                f.write(log_entry)
                f.flush()  # Ensure immediate write to file
                
                # Step 4: Loop back to capture next real-time frame
                # No buffering - the next frame captured will be the current live frame
                
    except KeyboardInterrupt:
        print(f"\n\nStopped. Analyzed {frame_number} frames.")
        print(f"Total timeouts: {timeout_count}")
        print(f"Analysis saved to {output_file}")


if __name__ == "__main__":
    main()
