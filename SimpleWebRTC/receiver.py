'''
Version: 1.2.0
Authors: @alirezashirmarz
email: ashirmarz@ufscar.br
Name: Receiving server (Simple WebRTC Setup)
'''

import asyncio, websockets, gi, json, time
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp

Gst.init(None)

class Receiver:
    def __init__(self):
        self.webrtc = Gst.ElementFactory.make("webrtcbin", "recv")
        self.pipe = Gst.Pipeline.new("pipe")
        self.pipe.add(self.webrtc)

        # ✅ ADD HERE (right after creating webrtcbin)
        #self.webrtc.connect("on-incoming-rtcp", self.on_rtcp)

    async def run(self):
        self.loop = asyncio.get_running_loop()
        # just change it to server IP and Port, so that's enough!
        self.ws = await websockets.connect("ws://127.0.0.1:8765")

        self.webrtc.connect("pad-added", self.on_pad)
        self.webrtc.connect("on-ice-candidate", self.on_ice)

        self.pipe.set_state(Gst.State.PLAYING)
        asyncio.create_task(self.stats_loop())

        #####################################
        # ✅ WAIT for pads to be created
        #await asyncio.sleep(2)

        # ✅ DEBUG: print pad names
        '''print("WebRTC pads:", [p.get_name() for p in self.webrtc.pads])

        # ✅ attach RTCP probe (try common names)
        rtcp_pad = (
            self.webrtc.get_static_pad("recv_rtcp_src_0") or
            self.webrtc.get_static_pad("rtcp_src_0")
        )

        if rtcp_pad:
            print("RTCP pad found:", rtcp_pad.get_name())
            rtcp_pad.add_probe(Gst.PadProbeType.BUFFER, self.on_rtcp)
        else:
            print("RTCP pad NOT found")'''
        #####################################

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
 

    def on_pad(self, webrtc, pad):
        pad_name = pad.get_name()
        print("NEW PAD:", pad_name)

        if not hasattr(self, "stats_started"):
            print("Starting stats loop...")
            asyncio.create_task(self.stats_loop())
            self.stats_started = True

        # -------- RTCP --------
        if "rtcp" in pad_name:
            print("🎯 RTCP PAD DETECTED:", pad_name)

            if not hasattr(self, "rtcp_attached"):
                pad.add_probe(Gst.PadProbeType.BUFFER, self.on_rtcp)
                self.rtcp_attached = True

            return
 
    def on_pad(self, webrtc, pad):
        print("NEW PAD:", pad.get_name())

        # ✅ attach probe HERE (before depay)
        pad.add_probe(Gst.PadProbeType.BUFFER, self.on_buffer)

        print("Receiving video...")

        depay = Gst.ElementFactory.make("rtph264depay")
        dec = Gst.ElementFactory.make("avdec_h264")
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


    def on_buffer(self, pad, info):
        buf = info.get_buffer()
        size = buf.get_size()

        # ✅ FIRST: extract data
        data = buf.extract_dup(0, buf.get_size())
        # RTP marker bit → frame detection
        marker = (data[1] >> 7) & 0x01

        # RTP timestamp (32-bit)
        rtp_ts = int.from_bytes(data[4:8], "big")
        
        if not hasattr(self, "last_ts"):
            self.last_ts = None

        if marker == 1:   # only at end of frame
            '''
            if self.last_ts is not None:

                ts_diff = (rtp_ts - self.last_ts) & 0xFFFFFFFF  # handle wrap
                ifg_server = ts_diff / 90000.0

                print(f"[IFG_server] {ifg_server*1000:.2f} ms")

            self.last_ts = rtp_ts
            '''
            now = time.time()

            # --- IFG_actual ---
            if hasattr(self, "last_arrival") and self.last_arrival is not None:
                ifg_actual = now - self.last_arrival
            else:
                ifg_actual = None

            # --- IFG_server ---
            if self.last_ts is not None:
                ts_diff = (rtp_ts - self.last_ts) & 0xFFFFFFFF
                ifg_server = ts_diff / 90000.0
            else:
                ifg_server = None

            # --- PRINT ---
            if ifg_actual is not None and ifg_server is not None:
                delta_ifg = ifg_actual - ifg_server

                print(f"[IFG] actual={ifg_actual*1000:.2f} ms | server={ifg_server*1000:.2f} ms | Δ={delta_ifg*1000:.2f} ms")

            # update
            self.last_arrival = now
            self.last_ts = rtp_ts


        #rtp_time_sec = rtp_ts / 90000.0
        #print(f"[RTP] TS={rrtp_time_sec}")



        if not hasattr(self, "cnt"):
            self.cnt = 0
            self.bytes = 0
            self.t0 = time.time()

        # ✅ count frames ONLY
        if marker == 1:
            self.cnt += 1

        self.bytes += size

        dt = time.time() - self.t0

        if dt > 1:
            fps = self.cnt / dt
            bitrate = (self.bytes * 8) / dt / 1000

            print(f"[STATS] FPS={fps:.2f}  Bitrate={bitrate:.1f} kbps")

            self.cnt = 0
            self.bytes = 0
            self.t0 = time.time()

        return Gst.PadProbeReturn.OK
 

    def on_ice(self, webrtc, mline, candidate):
        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({"ice": candidate})),
            self.loop
        )
    '''
    async def stats_loop(self):
        while True:
            await asyncio.sleep(2)

            promise = Gst.Promise.new()
            self.webrtc.emit("get-stats", None, promise)

            reply = promise.get_reply()
            self.handle_stats(reply)
    '''

    async def stats_loop(self):
        while True:
            await asyncio.sleep(2)

            promise = Gst.Promise.new()
            self.webrtc.emit("get-stats", None, promise)

            promise.wait()

            reply = promise.get_reply()

            if reply is None:
                continue

            self.handle_stats(reply)


    def handle_stats(self, reply):
        if reply is None:
            return
        
        stats = reply.get_value("stats")
        print("STATS RAW:", stats)

        if stats is None:
            return

        for s in stats:
            if "type" not in s:
                continue

            if s["type"] == "transport":
                rtt = s.get("round-trip-time")
                if rtt is not None:
                    print(f"[GCC] RTT={rtt:.4f}s")

            if s["type"] == "inbound-rtp":
                lost = s.get("packets-lost")
                jitter = s.get("jitter")

                print(f"[GCC] loss={lost} jitter={jitter}")
                
    



asyncio.run(Receiver().run())

