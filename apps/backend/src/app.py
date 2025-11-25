import asyncio
import time
import socketio
from pathlib import Path
from datetime import datetime
from aiohttp import web
from typing import Any, Dict
from game import Game

#ALLOWED_ORIGINS = ["http://localhost:3000/"]

#keep star for now to allow all connections
sio = socketio.AsyncServer(async_mode="aiohttp", cors_allowed_origins="*")
#init web app
app = web.Application() 
#server io connected to app
sio.attach(app) 


#Create a socketio event handler for when clients connect
@sio.event
#sid = session id, enviorn = HTTP request environment
async def connect(sid: str, environ: Dict[str, Any]) -> None:
    """Handle client connections - called when a frontend connects to the server"""
    #if a proxy set the header, use that IP. Otherwise use REMOTE_ADDR.
    x_forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for and x_forwarded_for.strip():
        client_ip_address = x_forwarded_for.split(",", 1)[0].strip()
    else:
        client_ip_address = environ.get("REMOTE_ADDR", "unknown")
    #log who connected and from where.
    print(f"[connect] client_sid={sid} client_ip={client_ip_address}")

    #set up this client's session. The game starts later in start_game.
    session_data = {
        "game": None,
        "agent": None,
        "statistics": {"games": 0, "best_score": 0, "avg_score": 0.0},
        "connected_at": time.time(),
        "update_task": None,
    }
    await sio.save_session(sid, session_data)

    #message to client
    await sio.emit("connected", {"sid": sid}, to=sid)


#Create a socketio event handler for when clients disconnect
@sio.event
async def disconnect(sid: str) -> None:
    """Handle client disconnections - cleanup any resources"""
    #print a message showing which client disconnected
    print(f"[disconnect] client_sid={sid} disconnected")

    #clean up any game sessions or resources for this client
    #get this client's session (if it exists).
    try:
        client_session: Dict[str, Any] = await sio.get_session(sid)
    except KeyError:
        #no session stored (nothing to clean up)
        return

    #stop the game loop if it's running.
    game_update_task = client_session.get("update_task")
    if game_update_task is not None:
        if not game_update_task.done():
            game_update_task.cancel()
            try:
                await game_update_task
            except asyncio.CancelledError:
                pass

    #log how long they stayed and any stats.
    client_statistics = client_session.get("statistics") or {}
    connected_at_ts = client_session.get("connected_at")
    if isinstance(connected_at_ts, (int, float)):
        session_lifetime_seconds = time.time() - connected_at_ts
        print(f"[disconnect] sid={sid} lifetime={session_lifetime_seconds:.2f}s stats={client_statistics}")
    else:
        print(f"[disconnect] sid={sid} stats={client_statistics}")

    #drop references to objects to help GC
    client_session["game"] = None
    client_session["agent"] = None
    #no need to re-save the session; Socket.IO will discard it after disconnect
    


# TODO: Create a socketio event handler for starting a new game
@sio.event
async def start_game(sid: str, data: Dict[str, Any]) -> None:
    #1. parse optional params from the client
    data = data or {}  # handle None payloads safely
    def to_pos_int(v):
        try:
            iv = int(v)
            return iv if iv > 0 else None
        except (TypeError, ValueError):
            return None

    grid_width  = to_pos_int(data.get("grid_width"))
    grid_height = to_pos_int(data.get("grid_height"))
    starting_ms = to_pos_int(data.get("starting_tick"))  # ms per tick

    #2. new game and apply config if provided
    # inside start_game, after you set grid_width / grid_height
    game = Game()
    if grid_width is not None:  game.grid_width  = grid_width
    if grid_height is not None: game.grid_height = grid_height

    # re-seed snake and food for the new grid
    if hasattr(game, "reset"):
        game.reset()

    # reapply tick if provided
    if starting_ms is not None:
        game.game_tick = starting_ms / 1000.0

    #3. optional AI later
    agent = None

    #4. save in the Socket.IO session, cancel any previous loop
    session = await sio.get_session(sid)
    prev = session.get("update_task")
    if prev is not None and not prev.done():
        prev.cancel()
        try:
            await prev
        except asyncio.CancelledError:
            pass

    session["game"] = game
    session["agent"] = agent
    await sio.save_session(sid, session)

    #send the first snapshot so the UI can draw
    await sio.emit("game_state", game.to_dict(), to=sid)

    #start the game loop in the background.
    task = asyncio.create_task(update_game(sid))
    session["update_task"] = task
    await sio.save_session(sid, session)

