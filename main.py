import sys
import os
from pathlib import Path


def configure_linux_display_backend() -> None:
    if not sys.platform.startswith("linux"):
        return

    is_wsl = "microsoft" in os.uname().release.lower()
    is_wayland = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
    if is_wsl or is_wayland:
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
        os.environ.setdefault("GDK_BACKEND", "x11")

    # WSLg can expose a 4K desktop as 96 DPI even when Windows uses 150%
    # scaling. Keep the default overridable for other displays.
    if is_wsl:
        os.environ.setdefault(
            "QT_SCALE_FACTOR", os.environ.get("SATNET_QT_SCALE_FACTOR", "1.5")
        )


def configure_application_font(app) -> None:
    if not sys.platform.startswith("linux"):
        return

    from PySide6.QtGui import QFont, QFontDatabase

    font_candidates = (
        Path("/mnt/c/Windows/Fonts/msyh.ttc"),
        Path("/mnt/c/Windows/Fonts/msyhl.ttc"),
        Path("/mnt/c/Windows/Fonts/simhei.ttf"),
    )
    for font_path in font_candidates:
        if not font_path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 9))
            return


def configure_application_style(app) -> None:
    """Use a predictable style without platform-provided dialog button icons."""
    if sys.platform == "darwin":
        return

    from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

    class ApplicationStyle(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, return_data=None):
            if hint == QStyle.SH_DialogButtonBox_ButtonsHaveIcons:
                return 0
            return super().styleHint(hint, option, widget, return_data)

    app.setStyle(ApplicationStyle(QStyleFactory.create("Fusion")))


def main() -> int:
    configure_linux_display_backend()

    # Qt reads its platform configuration during import/application startup.
    # Keep these imports after the environment has been configured.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    # Native dialogs run outside the application's font setup.  On WSL/Linux
    # systems without a system-wide CJK font this makes otherwise valid Chinese
    # text appear as boxes or garbled glyphs.  Qt dialogs inherit the YaHei font
    # loaded below and also match the application's theme.
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    app = QApplication(sys.argv)
    configure_application_style(app)
    configure_application_font(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
