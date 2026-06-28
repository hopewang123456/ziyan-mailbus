#!/usr/bin/env python3
"""补全 Courier Hub 交互模式：每轮玩家选路线 A/B/C。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "store/deliverables/game-courier-20260625"

ENGINE = r'''import random
from enum import Enum, auto
from typing import Callable, Optional
from game.content import GameState, pick_letters, RESOURCE_POOLS, ROUTES


class Phase(Enum):
    INTRO = auto()
    PICK_LETTERS = auto()
    ASSIGN_RESOURCES = auto()
    CHOOSE_ROUTE = auto()
    RESOLVE = auto()
    GAME_OVER = auto()


Context = dict
Handler = Callable[[GameState, Context], tuple[Phase, GameState, Context]]


def _prompt_route() -> str:
    from game.render import render_routes

    print(render_routes(), flush=True)
    while True:
        choice = input("选择路线 [A/B/C]: ").strip().upper()
        if choice in ROUTES:
            return choice
        print("无效输入，请输入 A、B 或 C。", flush=True)


def _intro(state: GameState, ctx: Context) -> tuple[Phase, GameState, Context]:
    return Phase.PICK_LETTERS, state, ctx


def _pick_letters(state: GameState, ctx: Context) -> tuple[Phase, GameState, Context]:
    rng = random.Random(state.seed + state.round)
    letters = pick_letters(rng)
    state.letters = letters
    pool = RESOURCE_POOLS.get(state.round, RESOURCE_POOLS[1])
    state.horses = pool["horses"]
    state.camels = pool["camels"]
    return Phase.ASSIGN_RESOURCES, state, {"letters": letters}


def _assign_resources(state: GameState, ctx: Context) -> tuple[Phase, GameState, Context]:
    letters = ctx.get("letters", state.letters)
    count = len(letters)
    rng = random.Random(state.seed + state.round + 99)

    if "route" in ctx:
        route_key = ctx["route"]
    elif not ctx.get("auto", True):
        route_key = _prompt_route()
    else:
        route_key = rng.choice(["A", "B", "C"])

    route = ROUTES[route_key]
    state.route_choice = route_key

    horses_needed = route["horse_cost"] * count
    camels_needed = route["camel_cost"] * count

    horse_shortfall = max(0, horses_needed - state.horses)
    camel_shortfall = max(0, camels_needed - state.camels)

    penalty = (horse_shortfall + camel_shortfall) * 5
    state.funds = max(0, state.funds - penalty)

    return Phase.CHOOSE_ROUTE, state, {"route": route_key, "penalty": penalty, "count": count}


def _choose_route(state: GameState, ctx: Context) -> tuple[Phase, GameState, Context]:
    return Phase.RESOLVE, state, ctx


def _resolve(state: GameState, ctx: Context) -> tuple[Phase, GameState, Context]:
    letters = state.letters
    route_key = state.route_choice or "A"
    route = ROUTES[route_key]

    rng = random.Random(state.seed + state.round + 50)
    delivered = 0
    revenue = 0
    for letter in letters:
        roll = rng.random()
        if roll > route["difficulty"]:
            delivered += 1
            revenue += letter["reward"]

    state.funds += revenue
    satisfaction_gain = (delivered / max(len(letters), 1)) * 30
    state.satisfaction = min(100, state.satisfaction + satisfaction_gain)

    state.history.append({
        "round": state.round,
        "letters": len(letters),
        "delivered": delivered,
        "route": route_key,
        "revenue": revenue,
        "satisfaction": round(state.satisfaction, 1),
    })

    if state.round >= 3:
        return Phase.GAME_OVER, state, ctx

    state.round += 1
    return Phase.PICK_LETTERS, state, ctx


def _game_over(state: GameState, ctx: Context) -> tuple[Phase, GameState, Context]:
    return Phase.GAME_OVER, state, ctx


HANDLERS: dict[Phase, Handler] = {
    Phase.INTRO: _intro,
    Phase.PICK_LETTERS: _pick_letters,
    Phase.ASSIGN_RESOURCES: _assign_resources,
    Phase.CHOOSE_ROUTE: _choose_route,
    Phase.RESOLVE: _resolve,
    Phase.GAME_OVER: _game_over,
}


def run_round(state: GameState, *, auto: bool = True, route: Optional[str] = None) -> GameState:
    """执行当前轮（含选路线）；交互模式每轮调用一次。"""
    ctx: Context = {"auto": auto}
    if route:
        ctx["route"] = route.upper()
    start_round = state.round
    phase = Phase.INTRO if not state.history and state.round == 1 else Phase.PICK_LETTERS
    while phase != Phase.GAME_OVER:
        phase, state, ctx = HANDLERS[phase](state, ctx)
        if state.round > start_round:
            break
    return state


def run_game(state: GameState, auto: bool = False, rng_override: Optional[random.Random] = None) -> GameState:
    """自动模式：连跑至 3 轮结束。rng_override 保留兼容。"""
    while len(state.history) < 3 and state.round <= 3:
        state = run_round(state, auto=True)
    return state
'''

MAIN = r'''import argparse
import ctypes
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from game.content import GameState
from game.engine import run_game, run_round
from game.render import render_full, set_plain


def _setup_windows_console() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def main() -> None:
    _setup_windows_console()
    parser = argparse.ArgumentParser(description="Courier Hub — 信件驿站")
    parser.add_argument("--auto", action="store_true", help="自动模式（验收用）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--save", type=str, default=None)
    parser.add_argument("--load", type=str, default=None)
    parser.add_argument("--plain", action="store_true", help="无 ANSI 颜色")
    args = parser.parse_args()
    set_plain(args.plain)

    if args.load:
        from game.save import load_game
        state = load_game(args.load)
    else:
        state = GameState(seed=args.seed)

    if args.auto:
        state = run_game(state, auto=True)
        print(render_full(state, phase_name="game_over"), flush=True)
        print(f"\n满意度: {state.satisfaction:.0f}/100", flush=True)
        sys.exit(0 if state.satisfaction >= 70 else 1)

    # 交互模式：每轮展示信件 → 玩家选路线 → 结算
    print(render_full(state, phase_name="intro"), flush=True)
    while len(state.history) < 3:
        print(render_full(state, phase_name="round"), flush=True)
        state = run_round(state, auto=False)
        last = state.history[-1] if state.history else {}
        print(
            render_full(
                state,
                phase_name="game_over" if len(state.history) >= 3 else "round_done",
                round_result=last,
            ),
            flush=True,
        )

    if args.save:
        from game.save import save_game
        save_game(state, args.save)

    print(f"\n满意度: {state.satisfaction:.0f}/100", flush=True)
    sys.exit(0 if state.satisfaction >= 70 else 1)


if __name__ == "__main__":
    main()
'''

RENDER_PATCH = """
    if phase_name in ("intro", "round", "round_done") or state.round == 1:
"""

if __name__ == "__main__":
    (ROOT / "game/engine.py").write_text(ENGINE, encoding="utf-8")
    (ROOT / "game/main.py").write_text(MAIN, encoding="utf-8")
    render_path = ROOT / "game/render.py"
    rt = render_path.read_text(encoding="utf-8")
    if "phase_name == \"round\"" not in rt:
        rt = rt.replace(
            '    if phase_name == "intro" or state.round == 1:',
            '    if phase_name in ("intro", "round", "round_done") or state.round == 1:',
        )
        render_path.write_text(rt, encoding="utf-8")
    play_ps1 = ROOT / "play.ps1"
    if play_ps1.exists():
        txt = play_ps1.read_text(encoding="utf-8")
        if "interactive" not in txt.lower():
            play_ps1.write_text(
                txt.replace(
                    'if ($args.Count -eq 0) {\n    python -m game.main --auto --seed 42',
                    'if ($args.Count -eq 0) {\n    Write-Host "[交互模式] 每轮输入 A/B/C 选路线" -ForegroundColor Yellow\n    python -m game.main',
                ),
                encoding="utf-8",
            )
    print("patched interactive mode:", ROOT)
