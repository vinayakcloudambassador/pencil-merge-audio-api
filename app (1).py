from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import storage
from pydub import AudioSegment
import os
import tempfile
import uuid

app = FastAPI()

class AudioInput(BaseModel):
    voice_url: str  # GCS URL for the voice file
    music_url: str  # GCS URL for the music file

def download_from_gcs(gcs_url, local_path):
    """
    Downloads a file from GCS given the GCS URL.
    """
    try:
        storage_client = storage.Client()
        bucket_name, blob_name = gcs_url.replace("gs://", "").split("/", 1)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_path)
        print(f"Downloaded {gcs_url} to {local_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download from GCS: {e}")

def upload_to_gcs(local_path, gcs_url):
    """
    Uploads a file to GCS.
    """
    try:
        storage_client = storage.Client()
        bucket_name, blob_name = gcs_url.replace("gs://", "").split("/", 1)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path)
        print(f"Uploaded {local_path} to {gcs_url}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to GCS: {e}")

def merge_audio(voice_path, music_path, output_path):
    """
    Merges voice and music audio files.
    """
    try:
        print("Loading audio files...")
        voice = AudioSegment.from_file(voice_path)
        music = AudioSegment.from_file(music_path)

        # Adjust background music volume
        music = music - 15

        # Overlay the voice on the music
        print("Merging audio files...")
        merged = music.overlay(voice)

        # Export the merged audio file
        merged.export(output_path, format="mp3")
        print(f"Merged audio saved to: {output_path}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during merging: {e}")

@app.post("/merge-audio/")
async def merge_audio_endpoint(input: AudioInput):
    """
    FastAPI endpoint to merge audio files.
    """
    # Temporary files for processing
    voice_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    music_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    output_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")

    try:
        # Download files from GCS
        download_from_gcs(input.voice_url, voice_temp_file.name)
        download_from_gcs(input.music_url, music_temp_file.name)

        # Merge the audio files
        merge_audio(voice_temp_file.name, music_temp_file.name, output_temp_file.name)

        # Generate a unique name for the output file in the same bucket
        # Here we generate a UUID-based filename
        bucket_name, _ = input.voice_url.replace("gs://", "").split("/", 1)
        output_gcs_path = f"gs://{bucket_name}/merged_audio/{uuid.uuid4().hex}.mp3"

        # Upload the merged audio to the same GCS bucket
        upload_to_gcs(output_temp_file.name, output_gcs_path)

        # Return the GCS URL of the uploaded file
        return {"output_url": output_gcs_path}

    finally:
        # Cleanup temporary files
        os.unlink(voice_temp_file.name)
        os.unlink(music_temp_file.name)
        os.unlink(output_temp_file.name)
