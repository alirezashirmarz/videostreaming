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

if CODEC == "vp8":
    PIPE = """
    webrtcbin name=send bundle-policy=max-bundle
    videotestsrc is-live=true !
    vp8enc !
    rtpvp8pay !
    application/x-rtp,media=video,encoding-name=VP8,payload=96 !
    send.
    """

elif CODEC == "h264":
    PIPE = """
    webrtcbin name=send bundle-policy=max-bundle
    videotestsrc is-live=true !
    x264enc tune=zerolatency bitrate=1000 speed-preset=ultrafast !
    rtph264pay config-interval=1 !
    application/x-rtp,media=video,encoding-name=H264,payload=96 !
    send.
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