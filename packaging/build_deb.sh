#!/bin/bash
# build_deb.sh — Build gói .deb cho Mini Cleaner từ mã nguồn hiện tại.
#
# Cách dùng: chạy từ thư mục gốc project (nơi có main.py, ui/, core/...)
#   chmod +x packaging/build_deb.sh
#   ./packaging/build_deb.sh
#
# Kết quả: file mini-cleaner_<version>_all.deb ở thư mục gốc project.

set -e

VERSION="1.0.0"
PKG_NAME="mini-cleaner"
BUILD_DIR="build/${PKG_NAME}_${VERSION}_all"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT"
rm -rf "$BUILD_DIR"

echo "==> Tạo cấu trúc thư mục Debian package..."
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/mini-cleaner"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/doc/mini-cleaner"

echo "==> Copy mã nguồn..."
cp -r main.py ui core resources "$BUILD_DIR/usr/lib/mini-cleaner/"
find "$BUILD_DIR/usr/lib/mini-cleaner" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> Tạo launcher script..."
cat > "$BUILD_DIR/usr/bin/mini-cleaner" << 'EOF'
#!/bin/sh
exec python3 /usr/lib/mini-cleaner/main.py "$@"
EOF
chmod 755 "$BUILD_DIR/usr/bin/mini-cleaner"

echo "==> Copy file .desktop và copyright..."
cp packaging/mini-cleaner.desktop "$BUILD_DIR/usr/share/applications/mini-cleaner.desktop"
cp packaging/copyright "$BUILD_DIR/usr/share/doc/mini-cleaner/copyright"

echo "==> Tạo DEBIAN/control..."
cat > "$BUILD_DIR/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, python3-psutil, gir1.2-gtk-4.0, gir1.2-adw-1, policykit-1
Recommends: wmctrl
Maintainer: Mini Cleaner Project <noreply@example.com>
Description: Don rac, giam sat process va toi uu he thong Ubuntu
 Mini Cleaner la ung dung desktop native cho Ubuntu, xay bang Python +
 GTK4 + Libadwaita. Xem README.md de biet chi tiet cac tinh nang.
EOF

echo "==> Thiết lập quyền file..."
find "$BUILD_DIR" -type d -exec chmod 755 {} \;
find "$BUILD_DIR" -type f -exec chmod 644 {} \;
chmod 755 "$BUILD_DIR/usr/bin/mini-cleaner"

echo "==> Build .deb..."
dpkg-deb --build --root-owner-group "$BUILD_DIR" "${PKG_NAME}_${VERSION}_all.deb"

echo ""
echo "✅ Xong! File: ${PROJECT_ROOT}/${PKG_NAME}_${VERSION}_all.deb"
echo "   Cài bằng:  sudo apt install ./${PKG_NAME}_${VERSION}_all.deb"
