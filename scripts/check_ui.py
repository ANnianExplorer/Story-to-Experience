"""Check shared UI tokens, contrast pairs and generated CSS; no browser claims."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / 'packages/ui/tokens.json'
CSS_PATH = ROOT / 'packages/ui/tokens.css'
CLASSICAL_PATH = ROOT / 'packages/ui/classical.css'
APP_STYLES = (
    ROOT / 'apps/workbench/src/styles.css',
    ROOT / 'apps/experience/src/styles.css',
    ROOT / 'apps/experience/src/backdrop.css',
    ROOT / 'apps/workbench/src/timeline.css',
)
REQUIRED_PAIRS = {
    ('ink', 'paper', 4.5), ('ink', 'surface', 4.5),
    ('muted', 'paper', 4.5), ('muted', 'surface', 4.5),
    ('surface', 'sea', 4.5), ('surface', 'sea-deep', 4.5),
    ('surface', 'accent', 4.5), ('accent-ink', 'accent-soft', 4.5),
    ('sea', 'sea-soft', 4.5), ('ink', 'foam', 4.5),
    ('error', 'error-soft', 4.5), ('success', 'success-soft', 4.5),
    ('warning', 'warning-soft', 4.5),
    ('control-border', 'surface', 3), ('sea-deep', 'paper', 3),
    # Editorial/classical roles added with the Kigo-inspired direction.
    ('surface', 'ink-void', 4.5), ('ink', 'paper-warm', 4.5),
    ('muted', 'paper-warm', 4.5), ('surface', 'seal', 4.5),
    ('seal', 'seal-soft', 4.5),
}


def luminance(value: str) -> float:
    channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels]
    return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(fg: str, bg: str) -> float:
    low, high = sorted((luminance(fg), luminance(bg)))
    return (high + 0.05) / (low + 0.05)


def render_css(tokens: dict) -> str:
    lines = ['/* Generated from tokens.json by scripts/check_ui.py --write. Do not edit. */', ':root {']
    def add(name: str, value: object) -> None:
        lines.append(f'  --xj-{name}: {value};')
    for name, value in tokens['colors'].items():
        add(f'color-{name}', value)
    add('font-family', tokens['font']['family'])
    for key, css_name in (
        ('display_family', 'font-display-family'),
        ('kai_family', 'font-kai-family'),
        ('label_family', 'font-label-family'),
    ):
        if key in tokens['font']:
            add(css_name, tokens['font'][key])
    for name, value in tokens['font']['size_px'].items():
        add(f'font-{name.replace("_", "-")}', f'{value}px')
    for name, value in tokens['font']['weight'].items():
        add(f'weight-{name}', value)
    for name, value in tokens['font']['line_height'].items():
        add(f'leading-{name}', value)
    for value in tokens['spacing_px']:
        add(f'space-{value}', f'{value}px')
    for name, value in tokens['radius_px'].items():
        add(f'radius-{name}', f'{value}px')
    for name, value in tokens['motion']['duration_ms'].items():
        add(f'motion-{name}', f'{value}ms')
    add('motion-stagger', f"{tokens['motion']['stagger_ms']}ms")
    add('motion-ease', 'cubic-bezier(' + ', '.join(str(x) for x in tokens['motion']['ease']) + ')')
    for name, value in tokens['motion']['translate_px'].items():
        add(f'motion-distance-{name}', f'{value}px')
    for name, value in tokens['motion']['scale'].items():
        add(f'motion-scale-{name}', value)
    lines.extend(['}', ''])
    return '\n'.join(lines)


HEX = re.compile(r'#[0-9A-Fa-f]{3,8}(?![0-9A-Za-z])')
RAW_COLOR = re.compile(r'(?:rgba?|hsla?)\(')


def defined_variables(tokens: dict) -> set[str]:
    names = {f'color-{key}' for key in tokens['colors']}
    names |= {f'font-{key.replace("_", "-")}' for key in tokens['font']['size_px']}
    names |= {f'weight-{key}' for key in tokens['font']['weight']}
    names |= {f'leading-{key}' for key in tokens['font']['line_height']}
    names |= {f'space-{value}' for value in tokens['spacing_px']}
    names |= {f'radius-{key}' for key in tokens['radius_px']}
    names |= {f'motion-{key}' for key in tokens['motion']['duration_ms']}
    names |= {'motion-stagger', 'motion-ease', 'font-family'}
    names |= {f'motion-distance-{key}' for key in tokens['motion']['translate_px']}
    names |= {f'motion-scale-{key}' for key in tokens['motion']['scale']}
    names |= {f'font-{key.replace("_", "-")}' for key in tokens['font'] if key.endswith('_family')}
    return names


def check_stylesheets(tokens: dict | None = None) -> list[str]:
    """Shared and app stylesheets must consume tokens, not declare values.

    The only allowed literal colours are inside the token-derived file itself.
    A hex literal or rgb()/hsl() call in a hand-written sheet means a second
    palette has appeared, so it fails here instead of drifting silently.
    """
    errors: list[str] = []
    allowed = defined_variables(tokens) if tokens is not None else set()
    sheets = [CLASSICAL_PATH, *APP_STYLES]
    for sheet in sheets:
        if not sheet.exists():
            continue
        text = sheet.read_text(encoding='utf-8')
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith('/*') or stripped.startswith('*'):
                continue
            found = HEX.findall(line) or RAW_COLOR.findall(line)
            if found:
                errors.append(
                    f'{sheet.resolve().relative_to(ROOT)}:{number} 使用了直接颜色值 {found[0]}，请改用 --xj- Token'
                )
            if tokens is not None:
                for name in re.findall(r'var\(--xj-([a-z0-9-]+)\)', line):
                    if name not in allowed:
                        errors.append(
                            f'{sheet.resolve().relative_to(ROOT)}:{number} 引用了未定义的 --xj-{name}（会在浏览器里静默失效）'
                        )
    return errors


def validate(tokens: dict) -> tuple[list[str], list[dict]]:
    errors: list[str] = []
    results: list[dict] = []
    colors = tokens['colors']
    for role in {'paper', 'surface', 'ink', 'muted', 'sea', 'sea-deep', 'sea-soft', 'foam', 'accent', 'accent-soft', 'accent-ink', 'ornament', 'border', 'control-border', 'error', 'error-soft', 'success', 'success-soft', 'warning', 'warning-soft', 'ink-void', 'paper-warm', 'seal', 'seal-soft', 'gilded', 'mist'}:
        if role not in colors:
            errors.append(f'missing color role: {role}')
    for name, value in colors.items():
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', value):
            errors.append(f'invalid HEX: {name}')
    pairs = tokens['contrast_pairs']
    actual_pairs = {(p['foreground'], p['background'], p['minimum']) for p in pairs}
    if not REQUIRED_PAIRS <= actual_pairs:
        errors.append('required contrast pairs removed or threshold changed')
    if errors:
        return errors, results
    for pair in pairs:
        fg, bg = pair['foreground'], pair['background']
        if fg not in colors or bg not in colors:
            errors.append(f'unknown contrast role: {fg}/{bg}')
            continue
        ratio = contrast(colors[fg], colors[bg])
        results.append({'pair': f'{fg}/{bg}', 'ratio': round(ratio, 3), 'minimum': pair['minimum']})
        # Compare unrounded numbers; 4.499 is not a 4.5 pass.
        if ratio < pair['minimum']:
            errors.append(f'contrast below threshold: {fg}/{bg}={ratio:.6f}')
    motion = tokens['motion']
    durations = motion['duration_ms']
    for name in ('fast', 'base', 'panel', 'scene', 'title', 'feedback', 'reduced'):
        if name not in durations:
            errors.append(f'missing motion duration: {name}')
    for name, value in durations.items():
        if not isinstance(value, (int, float)) or not 0 <= value <= 600:
            errors.append(f'invalid/overlong duration: {name}')
    if durations.get('reduced') != 0:
        errors.append('reduced motion must be immediate by default')
    if not 1 <= motion['title_max_groups'] <= 8 or not 0 <= motion['stagger_ms'] <= 50:
        errors.append('title grouping or stagger outside budget')
    total = durations.get('title', 0) + motion['stagger_ms'] * (motion['title_max_groups'] - 1)
    if total > motion['title_total_max_ms'] or motion['title_total_max_ms'] > 800:
        errors.append('title sequence exceeds 800ms budget')
    if any(not 0 <= value <= 16 for value in motion['translate_px'].values()):
        errors.append('translation exceeds 16px budget')
    if tokens['font']['size_px']['body'] < 16 or tokens['font']['size_px']['label'] < 12:
        errors.append('text below project minimum')
    if tokens['spacing_px'] != sorted(set(tokens['spacing_px'])) or any(x <= 0 or x % 4 for x in tokens['spacing_px']):
        errors.append('spacing must be unique positive multiples of four')
    return errors, results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Regenerate CSS after token checks pass')
    args = parser.parse_args()
    try:
        tokens = json.loads(TOKEN_PATH.read_text(encoding='utf-8'))
        errors, pairs = validate(tokens)
        errors.extend(check_stylesheets(tokens))
        if not errors:
            css = render_css(tokens)
            if args.write:
                CSS_PATH.write_text(css, encoding='utf-8', newline='\n')
            if not CSS_PATH.exists() or CSS_PATH.read_text(encoding='utf-8') != css:
                errors.append('generated CSS differs; run python scripts/check_ui.py --write')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors, pairs = [f'invalid token file: {exc}'], []
    print(json.dumps({'check': 'ui_token_baseline', 'status': 'failed' if errors else 'passed', 'contrast_pairs': pairs, 'errors': errors, 'scope': 'token/CSS/declared-pair/no-literal-colour checks; production React, real page contrast, motion and browser acceptance not implied'}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
