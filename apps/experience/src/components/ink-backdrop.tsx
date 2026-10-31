/**
 * Atmospheric background for the participant experience.
 *
 * Drawn by us with SVG + CSS (no reference-site assets): layered ink washes for
 * distant ridges, a brushy plum branch entering from the upper right, slow mist
 * bands and a few drifting petals. Nothing here carries information, it sits
 * behind all content, and every motion stops under `prefers-reduced-motion`.
 */
import React, { useMemo } from 'react';

interface Petal {
  left: number;
  delay: number;
  duration: number;
  size: number;
  drift: number;
  spin: number;
}

/** Deterministic pseudo-random: a re-render must not reshuffle the petals. */
function seeded(index: number, salt: number): number {
  const value = Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453;
  return value - Math.floor(value);
}

/** One tapering brush stroke: wide at the trunk, fine at the tip. */
function branchPath(points: readonly [number, number][], startWidth: number, endWidth: number): string {
  const left: string[] = [];
  const right: string[] = [];
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    if (!point) continue;
    const previous = points[Math.max(index - 1, 0)] ?? point;
    const next = points[Math.min(index + 1, points.length - 1)] ?? point;
    const dx = (next[0] ?? 0) - (previous[0] ?? 0);
    const dy = (next[1] ?? 0) - (previous[1] ?? 0);
    const length = Math.hypot(dx, dy) || 1;
    const ratio = index / Math.max(points.length - 1, 1);
    const width = startWidth + (endWidth - startWidth) * ratio;
    const nx = (-dy / length) * (width / 2);
    const ny = (dx / length) * (width / 2);
    left.push(`${(point[0] ?? 0) + nx},${(point[1] ?? 0) + ny}`);
    right.unshift(`${(point[0] ?? 0) - nx},${(point[1] ?? 0) - ny}`);
  }
  return `M${left.join(' L')} L${right.join(' L')} Z`;
}

const MAIN_BRANCH: readonly [number, number][] = [
  [900, -10],
  [806, 34],
  [720, 62],
  [636, 84],
  [552, 116],
  [470, 142],
  [392, 176],
  [318, 200],
  [246, 232],
  [176, 262],
  [112, 300],
  [52, 342],
];

const TWIGS: readonly { points: readonly [number, number][]; width: number }[] = [
  { points: [[552, 116], [596, 160], [636, 196], [678, 218]], width: 5 },
  { points: [[470, 142], [452, 196], [436, 248], [420, 300]], width: 4.4 },
  { points: [[392, 176], [356, 222], [330, 268], [312, 314]], width: 3.6 },
  { points: [[318, 200], [286, 240], [258, 278]], width: 3.2 },
  { points: [[678, 218], [722, 236], [766, 240]], width: 2.8 },
  { points: [[246, 232], [210, 206], [178, 184]], width: 2.4 },
  { points: [[176, 262], [148, 236], [126, 210]], width: 2 },
];

const BLOSSOMS: readonly { x: number; y: number; scale: number }[] = [
  { x: 678, y: 218, scale: 2.1 },
  { x: 636, y: 196, scale: 1.6 },
  { x: 452, y: 196, scale: 1.9 },
  { x: 420, y: 300, scale: 1.7 },
  { x: 330, y: 268, scale: 1.8 },
  { x: 258, y: 278, scale: 1.5 },
  { x: 210, y: 206, scale: 1.4 },
  { x: 126, y: 210, scale: 1.5 },
  { x: 766, y: 240, scale: 1.2 },
  { x: 112, y: 300, scale: 1.3 },
  { x: 552, y: 116, scale: 1.1 },
  { x: 392, y: 176, scale: 1 },
  { x: 312, y: 314, scale: 1.2 },
  { x: 178, y: 184, scale: 0.9 },
];

/** Five-petal plum blossom: five rotated ellipses around a speckled centre. */
function Blossom({ x, y, scale }: { x: number; y: number; scale: number }) {
  const petals = [0, 72, 144, 216, 288];
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      {petals.map((angle) => (
        <ellipse key={angle} className="blossom-petal" cx={0} cy={-7} rx={3.1} ry={5.2} transform={`rotate(${angle})`} />
      ))}
      <circle className="blossom-core" r={1.7} />
    </g>
  );
}

export function InkBackdrop({ seed = 1 }: { seed?: number }) {
  const petals = useMemo<Petal[]>(
    () =>
      Array.from({ length: 10 }, (_, index) => ({
        left: 8 + seeded(index, seed) * 84,
        delay: seeded(index, seed + 1) * 18,
        duration: 22 + seeded(index, seed + 2) * 16,
        size: 5 + seeded(index, seed + 3) * 5,
        drift: (seeded(index, seed + 4) - 0.5) * 90,
        spin: 200 + seeded(index, seed + 5) * 240,
      })),
    [seed],
  );

  return (
    <div className="backdrop" aria-hidden="true">
      <svg className="backdrop-ridge" viewBox="0 0 1440 620" preserveAspectRatio="none">
        <path className="ridge-far" d="M0 452 C150 404 258 424 372 392 C486 360 566 404 690 392 C814 380 916 416 1046 400 C1176 384 1320 412 1440 396 L1440 620 L0 620 Z" />
        <path className="ridge-mid" d="M0 506 C196 468 310 494 442 470 C574 446 668 484 800 476 C932 468 1058 500 1192 488 C1300 478 1382 492 1440 486 L1440 620 L0 620 Z" />
        <path className="ridge-near" d="M0 566 C232 540 366 556 508 546 C650 536 796 562 942 556 C1088 550 1266 566 1440 558 L1440 620 L0 620 Z" />
      </svg>

      <svg className="backdrop-branch" viewBox="0 0 860 360" preserveAspectRatio="xMaxYMin meet">
        <g className="branch-ink">
          <path d={branchPath(MAIN_BRANCH, 9, 1.4)} />
          {TWIGS.map((twig, index) => (
            <path key={index} d={branchPath(twig.points, twig.width, 0.5)} style={{ animationDelay: `${120 + index * 70}ms` }} />
          ))}
        </g>
        <g className="branch-blossoms">
          {BLOSSOMS.map((blossom, index) => (
            <g key={index} className="blossom" style={{ animationDelay: `${320 + index * 60}ms` }}>
              <Blossom x={blossom.x} y={blossom.y} scale={blossom.scale} />
            </g>
          ))}
        </g>
      </svg>

      <div className="backdrop-mist backdrop-mist-a" />
      <div className="backdrop-mist backdrop-mist-b" />

      <div className="backdrop-petals">
        {petals.map((petal, index) => (
          <span
            key={index}
            className="petal"
            style={{
              left: `${petal.left}%`,
              width: `${petal.size}px`,
              height: `${petal.size * 0.68}px`,
              animationDelay: `${petal.delay}s`,
              animationDuration: `${petal.duration}s`,
              ['--drift' as string]: `${petal.drift}px`,
              ['--spin' as string]: `${petal.spin}deg`,
            }}
          />
        ))}
      </div>
    </div>
  );
}
