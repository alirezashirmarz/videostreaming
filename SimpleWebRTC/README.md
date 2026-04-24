
# Simple WebRTC using Gstreamer


✅ 1. On SERVER machine

    Run:

        python3 server.py

    👉 It listens on:

        ws://0.0.0.0:8765

✅ 2. Find server IP

    Example:

        ip a

👉   suppose:

        192.168.1.10 (Just assumption to understand! use you IP!)

✅ 3. On BOTH sender & receiver

    Change this line:

        self.ws = await websockets.connect("ws://127.0.0.1:8765")

👉      to:

        self.ws = await websockets.connect("ws://192.168.1.10:8765")
    
    ⚠️ Important
        use server IP, NOT localhost
        same port: 8765
    🚀 Run order (different machines)
    
    (1) On SERVER machine:
        python3 server.py

    (2) On RECEIVER machine:
        python3 receiver.py
    
    (3) On SENDER machine:
        python3 sender.py

    🔥 Networking checklist (very important)

        If no connection:

            1. Firewall
                sudo ufw allow 8765
            
            2. Test connectivity

            From client:
                nc 192.168.1.10 8765

            👉 if connects → OK

            💬 Ultra short
            👉 replace 127.0.0.1 with server IP everywhere
            👉 run server first
            
            ⚡ Optional (cleaner)

            In your code:

            SERVER = "ws://192.168.1.10:8765"
            self.ws = await websockets.connect(SERVER)


