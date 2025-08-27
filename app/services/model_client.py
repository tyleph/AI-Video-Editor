import os
import json
from typing import List, Dict
from dotenv import load_dotenv
from google import genai

load_dotenv()

class GeminiModelClient:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash-lite"

    def caption_image(self, image_bytes: bytes, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model = self.model,
                contents=[
                    {"role": "user", "parts": [
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
                        {"text": prompt}
                    ]}
                ]

            )
            return getattr(response, "output_text", None) or response.candidates[0].content.parts[0].text
        except Exception as e:
            print(f"Error captioning image with Gemini: {e}")
            raise

    def summarize_from_captions(self, captions: List[str]) -> str:
        try:
            prompt = "Write a concise summary of the video using only these image captions. No meta-commentary. Just the summary:\n- " + "\n- ".join(captions)
            response = self.client.models.generate_content(
                model=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
            )
            return getattr(response, "output_text", None) or response.candidates[0].content.parts[0].text
        except Exception as e:
            print(f"Error summarizing from captions with Gemini: {e}")
            raise

    def analyze_spectrogram_to_json(self, image_bytes: bytes) -> List[Dict]:
        try:
            prompt = (
                "Analyze the spectrogram image and return ONLY a valid JSON array with objects of the form "
                '{ "time": number (seconds), "reason": string }. Do not include any text outside the JSON array.'
            )
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    {"role": "user", "parts": [
                        {"inline_data": {"mime_type": "image/png", "data": image_bytes}},
                        {"text": prompt}
                    ]}
                ]
            )

            # Attempt to parse JSON, handling potential extra text
            response_text = getattr(response, "output_text", None) or response.candidates[0].content.parts[0].text
            text_content = response_text.strip()
            if text_content.startswith('```json'):
                text_content = text_content[7:]
            if text_content.endswith('```'):
                text_content = text_content[:-3]
            
            # Fallback for strict JSON parsing if SDK doesn't support JSON mode directly
            try:
                return json.loads(text_content)
            except json.JSONDecodeError:
                # Attempt simple bracket extraction retry
                start_idx = text_content.find('[')
                end_idx = text_content.rfind(']')
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    json_str = text_content[start_idx : end_idx + 1]
                    return json.loads(json_str)
                else:
                    raise ValueError("Failed to extract valid JSON from Gemini response.")

        except Exception as e:
            print(f"Error analyzing spectrogram with Gemini: {e}")
            raise

    def sync_video_to_music_beats(self, music_cuts: List[Dict], full_description: str) -> List[Dict]:
        try:
            music_cut_info = "\n".join([f"- Music Beat at {cut['time']:.2f}s (Reason: {cut['reason']})" for cut in music_cuts])
            
            prompt = (
                "Given the following music beat information and video frame descriptions, "
                "suggest optimal video segments (start and end times in seconds) that would synchronize well with the music beats. "
                "Focus on aligning video scene changes or significant events with the music. "
                "Return ONLY a valid JSON array of objects, where each object has 'time' (float, start of video segment in seconds) "
                "and 'reason' (string, why this segment was chosen/synced). "
                "Do not include any text outside the JSON array.\n\n"
                "Music Beats:\n"
                f"{music_cut_info}\n\n"
                "Video Frame Descriptions (HH:MM:SS: description):\n"
                f"{full_description}\n\n"
                "Suggested Video Cuts (JSON array):"
            )
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}]
            )
            text_content = (getattr(response, "output_text", None) or response.candidates[0].content.parts[0].text).strip()
            if text_content.startswith('```json'):
                text_content = text_content[7:]
            if text_content.endswith('```'):
                text_content = text_content[:-3]
            
            try:
                return json.loads(text_content)
            except json.JSONDecodeError:
                start_idx = text_content.find('[')
                end_idx = text_content.rfind(']')
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    json_str = text_content[start_idx : end_idx + 1]
                    return json.loads(json_str)
                else:
                    raise ValueError("Failed to extract valid JSON for music sync from Gemini response.")

        except Exception as e:
            print(f"Error syncing video to music beats with Gemini: {e}")
            raise

    def select_and_summarize_highlights(self, full_description: str, scene_interval: int, user_prompt: str) -> List[Dict]:
        try:
            prompt = (
                "You are an AI video editor. Based on the following video frame descriptions, "
                f"identify and summarize key scenes that are relevant to the user's request: '{user_prompt}'. "
                "Segment the video into scenes approximately every "
                f"{scene_interval} seconds. For each *relevant* scene, provide a concise summary. "
                "Return ONLY a valid JSON array of objects, where each object has "
                "'start_timestamp' (string, HH:MM:SS), 'end_timestamp' (string, HH:MM:SS), "
                "'description' (string, single concise sentence summarizing the scene). "
                "Do not include any text outside the JSON array.\n\n"
                "Video Frame Descriptions (HH:MM:SS: description):\n"
                f"{full_description}\n\n"
                "Relevant Highlights (JSON array):"
            )
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}]
            )
            text_content = (getattr(response, "output_text", None) or response.candidates[0].content.parts[0].text).strip()
            if text_content.startswith('```json'):
                text_content = text_content[7:]
            if text_content.endswith('```'):
                text_content = text_content[:-3]
            
            try:
                return json.loads(text_content)
            except json.JSONDecodeError:
                start_idx = text_content.find('[')
                end_idx = text_content.rfind(']')
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    json_str = text_content[start_idx : end_idx + 1]
                    return json.loads(json_str)
                else:
                    raise ValueError("Failed to extract valid JSON for highlights from Gemini response.")

        except Exception as e:
            print(f"Error selecting and summarizing highlights with Gemini: {e}")
            raise

# Singleton instance
gemini_model_client = GeminiModelClient()
