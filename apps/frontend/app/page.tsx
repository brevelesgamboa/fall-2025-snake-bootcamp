"use client";

import { useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";

const HEADER_HEIGHT_PX = 64;

export default function Home() {
  // canvas and socket
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const socketRef = useRef<Socket | undefined>(undefined);

  // basic ui flags
  const [, setStarted] = useState(false);
  const [showBrand, setShowBrand] = useState(true);
  const brandTimerRef = useRef<number | null>(null);
  const startedOnceRef = useRef(false);

  // controls ui
  const [scoreBox, setScoreBox] = useState<number>(0);
  const [godMode, setGodMode] = useState<boolean>(false);

  // server snapshots for interpolation
  const lastServerSnakeRef = useRef<[number, number][]>([]);
  const curServerSnakeRef = useRef<[number, number][]>([]);

  // game state mirrors
  const snakeRef = useRef<[number, number][]>([]);
  const foodRef = useRef<[number, number] | null>(null);
  const gridRef = useRef<{ w: number; h: number }>({ w: 20, h: 20 });
  const scoreRef = useRef<number>(0);

  // timing and draw helpers
  const drawRef = useRef<(() => void) | null>(null);
  const tickMsRef = useRef<number>(150);
  const lastUpdateTsRef = useRef<number>(0);
  const trailRef = useRef<{ x: number; y: number; t: number; h: number }[]>([]);

  // graphic vals
  const SNAKE_GLOW_MULT = 1.4;  // bigger means wider glow
  const SNAKE_GLOW_MIN = 2;     // minimum glow blur in px
  const TRAIL_LIFETIME_MS = 350;
  const TRAIL_SIZE_MULT = 0.52; // relative to cell
  const TRAIL_ALPHA = 0.15;

  // set a starting timestamp after mount
  useEffect(() => {
    lastUpdateTsRef.current = performance.now();
  }, []);

  // socket wiring
  useEffect(() => {
    if (socketRef.current !== undefined) return;

    socketRef.current = io("http://localhost:8765", {
      transports: ["websocket"],
      path: "/socket.io",
      withCredentials: false,
    });

    const onConnect = () => {
      socketRef.current?.emit("start_game", {
        grid_width: 20,
        grid_height: 20,
        starting_tick: 125, // ms
      });
    };

    const onUpdate = (data: unknown) => {
      const s = data as any;

      // get next body from server, deep copy to avoid aliasing
      const nextBodyRaw = Array.isArray(s?.snake)
        ? (s.snake as [number, number][])
        : curServerSnakeRef.current;
      const nextBody: [number, number][] = nextBodyRaw.map(([x, y]) => [
        Number(x),
        Number(y),
      ]);

      // previous body is the last current snapshot (deep copy)
      let prevBody: [number, number][] = curServerSnakeRef.current.map(
        ([x, y]) => [x, y]
      );

      // first snapshot case
      if (prevBody.length === 0) {
        prevBody = nextBody.map(([x, y]) => [x, y]);
      }

      // align lengths only when needed
      if (nextBody.length > prevBody.length) {
        const pad = nextBody.length - prevBody.length;
        const tail =
          prevBody[prevBody.length - 1] ??
          nextBody[nextBody.length - 1] ??
          [0, 0];
        prevBody = [...prevBody, ...Array(pad).fill(tail)];
      } else if (nextBody.length < prevBody.length) {
        prevBody = prevBody.slice(0, nextBody.length);
      }

      // roll snapshots
      lastServerSnakeRef.current = prevBody;
      curServerSnakeRef.current = nextBody;

      // mirror plain state too
      snakeRef.current = nextBody;
      gridRef.current = {
        w: Number(s?.grid_width ?? gridRef.current.w),
        h: Number(s?.grid_height ?? gridRef.current.h),
      };
      scoreRef.current = Number(s?.score ?? scoreRef.current);
      setScoreBox(scoreRef.current);
      setGodMode(Boolean(s?.god_mode));

      // food boundary; only if field exists
      if (Object.prototype.hasOwnProperty.call(s, "food")) {
        let fx: number | undefined;
        let fy: number | undefined;

        if (Array.isArray(s.food) && s.food.length === 2) {
          fx = Number(s.food[0]);
          fy = Number(s.food[1]);
        } else if (s.food && typeof s.food === "object") {
          if (Number.isFinite(s.food.x) && Number.isFinite(s.food.y)) {
            fx = Number(s.food.x);
            fy = Number(s.food.y);
          }
        }

        if (Number.isFinite(fx) && Number.isFinite(fy)) {
          const gw = gridRef.current.w;
          const gh = gridRef.current.h;
          const nfx = fx as number; // safe after isFinite
          const nfy = fy as number; // safe after isFinite
          const cx = Math.min(gw - 1, Math.max(0, Math.floor(nfx)));
          const cy = Math.min(gh - 1, Math.max(0, Math.floor(nfy)));
          foodRef.current = [cx, cy];
        } else {
          foodRef.current = null;
        }
      }

      // first state branding once
      if (!startedOnceRef.current) {
        startedOnceRef.current = true;
        setStarted(true);
        if (brandTimerRef.current === null) {
          brandTimerRef.current = window.setTimeout(
            () => setShowBrand(false),
            3000
          );
        }
      }

      // snap canvas to grid
      const canvas = canvasRef.current;
      if (canvas) {
        const gw = gridRef.current.w;
        const gh = gridRef.current.h;
        const maxW = window.innerWidth;
        const maxH = window.innerHeight - HEADER_HEIGHT_PX;
        const cell = Math.max(1, Math.floor(Math.min(maxW / gw, maxH / gh)));
        const width = gw * cell;
        const height = gh * cell;
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width = width;
          canvas.height = height;
        }
      }

      // interpolation timing once per update
      const tick = Number(s?.game_tick_ms ?? 125);
      tickMsRef.current = Number.isFinite(tick) && tick > 0 ? tick : 125;
      lastUpdateTsRef.current = performance.now();

      // request draw
      drawRef.current?.();
    };

    const onConnectError = (err: any) => {
      console.error("[ui] connect_error:", err?.message || err);
    };

    socketRef.current.on("connect", onConnect);
    socketRef.current.on("game_state", onUpdate);
    socketRef.current.on("connect_error", onConnectError);

    return () => {
      if (brandTimerRef.current !== null) {
        clearTimeout(brandTimerRef.current);
        brandTimerRef.current = null;
      }
      socketRef.current?.off("connect", onConnect);
      socketRef.current?.off("game_state", onUpdate);
      socketRef.current?.off("connect_error", onConnectError);
      socketRef.current?.disconnect();
      socketRef.current = undefined;
    };
  }, []);

  // keyboard input to change direction
  useEffect(() => {
    const map: Record<string, string> = {
      ArrowUp: "UP",
      w: "UP",
      ArrowDown: "DOWN",
      s: "DOWN",
      ArrowLeft: "LEFT",
      a: "LEFT",
      ArrowRight: "RIGHT",
      d: "RIGHT",
    };

    const onKey = (e: KeyboardEvent) => {
      const dir = map[e.key];
      if (!dir) return;
      socketRef.current?.emit("change_direction", { direction: dir });
      e.preventDefault();
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // single raf repaint loop
  useEffect(() => {
    let raf = 0;
    const loop = () => {
      if (drawRef.current) drawRef.current();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // draw function with local null-guards so ts stays quiet
  useEffect(() => {
    function draw() {
      // get canvas every time so guard is obvious
      const canvas = canvasRef.current;
      if (!canvas) return;
      const context = canvas.getContext("2d");
      if (!context) return;

      // clear
      context.clearRect(0, 0, canvas.width, canvas.height);

      // theme colors
      const isDark = document.documentElement.classList.contains("dark");
      const bg = isDark ? "#111111" : "#f5f5f5";
      const foodColor = isDark ? "#f43f5e" : "#be123c";
      const textColor = isDark ? "#ffffff" : "#111111";

      // background
      context.fillStyle = bg;
      context.fillRect(0, 0, canvas.width, canvas.height);

      // grid sizing
      const gw = gridRef.current.w;
      const gh = gridRef.current.h;
      const cellCandidate = Math.min(canvas.width / gw, canvas.height / gh);
      const cell = Math.max(1, Math.floor(cellCandidate));
      const offsetX = Math.floor((canvas.width - gw * cell) / 2);
      const offsetY = Math.floor((canvas.height - gh * cell) / 2);

      // inner grid lines only
      context.strokeStyle = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.1)";
      context.lineWidth = 1;
      for (let x = 1; x < gw; x++) {
        const px = offsetX + x * cell + 0.5;
        context.beginPath();
        context.moveTo(px, offsetY);
        context.lineTo(px, offsetY + gh * cell);
        context.stroke();
      }
      for (let y = 1; y < gh; y++) {
        const py = offsetY + y * cell + 0.5;
        context.beginPath();
        context.moveTo(offsetX, py);
        context.lineTo(offsetX + gw * cell, py);
        context.stroke();
      }

      // food with pulsing glow inside the cell
      const food = foodRef.current;
      if (food) {
        const fx = offsetX + food[0] * cell;
        const fy = offsetY + food[1] * cell;

        const timeSec = performance.now() / 1000;
        const pulse = 0.5 + 0.5 * Math.sin(timeSec * 2 * Math.PI * 1.5);

        const inset = Math.max(1, Math.floor(cell * 0.15));
        context.save();
        context.imageSmoothingEnabled = false;
        context.globalAlpha = 0.45 + 0.55 * pulse;
        context.strokeStyle = "#ffcbcd";
        context.shadowColor = "#ffcbcd";
        context.shadowBlur =
          Math.max(6, Math.floor(cell * 0.5)) * (0.6 + 0.8 * pulse);
        context.lineWidth = Math.max(2, Math.floor(cell * 0.15));

        const sx = fx + inset + 0.5;
        const sy = fy + inset + 0.5;
        const sw = Math.max(1, cell - inset * 2 - 1);
        const sh = Math.max(1, cell - inset * 2 - 1);
        context.strokeRect(sx, sy, sw, sh);

        context.globalAlpha = 1;
        context.shadowBlur = 0;
        context.fillStyle = foodColor;
        context.fillRect(fx + inset, fy + inset, cell - inset * 2, cell - inset * 2);
        context.restore();
      }

      // interpolation amount 0..1
      const now = performance.now();
      let t = (now - lastUpdateTsRef.current) / tickMsRef.current;
      if (t < 0) t = 0;
      if (t > 1) t = 1;

      // rainbow base hue
      const baseHue = (now * 0.12) % 360;

      // pull snapshots
      const prev = lastServerSnakeRef.current;
      const cur = curServerSnakeRef.current;

      // if mismatch, hard draw; else draw with lerp and trail
      if (prev.length !== cur.length) {
        for (let i = 0; i < cur.length; i++) {
          const seg = cur[i];
          const hue = (baseHue + i * 8) % 360;
          const col = `hsl(${hue} 90% 55%)`;
          context.save();
          context.fillStyle = col;
          context.shadowColor = col;
          context.shadowBlur = Math.max(4, Math.floor(cell * 0.5));
          context.fillRect(
            offsetX + seg[0] * cell,
            offsetY + seg[1] * cell,
            cell,
            cell
          );
          context.restore();
        }
      } else {
        // trail pruning
        while (
          trailRef.current.length &&
          now - trailRef.current[0].t > TRAIL_LIFETIME_MS
        ) {
          trailRef.current.shift();
        }
        // draw trail dots
        for (let i = 0; i < trailRef.current.length; i++) {
          const p = trailRef.current[i];
          const age = now - p.t;
          const alpha = Math.max(0, 1 - age / TRAIL_LIFETIME_MS);
          const r = Math.max(2, Math.floor(cell * TRAIL_SIZE_MULT));
          const col = `hsl(${p.h} 90% 55%)`;
          context.save();
          context.globalAlpha = alpha * TRAIL_ALPHA;
          context.fillStyle = col;
          context.shadowColor = col;
          context.shadowBlur = Math.floor(cell * 0.6 * alpha);
          context.beginPath();
          context.arc(p.x, p.y, r, 0, Math.PI * 2);
          context.fill();
          context.restore();
        }

        // draw snake with interpolation and glow
        for (let i = 0; i < cur.length; i++) {
          const p0 = prev[i];
          const p1 = cur[i];
          const rx = p0[0] + (p1[0] - p0[0]) * t;
          const ry = p0[1] + (p1[1] - p0[1]) * t;

          const hue = (baseHue + i * 8) % 360;
          const col = `hsl(${hue} 90% 55%)`;
          context.save();
          context.fillStyle = col;
          context.shadowColor = col;
          context.shadowBlur = Math.max(
            SNAKE_GLOW_MIN,
            Math.floor(cell * SNAKE_GLOW_MULT)
          );
          context.fillRect(offsetX + rx * cell, offsetY + ry * cell, cell, cell);
          context.restore();

          // trail follows the tail (last segment)
          if (i === cur.length - 1) {
            trailRef.current.push({
              x: offsetX + rx * cell + cell / 2,
              y: offsetY + ry * cell + cell / 2,
              t: now,
              h: hue,
            });
            if (trailRef.current.length > 160) trailRef.current.shift();
          }
        }
      }

      // score text
      context.fillStyle = textColor;
      context.font = "14px ui-sans-serif, system-ui, -apple-system";
      context.textBaseline = "top";
      context.fillText(`score: ${scoreRef.current}`, 8, 8);
    }

    // register draw and do one paint
    drawRef.current = draw;
    draw();

    // redraw on theme change
    const observer = new MutationObserver(() => {
      if (drawRef.current) drawRef.current();
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => {
      observer.disconnect();
      drawRef.current = null;
    };
  }, []);

  // resize to grid
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const gw = gridRef.current.w;
      const gh = gridRef.current.h;
      const maxW = window.innerWidth;
      const maxH = window.innerHeight - HEADER_HEIGHT_PX;
      const cell = Math.max(1, Math.floor(Math.min(maxW / gw, maxH / gh)));
      const width = gw * cell;
      const height = gh * cell;

      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      if (drawRef.current) drawRef.current();
    };

    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <>
      {/* empty header to keep the 64px offset */}
      <header className="fixed top-0 left-0 right-0 h-16 px-4 bg-transparent pointer-events-none z-20" />

      <div className="absolute top-16 left-0 right-0 bottom-0 flex flex-col items-center justify-center">
        <canvas
          ref={canvasRef}
          width={gridRef.current.w * 16}
          height={gridRef.current.h * 16}
          style={{ position: "absolute", border: "none", outline: "none" }}
        />

        {showBrand && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="text-primary text-3xl font-extrabold mb-2 text-center">
              Sparky
            </span>
          </div>
        )}

        {/* bottom-right stack: badge + replay */}
        <div className="absolute bottom-4 right-4 z-20 flex flex-col items-end gap-2 pointer-events-none">
          <span className="px-3 py-1 rounded-md text-sm font-medium bg-black/40 text-white border border-white/20 backdrop-blur pointer-events-none select-none">
            Sparky
          </span>
          <button
            onClick={() => socketRef.current?.emit("replay_game")}
            className="pointer-events-auto px-4 py-2 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 shadow-lg"
          >
            Replay
          </button>
        </div>

        {/* right-side controls */}
        <div className="absolute bottom-24 right-6 z-20 flex flex-col gap-2 w-44 pointer-events-none">
          <label className="text-xs font-medium opacity-80 pointer-events-none">
            Score
          </label>

          <div className="flex items-center gap-2 pointer-events-auto">
            <input
              type="number"
              value={scoreBox}
              readOnly
              className="w-full rounded-md border border-border bg-background/80 px-2 py-1 text-sm"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 pointer-events-auto">
            <button
              onClick={() => socketRef.current?.emit("dec_score")}
              className="px-2 py-1 rounded-md bg-slate-600 text-white hover:bg-slate-700 text-sm"
            >
              −1
            </button>
            <button
              onClick={() => socketRef.current?.emit("inc_score")}
              className="px-2 py-1 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 text-sm"
            >
              +1
            </button>
            <button
              onClick={() => {
                for (let i = 0; i < 5; i++) socketRef.current?.emit("inc_score");
              }}
              className="px-2 py-1 rounded-md bg-emerald-700 text-white hover:bg-emerald-800 text-sm"
            >
              +5
            </button>
            <button
              onClick={() => {
                for (let i = 0; i < 10; i++) socketRef.current?.emit("inc_score");
              }}
              className="px-2 py-1 rounded-md bg-emerald-800 text-white hover:bg-emerald-900 text-sm"
            >
              +10
            </button>
          </div>

          <div className="mt-2 flex items-center justify-between pointer-events-auto">
            <span className="text-xs opacity-80">God mode</span>
            <button
              onClick={() => socketRef.current?.emit("toggle_god_mode")}
              className={`px-2 py-1 rounded-md text-white text-sm ${
                godMode ? "bg-amber-600 hover:bg-amber-700" : "bg-zinc-600 hover:bg-zinc-700"
              }`}
              title="ignore walls and self-collisions"
            >
              {godMode ? "On" : "Off"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
