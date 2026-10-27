import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

def main():
    # Enable High DPI scaling for modern displays
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    # 先建立 QApplication 讓 Windows OLE (OleInitialize) 以 STA 模式初始化
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 在 QApplication 建立後再載入 MainWindow 與相關音訊模組，
    # 避免 soundcard 在模組載入階段提前將 COM 初始化為 MTA 而引發 0x80010106 衝突
    from main_window import MainWindow
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
