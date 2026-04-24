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


CODEC = "h264"   # change here: vp8 / h264
SOURCE = "files"   # test / webcam / files
MY_PNG = "/home/alireza/mycg/CGReplay/Sources/Kombat/%04d.png"
WIDTH , HEIGHT = 640 , 480
# HEIGHT = 480

if SOURCE == "test":
    SRC = f"videotestsrc is-live=true ! video/x-raw,width={WIDTH},height={HEIGHT}"

elif SOURCE == "webcam":
    SRC = f"v4l2src ! videoconvert ! videoscale ! video/x-raw,width={WIDTH},height={HEIGHT}"

elif SOURCE == "files":
    #SRC = f"multifilesrc location={MY_PNG} start-index=1 loop=true caps=image/png,framerate=30/1 ! pngdec ! videoconvert ! videoscale ! videorate ! video/x-raw,framerate=30/1,width={WIDTH},height={HEIGHT} ! queue ! identity sync=true ! videorate"
    SRC = f"multifilesrc location={MY_PNG} start-index=1 loop=true caps=image/png,framerate=30/1 ! pngdec ! videoconvert ! videoscale ! videorate ! video/x-raw,framerate=30/1,width={WIDTH},height={HEIGHT} ! queue leaky=2 max-size-buffers=1 ! identity sync=true"



"""
if SOURCE == "test":
    SRC = "videotestsrc is-live=true"

elif SOURCE == "webcam":
    SRC = "v4l2src ! videoconvert"

elif SOURCE == "files":
    SRC = f'''
    multifilesrc location={MY_PNG} start-index=1 loop=true caps=image/png,framerate=30/1 !
    pngdec !
    videoconvert !
    videorate !
    video/x-raw,framerate=30/1 !
    queue !
    identity sync=true
    '''
"""
# codec part
if CODEC == "vp8":
    ENC = "vp8enc deadline=1 ! rtpvp8pay"
    CAPS = "application/x-rtp,media=video,encoding-name=VP8,payload=96"

elif CODEC == "h264":
    ENC = "x264enc tune=zerolatency bitrate=1000 speed-preset=ultrafast ! rtph264pay config-interval=1"
    CAPS = "application/x-rtp,media=video,encoding-name=H264,payload=96"


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