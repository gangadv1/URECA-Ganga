"""Small helper for stable result names."""

from __future__ import annotations

import argparse


def make_config_name(
    *,
    code: str = "gross-xz",
    b: int,
    g: int,
    M: int,
    clip: str | int,
    pc: int,
    pv: int,
    schedule: str | int,
) -> str:
    """Build a short name for one decoder/hardware setting."""
    clip_text = str(clip)
    if not clip_text.startswith("clip"):
        clip_text = f"clip{clip_text}"
    schedule_text = str(schedule).zfill(2) if isinstance(schedule, int) else str(schedule)
    if not schedule_text.startswith("sched"):
        schedule_text = f"sched{schedule_text}"
    return f"{code}_b{b}_g{g}_M{M}_{clip_text}_pc{pc}_pv{pv}_{schedule_text}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Print a fixed-point Relay-BP config name")
    parser.add_argument("--code", default="gross-xz")
    parser.add_argument("--b", type=int, required=True)
    parser.add_argument("--g", type=int, required=True)
    parser.add_argument("--M", type=int, required=True)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--pc", type=int, required=True)
    parser.add_argument("--pv", type=int, required=True)
    parser.add_argument("--schedule", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(
        make_config_name(
            code=args.code,
            b=args.b,
            g=args.g,
            M=args.M,
            clip=args.clip,
            pc=args.pc,
            pv=args.pv,
            schedule=args.schedule,
        )
    )


if __name__ == "__main__":
    main()

