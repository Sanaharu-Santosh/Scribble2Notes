import { type RefObject, useLayoutEffect, useState } from "react";

/**
 * Ratio between the image as rendered on screen and the source pixels the
 * backend measured against.
 *
 * Every overlay coordinate is multiplied by this, which is what keeps the text
 * layer glued to the ink when the window resizes or the layout reflows.
 */
export function useRenderedScale(
  ref: RefObject<HTMLImageElement>,
  sourceWidth: number | undefined,
): number {
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || !sourceWidth) return;

    const update = () => setScale(element.clientWidth / sourceWidth);
    update();

    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, sourceWidth]);

  return scale;
}
