#!/usr/bin/env python3
"""Fix Courier Hub Windows launch: PS5.1 UTF-8 BOM, --plain default, ASCII-safe scripts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "store/deliverables/game-courier-20260625"

PLAY_PS1 = """# Courier Hub launcher (UTF-8 BOM required for Windows PowerShell 5.1)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = "utf-8"
Write-Host "=== Courier Hub ===" -ForegroundColor Cyan
if ($args.Count -eq 0) {
    Write-Host "[Interactive] type A, B, or C each round" -ForegroundColor Yellow
    python -m game.main --plain
} else {
    python -m game.main --plain @args
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "Exit code: $LASTEXITCODE" -ForegroundColor Red
}
Read-Host "Press Enter to close"
"""

PLAY_BAT = r"""@echo off
chcp 65001>nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo === Courier Hub ===
if "%~1"=="" (
    echo [Interactive] type A, B, or C each round
    python -m game.main --plain
) else (
    python -m game.main --plain %*
)
if errorlevel 1 echo Failed with exit code %errorlevel%
pause
"""

PLAY_AUTO_BAT = r"""@echo off
chcp 65001>nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python -m game.main --plain --auto --seed 42
pause
"""

ROOT_LAUNCHER = Path(__file__).resolve().parents[2] / "play-courier-game.ps1"

ROOT_LAUNCHER_TEXT = """# Launch Courier Hub from repo root
$ErrorActionPreference = "Stop"
$gameRoot = Join-Path $PSScriptRoot "mail\\store\\deliverables\\game-courier-20260625"
if (-not (Test-Path $gameRoot)) {
    Write-Host "Game folder not found: $gameRoot" -ForegroundColor Red
    exit 1
}
& (Join-Path $gameRoot "play.ps1") @args
"""


def write_utf8_bom(path: Path, text: str) -> None:
    path.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))


def patch_main_interactive_order() -> None:
    """Show letters before route prompt: prepare round before display."""
    main_path = ROOT / "game/main.py"
    text = main_path.read_text(encoding="utf-8")
    old = """    # 交互模式：每轮展示信件 → 玩家选路线 → 结算
    print(render_full(state, phase_name="intro"), flush=True)
    while len(state.history) < 3:
        print(render_full(state, phase_name="round"), flush=True)
        state = run_round(state, auto=False)"""
    new = """    # Interactive: intro once, then each round show letters then prompt route
    print(render_full(state, phase_name="intro"), flush=True)
    while len(state.history) < 3:
        from game.engine import prepare_round

        state = prepare_round(state)
        print(render_full(state, phase_name="round"), flush=True)
        state = run_round(state, auto=False, skip_prepare=True)"""
    if old in text:
        text = text.replace(old, new)
        main_path.write_text(text, encoding="utf-8")


def patch_engine_prepare() -> None:
    engine_path = ROOT / "game/engine.py"
    text = engine_path.read_text(encoding="utf-8")
    if "def prepare_round" in text:
        return
    insert_after = "HANDLERS: dict[Phase, Handler] = {"
    prepare_fn = '''

def prepare_round(state: GameState) -> GameState:
    """Pick letters and resources for the current round (no route yet)."""
    rng = random.Random(state.seed + state.round)
    state.letters = pick_letters(rng)
    pool = RESOURCE_POOLS.get(state.round, RESOURCE_POOLS[1])
    state.horses = pool["horses"]
    state.camels = pool["camels"]
    state.route_choice = None
    return state

'''
    text = text.replace(insert_after, prepare_fn + insert_after, 1)

    old_run = '''def run_round(state: GameState, *, auto: bool = True, route: Optional[str] = None) -> GameState:
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
    return state'''
    new_run = '''def run_round(
    state: GameState,
    *,
    auto: bool = True,
    route: Optional[str] = None,
    skip_prepare: bool = False,
) -> GameState:
    """Run one round (route choice + resolve). Call prepare_round first in interactive mode."""
    ctx: Context = {"auto": auto, "letters": state.letters}
    if route:
        ctx["route"] = route.upper()
    start_round = state.round
    phase = Phase.ASSIGN_RESOURCES if skip_prepare else (
        Phase.INTRO if not state.history and state.round == 1 else Phase.PICK_LETTERS
    )
    while phase != Phase.GAME_OVER:
        phase, state, ctx = HANDLERS[phase](state, ctx)
        if state.round > start_round:
            break
    return state'''
    if old_run in text:
        text = text.replace(old_run, new_run)
    engine_path.write_text(text, encoding="utf-8")


def patch_render_plain_ascii() -> None:
    render_path = ROOT / "game/render.py"
    text = render_path.read_text(encoding="utf-8")
    if "def _box" in text:
        return
    box_fn = (
        "def _box(s: str) -> str:\n"
        "    if not PLAIN:\n"
        "        return s\n"
        "    for old, new in ((\"\u250c\", \"+\"), (\"\u2510\", \"+\"), (\"\u2514\", \"+\"), "
        "(\"\u2518\", \"+\"), (\"\u2500\", \"-\"), (\"\u2502\", \"|\"), (\"\u2550\", \"=\")):\n"
        "        s = s.replace(old, new)\n"
        "    return s\n\n\n"
    )
    text = text.replace("def _c(s: str, code: str) -> str:", box_fn + "def _c(s: str, code: str) -> str:")
    for _ in range(3):
        text = text.replace('return "\\n".join(lines)', 'return _box("\\n".join(lines))', 1)
    render_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    write_utf8_bom(ROOT / "play.ps1", PLAY_PS1)
    (ROOT / "play.bat").write_text(PLAY_BAT.replace("\n", "\r\n"), encoding="ascii")
    (ROOT / "play-auto.bat").write_text(PLAY_AUTO_BAT.replace("\n", "\r\n"), encoding="ascii")
    write_utf8_bom(ROOT_LAUNCHER, ROOT_LAUNCHER_TEXT)
    patch_engine_prepare()
    patch_main_interactive_order()
    patch_render_plain_ascii()
    print("fixed:", ROOT)
    print("fixed:", ROOT_LAUNCHER)
