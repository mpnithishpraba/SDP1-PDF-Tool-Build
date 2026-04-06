# TWZ Pdf — Build Instructions

## Prerequisites
- Python 3.8+ installed on build machine
- pip available

## Step 1: Install Dependencies
```
pip install PyMuPDF Pillow pyinstaller
```

## Step 2: Generate Icon (if not already done)
```
python -c "from PIL import Image; img = Image.open('ICON.jpg'); sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]; imgs = [img.resize(s, Image.LANCZOS) for s in sizes]; imgs[0].save('icon.ico', format='ICO', sizes=[(s,s) for s in [16,32,48,64,128,256]], append_images=imgs[1:])"
```

## Step 3: Build EXE
```
pyinstaller build.spec
```

## Step 4: Find Output
The resulting EXE will be at:
```
dist\TWZ Pdf.exe
```

## Notes
- The EXE bundles Python runtime + all libraries (~50-100MB)
- No Python installation needed on target machine
- No internet access required — fully offline
- Works on Windows 10 and 11 (best-effort Win7 support)
