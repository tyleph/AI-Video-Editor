# AI Video Editor Backend

This is the FastAPI backend for an AI-driven video editor, with 3 main functionalities:
1. Video Chat: Q&A chatbot for all your videos
2. Highlight Reel Generation: Video editing to create highlights
3. AutoCut: Syncs clips to music based on beats

## Setup

1.  **Clone the repository:**
    ```bash
    git clone [repository-url]
    cd ai-video-editor-backend
    ```

2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install FFmpeg:**
    Ensure FFmpeg is installed on your system and available in your PATH. You can download it from [ffmpeg.org](https://ffmpeg.org/download.html).

4.  **Firebase Project Setup:**
    *   Create a Firebase project.
    *   Enable Firebase Storage and Realtime Database.
    *   Generate a service account private key JSON file.
    *   Copy the content of this JSON file into the `FIREBASE_CREDENTIALS_JSON` environment variable in your `.env` file (as a single-line string).

5.  **Google Gemini API Key:**
    *   Obtain a Google Gemini API key from [Google AI Studio](https://aistudio.google.com/).
    *   Set the `GEMINI_API_KEY` environment variable in your `.env` file.

6.  **Environment Variables:**
    Create a `.env` file in the root directory of the project based on `.env.example` and fill in the values:
    ```
    FIREBASE_CREDENTIALS_JSON="YOUR_FIREBASE_SERVICE_ACCOUNT_JSON_STRING"
    FIREBASE_STORAGE_BUCKET="your-bucket-name.appspot.com"
    FIREBASE_DATABASE_URL="https://your-project-id-default-rtdb.firebaseio.com"
    GEMINI_API_KEY="YOUR_GOOGLE_GEMINI_API_KEY"
    ```

## Running the Application

```bash
uvicorn app.main:app --reload
```

The API documentation will be available at `http://127.0.0.1:8000/docs`.

## Usage and Testing

To test the full functionality, follow these steps in order:

### 1. Upload a Video to Firebase Storage

Manually upload your video file to Firebase Storage at the path `videos/{user_id}/{video_filename}`.
*Example:* `videos/testuser/my_vacation.mp4`

### 2. Process the Uploaded Video

Use the `/process-video` endpoint to analyze your video. This will sample frames, caption them, summarize the video, and store the results in Firebase Realtime Database.

**Endpoint:** `POST /process-video`
**Example `curl` command:**
```bash
curl -X POST "http://127.0.0.1:8000/process-video" \
     -H "Content-Type: application/json" \
     -d '{
           "user_id": "testuser",
           "video_filename": "my_vacation.mp4"
         }'
```

### 3. Create a Project

Combine one or more processed videos into a new project using the `/newProject` endpoint. This will concatenate the videos and build a `fullDescription` in the Realtime Database.

**Endpoint:** `POST /newProject`
**Example `curl` command:**
```bash
curl -X POST "http://127.0.0.1:8000/newProject" \
     -H "Content-Type: application/json" \
     -d '{
           "user_id": "testuser",
           "project_id": "vacation_project_1",
           "video_ids": ["my_vacation.mp4"]
         }'
```

### 4. Ask Questions with VideoChat

Interact with your project's video content using the VideoChat CLI.

**CLI Usage:**
```bash
python tests/video_chat_cli.py --user-id <your_user_id> --project-id <your_project_id>
# Example:
python tests/video_chat_cli.py --user-id testuser --project-id vacation_project_1
```
You can also provide an optional `--session-id` to continue a previous chat.

### 5. Generate Highlights Reel

Generate a highlight reel for your project using the `/highlights/generate` endpoint given a user prompt to guide highlight selection.

**Endpoint:** `POST /highlights/generate`
**CLI Usage:**
```bash
python tests/highlights_cli.py --user-id <your_user_id> --project-id <your_project_id> --prompt "<your_highlight_criteria>" [--scene-interval <seconds>] [--render-output <output_filename>]
# Example:
python tests/highlights_cli.py --user-id testuser --project-id vacation_project_1 --prompt "show me all the action scenes" --render-output highlights_output.mp4
```
*Note: The `--render-output` option will trigger the backend to render the highlights and save the resulting video to Firebase Storage. The CLI will then download it locally to the specified path.*

### 6. AutoCut Music Sync

Analyze a music file to get cut timestamps, now with enhanced video-to-music synchronization.

**Prerequisites:**
*   Upload your music file to Firebase Storage at `MusicFiles/{user_id}/{project_id}/{file_name}`.
    *Example:* `MusicFiles/testuser/vacation_project_1/my_song.mp3`
*   Ensure you have a project created (Step 3) as the AutoCut service will attempt to get the video duration from `projects/{user_id}/{project_id}/full.mp4` for filtering cuts, and also use the `fullDescription` for intelligent syncing.

**Endpoint:** `POST /autocut/analyze-song`
**CLI Usage:**
```bash
python tests/autocut_cli.py --user-id <your_user_id> --project-id <your_project_id> --file-name <your_music_filename> [--render-output <output_filename>]
# Example:
python tests/autocut_cli.py --user-id testuser --project-id vacation_project_1 --file-name my_song.mp3 --render-output autocut_output.mp4
```
*Note: The `--render-output` option will trigger the backend to render the AutoCut video and save the resulting video to Firebase Storage. The CLI will then download it locally to the specified path.*

### 7. Render Video with Cuts

Apply cuts to your project's full video based on descriptions (e.g., "CUT HH:MM:SS: reason") in the `fullDescription`, or by providing explicit segments.

**Endpoint:** `POST /rendervideo`
**Example `curl` command (using "CUT" markers):**
```bash
curl -X POST "http://127.0.0.1:8000/rendervideo" \
     -H "Content-Type: application/json" \
     -d '{
           "user_id": "testuser",
           "project_id": "vacation_project_1"
         }'
```
**Example `curl` command (using explicit segments):**
```bash
curl -X POST "http://127.0.0.1:8000/rendervideo" \
     -H "Content-Type: application/json" \
     -d '{
           "user_id": "testuser",
           "project_id": "vacation_project_1",
           "segments_to_keep": [[0.0, 10.0], [20.0, 30.0]]
         }'
```
