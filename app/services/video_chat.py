import os
import uuid
from typing import Dict, List, Any
from datetime import datetime
from memochain.session import MemoChainSession
from fastapi import HTTPException, status
from typing import Optional

from app.services.firebase_client import FirebaseClient
from app.services.model_client import GeminiModelClient
from app.utils.timecode import seconds_to_hhmmss, hhmmss_to_seconds

class VideoChat:
    def __init__(self, user_id: str, project_id: str, firebase_client: FirebaseClient, gemini_model_client: GeminiModelClient, session_id: Optional[str] = None):
        self.user_id = user_id
        self.project_id = project_id
        self.firebase_client = firebase_client
        self.gemini_model_client = gemini_model_client
        self.session_id = session_id if session_id else str(uuid.uuid4())
        self.chat_history: List[Dict[str, str]] = []
        self.memochain_session = MemoChainSession(session_id=self.session_id, context_window=8)
        self.full_description: str = self._load_full_description()
        self.system_prompt = self._build_system_prompt()

    def _load_full_description(self) -> str:
        project_ref = self.firebase_client.db_ref().child("projects").child(self.user_id).child(self.project_id)
        project_data = project_ref.get()
        if not project_data or "fullDescription" not in project_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {self.project_id} or its fullDescription not found.")
        return project_data["fullDescription"]

    def _build_system_prompt(self) -> str:
        # Assuming fullDescription is already sorted by timestamp
        context_lines = self.full_description.split('\n')
        
        prompt = (
            "You are a video Q&A assistant for answering questions about video content. Answer using the provided video context:\n\n"
            "Context:\n" + "\n".join(context_lines)
        )
        return prompt

    async def ask_question(self, question: str) -> Dict[str, str]:
        self.memochain_session.add_user_message(question)
        
        full_prompt = f"{self.system_prompt}\n\nUser: {question}\nAssistant:"
        
        try:
            # response = self.gemini_model_client.client.generate_content(contents=[full_prompt])
            response = self.gemini_model_client.client.models.generate_content(
                model=self.gemini_model_client.model,
                contents=[{"role": "user", "parts": [{"text": full_prompt}]}],
            )


            # assistant_response = response.text
            assistant_response = getattr(response, "output_text", None) or response.candidates[0].content.parts[0].text

        except Exception as e:
            print(f"Error asking question to Gemini: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gemini error: {e}")

        self.memochain_session.add_assistant_message(assistant_response)
        
        timestamp = datetime.now().isoformat()
        self.chat_history.append({"role": "user", "content": question, "timestamp": timestamp})
        self.chat_history.append({"role": "assistant", "content": assistant_response, "timestamp": timestamp})

        return {
            "response": assistant_response,
            "session_id": self.session_id,
            "timestamp": timestamp
        }

    def get_session_info(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "chat_history_count": len(self.chat_history)
        }

    def get_chat_history(self, limit: int = 10) -> List[Dict[str, str]]:
        return self.chat_history[-limit:]

    def search_frame_descriptions(self, keyword: str) -> List[Dict[str, str]]:
        found_descriptions = []
        # Assuming full_description is a string where each line is "HH:MM:SS: description"
        for line in self.full_description.split('\n'):
            if keyword.lower() in line.lower():
                found_descriptions.append({"content": line})
        return found_descriptions
