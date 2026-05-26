# Import dataclass to store normalized symbol style settings
from dataclasses import dataclass

# Import Path for filesystem paths
from pathlib import Path

# Import re for color and token parsing
import re

# Import math for pin direction geometry
import math

# Import existing S-expression helpers
from component_importer.symbol_footprint_linker import find_list_blocks_at_depth
from component_importer.symbol_footprint_linker import find_matching_paren
from component_importer.symbol_footprint_linker import find_symbol_blocks
from component_importer.symbol_footprint_linker import is_escaped
from component_importer.symbol_footprint_linker import remove_blocks_from_text
from component_importer.symbol_footprint_linker import starts_with_list_name


VALID_FILL_MODES = {
    "keep",
    "kicad_default",
    "color",
    "none",
    "outline",
    "background",
}
KICAD_DEFAULT_BODY_LINE_WIDTH_MM = 0.254
KICAD_DEFAULT_BODY_COLOR = "#840000"
KICAD_DEFAULT_TEXT_COLOR = "#006464"
KICAD_DEFAULT_PIN_NUMBER_COLOR = "#A90000"
# KiCad's common 100 mil pin length, stored in millimeters.
KICAD_DEFAULT_PIN_LENGTH_MM = 2.54
# Use 200 mil pins for denser symbols so pin numbers have more room.
KICAD_DENSE_SYMBOL_PIN_LENGTH_MM = 5.08
KICAD_DENSE_SYMBOL_PIN_COUNT_THRESHOLD = 9
KICAD_BODY_HORIZONTAL_PADDING_MM = 1.27
KICAD_PIN_NAME_MIDDLE_GAP_MM = 7.62
KICAD_PIN_NAME_TEXT_WIDTH_FACTOR = 0.8
KICAD_SYMBOL_GRID_MM = 2.54
KICAD_DEFAULT_FILL_COLOR = "#FFFFC2"
KICAD_DEFAULT_FILL_MODE = "kicad_default"
NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"


@dataclass
class SymbolStyle:
    line_width_mm: float = KICAD_DEFAULT_BODY_LINE_WIDTH_MM
    line_color: str = KICAD_DEFAULT_BODY_COLOR
    fill_mode: str = KICAD_DEFAULT_FILL_MODE
    fill_color: str = KICAD_DEFAULT_FILL_COLOR
    font_size_mm: float = 1.27
    pin_length_mm: float = KICAD_DEFAULT_PIN_LENGTH_MM


def format_kicad_number(value: float) -> str:
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")

    if text in {"", "-0"}:
        return "0"

    return text


def ceil_to_grid(value: float, grid: float) -> float:
    return math.ceil(value / grid) * grid


