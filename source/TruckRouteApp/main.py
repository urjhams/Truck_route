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
    # Step 1: ensure the SQLite file exists and migrations run before touching data.
    init_db()
    # Step 2: create the thin CRUD service that the UI will call into.
    db_service = DatabaseService()
    # Step 3: start Qt, wire our main window, and enter the event loop.
    app = QApplication(sys.argv)
    window = MainWindow(db_service)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
