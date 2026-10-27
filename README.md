# EconStatTools
My econometric toolbox

## Content
- LaTeX template for streamlining method description
- Collection of method descriptions
- Individual folders, containing code (applications and construction) and descriptions for econometric tools  
- `tools/absalon_export.py`: exports course slides from Absalon (KU's Canvas) to a local/OneDrive folder and writes a `courses.md` overview of every course and module

## Exporting Absalon material
1. In Absalon go to **Account → Settings → + New access token** and copy the token.
2. Run on your own computer (Python 3.8+, no packages needed):
   ```
   python tools/absalon_export.py --out "~/OneDrive/Absalon"
   ```
   Paste the token when asked. Add `--all` for every file instead of just slides, or `--list-only` to only write `courses.md`.

The downloaded material is the lecturers' copyrighted work, so it stays in OneDrive and is not committed here.