#Create event handlers for saving/loading AI models
@sio.event
async def save_model(sid: str, data: Dict[str, Any]) -> None:
    """save the current agent to disk"""
    session: Dict[str, Any] = await sio.get_session(sid)
    agent = session.get("agent")
    #must have an agent to save.
    if agent is None:
        await sio.emit("model_error", {"error": "No agent for this session. Start a game with AI first."}, to=sid)
        return

    #where to save
    target_dir = data.get("dir") or data.get("directory") or "checkpoints"
    tag = data.get("tag")
    filename = data.get("filename")
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    #default filename if none given.
    if not filename:
        time_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = "snake_agent"
        if tag:
            base += f"_{tag}"
        filename = f"{base}_{time_tag}.bin"

    filepath = str(Path(target_dir) / filename)

    #use agent.save() or model.save() if available
    model = getattr(agent, "model", None)
    try:
        if callable(getattr(agent, "save", None)):
            agent.save(filepath)
        elif model is not None and callable(getattr(model, "save", None)):
            model.save(filepath)
        else:
            await sio.emit("model_error", {"error": "No save() found on agent or agent.model."}, to=sid)
            return
    except Exception as e:
        await sio.emit("model_error", {"error": f"save failed: {type(e).__name__}: {e}"}, to=sid)
        return
    #send the save path back to the client
    await sio.emit("model_saved", {"path": filepath}, to=sid)


@sio.event
async def load_model(sid: str, data: Dict[str, Any]) -> None:
    """load a saved agent from disk """
    session: Dict[str, Any] = await sio.get_session(sid)
    agent = session.get("agent")
    #must have an agent to load into.
    if agent is None:
        await sio.emit("model_error", {"error": "No agent for this session. Start a game with AI first."}, to=sid)
        return
    #need a valid file path
    checkpoint_path = data.get("path") or data.get("filepath") or data.get("file")
    if not checkpoint_path:
        await sio.emit("model_error", {"error": "Missing 'path' to checkpoint."}, to=sid)
        return
    if not Path(checkpoint_path).exists():
        await sio.emit("model_error", {"error": f"File not found: {checkpoint_path}"}, to=sid)
        return
    #use agent.load() or model.load() if available.
    model = getattr(agent, "model", None)
    try:
        if callable(getattr(agent, "load", None)):
            agent.load(checkpoint_path)
        elif model is not None and callable(getattr(model, "load", None)):
            model.load(checkpoint_path)
        else:
            await sio.emit("model_error", {"error": "No load() method found on agent or agent.model."}, to=sid)
            return
    except Exception as e:
        await sio.emit("model_error", {"error": f"load failed: {type(e).__name__}: {e}"}, to=sid)
        return
    #confirm success
    await sio.emit("model_loaded", {"path": checkpoint_path}, to=sid)
    
async def handle_ping(request: Any) -> Any:
    """Simple ping endpoint to keep server alive and check if it's running"""
    return web.json_response({"message": "pong"})

#keep snake length tied to score
def _sync_length_with_score(game: Any) -> None:
    try:
        body = list(getattr(game.snake, "body", []))
        target = max(1, int(getattr(game, "score", 0)) + 1)
        if not body:
            return
        if len(body) < target:
            tail = body[-1]
            body.extend([tail] * (target - len(body)))
        elif len(body) > target:
            body = body[:target]
        game.snake.body = body
    except Exception:
        pass

