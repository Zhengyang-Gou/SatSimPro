import sys
import os


def configure_linux_display_backend() -> None:
    if not sys.platform.startswith("linux"):
        return

    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return

    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("GDK_BACKEND", "x11")


def main() -> int:
    configure_linux_display_backend()

    # Qt reads its platform configuration during import/application startup.
    # Keep these imports after the environment has been configured.
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication(sys.argv)
    if sys.platform != "darwin":
        app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
