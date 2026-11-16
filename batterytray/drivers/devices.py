"""A model library for the supported wireless mice, keyboards and headsets.

A lot of these peripherals expose the *same* vendor HID protocol, and one
receiver often serves several models. The protocol therefore cannot tell the
model apart — only the USB product id can. This module keeps that mapping in
one place, so adding a model is a data change and not a code change.

The table was collected from the open-source projects listed in
``README.md``. Every row names the protocol family it belongs to, so the
drivers can be checked against it.

References:
    435311382/Volt                       - docs/DEVICES.md, 137 models
    Fan4Metal/mouse_tray                 - the chipset tables
    ahutsunboy/2.4g-battery-tray-python  - the receiver pid lists
    ryanlewis/mousebatt                  - the Pulsar and VAXEE receivers
"""

from __future__ import annotations

# The kinds of peripheral a model can be. They match the kinds the app uses.
KIND_MOUSE = "mouse"
KIND_KEYBOARD = "keyboard"
KIND_HEADSET = "headset"
KIND_CONTROLLER = "controller"


class Model:
    """One known peripheral model."""

    __slots__ = ("name", "kind", "vendor", "protocol")

    def __init__(self, name: str, kind: str, vendor: str, protocol: str):
        self.name = name
        self.kind = kind
        self.vendor = vendor
        self.protocol = protocol

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Model({self.name!r}, {self.kind!r})"


# The models, keyed by ``(vendor id, product id)``. A product id that is not
# in the table is still usable: the protocol name is shown instead.
MODELS: dict[tuple[int, int], Model] = {}


def _add(vendor_id: int, product_ids: tuple[int, ...], name: str, kind: str,
         vendor: str, protocol: str) -> None:
    """Registers one model under every one of its product ids."""
    model = Model(name, kind, vendor, protocol)
    for product_id in product_ids:
        MODELS[(vendor_id, product_id)] = model


# ----------------------------------------------------------------------
# ATK / VXE / VGN — the Compx frame family.
# The dongle and the wired mouse use different product ids, so both are
# listed and the app shows one row for the pair.
# ----------------------------------------------------------------------
_add(0x373B, (0x10C9,), "ATK X1 SE", KIND_MOUSE, "ATK", "compx17")
_add(0x373B, (0x1031,), "ATK F1 Ultimate", KIND_MOUSE, "ATK", "compx17")
_add(0x373B, (0x11D9,), "ATK A9 Ultimate", KIND_MOUSE, "ATK", "compx17")
_add(0x373B, (0x1155, 0x124F), "ATK Zero", KIND_MOUSE, "ATK", "compx64")
_add(0x373B, (0x104D,), "VXE MAD R", KIND_MOUSE, "VXE", "compx17")
_add(0x373B, (0x1040,), "VXE MAD R Major Plus", KIND_MOUSE, "VXE", "compx17")
_add(0x373B, (0x1085,), "VXE R1 SE+ 1K 接收器", KIND_MOUSE, "VXE", "compx17")
_add(0x3554, (0xF58A,), "VXE R1 Pro Max", KIND_MOUSE, "VXE", "compx17")
_add(0x3554, (0xF58E,), "VXE R1 SE+", KIND_MOUSE, "VXE", "compx17")
_add(0x3554, (0xF503,), "VGN F1 Pro", KIND_MOUSE, "VGN", "compx17")
_add(0x3554, (0xFB3E,), "VGN F2 Pro Max", KIND_MOUSE, "VGN", "compx17")
_add(0x3554, (0xF524,), "Zaopin Z2 Mini", KIND_MOUSE, "Zaopin", "compx17")
_add(0x3554, (0xF5F7,), "Scyrox V8", KIND_MOUSE, "Scyrox", "compx17")
_add(0x260D, (0x1175,), "Dareu A950 Air", KIND_MOUSE, "Dareu", "compx17")
_add(0x260D, (0x1154,), "Dareu A950 Wing", KIND_MOUSE, "Dareu", "compx17")
_add(0x33E4, (0x3854,), "G-Wolves Lycan", KIND_MOUSE, "G-Wolves", "compx17")

