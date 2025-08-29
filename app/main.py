import os
import json
import tempfile
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Import services and utilities
import uuid
from app.services.firebase_client import firebase_client
from app.services.model_client import gemini_model_client
from app.services.video_service import VideoProcessingService
from app.services.video_chat import VideoChat
from app.services.highlights_reel import HighlightsReelGen
from app.services.autocut_service import AutoCut
from app.utils.timecode import seconds_to_hhmmss, hhmmss_to_seconds
from app.utils.sanitize import sanitize_firebase_key
from app.utils.ffmpeg_tools import get_video_duration, sample_frames, concatenate_videos, render_video_with_cuts

# --- Data Models ---
class VideoProcessRequest(BaseModel):
    user_id: str
    video_filename: str

class VideoProcessResponse(BaseModel):
    message: str
    video_id: str
    user_id: str
    status: str

class ProcessingResult(BaseModel):
    id: str
    user_id: str
    frame_descriptions: Dict[str, str]  # "HH:MM:SS" -> caption
    summary: str
    status: str
    processed_at: str

class NewProjectRequest(BaseModel):
    user_id: str
    project_id: str
    video_ids: List[str]

class NewProjectResponse(BaseModel):
    project_id: str
    user_id: str
    status: str
    message: str
    output_filename: Optional[str]

from typing import Tuple # Add this import

class RenderVideoRequest(BaseModel):
    user_id: str
    project_id: str
    segments_to_keep: Optional[List[Tuple[float, float]]] = None
    audio_file_name: Optional[str] = None  # Add this line

class RenderVideoResponse(BaseModel):
    project_id: str
    user_id: str
    status: str
    message: str
    output_filename: Optional[str]

class VideoChatQuestionRequest(BaseModel):
    question: str
    user_id: str
    project_id: str
    session_id: Optional[str] = None

class VideoChatQuestionResponse(BaseModel):
    response: str
    session_id: str
    timestamp: str

class HighlightsRequest(BaseModel):
    user_id: str
    project_id: str
    scene_interval: Optional[int] = 12
    user_prompt: Optional[str] = None

class HighlightsResponse(BaseModel):
    user_id: str
    project_id: str
    highlights: List[Dict]  # [{scene_id, start_timestamp, end_timestamp, description}]
    total_scenes: int
    generated_at: str

class SongAnalysisRequest(BaseModel):
    user_id: str
    project_id: str
    file_name: str

class Cut(BaseModel):
    time: float  # seconds
    reason: str

# --- FastAPI App Initialization ---
app = FastAPI(
    title="AI Video Editor Backend",
    description="FastAPI backend for an AI-driven video editor using Google Gemini.",
    version="1.0.0",
)

# In-memory session store for VideoChat
video_chat_sessions: Dict[str, VideoChat] = {}

# --- Health and Info Endpoints ---
@app.get("/", summary="Basic service info")
async def read_root():
    return {
        "service_name": "AI Video Editor Backend",
        "version": "1.0.0",
        "endpoints": [
            "/health", "/process-video", "/video-result/{user_id}/{video_filename}",
            "/list-videos", "/newProject", "/rendervideo", "/videochat/ask",
            "/videochat/session/{session_id}", "/videochat/history/{session_id}",
            "/videochat/search/{session_id}", "/highlights/generate",
            "/autocut/analyze-song", "/debug/storage-exists", "/debug/project",
            "/debug/video-analysis"
        ]
    }

