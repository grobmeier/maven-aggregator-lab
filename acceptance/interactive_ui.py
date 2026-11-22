# SPDX-License-Identifier: Apache-2.0
"""Provide arrow-key menus and folder browsing through the standard terminal library."""

from pathlib import Path
import textwrap


class Cancelled(Exception):
    pass


def display(value):
    return "".join(char if char.isprintable() else " " for char in str(value))


class TerminalUI:
    def __init__(self, screen, curses):
        self.screen, self.curses = screen, curses
        screen.keypad(True)
        try:
            curses.curs_set(0)
            curses.set_escdelay(50)
        except (curses.error, AttributeError):
            pass

    def put(self, row, text, attributes=0):
        height, width = self.screen.getmaxyx()
        if 0 <= row < height - 1 and width > 2:
            try:
                self.screen.addnstr(row, 1, display(text), width - 2, attributes)
            except self.curses.error:
                pass

    def heading(self, title):
        height, width = self.screen.getmaxyx()
        lines = []
        for line in title.splitlines():
            lines.extend(textwrap.wrap(display(line), max(10, width - 3)) or [""])
        for row, line in enumerate(lines[:max(1, height - 6)]):
            self.put(row, line)
        return min(len(lines), max(1, height - 6)) + 1

    def choose(self, title, options, default=None, folder_navigation=False):
        if not options:
            raise ValueError("The menu has no choices.")
        selected = next((i for i, (_, value) in enumerate(options) if value == default), 0)
        while True:
            self.screen.erase()
            start = self.heading(title)
            height, _ = self.screen.getmaxyx()
            room = max(1, height - start - 3)
            offset = max(0, selected - room + 1)
            for i in range(offset, min(len(options), offset + room)):
                self.put(start + i - offset, ("> " if i == selected else "  ") + options[i][0],
                         self.curses.A_REVERSE if i == selected else 0)
            self.put(height - 2, "Arrows: browse | Enter: select | Esc: cancel" if folder_navigation else "Up/Down: move | Enter: select | Esc: cancel")
            self.screen.refresh()
            key = self.screen.get_wch()
            if key in (self.curses.KEY_UP, "k"):
                selected = (selected - 1) % len(options)
            elif key in (self.curses.KEY_DOWN, "j"):
                selected = (selected + 1) % len(options)
            elif key in ("\n", "\r", self.curses.KEY_ENTER):
                return options[selected][1]
            elif key in ("\x1b", "q"):
                raise Cancelled()
            elif folder_navigation and key == self.curses.KEY_LEFT:
                return "parent"
            elif folder_navigation and key == self.curses.KEY_RIGHT and isinstance(options[selected][1], Path):
                return options[selected][1]

    def text(self, title, default=""):
        characters, cursor = list(default), len(default)
        try:
            self.curses.curs_set(1)
            while True:
                self.screen.erase()
                row = self.heading(title)
                height, width = self.screen.getmaxyx()
                room = max(1, width - 4)
                offset = max(0, cursor - room + 1)
                self.put(row, "".join(characters[offset:offset + room]))
                self.put(height - 2, "Type or paste | Enter: accept | Esc: cancel")
                try:
                    self.screen.move(min(row, height - 2), min(width - 2, 1 + cursor - offset))
                except self.curses.error:
                    pass
                self.screen.refresh()
                key = self.screen.get_wch()
                if key in ("\n", "\r", self.curses.KEY_ENTER):
                    return "".join(characters)
                if key == "\x1b":
                    raise Cancelled()
                if key in (self.curses.KEY_LEFT,):
                    cursor = max(0, cursor - 1)
                elif key in (self.curses.KEY_RIGHT,):
                    cursor = min(len(characters), cursor + 1)
                elif key in (self.curses.KEY_BACKSPACE, "\x7f", "\b") and cursor:
                    cursor -= 1
                    characters.pop(cursor)
                elif key == self.curses.KEY_DC and cursor < len(characters):
                    characters.pop(cursor)
                elif isinstance(key, str) and key.isprintable():
                    characters.insert(cursor, key)
                    cursor += 1
        finally:
            try:
                self.curses.curs_set(0)
            except self.curses.error:
                pass

    def folder(self, title, start):
        current = Path(start).expanduser()
        if not current.is_dir():
            current = current.parent if current.parent.is_dir() else Path.home()
        current = current.resolve()
        show_hidden = False
        while True:
            try:
                directories = sorted((p for p in current.iterdir() if p.is_dir() and (show_hidden or not p.name.startswith("."))),
                                     key=lambda p: p.name.casefold())
            except (OSError, RuntimeError) as error:
                self.message(str(error))
                current = current.parent
                continue
            options = [("Select this folder", "select"), (".. / Parent folder", "parent"),
                       ("Type or paste a path", "type"), ("Hide hidden folders" if show_hidden else "Show hidden folders", "hidden"),
                       *[(p.name + "/", p) for p in directories]]
            picked = self.choose(title + "\n" + str(current), options, folder_navigation=True)
            if picked == "select":
                return current
            if picked == "parent":
                current = current.parent
            elif picked == "hidden":
                show_hidden = not show_hidden
            elif picked == "type":
                path = Path(self.text("Folder path", str(current))).expanduser()
                if path.is_dir():
                    current = path.resolve()
                else:
                    self.message("That folder does not exist.")
            else:
                current = picked.resolve()

    def many(self, title, options, defaults=()):
        selected = set(defaults)
        cursor = "done"
        while True:
            rows = [("Continue with selected cases", "done")]
            rows += [("[" + ("x" if value in selected else " ") + "] " + label, value) for label, value in options]
            picked = self.choose(title + f"\nSelected: {len(selected)}. Enter toggles a case.", rows, default=cursor)
            cursor = picked
            if picked == "done":
                if selected:
                    return [value for _, value in options if value in selected]
                self.message("Select at least one case.")
            elif picked in selected:
                selected.remove(picked)
            else:
                selected.add(picked)

    def message(self, text):
        self.choose(text, [("Continue", None)])
