"""Entry point for the layered application layout."""

import tkinter as tk

from .gui import FundamentalApp


def main() -> None:
    root = tk.Tk()
    FundamentalApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
