import hid
for d in hid.enumerate():
    print(f"{d.get('vendor_id',0):04X}:{d.get('product_id',0):04X} usage={d.get('usage_page')}:{d.get('usage')} if={d.get('interface_number')} {d.get('product_string')!r}")