@app.get("/health", summary="Health check")
async def health_check():
    try:
        # Try to access Firebase to check connection
        firebase_client.db_ref().child("health_check").set({"timestamp": datetime.now().isoformat()})
        # Try a simple Gemini call (e.g., list models) to check connection
        # This might be too heavy for a health check, so we'll skip for now
        # gemini_model_client.client.list_models()
        return {"status": "ok", "firebase": "connected", "gemini": "ready (assumed)"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Health check failed: {e}")

# --- Debug/Testing Endpoints ---
@app.get("/debug/storage-exists", summary="Check if a blob exists in Firebase Storage")
async def debug_storage_exists(path: str):
    try:
        bucket = firebase_client.get_bucket()
        blob = bucket.blob(path)
        exists = blob.exists()
        return {"path": path, "exists": exists}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error checking storage: {e}")

@app.get("/debug/project/{user_id}/{project_id}", summary="Summary of project data")
async def debug_project_summary(user_id: str, project_id: str):
    try:
        project_ref = firebase_client.db_ref().child("projects").child(user_id).child(project_id)
        project_data = project_ref.get()
        if not project_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

        video_ids_count = len(project_data.get("video_ids", []))
        full_description_size = len(project_data.get("fullDescription", ""))
        output_filename = project_data.get("output_filename")

        storage_files_presence = {}
        bucket = firebase_client.get_bucket()
        if output_filename:
            full_mp4_path = f"projects/{user_id}/{project_id}/full.mp4"
            preview_mp4_path = f"projects/{user_id}/{project_id}/preview.mp4"
            storage_files_presence["full.mp4"] = bucket.blob(full_mp4_path).exists()
            storage_files_presence["preview.mp4"] = bucket.blob(preview_mp4_path).exists()

        return {
            "user_id": user_id,
            "project_id": project_id,
            "video_ids_count": video_ids_count,
            "fullDescription_size": full_description_size,
            "output_filename": output_filename,
            "storage_files_presence": storage_files_presence,
            "project_data": project_data # Raw data for inspection
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching project debug info: {e}")

from starlette.responses import StreamingResponse

@app.get("/debug/video-analysis/{user_id}/{video_filename}", summary="Returns raw DB node for video analysis")
async def debug_video_analysis(user_id: str, video_filename: str):
    try:
        sanitized_filename = sanitize_firebase_key(video_filename)
        video_analysis_ref = firebase_client.db_ref().child("video_analysis").child(user_id).child(sanitized_filename)
        analysis_data = video_analysis_ref.get()
        if not analysis_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video analysis data not found.")
        return analysis_data
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching video analysis debug info: {e}")

@app.get("/debug/download-file", summary="[TEMPORARY] Download a file from Firebase Storage locally")
async def debug_download_file(path: str):
    try:
        bucket = firebase_client.get_bucket()
        blob = bucket.blob(path)
        if not blob.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found in storage: {path}")
        
        # Save directly to current directory
        local_path = os.path.join(os.getcwd(), os.path.basename(path))
        blob.download_to_filename(local_path)

        return {"message": f"File downloaded successfully to {local_path}"}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error downloading file from storage: {e}"
        )
    
video_processing_service = VideoProcessingService(firebase_client, gemini_model_client)

@app.post("/process-video", response_model=VideoProcessResponse, summary="Process a video for frame analysis and summary")
async def process_video_endpoint(request: VideoProcessRequest):
    try:
        await video_processing_service.process_video(request.user_id, request.video_filename)
        return VideoProcessResponse(
            message="Video processing initiated and completed.",
            video_id=sanitize_firebase_key(request.video_filename),
            user_id=request.user_id,
            status="completed"
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Video processing failed: {e}")

@app.get("/video-result/{user_id}/{video_filename}", response_model=ProcessingResult, summary="Get video processing results")
async def get_video_result(user_id: str, video_filename: str):
    sanitized_filename = sanitize_firebase_key(video_filename)
    video_analysis_ref = firebase_client.db_ref().child("video_analysis").child(user_id).child(sanitized_filename)
    analysis_data = video_analysis_ref.get()

    if not analysis_data or analysis_data.get("status") != "completed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video analysis not found or not completed.")
    
    return ProcessingResult(**analysis_data)

@app.get("/list-videos", summary="Lists available video files for quick inspection")
async def list_videos(user_id: Optional[str] = None):
    bucket = firebase_client.get_bucket()
    blobs = bucket.list_blobs(prefix=f"videos/{user_id}/" if user_id else "videos/")
    video_files = []
    for blob in blobs:
        # Filter out directories and ensure it's a video file (simple check)
        if not blob.name.endswith('/') and any(blob.name.lower().endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.mkv']):
            parts = blob.name.split('/')
            if len(parts) >= 3: # Expecting videos/{user_id}/{video_filename}
                file_user_id = parts[1]
                filename = parts[2]
                video_files.append({
                    "user_id": file_user_id,
                    "video_filename": filename,
                    "path": blob.name,
                    "size": blob.size,
                    "updated": blob.updated.isoformat()
                })
    return {"videos": video_files}

# --- Project Creation and Rendering Endpoints ---
@app.post("/newProject", response_model=NewProjectResponse, summary="Create a new project by concatenating videos")
async def create_new_project(request: NewProjectRequest):
    user_id = request.user_id
    project_id = request.project_id
    video_ids = request.video_ids

    if not video_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No video_ids provided for the project.")

    project_output_path_in_storage = f"projects/{user_id}/{project_id}/full.mp4"
    bucket = firebase_client.get_bucket()
    project_ref = firebase_client.db_ref().child("projects").child(user_id).child(project_id)

    local_video_paths = []
    full_description_entries = []
    current_offset_seconds = 0.0

    with tempfile.TemporaryDirectory() as temp_dir:
        for video_id in video_ids:
            sanitized_video_id = sanitize_firebase_key(video_id)
            video_analysis_ref = firebase_client.db_ref().child("video_analysis").child(user_id).child(sanitized_video_id)
            video_analysis_data = video_analysis_ref.get()

            if not video_analysis_data or video_analysis_data.get("status") != "completed":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Video analysis for {video_id} not found or not completed.")

            video_filename = video_id # Assuming video_id is the original filename
            video_path_in_storage = f"videos/{user_id}/{video_filename}"
            blob = bucket.blob(video_path_in_storage)

            if not blob.exists():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source video {video_filename} not found in storage.")

            local_video_path = os.path.join(temp_dir, video_filename)
            blob.download_to_filename(local_video_path)
            local_video_paths.append(local_video_path)

            # Build fullDescription with offsets
            frame_descriptions = video_analysis_data.get("frame_descriptions", {})
            sorted_timestamps = sorted(frame_descriptions.keys(), key=hhmmss_to_seconds)
            
            for ts_str in sorted_timestamps:
                original_seconds = hhmmss_to_seconds(ts_str)
                offset_seconds = original_seconds + current_offset_seconds
                offset_ts_str = seconds_to_hhmmss(offset_seconds)
                full_description_entries.append(f"{offset_ts_str}: {frame_descriptions[ts_str]}")
            
            current_offset_seconds += get_video_duration(local_video_path)

        output_filename = f"{project_id}_full.mp4"
        local_output_path = os.path.join(temp_dir, output_filename)
        concatenate_videos(local_video_paths, local_output_path)
        print(f"Concatenated videos to {local_output_path}")

        # Upload concatenated video to Firebase Storage
        output_blob = bucket.blob(project_output_path_in_storage)
        output_blob.upload_from_filename(local_output_path)
        print(f"Uploaded {local_output_path} to {project_output_path_in_storage}")

        # Update Realtime Database
        project_data = {
            "video_ids": video_ids,
            "fullDescription": "\n".join(full_description_entries),
            "createdAt": datetime.now().isoformat(),
            "output_filename": project_output_path_in_storage
        }
        project_ref.set(project_data)
        print(f"Project data saved to Firebase for {project_id}")

    return NewProjectResponse(
        project_id=project_id,
        user_id=user_id,
        status="completed",
        message="Project created and videos concatenated successfully.",
        output_filename=project_output_path_in_storage
    )

@app.post("/rendervideo", response_model=RenderVideoResponse, summary="Render a video with cuts or specified segments")
async def render_project_video(request: RenderVideoRequest):
    user_id = request.user_id
    project_id = request.project_id

    project_ref = firebase_client.db_ref().child("projects").child(user_id).child(project_id)
    project_data = project_ref.get()
    if not project_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found.")

    full_mp4_path_in_storage = project_data.get("output_filename")
    if not full_mp4_path_in_storage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Full video for project {project_id} not found in storage metadata.")

    bucket = firebase_client.get_bucket()
    full_mp4_blob = bucket.blob(full_mp4_path_in_storage)
    if not full_mp4_blob.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Full video file {full_mp4_path_in_storage} not found in storage.")

    final_segments_to_keep: List[Tuple[float, float]] = []

    if request.segments_to_keep:
        # Use explicitly provided segments
        final_segments_to_keep = request.segments_to_keep
        print(f"Rendering with explicit segments: {final_segments_to_keep}")
    else:
        # Fallback to existing logic: compute segments from "CUT" markers
        full_description_lines = project_data.get("fullDescription", "").split('\n')
        cut_timestamps = [] # List of seconds where cuts should be applied
        for line in full_description_lines:
            if line.strip().lower().startswith("cut"):
                try:
                    parts = line.split(":", 3)
                    if len(parts) >= 3:
                        ts_str = f"{parts[1].strip()}:{parts[2].strip()}:{parts[3].split(':',1)[0].strip()}"
                        cut_timestamps.append(hhmmss_to_seconds(ts_str))
                    else:
                        print(f"Warning: Could not parse cut timestamp from line: {line}")
                except ValueError:
                    print(f"Warning: Could not parse cut timestamp from line: {line}")

        with tempfile.TemporaryDirectory() as temp_dir:
            local_full_mp4_path_for_duration = os.path.join(temp_dir, "full_duration.mp4")
            full_mp4_blob.download_to_filename(local_full_mp4_path_for_duration)
            video_duration = get_video_duration(local_full_mp4_path_for_duration)
            os.remove(local_full_mp4_path_for_duration) # Clean up temp file

        current_start = 0.0
        sorted_cut_timestamps = sorted(list(set(cut_timestamps)))

        for cut_time in sorted_cut_timestamps:
            if cut_time > current_start:
                final_segments_to_keep.append((current_start, cut_time))
            current_start = cut_time + 1.0 # Apply 1-second cut

        if current_start < video_duration:
            final_segments_to_keep.append((current_start, video_duration))
        print(f"Rendering with segments derived from 'CUT' markers: {final_segments_to_keep}")

    if not final_segments_to_keep:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No segments to keep for rendering.")

    with tempfile.TemporaryDirectory() as temp_dir:
        local_full_mp4_path = os.path.join(temp_dir, "full.mp4")
        full_mp4_blob.download_to_filename(local_full_mp4_path)
        print(f"Downloaded full video to {local_full_mp4_path}")
        
        preview_output_filename = f"{project_id}_preview.mp4"
        local_preview_path = os.path.join(temp_dir, preview_output_filename)
        preview_path_in_storage = f"projects/{user_id}/{project_id}/preview.mp4"

        audio_path = None
        if request.audio_file_name:
            # Download the MP3 file from storage
            audio_path_in_storage = f"MusicFiles/{user_id}/{project_id}/{request.audio_file_name}"
            audio_blob = bucket.blob(audio_path_in_storage)
            if audio_blob.exists():
                audio_path = os.path.join(temp_dir, request.audio_file_name)
                audio_blob.download_to_filename(audio_path)
                print(f"Downloaded audio file to {audio_path}")
            else:
                print(f"Warning: Audio file {audio_path_in_storage} not found, using original audio")

        # Update the render_video_with_cuts call:
        render_video_with_cuts(local_full_mp4_path, local_preview_path, final_segments_to_keep, audio_path)
        print(f"Rendered preview video to {local_preview_path}")

        preview_blob = bucket.blob(preview_path_in_storage)
        preview_blob.upload_from_filename(local_preview_path)
        print(f"Uploaded {local_preview_path} to {preview_path_in_storage}")

        project_ref.update({"preview_filename": preview_path_in_storage})

    return RenderVideoResponse(
        project_id=project_id,
        user_id=user_id,
        status="completed",
        message="Video rendered successfully.",
        output_filename=preview_path_in_storage
    )

# --- VideoChat Endpoints ---
@app.post("/videochat/ask", response_model=VideoChatQuestionResponse, summary="Ask a question about a video project")
async def ask_video_chat(request: VideoChatQuestionRequest):
    session_id = request.session_id
    if not session_id or session_id not in video_chat_sessions:
        # Create a new session
        new_session_id = str(uuid.uuid4())
        video_chat_instance = VideoChat(
            user_id=request.user_id,
            project_id=request.project_id,
            firebase_client=firebase_client,
            gemini_model_client=gemini_model_client,
            session_id=new_session_id
        )
        video_chat_sessions[new_session_id] = video_chat_instance
        session_id = new_session_id
    else:
        video_chat_instance = video_chat_sessions[session_id]

    try:
        response_data = await video_chat_instance.ask_question(request.question)
        return VideoChatQuestionResponse(**response_data)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"VideoChat question failed: {e}")

@app.get("/videochat/session/{session_id}", summary="Get VideoChat session info")
async def get_video_chat_session_info(session_id: str):
    if session_id not in video_chat_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VideoChat session not found.")
    
    return video_chat_sessions[session_id].get_session_info()

@app.get("/videochat/history/{session_id}", summary="Return last N entries in chat history")
async def get_video_chat_history(session_id: str, limit: int = 10):
    if session_id not in video_chat_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VideoChat session not found.")
    
    return video_chat_sessions[session_id].get_chat_history(limit)

@app.get("/videochat/search/{session_id}", summary="Searches frame descriptions")
async def search_video_chat(session_id: str, keyword: str):
    if session_id not in video_chat_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VideoChat session not found.")
    
    return video_chat_sessions[session_id].search_frame_descriptions(keyword)

# --- Highlights Reel Endpoints ---
highlights_reel_gen = HighlightsReelGen(firebase_client, gemini_model_client)

@app.post("/highlights/generate", response_model=HighlightsResponse, summary="Generate highlights for a project")
async def generate_highlights(request: HighlightsRequest):
    try:
        highlights_data = await highlights_reel_gen.generate_highlights(
            user_id=request.user_id,
            project_id=request.project_id,
            scene_interval=request.scene_interval,
            user_prompt=request.user_prompt
        )
        return HighlightsResponse(**highlights_data)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Highlights generation failed: {e}")

# --- AutoCut Endpoints ---
autocut_service = AutoCut(firebase_client, gemini_model_client)

@app.post("/autocut/analyze-song", response_model=List[Cut], summary="Analyze a song for cut timestamps")
async def analyze_song_for_autocut(request: SongAnalysisRequest):
    try:
        cuts = await autocut_service.analyze_song(
            user_id=request.user_id,
            project_id=request.project_id,
            file_name=request.file_name
        )
        return [Cut(**cut) for cut in cuts]
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"AutoCut analysis failed: {e}")
