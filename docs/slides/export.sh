#!/usr/bin/env bash
# Re-export the deck to PDF and regenerate the README cover image from slide one.
set -euo pipefail
cd "$(dirname "$0")"

DECK=Rahul_Ramachandran_ReconMind-ProjectSubmission
SOFFICE=${SOFFICE:-$(command -v soffice || echo /Applications/LibreOffice.app/Contents/MacOS/soffice)}

"$SOFFICE" --headless --convert-to pdf --outdir . "$DECK.pptx"
uvx --with pymupdf python -c "import pymupdf; pymupdf.open('$DECK.pdf')[0].get_pixmap(dpi=144).save('cover.png')"
echo "wrote $DECK.pdf and cover.png"
