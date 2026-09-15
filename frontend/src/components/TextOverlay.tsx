import { useLayoutEffect, useRef } from "react";

import type { Quad, TextRegion } from "../types";

/**
 * The Lens trick, in one component.
 *
 * The photo is never touched. For each detected region we place a real <span>
 * of real text at the region's coordinates, rotate it to match the slant of the
 * writing, then stretch it horizontally so its width matches the ink beneath.
 * The text is transparent, so what the user sees is their own photo — but what
 * the browser sees is selectable text, which is why copy/paste, find-in-page and
 * screen readers all just work.
 *
 * The stretch step is what makes selection highlights line up. Rather than
 * guessing a font that happens to match the handwriting, we render any font at
 * the right height and scale it on the x-axis to the measured target width.
 */

function quadWidth(quad: Quad): number {
  const [topLeft, topRight] = quad.points;
  return Math.hypot(topRight.x - topLeft.x, topRight.y - topLeft.y);
}

function confidenceColor(confidence: number): string {
  // 0 -> red, 1 -> green. Only shown in "show boxes" debug mode, where the
  // point is spotting the regions an engine is unsure about at a glance.
  return `hsl(${Math.round(confidence * 120)}, 70%, 45%)`;
}

interface Props {
  regions: TextRegion[];
  scale: number;
  showBoxes: boolean;
}

export function TextOverlay({ regions, scale, showBoxes }: Props) {
  const spans = useRef(new Map<string, HTMLSpanElement>());

  useLayoutEffect(() => {
    const entries = regions
      .map((region) => ({ region, element: spans.current.get(region.id) }))
      .filter((entry): entry is { region: TextRegion; element: HTMLSpanElement } =>
        Boolean(entry.element),
      );

    // Batch: clear transforms, then read every width in one layout flush, then
    // write every transform. Interleaving reads and writes here would force a
    // reflow per region, which is visible on a page with a hundred lines.
    for (const { element } of entries) element.style.transform = "";
    const naturalWidths = entries.map(({ element }) => element.getBoundingClientRect().width);

    entries.forEach(({ region, element }, index) => {
      const target = quadWidth(region.quad) * scale;
      const natural = naturalWidths[index];
      const stretch = natural > 0 ? target / natural : 1;
      element.style.transform = `rotate(${region.quad.angle_deg}deg) scaleX(${stretch})`;
    });
  }, [regions, scale]);

  return (
    <div className="overlay" aria-label="Recognized text layer">
      {regions.map((region) => {
        const [topLeft] = region.quad.points;
        return (
          <span
            key={region.id}
            ref={(element) => {
              if (element) spans.current.set(region.id, element);
              else spans.current.delete(region.id);
            }}
            className="overlay-text"
            title={`${region.text} — ${Math.round(region.confidence * 100)}% confident`}
            style={{
              left: `${topLeft.x * scale}px`,
              top: `${topLeft.y * scale}px`,
              fontSize: `${region.quad.height * scale}px`,
              outline: showBoxes ? `1px solid ${confidenceColor(region.confidence)}` : undefined,
            }}
          >
            {region.text}
          </span>
        );
      })}
    </div>
  );
}
