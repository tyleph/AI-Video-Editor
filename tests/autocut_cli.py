import argparse
import requests
import json
import os
from typing import List, Tuple, Optional

# Assuming the FastAPI app is running locally at this URL
BASE_URL = "http://127.0.0.1:8000"

def analyze_song_cli(user_id: str, project_id: str, file_name: str, render_output: Optional[str] = None):
    print(f"Analyzing song '{file_name}' for User: {user_id}, Project: {project_id}")

    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "file_name": file_name
    }

    try:
        response = requests.post(f"{BASE_URL}/autocut/analyze-song", json=payload)
        response.raise_for_status() # Raise an exception for HTTP errors
        cuts = response.json()
        
        if cuts:
            print("\n--- AutoCut Analysis Results ---")
            segments_to_keep = []
            # For AutoCut, we'll define each segment to start at cut.time and last for a fixed duration (e.g., 3 seconds)
            # This is a minimal implementation; more advanced logic would be needed for true music-video sync.
            segment_duration = 3.0 
            for i, cut in enumerate(cuts):
                print(f"Cut {i+1}: Time={cut['time']:.2f}s, Reason='{cut['reason']}'")
                segments_to_keep.append((cut['time'], cut['time'] + segment_duration))
            print("--------------------------------")

            if render_output:
                print(f"\nRendering AutoCut video to local file: {render_output}")
                render_payload = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "segments_to_keep": segments_to_keep,
                    "audio_file_name": file_name  # Add this line
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
            print("No cuts generated or found for this song.")

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
    parser = argparse.ArgumentParser(description="AutoCut CLI tester for AI Video Editor Backend.")
    parser.add_argument("--user-id", required=True, help="The user ID associated with the music file.")
    parser.add_argument("--project-id", required=True, help="The project ID associated with the music file.")
    parser.add_argument("--file-name", required=True, help="The filename of the music file in Firebase Storage (e.g., 'my_song.mp3').")
    parser.add_argument("--render-output", type=str, help="Optional local path to save the rendered AutoCut video.")
    args = parser.parse_args()

    analyze_song_cli(args.user_id, args.project_id, args.file_name, args.render_output)

if __name__ == "__main__":
    main()
