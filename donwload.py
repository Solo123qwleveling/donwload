import yt_dlp

# Replace with your video URL
url = "https://www.youtube.com/watch?v=UtMMjXOlRQc"

# Download options
ydl_opts = {
    # Tries to get the best video (up to 4K) + best audio
    'format': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]',

    # Output file settings
    'outtmpl': r'C:\Users\B3\Downloads\%(title)s.%(ext)s',
    'merge_output_format': 'mp4',

    # Error handling and fallback options
    'ignoreerrors': True,  # Skip broken videos instead of crashing
    'noprogress': False,  # Show download progress
    'no_warnings': False,  # Show useful warnings
    'quiet': False,  # Keep logs visible
    'retries': 3,  # Retry failed requests
    'windowsfilenames': True,  # Avoid invalid chars in filenames

    # Postprocessing: merge video + audio with ffmpeg
    'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4',
    }],
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    # Try updating automatically before downloading
    try:
        ydl.update()
    except Exception as e:
        print("Auto-update skipped:", e)

    ydl.download([url])