from EASGen import EASGen
from pydub import AudioSegment
from EAS2Text import EAS2Text
import datetime
import time
import subprocess
import os
import pyaudio
import wave
import threading
import audioop
from pydub import AudioSegment

from discord_webhook import DiscordEmbed, DiscordWebhook

def send_to_discord(url, same, state):
    #Change the webhook settings here
    webhook_url = "put your webhook url here"
    StationTitle = 'The best radio station' ## This is the very top, put your CALLSIGN or similar here.
    StationURL = 'https://radiorandom.org' ## Link to go to if you click the Station Title
    AlertURL = 'http://radiorandom.org:8000/WBJM' ## Link that will be highlighted with the Alert Name

    ##Color Config
    wek = 0x7CFC00
    unk = 0x797979
    adv = 0xffcc00
    wat = 0xff6600
    war = 0xff0000
    ean = 0x000000

    data = EAS2Text(same)
    details = f"{data.EASText}"
    if any(word.lower() in details.lower() for word in ['Action', 'Center']):
        color = ean
    elif any(word.lower() in details.lower() for word in ['Demo', 'Test']):
        color = wek
    elif any(word.lower() in details.lower() for word in ['Advisory', 'Statement', 'Administrative', 'Practice', 'Transmitter', 'Network']):
        color = adv
    elif any(word.lower() in details.lower() for word in ['Watch']):
        color = wat
    elif any(word.lower() in details.lower() for word in ['Warning', 'Emergency', 'Alert', 'Evacuation', 'Notification']):
        color = war
    else:
        color = unk

    if state == False:
        embed = DiscordEmbed(title="Alert Received", description="A SAME Alert Was Received!", color=color, url=AlertURL)
        embed.set_author(name=StationTitle, url=StationURL)
        embed.add_embed_field(name='Monitor Details: ', value= "Stream URL: " + url + " at " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        embed.add_embed_field(name='EAS Text Data:', value= "```" + details + "```", inline=False)
        embed.add_embed_field(name='EAS Protocol Data:', value="```" + same + "```", inline=False)
        embed.add_embed_field(name='', value="Better than the rest", inline=False)
        embed.set_footer(text="omnisDEC Software ENDEC Version 0.10")
    elif state == True:
        embed = DiscordEmbed(title="Alert Sent", description="A SAME Alert Was Forwarded!", color=color, url=AlertURL)
        embed.set_author(name=StationTitle, url=StationURL)
        embed.add_embed_field(name='Timestamp', value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)  # Provide a value for the 'value' parameter
        embed.add_embed_field(name='EAS Text Data:', value= "```" + details + "```", inline=False)
        embed.add_embed_field(name='EAS Protocol Data:', value="```" + same + "```", inline=False)
        embed.add_embed_field(name='', value="Better than the rest", inline=False)
        embed.set_footer(text="omnisDEC Software ENDEC Version 0.10")

    webhook = DiscordWebhook(url=webhook_url)
    webhook.add_embed(embed)
    webhook.execute()


def encode(header, filename, stream):
    global wait_event

    if wait_event.is_set():
        print("Alert is being relayed. Waiting...")
        wait_event.wait()  # Wait for the wait_event to be set (alert relayed)
        wait_event.clear()  # Clear the event for the next alert
        time.sleep(120)  # Wait for 120 seconds

    eas_header = header
    header_segments = eas_header.split("-")
    header_segments[-2] = callsign
    new_eas_header = "-".join(header_segments)
    print("Alert Encoded! Sending alert with SAME header of: " + new_eas_header)
    send_to_discord("no", new_eas_header, True)

    alertAudio = AudioSegment.from_wav(file=filename)  # Import Audio data
    Alert = EASGen.genEAS(
        header=new_eas_header,
        attentionTone=False,
        audio=alertAudio,
        mode="DIGITAL",
        endOfMessage=True,
        sampleRate=32000,
    )  # Generate an EAS SAME message with an ATTN signal, the imported WAV file as the audio, with EOMs, and with a SAGE DIGITAL ENDEC style.

    Alert.set_channels(1).set_sample_width(2)

    wf = Alert._data
    stream.start_stream()
    stream.write(wf)
    stream.stop_stream()
    print("")
    print("EOM Sent! Returning to monitoring for alerts.")


def process_monitor_output(monitor, url, stream):
    while True:
        line = (
            monitor.stdout.readline()
            .decode("utf-8")
            .replace("EAS: ", "")
            .replace("\n", "")
        )
        if "ZCZC-" in line:
            raw_header = line.strip()
            decoded_data = EAS2Text(raw_header)
            print(
                "SAME Header received from soundcard monitor at "
                + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                + "."
            )
            print("Header: " + raw_header)
            print("Decoded EAS Data:")
            print(f"{decoded_data.EASText}")
            send_to_discord(url, raw_header, False)

            output_filename = f"alert_audio_{url.replace(':', '_').replace('/', '_').replace('.', '_')}.wav"

            time.sleep(1.5)
            print("Recording alert!")
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", url, "-f", "wav", output_filename]
            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            while True:
                appended_line = monitor.stdout.readline().decode("utf-8")
                line += appended_line
                if "NNNN" in appended_line:
                    time.sleep(1.5)
                    ffmpeg_process.terminate()
                    break

            ffmpeg_process.communicate()

            print("Alert recorded! Modifying audio...")
            audio = AudioSegment.from_wav(output_filename)

            # Adjust the audio to be divisible by 16 and 24000
            samples = audio.get_array_of_samples()
            frames = len(samples) // audio.channels
            frames -= frames % (16 * 24000)  # Adjust the frames to be divisible
            samples = samples[:frames * audio.channels]
            audio = audio._spawn(samples)

            # Set the frame rate, channels, and sample width
            audio = audio.set_frame_rate(24000).set_channels(1).set_sample_width(2)

            # Save the modified audio
            audio.export(output_filename, format="wav")

            print("Alert modified! Encoding alert!")
            encode(raw_header, output_filename, stream)


def main():
    global wait_event
    global callsign

    callsign = "WINDOWS"  # Change the callsign to whatever you like, as long as it is 8 characters.
    print("Welcome to omnisDEC!")
    wait_event = threading.Event()  # Event to signal waiting
    audio = pyaudio.PyAudio()  # Initialize Pyaudio systems ONCE only.
    stream = audio.open(
        format=audio.get_format_from_width(2), channels=1, rate=32000, output=True
    )  # Create a stream at 32K sample rate, 16-bit width, and 1 channel.

    path = os.getcwd()
    # Start the monitor
    mon1 = subprocess.Popen([f"{path}/mon1.bat"], stdout=subprocess.PIPE)
    mon2 = subprocess.Popen([f"{path}/mon2.bat"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("Now monitoring monitors for alerts!")


    # Create threads for processing the output of each monitor
    thread1 = threading.Thread(
        target=process_monitor_output,
        args=(mon1, "https://icecast.gwes-eas.network/ERN-JON", stream),
    )
    thread2 = threading.Thread(
        target=process_monitor_output, args=(mon2, "https://icecast.gwes-eas.network/ERN-CRTV", stream)
    )

    # Start the threads
    thread1.start()
    thread2.start()

    # Wait for the threads to finish
    thread1.join()
    thread2.join()

    stream.stop_stream()
    stream.close()
    audio.terminate()


if __name__ == "__main__":
    main()
