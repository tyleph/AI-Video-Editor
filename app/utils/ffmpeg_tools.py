import ffmpeg
import os
import subprocess
from typing import List, Tuple

def get_video_duration(input_path: str) -> float:
    """Gets the duration of a video in seconds."""
    try:
        probe = ffmpeg.probe(input_path)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream and 'duration' in video_stream:
            return float(video_stream['duration'])
        elif 'format' in probe and 'duration' in probe['format']:
            return float(probe['format']['duration'])
        return 0.0
    except ffmpeg.Error as e:
        print(f"FFmpeg error getting duration for {input_path}: {e.stderr.decode()}")
        raise
    except Exception as e:
        print(f"Error getting video duration for {input_path}: {e}")
        raise

def sample_frames(input_path: str, output_dir: str, interval: int = 6) -> List[Tuple[str, float]]:
    """
    Samples frames from a video at a given interval.
    Returns a list of (frame_path, seconds) tuples.
    """
    os.makedirs(output_dir, exist_ok=True)
    frames_data = []
    duration = get_video_duration(input_path)

    try:
        # Sample at midpoints: for segment [0..3) sample at 1.5s, then 4.5s, etc.
        current_time = interval / 2.0
        while current_time < duration:
            frame_filename = f"frame_{int(current_time * 1000)}.jpg"
            frame_path = os.path.join(output_dir, frame_filename)
            
            (
                ffmpeg
                .input(input_path, ss=current_time)
                .output(frame_path, vframes=1, vf='scale=-1:360') # Scale to height 360 for speed
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
            frames_data.append((frame_path, current_time))
            current_time += interval
    except ffmpeg.Error as e:
        print(f"FFmpeg error sampling frames from {input_path}: {e.stderr.decode()}")
        raise
    except Exception as e:
        print(f"Error sampling frames from {input_path}: {e}")
        raise
    return frames_data

def concatenate_videos(input_paths: List[str], output_path: str):
    """Concatenates multiple video files into a single output file."""
    try:
        # Create a file list for ffmpeg concat demuxer
        list_file_path = "file_list.txt"
        with open(list_file_path, "w") as f:
            for path in input_paths:
                f.write(f"file '{path}'\n")

        # Use ffmpeg concat demuxer
        (
            ffmpeg
            .input(list_file_path, f='concat', safe=0)
            .output(output_path, c='copy') # Copy streams without re-encoding for speed
            .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        )
        os.remove(list_file_path)
    except ffmpeg.Error as e:
        print(f"FFmpeg error concatenating videos: {e.stderr.decode()}")
        raise
    except Exception as e:
        print(f"Error concatenating videos: {e}")
        raise

def render_video_with_cuts(input_path: str, output_path: str, cuts: List[Tuple[float, float]], audio_path: str = None):
    """
    Renders a video by applying cuts.
    `cuts` is a list of (start_time, end_time) tuples for segments to KEEP.
    `audio_path` is an optional path to an audio file to replace the original audio.
    """
    if not cuts:
        # If no cuts, just copy the original video
        print("No cuts specified, copying original video.")
        
        if audio_path:
            # Replace audio even when no cuts
            (
                ffmpeg
                .output(
                    ffmpeg.input(input_path)['v'],
                    ffmpeg.input(audio_path)['a'],
                    output_path, 
                    vcodec='libx264', 
                    acodec='aac', 
                    strict='experimental', 
                    pix_fmt='yuv420p',
                    shortest=None  # Use shortest stream duration
                )
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
        else:
            (
                ffmpeg
                .input(input_path)
                .output(output_path, c='copy')
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
        return

    try:
        # Create video segments (video only, no audio)
        video_segments = []
        for i, (start, end) in enumerate(cuts):
            segment_input = ffmpeg.input(input_path, ss=start, to=end)
            video_segments.append(segment_input.video)

        # Concatenate video segments
        concatenated_video = ffmpeg.concat(*video_segments, v=1, a=0)  # a=0 means no audio output
        
        if audio_path:
            # Use the provided audio file
            audio_input = ffmpeg.input(audio_path)
            (
                ffmpeg
                .output(
                    concatenated_video, 
                    audio_input['a'], 
                    output_path, 
                    vcodec='libx264', 
                    acodec='aac', 
                    strict='experimental', 
                    pix_fmt='yuv420p',
                    shortest=None  # Use shortest stream duration
                )
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
        else:
            # Original behavior - concatenate audio from video segments
            audio_segments = []
            for i, (start, end) in enumerate(cuts):
                segment_input = ffmpeg.input(input_path, ss=start, to=end)
                audio_segments.append(segment_input.audio)
            
            concatenated_audio = ffmpeg.concat(*audio_segments, v=0, a=1)
            (
                ffmpeg
                .output(concatenated_video, concatenated_audio, output_path, vcodec='libx264', acodec='aac', strict='experimental', pix_fmt='yuv420p')
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )

    except ffmpeg.Error as e:
        print(f"FFmpeg error rendering video with cuts: {e.stderr.decode()}")
        raise
    except Exception as e:
        print(f"Error rendering video with cuts: {e}")
        raise
