# test_client.py

import os
import socketio

#create a socket.io client object here
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=10,
    reconnection_delay=1,
    reconnection_delay_max=5,
)

#create an event handler for 'connect' that prints a message
#and sends a "start_game" event to the backend
@sio.event
def connect():
    print("[client] connected")
    payload = {"grid_width": 20, "grid_height": 20, "starting_tick": 150}
    sio.emit("start_game", payload)

    # speed up to 75 ms
    sio.emit("change_delay", {"ms": 75})


#handle the server's initial ack (optional)
@sio.on("connected")
def connected(data):
    print(f"[client] server connected ack: {data}")

#create an event handler for 'game_state' that prints the game state
@sio.on("game_state")
def game_state(data):
    score = data.get("score")
    tick = data.get("game_tick")
    gw = data.get("grid_width")
    gh = data.get("grid_height")
    print(f"[state] score={score} tick={tick} grid={gw}x{gh}")

#create an event handler for 'disconnect' that prints something like "disconnected"
@sio.event
def disconnect():
    print("[client] disconnected")

#main function to run the client
def main():
    #connect to the backend; tries common defaults unless BACKEND_URL is set
    backend_url = os.getenv("BACKEND_URL")
    candidates = [backend_url] if backend_url else [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8765",
    ]

    last_err = None
    for target in candidates:
        try:
            print(f"[client] connecting to {target} ...")
            #allow both websocket and polling; websocket preferred
            sio.connect(target, transports=["websocket", "polling"])
            break
        except Exception as e:
            print(f"[client] failed to connect to {target}: {e}")
            last_err = e
    else:
        print(f"[client] unable to connect to any target: {last_err}")
        return

    try:
        #keep the client alive to receive updates
        sio.wait()
    except KeyboardInterrupt:
        print("[client] stopping...")
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()