# The VXE R1 series is also sold with dongles of its own.
_add(0x320F, (0x5055,), "VXE R1 SE+ 接收器", KIND_MOUSE, "VXE", "compx17")
_add(0x3537, (0x2106,), "VXE R1 SE+ 接收器", KIND_MOUSE, "VXE", "compx17")

# ----------------------------------------------------------------------
# AULA / LEOBOG / 狼蛛 — the 20 byte frame. The receiver product id
# 0xFA09 is shared by several brands, so one entry lists them all.
# ----------------------------------------------------------------------
_add(0x3554, (0xFA09,), "AULA F75 / F99 键盘", KIND_KEYBOARD, "AULA", "aula")
_add(0x3554, (0xFA0A, 0xFA10), "AULA F87 键盘", KIND_KEYBOARD, "AULA", "aula")
_add(0x3554, (0xFA08,), "AULA F68 键盘", KIND_KEYBOARD, "AULA", "aula")
_add(0x3554, (0xFA60,), "Attack Shark X3 鼠标", KIND_MOUSE, "Attack Shark", "aula")
_add(0x258A, (0x0138,), "迈从 G3 无线鼠标", KIND_MOUSE, "迈从", "aula")

# ----------------------------------------------------------------------
# Pulsar — the same 17 byte Compx frame on its own vendor id.
# ----------------------------------------------------------------------
_add(0x3710, (0x5406,), "Pulsar 8K 接收器 Gen.2", KIND_MOUSE, "Pulsar", "compx17")
_add(0x3710, (0x5403, 0x3408), "Pulsar 8K 接收器 XS-1", KIND_MOUSE, "Pulsar", "pulsar")

# ----------------------------------------------------------------------
# Attack Shark — the dongle pushes the level on its own.
# ----------------------------------------------------------------------
_add(0x1D57, (0xFA60,), "Attack Shark X3 鼠标", KIND_MOUSE, "Attack Shark", "attackshark")
_add(0x1D57, (0xFA62,), "Attack Shark X6 鼠标", KIND_MOUSE, "Attack Shark", "attackshark")
_add(0x1D57, (0xFA61,), "Attack Shark R1 鼠标", KIND_MOUSE, "Attack Shark", "attackshark")

# ----------------------------------------------------------------------
# MCHOSE / 迈从 — the control collection with the xor obfuscation.
# ----------------------------------------------------------------------
_add(0x3837, (0x1020,), "MCHOSE L7 Pro 鼠标", KIND_MOUSE, "MCHOSE", "mchose")
_add(0x3837, (0x1001,), "MCHOSE K7 Ultra 鼠标", KIND_MOUSE, "MCHOSE", "mchose")
_add(0x5253, (0x1020,), "MCHOSE L7 Pro 鼠标", KIND_MOUSE, "MCHOSE", "mchose")
_add(0x5253, (0x1021,), "MCHOSE A7 Pro 鼠标", KIND_MOUSE, "MCHOSE", "mchose")

# ----------------------------------------------------------------------
# Keychron — the vendor collection with usage page 0xFFC1.
# ----------------------------------------------------------------------
_add(0x3434, (0xD028,), "Keychron 接收器", KIND_MOUSE, "Keychron", "keychron")
_add(0x3434, (0xD048,), "Keychron M5 鼠标", KIND_MOUSE, "Keychron", "keychron")
_add(0x3434, (0xD049,), "Keychron M6 8K 鼠标", KIND_MOUSE, "Keychron", "keychron")
_add(0x3434, (0xD056,), "Keychron M7 8K 鼠标", KIND_MOUSE, "Keychron", "keychron")

# ----------------------------------------------------------------------
# Rapoo / 雷柏 — the dongle pushes a status packet.
# ----------------------------------------------------------------------
_add(0x24AE, (0x4077,), "雷柏 VT 系列鼠标", KIND_MOUSE, "Rapoo", "rapoo")

