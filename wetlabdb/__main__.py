"""Module entry point.

``python -m wetlabdb`` starts the hosted web UI. Pass ``--tk`` to launch the
legacy desktop application during the transition period.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wetlabdb")
    parser.add_argument(
        "--tk",
        action="store_true",
        help="Launch the legacy Tkinter desktop UI instead of the web server.",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.tk:
        from wetlabdb.ui.app import WetlabDBApp

        app = WetlabDBApp()
        app.mainloop()
        return

    import uvicorn

    uvicorn.run(
        "wetlabdb.api.app:get_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=1,
    )


if __name__ == "__main__":
    main()
