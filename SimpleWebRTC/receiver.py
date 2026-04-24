'''
Version: 1.2.0
Authors: @alirezashirmarz
email: ashirmarz@ufscar.br
Name: Receiving server (Simple WebRTC Setup)
'''

import asyncio, websockets, gi, json
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp

Gst.init(None)

class Receiver:
    def __init__(self):
        self.webrtc = Gst.ElementFactory.make("webrtcbin", "recv")
        self.pipe = Gst.Pipeline.new("pipe")
        self.pipe.add(self.webrtc)

    async def run(self):
        self.loop = asyncio.get_running_loop()
        # just change it to server IP and Port, so that's enough!
        self.ws = await websockets.connect("ws://127.0.0.1:8765")

        self.webrtc.connect("pad-added", self.on_pad)
        self.webrtc.connect("on-ice-candidate", self.on_ice)

        self.pipe.set_state(Gst.State.PLAYING)

        async for msg in self.ws:
            data = json.loads(msg)

            if "offer" in data:
                await self.handle_offer(data["offer"])
            elif "ice" in data:
                self.webrtc.emit("add-ice-candidate", 0, data["ice"])

    async def handle_offer(self, sdp):
        res, msg = GstSdp.SDPMessage.new()
        GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), msg)

        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER, msg)
        
        print("RECEIVED SDP:\n", sdp)

        self.webrtc.emit("set-remote-description", offer, Gst.Promise.new())

        promise = Gst.Promise.new_with_change_func(self.on_answer, None, None)
        self.webrtc.emit("create-answer", None, promise)

    def on_answer(self, promise, *_):
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value("answer")

        self.webrtc.emit("set-local-description", answer, Gst.Promise.new())

        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({"answer": answer.sdp.as_text()})),
            self.loop
        )
    """
    def on_pad(self, webrtc, pad):
        print("Receiving video...")

        depay = Gst.ElementFactory.make("rtpvp8depay")
        dec = Gst.ElementFactory.make("vp8dec")
        conv = Gst.ElementFactory.make("videoconvert")
        sink = Gst.ElementFactory.make("autovideosink")

        self.pipe.add(depay, dec, conv, sink)

        depay.link(dec)
        dec.link(conv)
        conv.link(sink)

        pad.link(depay.get_static_pad("sink"))

        depay.sync_state_with_parent()
        dec.sync_state_with_parent()
        conv.sync_state_with_parent()
        sink.sync_state_with_parent()
    """
    def on_pad(self, webrtc, pad):
        print("Receiving video...")

        caps = pad.get_current_caps().to_string()

        if "VP8" in caps:
            depay = Gst.ElementFactory.make("rtpvp8depay")
            dec = Gst.ElementFactory.make("vp8dec")

        elif "H264" in caps:
            depay = Gst.ElementFactory.make("rtph264depay")
            dec = Gst.ElementFactory.make("avdec_h264")

        else:
            print("Unknown codec:", caps)
            return

        conv = Gst.ElementFactory.make("videoconvert")
        sink = Gst.ElementFactory.make("autovideosink")

        self.pipe.add(depay, dec, conv, sink)

        depay.link(dec)
        dec.link(conv)
        conv.link(sink)

        pad.link(depay.get_static_pad("sink"))

        depay.sync_state_with_parent()
        dec.sync_state_with_parent()
        conv.sync_state_with_parent()
        sink.sync_state_with_parent()
    
    



    def on_ice(self, _, mline, candidate):
        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({"ice": candidate})),
            self.loop
        )

asyncio.run(Receiver().run())