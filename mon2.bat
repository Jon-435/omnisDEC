ffmpeg -i "http://radiorandom.org:8000/WBJM" -f s16le -acodec pcm_s16le -ar 22050 -ac 1 - 2>NUL | decoder -r 22050