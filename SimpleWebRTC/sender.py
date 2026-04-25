'''
Version: 1.2.0
Authors: @alirezashirmarz
email: ashirmarz@ufscar.br
Name: Streaming Server (Simple WebRTC Setup)
'''

import asyncio, websockets, gi, json
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp

Gst.init(None)

## Encoder Configuration (Default values)
ENCODER_CONFIG = {
    "codec": "h264",   # vp8 / h264

    # common
    "bitrate": 3000,        # kbps (h264) / bps (vp8)
    "fps": 24,
    "gop": 30,              # keyframe interval
    "width": 640,
    "height": 480,

    # h264 specific
    "preset": "ultrafast",
    "tune": "zerolatency",
    "bframes": 0,

    # Quantization Parameter (QP)
    "qp_min": 70,
    "qp_max": 80,

    # vp8 specific
    "deadline": 1,
    "cpu_used": 4
}
cfg = ENCODER_CONFIG  # define the object from the dictionary!


## Video Codec/Source Selection + Files for straming! 
CODEC = "h264"   # change here: vp8 / h264
SOURCE = "files"   # test / webcam / files
MY_PNG = "/home/alireza/mycg/CGReplay/Sources/Kombat/%04d.png"
WIDTH , HEIGHT = cfg["width"] , cfg["height"] 
FPS = cfg["fps"] # this only used for files state

"""
# Encoder configuration:
    ENCODER_CONFIG["bitrate"] = 2000
    ENCODER_CONFIG["gop"] = 60
    ENCODER_CONFIG["fps"] = 60
    ENCODER_CONFIG["width"] = 1280
    ENCODER_CONFIG["height"] = 720
"""

## Source of streaming 
if SOURCE == "test":
    SRC = f"videotestsrc is-live=true ! video/x-raw,width={WIDTH},height={HEIGHT}"

elif SOURCE == "webcam":
    SRC = f"v4l2src ! videoconvert ! videoscale ! video/x-raw,width={WIDTH},height={HEIGHT}"

elif SOURCE == "files":
    #SRC = f"multifilesrc location={MY_PNG} start-index=1 loop=true caps=image/png,framerate=30/1 ! pngdec ! videoconvert ! videoscale ! videorate ! video/x-raw,framerate=30/1,width={WIDTH},height={HEIGHT} ! queue ! identity sync=true ! videorate"
    #SRC = f"multifilesrc location={MY_PNG} start-index=1 loop=true caps=image/png,framerate=30/1 ! pngdec ! videoconvert ! videoscale ! videorate ! video/x-raw,framerate=30/1,width={WIDTH},height={HEIGHT} ! queue leaky=2 max-size-buffers=1 ! identity sync=true"
    SRC = f"multifilesrc location={MY_PNG} start-index=1 loop=true caps=image/png,framerate={FPS}/1 ! pngdec ! videoconvert ! videoscale ! videorate ! video/x-raw,framerate={FPS}/1,width={WIDTH},height={HEIGHT} ! queue leaky=2 max-size-buffers=1 ! identity sync=true"


if cfg["codec"] == "h264":
    ENC = (
        f"x264enc "  # CPU-only -> "x264enc" | GPU (NVIDIA) -> "nvh264enc"  | GPU (Intel) -> "vaapih264enc" 
        f"bitrate={cfg['bitrate']} "
        f"key-int-max={cfg['gop']} "
        f"qp-min={cfg['qp_min']} "
        f"qp-max={cfg['qp_max']} "
        f"speed-preset={cfg['preset']} "
        f"tune={cfg['tune']} "
        f"bframes={cfg['bframes']} ! "
        f"rtph264pay config-interval=1"
    )

    CAPS = "application/x-rtp,media=video,encoding-name=H264,payload=96"


elif cfg["codec"] == "vp8":
    ENC = (
        f"vp8enc "
        f"target-bitrate={cfg['bitrate']*1000} "
        f"keyframe-max-dist={cfg['gop']} "
        f"deadline={cfg['deadline']} "
        f"cpu-used={cfg['cpu_used']} ! "
        f"rtpvp8pay"
    )

    CAPS = "application/x-rtp,media=video,encoding-name=VP8,payload=96"



"""
## Encoder & Caps
# codec part
if CODEC == "vp8":
    ENC = "vp8enc deadline=1 ! rtpvp8pay"
    CAPS = "application/x-rtp,media=video,encoding-name=VP8,payload=96"

elif CODEC == "h264":
    ENC = "x264enc tune=zerolatency bitrate=1000 speed-preset=ultrafast ! rtph264pay config-interval=1"
    CAPS = "application/x-rtp,media=video,encoding-name=H264,payload=96"
"""
##########################################################################################

PIPE = f"""
webrtcbin name=send bundle-policy=max-bundle
{SRC} ! {ENC} ! {CAPS} ! send.
""".replace("\n", " ")

"""
PIPE = f'''
webrtcbin name=send bundle-policy=max-bundle
{SRC} ! {ENC} ! {CAPS} ! send.
'''
"""

"""
if CODEC == "vp8":
    PIPE = '''
    webrtcbin name=send bundle-policy=max-bundle
    videotestsrc is-live=true !
    vp8enc !
    rtpvp8pay !
    application/x-rtp,media=video,encoding-name=VP8,payload=96 !
    send.
    '''
elif CODEC == "h264":
    PIPE = '''
    webrtcbin name=send bundle-policy=max-bundle
    videotestsrc is-live=true !
    x264enc tune=zerolatency bitrate=1000 speed-preset=ultrafast !
    rtph264pay config-interval=1 !
    application/x-rtp,media=video,encoding-name=H264,payload=96 !
    send.
    '''
"""

#PIPE = """
#webrtcbin name=send bundle-policy=max-bundle
#videotestsrc is-live=true !
#vp8enc !
#rtpvp8pay !
#application/x-rtp,media=video,encoding-name=VP8,payload=96 !
#send.
#"""

class Sender:
    def __init__(self):
        self.pipe = Gst.parse_launch(PIPE)
        self.webrtc = self.pipe.get_by_name("send")

    async def run(self):
        self.loop = asyncio.get_running_loop()
        # just change it to server IP and Port, so that's enough!
        self.ws = await websockets.connect("ws://127.0.0.1:8765")

        self.webrtc.connect("on-negotiation-needed", self.on_negotiation)
        self.webrtc.connect("on-ice-candidate", self.on_ice)

        self.pipe.set_state(Gst.State.PLAYING)

        async for msg in self.ws:
            data = json.loads(msg)
            if "answer" in data:
                self.set_remote(data["answer"])
            elif "ice" in data:
                self.webrtc.emit("add-ice-candidate", 0, data["ice"])

    def on_negotiation(self, element):
        promise = Gst.Promise.new_with_change_func(self.on_offer, None, None)
        element.emit("create-offer", None, promise)

    def on_offer(self, promise, *_):
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value("offer")

        print("OFFER SDP:\n", offer.sdp.as_text())

        self.webrtc.emit("set-local-description", offer, Gst.Promise.new())

        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({"offer": offer.sdp.as_text()})),
            self.loop
        )

    def set_remote(self, sdp):
        res, msg = GstSdp.SDPMessage.new()
        GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), msg)

        answer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.ANSWER, msg)

        self.webrtc.emit("set-remote-description", answer, Gst.Promise.new())

    def on_ice(self, _, mline, candidate):
        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({"ice": candidate})),
            self.loop
        )

asyncio.run(Sender().run())