#attach session flags to payload
def _state_payload(game: Any, session: Dict[str, Any]) -> Dict[str, Any]:
    state = game.to_dict()
    state["god_mode"] = bool(session.get("god_mode", False))
    return state

#event: set score to an explicit value
@sio.event
async def set_score(sid: str, data: Dict[str, Any]) -> None:
    session: Dict[str, Any] = await sio.get_session(sid)
    game = session.get("game")
    if game is None:
        return
    try:
        val = int((data or {}).get("score", 0))
    except Exception:
        val = 0
    game.score = max(0, val)
    _sync_length_with_score(game)
    await sio.emit("game_state", _state_payload(game, session), to=sid)

#event: increase score by 1
@sio.event
async def inc_score(sid: str) -> None:
    session: Dict[str, Any] = await sio.get_session(sid)
    game = session.get("game")
    if game is None:
        return
    game.score = int(getattr(game, "score", 0)) + 1
    _sync_length_with_score(game)
    await sio.emit("game_state", _state_payload(game, session), to=sid)

#event: decrease score by 1
@sio.event
async def dec_score(sid: str) -> None:
    session: Dict[str, Any] = await sio.get_session(sid)
    game = session.get("game")
    if game is None:
        return
    game.score = max(0, int(getattr(game, "score", 0)) - 1)
    _sync_length_with_score(game)
    await sio.emit("game_state", _state_payload(game, session), to=sid)
    
#event: toggle god mode flag in session
@sio.event
async def toggle_god_mode(sid: str) -> None:
    session: Dict[str, Any] = await sio.get_session(sid)
    session["god_mode"] = not bool(session.get("god_mode", False))
    await sio.save_session(sid, session)
    game = session.get("game")
    if game is not None:
        await sio.emit("game_state", _state_payload(game, session), to=sid)

@sio.event
async def change_delay(sid: str, data: Dict[str, Any]) -> None:
    """change the game tick duration"""
    data = data or {}
    # accept seconds or milliseconds
    seconds = data.get("seconds")
    ms = data.get("ms") or data.get("milliseconds") or data.get("delay_ms") or data.get("tick_ms")

    try:
        if seconds is not None:
            new_tick = float(seconds)
        elif ms is not None:
            new_tick = float(ms) / 1000.0
        else:
            return
    except (TypeError, ValueError):
        return

    # clamp to something reasonable
    if new_tick <= 0:
        return

    session = await sio.get_session(sid)
    game = session.get("game")
    if game is None:
        return

    game.game_tick = new_tick
    # optional ack back to this client
    await sio.emit("delay_changed", {"game_tick": game.game_tick}, to=sid)
    #Create a socketio event handler for direction input
@sio.event
async def change_direction(sid: str, data: Dict[str, Any]) -> None:
    """client requested a direction change"""
    data = data or {}
    direction = data.get("direction")
    if not isinstance(direction, str):
        return

    session = await sio.get_session(sid)
    game = session.get("game")
    if game is None or not hasattr(game, "queue_change"):
        return

    game.queue_change(direction.upper())
    print(f"[input] sid={sid} dir={direction}")

@sio.event
async def replay_game(sid: str) -> None:
    """reset the current game or start a fresh one, then ensure the loop is running"""
    session: Dict[str, Any] = await sio.get_session(sid)
    prev_game = session.get("game")

    if prev_game and callable(getattr(prev_game, "reset", None)):
        prev_game.reset()
        game = prev_game
    else:
        # carry forward basic settings if possible
        gw = int(getattr(prev_game, "grid_width", 20) or 20)
        gh = int(getattr(prev_game, "grid_height", 20) or 20)
        tick = float(getattr(prev_game, "game_tick", 0.15) or 0.15)

        game = Game()
        game.grid_width = gw
        game.grid_height = gh
        game.game_tick = tick

        session["game"] = game

    # make sure there is visible food right away (in case reset/init skipped it)
    try:
        if hasattr(game, "food") and hasattr(game.food, "spawn_food"):
            game.food.eaten = True
            game.food.spawn_food()
    except Exception:
        pass

    await sio.save_session(sid, session)
    await sio.emit("game_state", game.to_dict(), to=sid)

    # if the old loop ended (e.g., after game over), spin a new one
    task = session.get("update_task")
    if task is None or task.done():
        session["update_task"] = asyncio.create_task(update_game(sid))
        await sio.save_session(sid, session)

