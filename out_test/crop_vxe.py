from PIL import Image
img = Image.open(r'D:\Desktop\a\out_test\screen3.png')
# BatteryTray window in the screenshot (2048x1152 source)
img.crop((120, 105, 690, 550)).save(r'D:\Desktop\a\out_test\vxe_fixed.png')
print(img.size)