# ----------------------------------------------------------------------
# Lamzu / 达尔优 / Ninjutso / HyperX / Bloody — the feature reports.
# ----------------------------------------------------------------------
_add(0x373E, (0x0010,), "Lamzu Inca 鼠标", KIND_MOUSE, "Lamzu", "lamzu")
_add(0x373E, (0x001E,), "Lamzu Maya X 鼠标", KIND_MOUSE, "Lamzu", "lamzu")
_add(0x373E, (0x0040,), "Lamzu Thorn V2 鼠标", KIND_MOUSE, "Lamzu", "lamzu")
_add(0x37B0, (0x0010,), "Lamzu Inca 鼠标", KIND_MOUSE, "Lamzu", "lamzu")
_add(0x1915, (0xAE1C,), "Ninjutso Sora V2 鼠标", KIND_MOUSE, "Ninjutso", "ninjutso")
_add(0x03F0, (0x08BE,), "HyperX Cloud Alpha 2 无线耳机", KIND_HEADSET, "HyperX", "hyperx")
_add(0x03F0, (0x16ED,), "HyperX Cloud Alpha S 无线耳机", KIND_HEADSET, "HyperX", "hyperx")
_add(0x03F0, (0x098D,), "HyperX Cloud Alpha 无线耳机", KIND_HEADSET, "HyperX", "hyperx")
_add(0x03F0, (0x05B7,), "HyperX Cloud III 无线耳机", KIND_HEADSET, "HyperX", "hyperx")
_add(0x1956, (0x3069,), "Bloody SG5 Pro 鼠标", KIND_MOUSE, "A4Tech", "bloody")

# ----------------------------------------------------------------------
# SteelSeries — the keyboard and the headset families.
# ----------------------------------------------------------------------
_add(0x1038, (0x12B3, 0x12B6, 0x12D7, 0x12D5), "SteelSeries Arctis 1 耳机", KIND_HEADSET, "SteelSeries", "steelseries")
_add(0x1038, (0x1260, 0x12AD, 0x1252, 0x1280), "SteelSeries Arctis 7 耳机", KIND_HEADSET, "SteelSeries", "steelseries")
_add(0x1038, (0x12C2, 0x12C4), "SteelSeries Arctis 9 耳机", KIND_HEADSET, "SteelSeries", "steelseries")
_add(0x1038, (0x1290,), "SteelSeries Arctis Pro 无线耳机", KIND_HEADSET, "SteelSeries", "steelseries")
_add(0x1038, (0x220E, 0x2212, 0x2216, 0x2236), "SteelSeries Arctis 7+ 耳机", KIND_HEADSET, "SteelSeries", "steelseries_nova")
_add(0x1038, (0x12EC,), "SteelSeries Nova 3 耳机", KIND_HEADSET, "SteelSeries", "steelseries_nova")
_add(0x1038, (0x2269, 0x226D), "SteelSeries Nova 3P 耳机", KIND_HEADSET, "SteelSeries", "steelseries_nova")
_add(0x1038, (0x2232, 0x2253), "SteelSeries Nova 5 耳机", KIND_HEADSET, "SteelSeries", "steelseries_nova")
_add(0x1038, (0x220A, 0x2298, 0x22A7), "SteelSeries Nova 7P 耳机", KIND_HEADSET, "SteelSeries", "steelseries_nova")
_add(0x1038, (0x12E0, 0x12E5), "SteelSeries Nova Pro 无线耳机", KIND_HEADSET, "SteelSeries", "steelseries_nova")
_add(0x1038, (0x230A,), "SteelSeries GameBuds 耳机", KIND_HEADSET, "SteelSeries", "steelseries_nova")

# ----------------------------------------------------------------------
# Other vendors whose protocol is known but whose model list is short.
# ----------------------------------------------------------------------
_add(0x1B1C, (0x0A14, 0x0A16, 0x0A17, 0x0A1A, 0x0A1D, 0x0A2B, 0x0A38,
                0x0A4F, 0x0A51, 0x0A52, 0x0A55, 0x0A56, 0x0A75, 0x1B23,
                0x1B27, 0x1B29, 0x1B2A),
    "Corsair Void 耳机", KIND_HEADSET, "Corsair", "corsair_void")
