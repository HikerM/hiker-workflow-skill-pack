from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from qt_specialization import audit


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")


class QtSpecializationTests(unittest.TestCase):
    def test_qt_positive_evidence_covers_version_lifecycle_and_deployment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "CMakeLists.txt", """
find_package(Qt6 6.5 REQUIRED COMPONENTS Core Widgets Test)
qt_add_executable(app src/MainWindow.cpp resources.qrc)
qt_generate_deploy_app_script(TARGET app OUTPUT_SCRIPT deploy_script)
install(SCRIPT ${deploy_script})
enable_testing()
""")
            write(root, "src/MainWindow.cpp", """
#include <QThread>
#include <QPointer>
class MainWindow : public QObject { Q_OBJECT signals: void done(); public slots: void run(); };
void setup(QObject* parent){ auto button = new QPushButton(parent); QPointer<QObject> guard(parent); connect(button, &QPushButton::clicked, parent, []{}, Qt::QueuedConnection); QThread* worker = new QThread(parent); auto icon = QIcon(\":/icons/app.svg\"); }
""")
            write(root, "resources.qrc", "<RCC><qresource><file>icons/app.svg</file></qresource></RCC>")
            write(root, "tests/TestMain.cpp", "#include <QtTest>\nclass TestMain: public QObject{}; QTEST_MAIN(TestMain)")
            data = audit(root)
            self.assertEqual("PASS", data["result"], data)
            self.assertEqual("6.5", data["identity"]["qt_version"])
            self.assertTrue(all(item["status"] == "PASS" for item in data["dimensions"].values()))

    def test_qt_negative_detects_unknown_version_and_cross_thread_direct_connection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "CMakeLists.txt", "find_package(Qt6 REQUIRED COMPONENTS Core Widgets)\nqt_add_executable(app src/MainWindow.cpp)\n")
            write(root, "src/MainWindow.cpp", "class MainWindow { void run(){ QThread worker; connect(this, &MainWindow::x, &worker, &QThread::start, Qt::DirectConnection); } };")
            data = audit(root)
            self.assertEqual("BLOCKED", data["result"])
            self.assertEqual("GAP", data["dimensions"]["identity_and_version"]["status"])
            self.assertIn("cross-thread-direct-connection", {item["rule"] for item in data["dimensions"]["threading"]["findings"]})

    def test_non_qt_project_is_blocked_instead_of_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); write(root, "CMakeLists.txt", "add_executable(app main.cpp)")
            write(root, "main.cpp", "int main(){}")
            data = audit(root)
            self.assertEqual("BLOCKED", data["result"])
            self.assertEqual("unknown", data["identity"]["qt_major"])

    def test_default_audit_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); audit(root)
            self.assertFalse((root / ".ai").exists())


if __name__ == "__main__":
    unittest.main()
