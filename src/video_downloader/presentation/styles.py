APP_STYLE = """
QWidget {
    background: #ffffff;
    color: #30343b;
    font-family: "Noto Sans", "Segoe UI", sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog { background: #f5f6f8; }
QLabel { background: transparent; }
QFrame#topBar {
    background: #ffffff;
    border-bottom: 1px solid #e7e9ed;
}
QLabel#appTitle { font-size: 16px; font-weight: 700; color: #343941; }
QLabel#pageHeading { font-size: 26px; font-weight: 700; color: #242b35; }
QPushButton#headerButton, QPushButton#menuButton {
    background: #f0f1f3;
    border: 0;
    border-radius: 3px;
    color: #3d4249;
    padding: 7px 12px;
    font-weight: 600;
}
QPushButton#headerButton:hover, QPushButton#menuButton:hover { background: #e7e9ec; }
QPushButton#headerButton:pressed, QPushButton#menuButton:pressed { background: #d7dee7; }
QPushButton#headerButton:focus, QPushButton#menuButton:focus { border: 2px solid #265da3; }
QPushButton#headerButton:disabled, QPushButton#menuButton:disabled {
    background: #f0f2f5; color: #677384;
}
QPushButton#menuButton { min-width: 16px; font-size: 16px; padding: 4px 10px; }
QFrame#formCard {
    background: #ffffff;
    border: 1px solid #dfe4ec;
    border-radius: 3px;
}
QLabel#fieldLabel { color: #414b59; font-size: 13px; font-weight: 600; }
QLineEdit#urlEdit {
    background: #ffffff;
    color: #30343b;
    border: 1px solid #aab5c3;
    border-radius: 3px;
    padding: 12px 12px;
    selection-background-color: #438be9;
    min-height: 20px;
}
QLineEdit#urlEdit:focus { border-color: #347fe4; }
QLineEdit#urlEdit:disabled { background: #fafbfd; color: #7b8490; }
QFrame#separator { background: #e7e9ed; border: 0; }
QComboBox#qualityCombo {
    background: #ffffff;
    color: #353a42;
    border: 0;
    padding: 7px 4px;
}
QComboBox#qualityCombo:disabled { color: #9299a4; }
QComboBox#qualityCombo::drop-down { border: 0; width: 20px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #30343b;
    border: 1px solid #dfe4ec;
    selection-background-color: #dceaff;
    selection-color: #203c63;
    padding: 4px;
}
QLabel#folderLabel { color: #6e7784; }
QPushButton#textButton {
    background: transparent;
    border: 0;
    color: #245ba4;
    font-weight: 600;
    padding: 5px;
}
QPushButton#textButton:hover { color: #174b91; }
QPushButton#textButton:pressed { color: #123b73; background: #edf3fc; }
QPushButton#textButton:focus { border: 2px solid #265da3; }
QPushButton#textButton:disabled { color: #677384; }
QLabel#hint { color: #596575; font-size: 13px; }
QPushButton#primaryButton {
    background: #2167bb;
    color: #ffffff;
    border: 0;
    border-radius: 3px;
    padding: 12px 24px;
    min-height: 20px;
    font-weight: 700;
}
QPushButton#primaryButton:hover { background: #226dce; }
QPushButton#primaryButton:pressed { background: #174d91; }
QPushButton#primaryButton:focus { border: 2px solid #123b73; }
QPushButton#primaryButton:disabled { background: #dce5f0; color: #536170; }
QLabel#progressHeading { font-size: 17px; font-weight: 700; color: #353a42; }
QLabel#progressTitle { font-size: 13px; color: #4d535d; }
QFrame#preview {
    border: 0;
    border-radius: 2px;
    background: #eaf1fa;
}
QLabel#previewImage { background: transparent; }
QLabel#playMark {
    background: rgba(25, 43, 68, 175);
    border-radius: 3px;
    color: #ffffff;
    font-size: 28px;
    padding-left: 4px;
}
QProgressBar {
    background: #d9dce1;
    border: 0;
    border-radius: 0px;
    height: 9px;
}
QProgressBar::chunk { background: #347fe4; border-radius: 0px; }
QLabel#progressDetails { color: #596575; font-size: 13px; }
QLineEdit, QComboBox {
    background: #ffffff;
    color: #30343b;
    border: 1px solid #d8dde5;
    border-radius: 3px;
    padding: 7px;
}
QPushButton {
    background: #eef0f3;
    color: #3d4249;
    border: 0;
    border-radius: 3px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #e2e6eb; }
QPushButton:pressed { background: #d2dce9; }
QPushButton:focus { border: 2px solid #265da3; }
QPushButton:disabled { background: #f0f2f5; color: #677384; }
QLabel#videoTitle { font-size: 17px; font-weight: 700; }
QLabel#muted { color: #818b97; }
QToolTip { background: #f7f9fc; color: #30343b; border: 1px solid #dfe4ec; }
"""
