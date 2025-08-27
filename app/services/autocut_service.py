import os
import tempfile
import json
from typing import List, Dict
from pydub import AudioSegment
import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
from fastapi import HTTPException, status

from app.services.firebase_client import FirebaseClient
from app.services.model_client import GeminiModelClient
from app.utils.ffmpeg_tools import get_video_duration # To get video duration for filtering cuts

class AutoCut:
    def __init__(self, firebase_client: FirebaseClient, gemini_model_client: GeminiModelClient):
        self.firebase_client = firebase_client
        self.gemini_model_client = gemini_model_client

    async def analyze_song(self, user_id: str, project_id: str, file_name: str) -> List[Dict]:
        music_path_in_storage = f"MusicFiles/{user_id}/{project_id}/{file_name}"
        bucket = self.firebase_client.get_bucket()
        blob = bucket.blob(music_path_in_storage)

        if not blob.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Music file not found in storage: {music_path_in_storage}")

        with tempfile.TemporaryDirectory() as temp_dir:
            local_music_path = os.path.join(temp_dir, file_name)
            local_wav_path = os.path.join(temp_dir, "audio.wav")
            
            blob.download_to_filename(local_music_path)
            print(f"Downloaded {file_name} to {local_music_path}")

            # Convert to WAV if needed using pydub
            audio = AudioSegment.from_file(local_music_path)
            audio.export(local_wav_path, format="wav")
            print(f"Converted {file_name} to WAV at {local_wav_path}")

            # Generate mel spectrogram
            y, sr = librosa.load(local_wav_path)
            
            # Ensure the spectrogram image is generated without displaying it
            plt.figure(figsize=(10, 4), dpi=100) # Smaller figure size for faster processing
            librosa.display.specshow(librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=sr), ref=np.max),
                                     sr=sr, x_axis='time', y_axis='mel')
            plt.colorbar(format='%+2.0f dB')
            plt.title('Mel-frequency spectrogram')
            plt.tight_layout()
            
            spectrogram_path = os.path.join(temp_dir, "spectrogram.png")
            plt.savefig(spectrogram_path, bbox_inches='tight', pad_inches=0)
            plt.close() # Close the plot to free memory
            print(f"Generated spectrogram at {spectrogram_path}")

            with open(spectrogram_path, "rb") as f:
                spectrogram_bytes = f.read()
            
            music_cuts_raw = self.gemini_model_client.analyze_spectrogram_to_json(spectrogram_bytes)
            print(f"Gemini returned raw music cuts: {music_cuts_raw}")

            # Fetch fullDescription for video context
            project_ref = self.firebase_client.db_ref().child("projects").child(user_id).child(project_id)
            project_data = project_ref.get()
            if not project_data or "fullDescription" not in project_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} or its fullDescription not found for AutoCut sync.")
            full_description = project_data["fullDescription"]

            # Second Gemini call to sync video to music beats
            synchronized_cuts = self.gemini_model_client.sync_video_to_music_beats(music_cuts_raw, full_description)
            print(f"Gemini returned synchronized video cuts: {synchronized_cuts}")

            # Get video duration for filtering
            project_video_path_in_storage = f"projects/{user_id}/{project_id}/full.mp4"
            project_video_blob = bucket.blob(project_video_path_in_storage)
            
            video_duration = 0.0
            if project_video_blob.exists():
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video_file:
                    temp_video_path = temp_video_file.name
                project_video_blob.download_to_filename(temp_video_path)
                video_duration = get_video_duration(temp_video_path)
                os.remove(temp_video_path)
            else:
                print(f"Warning: Project video {project_video_path_in_storage} not found, cannot filter synchronized cuts by video duration.")

            filtered_cuts = []
            for cut in synchronized_cuts:
                if isinstance(cut, dict) and "time" in cut and "reason" in cut:
                    try:
                        cut_time = float(cut["time"])
                        if cut_time >= 0 and (video_duration == 0 or cut_time <= video_duration):
                            filtered_cuts.append({"time": cut_time, "reason": str(cut["reason"])})
                        else:
                            print(f"Filtered out synchronized cut at {cut_time}s (outside video duration {video_duration}s).")
                    except ValueError:
                        print(f"Skipping invalid synchronized cut time: {cut['time']}")
                else:
                    print(f"Skipping malformed synchronized cut entry: {cut}")
            
            return filtered_cuts
