import argparse
import requests
import json
import os
from typing import List, Tuple, Optional

from tests.timecode import hhmmss_to_seconds # Import from utils

# Assuming the FastAPI app is running locally at this URL
BASE_URL = "http://127.0.0.1:8000"

def generate_highlights_cli(user_id: str, project_id: str, scene_interval: int = 12, user_prompt: Optional[str] = None, render_output: Optional[str] = None):
    print(f"Generating highlights for User: {user_id}, Project: {project_id} with scene interval: {scene_interval}s")
    if user_prompt:
        print(f"Using prompt: '{user_prompt}'")

    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "scene_interval": scene_interval,
        "user_prompt": user_prompt
    }

    try:
        response = requests.post(f"{BASE_URL}/highlights/generate", json=payload)
        response.raise_for_status() # Raise an exception for HTTP errors
        highlights_data = response.json()
        
        if highlights_data and highlights_data.get("highlights"):
            print("\n--- Highlights Reel Results ---")
            print(f"Total Scenes: {highlights_data['total_scenes']}")
            print(f"Generated At: {highlights_data['generated_at']}")
            
            segments_to_keep = []
            for i, highlight in enumerate(highlights_data['highlights']):
                print(f"Scene {i+1}: ID={highlight['scene_id']}, Start={highlight['start_timestamp']}, End={highlight['end_timestamp']}, Description='{highlight['description']}'")
                segments_to_keep.append((hhmmss_to_seconds(highlight['start_timestamp']), hhmmss_to_seconds(highlight['end_timestamp'])))
            print("-------------------------------")

            if render_output:
                print(f"\nRendering highlights to local file: {render_output}")
                render_payload = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "segments_to_keep": segments_to_keep
                }
                render_response = requests.post(f"{BASE_URL}/rendervideo", json=render_payload)
                render_response.raise_for_status()
                render_data = render_response.json()
                
                if render_data and render_data.get("output_filename"):
                    rendered_video_path_in_storage = render_data["output_filename"]
                    
                    # Download the rendered video locally using the debug endpoint
                    download_url = f"{BASE_URL}/debug/download-file?path={rendered_video_path_in_storage}"
                    print(f"Attempting to download from: {download_url}")
                    download_response = requests.get(download_url, stream=True)
                    download_response.raise_for_status()

                    with open(render_output, 'wb') as f:
                        for chunk in download_response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"Downloaded rendered video to {render_output}")
                else:
                    print("Failed to get rendered video path from backend.")

        else:
            print("No highlights generated or found for this project.")

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with the backend: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
    except json.JSONDecodeError:
        print("Error: Could not decode JSON response from the server.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def main():
    parser = argparse.ArgumentParser(description="HighlightsReelGen CLI tester for AI Video Editor Backend.")
    parser.add_argument("--user-id", required=True, help="The user ID for the project.")
    parser.add_argument("--project-id", required=True, help="The project ID for which to generate highlights.")
    parser.add_argument("--scene-interval", type=int, default=12, help="Optional scene interval in seconds (default: 12).")
    parser.add_argument("--prompt", type=str, help="Optional user prompt to guide highlight generation (e.g., 'sports highlights').")
    parser.add_argument("--render-output", type=str, help="Optional local path to save the rendered highlights video.")
    args = parser.parse_args()

    generate_highlights_cli(args.user_id, args.project_id, args.scene_interval, args.prompt, args.render_output)

if __name__ == "__main__":
    main()
