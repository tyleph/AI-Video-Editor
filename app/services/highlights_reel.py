import os
import tempfile
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import HTTPException, status

from app.services.firebase_client import FirebaseClient
from app.services.model_client import GeminiModelClient
from app.utils.timecode import seconds_to_hhmmss, hhmmss_to_seconds
from app.utils.ffmpeg_tools import get_video_duration


class HighlightsReelGen:
    def __init__(self, firebase_client: FirebaseClient, gemini_model_client: GeminiModelClient):
        self.firebase_client = firebase_client
        self.gemini_model_client = gemini_model_client

    async def generate_highlights(self, user_id: str, project_id: str, scene_interval: int = 12, user_prompt: Optional[str] = None) -> Dict[str, Any]:
        project_ref = self.firebase_client.db_ref().child("projects").child(user_id).child(project_id)
        project_data = project_ref.get()
        if not project_data or "fullDescription" not in project_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} or its fullDescription not found.")
        
        full_description = project_data["fullDescription"]
        
        if user_prompt:
            # Use Gemini to select and summarize highlights based on user prompt
            try:
                highlights_raw = self.gemini_model_client.select_and_summarize_highlights(full_description, scene_interval, user_prompt)
                highlights = []
                for i, h in enumerate(highlights_raw):
                    highlights.append({
                        "scene_id": i + 1,
                        "start_timestamp": h.get("start_timestamp", "00:00:00"),
                        "end_timestamp": h.get("end_timestamp", "00:00:00"),
                        "description": h.get("description", "No description.")
                    })
                total_scenes = len(highlights)
            except Exception as e:
                print(f"Error generating user-prompted highlights: {e}")
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gemini error during prompted highlights generation: {e}")
        else:
            # Fallback to existing logic if no user prompt
            full_description_lines = full_description.split('\n')
            frame_descriptions: Dict[float, str] = {} # seconds -> description
            for line in full_description_lines:
                if ": " in line:
                    timestamp_str, desc = line.split(": ", 1)
                    try:
                        seconds = hhmmss_to_seconds(timestamp_str)
                        frame_descriptions[seconds] = desc
                    except ValueError:
                        print(f"Warning: Could not parse timestamp from line: {line}")
            
            if not frame_descriptions:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No frame descriptions found for the project.")

            sorted_timestamps = sorted(frame_descriptions.keys())
            
            highlights = []
            scene_id_counter = 0
            
            if not sorted_timestamps:
                total_scenes = 0
            else:
                video_duration = sorted_timestamps[-1] if sorted_timestamps else 0
                current_scene_start_time = 0.0
                while current_scene_start_time < video_duration:
                    scene_id_counter += 1
                    scene_end_time = min(current_scene_start_time + scene_interval, video_duration)

                    scene_frames_captions = []
                    for ts in sorted_timestamps:
                        if current_scene_start_time <= ts < scene_end_time:
                            scene_frames_captions.append(f"At {seconds_to_hhmmss(ts)}: {frame_descriptions[ts]}")
                    
                    scene_summary = "No summary available for this scene."
                    if scene_frames_captions:
                        summary_prompt_lines = scene_frames_captions[:3]
                        summary_prompt = "Create a single concise sentence that summarizes this scene based on these frame descriptions:\n" + "\n".join(summary_prompt_lines)
                        try:
                            response = self.gemini_model_client.client.models.generate_content(
                                model=self.gemini_model_client.model,
                                contents=[{"role": "user", "parts": [{"text": summary_prompt}]}],
                            )
                            scene_summary = getattr(response, "output_text", None) or response.candidates[0].content.parts[0].text
                        except Exception as e:
                            print(f"Error summarizing scene {scene_id_counter}: {e}")

                    highlights.append({
                        "scene_id": scene_id_counter,
                        "start_timestamp": seconds_to_hhmmss(current_scene_start_time),
                        "end_timestamp": seconds_to_hhmmss(scene_end_time),
                        "description": scene_summary
                    })
                    
                    current_scene_start_time = scene_end_time
                total_scenes = scene_id_counter
            
        return {
            "user_id": user_id,
            "project_id": project_id,
            "highlights": highlights,
            "total_scenes": total_scenes,
            "generated_at": datetime.now().isoformat()
        }