# TODO: Implement the main game loop
async def update_game(sid: str) -> None:
    """Main game loop - runs continuously while the game is active"""
    while True:
        #stop if the client session is gone.
        try:
            session: Dict[str, Any] = await sio.get_session(sid)
        except KeyError:
            return

        #current state for this client.
        game = session.get("game")
        agent = session.get("agent")

        #no game means nothing to run.
        if game is None:
            return

        #stop if the game ended.
        if hasattr(game, "running") and not game.running:
            return

        #let the agent choose a move if present.
        if agent is not None and callable(getattr(agent, "get_action", None)):
            try:
                #numeric state for agents (guard if to_vector isn't implemented)
                if callable(getattr(game, "to_vector", None)):
                    state_vector = game.to_vector()
                else:
                    state_vector = game.to_dict()
                action = agent.get_action(state_vector)

                #string action: "UP"/"DOWN"/"LEFT"/"RIGHT"
                if isinstance(action, str) and hasattr(game, "queue_change"):
                    game.queue_change(action)

                #action: [1,0,0]=straight, [0,1,0]=right, [0,0,1]=left
                elif isinstance(action, (list, tuple)) and len(action) == 3:
                    if action[1] == 1 and hasattr(game, "queue_change"):
                        game.queue_change("RIGHT")
                    elif action[2] == 1 and hasattr(game, "queue_change"):
                        game.queue_change("LEFT")
                    #straight = no direction change
            except Exception:
                #keep the loop alive even if the agent throws.
                pass

        #advance one frame (handles input queue, movement, food, timing).
        prev_score = getattr(game, "score", 0)
        game.step()
        new_score = getattr(game, "score", 0)

        #if score dropped back to 0 from a positive value, log a reset
        if prev_score > 0 and new_score == 0:
            print(f"[game] sid={sid} reset (score -> 0)")

        #save session (keeps dict consistent if references change).
        session["game"] = game
        await sio.save_session(sid, session)

        #send the latest state to the client.
        #wrap collisions and ignore death if god mode
        if bool(session.get("god_mode", False)):
            try:
                #wrap head into bounds
                if hasattr(game, "snake") and getattr(game.snake, "body", None):
                    W = int(getattr(game, "grid_width", 0))
                    H = int(getattr(game, "grid_height", 0))
                    hx, hy = game.snake.body[0]
                    nx = (hx % W) if W > 0 else hx
                    ny = (hy % H) if H > 0 else hy
                    if (nx, ny) != (hx, hy):
                        game.snake.body[0] = (nx, ny)
                    #cut self-collision: keep up to the first head hit
                    for i in range(1, len(game.snake.body)):
                        if game.snake.body[i] == (nx, ny):
                            game.snake.body = game.snake.body[:i]
                            break
                #force game alive
                if hasattr(game, "running"):
                    game.running = True
            except Exception:
                pass
        #send the latest state to the client with flags
        await sio.emit("game_state", _state_payload(game, session), to=sid)

        #wait for the next frame. game_tick is in seconds.
        tick_seconds = float(getattr(game, "game_tick", 0.03))
        await asyncio.sleep(max(0.0, tick_seconds))

        


