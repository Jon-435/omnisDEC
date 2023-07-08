from EASGen import EASGen
from pydub import AudioSegment
from EAS2Text import EAS2Text
import datetime
import time
import subprocess
import sys
import os
import pyaudio
import wave
import threading

callsign = "WINDOWS"  # Change the callsign to whatever you like, as long as it is 8 characters.
print("Welcome to omnisDEC!")
relay = False
wait_event = threading.Event()  # Event to signal waiting

def encode(header, filename):
    global relay
    global wait_event

    if relay:
        print("Alert is being relayed. Waiting...")
        wait_event.wait()  # Wait for the wait_event to be set (alert relayed)
        wait_event.clear()  # Clear the event for the next alert
        time.sleep(120)  # Wait for 120 seconds

    relay = True
    eas_header = header
    header_segments = eas_header.split("-")
    header_segments[-2] = callsign
    new_eas_header = "-".join(header_segments)
    audio = AudioSegment.from_wav(filename)  # Alert Audio import
    print("Alert Encoded! Sending alert with SAME header of: " + new_eas_header)
    Alert = EASGen.genEAS(header=new_eas_header, attentionTone=False, audio=audio, mode="DIGITAL", endOfMessage=True)  # Generate an EAS SAME message with an ATTN signal, the imported WAV file as the audio, with EOMs, and with a SAGE DIGITAL ENDEC style.
    EASGen.export_wav("Alert.wav", Alert)

    wave_file = "Alert.wav"
    with wave.open(wave_file, 'rb') as wf:
        audio = pyaudio.PyAudio()
        stream = audio.open(format=audio.get_format_from_width(wf.getsampwidth()),
                            channels=wf.getnchannels(),
                            rate=wf.getframerate(),
                            output=True)
        chunk_size = 1024
        data = wf.readframes(chunk_size)
        while data:
            stream.write(data)
            data = wf.readframes(chunk_size)
        stream.stop_stream()
        stream.close()
        audio.terminate()
        print("")
        print("EOM Sent! Returning to monitoring for alerts!")
        relay = False

path = os.getcwd()
# Start the monitor
mon1 = subprocess.Popen([f"{path}/mon1.bat"], stdout=subprocess.PIPE)
mon2 = subprocess.Popen([f"{path}/mon2.bat"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
print("Now monitoring monitors for alerts!")


def process_monitor_output(monitor, url):
    while True:
        line = monitor.stdout.readline().decode("utf-8").replace("EAS: ", "").replace("\n", "")
        if "ZCZC-" in line:
            raw_header = line.strip()
            decoded_data = EAS2Text(raw_header)
            print("SAME Header received from soundcard monitor at " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ".")
            print("Header: " + raw_header)
            print("Decoded EAS Data:")
            print(f"{decoded_data.EASText}")
            output_filename = f"alert_audio_{url.replace(':', '_').replace('/', '_').replace('.', '_')}.wav"
            ffmpeg_cmd = f'ffmpeg -i "{url}" -f s16le -acodec pcm_s16le -ar 22050 -ac 1 -'
            output_wf = wave.open(output_filename, 'wb')
            output_wf.setnchannels(1)
            output_wf.setsampwidth(2)
            output_wf.setframerate(22050)

            write_lock = threading.Lock()
            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1024, shell=True)

            def write_audio_frames():
                while True:
                    data = ffmpeg_process.stdout.read(1024)
                    if not data:
                        break
                    with write_lock:
                        output_wf.writeframes(data)

            print("Recording alert!")
            write_thread = threading.Thread(target=write_audio_frames)
            write_thread.start()

            line = ""
            while True:
                line += monitor.stdout.readline().decode("utf-8")
                if "NNNN" in line:
                    break

            ffmpeg_process.stdout.close()
            ffmpeg_process.stderr.close()
            ffmpeg_process.wait()
            write_thread.join()
            output_wf.close()

            print("Alert recorded! Encoding alert!")
            result = encode(raw_header, output_filename)
            if result == "WAIT":
                wait_event.set()  # Set the wait_event to signal waiting

            # Reset the line variable
            line = ""

        elif not line:
            break  # Break out of the loop if no more lines are received (monitor process ended)


# Create threads for processing the output of each monitor
thread1 = threading.Thread(target=process_monitor_output, args=(mon1, "https://icecast.gwes-eas.network/ERN-JON"))
thread2 = threading.Thread(target=process_monitor_output, args=(mon2, "http://radiorandom.org:8000/WBJM"))

# Start the threads
thread1.start()
thread2.start()

# Wait for the threads to finish
thread1.join()
thread2.join()