def normalize_float(
    value: object,
    fallback: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback

    if number < minimum:
        return minimum

    if number > maximum:
        return maximum

    return number


def normalize_hex_color(value: object, fallback: str = "#000000") -> str:
    text = str(value or "").strip()

    if not text:
        text = fallback

    if not text.startswith("#"):
        text = f"#{text}"

    short_match = re.fullmatch(r"#([0-9A-Fa-f]{3})", text)
    if short_match:
        chars = short_match.group(1)
        text = "#" + "".join(char * 2 for char in chars)

    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        return fallback.upper()

    return text.upper()


def normalize_fill_mode(
    value: object,
    fallback: str = KICAD_DEFAULT_FILL_MODE,
) -> str:
    fill_mode = str(value or "").strip().lower()

    if fill_mode in VALID_FILL_MODES:
        return fill_mode

    return fallback


def normalize_symbol_style(style: SymbolStyle | dict | None) -> SymbolStyle | None:
    if style is None:
        return None

    if isinstance(style, SymbolStyle):
        data = style.__dict__
    elif isinstance(style, dict):
        data = style
    else:
        raise TypeError("symbol_style must be a SymbolStyle, dict, or None.")

    return SymbolStyle(
        line_width_mm=normalize_float(
            data.get("line_width_mm"),
            fallback=KICAD_DEFAULT_BODY_LINE_WIDTH_MM,
            minimum=0.0,
            maximum=5.0,
        ),
        line_color=normalize_hex_color(
            data.get("line_color"),
            fallback=KICAD_DEFAULT_BODY_COLOR,
        ),
        fill_mode=normalize_fill_mode(
            data.get("fill_mode"),
            fallback=KICAD_DEFAULT_FILL_MODE,
        ),
        fill_color=normalize_hex_color(
            data.get("fill_color"),
            fallback=KICAD_DEFAULT_FILL_COLOR,
        ),
        font_size_mm=normalize_float(
            data.get("font_size_mm"),
            fallback=1.27,
            minimum=0.1,
            maximum=20.0,
        ),
        pin_length_mm=normalize_float(
            data.get("pin_length_mm"),
            fallback=KICAD_DEFAULT_PIN_LENGTH_MM,
            minimum=0.0,
            maximum=20.0,
        ),
    )


def symbol_style_to_dict(style: SymbolStyle) -> dict:
    return {
        "line_width_mm": style.line_width_mm,
        "line_color": style.line_color,
        "fill_mode": style.fill_mode,
        "fill_color": style.fill_color,
        "font_size_mm": style.font_size_mm,
        "pin_length_mm": style.pin_length_mm,
    }


def hex_color_to_rgb(color: str) -> tuple[int, int, int]:
    color = normalize_hex_color(color)

    return (
        int(color[1:3], 16),
        int(color[3:5], 16),
        int(color[5:7], 16),
    )


def find_list_blocks(text: str, list_name: str) -> list[dict]:
    blocks = []
    in_string = False
    index = 0

    while index < len(text):
        char = text[index]

        if char == '"' and not is_escaped(text, index):
            in_string = not in_string
            index += 1
            continue

        if in_string:
            index += 1
            continue

        if char == "(" and starts_with_list_name(text, index, list_name):
            end_index = find_matching_paren(text, index)
            blocks.append(
                {
                    "start": index,
                    "end": end_index,
                    "text": text[index:end_index + 1],
                }
            )
            index = end_index + 1
            continue

        index += 1

    return blocks


def get_child_token_value(parent_block: str, child_name: str, fallback: str) -> str:
    child_blocks = find_list_blocks_at_depth(
        text=parent_block,
        list_name=child_name,
        target_depth=1,
    )

    if not child_blocks:
        return fallback

    match = re.match(
        rf"\({re.escape(child_name)}\s+([^\s()]+)",
        child_blocks[0]["text"],
    )

    if not match:
        return fallback

    return match.group(1)


def build_stroke_block(style: SymbolStyle, old_stroke_block: str) -> str:
    stroke_type = get_child_token_value(
        parent_block=old_stroke_block,
        child_name="type",
        fallback="default",
    )
    red, green, blue = hex_color_to_rgb(style.line_color)

    return (
        f"(stroke (width {format_kicad_number(style.line_width_mm)}) "
        f"(type {stroke_type}) "
        f"(color {red} {green} {blue} 1))"
    )


def build_fill_block(style: SymbolStyle) -> str:
    if style.fill_mode in {"kicad_default", "color"}:
        fill_color = style.fill_color

        if style.fill_mode == "kicad_default":
            fill_color = KICAD_DEFAULT_FILL_COLOR

        red, green, blue = hex_color_to_rgb(fill_color)
        return f"(fill (type color) (color {red} {green} {blue} 1))"

    return f"(fill (type {style.fill_mode}))"


def build_rectangle_block(
    style: SymbolStyle,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    indent: str,
) -> str:
    return (
        f"{indent}(rectangle\n"
        f"{indent}  (start {format_kicad_number(min_x)} {format_kicad_number(max_y)})\n"
        f"{indent}  (end {format_kicad_number(max_x)} {format_kicad_number(min_y)})\n"
        f"{indent}  {build_stroke_block(style, '(stroke (type default))')}\n"
        f"{indent}  {build_fill_block(style)}\n"
        f"{indent})"
    )


def build_font_block(style: SymbolStyle) -> str:
    parts = ["(font"]

    font_size = format_kicad_number(style.font_size_mm)
    parts.append(f"(size {font_size} {font_size})")

    return " ".join(parts) + ")"


def floats_match(left: float, right: float, tolerance: float = 0.000001) -> bool:
    return abs(left - right) <= tolerance


def points_match(
    left: tuple[float, float],
    right: tuple[float, float],
    tolerance: float = 0.000001,
) -> bool:
    return (
        floats_match(left[0], right[0], tolerance)
        and floats_match(left[1], right[1], tolerance)
    )


def get_block_indent(text: str, start_index: int) -> str:
    line_start = text.rfind("\n", 0, start_index) + 1
    line_prefix = text[line_start:start_index]
    match = re.match(r"[ \t]*", line_prefix)

    if not match:
        return ""

    return match.group(0)


def parse_polyline_points(polyline_block: str) -> list[tuple[float, float]]:
    pts_blocks = find_list_blocks_at_depth(
        text=polyline_block,
        list_name="pts",
        target_depth=1,
    )

    if not pts_blocks:
        return []

    points = []

    for match in re.finditer(
        r"\(xy\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))\)",
        pts_blocks[0]["text"],
    ):
        points.append((float(match.group(1)), float(match.group(2))))

    return points


def build_axis_aligned_segment(block: dict) -> dict | None:
    points = parse_polyline_points(block["text"])

    if len(points) != 2:
        return None

    first, second = points

    if points_match(first, second):
        return None

    if floats_match(first[0], second[0]):
        return {
            **block,
            "orientation": "vertical",
            "x": first[0],
            "min_y": min(first[1], second[1]),
            "max_y": max(first[1], second[1]),
        }

    if floats_match(first[1], second[1]):
        return {
            **block,
            "orientation": "horizontal",
            "y": first[1],
            "min_x": min(first[0], second[0]),
            "max_x": max(first[0], second[0]),
        }

    return None


def find_rectangular_outline_polyline_groups(
    text: str,
    polyline_blocks: list[dict],
) -> list[dict]:
    segments = []

    for block in polyline_blocks:
        segment = build_axis_aligned_segment(block)

        if segment is not None:
            segments.append(segment)

    verticals = [
        segment
        for segment in segments
        if segment["orientation"] == "vertical"
    ]
    horizontals = [
        segment
        for segment in segments
        if segment["orientation"] == "horizontal"
    ]
    used_starts = set()
    groups = []

    for left_index, left in enumerate(verticals):
        if left["start"] in used_starts:
            continue

        for right in verticals[left_index + 1:]:
            if right["start"] in used_starts:
                continue

            if floats_match(left["x"], right["x"]):
                continue

            if not floats_match(left["min_y"], right["min_y"]):
                continue

            if not floats_match(left["max_y"], right["max_y"]):
                continue

            min_x = min(left["x"], right["x"])
            max_x = max(left["x"], right["x"])
            min_y = left["min_y"]
            max_y = left["max_y"]
            bottom = None
            top = None

            for horizontal in horizontals:
                if horizontal["start"] in used_starts:
                    continue

                if not floats_match(horizontal["min_x"], min_x):
                    continue

                if not floats_match(horizontal["max_x"], max_x):
                    continue

                if floats_match(horizontal["y"], min_y):
                    bottom = horizontal

                elif floats_match(horizontal["y"], max_y):
                    top = horizontal

            if bottom is None or top is None:
                continue

            rectangle_blocks = [left, right, bottom, top]
            first_block = min(rectangle_blocks, key=lambda item: item["start"])
            groups.append(
                {
                    "blocks": rectangle_blocks,
                    "insert_start": first_block["start"],
                    "min_x": min_x,
                    "max_x": max_x,
                    "min_y": min_y,
                    "max_y": max_y,
                    "indent": get_block_indent(text, first_block["start"]),
                }
            )
            used_starts.update(block["start"] for block in rectangle_blocks)
            break

    return groups


def replace_rectangular_outline_polylines(
    text: str,
    style: SymbolStyle,
) -> str:
    if style.fill_mode == "keep":
        return text

    polyline_blocks = find_list_blocks(text=text, list_name="polyline")
    rectangle_groups = find_rectangular_outline_polyline_groups(
        text=text,
        polyline_blocks=polyline_blocks,
    )

    for group in sorted(
        rectangle_groups,
        key=lambda item: item["insert_start"],
        reverse=True,
    ):
        first_start = group["insert_start"]
        rectangle_block = build_rectangle_block(
            style=style,
            min_x=group["min_x"],
            max_x=group["max_x"],
            min_y=group["min_y"],
            max_y=group["max_y"],
            indent=group["indent"],
        )

        for block in sorted(
            group["blocks"],
            key=lambda item: item["start"],
            reverse=True,
        ):
            replacement = rectangle_block if block["start"] == first_start else ""
            text = text[:block["start"]] + replacement + text[block["end"] + 1:]

    return text


def replace_effects_font(
    effects_block: str,
    style: SymbolStyle,
) -> str:
    font_blocks = find_list_blocks_at_depth(
        text=effects_block,
        list_name="font",
        target_depth=1,
    )
    color_blocks = find_list_blocks_at_depth(
        text=effects_block,
        list_name="color",
        target_depth=1,
    )

    cleaned_effects_block = remove_blocks_from_text(
        text=effects_block,
        blocks=font_blocks + color_blocks,
    )
    insert_position = len("(effects")
    remaining_effects = cleaned_effects_block[insert_position:].strip()

    if remaining_effects == ")":
        suffix = ")"
    else:
        suffix = f" {remaining_effects}"

    return (
        cleaned_effects_block[:insert_position]
        + " "
        + build_font_block(style)
        + suffix
    )


def replace_blocks_by_name(
    text: str,
    list_name: str,
    build_replacement,
) -> str:
    blocks = find_list_blocks(text=text, list_name=list_name)

    for block in sorted(blocks, key=lambda item: item["start"], reverse=True):
        replacement = build_replacement(block["text"])
        text = text[:block["start"]] + replacement + text[block["end"] + 1:]

    return text


def replace_effects_blocks(text: str, style: SymbolStyle) -> str:
    blocks = find_list_blocks(text=text, list_name="effects")

    for block in sorted(blocks, key=lambda item: item["start"], reverse=True):
        replacement = replace_effects_font(
            effects_block=block["text"],
            style=style,
        )
        text = text[:block["start"]] + replacement + text[block["end"] + 1:]

    return text


def remove_unsupported_effect_color_blocks(text: str) -> str:
    blocks = find_list_blocks(text=text, list_name="effects")

    for block in sorted(blocks, key=lambda item: item["start"], reverse=True):
        color_blocks = find_list_blocks_at_depth(
            text=block["text"],
            list_name="color",
            target_depth=1,
        )

        if not color_blocks:
            continue

        replacement = remove_blocks_from_text(
            text=block["text"],
            blocks=color_blocks,
        )
        text = text[:block["start"]] + replacement + text[block["end"] + 1:]

    return text


def parse_pin_at_block(at_block: str) -> tuple[float, float, float] | None:
    match = re.fullmatch(
        rf"\(at\s+({NUMBER_PATTERN})\s+({NUMBER_PATTERN})\s+({NUMBER_PATTERN})\)",
        at_block.strip(),
    )

    if not match:
        return None

    return (
        float(match.group(1)),
        float(match.group(2)),
        float(match.group(3)),
    )


def parse_point_block(
    point_block: str,
    point_name: str,
) -> tuple[float, float] | None:
    match = re.fullmatch(
        rf"\({re.escape(point_name)}\s+({NUMBER_PATTERN})\s+({NUMBER_PATTERN})\)",
        point_block.strip(),
    )

    if not match:
        return None

    return (float(match.group(1)), float(match.group(2)))


def parse_pin_length_block(length_block: str) -> float | None:
    match = re.fullmatch(
        rf"\(length\s+({NUMBER_PATTERN})\)",
        length_block.strip(),
    )

    if not match:
        return None

    return float(match.group(1))


def parse_pin_name(pin_block: str) -> str:
    name_blocks = find_list_blocks_at_depth(
        text=pin_block,
        list_name="name",
        target_depth=1,
    )

    if not name_blocks:
        return ""

    match = re.match(r'\(name\s+"((?:[^"\\]|\\.)*)"', name_blocks[0]["text"])

    if not match:
        return ""

    return match.group(1).replace(r"\"", '"').replace(r"\\", "\\")


def estimate_pin_name_width(name: str, font_size_mm: float) -> float:
    return len(name) * font_size_mm * KICAD_PIN_NAME_TEXT_WIDTH_FACTOR


def clean_pin_direction_value(value: float) -> float:
    if floats_match(value, 0.0):
        return 0.0

    if floats_match(value, 1.0):
        return 1.0

    if floats_match(value, -1.0):
        return -1.0

    return value


def build_pin_at_block(x: float, y: float, rotation: float) -> str:
    return (
        f"(at {format_kicad_number(x)} "
        f"{format_kicad_number(y)} "
        f"{format_kicad_number(rotation)})"
    )


def build_pin_length_block(length_mm: float) -> str:
    return f"(length {format_kicad_number(length_mm)})"


def build_point_block(point_name: str, x: float, y: float) -> str:
    return (
        f"({point_name} {format_kicad_number(x)} "
        f"{format_kicad_number(y)})"
    )


def normalize_pin_length_block(pin_block: str, pin_length_mm: float) -> str:
    at_blocks = find_list_blocks_at_depth(
        text=pin_block,
        list_name="at",
        target_depth=1,
    )
    length_blocks = find_list_blocks_at_depth(
        text=pin_block,
        list_name="length",
        target_depth=1,
    )

    if len(at_blocks) != 1 or len(length_blocks) != 1:
        return pin_block

    parsed_at = parse_pin_at_block(at_blocks[0]["text"])
    old_length = parse_pin_length_block(length_blocks[0]["text"])

    if parsed_at is None or old_length is None:
        return pin_block

    pin_x, pin_y, rotation = parsed_at
    new_length = pin_length_mm
    angle_radians = math.radians(rotation)
    direction_x = clean_pin_direction_value(math.cos(angle_radians))
    direction_y = clean_pin_direction_value(math.sin(angle_radians))
    inner_x = pin_x + direction_x * old_length
    inner_y = pin_y + direction_y * old_length
    new_pin_x = inner_x - direction_x * new_length
    new_pin_y = inner_y - direction_y * new_length

    replacements = [
        {
            **at_blocks[0],
            "replacement": build_pin_at_block(new_pin_x, new_pin_y, rotation),
        },
        {
            **length_blocks[0],
            "replacement": build_pin_length_block(new_length),
        },
    ]

    for block in sorted(replacements, key=lambda item: item["start"], reverse=True):
        pin_block = (
            pin_block[:block["start"]]
            + block["replacement"]
            + pin_block[block["end"] + 1:]
        )

    return pin_block


def normalize_symbol_pin_lengths(symbol_block: str, style: SymbolStyle) -> str:
    pin_blocks = find_list_blocks(text=symbol_block, list_name="pin")
    pin_length_mm = style.pin_length_mm

    if len(pin_blocks) > KICAD_DENSE_SYMBOL_PIN_COUNT_THRESHOLD:
        pin_length_mm = KICAD_DENSE_SYMBOL_PIN_LENGTH_MM

    for block in sorted(pin_blocks, key=lambda item: item["start"], reverse=True):
        replacement = normalize_pin_length_block(
            pin_block=block["text"],
            pin_length_mm=pin_length_mm,
        )
        symbol_block = (
            symbol_block[:block["start"]]
            + replacement
            + symbol_block[block["end"] + 1:]
        )

    return symbol_block


def parse_pin_geometry(pin_block: dict) -> dict | None:
    at_blocks = find_list_blocks_at_depth(
        text=pin_block["text"],
        list_name="at",
        target_depth=1,
    )
    length_blocks = find_list_blocks_at_depth(
        text=pin_block["text"],
        list_name="length",
        target_depth=1,
    )

    if len(at_blocks) != 1 or len(length_blocks) != 1:
        return None

    parsed_at = parse_pin_at_block(at_blocks[0]["text"])
    length = parse_pin_length_block(length_blocks[0]["text"])

    if parsed_at is None or length is None:
        return None

    pin_x, pin_y, rotation = parsed_at
    angle_radians = math.radians(rotation)
    direction_x = clean_pin_direction_value(math.cos(angle_radians))
    direction_y = clean_pin_direction_value(math.sin(angle_radians))

    return {
        **pin_block,
        "pin_x": pin_x,
        "pin_y": pin_y,
        "rotation": rotation,
        "length": length,
        "direction_x": direction_x,
        "direction_y": direction_y,
        "inner_x": pin_x + direction_x * length,
        "inner_y": pin_y + direction_y * length,
        "at_block": at_blocks[0],
        "name": parse_pin_name(pin_block["text"]),
    }


def parse_rectangle_geometry(rectangle_block: dict) -> dict | None:
    start_blocks = find_list_blocks_at_depth(
        text=rectangle_block["text"],
        list_name="start",
        target_depth=1,
    )
    end_blocks = find_list_blocks_at_depth(
        text=rectangle_block["text"],
        list_name="end",
        target_depth=1,
    )

    if len(start_blocks) != 1 or len(end_blocks) != 1:
        return None

    start_point = parse_point_block(start_blocks[0]["text"], "start")
    end_point = parse_point_block(end_blocks[0]["text"], "end")

    if start_point is None or end_point is None:
        return None

    min_x = min(start_point[0], end_point[0])
    max_x = max(start_point[0], end_point[0])
    min_y = min(start_point[1], end_point[1])
    max_y = max(start_point[1], end_point[1])

    return {
        **rectangle_block,
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "center_x": (min_x + max_x) / 2,
        "start_block": start_blocks[0],
        "end_block": end_blocks[0],
    }


def pin_inner_point_is_inside_y_range(pin: dict, rectangle: dict) -> bool:
    return (
        pin["inner_y"] >= rectangle["min_y"] - 0.000001
        and pin["inner_y"] <= rectangle["max_y"] + 0.000001
    )


def pin_inner_point_is_inside_x_range(pin: dict, rectangle: dict) -> bool:
    return (
        pin["inner_x"] >= rectangle["min_x"] - 0.000001
        and pin["inner_x"] <= rectangle["max_x"] + 0.000001
    )


def collect_rectangle_side_pins(
    rectangle: dict,
    pin_blocks: list[dict],
) -> tuple[list[dict], list[dict], bool]:
    left_pins = []
    right_pins = []
    has_top_or_bottom_pins = False

    for pin_block in pin_blocks:
        pin = parse_pin_geometry(pin_block)

        if pin is None:
            continue

        if (
            floats_match(pin["inner_x"], rectangle["min_x"])
            and pin_inner_point_is_inside_y_range(pin, rectangle)
            and floats_match(pin["direction_x"], 1.0)
        ):
            left_pins.append(pin)
            continue

        if (
            floats_match(pin["inner_x"], rectangle["max_x"])
            and pin_inner_point_is_inside_y_range(pin, rectangle)
            and floats_match(pin["direction_x"], -1.0)
        ):
            right_pins.append(pin)
            continue

        if (
            (
                floats_match(pin["inner_y"], rectangle["min_y"])
                or floats_match(pin["inner_y"], rectangle["max_y"])
            )
            and pin_inner_point_is_inside_x_range(pin, rectangle)
        ):
            has_top_or_bottom_pins = True

    return left_pins, right_pins, has_top_or_bottom_pins


def calculate_standard_body_width(
    left_pins: list[dict],
    right_pins: list[dict],
    style: SymbolStyle,
) -> float:
    left_width = max(
        [estimate_pin_name_width(pin["name"], style.font_size_mm) for pin in left_pins],
        default=0.0,
    )
    right_width = max(
        [estimate_pin_name_width(pin["name"], style.font_size_mm) for pin in right_pins],
        default=0.0,
    )
    raw_width = (
        left_width
        + right_width
        + KICAD_PIN_NAME_MIDDLE_GAP_MM
        + (KICAD_BODY_HORIZONTAL_PADDING_MM * 2)
    )

    return ceil_to_grid(raw_width, KICAD_SYMBOL_GRID_MM)


def build_resized_rectangle_block(
    rectangle_block: dict,
    new_min_x: float,
    new_max_x: float,
) -> str:
    block_text = rectangle_block["text"]
    replacements = [
        {
            **rectangle_block["start_block"],
            "replacement": build_point_block(
                "start",
                new_min_x,
                rectangle_block["max_y"],
            ),
        },
        {
            **rectangle_block["end_block"],
            "replacement": build_point_block(
                "end",
                new_max_x,
                rectangle_block["min_y"],
            ),
        },
    ]

    for block in sorted(replacements, key=lambda item: item["start"], reverse=True):
        block_text = (
            block_text[:block["start"]]
            + block["replacement"]
            + block_text[block["end"] + 1:]
        )

    return block_text


def build_moved_pin_block(pin: dict, new_inner_x: float) -> str:
    new_pin_x = new_inner_x - pin["direction_x"] * pin["length"]
    new_pin_y = pin["inner_y"] - pin["direction_y"] * pin["length"]
    replacement = build_pin_at_block(new_pin_x, new_pin_y, pin["rotation"])
    block_text = pin["text"]
    at_block = pin["at_block"]

    return (
        block_text[:at_block["start"]]
        + replacement
        + block_text[at_block["end"] + 1:]
    )


def normalize_symbol_body_width(symbol_block: str, style: SymbolStyle) -> str:
    rectangle_blocks = find_list_blocks(text=symbol_block, list_name="rectangle")
    pin_blocks = find_list_blocks(text=symbol_block, list_name="pin")
    replacements = []
    used_pin_starts = set()

    for rectangle_block in rectangle_blocks:
        rectangle = parse_rectangle_geometry(rectangle_block)

        if rectangle is None:
            continue

        left_pins, right_pins, has_top_or_bottom_pins = collect_rectangle_side_pins(
            rectangle=rectangle,
            pin_blocks=pin_blocks,
        )

        if has_top_or_bottom_pins or not left_pins or not right_pins:
            continue

        target_width = calculate_standard_body_width(
            left_pins=left_pins,
            right_pins=right_pins,
            style=style,
        )
        current_width = rectangle["max_x"] - rectangle["min_x"]

        if floats_match(target_width, current_width):
            continue

        new_min_x = rectangle["center_x"] - (target_width / 2)
        new_max_x = rectangle["center_x"] + (target_width / 2)
        replacements.append(
            {
                "start": rectangle["start"],
                "end": rectangle["end"],
                "replacement": build_resized_rectangle_block(
                    rectangle_block=rectangle,
                    new_min_x=new_min_x,
                    new_max_x=new_max_x,
                ),
            }
        )

        for pin in left_pins:
            if pin["start"] in used_pin_starts:
                continue

            replacements.append(
                {
                    "start": pin["start"],
                    "end": pin["end"],
                    "replacement": build_moved_pin_block(pin, new_min_x),
                }
            )
            used_pin_starts.add(pin["start"])

        for pin in right_pins:
            if pin["start"] in used_pin_starts:
                continue

            replacements.append(
                {
                    "start": pin["start"],
                    "end": pin["end"],
                    "replacement": build_moved_pin_block(pin, new_max_x),
                }
            )
            used_pin_starts.add(pin["start"])

    for replacement in sorted(replacements, key=lambda item: item["start"], reverse=True):
        symbol_block = (
            symbol_block[:replacement["start"]]
            + replacement["replacement"]
            + symbol_block[replacement["end"] + 1:]
        )

    return symbol_block


def normalize_pin_names_block(pin_names_block: str) -> str:
    offset_blocks = find_list_blocks_at_depth(
        text=pin_names_block,
        list_name="offset",
        target_depth=1,
    )
    cleaned_block = remove_blocks_from_text(
        text=pin_names_block,
        blocks=offset_blocks,
    )
    remaining = cleaned_block[len("(pin_names"):].strip()

    if remaining == ")":
        return ""

    return "(pin_names " + remaining


def remove_custom_pin_name_offsets(symbol_block: str) -> str:
    pin_name_blocks = find_list_blocks_at_depth(
        text=symbol_block,
        list_name="pin_names",
        target_depth=1,
    )

    for block in sorted(pin_name_blocks, key=lambda item: item["start"], reverse=True):
        replacement = normalize_pin_names_block(block["text"])
        symbol_block = (
            symbol_block[:block["start"]]
            + replacement
            + symbol_block[block["end"] + 1:]
        )

    return symbol_block


def apply_symbol_style_to_symbol_block(
    symbol_block: str,
    symbol_style: SymbolStyle | dict,
) -> str:
    style = normalize_symbol_style(symbol_style)

    if style is None:
        return symbol_block

    symbol_block = remove_custom_pin_name_offsets(symbol_block)
    symbol_block = normalize_symbol_pin_lengths(symbol_block, style)

    symbol_block = replace_blocks_by_name(
        text=symbol_block,
        list_name="stroke",
        build_replacement=lambda block_text: build_stroke_block(style, block_text),
    )

    if style.fill_mode != "keep":
        symbol_block = replace_blocks_by_name(
            text=symbol_block,
            list_name="fill",
            build_replacement=lambda _block_text: build_fill_block(style),
        )
        symbol_block = replace_rectangular_outline_polylines(
            text=symbol_block,
            style=style,
        )
        symbol_block = normalize_symbol_body_width(
            symbol_block=symbol_block,
            style=style,
        )

    symbol_block = replace_effects_blocks(text=symbol_block, style=style)

    return symbol_block


def apply_symbol_style_to_library_content(
    symbol_library_content: str,
    symbol_style: SymbolStyle | dict,
    symbol_names: list[str] | None = None,
) -> tuple[str, list[str]]:
    style = normalize_symbol_style(symbol_style)

    if style is None:
        return symbol_library_content, []

    requested_names = None
    if symbol_names is not None:
        requested_names = set(symbol_names)

    styled_symbol_names = []
    symbol_blocks = find_symbol_blocks(symbol_library_content)

    for block in sorted(symbol_blocks, key=lambda item: item["start"], reverse=True):
        symbol_name = block.get("name", "")

        if requested_names is not None and symbol_name not in requested_names:
            continue

        new_symbol_block = apply_symbol_style_to_symbol_block(
            symbol_block=block["text"],
            symbol_style=style,
        )

        if new_symbol_block != block["text"]:
            styled_symbol_names.append(symbol_name)
            symbol_library_content = (
                symbol_library_content[:block["start"]]
                + new_symbol_block
                + symbol_library_content[block["end"] + 1:]
            )

    styled_symbol_names.reverse()
    return symbol_library_content, styled_symbol_names


def apply_symbol_style_to_symbol_file(
    symbol_library_path: str | Path,
    symbol_style: SymbolStyle | dict,
    symbol_names: list[str] | None = None,
) -> dict:
    symbol_library_path = Path(symbol_library_path)
    style = normalize_symbol_style(symbol_style)

    if style is None:
        return {
            "symbol_library": str(symbol_library_path),
            "updated": False,
            "styled_symbol_names": [],
            "style": None,
        }

    content = symbol_library_path.read_text(encoding="utf-8", errors="ignore")
    updated_content, styled_symbol_names = apply_symbol_style_to_library_content(
        symbol_library_content=content,
        symbol_style=style,
        symbol_names=symbol_names,
    )
    updated = updated_content != content

    if updated:
        symbol_library_path.write_text(updated_content, encoding="utf-8")

    return {
        "symbol_library": str(symbol_library_path),
        "updated": updated,
        "styled_symbol_names": styled_symbol_names,
        "style": symbol_style_to_dict(style),
    }