_add(0x1B1C, (0x0A64, 0x0A62), "Corsair Virtuoso XT 耳机", KIND_HEADSET, "Corsair", "corsair_virtuoso")
_add(0x0B0E, (0x2519,), "Jabra Evolve2 65 Flex 耳机", KIND_HEADSET, "Jabra", "jabra")
_add(0x0B0E, (0x24C7,), "Jabra Link 380 耳机", KIND_HEADSET, "Jabra", "jabra")
_add(0x0B0E, (0x2E57,), "Jabra Link 390 耳机", KIND_HEADSET, "Jabra", "jabra")
_add(0x054C, (0x0EC2,), "Sony INZONE Buds 耳机", KIND_HEADSET, "Sony", "sony_inzone")
_add(0x3329, (0x4B19,), "Audeze Maxwell 耳机", KIND_HEADSET, "Audeze", "audeze")
_add(0x3329, (0x4B29,), "Audeze Maxwell 2 耳机", KIND_HEADSET, "Audeze", "audeze")
_add(0x17EF, (0xA07D,), "Lenovo 无线耳麦", KIND_HEADSET, "Lenovo", "lenovo_voip")
_add(0x047F, (0x02EE,), "Plantronics BT600 耳机", KIND_HEADSET, "Plantronics", "plantronics")
_add(0x3837, (0x385D,), "MCHOSE V9 Pro 耳机", KIND_HEADSET, "MCHOSE", "mchose_headset")
_add(0x3837, (0x6045,), "MCHOSE X9 耳机", KIND_HEADSET, "MCHOSE", "mchose_headset")
_add(0x1532, (0x0555, 0x1014), "Razer BlackShark V2 Pro 耳机", KIND_HEADSET, "Razer", "razer_headset")
_add(0x0B05, (0x193E,), "ASUS ROG Falchion 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1B84,), "ASUS ROG PELTA 耳机", KIND_HEADSET, "ASUS", "asus")
_add(0x1915, (0x910B,), "NINX NX60 ANSI 键盘", KIND_KEYBOARD, "NINX", "ninjutso")
_add(0x093A, (0x522C,), "Incott G24 Pro 鼠标", KIND_MOUSE, "Incott", "aula")

# ----------------------------------------------------------------------
# Lofree — the Hyzen keyboard on its 2.4 GHz dongle.
# ----------------------------------------------------------------------
_add(0x388D, (0x0025,), "Lofree Hyzen 键盘", KIND_KEYBOARD, "Lofree", "lofree")

# ----------------------------------------------------------------------
# NZXT — the Lift Elite mouse on its dongle and on its cable.
# ----------------------------------------------------------------------
_add(0x1E71, (0x2101,), "NZXT Lift Elite 无线鼠标", KIND_MOUSE, "NZXT", "nzxt")
_add(0x1E71, (0x2129,), "NZXT Lift Elite 无线鼠标", KIND_MOUSE, "NZXT", "nzxt")

# ----------------------------------------------------------------------
# ASUS ROG — the keyboard families that answer the power query.
# ----------------------------------------------------------------------
_add(0x0B05, (0x193C,), "ASUS ROG Falchion 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1B04,), "ASUS ROG Falchion RX 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x196B,), "ASUS ROG Claymore II 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1A85,), "ASUS ROG Azoth 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1B42,), "ASUS ROG Azoth Extreme 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1CF1,), "ASUS ROG Azoth Extreme SE 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
# The Omni receiver carries the keyboards on its own channel. Its product id
# is the one of the receiver, so the name of the keyboard behind it comes
# from the pair list instead. The kind is the keyboard, because that is what
# the receiver shows the level of.
_add(0x0B05, (0x1ACE,), "ASUS ROG Omni 接收器", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1AB3,), "ASUS ROG Strix Scope II 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1AB5,), "ASUS ROG Strix Scope II RX 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1AAE,), "ASUS ROG Strix Scope II 96 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1B78,), "ASUS ROG Strix Scope II 96 RX 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x19FE,), "ASUS ROG Strix Flare II 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x19FC,), "ASUS ROG Strix Flare II Animate 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x194B,), "ASUS TUF GAMING K3 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1B30,), "ASUS TUF GAMING K3 Gen II 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1C60,), "ASUS TUF GAMING K3 Gen II 鸭子版键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")
_add(0x0B05, (0x1B3A,), "ASUS TX 98 键盘", KIND_KEYBOARD, "ASUS", "asus_keyboard")


def lookup(vendor_id: int, product_id: int) -> Model | None:
    """Returns the model for a USB id, or ``None`` when it is unknown."""
    return MODELS.get((vendor_id, product_id))


def known_vendor_ids() -> set[int]:
    """The vendor ids that have at least one known model."""
    return {vendor_id for vendor_id, _ in MODELS}
