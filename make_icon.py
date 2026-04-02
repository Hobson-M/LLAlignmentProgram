from PIL import Image

# Convert the logo to ICO format
logo_path = r"C:\Users\Koku\.gemini\antigravity\brain\981b5d7f-bc94-4ead-9ad3-327a61333b7b\betting_tracker_icon_1775090188411.png"
ico_path = r"c:\Users\Koku\Desktop\betting-tracker\static\icon.ico"

img = Image.open(logo_path)
img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])

print("Icon created successfully at", ico_path)
