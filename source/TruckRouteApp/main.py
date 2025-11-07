"""
GUI entry point for the Truck Route desktop application.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from TruckRouteApp.db import init_db
from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.ui import MainWindow


def main() -> int:
    """Initialise dependencies, spawn the main window, and start the Qt loop."""
    init_db()
    db_service = DatabaseService()
    app = QApplication(sys.argv)
    window = MainWindow(db_service)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

