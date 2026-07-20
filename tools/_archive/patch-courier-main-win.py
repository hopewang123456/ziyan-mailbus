from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "store/deliverables/game-courier-20260625/game/main.py"

MAIN = r'''import argparse
import ctypes
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from game.content import GameState
from game.engine import run_game
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
    parser = argparse.ArgumentParser(description="Courier Hub")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save", type=str, default=None)
    parser.add_argument("--load", type=str, default=None)
    parser.add_argument("--plain", action="store_true", help="no ANSI colors")
    args = parser.parse_args()
    set_plain(args.plain)

    if args.load:
        from game.save import load_game
        state = load_game(args.load)
    else:
        state = GameState(seed=args.seed)

    rng = random.Random(args.seed)

    if args.auto:
        state = run_game(state, auto=True, rng_override=rng)
        print(render_full(state, phase_name="game_over"), flush=True)
        print(f"\n满意度: {state.satisfaction:.0f}/100", flush=True)
        sys.exit(0 if state.satisfaction >= 70 else 1)

    print(render_full(state, phase_name="intro"), flush=True)
    while True:
        state.letters = []
        state_copy = run_game(state, auto=True, rng_override=rng)
        last = state_copy.history[-1] if state_copy.history else {}
        print(
            render_full(
                state_copy,
                phase_name="game_over" if state_copy.round >= 3 else "",
                round_result=last,
            ),
            flush=True,
        )
        if state_copy.round >= 3:
            break
        state = state_copy
        input("\n按回车继续下一轮...")

    if args.save:
        from game.save import save_game
        save_game(state_copy, args.save)

    print(f"\n满意度: {state_copy.satisfaction:.0f}/100", flush=True)
    sys.exit(0 if state_copy.satisfaction >= 70 else 1)


if __name__ == "__main__":
    main()
'''

if __name__ == "__main__":
    TARGET.write_text(MAIN, encoding="utf-8")
    root = TARGET.parents[1]
    (root / "play.ps1").write_text(
        """# Courier Hub launcher
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
Write-Host "=== Courier Hub ===" -ForegroundColor Cyan
if ($args.Count -eq 0) {
    python -m game.main --auto --seed 42
} else {
    python -m game.main @args
}
if ($LASTEXITCODE -ne 0) { Write-Host "失败 exit $LASTEXITCODE" -ForegroundColor Red }
Read-Host "按回车关闭"
""",
        encoding="utf-8",
    )
    (root / "play.bat").write_text(
        "@echo off\r\nchcp 65001>nul\r\nset PYTHONIOENCODING=utf-8\r\ncd /d \"%~dp0\"\r\n"
        "if \"%~1\"==\"\" (python -m game.main --auto --seed 42) else (python -m game.main %*)\r\n"
        "pause\r\n",
        encoding="ascii",
    )
    print("wrote", TARGET)
    print("wrote", root / "play.ps1")
