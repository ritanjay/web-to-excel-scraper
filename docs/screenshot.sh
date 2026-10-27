#!/usr/bin/env bash
# Take real screenshots of a workbook open in LibreOffice Calc (for the README).
# Usage: bash docs/screenshot.sh sample-output/books.xlsx docs
# Needs: libreoffice-calc, xvfb, imagemagick, python3 + openpyxl.
set -euo pipefail
XLSX=$(realpath "$1"); OUT=$(realpath "${2:-docs}")
WORK=$(mktemp -d); PROFILE="$WORK/profile"
W=1500; H=860
mkdir -p "$PROFILE/user"
cat > "$PROFILE/user/registrymodifications.xcu" <<XCU
<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Setup/Office/Factories/org.openoffice.Setup:Factory['com.sun.star.sheet.SpreadsheetDocument']"><prop oor:name="ooSetupFactoryWindowAttributes" oor:op="fuse"><value>0,0,$W,$H;4;0,0,$W,$H;</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop><prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false</value></prop></item>
</oor:items>
XCU

# A copy with the Summary sheet active, so Calc opens on it.
python3 - "$XLSX" "$WORK/summary.xlsx" <<'PY'
import sys
from openpyxl import load_workbook
wb = load_workbook(sys.argv[1])
wb.active = wb.sheetnames.index("Summary")
wb.save(sys.argv[2])
PY

shoot() {  # file.xlsx out.png
  xvfb-run -a -s "-screen 0 ${W}x${H}x24" bash -c "
    soffice -env:UserInstallation=file://$PROFILE --calc --norestore --nologo '$1' >/dev/null 2>&1 &
    sleep ${WAIT:-30}
    import -window root -crop ${W}x${H}+0+0 '$2'
    pkill -x soffice.bin || true; sleep 2"
}
mkdir -p "$OUT"
shoot "$XLSX" "$OUT/excel-books.png"
shoot "$WORK/summary.xlsx" "$OUT/excel-summary.png"
rm -rf "$WORK"
ls -la "$OUT"/excel-*.png