# TODO: Helper function for AI agent interaction with game
async def update_agent_game_state(game: Game, agent: Any) -> None:
    """Handle AI agent decision making and training"""

    #no agent or game means nothing to do
    if agent is None or game is None:
        return

    #get current state for the agent
    if callable(getattr(agent, "get_state", None)):
        state_old = agent.get_state(game)
    elif callable(getattr(game, "to_vector", None)):
        state_old = game.to_vector()
    else:
        g = game.to_dict()
        state_old = [g.get("grid_width"), g.get("grid_height"), g.get("score")]

    #have the agent choose an action (forward, left, right) with safe fallback
    if callable(getattr(agent, "get_action", None)):
        action = agent.get_action(state_old)
    else:
        action = [1, 0, 0]  # straight

    #convert the action to a game direction and apply it
    if isinstance(action, str) and hasattr(game, "queue_change"):
        game.queue_change(action)
    elif isinstance(action, (list, tuple)) and len(action) == 3 and hasattr(game, "queue_change"):
        if action[1] == 1:
            game.queue_change("RIGHT")
        elif action[2] == 1:
            game.queue_change("LEFT")
        #straight -> no change

    #step the game forward one frame
    prev_score = getattr(game, "score", 0)
    game.step()
    done = (hasattr(game, "running") and not game.running)

    #calculate a reward signal
    if callable(getattr(agent, "calculate_reward", None)):
        reward = agent.calculate_reward(game, done)
    else:
        #basic reward: +10 on score increase, -10 on death, else 0
        reward = 10 if getattr(game, "score", 0) > prev_score else (-10 if done else 0)

    #get new state after the action
    if callable(getattr(agent, "get_state", None)):
        state_new = agent.get_state(game)
    elif callable(getattr(game, "to_vector", None)):
        state_new = game.to_vector()
    else:
        g = game.to_dict()
        state_new = [g.get("grid_width"), g.get("grid_height"), g.get("score")]

    #train short-term on this step (s, a, r, s', done)
    if callable(getattr(agent, "train_short_memory", None)):
        agent.train_short_memory(state_old, action, reward, state_new, done)

    #store experience in replay memory
    if callable(getattr(agent, "remember", None)):
        agent.remember(state_old, action, reward, state_new, done)

    #if episode ended, do long-term updates and prep next round
    if done:
        if callable(getattr(agent, "train_long_memory", None)):
            agent.train_long_memory()

        #update simple statistics if the agent tracks them
        stats = getattr(agent, "statistics", None)
        if isinstance(stats, dict):
            stats["games"] = stats.get("games", 0) + 1
            cur = getattr(game, "score", 0)
            best = stats.get("best_score", 0)
            total = stats.get("total_score", 0) + cur
            games = stats["games"]
            stats["total_score"] = total
            stats["best_score"] = max(best, cur)
            stats["avg_score"] = (total / games) if games else 0.0
        elif hasattr(agent, "n_games"):
            try:
                agent.n_games += 1
            except Exception:
                pass

        #reset the game if supported
        if callable(getattr(game, "reset", None)):
            game.reset()


# TODO: Main server startup function
async def main() -> None:
    """start the web server and socketio server"""
    #add the ping endpoint to the web app router
    #ok if already added elsewhere; ignore duplicates
    try:
        app.router.add_get("/ping", handle_ping)
    except Exception:
        pass

    #create and configure the web server runner
    runner = web.AppRunner(app)
    await runner.setup()

    #start the server on the appropriate host and port
    import os
    host = os.getenv("HOST", "0.0.0.0")
    try:
        port = int(os.getenv("PORT", "8080"))
    except ValueError:
        port = 8080
    print(f"[server] starting on http://{host}:{port} ...")  # early print
    site = web.TCPSite(runner, host=host, port=port)

    try:
        await site.start()

        #print server startup message
        print(f"[server] listening on http://{host}:{port}")

        #keep the server running indefinitely
        await asyncio.Event().wait()

    except asyncio.CancelledError:
        #shutdown requested; exit cleanly
        pass
    except Exception as e:
        #handle any errors gracefully
        print(f"[server] error: {type(e).__name__}: {e}")
        raise
    finally:
        #always clean up the runner
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
