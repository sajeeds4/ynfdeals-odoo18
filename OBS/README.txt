OBS WHATNOT OVERLAY TEMPLATE

FILES
- overlay.html      -> add this as an OBS Browser Source
- style.css         -> overlay styling
- app.js            -> auto-refreshes data from data.json
- data.json         -> all editable text values
- controller.py     -> quick terminal editor for data.json

HOW TO LOAD IN OBS
1. Open OBS.
2. Set canvas to 1080x1920.
3. Add your main live camera as a Video Capture Device.
4. Add your top-right product video as a Media Source and place it under the overlay.
5. Add Browser Source:
   - Local file: checked
   - File: choose overlay.html
   - Width: 1080
   - Height: 1920
6. Put the Browser Source above your camera and video sources.
7. Fit the main camera inside the transparent left area.
8. Fit your product video inside the top-right framed box.

HOW TO CHANGE TEXT FAST
Option A:
- Open data.json in any editor and change the values.
- OBS browser source refreshes automatically every ~1.5 seconds.

Option B:
- Run in terminal:
  python3 controller.py
- Fill in the prompts.

RECOMMENDED OBS SOURCE ORDER
1. Main Camera
2. Product Video (top-right)
3. Browser Source -> overlay.html

NOTE
I cannot open OBS from here, but this template is ready for you to load directly into OBS.
