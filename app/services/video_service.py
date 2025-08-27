import os
import tempfile
from typing import List, Dict
from datetime import datetime
from fastapi import HTTPException, status

from app.services.firebase_client import FirebaseClient
from app.services.model_client import GeminiModelClient
from app.utils.timecode import seconds_to_hhmmss
from app.utils.sanitize import sanitize_firebase_key
from app.utils.ffmpeg_tools import sample_frames

class VideoProcessingService:
    def __init__(self, firebase_client: FirebaseClient, gemini_model_client: GeminiModelClient):
        self.firebase_client = firebase_client
        self.gemini_model_client = gemini_model_client

    async def process_video(self, user_id: str, video_filename: str) -> dict:
        video_path_in_storage = f"videos/{user_id}/{video_filename}"
        bucket = self.firebase_client.get_bucket()
        blob = bucket.blob(video_path_in_storage)

        if not blob.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Video not found in storage: {video_path_in_storage}")

        with tempfile.TemporaryDirectory() as temp_dir:
            local_video_path = os.path.join(temp_dir, video_filename)
            blob.download_to_filename(local_video_path)
            print(f"Downloaded {video_filename} to {local_video_path}")

            frames_output_dir = os.path.join(temp_dir, "frames")
            sampled_frames = sample_frames(local_video_path, frames_output_dir, interval=6)
            print(f"Sampled {len(sampled_frames)} frames.")

            frame_descriptions = {}
            captions_list = []
            caption_prompt = "Provide a very brief, precise caption of the main content in this image (max 2 sentences). Focus on key objects, actions, and context."

            for frame_path, timestamp in sampled_frames:
                try:
                    with open(frame_path, "rb") as f:
                        image_bytes = f.read()
                    caption = self.gemini_model_client.caption_image(image_bytes, caption_prompt)
                    hhmmss_timestamp = seconds_to_hhmmss(timestamp)
                    frame_descriptions[hhmmss_timestamp] = caption
                    captions_list.append(caption)
                    print(f"Caption for {hhmmss_timestamp}: {caption}")
                except Exception as e:
                    print(f"Skipping frame {frame_path} due to error: {e}")
                    # Continue processing other frames even if one fails

            summary = self.gemini_model_client.summarize_from_captions(captions_list)
            print(f"Video summary: {summary}")

            sanitized_filename = sanitize_firebase_key(video_filename)
            video_analysis_ref = self.firebase_client.db_ref().child("video_analysis").child(user_id).child(sanitized_filename)
            
            result_data = {
                "id": sanitized_filename,
                "user_id": user_id,
                "frame_descriptions": frame_descriptions,
                "summary": summary,
                "status": "completed",
                "processed_at": datetime.now().isoformat()
            }
            video_analysis_ref.set(result_data)
            print(f"Video analysis results saved to Firebase for {video_filename}")
            return result_data
