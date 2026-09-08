"""Build captions in explicit video coordinates, without inherited VTT styling."""
import html
import re
import textwrap

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Liberation Sans,48,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,5,108,108,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def seconds(stamp):
    hours, minutes, secs = stamp.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(secs)


def ass_time(value):
    ticks = round(value * 100)
    hours, ticks = divmod(ticks, 360000)
    minutes, ticks = divmod(ticks, 6000)
    secs, ticks = divmod(ticks, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{ticks:02}"


def write_centered_ass(srt, destination, scale=1.0):
    words = []
    for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8-sig").strip()):
        lines = block.splitlines()
        timing_index = next((i for i, line in enumerate(lines) if " --> " in line), None)
        if timing_index is None:
            continue
        start, end = lines[timing_index].split(" --> ")
        start, end = seconds(start), seconds(end.split()[0])
        text = " ".join(lines[timing_index + 1:])
        text = re.sub(r"\{[^}]*\}|<[^>]*>", "", text)
        text = html.unescape(text).replace("\\", "/").replace("{", "(").replace("}", ")")
        tokens = [fragment for word in text.split()
                  for fragment in textwrap.wrap(word, 18, break_on_hyphens=False)]
        if end <= start or not tokens:
            continue
        # The normal input has word timestamps. Older sentence cues are split
        # proportionally rather than displaying an entire sentence at once.
        total = sum(len(word) for word in tokens)
        cursor = start
        for word in tokens:
            finish = cursor + (end - start) * len(word) / total
            words.append((cursor * scale, finish * scale, word))
            cursor = finish
    if not words:
        raise ValueError("Narration returned no usable caption timestamps")
    groups = []
    group = []
    for word in words:
        proposed = " ".join(item[2] for item in group + [word])
        if group and (len(group) >= 4 or len(textwrap.wrap(proposed, 18)) > 2
                      or word[0] - group[-1][1] > 0.4):
            groups.append(group)
            group = []
        group.append(word)
    if group:
        groups.append(group)
    events = []
    for group in groups:
        text = r"\N".join(textwrap.wrap(" ".join(item[2] for item in group), 18))
        events.append(f"Dialogue: 0,{ass_time(group[0][0])},{ass_time(group[-1][1])},Default,,0,0,0,,"
                      + r"{\an5\pos(540,960)}" + text)
    destination.write_text(HEADER + "\n".join(events) + "\n", encoding="utf-8")
